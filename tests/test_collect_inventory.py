# pyright: basic
from __future__ import annotations

import importlib.machinery
import importlib.util
import io
import json
import os
import plistlib
import stat
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock


SCRIPT = (
    Path(__file__).parents[1]
    / "skills"
    / "system-and-demo"
    / "maintain-mac-dev-environment"
    / "scripts"
    / "collect_inventory.py"
)
SKILL = SCRIPT.parents[1] / "SKILL.md"
SPEC = importlib.util.spec_from_file_location("collect_inventory", SCRIPT)
assert SPEC and SPEC.loader
assert isinstance(SPEC.loader, importlib.machinery.SourceFileLoader)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class CollectInventoryTests(unittest.TestCase):
    def test_redacts_home_hostname_and_credentials(self) -> None:
        token_like = "ghp_" + "a" * 24
        value = (
            f'/Users/alice/project host.local alice DEMO_API_KEY=secret-value '
            f'DEMO_SECRET="secret with spaces" '
            f'"ACCESS_TOKEN": "json-secret" Authorization: Bearer abcdefghijklmnop '
            f'postgresql://user:password@db.local/example {token_like}'
        )
        actual = MODULE.redact_text(value, Path("/Users/alice"), "host.local", "alice")
        self.assertEqual(
            actual,
            '$HOME/project $HOST $USER DEMO_API_KEY=<redacted> '
            'DEMO_SECRET=<redacted> '
            '"ACCESS_TOKEN": "<redacted>" Authorization: Bearer <redacted> '
            'postgresql://user:<redacted>@db.local/example <redacted-token>',
        )

    def test_redacts_dictionary_keys(self) -> None:
        self.assertEqual(
            MODULE.redact_data({"DEMO_API_TOKEN=secret": "safe"}),
            {"DEMO_API_TOKEN=<redacted>": "safe"},
        )

    def test_rejects_non_allowlisted_commands(self) -> None:
        with self.assertRaisesRegex(ValueError, "not allowlisted"):
            MODULE.run_safe(["rm", "-rf", "/tmp/example"])

    def test_rejects_mutating_subcommands_of_allowlisted_tools(self) -> None:
        with self.assertRaisesRegex(ValueError, "not an approved read-only invocation"):
            MODULE.run_safe(["brew", "cleanup"])
        with self.assertRaisesRegex(ValueError, "not an approved read-only invocation"):
            MODULE.run_safe(["docker", "system", "prune"])

    def test_policy_rejects_unknown_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            policy_path = Path(temp_dir).resolve() / "policy.json"
            policy_path.write_text(json.dumps({"schema_version": 1, "scan_processes": True}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "unknown policy fields"):
                MODULE.load_policy(policy_path)

    def test_policy_rejects_string_boolean(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            policy_path = Path(temp_dir).resolve() / "policy.json"
            policy_path.write_text(
                json.dumps({"schema_version": 1, "scan_project_pins": "false"}),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "scan_project_pins must be a boolean"):
                MODULE.load_policy(policy_path)

    def test_policy_rejects_boolean_schema_version(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            policy_path = Path(temp_dir).resolve() / "policy.json"
            policy_path.write_text(json.dumps({"schema_version": True}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "unsupported policy schema_version"):
                MODULE.load_policy(policy_path)

    def test_policy_rejects_relative_broad_and_symlink_project_roots(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir).resolve()
            real_root = base / "projects"
            real_root.mkdir()
            symlink_root = base / "linked-projects"
            symlink_root.symlink_to(real_root, target_is_directory=True)
            symlink_ancestor_root = symlink_root / "nested"
            policy_path = base / "policy.json"

            for project_root in (
                "relative/projects",
                str(Path.home()),
                str(Path.home().parent),
                "/",
                str(symlink_root),
                str(symlink_ancestor_root),
            ):
                policy_path.write_text(
                    json.dumps({"schema_version": 1, "project_roots": [project_root]}),
                    encoding="utf-8",
                )
                with self.subTest(project_root=project_root), self.assertRaises(ValueError):
                    MODULE.load_policy(policy_path)

    def test_relative_xdg_config_home_is_ignored(self) -> None:
        with mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": "relative/config"}):
            self.assertEqual(
                MODULE.default_policy_path(),
                Path.home() / ".config" / "skillctl" / "maintain-mac-dev-environment.json",
            )

    def test_application_inventory_is_opt_in(self) -> None:
        self.assertFalse(MODULE.DEFAULT_POLICY["include_application_inventory"])

    def test_policy_reader_refuses_symlinks_and_fifos_without_blocking(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir).resolve()
            target = base / "policy-target.json"
            target.write_text(json.dumps({"schema_version": 1}), encoding="utf-8")
            link = base / "policy-link.json"
            link.symlink_to(target)
            with self.assertRaisesRegex(ValueError, "symlink components"):
                MODULE.load_policy(link)

            broken_link = base / "broken-policy-link.json"
            broken_link.symlink_to(base / "missing-target.json")
            with self.assertRaisesRegex(ValueError, "symlink components"):
                MODULE.load_policy(broken_link)

            fifo = base / "policy.fifo"
            os.mkfifo(fifo)
            with self.assertRaisesRegex(ValueError, "bounded regular file"):
                MODULE.load_policy(fifo)

    def test_project_pin_scan_is_bounded_and_prunes_dependencies(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir).resolve()
            (root / "app").mkdir()
            (root / "app" / ".nvmrc").write_text("v24.5.0\n", encoding="utf-8")
            (root / "app" / "node_modules").mkdir()
            (root / "app" / "node_modules" / ".nvmrc").write_text("v1\n", encoding="utf-8")
            (root / "app" / ".tool-versions").write_text("x" * 1001, encoding="utf-8")
            sensitive = root / "sensitive.txt"
            sensitive.write_text("do-not-read\n", encoding="utf-8")
            (root / "app" / ".python-version").symlink_to(sensitive)
            policy = {
                **MODULE.DEFAULT_POLICY,
                "project_roots": [str(root)],
                "scan_project_pins": True,
            }
            self.assertEqual(
                MODULE.collect_project_pins(policy),
                [{"root": "root-1", "relative_path": "app/.nvmrc", "value": "v24.5.0"}],
            )

    def test_shadowed_allowlisted_executable_is_not_run(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            executable = Path(temp_dir).resolve() / "brew"
            marker = Path(temp_dir).resolve() / "executed"
            executable.write_text(f"#!/bin/sh\ntouch {marker}\n", encoding="utf-8")
            executable.chmod(0o755)
            previous_path = os.environ.get("PATH", "")
            os.environ["PATH"] = f"{temp_dir}:{previous_path}"
            try:
                result = MODULE.run_safe(["brew", "--version"])
            finally:
                os.environ["PATH"] = previous_path
            self.assertEqual(result["status"], "untrusted-path")
            self.assertFalse(marker.exists())

    def test_homebrew_entrypoint_requires_a_matching_formula_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir).resolve()
            link_dir = base / "bin"
            target_dir = base / "Cellar" / "node" / "1.0" / "bin"
            link_dir.mkdir()
            target_dir.mkdir(parents=True)
            entrypoint = link_dir / "node"
            target = target_dir / "node"
            entrypoint.write_text("#!/bin/sh\n", encoding="utf-8")
            entrypoint.chmod(0o755)
            target.write_text("#!/bin/sh\n", encoding="utf-8")
            target.chmod(0o755)

            with mock.patch.multiple(
                MODULE,
                HOMEBREW_LINK_DIRS=(link_dir,),
                HOMEBREW_CELLAR_ROOTS=(base / "Cellar",),
                HOMEBREW_FORMULA_PATTERNS={"node": ("node", "node@*")},
            ):
                self.assertFalse(MODULE.trusted_executable_path(entrypoint, entrypoint, "node"))
                entrypoint.unlink()
                entrypoint.symlink_to(target)
                self.assertTrue(MODULE.trusted_executable_path(entrypoint, target, "node"))

                unrelated = base / "Cellar" / "unrelated" / "1.0" / "bin" / "node"
                unrelated.parent.mkdir(parents=True)
                unrelated.write_text("#!/bin/sh\n", encoding="utf-8")
                unrelated.chmod(0o755)
                self.assertFalse(MODULE.trusted_executable_path(entrypoint, unrelated, "node"))

    def test_accepts_only_mapped_homebrew_brew_targets(self) -> None:
        self.assertEqual(
            MODULE.HOMEBREW_BREW_TARGETS,
            {
                Path("/opt/homebrew/bin/brew"): frozenset({Path("/opt/homebrew/bin/brew")}),
                Path("/usr/local/bin/brew"): frozenset(
                    {
                        Path("/usr/local/bin/brew"),
                        Path("/usr/local/Homebrew/bin/brew"),
                    }
                ),
            },
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir).resolve()
            entrypoint = base / "bin" / "brew"
            target = base / "Homebrew" / "bin" / "brew"
            wrong_target = base / "OtherHomebrew" / "bin" / "brew"
            entrypoint.parent.mkdir()
            target.parent.mkdir(parents=True)
            wrong_target.parent.mkdir(parents=True)
            target.write_text("#!/bin/sh\n", encoding="utf-8")
            target.chmod(0o755)
            wrong_target.write_text("#!/bin/sh\n", encoding="utf-8")
            wrong_target.chmod(0o755)
            entrypoint.symlink_to(target)

            with mock.patch.object(
                MODULE,
                "HOMEBREW_BREW_TARGETS",
                {entrypoint: frozenset({entrypoint, target})},
            ):
                self.assertTrue(MODULE.trusted_executable_path(entrypoint, target, "brew"))
                self.assertFalse(MODULE.trusted_executable_path(entrypoint, wrong_target, "brew"))

    def test_supported_app_symlink_can_live_in_a_homebrew_link_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir).resolve()
            link_dir = base / "bin"
            app_root = base / "Applications" / "OrbStack.app"
            target = app_root / "Contents" / "MacOS" / "docker-tools"
            link_dir.mkdir()
            target.parent.mkdir(parents=True)
            target.write_text("binary\n", encoding="utf-8")
            target.chmod(0o755)
            entrypoint = link_dir / "docker"
            entrypoint.symlink_to(target)

            with mock.patch.multiple(
                MODULE,
                APP_EXECUTABLE_MAPPINGS={"docker": {entrypoint: frozenset({target})}},
            ):
                self.assertTrue(MODULE.trusted_executable_path(entrypoint, target, "docker"))
                wrong_target = app_root / "Contents" / "MacOS" / "uninstall"
                wrong_target.write_text("binary\n", encoding="utf-8")
                wrong_target.chmod(0o755)
                self.assertFalse(MODULE.trusted_executable_path(entrypoint, wrong_target, "docker"))

    def test_safe_environment_does_not_forward_credentials(self) -> None:
        previous = os.environ.get("TEST_API_KEY")
        os.environ["TEST_API_KEY"] = "secret"
        try:
            self.assertNotIn("TEST_API_KEY", MODULE.safe_environment())
        finally:
            if previous is None:
                os.environ.pop("TEST_API_KEY", None)
            else:
                os.environ["TEST_API_KEY"] = previous

    def test_collect_system_probes_the_configured_shell_path(self) -> None:
        calls: list[list[str]] = []

        def fake_run_safe(args: list[str]) -> dict[str, object]:
            calls.append(args)
            output = "14.5" if args[0] == "sw_vers" else "zsh 5.9"
            return {"ok": True, "status": "ok", "returncode": 0, "stdout": output}

        with (
            mock.patch.dict(os.environ, {"SHELL": "/bin/zsh"}),
            mock.patch.object(MODULE, "run_safe", side_effect=fake_run_safe),
        ):
            result = MODULE.collect_system()

        self.assertIn(["/bin/zsh", "--version"], calls)
        self.assertNotIn(["zsh", "--version"], calls)
        self.assertEqual(result["shell"], "/bin/zsh")
        self.assertEqual(result["shell_version"], "zsh 5.9")

    def test_homebrew_casks_follow_application_inventory_opt_in(self) -> None:
        calls: list[list[str]] = []

        def fake_run_safe(args: list[str]) -> dict[str, object]:
            calls.append(args)
            return {"ok": True, "status": "ok", "returncode": 0, "stdout": ""}

        with (
            mock.patch.object(MODULE.shutil, "which", return_value="/opt/homebrew/bin/brew"),
            mock.patch.object(MODULE, "run_safe", side_effect=fake_run_safe),
        ):
            result = MODULE.collect_brew(False)
            self.assertEqual(result["casks"], [])
            self.assertEqual(result["casks_status"], "not-requested")
            self.assertNotIn(["brew", "list", "--cask"], calls)

            calls.clear()
            MODULE.collect_brew(True)
            self.assertIn(["brew", "list", "--cask"], calls)

    def test_failed_homebrew_services_output_is_not_parsed(self) -> None:
        def fake_run_safe(args: list[str]) -> dict[str, object]:
            if args == ["brew", "services", "list"]:
                return {
                    "ok": False,
                    "status": "nonzero-exit",
                    "returncode": 1,
                    "stdout": "Error: service command failed\npostgresql started",
                }
            return {"ok": True, "status": "ok", "returncode": 0, "stdout": ""}

        with (
            mock.patch.object(MODULE.shutil, "which", return_value="/opt/homebrew/bin/brew"),
            mock.patch.object(MODULE, "run_safe", side_effect=fake_run_safe),
        ):
            result = MODULE.collect_brew(False)

        self.assertEqual(result["services"], [])
        self.assertEqual(result["services_status"], "nonzero-exit")

    def test_reads_global_node_package_metadata_without_executing_package_code(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            prefix = Path(temp_dir).resolve()
            package = prefix / "lib" / "node_modules" / "@example" / "tool"
            package.mkdir(parents=True)
            (package / "package.json").write_text(
                json.dumps({"name": "@example/tool", "version": "1.2.3"}),
                encoding="utf-8",
            )
            self.assertEqual(
                MODULE.node_packages_in_prefix(prefix),
                [{"name": "@example/tool", "version": "1.2.3"}],
            )

    def test_skips_symlinked_global_node_packages(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir).resolve()
            prefix = base / "prefix"
            scope = prefix / "lib" / "node_modules" / "@private"
            scope.mkdir(parents=True)
            private_package = base / "private-project"
            private_package.mkdir()
            (private_package / "package.json").write_text(
                json.dumps({"name": "@private/project-secret", "version": "1.0.0"}),
                encoding="utf-8",
            )
            (scope / "linked-tool").symlink_to(private_package, target_is_directory=True)
            self.assertEqual(MODULE.node_packages_in_prefix(prefix), [])

    def test_skips_non_object_and_symlink_ancestor_node_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir).resolve()
            prefix = base / "prefix"
            package = prefix / "lib" / "node_modules" / "tool"
            package.mkdir(parents=True)
            (package / "package.json").write_text("[]", encoding="utf-8")
            self.assertEqual(MODULE.node_packages_in_prefix(prefix), [])

            real_prefix = base / "real-prefix"
            real_package = real_prefix / "lib" / "node_modules" / "private-tool"
            real_package.mkdir(parents=True)
            (real_package / "package.json").write_text(
                json.dumps({"name": "private-tool", "version": "1.0.0"}),
                encoding="utf-8",
            )
            linked_prefix = base / "linked-prefix"
            linked_prefix.symlink_to(real_prefix, target_is_directory=True)
            self.assertEqual(MODULE.node_packages_in_prefix(linked_prefix), [])

            prefix_with_linked_lib = base / "prefix-with-linked-lib"
            prefix_with_linked_lib.mkdir()
            (prefix_with_linked_lib / "lib").symlink_to(real_prefix / "lib", target_is_directory=True)
            self.assertEqual(MODULE.node_packages_in_prefix(prefix_with_linked_lib), [])

    def test_application_metadata_is_bounded_and_nofollow(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir).resolve()
            app = base / "Example.app"
            contents = app / "Contents"
            contents.mkdir(parents=True)
            info = contents / "Info.plist"
            info.write_bytes(plistlib.dumps({"CFBundleShortVersionString": "1.2.3"}))
            self.assertEqual(MODULE.application_version(app), "1.2.3")

            private_info = base / "private.plist"
            private_info.write_bytes(plistlib.dumps({"CFBundleShortVersionString": "secret"}))
            info.unlink()
            info.symlink_to(private_info)
            self.assertIsNone(MODULE.application_version(app))

    def test_postgres_inventory_skips_symlinked_clusters(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir).resolve()
            var_root = base / "var"
            real_cluster = var_root / "postgresql@16"
            real_cluster.mkdir(parents=True)
            (real_cluster / "PG_VERSION").write_text("16\n", encoding="ascii")

            external_cluster = base / "external-cluster"
            external_cluster.mkdir()
            (external_cluster / "PG_VERSION").write_text("15\n", encoding="ascii")
            (var_root / "postgresql@15").symlink_to(external_cluster, target_is_directory=True)

            with mock.patch.object(MODULE, "POSTGRES_VAR_ROOTS", (var_root,)):
                self.assertEqual(
                    MODULE.collect_postgres(False),
                    [
                        {
                            "cluster": "postgresql@16",
                            "major_version": "16",
                            "data_directory_present": True,
                            "size_bytes": None,
                        }
                    ],
                )

    def test_snapshot_output_is_owner_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir).resolve() / "state" / "inventory.json"
            output.parent.mkdir()
            output.write_text("previous\n", encoding="utf-8")
            output.chmod(0o644)
            MODULE.write_private_output(output, "{}")
            self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o600)
            self.assertEqual(output.read_text(encoding="utf-8"), "{}\n")

    @unittest.skipUnless(hasattr(os, "O_NOFOLLOW"), "platform does not support O_NOFOLLOW")
    def test_snapshot_output_refuses_symlinks(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir).resolve() / "target.json"
            target.write_text("original\n", encoding="utf-8")
            link = Path(temp_dir).resolve() / "inventory.json"
            link.symlink_to(target)
            with self.assertRaises(ValueError):
                MODULE.write_private_output(link, "replacement")
            self.assertEqual(target.read_text(encoding="utf-8"), "original\n")

    def test_snapshot_output_refuses_hardlinks_and_special_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir).resolve()
            target = base / "target.json"
            target.write_text("original\n", encoding="utf-8")
            hardlink = base / "hardlink.json"
            os.link(target, hardlink)
            with self.assertRaisesRegex(ValueError, "hard-linked"):
                MODULE.write_private_output(hardlink, "replacement")
            self.assertEqual(target.read_text(encoding="utf-8"), "original\n")

            fifo = base / "inventory.fifo"
            os.mkfifo(fifo)
            with self.assertRaisesRegex(ValueError, "regular file"):
                MODULE.write_private_output(fifo, "replacement")

    def test_snapshot_output_refuses_relative_paths_and_symlink_parents(self) -> None:
        with self.assertRaisesRegex(ValueError, "absolute file path"):
            MODULE.write_private_output(Path("relative.json"), "{}")

        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir).resolve()
            real_parent = base / "real"
            real_parent.mkdir()
            linked_parent = base / "linked"
            linked_parent.symlink_to(real_parent, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "parent must not contain symlink components"):
                MODULE.write_private_output(linked_parent / "inventory.json", "{}")

            with self.assertRaisesRegex(ValueError, "parent must not contain symlink components"):
                MODULE.write_private_output(linked_parent / "nested" / "inventory.json", "{}")
            self.assertFalse((real_parent / "nested").exists())

    def test_main_withholds_local_paths_from_output_errors(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir).resolve()
            target = base / "target.json"
            target.write_text("original\n", encoding="utf-8")
            output = base / "private-output.json"
            output.symlink_to(target)
            stderr = io.StringIO()
            with (
                mock.patch.object(MODULE, "collect_inventory", return_value={}),
                redirect_stderr(stderr),
            ):
                exit_code = MODULE.main(
                    ["--policy", str(base / "missing-policy.json"), "--output", str(output)]
                )
            self.assertEqual(exit_code, 2)
            self.assertIn("local details withheld", stderr.getvalue())
            self.assertNotIn(str(output), stderr.getvalue())

    def test_main_withholds_unexpected_exceptions_and_invalid_arguments(self) -> None:
        stderr = io.StringIO()
        with (
            mock.patch.object(MODULE, "collect_inventory", side_effect=RuntimeError("/Users/alice/private")),
            redirect_stderr(stderr),
        ):
            exit_code = MODULE.main(["--policy", "/private/tmp/missing-policy.json"])
        self.assertEqual(exit_code, 2)
        self.assertNotIn("/Users/alice/private", stderr.getvalue())
        self.assertNotIn("Traceback", stderr.getvalue())

        stderr = io.StringIO()
        with redirect_stderr(stderr):
            exit_code = MODULE.main(["--unknown", "/Users/alice/private-argument"])
        self.assertEqual(exit_code, 2)
        self.assertNotIn("/Users/alice/private-argument", stderr.getvalue())
        self.assertNotIn("Traceback", stderr.getvalue())

    def test_main_preserves_an_explicitly_empty_argument_list(self) -> None:
        arguments = MODULE.argparse.Namespace(
            policy=Path("/private/tmp/missing-policy.json"),
            output=None,
            deep=False,
            pretty=False,
        )
        stdout = io.StringIO()
        with (
            mock.patch.object(MODULE.sys, "argv", ["collector", "--unexpected-host-argument"]),
            mock.patch.object(MODULE, "parse_args", return_value=arguments) as parse_args,
            mock.patch.object(MODULE, "load_policy", return_value=MODULE.DEFAULT_POLICY),
            mock.patch.object(MODULE, "collect_inventory", return_value={}),
            redirect_stdout(stdout),
        ):
            self.assertEqual(MODULE.main([]), 0)
        parse_args.assert_called_once_with([])

    def test_skill_invocation_is_independent_of_the_working_directory(self) -> None:
        skill_text = SKILL.read_text(encoding="utf-8")
        self.assertIn("SKILL_MD_PATH", skill_text)
        self.assertIn('python3 "$SKILL_DIR/scripts/collect_inventory.py" --pretty', skill_text)
        self.assertNotIn("python3 scripts/collect_inventory.py --pretty", skill_text)


if __name__ == "__main__":
    unittest.main()
