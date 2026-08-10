from __future__ import annotations

import importlib.util
import fcntl
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType
from typing import ContextManager, Protocol, cast, final, override
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
MANAGER_PATH = (
    ROOT
    / "skills"
    / "agent-infra"
    / "trellis-task-reuse"
    / "scripts"
    / "manage_trellis_task_reuse.py"
)


class MigrationLike(Protocol):
    source_overlay_version: str
    source_sha256: str


class FileSpecLike(Protocol):
    path: str
    required: bool
    compatible_overlay_sha256s: tuple[str, ...]
    migrations: tuple[MigrationLike, ...]


class PatchSetLike(Protocol):
    trellis_version: str
    patch_path: Path
    files: tuple[FileSpecLike, ...]


class ManagerModule(Protocol):
    OVERLAY_ID: str
    OVERLAY_VERSION: str
    METADATA_REL_PATH: Path
    PATCH_067: Path
    PATCH_SETS: dict[str, PatchSetLike]
    FileSpec: type
    PatchSet: type
    MigrationSpec: type

    def sha256_bytes(self, data: bytes) -> str: ...

    def inspect_project(
        self, project: Path, patch_sets: dict[str, object] | None = None
    ) -> dict[str, object]: ...

    def apply_project(
        self, project: Path, patch_sets: dict[str, object] | None = None
    ) -> dict[str, object]: ...

    def apply_projects(
        self, projects: list[Path], patch_sets: dict[str, object] | None = None
    ) -> list[dict[str, object]]: ...

    def discover_projects(self, roots: list[Path]) -> list[Path]: ...

    def load_patch_document(self, patch_set: PatchSetLike) -> dict[str, object]: ...

    def atomic_write(self, path: Path, data: bytes, mode: int) -> object: ...

    def atomic_create(self, path: Path, data: bytes, mode: int) -> object: ...

    def project_lock(self, project: Path, operation: int) -> ContextManager[None]: ...

    def load_migration_document(
        self, file_spec: FileSpecLike, migration: MigrationLike
    ) -> object: ...

    def validate_patch_set(self, patch_set: object) -> None: ...


def load_manager() -> ManagerModule:
    spec = importlib.util.spec_from_file_location("trellis_task_reuse", MANAGER_PATH)
    assert spec is not None and spec.loader is not None
    module: ModuleType = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return cast(ManagerModule, cast(object, module))


MANAGER = load_manager()

WORKFLOW_BASELINE = "alpha\nbeta\n"
WORKFLOW_OVERLAY = "alpha\nBETA\ngamma\n"
WORKFLOW_COMPATIBLE = "alpha\nBETA with local detail\ngamma\n"
WORKFLOW_OLD_OVERLAY = "alpha\nOLD\ngamma\n"
TASK_BASELINE = "one\ntwo\n"
TASK_OVERLAY = "one\nTWO\n"
OPTIONAL_BASELINE = "before\n"
OPTIONAL_OVERLAY = "after\n"

FIXTURE_PATCH = """--- a/.trellis/workflow.md
+++ b/.trellis/workflow.md
@@ -1,2 +1,3 @@
 alpha
-beta
+BETA
+gamma
--- a/.trellis/scripts/task.py
+++ b/.trellis/scripts/task.py
@@ -1,2 +1,2 @@
 one
-two
+TWO
--- a/.agents/skills/trellis-start/SKILL.md
+++ b/.agents/skills/trellis-start/SKILL.md
@@ -1 +1 @@
-before
+after
"""

FIXTURE_MIGRATION_PATCH = """--- a/.trellis/workflow.md
+++ b/.trellis/workflow.md
@@ -1,3 +1,3 @@
 alpha
-OLD
+BETA
 gamma
"""


@final
class TestTrellisTaskReuse(unittest.TestCase):
    temporary_directory: tempfile.TemporaryDirectory[str]  # pyright: ignore[reportUninitializedInstanceVariable]
    root: Path  # pyright: ignore[reportUninitializedInstanceVariable]
    patch_path: Path  # pyright: ignore[reportUninitializedInstanceVariable]
    migration_patch_path: Path  # pyright: ignore[reportUninitializedInstanceVariable]
    fixture_patch_set: PatchSetLike  # pyright: ignore[reportUninitializedInstanceVariable]
    patch_sets: dict[str, object]  # pyright: ignore[reportUninitializedInstanceVariable]

    @override
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)
        self.patch_path = self.root / "fixture.patch"
        self.patch_path.write_text(FIXTURE_PATCH, encoding="utf-8")
        self.migration_patch_path = self.root / "fixture-migration.patch"
        self.migration_patch_path.write_text(
            FIXTURE_MIGRATION_PATCH,
            encoding="utf-8",
        )

        file_spec = MANAGER.FileSpec
        patch_set = MANAGER.PatchSet
        self.fixture_patch_set = cast(
            PatchSetLike,
            patch_set(
                trellis_version="fixture",
                patch_path=self.patch_path,
                patch_sha256=MANAGER.sha256_bytes(FIXTURE_PATCH.encode("utf-8")),
                files=(
                    file_spec(
                        ".trellis/workflow.md",
                        MANAGER.sha256_bytes(WORKFLOW_BASELINE.encode()),
                        MANAGER.sha256_bytes(WORKFLOW_OVERLAY.encode()),
                        required=True,
                        compatible_overlay_sha256s=(
                            MANAGER.sha256_bytes(WORKFLOW_COMPATIBLE.encode()),
                        ),
                        migrations=(
                            MANAGER.MigrationSpec(
                                source_overlay_version="0.9.0",
                                source_sha256=MANAGER.sha256_bytes(
                                    WORKFLOW_OLD_OVERLAY.encode()
                                ),
                                patch_path=self.migration_patch_path,
                                patch_sha256=MANAGER.sha256_bytes(
                                    FIXTURE_MIGRATION_PATCH.encode()
                                ),
                            ),
                        ),
                    ),
                    file_spec(
                        ".trellis/scripts/task.py",
                        MANAGER.sha256_bytes(TASK_BASELINE.encode()),
                        MANAGER.sha256_bytes(TASK_OVERLAY.encode()),
                        required=True,
                    ),
                    file_spec(
                        ".agents/skills/trellis-start/SKILL.md",
                        MANAGER.sha256_bytes(OPTIONAL_BASELINE.encode()),
                        MANAGER.sha256_bytes(OPTIONAL_OVERLAY.encode()),
                    ),
                ),
            ),
        )
        self.patch_sets = {"fixture": self.fixture_patch_set}

    def create_project(self, relative_path: str = "project") -> Path:
        project = self.root / relative_path
        (project / ".trellis/scripts").mkdir(parents=True)
        (project / ".trellis/.version").write_text("fixture", encoding="utf-8")
        (project / ".trellis/workflow.md").write_text(
            WORKFLOW_BASELINE, encoding="utf-8"
        )
        (project / ".trellis/scripts/task.py").write_text(
            TASK_BASELINE, encoding="utf-8"
        )
        return project

    def inspect(self, project: Path) -> dict[str, object]:
        return MANAGER.inspect_project(project, self.patch_sets)

    def apply(self, project: Path) -> dict[str, object]:
        return MANAGER.apply_project(project, self.patch_sets)

    def test_check_is_read_only_and_reports_recognized_baseline(self) -> None:
        project = self.create_project()
        before = (project / ".trellis/workflow.md").read_bytes()

        report = self.inspect(project / ".trellis/scripts")

        self.assertEqual(report["status"], "needs_apply")
        self.assertEqual((project / ".trellis/workflow.md").read_bytes(), before)
        self.assertFalse((project / MANAGER.METADATA_REL_PATH).exists())

    def test_apply_is_idempotent_and_writes_deterministic_metadata(self) -> None:
        project = self.create_project()

        first = self.apply(project)
        metadata_path = project / MANAGER.METADATA_REL_PATH
        first_metadata = metadata_path.read_bytes()
        first_workflow = (project / ".trellis/workflow.md").read_bytes()
        metadata_mtime = metadata_path.stat().st_mtime_ns
        workflow_mtime = (project / ".trellis/workflow.md").stat().st_mtime_ns

        second = self.apply(project)

        self.assertEqual(first["status"], "applied")
        self.assertEqual(second["status"], "applied")
        self.assertEqual(first_metadata, metadata_path.read_bytes())
        self.assertEqual(
            first_workflow, (project / ".trellis/workflow.md").read_bytes()
        )
        self.assertEqual(metadata_mtime, metadata_path.stat().st_mtime_ns)
        self.assertEqual(
            workflow_mtime, (project / ".trellis/workflow.md").stat().st_mtime_ns
        )
        payload = json.loads(first_metadata)
        self.assertEqual(payload["overlay_id"], MANAGER.OVERLAY_ID)
        self.assertEqual(payload["overlay_version"], MANAGER.OVERLAY_VERSION)
        self.assertEqual(payload["verification"]["status"], "verified")

    def test_project_lock_serializes_separate_descriptors(self) -> None:
        project = self.create_project()
        trellis_dir = project / ".trellis"
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)

        with MANAGER.project_lock(project, fcntl.LOCK_EX):
            descriptor = os.open(trellis_dir, flags)
            try:
                with self.assertRaises(BlockingIOError):
                    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            finally:
                os.close(descriptor)

        descriptor = os.open(trellis_dir, flags)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)

    def test_optional_platform_file_is_patched_when_present(self) -> None:
        project = self.create_project()
        optional = project / ".agents/skills/trellis-start/SKILL.md"
        optional.parent.mkdir(parents=True)
        optional.write_text(OPTIONAL_BASELINE, encoding="utf-8")

        report = self.apply(project)

        self.assertEqual(report["status"], "applied")
        self.assertEqual(optional.read_text(encoding="utf-8"), OPTIONAL_OVERLAY)

    def test_audited_compatible_overlay_is_preserved_and_recorded(self) -> None:
        project = self.create_project()
        workflow = project / ".trellis/workflow.md"
        workflow.write_text(WORKFLOW_COMPATIBLE, encoding="utf-8")

        report = self.apply(project)

        self.assertEqual(report["status"], "applied")
        self.assertEqual(workflow.read_text(encoding="utf-8"), WORKFLOW_COMPATIBLE)
        metadata = json.loads(
            (project / MANAGER.METADATA_REL_PATH).read_text(encoding="utf-8")
        )
        files = metadata["verification"]["files"]
        workflow_entry = next(
            item for item in files if item["path"] == ".trellis/workflow.md"
        )
        self.assertEqual(
            workflow_entry["sha256"],
            MANAGER.sha256_bytes(WORKFLOW_COMPATIBLE.encode()),
        )

    def test_versioned_migration_is_applied_and_recorded(self) -> None:
        project = self.create_project()
        workflow = project / ".trellis/workflow.md"
        workflow.write_text(WORKFLOW_OLD_OVERLAY, encoding="utf-8")
        metadata_path = project / MANAGER.METADATA_REL_PATH
        metadata_path.parent.mkdir(parents=True)
        metadata_path.write_text(
            json.dumps(
                {
                    "overlay_id": MANAGER.OVERLAY_ID,
                    "overlay_version": "0.9.0",
                }
            ),
            encoding="utf-8",
        )

        before = self.inspect(project)
        file_reports = cast(list[dict[str, object]], before["files"])
        workflow_report = next(
            item for item in file_reports if item["path"] == ".trellis/workflow.md"
        )
        after = self.apply(project)

        self.assertEqual(before["status"], "needs_apply")
        self.assertEqual(workflow_report["status"], "migration")
        migration = workflow_report["migration"]
        if not isinstance(migration, dict):
            self.fail("migration report is not an object")
        self.assertEqual(migration["source_overlay_version"], "0.9.0")
        self.assertEqual(after["status"], "applied")
        self.assertEqual(workflow.read_text(encoding="utf-8"), WORKFLOW_OVERLAY)
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        self.assertEqual(metadata["overlay_version"], MANAGER.OVERLAY_VERSION)

    def test_migration_requires_recorded_source_overlay_version(self) -> None:
        project = self.create_project()
        workflow = project / ".trellis/workflow.md"
        workflow.write_text(WORKFLOW_OLD_OVERLAY, encoding="utf-8")

        report = self.inspect(project)

        self.assertEqual(report["status"], "conflict")
        errors = cast(list[object], report["errors"])
        self.assertTrue(
            any(
                "without a recorded source overlay version" in str(error)
                for error in errors
            )
        )
        with self.assertRaisesRegex(
            RuntimeError,
            "without a recorded source overlay version",
        ):
            self.apply(project)
        self.assertEqual(workflow.read_text(encoding="utf-8"), WORKFLOW_OLD_OVERLAY)
        self.assertFalse((project / MANAGER.METADATA_REL_PATH).exists())

    def test_conflict_preflight_prevents_partial_writes(self) -> None:
        project = self.create_project()
        workflow = project / ".trellis/workflow.md"
        task = project / ".trellis/scripts/task.py"
        task.write_text("local change\n", encoding="utf-8")
        before = workflow.read_bytes()

        with self.assertRaises(RuntimeError):
            self.apply(project)

        self.assertEqual(workflow.read_bytes(), before)
        self.assertEqual(task.read_text(encoding="utf-8"), "local change\n")
        self.assertFalse((project / MANAGER.METADATA_REL_PATH).exists())

    def test_bulk_conflict_preflight_writes_no_projects(self) -> None:
        first = self.create_project("projects/first")
        second = self.create_project("projects/second")
        first_workflow = first / ".trellis/workflow.md"
        second_task = second / ".trellis/scripts/task.py"
        first_before = first_workflow.read_bytes()
        second_task.write_text("local change\n", encoding="utf-8")

        reports = MANAGER.apply_projects([second, first], self.patch_sets)

        self.assertEqual(
            [report["status"] for report in reports],
            ["needs_apply", "conflict"],
        )
        self.assertEqual(first_workflow.read_bytes(), first_before)
        self.assertFalse((first / MANAGER.METADATA_REL_PATH).exists())
        self.assertEqual(second_task.read_text(encoding="utf-8"), "local change\n")
        self.assertFalse((second / MANAGER.METADATA_REL_PATH).exists())

    def test_bulk_apply_holds_every_project_lock_during_writes(self) -> None:
        first = self.create_project("projects/first")
        second = self.create_project("projects/second")
        original_atomic_write = MANAGER.atomic_write
        locks_checked = False

        def verify_locks(path: Path, data: bytes, mode: int) -> object:
            nonlocal locks_checked
            if not locks_checked:
                locks_checked = True
                for project in (first, second):
                    descriptor = os.open(
                        project / ".trellis",
                        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
                    )
                    try:
                        with self.assertRaises(BlockingIOError):
                            fcntl.flock(
                                descriptor,
                                fcntl.LOCK_EX | fcntl.LOCK_NB,
                            )
                    finally:
                        os.close(descriptor)
            return original_atomic_write(path, data, mode)

        with patch.object(MANAGER, "atomic_write", side_effect=verify_locks):
            reports = MANAGER.apply_projects([second, first], self.patch_sets)

        self.assertTrue(locks_checked)
        self.assertEqual(
            [report["status"] for report in reports],
            ["applied", "applied"],
        )

    def test_write_failure_rolls_back_prior_updates(self) -> None:
        project = self.create_project()
        workflow = project / ".trellis/workflow.md"
        task = project / ".trellis/scripts/task.py"
        workflow_before = workflow.read_bytes()
        task_before = task.read_bytes()
        original_atomic_write = MANAGER.atomic_write
        write_count = 0

        def fail_second_write(path: Path, data: bytes, mode: int) -> object:
            nonlocal write_count
            write_count += 1
            if write_count == 2:
                raise OSError("injected write failure")
            return original_atomic_write(path, data, mode)

        with patch.object(MANAGER, "atomic_write", side_effect=fail_second_write):
            with self.assertRaisesRegex(RuntimeError, "changes were rolled back"):
                self.apply(project)

        self.assertEqual(workflow.read_bytes(), workflow_before)
        self.assertEqual(task.read_bytes(), task_before)
        self.assertFalse((project / MANAGER.METADATA_REL_PATH).exists())
        self.assertEqual(list(project.rglob("*.tmp")), [])

    def test_rollback_preserves_a_concurrent_update(self) -> None:
        project = self.create_project()
        workflow = project / ".trellis/workflow.md"
        task = project / ".trellis/scripts/task.py"
        concurrent_data = b"concurrent workflow update\n"
        original_atomic_write = MANAGER.atomic_write
        write_count = 0

        def mutate_after_first_write(path: Path, data: bytes, mode: int) -> object:
            nonlocal write_count
            write_count += 1
            if write_count == 2:
                raise OSError("injected write failure")
            installed = original_atomic_write(path, data, mode)
            if write_count == 1:
                path.write_bytes(concurrent_data)
            return installed

        with patch.object(
            MANAGER, "atomic_write", side_effect=mutate_after_first_write
        ):
            with self.assertRaisesRegex(RuntimeError, "rollback incomplete"):
                self.apply(project)

        self.assertEqual(workflow.read_bytes(), concurrent_data)
        self.assertEqual(task.read_text(encoding="utf-8"), TASK_BASELINE)
        self.assertFalse((project / MANAGER.METADATA_REL_PATH).exists())

    def test_concurrent_metadata_creation_is_preserved(self) -> None:
        project = self.create_project()
        task = (project / ".trellis/scripts/task.py").resolve()
        metadata_path = (project / MANAGER.METADATA_REL_PATH).resolve()
        concurrent_metadata = b'{"overlay_id":"concurrent-owner"}\n'
        original_atomic_write = MANAGER.atomic_write

        def create_metadata_after_target_write(
            path: Path, data: bytes, mode: int
        ) -> object:
            installed = original_atomic_write(path, data, mode)
            if path == task:
                metadata_path.parent.mkdir(parents=True, exist_ok=True)
                metadata_path.write_bytes(concurrent_metadata)
            return installed

        with patch.object(
            MANAGER, "atomic_write", side_effect=create_metadata_after_target_write
        ):
            with self.assertRaisesRegex(RuntimeError, "metadata changed during apply"):
                self.apply(project)

        self.assertEqual(metadata_path.read_bytes(), concurrent_metadata)

    def test_rollback_preserves_metadata_replaced_after_publication(self) -> None:
        project = self.create_project()
        metadata_path = project / MANAGER.METADATA_REL_PATH
        concurrent_metadata = b'{"overlay_id":"concurrent-owner"}\n'
        original_atomic_create = MANAGER.atomic_create

        def replace_published_metadata(path: Path, data: bytes, mode: int) -> object:
            installed = original_atomic_create(path, data, mode)
            path.write_bytes(concurrent_metadata)
            return installed

        with patch.object(
            MANAGER,
            "atomic_create",
            side_effect=replace_published_metadata,
        ):
            with self.assertRaisesRegex(RuntimeError, "rollback incomplete"):
                self.apply(project)

        self.assertEqual(metadata_path.read_bytes(), concurrent_metadata)

    def test_published_metadata_is_tracked_when_temporary_cleanup_fails(self) -> None:
        project = self.create_project()
        workflow = project / ".trellis/workflow.md"
        task = project / ".trellis/scripts/task.py"
        metadata_path = project / MANAGER.METADATA_REL_PATH
        workflow_before = workflow.read_bytes()
        task_before = task.read_bytes()
        original_unlink = Path.unlink
        cleanup_failed = False

        def fail_first_metadata_temp_cleanup(
            path: Path, missing_ok: bool = False
        ) -> None:
            nonlocal cleanup_failed
            if path.name.endswith(".tmp") and not cleanup_failed:
                cleanup_failed = True
                raise OSError("injected temporary cleanup failure")
            original_unlink(path, missing_ok=missing_ok)

        with patch.object(
            type(metadata_path),
            "unlink",
            new=fail_first_metadata_temp_cleanup,
        ):
            with self.assertRaisesRegex(RuntimeError, "changes were rolled back"):
                self.apply(project)

        self.assertTrue(cleanup_failed)
        self.assertEqual(workflow.read_bytes(), workflow_before)
        self.assertEqual(task.read_bytes(), task_before)
        self.assertFalse(metadata_path.exists())
        self.assertEqual(list(metadata_path.parent.glob("*.tmp")), [])

    def test_unknown_version_fails_closed(self) -> None:
        project = self.create_project()
        (project / ".trellis/.version").write_text("9.9.9", encoding="utf-8")
        before = (project / ".trellis/workflow.md").read_bytes()

        report = MANAGER.inspect_project(project, self.patch_sets)

        self.assertEqual(report["status"], "unsupported")
        self.assertEqual((project / ".trellis/workflow.md").read_bytes(), before)

    def test_symlinked_target_is_rejected_without_touching_destination(self) -> None:
        project = self.create_project()
        target = project / ".trellis/workflow.md"
        destination = self.root / "outside.md"
        destination.write_text(WORKFLOW_BASELINE, encoding="utf-8")
        target.unlink()
        target.symlink_to(destination)

        report = self.inspect(project)

        self.assertEqual(report["status"], "conflict")
        self.assertEqual(destination.read_text(encoding="utf-8"), WORKFLOW_BASELINE)

    def test_hard_linked_target_is_rejected_without_touching_destination(self) -> None:
        project = self.create_project()
        target = project / ".trellis/workflow.md"
        destination = self.root / "outside-hardlink.md"
        destination.write_text(WORKFLOW_BASELINE, encoding="utf-8")
        target.unlink()
        target.hardlink_to(destination)

        report = self.inspect(project)

        self.assertEqual(report["status"], "conflict")
        self.assertEqual(destination.read_text(encoding="utf-8"), WORKFLOW_BASELINE)

    def test_apply_does_not_touch_task_spec_workspace_or_runtime_state(self) -> None:
        project = self.create_project()
        sentinels = {
            project / ".trellis/tasks/example/task.json": b'{"status":"planning"}\n',
            project / ".trellis/spec/index.md": b"spec\n",
            project / ".trellis/workspace/user/journal-1.md": b"journal\n",
            project / ".trellis/.runtime/sessions/window.json": b'{"task":"x"}\n',
            project / ".trellis/.template-hashes.json": b"{}\n",
            project / ".trellis/.developer": b"user\n",
            project / ".trellis/.current-task": b"legacy\n",
            project / ".trellis/config.yaml": b"session_auto_commit: false\n",
        }
        for path, data in sentinels.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)

        self.apply(project)

        for path, data in sentinels.items():
            self.assertEqual(path.read_bytes(), data)

    def test_scan_finds_projects_and_prunes_dependency_trees(self) -> None:
        first = self.create_project("projects/one")
        second = self.create_project("projects/nested/two")
        ignored = self.create_project("projects/node_modules/ignored")

        discovered = MANAGER.discover_projects([self.root / "projects"])

        self.assertEqual(
            discovered, sorted([first.resolve(), second.resolve()], key=str)
        )
        self.assertNotIn(ignored.resolve(), discovered)

    def test_patch_resource_fingerprint_mismatch_is_blocking(self) -> None:
        project = self.create_project()
        self.patch_path.write_text(FIXTURE_PATCH + "\n", encoding="utf-8")

        with self.assertRaises(RuntimeError):
            self.apply(project)

    def test_protected_directory_roots_are_rejected(self) -> None:
        baseline_sha256 = MANAGER.sha256_bytes(b"baseline")
        overlay_sha256 = MANAGER.sha256_bytes(b"overlay")

        for protected_path in (
            ".trellis/.runtime",
            ".trellis/spec",
            ".trellis/tasks",
            ".trellis/workspace",
        ):
            with self.subTest(path=protected_path):
                patch_set = MANAGER.PatchSet(
                    trellis_version="fixture",
                    patch_path=self.patch_path,
                    patch_sha256=MANAGER.sha256_bytes(FIXTURE_PATCH.encode()),
                    files=(
                        MANAGER.FileSpec(
                            protected_path,
                            baseline_sha256,
                            overlay_sha256,
                            required=True,
                        ),
                    ),
                )
                with self.assertRaisesRegex(RuntimeError, "protected path"):
                    MANAGER.validate_patch_set(patch_set)

    def test_production_patch_manifests_and_resources_are_internally_consistent(
        self,
    ) -> None:
        expected_file_counts = {"0.6.7": 18, "0.6.14": 18}

        for version, expected_file_count in expected_file_counts.items():
            with self.subTest(version=version):
                production = MANAGER.PATCH_SETS[version]
                parsed = MANAGER.load_patch_document(production)

                self.assertEqual(production.trellis_version, version)
                self.assertEqual(len(parsed), expected_file_count)
                self.assertEqual(
                    set(parsed),
                    {file_spec.path for file_spec in production.files},
                )

    def test_production_lite_compatibility_hashes_are_exact(self) -> None:
        production_067 = MANAGER.PATCH_SETS["0.6.7"]
        extension = next(
            spec
            for spec in production_067.files
            if spec.path == ".omp/extensions/trellis/index.ts"
        )
        self.assertEqual(
            extension.compatible_overlay_sha256s[-2:],
            (
                "7357b764398f648b44607c42b6033425aaad2b1d755a8df34586c6bb090a2a0c",
                "f03f1d23b299a56ea9e5d88eafa962d252fe3a3eab7459a39bb79be111e11176",
            ),
        )
        workflow_067 = next(
            spec
            for spec in production_067.files
            if spec.path == ".trellis/workflow.md"
        )
        self.assertEqual(
            workflow_067.compatible_overlay_sha256s[-2:],
            (
                "e4b42a0232b2a70a67934dc51a7b66d7dc9cd4b920b2af14f19c052a4f8b06de",
                "9cfb471130185643cc4b39849e8388bb560aaf7fdbffe4f35e1bec39e70cf0de",
            ),
        )

        production_0614 = MANAGER.PATCH_SETS["0.6.14"]
        actual = {
            spec.path: spec.compatible_overlay_sha256s
            for spec in production_0614.files
            if spec.compatible_overlay_sha256s
        }
        self.assertEqual(
            actual,
            {
                ".trellis/workflow.md": (
                    "e4b42a0232b2a70a67934dc51a7b66d7dc9cd4b920b2af14f19c052a4f8b06de",
                    "9cfb471130185643cc4b39849e8388bb560aaf7fdbffe4f35e1bec39e70cf0de",
                ),
                ".agents/skills/trellis-brainstorm/SKILL.md": (
                    "040e9a60859e74b1ad0ff1c35fd6624eaeb3bd5dab3de692f6dbfc0fe41db1e4",
                ),
                ".agents/skills/trellis-start/SKILL.md": (
                    "d23e0fa3970da633986c83e0e2ac244e3cb7331a1bd36a1c57a798e89693e42b",
                ),
                ".agents/skills/trellis-continue/SKILL.md": (
                    "482c4b70a7e3ddfe62b46d301046104b4d9719486bd463aa5b242e9212d51292",
                ),
                ".omp/skills/trellis-brainstorm/SKILL.md": (
                    "040e9a60859e74b1ad0ff1c35fd6624eaeb3bd5dab3de692f6dbfc0fe41db1e4",
                ),
                ".omp/commands/trellis-continue.md": (
                    "03de3c9f30fd23d98e50235ee64443a2acc293317b3b9e065fa08c73c17d5bfc",
                ),
            },
        )

    def test_production_0614_session_start_directive_is_reuse_first(self) -> None:
        production = MANAGER.PATCH_SETS["0.6.14"]
        session_start = next(
            spec
            for spec in production.files
            if spec.path == ".codex/hooks/session-start.py"
        )
        patch_text = production.patch_path.read_text(encoding="utf-8")

        self.assertFalse(session_start.required)
        self.assertIn("--- a/.codex/hooks/session-start.py", patch_text)
        self.assertIn(
            '+            "Next: Search unarchived tasks before proposing creation; reuse the one "',
            patch_text,
        )
        self.assertNotIn(
            '+            "Next: Classify the current turn and ask for task-creation consent "',
            patch_text,
        )

    def test_production_old_overlays_are_migrations_not_compatible_variants(
        self,
    ) -> None:
        production = MANAGER.PATCH_SETS["0.6.7"]
        task = next(
            spec for spec in production.files if spec.path == ".trellis/scripts/task.py"
        )
        active_task = next(
            spec
            for spec in production.files
            if spec.path == ".trellis/scripts/common/active_task.py"
        )

        self.assertEqual(
            {migration.source_overlay_version for migration in task.migrations},
            {"1.0.0", "1.0.1"},
        )
        self.assertEqual(
            {migration.source_sha256 for migration in task.migrations},
            {"ba1df54c674376a6ac19aa11af872de5902ce817c4116957083ef0335a06bd3a"},
        )
        self.assertEqual(
            {migration.source_sha256 for migration in active_task.migrations},
            {"72629bb4703ddacc5a3e3fc77597b6c0503f694c9dd41ab92eeeb011a6867e28"},
        )
        self.assertEqual(task.compatible_overlay_sha256s, ())
        self.assertEqual(active_task.compatible_overlay_sha256s, ())
        for file_spec in (task, active_task):
            for migration in file_spec.migrations:
                MANAGER.load_migration_document(file_spec, migration)

    def test_production_patch_preserves_native_pi_when_adding_omp(self) -> None:
        patch_text = MANAGER.PATCH_067.read_text(encoding="utf-8")
        pi_mapping = '    ("pi", ("PI_SESSION_ID", "PI_SESSIONID")),'
        omp_mapping = '    ("omp", ("PI_SESSION_ID", "PI_SESSIONID")),'

        self.assertNotIn(f"-{pi_mapping}", patch_text)
        self.assertIn(f" {pi_mapping}", patch_text)
        self.assertIn(f"+{omp_mapping}", patch_text)

    def test_production_task_use_requires_an_active_task_directory(self) -> None:
        patch_text = MANAGER.PATCH_067.read_text(encoding="utf-8")

        self.assertIn("is_within_tasks_dir", patch_text)
        self.assertIn("task_json_path.is_file()", patch_text)
        self.assertIn("Status preserved: {task_data['status']}", patch_text)
        self.assertNotIn("Status preserved: {status}", patch_text)


if __name__ == "__main__":
    unittest.main()
