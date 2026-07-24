from __future__ import annotations

import importlib.util
import json
import stat
import tempfile
import unittest
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Protocol, cast, final, override

ROOT = Path(__file__).resolve().parents[1]
MANAGER_PATH = (
    ROOT
    / "skills"
    / "agent-infra"
    / "agent-process-monitor"
    / "scripts"
    / "manage_agent_process_monitor.py"
)


class ManagerModule(Protocol):
    def install(
        self,
        source: Path,
        target: Path,
        state_root: Path,
        *,
        verify_plugin: Callable[[Path], str],
        require_macos: bool,
    ) -> dict[str, object]: ...

    def status(
        self, source: Path, target: Path, state_root: Path
    ) -> dict[str, object]: ...

    def list_backups(self, state_root: Path) -> list[dict[str, object]]: ...

    def rollback(
        self,
        source: Path,
        target: Path,
        state_root: Path,
        backup_name: str,
        *,
        verify_plugin: Callable[[Path], str],
        require_macos: bool,
    ) -> dict[str, object]: ...

    def sha256_file(self, path: Path) -> str: ...


def load_manager() -> ManagerModule:
    spec = importlib.util.spec_from_file_location(
        "agent_process_monitor_manager", MANAGER_PATH
    )
    assert spec is not None and spec.loader is not None
    module: ModuleType = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return cast(ManagerModule, cast(object, module))


MANAGER = load_manager()


def plugin_text(version: str, marker: str) -> str:
    return "\n".join(
        (
            "#!/usr/bin/env python3",
            "# <xbar.title>Agent Process Monitor</xbar.title>",
            f"# <xbar.version>{version}</xbar.version>",
            "# <xbar.author>Fixture</xbar.author>",
            "# <xbar.desc>Fixture monitor.</xbar.desc>",
            "# <xbar.dependencies>python3</xbar.dependencies>",
            "",
            f'print("AI fixture {marker}")',
            "",
        )
    )


@final
class TestAgentProcessMonitorManager(unittest.TestCase):
    @override
    def __init__(self, methodName: str = "runTest") -> None:
        super().__init__(methodName)
        self.temporary_directory: tempfile.TemporaryDirectory[str] = (
            tempfile.TemporaryDirectory()
        )
        self.addCleanup(self.temporary_directory.cleanup)
        self.root: Path = Path(self.temporary_directory.name)
        self.source: Path = self.root / "canonical" / "mcp-monitor.15s.py"
        self.target: Path = self.root / "xbar" / "mcp-monitor.15s.py"
        self.state_root: Path = self.root / "state"
        self.write_plugin(self.source, "1.0.0", "one")

    @staticmethod
    def verify_plugin(path: Path) -> str:
        text = path.read_text(encoding="utf-8")
        if "AI fixture" not in text:
            raise OSError("fixture verification failed")
        return f"verified {path.name}"

    @staticmethod
    def write_plugin(path: Path, version: str, marker: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        _ = path.write_text(plugin_text(version, marker), encoding="utf-8")
        path.chmod(0o755)

    def install(self) -> dict[str, object]:
        return MANAGER.install(
            self.source,
            self.target,
            self.state_root,
            verify_plugin=self.verify_plugin,
            require_macos=False,
        )

    def test_clean_install_writes_executable_and_private_metadata(self) -> None:
        result = self.install()

        self.assertEqual(result["action"], "installed")
        self.assertEqual(self.target.read_bytes(), self.source.read_bytes())
        self.assertEqual(stat.S_IMODE(self.target.stat().st_mode), 0o755)
        metadata_path = self.state_root / "install.json"
        self.assertEqual(stat.S_IMODE(metadata_path.stat().st_mode), 0o600)
        metadata_raw = cast(
            object, json.loads(metadata_path.read_text(encoding="utf-8"))
        )
        self.assertIsInstance(metadata_raw, dict)
        metadata = cast(dict[str, object], metadata_raw)
        self.assertEqual(metadata["version"], "1.0.0")
        self.assertEqual(metadata["sha256"], MANAGER.sha256_file(self.target))
        self.assertEqual(MANAGER.list_backups(self.state_root), [])

    def test_current_install_is_noop_without_backup(self) -> None:
        _ = self.install()

        result = self.install()

        self.assertEqual(result["action"], "noop")
        self.assertIsNone(result["backup"])
        self.assertEqual(MANAGER.list_backups(self.state_root), [])

    def test_status_detects_manual_target_drift(self) -> None:
        _ = self.install()
        self.write_plugin(self.target, "1.0.1", "manual")

        result = MANAGER.status(self.source, self.target, self.state_root)

        self.assertEqual(result["status"], "drifted")

    def test_invalid_source_cannot_replace_working_target(self) -> None:
        _ = self.install()
        original = self.target.read_bytes()
        _ = self.source.write_text("not a plugin\n", encoding="utf-8")

        with self.assertRaises(RuntimeError):
            _ = self.install()

        self.assertEqual(self.target.read_bytes(), original)
        self.assertEqual(MANAGER.list_backups(self.state_root), [])

    def test_install_rejects_symlink_target_without_touching_destination(self) -> None:
        destination = self.root / "outside" / "mcp-monitor.15s.py"
        self.write_plugin(destination, "0.9.0", "outside")
        original = destination.read_bytes()
        self.target.parent.mkdir(parents=True, exist_ok=True)
        self.target.symlink_to(destination)

        with self.assertRaises(RuntimeError):
            _ = self.install()

        self.assertTrue(self.target.is_symlink())
        self.assertEqual(destination.read_bytes(), original)

    def test_update_creates_backup_and_installs_identical_bytes(self) -> None:
        _ = self.install()
        previous = self.target.read_bytes()
        self.write_plugin(self.source, "2.0.0", "two")

        result = self.install()

        self.assertEqual(result["action"], "installed")
        self.assertEqual(self.target.read_bytes(), self.source.read_bytes())
        backups = MANAGER.list_backups(self.state_root)
        self.assertEqual(len(backups), 1)
        backup_path = self.state_root / "backups" / cast(str, backups[0]["name"])
        self.assertEqual(backup_path.read_bytes(), previous)

    def test_failed_post_install_verification_restores_previous_target(self) -> None:
        _ = self.install()
        previous = self.target.read_bytes()
        self.write_plugin(self.source, "2.0.0", "two")

        def fail_new_target(path: Path) -> str:
            if path.resolve() == self.target.resolve() and "2.0.0" in path.read_text(
                encoding="utf-8"
            ):
                raise OSError("reject installed fixture")
            return self.verify_plugin(path)

        with self.assertRaises(RuntimeError):
            _ = MANAGER.install(
                self.source,
                self.target,
                self.state_root,
                verify_plugin=fail_new_target,
                require_macos=False,
            )

        self.assertEqual(self.target.read_bytes(), previous)
        metadata_raw = cast(
            object,
            json.loads((self.state_root / "install.json").read_text(encoding="utf-8")),
        )
        self.assertIsInstance(metadata_raw, dict)
        metadata = cast(dict[str, object], metadata_raw)
        self.assertEqual(metadata["version"], "1.0.0")

    def test_rollback_restores_contained_backup_and_rejects_traversal(self) -> None:
        _ = self.install()
        first = self.target.read_bytes()
        self.write_plugin(self.source, "2.0.0", "two")
        _ = self.install()
        backup_name = cast(str, MANAGER.list_backups(self.state_root)[0]["name"])

        with self.assertRaises(RuntimeError):
            _ = MANAGER.rollback(
                self.source,
                self.target,
                self.state_root,
                "../outside.py",
                verify_plugin=self.verify_plugin,
                require_macos=False,
            )

        result = MANAGER.rollback(
            self.source,
            self.target,
            self.state_root,
            backup_name,
            verify_plugin=self.verify_plugin,
            require_macos=False,
        )

        self.assertEqual(result["action"], "rolled-back")
        self.assertEqual(self.target.read_bytes(), first)
        self.assertEqual(stat.S_IMODE(self.target.stat().st_mode), 0o755)


if __name__ == "__main__":
    _ = unittest.main()
