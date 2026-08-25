from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType
from typing import Any, cast, final, override
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
MANAGER_PATH = (
    ROOT
    / "skills"
    / "agent-infra"
    / "trellis-lite"
    / "scripts"
    / "manage_trellis_lite.py"
)
TASK_REUSE_MANAGER_PATH = (
    ROOT
    / "skills"
    / "agent-infra"
    / "trellis-task-reuse"
    / "scripts"
    / "manage_trellis_task_reuse.py"
)


def load_manager() -> ModuleType:
    spec = importlib.util.spec_from_file_location("trellis_lite", MANAGER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_task_reuse_manager() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "trellis_task_reuse_for_lite_tests", TASK_REUSE_MANAGER_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


MANAGER = load_manager()
TASK_REUSE_MANAGER = load_task_reuse_manager()


@final
class TestTrellisLite(unittest.TestCase):
    temporary_directory: tempfile.TemporaryDirectory[str]  # pyright: ignore[reportUninitializedInstanceVariable]
    root: Path  # pyright: ignore[reportUninitializedInstanceVariable]
    resources: Path  # pyright: ignore[reportUninitializedInstanceVariable]
    specs: tuple[Any, ...]  # pyright: ignore[reportUninitializedInstanceVariable, reportExplicitAny]

    @override
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)
        self.resources = self.root / "resources"
        baseline = b"heavy workflow\n"
        overlay = b"lite workflow\n"
        optional_baseline = b"fix and recheck\n"
        optional_overlay = b"report once\n"
        file_spec = MANAGER.FileSpec
        sha256_bytes = MANAGER.sha256_bytes
        self.specs = (
            file_spec(
                ".trellis/workflow.md",
                sha256_bytes(baseline),
                sha256_bytes(overlay),
                required=True,
            ),
            file_spec(
                ".omp/skills/trellis-check/SKILL.md",
                sha256_bytes(optional_baseline),
                sha256_bytes(optional_overlay),
            ),
        )
        (self.resources / ".trellis").mkdir(parents=True)
        (self.resources / ".trellis/workflow.md").write_bytes(overlay)
        (self.resources / ".omp/skills/trellis-check").mkdir(parents=True)
        (self.resources / ".omp/skills/trellis-check/SKILL.md").write_bytes(
            optional_overlay
        )

    def create_project(self, *, optional: bool = True) -> Path:
        project = self.root / "project"
        (project / ".trellis").mkdir(parents=True)
        (project / ".trellis/.version").write_text("0.6.7", encoding="utf-8")
        (project / ".trellis/workflow.md").write_bytes(b"heavy workflow\n")
        if optional:
            (project / ".omp/skills/trellis-check").mkdir(parents=True)
            (project / ".omp/skills/trellis-check/SKILL.md").write_bytes(
                b"fix and recheck\n"
            )
        return project

    def apply(self, project: Path) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            MANAGER.apply_project(
                project,
                self.specs,
                self.resources,
                run_prerequisite=False,
            ),
        )

    def inspect(self, project: Path) -> dict[str, Any]:
        return cast(dict[str, Any], MANAGER.inspect_project(project, self.specs))

    def test_apply_is_idempotent_and_writes_verified_metadata(self) -> None:
        project = self.create_project()

        first = self.apply(project)
        metadata_path = project / MANAGER.METADATA_REL_PATH
        first_metadata = metadata_path.read_bytes()
        first_mtime = metadata_path.stat().st_mtime_ns
        second = self.apply(project)

        self.assertEqual(first["status"], "applied")
        self.assertEqual(second["status"], "applied")
        self.assertEqual(first_metadata, metadata_path.read_bytes())
        self.assertEqual(first_mtime, metadata_path.stat().st_mtime_ns)
        metadata = json.loads(first_metadata)
        self.assertEqual(metadata["overlay_id"], "trellis-lite")
        self.assertEqual(metadata["overlay_version"], "1.0.12")
        self.assertEqual(metadata["verification"]["status"], "verified")

    def test_check_is_read_only_and_reports_recognized_baseline(self) -> None:
        project = self.create_project()
        before = (project / ".trellis/workflow.md").read_bytes()

        report = self.inspect(project)

        self.assertEqual(report["status"], "needs_apply")
        self.assertEqual(before, (project / ".trellis/workflow.md").read_bytes())
        self.assertFalse((project / MANAGER.METADATA_REL_PATH).exists())

    def test_optional_platform_files_may_be_absent(self) -> None:
        project = self.create_project(optional=False)

        report = self.apply(project)

        self.assertEqual(report["status"], "applied")
        optional = next(
            item
            for item in report["files"]
            if item["path"] == ".omp/skills/trellis-check/SKILL.md"
        )
        self.assertEqual(optional["status"], "absent")

    def test_unknown_local_content_fails_closed(self) -> None:
        project = self.create_project()
        workflow = project / ".trellis/workflow.md"
        workflow.write_text("local customization\n", encoding="utf-8")

        with self.assertRaises(MANAGER.LiteError):
            self.apply(project)

        self.assertEqual(workflow.read_text(encoding="utf-8"), "local customization\n")

    def test_unknown_trellis_version_is_read_only_and_unsupported(self) -> None:
        project = self.create_project()
        version = project / ".trellis/.version"
        version.write_text("9.9.9", encoding="utf-8")
        workflow = project / ".trellis/workflow.md"
        before = workflow.read_bytes()

        report = MANAGER.inspect_project(project)

        self.assertEqual(report["status"], "unsupported")
        self.assertEqual(workflow.read_bytes(), before)
        self.assertFalse((project / MANAGER.METADATA_REL_PATH).exists())

    def test_unknown_trellis_version_apply_reports_unsupported_without_writes(
        self,
    ) -> None:
        project = self.create_project()
        (project / ".trellis/.version").write_text("9.9.9", encoding="utf-8")
        workflow = project / ".trellis/workflow.md"
        before = workflow.read_bytes()

        result = subprocess.run(
            [
                sys.executable,
                str(MANAGER_PATH),
                "apply",
                "--project",
                str(project),
                "--json",
            ],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stdout)["status"], "unsupported")
        self.assertEqual(workflow.read_bytes(), before)
        self.assertFalse((project / MANAGER.METADATA_REL_PATH).exists())

    def test_symlinked_managed_parent_cannot_write_outside_project(self) -> None:
        project = self.create_project(optional=False)
        outside = self.root / "outside"
        outside_target = outside / "skills/trellis-check/SKILL.md"
        outside_target.parent.mkdir(parents=True)
        outside_target.write_bytes(b"fix and recheck\n")
        (project / ".omp").symlink_to(outside, target_is_directory=True)

        with self.assertRaisesRegex(MANAGER.LiteError, "symlinked project path"):
            self.apply(project)

        self.assertEqual(outside_target.read_bytes(), b"fix and recheck\n")
        self.assertEqual(
            (project / ".trellis/workflow.md").read_bytes(), b"heavy workflow\n"
        )
        self.assertFalse((project / MANAGER.METADATA_REL_PATH).exists())

    def test_symlinked_metadata_parent_fails_before_managed_file_writes(self) -> None:
        project = self.create_project(optional=False)
        outside = self.root / "outside-overlays"
        outside.mkdir()
        (project / ".trellis/.overlays").symlink_to(
            outside, target_is_directory=True
        )

        with self.assertRaisesRegex(MANAGER.LiteError, "symlinked project path"):
            self.apply(project)

        self.assertEqual(
            (project / ".trellis/workflow.md").read_bytes(), b"heavy workflow\n"
        )
        self.assertEqual(list(outside.iterdir()), [])

    def test_lite_conflict_preflights_before_prerequisite_writes(self) -> None:
        project = self.create_project()
        conflicted = project / ".omp/skills/trellis-check/SKILL.md"
        conflicted.write_bytes(b"local customization\n")
        prerequisite_report = {"status": "needs_apply", "files": []}

        with (
            patch.object(
                MANAGER,
                "inspect_task_reuse",
                return_value=prerequisite_report,
            ),
            patch.object(MANAGER, "apply_task_reuse") as prerequisite_apply,
            self.assertRaisesRegex(MANAGER.LiteError, "unrecognized local content"),
        ):
            MANAGER.apply_project(
                project,
                self.specs,
                self.resources,
                run_prerequisite=True,
            )

        prerequisite_apply.assert_not_called()
        self.assertEqual(
            (project / ".trellis/workflow.md").read_bytes(), b"heavy workflow\n"
        )
        self.assertEqual(conflicted.read_bytes(), b"local customization\n")

    def test_shipped_resource_hashes_match_manifest(self) -> None:
        for version, patch_set in MANAGER.PATCH_SETS.items():
            with self.subTest(version=version):
                for spec in patch_set.files:
                    if spec.replacements:
                        continue
                    resource = patch_set.resource_root / spec.path
                    self.assertTrue(resource.is_file(), f"{version}:{spec.path}")
                    self.assertEqual(
                        MANAGER.sha256_bytes(resource.read_bytes()),
                        spec.overlay_sha256,
                        f"{version}:{spec.path}",
                    )

    def test_production_patch_sets_manage_the_exact_policy_surface(self) -> None:
        expected_067 = {
            ".trellis/workflow.md",
            ".omp/extensions/trellis/index.ts",
            ".omp/skills/trellis-brainstorm/SKILL.md",
            ".omp/skills/trellis-check/SKILL.md",
            ".omp/agents/trellis-check.md",
            ".omp/commands/trellis-continue.md",
            ".agents/skills/trellis-brainstorm/SKILL.md",
            ".agents/skills/trellis-start/SKILL.md",
            ".agents/skills/trellis-check/SKILL.md",
            ".agents/skills/trellis-continue/SKILL.md",
            ".codex/agents/trellis-check.toml",
            ".codex/hooks/inject-workflow-state.py",
            ".trellis/scripts/common/config.py",
            ".trellis/scripts/common/workflow_phase.py",
        }
        expected_0614 = {
            ".trellis/workflow.md",
            ".omp/extensions/trellis/index.ts",
            ".omp/skills/trellis-brainstorm/SKILL.md",
            ".omp/skills/trellis-check/SKILL.md",
            ".omp/agents/trellis-check.md",
            ".omp/commands/trellis-continue.md",
            ".agents/skills/trellis-brainstorm/SKILL.md",
            ".agents/skills/trellis-start/SKILL.md",
            ".agents/skills/trellis-check/SKILL.md",
            ".agents/skills/trellis-continue/SKILL.md",
            ".codex/agents/trellis-check.toml",
        }

        self.assertEqual(
            {spec.path for spec in MANAGER.PATCH_SETS["0.6.7"].files},
            expected_067,
        )
        self.assertEqual(
            {spec.path for spec in MANAGER.PATCH_SETS["0.6.14"].files},
            expected_0614,
        )

    def test_recognized_overlay_revision_upgrades_idempotently(self) -> None:
        project = self.create_project(optional=False)
        target = project / ".trellis/workflow.md"
        target.write_bytes(b"lite 1.0.6\n")
        desired = b"lite 1.0.7\n"
        resource = self.resources / ".trellis/workflow.md"
        resource.write_bytes(desired)
        file_spec = cast(type, MANAGER.FileSpec)
        spec = file_spec(
            ".trellis/workflow.md",
            MANAGER.sha256_bytes(b"heavy workflow\n"),
            MANAGER.sha256_bytes(desired),
            required=True,
            upgrade_sha256s=(MANAGER.sha256_bytes(b"lite 1.0.6\n"),),
        )

        first = MANAGER.apply_project(
            project,
            (spec,),
            self.resources,
            run_prerequisite=False,
        )
        second = MANAGER.apply_project(
            project,
            (spec,),
            self.resources,
            run_prerequisite=False,
        )

        self.assertEqual(first["status"], "applied")
        self.assertEqual(second["status"], "applied")
        self.assertEqual(target.read_bytes(), desired)

    def test_replacement_overlay_applies_without_a_resource_copy(self) -> None:
        project = self.create_project(optional=False)
        target = project / ".trellis/workflow.md"
        baseline = b'mode = "inline"\n'
        desired = b'mode = "sub-agent"\n'
        target.write_bytes(baseline)
        file_spec = cast(type, MANAGER.FileSpec)
        replacement_spec = cast(type, MANAGER.ReplacementSpec)
        spec = file_spec(
            ".trellis/workflow.md",
            MANAGER.sha256_bytes(baseline),
            MANAGER.sha256_bytes(desired),
            required=True,
            replacements=(
                replacement_spec(b'mode = "inline"', b'mode = "sub-agent"'),
            ),
        )

        first = MANAGER.apply_project(
            project,
            (spec,),
            self.resources,
            run_prerequisite=False,
        )
        second = MANAGER.apply_project(
            project,
            (spec,),
            self.resources,
            run_prerequisite=False,
        )

        self.assertEqual(first["status"], "applied")
        self.assertEqual(second["status"], "applied")
        self.assertEqual(target.read_bytes(), desired)

    def test_recoverable_context_reports_omissions_and_keeps_later_small_file(
        self,
    ) -> None:
        project = self.root / "context-project"
        task = project / ".trellis/tasks/08-09-context-boundary"
        spec_dir = project / ".trellis/spec"
        task.mkdir(parents=True)
        spec_dir.mkdir(parents=True)
        (task / "task.json").write_text(
            json.dumps({"title": "Context boundary", "status": "in_progress"}),
            encoding="utf-8",
        )
        (task / "prd.md").write_text("PRD-CONTENT\n", encoding="utf-8")
        (task / "design.md").write_text(
            "D" * (49 * 1024) + "DESIGN-TAIL\n",
            encoding="utf-8",
        )
        (task / "implement.md").write_text("I" * (46 * 1024), encoding="utf-8")
        (task / "info.md").write_text("N" * (46 * 1024), encoding="utf-8")

        referenced = []
        for name in ("large-a.md", "large-b.md", "large-c.md"):
            path = spec_dir / name
            path.write_text(name + "\n" + "X" * (70 * 1024), encoding="utf-8")
            referenced.append(path)
        small = spec_dir / "later-small.md"
        small.write_text("LATER-SMALL-CONTENT\n", encoding="utf-8")
        forbidden = project / "src/forbidden.ts"
        forbidden.parent.mkdir(parents=True)
        forbidden.write_text("FORBIDDEN-SOURCE-CONTENT\n", encoding="utf-8")
        check_only = spec_dir / "check-only.md"
        check_only.write_text("CHECK-ONLY-CONTENT\n", encoding="utf-8")

        implement_rows = [
            {"file": str(path.relative_to(project)), "reason": "boundary"}
            for path in referenced
        ]
        implement_rows.extend(
            [
                {"file": str(small.relative_to(project)), "reason": "later"},
                {"file": str(forbidden.relative_to(project)), "reason": "reject"},
            ]
        )
        (task / "implement.jsonl").write_text(
            "\n".join(json.dumps(row) for row in implement_rows) + "\n",
            encoding="utf-8",
        )
        (task / "check.jsonl").write_text(
            json.dumps(
                {"file": str(check_only.relative_to(project)), "reason": "check"}
            )
            + "\n",
            encoding="utf-8",
        )

        runner = self.root / "run-context.mjs"
        runner.write_text(
            """import { pathToFileURL } from \"node:url\";
const [extensionPath, projectRoot, taskDir] = process.argv.slice(2);
const extension = await import(pathToFileURL(extensionPath).href);
process.stdout.write(extension.buildTaskContext(projectRoot, taskDir));
""",
            encoding="utf-8",
        )
        for version, patch_set in MANAGER.PATCH_SETS.items():
            with self.subTest(version=version):
                extension_path = (
                    patch_set.resource_root / ".omp/extensions/trellis/index.ts"
                )
                result = subprocess.run(
                    [
                        "node",
                        "--experimental-strip-types",
                        str(runner),
                        str(extension_path),
                        str(project),
                        str(task),
                    ],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                context = result.stdout

                self.assertLessEqual(len(context.encode("utf-8")), 256 * 1024)
                self.assertIn('"title":"Context boundary"', context)
                self.assertIn('"source_of_truth":"disk"', context)
                self.assertIn('"captured_at":', context)
                self.assertIn("inline means complete at capture time", context)
                self.assertIn("LATER-SMALL-CONTENT", context)
                self.assertNotIn("FORBIDDEN-SOURCE-CONTENT", context)
                self.assertNotIn("CHECK-ONLY-CONTENT", context)
                self.assertNotIn("DESIGN-TAIL", context)

                manifest_text = context.split("## File Manifest\n\n", 1)[1].split(
                    "\n\n## Inline File Cache", 1
                )[0]
                manifest = [
                    json.loads(line[2:])
                    for line in manifest_text.splitlines()
                    if line.startswith("- ")
                ]
                by_path = {entry["path"]: entry for entry in manifest}
                design_entry = by_path[
                    ".trellis/tasks/08-09-context-boundary/design.md"
                ]
                self.assertEqual(design_entry["status"], "omitted")
                self.assertTrue(design_entry["required_read"])
                self.assertIn("canonical design exceeds", design_entry["reason"])
                self.assertIn(
                    ".trellis/spec/later-small.md",
                    by_path,
                    sorted(by_path),
                )
                self.assertEqual(
                    by_path[".trellis/spec/later-small.md"]["status"], "inline"
                )
                self.assertEqual(
                    by_path[".trellis/spec/check-only.md"]["status"], "omitted"
                )
                self.assertIn(
                    "not selected for the current agent role",
                    by_path[".trellis/spec/check-only.md"]["reason"],
                )
                self.assertEqual(by_path["src/forbidden.ts"]["status"], "omitted")
                self.assertTrue(
                    any(
                        by_path[f".trellis/spec/{path.name}"]["status"] == "omitted"
                        and "budget exhausted"
                        in by_path[f".trellis/spec/{path.name}"]["reason"]
                        for path in referenced
                    )
                )
                for entry in manifest:
                    self.assertIn(
                        entry["status"], {"inline", "truncated", "omitted"}
                    )
                    self.assertIn("bytes", entry)
                    if entry["status"] != "inline":
                        self.assertIn("reason", entry)

    def test_main_task_context_rehydrates_after_compaction(self) -> None:
        project = self.root / "main-compaction-project"
        task = project / ".trellis/tasks/08-09-main-compaction"
        runtime = project / ".trellis/.runtime/sessions"
        task.mkdir(parents=True)
        runtime.mkdir(parents=True)
        (project / ".trellis/workflow.md").write_text(
            "# Workflow\n", encoding="utf-8"
        )
        (task / "task.json").write_text(
            json.dumps({"title": "Main compaction", "status": "in_progress"}),
            encoding="utf-8",
        )
        (task / "prd.md").write_text("MAIN-COMPACTION-PRD\n", encoding="utf-8")
        (runtime / "omp_compaction_probe.json").write_text(
            json.dumps(
                {
                    "platform": "session",
                    "current_task": ".trellis/tasks/08-09-main-compaction",
                    "current_run": None,
                }
            ),
            encoding="utf-8",
        )

        runner = self.root / "main-compaction.mjs"
        runner.write_text(
            """import { pathToFileURL } from "node:url";
const [extensionPath, projectRoot] = process.argv.slice(2);
const extension = await import(pathToFileURL(extensionPath).href);
const handlers = {};
const sent = [];
extension.default({
  on(name, handler) { handlers[name] = handler; },
  async sendMessage(message) { sent.push(message); },
});
const ctx = {
  cwd: projectRoot,
  ui: { notify() {} },
  sessionManager: {
    getSessionId: () => "compaction_probe",
    getEntries: () => [],
  },
};
await handlers.session_start({}, ctx);
await handlers.session_before_compact({}, ctx);
const result = await handlers.context({ messages: [] }, ctx);
const after = result?.messages ?? [];
process.stdout.write(JSON.stringify({
  beforeTypes: sent.map(message => message.customType),
  afterTypes: after.map(message => message.customType),
  afterTaskContent: after.find(message => message.customType === "trellis-task-context")?.content ?? null,
}));
""",
            encoding="utf-8",
        )

        for version, patch_set in MANAGER.PATCH_SETS.items():
            with self.subTest(version=version):
                extension_path = (
                    patch_set.resource_root / ".omp/extensions/trellis/index.ts"
                )
                result = subprocess.run(
                    [
                        "node",
                        "--experimental-strip-types",
                        str(runner),
                        str(extension_path),
                        str(project),
                    ],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                payload = json.loads(result.stdout)
                self.assertIn("trellis-task-context", payload["beforeTypes"])
                self.assertIn("trellis-task-context", payload["afterTypes"])
                self.assertIn("trellis-workflow-state", payload["afterTypes"])
                self.assertIn("MAIN-COMPACTION-PRD", payload["afterTaskContent"])

    def test_lite_profile_is_injected_and_bounds_writes_and_verification(self) -> None:
        project = self.root / "profile-project"
        task = project / ".trellis/tasks/08-25-profile"
        runtime = project / ".trellis/.runtime/sessions"
        task.mkdir(parents=True)
        runtime.mkdir(parents=True)
        (task / "task.json").write_text(
            json.dumps(
                {
                    "title": "Profile boundary",
                    "status": "in_progress",
                    "lite": {
                        "change_mode": "P0",
                        "verification_level": "V1",
                        "checker": "off",
                        "allowed_paths": ["frontend/**"],
                        "forbidden_paths": ["backend/**"],
                        "selected_by": "user",
                    },
                }
            ),
            encoding="utf-8",
        )
        (task / "prd.md").write_text("PROFILE-PRD\n", encoding="utf-8")
        (runtime / "omp_profile_probe.json").write_text(
            json.dumps(
                {
                    "platform": "session",
                    "current_task": ".trellis/tasks/08-25-profile",
                    "current_run": None,
                }
            ),
            encoding="utf-8",
        )
        runner = self.root / "profile-guard.mjs"
        runner.write_text(
            """import { pathToFileURL } from \"node:url\";
const [extensionPath, projectRoot] = process.argv.slice(2);
const extension = await import(pathToFileURL(extensionPath).href);
const handlers = {};
extension.default({ on(name, handler) { handlers[name] = handler; }, async sendMessage() {} });
const ctx = {
  cwd: projectRoot,
  ui: { notify() {} },
  sessionManager: {
    getSessionId: () => \"profile_probe\",
    getSessionFile: () => undefined,
    getEntries: () => [],
  },
};
await handlers.session_start({}, ctx);
const allowed = handlers.tool_call({ toolName: \"write\", input: { path: \"frontend/Feature.tsx\" } }, ctx) ?? null;
const blocked = handlers.tool_call({ toolName: \"write\", input: { path: \"backend/policy.py\" } }, ctx) ?? null;
const firstCheck = handlers.tool_call({ toolName: \"bash\", input: { command: \"npm test -- Feature\" } }, ctx) ?? null;
const secondCheck = handlers.tool_call({ toolName: \"bash\", input: { command: \"npm test -- Feature\" } }, ctx) ?? null;
process.stdout.write(JSON.stringify({ allowed, blocked, firstCheck, secondCheck }));
""",
            encoding="utf-8",
        )

        for version, patch_set in MANAGER.PATCH_SETS.items():
            with self.subTest(version=version):
                extension_path = patch_set.resource_root / ".omp/extensions/trellis/index.ts"
                context_runner = self.root / f"profile-context-{version}.mjs"
                context_runner.write_text(
                    """import { pathToFileURL } from \"node:url\";
const [extensionPath, projectRoot, taskDir] = process.argv.slice(2);
const extension = await import(pathToFileURL(extensionPath).href);
process.stdout.write(extension.buildTaskContext(projectRoot, taskDir));
""",
                    encoding="utf-8",
                )
                context_result = subprocess.run(
                    [
                        "node",
                        "--experimental-strip-types",
                        str(context_runner),
                        str(extension_path),
                        str(project),
                        str(task),
                    ],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                self.assertIn('"change_mode":"P0"', context_result.stdout)
                self.assertIn('"verification_level":"V1"', context_result.stdout)
                self.assertIn('"allowed_paths":["frontend/**"]', context_result.stdout)

                guard_result = subprocess.run(
                    [
                        "node",
                        "--experimental-strip-types",
                        str(runner),
                        str(extension_path),
                        str(project),
                    ],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                payload = json.loads(guard_result.stdout)
                self.assertIsNone(payload["allowed"])
                self.assertTrue(payload["blocked"]["block"])
                self.assertIn("Lite profile", payload["blocked"]["reason"])
                self.assertIsNone(payload["firstCheck"])
                self.assertTrue(payload["secondCheck"]["block"])
                self.assertIn("verification budget exhausted", payload["secondCheck"]["reason"])

    def test_active_task_pointer_rejects_escape_and_keeps_local_fallback(
        self,
    ) -> None:
        runner = self.root / "active-task-boundary.mjs"
        runner.write_text(
            """import { pathToFileURL } from "node:url";
const [extensionPath, projectRoot] = process.argv.slice(2);
const extension = await import(pathToFileURL(extensionPath).href);
const handlers = {};
const sent = [];
extension.default({
  on(name, handler) { handlers[name] = handler; },
  async sendMessage(message) { sent.push(message); },
});
const ctx = {
  cwd: projectRoot,
  ui: { notify() {} },
  sessionManager: {
    getSessionId: () => undefined,
    getSessionFile: () => undefined,
    getEntries: () => [],
  },
};
await handlers.session_start({}, ctx);
const before = await handlers.before_agent_start({}, ctx);
process.stdout.write(JSON.stringify({
  taskContext: sent.find(message => message.customType === "trellis-task-context")?.content ?? null,
  workflow: before?.message?.content ?? null,
}));
""",
            encoding="utf-8",
        )

        outside_project = self.root / "active-task-outside-project"
        outside = self.root / "outside"
        (outside_project / ".trellis/.runtime/sessions").mkdir(parents=True)
        (outside_project / ".trellis/workflow.md").write_text(
            """[workflow-state:no_task]
NO-TASK-WORKFLOW
[/workflow-state:no_task]

[workflow-state:completed]
OUTSIDE-STATUS-SELECTED
[/workflow-state:completed]
""",
            encoding="utf-8",
        )
        (outside_project / ".trellis/.runtime/sessions/probe.json").write_text(
            json.dumps({"current_task": "../outside"}),
            encoding="utf-8",
        )
        outside.mkdir()
        (outside / "task.json").write_text(
            json.dumps({"title": "Outside", "status": "completed"}),
            encoding="utf-8",
        )
        (outside / "prd.md").write_text("OUTSIDE-PRD\n", encoding="utf-8")

        local_project = self.root / "active-task-local-project"
        local_task = local_project / ".trellis/tasks/07-22-following-radar"
        (local_project / ".trellis/.runtime/sessions").mkdir(parents=True)
        local_task.mkdir(parents=True)
        (local_project / ".trellis/workflow.md").write_text(
            """[workflow-state:no_task]
NO-TASK-WORKFLOW
[/workflow-state:no_task]

[workflow-state:planning]
LOCAL-TASK-SELECTED
[/workflow-state:planning]
""",
            encoding="utf-8",
        )
        (local_project / ".trellis/.runtime/sessions/probe.json").write_text(
            json.dumps(
                {"current_task": ".trellis/tasks/07-22-following-radar"}
            ),
            encoding="utf-8",
        )
        (local_task / "task.json").write_text(
            json.dumps({"title": "Following Radar", "status": "planning"}),
            encoding="utf-8",
        )
        (local_task / "prd.md").write_text("LOCAL-PRD\n", encoding="utf-8")

        clean_env = {
            key: value
            for key, value in os.environ.items()
            if key not in {"PI_BLOCKED_AGENT", "TRELLIS_CONTEXT_ID"}
        }

        def run(extension_path: Path, project: Path) -> dict[str, object]:
            result = subprocess.run(
                [
                    "node",
                    "--experimental-strip-types",
                    str(runner),
                    str(extension_path),
                    str(project),
                ],
                check=True,
                capture_output=True,
                text=True,
                env=clean_env,
            )
            return cast(dict[str, object], json.loads(result.stdout))

        for version, patch_set in MANAGER.PATCH_SETS.items():
            extension_path = (
                patch_set.resource_root / ".omp/extensions/trellis/index.ts"
            )
            with self.subTest(version=version, pointer="outside"):
                escaped = run(extension_path, outside_project)
                self.assertIsNone(escaped["taskContext"])
                self.assertIn("NO-TASK-WORKFLOW", escaped["workflow"])
                self.assertNotIn("OUTSIDE-STATUS-SELECTED", escaped["workflow"])

            with self.subTest(version=version, pointer="local"):
                local = run(extension_path, local_project)
                self.assertIn("LOCAL-PRD", local["taskContext"])
                self.assertIn(
                    '"path":".trellis/tasks/07-22-following-radar"',
                    local["taskContext"],
                )
                self.assertIn("LOCAL-TASK-SELECTED", local["workflow"])

    def test_0614_child_assignment_change_fails_closed(self) -> None:
        project = self.root / "warm-child-project"
        for name, title in (("task-a", "Task A"), ("task-b", "Task B")):
            task = project / f".trellis/tasks/{name}"
            task.mkdir(parents=True)
            (task / "task.json").write_text(
                json.dumps({"title": title, "status": "in_progress"}),
                encoding="utf-8",
            )
            (task / "prd.md").write_text(f"{title.upper()}-CONTENT\n", encoding="utf-8")
        (project / ".trellis/workflow.md").parent.mkdir(parents=True, exist_ok=True)
        (project / ".trellis/workflow.md").write_text(
            "# Workflow\n", encoding="utf-8"
        )

        runner = self.root / "warm-child.mjs"
        runner.write_text(
            """import { pathToFileURL } from "node:url";
const [extensionPath, projectRoot] = process.argv.slice(2);
const extension = await import(pathToFileURL(extensionPath).href);
const handlers = {};
let entries = [
  { type: "session_init", agent: "trellis-check" },
  { type: "message", message: { role: "user", content: "Active task: .trellis/tasks/task-a" } },
];
extension.default({ on(name, handler) { handlers[name] = handler; } });
const ctx = {
  cwd: projectRoot,
  ui: { notify() {} },
  sessionManager: {
    getSessionId: () => "warm-child-probe",
    getEntries: () => entries,
  },
};
await handlers.session_start({}, ctx);
const first = await handlers.before_agent_start({}, ctx);
entries = [...entries, { type: "message", message: { role: "user", content: "Active task: .trellis/tasks/task-b" } }];
const second = await handlers.before_agent_start({}, ctx);
await handlers.session_before_compact({}, ctx);
const afterCompact = await handlers.context({ messages: [] }, ctx);
const content = (message) => typeof message?.content === "string" ? message.content : "";
process.stdout.write(JSON.stringify({
  first: content(first?.message),
  second: content(second?.message),
  afterCompact: (afterCompact?.messages ?? []).map(content),
}));
""",
            encoding="utf-8",
        )

        extension_path = (
            MANAGER.PATCH_SETS["0.6.14"].resource_root
            / ".omp/extensions/trellis/index.ts"
        )
        result = subprocess.run(
            [
                "node",
                "--experimental-strip-types",
                str(runner),
                str(extension_path),
                str(project),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(result.stdout)
        self.assertIn('"title":"Task A"', payload["first"])
        self.assertIn("<task-context-error>", payload["second"])
        self.assertNotIn('"title":"Task A"', payload["second"])
        self.assertTrue(
            any("<task-context-error>" in message for message in payload["afterCompact"])
        )

    def test_0614_child_recovery_requires_its_own_explicit_task(self) -> None:
        extension_path = (
            MANAGER.PATCH_SETS["0.6.14"].resource_root
            / ".omp/extensions/trellis/index.ts"
        )
        runner = self.root / "recover-child.mjs"
        entries_path = self.root / "entries.json"
        runner.write_text(
            """import { readFileSync } from "node:fs";
import { pathToFileURL } from "node:url";
const [extensionPath, entriesPath] = process.argv.slice(2);
const extension = await import(pathToFileURL(extensionPath).href);
const entries = JSON.parse(readFileSync(entriesPath, "utf-8"));
process.stdout.write(JSON.stringify({
  agent: extension.recoverAgentType(entries),
  task: extension.recoverExplicitTaskPath(entries),
}));
""",
            encoding="utf-8",
        )

        def recover(entries: list[dict[str, object]]) -> dict[str, object]:
            entries_path.write_text(json.dumps(entries), encoding="utf-8")
            result = subprocess.run(
                [
                    "node",
                    "--experimental-strip-types",
                    str(runner),
                    str(extension_path),
                    str(entries_path),
                ],
                check=True,
                capture_output=True,
                text=True,
                env={**os.environ, "PI_BLOCKED_AGENT": "trellis-implement"},
            )
            return cast(dict[str, object], json.loads(result.stdout))

        valid = recover(
            [
                {"type": "session_init", "agent": "trellis-check"},
                {
                    "type": "message",
                    "message": {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": (
                                    "Complete this assignment.\n\n"
                                    "Active task: .trellis/tasks/08-09-demo\n"
                                    "# Target\nReview only."
                                ),
                            }
                        ],
                    },
                },
            ]
        )
        session_init_assignment = recover(
            [
                {
                    "type": "session_init",
                    "agent": "trellis-check",
                    "task": (
                        "Complete the assignment below, thoroughly:\n\n"
                        "Active task: .trellis/tasks/08-09-session-init"
                    ),
                }
            ]
        )
        punctuated_assignment = recover(
            [
                {
                    "type": "session_init",
                    "agent": "trellis-check",
                    "task": (
                        "Complete the assignment below, thoroughly:\n\n"
                        "Active task: .trellis/tasks/08-09-punctuated."
                    ),
                }
            ]
        )
        ambiguous = recover(
            [
                {"type": "session_init", "agent": "trellis-check"},
                {
                    "type": "message",
                    "message": {
                        "role": "user",
                        "content": (
                            "Active task: .trellis/tasks/08-09-first\n"
                            "Active task: .trellis/tasks/08-09-second"
                        ),
                    },
                },
            ]
        )
        environment_only = recover([])

        self.assertEqual(
            valid,
            {"agent": "trellis-check", "task": ".trellis/tasks/08-09-demo"},
        )
        self.assertEqual(
            session_init_assignment,
            {
                "agent": "trellis-check",
                "task": ".trellis/tasks/08-09-session-init",
            },
        )
        self.assertEqual(
            punctuated_assignment,
            {
                "agent": "trellis-check",
                "task": ".trellis/tasks/08-09-punctuated",
            },
        )
        self.assertEqual(ambiguous, {"agent": "trellis-check", "task": None})
        self.assertEqual(environment_only, {"agent": None, "task": None})
        source = extension_path.read_text(encoding="utf-8")
        self.assertNotIn("PI_BLOCKED_AGENT", source)
        self.assertNotIn("process.env.TRELLIS_CONTEXT_ID =", source)

    def test_0614_bash_context_key_is_per_call_and_does_not_mutate_process_env(
        self,
    ) -> None:
        extension_path = (
            MANAGER.PATCH_SETS["0.6.14"].resource_root
            / ".omp/extensions/trellis/index.ts"
        )
        runner = self.root / "tool-call-env.mjs"
        runner.write_text(
            """import { pathToFileURL } from "node:url";
const extension = await import(pathToFileURL(process.argv[2]).href);
const handlers = {};
extension.default({ on(name, handler) { handlers[name] = handler; } });
delete process.env.TRELLIS_CONTEXT_ID;
const derived = { env: { EXISTING: "kept" } };
handlers.tool_call(
  { toolName: "bash", input: derived },
  { sessionManager: { getSessionId: () => "child/session" } },
);
const explicit = { env: { TRELLIS_CONTEXT_ID: "caller-wins" } };
handlers.tool_call(
  { toolName: "bash", input: explicit },
  { sessionManager: { getSessionId: () => "child/session" } },
);
process.stdout.write(JSON.stringify({
  derived: derived.env,
  explicit: explicit.env,
  globalValue: process.env.TRELLIS_CONTEXT_ID ?? null,
}));
""",
            encoding="utf-8",
        )

        result = subprocess.run(
            [
                "node",
                "--experimental-strip-types",
                str(runner),
                str(extension_path),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(result.stdout)

        self.assertEqual(payload["derived"]["TRELLIS_CONTEXT_ID"], "omp_child_session")
        self.assertEqual(payload["derived"]["EXISTING"], "kept")
        self.assertEqual(payload["explicit"]["TRELLIS_CONTEXT_ID"], "caller-wins")
        self.assertIsNone(payload["globalValue"])

    def test_omp_checker_extension_blocks_every_noninspection_tool(self) -> None:
        runner = self.root / "checker-tool-guard.mjs"
        runner.write_text(
            """import { pathToFileURL } from "node:url";
const extension = await import(pathToFileURL(process.argv[2]).href);
const handlers = {};
extension.default({ on(name, handler) { handlers[name] = handler; } });
const ctx = {
  sessionManager: {
    getSessionId: () => "checker/session",
    getEntries: () => [{ type: "session_init", agent: "trellis-check" }],
  },
};
const allowed = Object.fromEntries(
  ["read", "grep", "glob", "ast_grep", "yield"].map((toolName) => [
    toolName,
    handlers.tool_call({ toolName, input: {} }, ctx) ?? null,
  ]),
);
const blocked = Object.fromEntries(
  [
    "bash",
    "write",
    "task",
    "hub",
    "mcp__jira_update_issue",
    "extension_mutating_tool",
    "custom_mutating_tool",
  ].map((toolName) => [
    toolName,
    handlers.tool_call({ toolName, input: {} }, ctx),
  ]),
);
process.stdout.write(JSON.stringify({ allowed: allowed ?? null, blocked }));
""",
            encoding="utf-8",
        )

        for version, patch_set in MANAGER.PATCH_SETS.items():
            with self.subTest(version=version):
                extension_path = (
                    patch_set.resource_root / ".omp/extensions/trellis/index.ts"
                )
                result = subprocess.run(
                    [
                        "node",
                        "--experimental-strip-types",
                        str(runner),
                        str(extension_path),
                    ],
                    check=True,
                    capture_output=True,
                    text=True,
                    env={**os.environ, "PI_BLOCKED_AGENT": "trellis-check"},
                )
                payload = json.loads(result.stdout)
                for tool_name, decision in payload["allowed"].items():
                    self.assertIsNone(decision, tool_name)
                for tool_name, decision in payload["blocked"].items():
                    self.assertTrue(decision["block"], tool_name)
                    self.assertIn("blocked non-inspection tool", decision["reason"])

    def test_0614_context_allows_only_explicitly_trusted_task_and_spec_symlinks(
        self,
    ) -> None:
        project = self.root / "symlink-project"
        trellis = project / ".trellis"
        external_tasks = self.root / "external-tasks"
        external_spec = self.root / "external-spec"
        task = external_tasks / "08-09-linked"
        task.mkdir(parents=True)
        external_spec.mkdir()
        trellis.mkdir(parents=True)
        (trellis / "tasks").symlink_to(external_tasks, target_is_directory=True)
        (trellis / "spec").symlink_to(external_spec, target_is_directory=True)
        (trellis / "config.yaml").write_text(
            "channel:\n  trusted_context_dirs:\n    - ../external-spec\n",
            encoding="utf-8",
        )
        (task / "task.json").write_text(
            json.dumps({"title": "Linked", "status": "in_progress"}),
            encoding="utf-8",
        )
        (task / "prd.md").write_text("LINKED-PRD\n", encoding="utf-8")
        (external_spec / "guide.md").write_text(
            "TRUSTED-SPEC-CONTENT\n", encoding="utf-8"
        )
        (task / "implement.jsonl").write_text(
            json.dumps({"file": ".trellis/spec/guide.md", "reason": "guide"})
            + "\n",
            encoding="utf-8",
        )
        extension_path = (
            MANAGER.PATCH_SETS["0.6.14"].resource_root
            / ".omp/extensions/trellis/index.ts"
        )
        runner = self.root / "trusted-context.mjs"
        runner.write_text(
            """import { pathToFileURL } from "node:url";
const [extensionPath, projectRoot, taskDir] = process.argv.slice(2);
const extension = await import(pathToFileURL(extensionPath).href);
process.stdout.write(extension.buildTaskContext(projectRoot, taskDir, "trellis-implement"));
""",
            encoding="utf-8",
        )

        result = subprocess.run(
            [
                "node",
                "--experimental-strip-types",
                str(runner),
                str(extension_path),
                str(project),
                str(trellis / "tasks/08-09-linked"),
            ],
            check=True,
            capture_output=True,
            text=True,
        )

        self.assertIn("LINKED-PRD", result.stdout)
        self.assertIn("TRUSTED-SPEC-CONTENT", result.stdout)
        self.assertIn('"path":".trellis/tasks/08-09-linked"', result.stdout)

    def test_policy_routes_subagents_without_an_automatic_fix_loop(self) -> None:
        for version, patch_set in MANAGER.PATCH_SETS.items():
            with self.subTest(version=version):
                workflow = (
                    patch_set.resource_root / ".trellis/workflow.md"
                ).read_text(encoding="utf-8")
                start = (
                    patch_set.resource_root
                    / ".agents/skills/trellis-start/SKILL.md"
                ).read_text(encoding="utf-8")
                brainstorm = (
                    patch_set.resource_root
                    / ".agents/skills/trellis-brainstorm/SKILL.md"
                ).read_text(encoding="utf-8")
                combined = f"{workflow}\n{start}\n{brainstorm}"

                self.assertIn("Small work stays in the main session", combined)
                self.assertIn("one report-only checker", combined)
                self.assertIn("defaults to parallel implementers", combined)
                self.assertIn("one `trellis-research` agent by default", combined)
                self.assertIn("Only the main agent dispatches", combined)
                self.assertIn("explicit user authorization", combined)
                self.assertIn("Most work needs only a concise `prd.md`", combined)
                for forbidden in (
                    "maximum autonomous loop",
                    "allow one targeted correction",
                    "One failed check permits",
                    "Stop after a second failure",
                    "For every non-trivial task",
                    "must each contain at least one real spec/research entry",
                    "subsequent user message that explicitly approves",
                ):
                    self.assertNotIn(forbidden, combined)

    def test_checker_resources_have_a_runtime_read_only_boundary(self) -> None:
        forbidden_tools = {"write", "edit", "bash", "lsp", "task"}
        for version, patch_set in MANAGER.PATCH_SETS.items():
            with self.subTest(version=version):
                agent = (
                    patch_set.resource_root / ".omp/agents/trellis-check.md"
                ).read_text(encoding="utf-8")
                tools_line = next(
                    line for line in agent.splitlines() if line.startswith("tools:")
                )
                tools = {
                    item.strip()
                    for item in tools_line.removeprefix("tools:").split(",")
                    if item.strip()
                }
                self.assertEqual(tools, {"read", "grep", "glob", "ast_grep"})
                self.assertTrue(forbidden_tools.isdisjoint(tools))
                for required in (
                    "Runtime Boundary",
                    "runtime-enforced read-only execution boundary",
                    "OMP may still advertise implicit `hub`, MCP, custom",
                    "implementation-session checks are sufficient",
                    "Treat full-suite",
                    "task.py finish",
                    "task.py archive",
                    "task/spec/session state",
                    "Report findings only",
                    "extension-provided tools to the child session",
                    "blocks all of them",
                ):
                    self.assertIn(required, agent)
                for forbidden in (
                    "Runs one proportional verification pass",
                    "Select the narrowest tests",
                    "Never run a full suite",
                    "exact commands/results",
                ):
                    self.assertNotIn(forbidden, agent)

                for relative_path in (
                    ".omp/skills/trellis-check/SKILL.md",
                    ".agents/skills/trellis-check/SKILL.md",
                ):
                    skill = (patch_set.resource_root / relative_path).read_text(
                        encoding="utf-8"
                    )
                    self.assertIn("read-only evidence reviewer", skill)
                    self.assertIn("Never edit files", skill)
                    self.assertIn("task.py archive", skill)
                    self.assertNotIn("Edit only when", skill)
                    self.assertNotIn("bounded checker edit", skill)

                codex = (
                    patch_set.resource_root / ".codex/agents/trellis-check.toml"
                ).read_text(encoding="utf-8")
                self.assertIn('sandbox_mode = "read-only"', codex)
                self.assertIn("read-only evidence reviewer", codex)
                self.assertIn("Perform one proportional evidence review", codex)
                self.assertIn("do not edit files, run tests, builds", codex)
                self.assertIn("Report findings only", codex)
                self.assertIn("task.py finish", codex)
                self.assertNotIn(
                    "or `python3 ./.trellis/scripts/task.py current --source`",
                    codex,
                )
                self.assertNotIn("Run one proportional verification pass", codex)
                self.assertNotIn("exact commands/results", codex)

                workflow = (patch_set.resource_root / ".trellis/workflow.md").read_text(
                    encoding="utf-8"
                )
                self.assertIn("runtime-read-only", workflow)
                self.assertIn("The checker cannot make it", workflow)
                self.assertNotIn("bounded checker edit", workflow)

    def test_production_103_checker_policy_hashes_are_upgrade_inputs(self) -> None:
        common = {
            ".trellis/workflow.md": (
                "e4b42a0232b2a70a67934dc51a7b66d7dc9cd4b920b2af14f19c052a4f8b06de"
            ),
            ".omp/skills/trellis-check/SKILL.md": (
                "cddd39b6c660f1b44b6dc067153dcd366ee3597fa990f042a5c871d311d58da9"
            ),
            ".agents/skills/trellis-check/SKILL.md": (
                "cddd39b6c660f1b44b6dc067153dcd366ee3597fa990f042a5c871d311d58da9"
            ),
        }
        version_specific = {
            "0.6.7": {
                ".omp/agents/trellis-check.md": (
                    "a03e2178e746cefe5b31f19b05d040bdc04f71e68279b38bb7392c45c323ef43"
                ),
                ".codex/agents/trellis-check.toml": (
                    "d3322d3387bac26e549835d6acc5892518f867cac74a152dfb356c17579c2787"
                ),
            },
            "0.6.14": {
                ".omp/agents/trellis-check.md": (
                    "011657e453c80450de7c76da4be96c434be36878113c226aff091726949a9dd8"
                ),
                ".codex/agents/trellis-check.toml": (
                    "1bbd07802c97ba926df3c3bdbf1f0e010c89fe81e9c6208290e01e9399e4aa30"
                ),
            },
        }
        for version, patch_set in MANAGER.PATCH_SETS.items():
            specs = {spec.path: spec for spec in patch_set.files}
            for path, digest in {**common, **version_specific[version]}.items():
                with self.subTest(version=version, path=path):
                    self.assertIn(digest, specs[path].upgrade_sha256s)

    def test_production_104_checker_policy_hashes_are_upgrade_inputs(self) -> None:
        version_specific = {
            "0.6.7": {
                ".omp/agents/trellis-check.md": (
                    "3cd5b1991c4cd9955d27f3277b837d91e713671af10f022865ba906183d0ca69"
                ),
                ".codex/agents/trellis-check.toml": (
                    "ef47f7d925f9c81e49cc49bd73aba72cd3b6cfbb6998bfbcd775c4c84a65c1f8"
                ),
            },
            "0.6.14": {
                ".omp/agents/trellis-check.md": (
                    "399258f4b91db2b9fcd5a1e5f1b09aba394db1348f13d0bcdd4e52e5d20d0985"
                ),
                ".codex/agents/trellis-check.toml": (
                    "d94c0719b7853ed54ae1d6b2faaa89f69385a3e4882cb7371389e47ca91d0640"
                ),
            },
        }
        for version, patch_set in MANAGER.PATCH_SETS.items():
            specs = {spec.path: spec for spec in patch_set.files}
            for path, digest in version_specific[version].items():
                with self.subTest(version=version, path=path):
                    self.assertIn(digest, specs[path].upgrade_sha256s)

    def test_production_105_checker_policy_hashes_are_upgrade_inputs(self) -> None:
        version_specific = {
            "0.6.7": {
                ".omp/agents/trellis-check.md": (
                    "c2a06697136fc310189d9ffcb550fdc8452b5bdc7ae56976a7d363cdbba8b550"
                ),
                ".codex/agents/trellis-check.toml": (
                    "b8d6b3cd391e6e61926b83e1e93f5d24c2ed529fc6bb96ee05e9161167d700d9"
                ),
            },
            "0.6.14": {
                ".omp/agents/trellis-check.md": (
                    "e3c0765eeb824a80d9522e268f13867329d121600913c36ba01fccddf187fa4e"
                ),
            },
        }
        for version, patch_set in MANAGER.PATCH_SETS.items():
            specs = {spec.path: spec for spec in patch_set.files}
            for path, digest in version_specific[version].items():
                with self.subTest(version=version, path=path):
                    self.assertIn(digest, specs[path].upgrade_sha256s)

    def test_production_106_runtime_boundary_hashes_are_upgrade_inputs(self) -> None:
        version_specific = {
            "0.6.7": {
                ".omp/extensions/trellis/index.ts": (
                    "f03f1d23b299a56ea9e5d88eafa962d252fe3a3eab7459a39bb79be111e11176"
                ),
                ".omp/agents/trellis-check.md": (
                    "cf85b24b8c38feb12489408f35a9cb8a1821be1cc9f14d690684db99fce9a4fc"
                ),
            },
            "0.6.14": {
                ".omp/extensions/trellis/index.ts": (
                    "1a1f41bb1536148628821ea8286c0a370adb2563d27264f90c5608d9f95f59e1"
                ),
                ".omp/agents/trellis-check.md": (
                    "1d16269e1fd711cf1d3042e225a725b7f2e263d236652b8f4f5dff0c3a9ae6fb"
                ),
            },
        }
        for version, patch_set in MANAGER.PATCH_SETS.items():
            specs = {spec.path: spec for spec in patch_set.files}
            for path, digest in version_specific[version].items():
                with self.subTest(version=version, path=path):
                    self.assertIn(digest, specs[path].upgrade_sha256s)

    def test_production_107_checker_boundary_hashes_are_upgrade_inputs(self) -> None:
        version_specific = {
            "0.6.7": {
                ".omp/extensions/trellis/index.ts": (
                    "d29bb4002d7bb09585fb137e46e2bc4440dc29b95bb9a850bc8158c1314dcf45"
                ),
                ".omp/agents/trellis-check.md": (
                    "73c8b91f3b1487af5a084a4b23af72de526977b17aa8d56214107672116f0bd6"
                ),
            },
            "0.6.14": {
                ".omp/extensions/trellis/index.ts": (
                    "4b05099b16a243053b96d653a683359399cd04ec3bc6d9e65f71f761b150c4ba"
                ),
                ".omp/agents/trellis-check.md": (
                    "21ec69b27deabced5472af66a9d463d17f001b4d71af03b4eb4f92b81ac7b946"
                ),
            },
        }
        for version, patch_set in MANAGER.PATCH_SETS.items():
            specs = {spec.path: spec for spec in patch_set.files}
            for path, digest in version_specific[version].items():
                with self.subTest(version=version, path=path):
                    self.assertIn(digest, specs[path].upgrade_sha256s)

    def test_production_108_runtime_hashes_are_upgrade_inputs(self) -> None:
        version_specific = {
            "0.6.7": (
                "9b09cb4fd14ad1ca429efa55547f76dd6837c72c9dd50571ae676b28d4d9e00f"
            ),
            "0.6.14": (
                "f563f175590b81374a518c54112558f4b4986024e6a5db2382db05847dcafad4"
            ),
        }
        for version, patch_set in MANAGER.PATCH_SETS.items():
            with self.subTest(version=version):
                specs = {spec.path: spec for spec in patch_set.files}
                self.assertIn(
                    version_specific[version],
                    specs[".omp/extensions/trellis/index.ts"].upgrade_sha256s,
                )

    def test_production_109_child_runtime_hash_is_upgrade_input(self) -> None:
        spec = {
            item.trellis_version: next(
                file_spec
                for file_spec in item.files
                if file_spec.path == ".omp/extensions/trellis/index.ts"
            )
            for item in MANAGER.PATCH_SETS.values()
        }["0.6.14"]
        self.assertIn(
            "c814c8d09cae79f3cc62328b1c19dd79d80694e622cec2c4227c194fd8ce3ca9",
            spec.upgrade_sha256s,
        )

    def test_production_110_active_task_guard_hashes_are_upgrade_inputs(
        self,
    ) -> None:
        previous_hashes = {
            "0.6.7": (
                "a5a7604b53b5ffdfa6039fe3531b41e2605f60d474a27271b4409aa9bb527e92"
            ),
            "0.6.14": (
                "4fbc341bc15ac3e1960abff788a4ab55d6fdb788755673ff8a741bc232ee9395"
            ),
        }
        for version, patch_set in MANAGER.PATCH_SETS.items():
            with self.subTest(version=version):
                spec = next(
                    file_spec
                    for file_spec in patch_set.files
                    if file_spec.path == ".omp/extensions/trellis/index.ts"
                )
                self.assertIn(previous_hashes[version], spec.upgrade_sha256s)

    def test_0614_task_reuse_and_lite_converge_without_overwriting_each_other(
        self,
    ) -> None:
        project = self.root / "interop-project"
        workflow = project / ".trellis/workflow.md"
        task_script = project / ".trellis/scripts/task.py"
        workflow.parent.mkdir(parents=True)
        task_script.parent.mkdir(parents=True)
        (project / ".trellis/.version").write_text("0.6.14\n", encoding="utf-8")

        upstream_workflow = b"upstream workflow\n"
        reused_workflow = b"reuse-first workflow\n"
        lite_workflow = b"lite workflow\n"
        upstream_task = b'def route():\n    return "create"\n'
        reused_task = b'def route():\n    return "reuse"\n'
        workflow.write_bytes(upstream_workflow)
        task_script.write_bytes(upstream_task)

        patch_text = """--- a/.trellis/workflow.md
+++ b/.trellis/workflow.md
@@ -1 +1 @@
-upstream workflow
+reuse-first workflow
--- a/.trellis/scripts/task.py
+++ b/.trellis/scripts/task.py
@@ -1,2 +1,2 @@
 def route():
-    return "create"
+    return "reuse"
"""
        patch_path = self.root / "task-reuse.patch"
        patch_path.write_text(patch_text, encoding="utf-8")
        reuse_file_spec = cast(type, TASK_REUSE_MANAGER.FileSpec)
        reuse_patch_set = TASK_REUSE_MANAGER.PatchSet(
            trellis_version="0.6.14",
            patch_path=patch_path,
            patch_sha256=TASK_REUSE_MANAGER.sha256_bytes(patch_text.encode()),
            files=(
                reuse_file_spec(
                    ".trellis/workflow.md",
                    TASK_REUSE_MANAGER.sha256_bytes(upstream_workflow),
                    TASK_REUSE_MANAGER.sha256_bytes(reused_workflow),
                    required=True,
                    compatible_overlay_sha256s=(
                        TASK_REUSE_MANAGER.sha256_bytes(lite_workflow),
                    ),
                ),
                reuse_file_spec(
                    ".trellis/scripts/task.py",
                    TASK_REUSE_MANAGER.sha256_bytes(upstream_task),
                    TASK_REUSE_MANAGER.sha256_bytes(reused_task),
                    required=True,
                ),
            ),
        )

        lite_resources = self.root / "interop-resources"
        lite_resource = lite_resources / ".trellis/workflow.md"
        lite_resource.parent.mkdir(parents=True)
        lite_resource.write_bytes(lite_workflow)
        lite_spec = MANAGER.FileSpec(
            ".trellis/workflow.md",
            MANAGER.sha256_bytes(reused_workflow),
            MANAGER.sha256_bytes(lite_workflow),
            required=True,
        )

        reuse_patch_sets = {"0.6.14": reuse_patch_set}

        def inspect_reuse(_project: Path) -> dict[str, object]:
            return TASK_REUSE_MANAGER.inspect_project(project, reuse_patch_sets)

        def apply_reuse(_project: Path) -> dict[str, object]:
            return TASK_REUSE_MANAGER.apply_project(project, reuse_patch_sets)

        with (
            patch.object(MANAGER, "inspect_task_reuse", side_effect=inspect_reuse),
            patch.object(MANAGER, "apply_task_reuse", side_effect=apply_reuse),
        ):
            first = MANAGER.apply_project(
                project,
                (lite_spec,),
                lite_resources,
                run_prerequisite=True,
            )
            self.assertEqual(first["status"], "applied")
            self.assertEqual(
                TASK_REUSE_MANAGER.inspect_project(project, reuse_patch_sets)[
                    "status"
                ],
                "applied",
            )

            tracked = (
                workflow,
                task_script,
                project / TASK_REUSE_MANAGER.METADATA_REL_PATH,
                project / MANAGER.METADATA_REL_PATH,
            )
            before = {
                path: (path.read_bytes(), path.stat().st_mtime_ns)
                for path in tracked
            }

            second = MANAGER.apply_project(
                project,
                (lite_spec,),
                lite_resources,
                run_prerequisite=True,
            )

        self.assertEqual(second["status"], "applied")

        self.assertEqual(workflow.read_bytes(), lite_workflow)
        self.assertEqual(task_script.read_bytes(), reused_task)
        self.assertEqual(
            before,
            {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in tracked},
        )


if __name__ == "__main__":
    unittest.main()
