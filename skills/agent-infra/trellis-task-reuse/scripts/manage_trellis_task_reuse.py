#!/usr/bin/env python3
"""Audit and apply the versioned Trellis task-reuse overlay."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import stat
import tempfile
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator, Sequence, cast

OVERLAY_ID = "trellis-task-reuse"
OVERLAY_VERSION = "1.0.3"
METADATA_SCHEMA_VERSION = 1
METADATA_REL_PATH = Path(".trellis/.overlays/trellis-task-reuse.json")
SKILL_ROOT = Path(__file__).resolve().parents[1]


class OverlayError(RuntimeError):
    """The overlay cannot proceed without risking local project state."""


@dataclass(frozen=True)
class MigrationSpec:
    source_overlay_version: str
    source_sha256: str
    patch_path: Path
    patch_sha256: str


@dataclass(frozen=True)
class FileSpec:
    path: str
    baseline_sha256: str
    overlay_sha256: str
    required: bool = False
    compatible_overlay_sha256s: tuple[str, ...] = ()
    migrations: tuple[MigrationSpec, ...] = ()


@dataclass(frozen=True)
class PatchSet:
    trellis_version: str
    patch_path: Path
    patch_sha256: str
    files: tuple[FileSpec, ...]


@dataclass(frozen=True)
class Hunk:
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    lines: tuple[str, ...]


@dataclass(frozen=True)
class FileState:
    data: bytes
    mode: int
    device: int
    inode: int


@dataclass(frozen=True)
class AppliedWrite:
    original: FileState | None
    installed: FileState


class PublishedCreateCleanupError(OverlayError):
    """A no-replace publication succeeded but its temporary link remains."""

    def __init__(
        self,
        path: Path,
        installed: FileState,
        temporary_path: Path,
        error: OSError,
    ) -> None:
        super().__init__(f"cannot remove temporary link for {path}: {error}")
        self.installed = installed
        self.temporary_path = temporary_path


PATCH_067 = SKILL_ROOT / "patches" / "trellis-0.6.7-task-reuse.patch"
PATCH_067_SHA256 = "e1be9d736814e3208d6830a33ca99f66f754c843e8733a1279f535e8e3c21e0c"
PATCH_067_TASK_MIGRATION = SKILL_ROOT / "patches" / "trellis-0.6.7-task-to-1.0.2.patch"
PATCH_067_TASK_MIGRATION_SHA256 = (
    "43e76445948cb4c054056f18ecc1ade989ae84ed54c4fedd52fc34ab1fc528e4"
)
PATCH_067_ACTIVE_TASK_MIGRATION = (
    SKILL_ROOT / "patches" / "trellis-0.6.7-active-task-to-1.0.2.patch"
)
PATCH_067_ACTIVE_TASK_MIGRATION_SHA256 = (
    "8140d2e7f1d22c0980202f14187184d7d9d9f9d1f657efb5ac8ae7b5d1df12d5"
)
PATCH_0614 = SKILL_ROOT / "patches" / "trellis-0.6.14-task-reuse.patch"
PATCH_0614_SHA256 = "276f1d36c6315733e944e501b98adf2a112481637facef0257dfe5767f45ee2a"

PATCH_SETS: dict[str, PatchSet] = {
    "0.6.7": PatchSet(
        trellis_version="0.6.7",
        patch_path=PATCH_067,
        patch_sha256=PATCH_067_SHA256,
        files=(
            FileSpec(
                ".trellis/workflow.md",
                "9eb806e50767409b26dba4a63f34bc8cf58a8affcc18fe83e47568b5aca23510",
                "6a0918bb68a5af1f6f0aba0efc004584d5819b36e2b84c093ea0dfdf1cc30ce6",
                required=True,
                compatible_overlay_sha256s=(
                    "0dbc59aa0df5a35e41da1973cf5f38efaa6f9add75bc2fec442730beaa698e08",
                    "a9e2947a60ceab3acfd2d8c711323e72dbceaea9374e120a5dae1f98e254c54d",
                    "e4b42a0232b2a70a67934dc51a7b66d7dc9cd4b920b2af14f19c052a4f8b06de",
                    "9cfb471130185643cc4b39849e8388bb560aaf7fdbffe4f35e1bec39e70cf0de",
                    "cc47c03259d07ef5ea44474c99c265a4544ee65f3edfefa49f52668ce2efb9de",
                ),
            ),
            FileSpec(
                ".trellis/scripts/task.py",
                "46a94e4acf1c967fe5c3606ba5d1572cd0c43033a16fe01de55ac568954e6c18",
                "2af4011b612f225c72d26d9523b14d1828455b3a25ebe15df63f6094da9cae48",
                required=True,
                migrations=(
                    MigrationSpec(
                        source_overlay_version="1.0.0",
                        source_sha256="ba1df54c674376a6ac19aa11af872de5902ce817c4116957083ef0335a06bd3a",
                        patch_path=PATCH_067_TASK_MIGRATION,
                        patch_sha256=PATCH_067_TASK_MIGRATION_SHA256,
                    ),
                    MigrationSpec(
                        source_overlay_version="1.0.1",
                        source_sha256="ba1df54c674376a6ac19aa11af872de5902ce817c4116957083ef0335a06bd3a",
                        patch_path=PATCH_067_TASK_MIGRATION,
                        patch_sha256=PATCH_067_TASK_MIGRATION_SHA256,
                    ),
                ),
            ),
            FileSpec(
                ".trellis/scripts/common/active_task.py",
                "8ac10263a88262aeaec2c600b33f3761f99d80c305718609a3bef97a2ff08938",
                "c71e2100dc0e269136d6fc14bf1154e2e5013c0b5702309e05cc8c3d0e29f05a",
                required=True,
                migrations=(
                    MigrationSpec(
                        source_overlay_version="1.0.0",
                        source_sha256="72629bb4703ddacc5a3e3fc77597b6c0503f694c9dd41ab92eeeb011a6867e28",
                        patch_path=PATCH_067_ACTIVE_TASK_MIGRATION,
                        patch_sha256=PATCH_067_ACTIVE_TASK_MIGRATION_SHA256,
                    ),
                ),
            ),
            FileSpec(
                ".trellis/scripts/common/task_store.py",
                "0810ca640b7423dce39bdf0528120438bbeae49e443dc105d9eea28b1824b9a6",
                "f568bc0a3d52f34e5d0009ed7e8c65e57359f1807ea867c940631b796d78c3af",
                required=True,
            ),
            FileSpec(
                ".agents/skills/trellis-brainstorm/SKILL.md",
                "3bbfb6506af3c318c6f9b3c280517ce93a02e40e27535de7ff5fc029d3027860",
                "ed3a18999b561412741b8437867591773722fbc977f79d3e8199a635474c93ee",
                compatible_overlay_sha256s=(
                    "6e7efcaa36fe205be9804ae35346395aea7aa024e9e0d63dec62d6651016cd5f",
                    "040e9a60859e74b1ad0ff1c35fd6624eaeb3bd5dab3de692f6dbfc0fe41db1e4",
                ),
            ),
            FileSpec(
                ".agents/skills/trellis-start/SKILL.md",
                "79a5ba7a2aff3c72e06d7f4cd6942dc4f4f4092dd40f9c8e94f1838024a81e4d",
                "c2cf7022e1c00564bd3c1dd2fe1633d662f51c2ce240d10388da64de219459dc",
                compatible_overlay_sha256s=(
                    "43c59c6269dfc4421d995a8bd45c50138bfdd690aead5b83667fcbd16ee2dbb2",
                    "16ccf3fc6399893e4d51baf3c0bf31fc887c4d06bf6fa86f1a577e25d2f28076",
                    "d23e0fa3970da633986c83e0e2ac244e3cb7331a1bd36a1c57a798e89693e42b",
                ),
            ),
            FileSpec(
                ".agents/skills/trellis-continue/SKILL.md",
                "7723ccf49fbf19d8f086cacc7a080bd8be8db6fc70a32908b80f68efa318d7bf",
                "745d3811dad215d6c9055f54a4a5cd699844c6e93f86323cd7461f79ed0bd2dc",
                compatible_overlay_sha256s=(
                    "75ec153cd26d58982bcbbcf19f501fd19ef8505aa21d4aa35ff81732a0683f0d",
                    "eede8d13227f98c81d40978d9258ea5f39b0b862cf6b56191c07851cdd3f28e5",
                    "482c4b70a7e3ddfe62b46d301046104b4d9719486bd463aa5b242e9212d51292",
                ),
            ),
            FileSpec(
                ".agents/skills/trellis-meta/references/customize-local/change-task-lifecycle.md",
                "60ff9efb93604b87a461a4af30322d76750402a51e40f31531a7ff88d309996d",
                "a96f3924bda2d221b14468b8c04d81c7ee38b259ca5a072ddb1e32652f0e2a00",
                compatible_overlay_sha256s=(
                    "a825bc42c5c67cfa5722faddff49aeb20c24ba278ff4c5b5e281433649d4ca3b",
                ),
            ),
            FileSpec(
                ".agents/skills/trellis-meta/references/local-architecture/task-system.md",
                "2b561d49c390f7d0db5391912946133be4bf73189231e2b8cc9afa1c5ac6165a",
                "0134f7fead6d1dbe1849a2e9e2dd1e757b08ba540b569474c5cdd4fc270f2023",
                compatible_overlay_sha256s=(
                    "7d912f3f3fd71c25bfda53f472742394acd8f7649d16c0bf03eb7cab4348c41c",
                ),
            ),
            FileSpec(
                ".agents/skills/trellis-session-insight/SKILL.md",
                "a1a5bf53aaf5cd5a48137b7bf01b6c4685c9bdd0d1796f595e7bd90e12c3a6a0",
                "0b38825e2099f2808512cefe769b20c667fd63b5319bb1cbe6347c2feb316e6a",
                compatible_overlay_sha256s=(
                    "0ad224596c92bcc19d52861ab89acd25efdc79821b24d590d778ef23310bbc82",
                ),
            ),
            FileSpec(
                ".agents/skills/trellis-session-insight/references/cli-quick-reference.md",
                "c520353fe3fc00b9702ed4f780647c8fbd6d342e66527a03647f533a9fe09779",
                "eff1b548f47b7779f401a78c76386730731f8dbceb5e66f33695d4d678e21692",
                compatible_overlay_sha256s=(
                    "e820b5ff1efe60ecb717c0c30e62270582317fcd42baab95a10565d14ad8e95a",
                ),
            ),
            FileSpec(
                ".omp/extensions/trellis/index.ts",
                "c33e75a3e3601999aa42be04e3c492e432175643f74dcaa49e5b6af26797e478",
                "10cb806e89ba7d0c1bdb0c56168ca5999a07d0ed05e45fb9282ad680f7c4ef4a",
                compatible_overlay_sha256s=(
                    "d3f9740d3eca30d0ce3284e6fe7f55a01ee400a1ce225e42c42b8e9201ee4c71",
                    "8e69cec07e9e2b8b93f8d862e98a0b89ee839ce01a5dc9c797511fdf1048c65a",
                    "7009c8f32d4d8c38cc02fa7ec402a2f29c3d4722c147c5ad6121426c82a9c875",
                    "62520c25f195678ebd4e8644e249b07595e9d8ce83df50d8f8bb2701944d3035",
                    "7357b764398f648b44607c42b6033425aaad2b1d755a8df34586c6bb090a2a0c",
                    "f03f1d23b299a56ea9e5d88eafa962d252fe3a3eab7459a39bb79be111e11176",
                ),
            ),
            FileSpec(
                ".omp/skills/trellis-brainstorm/SKILL.md",
                "3bbfb6506af3c318c6f9b3c280517ce93a02e40e27535de7ff5fc029d3027860",
                "a01199832ee26b9449f02ce87b25cb8f6a7ac3aa7f6e92809a8eb1b638bbedf5",
                compatible_overlay_sha256s=(
                    "6e7efcaa36fe205be9804ae35346395aea7aa024e9e0d63dec62d6651016cd5f",
                    "040e9a60859e74b1ad0ff1c35fd6624eaeb3bd5dab3de692f6dbfc0fe41db1e4",
                ),
            ),
            FileSpec(
                ".omp/commands/trellis-continue.md",
                "e4b0a731cfc23859436766c0242bfe133f63dd0d3ea94198c9cfa1ea21e64808",
                "97e38675c1004b79ede3d25d2950cf5979637050f31394179bc7b830c648fb8d",
                compatible_overlay_sha256s=(
                    "81bfd7538530ef0a2fd5c9d151191e800122cd205eb66ce9579d2e93ff20faf9",
                    "03de3c9f30fd23d98e50235ee64443a2acc293317b3b9e065fa08c73c17d5bfc",
                ),
            ),
            FileSpec(
                ".omp/skills/trellis-meta/references/customize-local/change-task-lifecycle.md",
                "60ff9efb93604b87a461a4af30322d76750402a51e40f31531a7ff88d309996d",
                "a96f3924bda2d221b14468b8c04d81c7ee38b259ca5a072ddb1e32652f0e2a00",
                compatible_overlay_sha256s=(
                    "a825bc42c5c67cfa5722faddff49aeb20c24ba278ff4c5b5e281433649d4ca3b",
                ),
            ),
            FileSpec(
                ".omp/skills/trellis-meta/references/local-architecture/task-system.md",
                "2b561d49c390f7d0db5391912946133be4bf73189231e2b8cc9afa1c5ac6165a",
                "0134f7fead6d1dbe1849a2e9e2dd1e757b08ba540b569474c5cdd4fc270f2023",
                compatible_overlay_sha256s=(
                    "7d912f3f3fd71c25bfda53f472742394acd8f7649d16c0bf03eb7cab4348c41c",
                ),
            ),
            FileSpec(
                ".omp/skills/trellis-session-insight/SKILL.md",
                "a1a5bf53aaf5cd5a48137b7bf01b6c4685c9bdd0d1796f595e7bd90e12c3a6a0",
                "0b38825e2099f2808512cefe769b20c667fd63b5319bb1cbe6347c2feb316e6a",
                compatible_overlay_sha256s=(
                    "0ad224596c92bcc19d52861ab89acd25efdc79821b24d590d778ef23310bbc82",
                ),
            ),
            FileSpec(
                ".omp/skills/trellis-session-insight/references/cli-quick-reference.md",
                "c520353fe3fc00b9702ed4f780647c8fbd6d342e66527a03647f533a9fe09779",
                "eff1b548f47b7779f401a78c76386730731f8dbceb5e66f33695d4d678e21692",
                compatible_overlay_sha256s=(
                    "e820b5ff1efe60ecb717c0c30e62270582317fcd42baab95a10565d14ad8e95a",
                ),
            ),
        ),
    ),
    "0.6.14": PatchSet(
        trellis_version="0.6.14",
        patch_path=PATCH_0614,
        patch_sha256=PATCH_0614_SHA256,
        files=(
            FileSpec(
                ".trellis/workflow.md",
                "e2c5ab7004ff83a5a804b50df81746aa1d558dd4480463287622605f86a82a76",
                "d2ea5e032b53bf7931074519b8110b924968a1b184dd7850b62777c4202462d2",
                required=True,
                compatible_overlay_sha256s=(
                    "e4b42a0232b2a70a67934dc51a7b66d7dc9cd4b920b2af14f19c052a4f8b06de",
                    "9cfb471130185643cc4b39849e8388bb560aaf7fdbffe4f35e1bec39e70cf0de",
                    "cc47c03259d07ef5ea44474c99c265a4544ee65f3edfefa49f52668ce2efb9de",
                ),
            ),
            FileSpec(
                ".trellis/scripts/task.py",
                "e0ffed9f14994069f0c992141e3ec168524be5af32e3681e6ea30ba0a5da4bc4",
                "7bfdf220cc23d97a7e14b1c1de9ed2a829e6da0050474541d5e034e2592861ae",
                required=True,
            ),
            FileSpec(
                ".trellis/scripts/common/active_task.py",
                "28a81f8828538fb70a15c88edd90eda9d685adbde8862f67f630bce5b27d9832",
                "8c962930e85ee4c1302f41d816058dd669eb9bd0f6cd19104cfa848dd474f787",
                required=True,
            ),
            FileSpec(
                ".trellis/scripts/common/task_store.py",
                "e3c2fbf8b79b591e39fc3c9f4e2f3ee0c840c8201c94a16709ec743fa45037f6",
                "5019e1a4522465ceaeec340bee339ab6c9fcd88774140807840aed3adf45caea",
                required=True,
            ),
            FileSpec(
                ".agents/skills/trellis-brainstorm/SKILL.md",
                "a0f226ddcb8a3e846acd2a35d121996e9ca55165ce76202095d0b65e2b48a5e8",
                "ddb7f9b49966995f606cd212b9c3f891e986d343b9d461c23beb360cda644caf",
                compatible_overlay_sha256s=(
                    "040e9a60859e74b1ad0ff1c35fd6624eaeb3bd5dab3de692f6dbfc0fe41db1e4",
                ),
            ),
            FileSpec(
                ".agents/skills/trellis-start/SKILL.md",
                "79a5ba7a2aff3c72e06d7f4cd6942dc4f4f4092dd40f9c8e94f1838024a81e4d",
                "c2cf7022e1c00564bd3c1dd2fe1633d662f51c2ce240d10388da64de219459dc",
                compatible_overlay_sha256s=(
                    "d23e0fa3970da633986c83e0e2ac244e3cb7331a1bd36a1c57a798e89693e42b",
                ),
            ),
            FileSpec(
                ".agents/skills/trellis-continue/SKILL.md",
                "7723ccf49fbf19d8f086cacc7a080bd8be8db6fc70a32908b80f68efa318d7bf",
                "745d3811dad215d6c9055f54a4a5cd699844c6e93f86323cd7461f79ed0bd2dc",
                compatible_overlay_sha256s=(
                    "482c4b70a7e3ddfe62b46d301046104b4d9719486bd463aa5b242e9212d51292",
                ),
            ),
            FileSpec(
                ".codex/hooks/session-start.py",
                "14de3be1cf6eb9c9feba348d8998b407f3837d6c0756b74210c9200543440677",
                "b0a48027528d8bce3d3085a52a548e231c0ea3bdf3b440f181dc66f62c46a1ee",
            ),
            FileSpec(
                ".agents/skills/trellis-meta/references/customize-local/change-task-lifecycle.md",
                "60ff9efb93604b87a461a4af30322d76750402a51e40f31531a7ff88d309996d",
                "a96f3924bda2d221b14468b8c04d81c7ee38b259ca5a072ddb1e32652f0e2a00",
            ),
            FileSpec(
                ".agents/skills/trellis-meta/references/local-architecture/task-system.md",
                "2b561d49c390f7d0db5391912946133be4bf73189231e2b8cc9afa1c5ac6165a",
                "0134f7fead6d1dbe1849a2e9e2dd1e757b08ba540b569474c5cdd4fc270f2023",
            ),
            FileSpec(
                ".agents/skills/trellis-session-insight/SKILL.md",
                "d20f1d20c6946e26ba6f848b9a016d9a16c803d87501462e5b11a2ced6f56643",
                "26231d89563155b4a549e27dc94ab9f92b4b29e14a2f17e1ae3ff0f97c7cb753",
            ),
            FileSpec(
                ".agents/skills/trellis-session-insight/references/cli-quick-reference.md",
                "c520353fe3fc00b9702ed4f780647c8fbd6d342e66527a03647f533a9fe09779",
                "eff1b548f47b7779f401a78c76386730731f8dbceb5e66f33695d4d678e21692",
            ),
            FileSpec(
                ".omp/skills/trellis-brainstorm/SKILL.md",
                "a0f226ddcb8a3e846acd2a35d121996e9ca55165ce76202095d0b65e2b48a5e8",
                "4571fc7b9253647f7e31cc0f51251e21b3447a9dcd478a62763b877eecf8f5e4",
                compatible_overlay_sha256s=(
                    "040e9a60859e74b1ad0ff1c35fd6624eaeb3bd5dab3de692f6dbfc0fe41db1e4",
                ),
            ),
            FileSpec(
                ".omp/commands/trellis-continue.md",
                "6075e18c5661445475ecb20c4e1dd216b3c3790244311b4fc933ef365bd3ae0c",
                "d45eae4635bf37f41f5c2b49e87cd7e7623edebac6f9deb30ce41f6ecf7c9cc8",
                compatible_overlay_sha256s=(
                    "03de3c9f30fd23d98e50235ee64443a2acc293317b3b9e065fa08c73c17d5bfc",
                ),
            ),
            FileSpec(
                ".omp/skills/trellis-meta/references/customize-local/change-task-lifecycle.md",
                "60ff9efb93604b87a461a4af30322d76750402a51e40f31531a7ff88d309996d",
                "a96f3924bda2d221b14468b8c04d81c7ee38b259ca5a072ddb1e32652f0e2a00",
            ),
            FileSpec(
                ".omp/skills/trellis-meta/references/local-architecture/task-system.md",
                "2b561d49c390f7d0db5391912946133be4bf73189231e2b8cc9afa1c5ac6165a",
                "0134f7fead6d1dbe1849a2e9e2dd1e757b08ba540b569474c5cdd4fc270f2023",
            ),
            FileSpec(
                ".omp/skills/trellis-session-insight/SKILL.md",
                "d20f1d20c6946e26ba6f848b9a016d9a16c803d87501462e5b11a2ced6f56643",
                "26231d89563155b4a549e27dc94ab9f92b4b29e14a2f17e1ae3ff0f97c7cb753",
            ),
            FileSpec(
                ".omp/skills/trellis-session-insight/references/cli-quick-reference.md",
                "c520353fe3fc00b9702ed4f780647c8fbd6d342e66527a03647f533a9fe09779",
                "eff1b548f47b7779f401a78c76386730731f8dbceb5e66f33695d4d678e21692",
            ),
        ),
    ),
}

HUNK_HEADER = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(?: .*)?$")
PRUNED_SCAN_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "__pycache__",
    "node_modules",
    "vendor",
}
PROTECTED_PROJECT_PATHS = {
    ".trellis/.runtime",
    ".trellis/.current-task",
    ".trellis/.developer",
    ".trellis/.template-hashes.json",
    ".trellis/.version",
    ".trellis/config.yaml",
    ".trellis/spec",
    ".trellis/tasks",
    ".trellis/workspace",
}
PROTECTED_PROJECT_PREFIXES = (
    ".trellis/.runtime/",
    ".trellis/spec/",
    ".trellis/tasks/",
    ".trellis/workspace/",
)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def has_symlink_component(project: Path, target: Path) -> bool:
    relative = target.relative_to(project)
    current = project
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            return True
        if not current.exists():
            break
    return False


def validate_patch_set(patch_set: PatchSet) -> None:
    seen: set[str] = set()
    for spec in patch_set.files:
        path = Path(spec.path)
        normalized = path.as_posix()
        if path.is_absolute() or ".." in path.parts or normalized != spec.path:
            raise OverlayError(f"unsafe patch target in manifest: {spec.path}")
        if spec.path in seen:
            raise OverlayError(f"duplicate patch target in manifest: {spec.path}")
        if spec.path in PROTECTED_PROJECT_PATHS or spec.path.startswith(
            PROTECTED_PROJECT_PREFIXES
        ):
            raise OverlayError(f"protected path in patch manifest: {spec.path}")
        fingerprints = (
            spec.baseline_sha256,
            spec.overlay_sha256,
            *spec.compatible_overlay_sha256s,
        )
        if any(not re.fullmatch(r"[0-9a-f]{64}", value) for value in fingerprints):
            raise OverlayError(f"invalid target fingerprint in manifest: {spec.path}")
        if len(set(fingerprints)) != len(fingerprints):
            raise OverlayError(f"duplicate target fingerprint in manifest: {spec.path}")
        migration_keys: set[tuple[str, str]] = set()
        for migration in spec.migrations:
            if not migration.source_overlay_version.strip():
                raise OverlayError(f"empty migration version in manifest: {spec.path}")
            migration_fingerprints = (
                migration.source_sha256,
                migration.patch_sha256,
            )
            if any(
                not re.fullmatch(r"[0-9a-f]{64}", value)
                for value in migration_fingerprints
            ):
                raise OverlayError(
                    f"invalid migration fingerprint in manifest: {spec.path}"
                )
            if migration.source_sha256 in fingerprints:
                raise OverlayError(
                    f"migration source duplicates a current fingerprint: {spec.path}"
                )
            migration_key = (
                migration.source_overlay_version,
                migration.source_sha256,
            )
            if migration_key in migration_keys:
                raise OverlayError(
                    f"duplicate migration source in manifest: {spec.path}"
                )
            migration_keys.add(migration_key)
        seen.add(spec.path)


def find_project_root(start: Path) -> Path:
    candidate = start.expanduser()
    if not candidate.exists():
        raise OverlayError(f"project path does not exist: {candidate}")
    if candidate.is_file():
        candidate = candidate.parent
    candidate = candidate.resolve()
    for directory in (candidate, *candidate.parents):
        if (directory / ".trellis/.version").is_file():
            return directory
    raise OverlayError(f"no .trellis/.version found from {start}")


def read_trellis_version(project: Path) -> str:
    trellis_dir = project / ".trellis"
    version_path = trellis_dir / ".version"
    if trellis_dir.is_symlink() or version_path.is_symlink():
        raise OverlayError("refusing a symlinked .trellis directory or version file")
    try:
        version = version_path.read_text(encoding="utf-8").strip()
    except OSError as error:
        raise OverlayError(f"cannot read {version_path}: {error}") from error
    if not version:
        raise OverlayError(f"empty Trellis version file: {version_path}")
    return version


@contextmanager
def project_lock(project: Path, operation: int) -> Iterator[None]:
    """Lock the existing .trellis directory without creating project state."""
    trellis_dir = project / ".trellis"
    flags = os.O_RDONLY
    flags |= getattr(os, "O_DIRECTORY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    flags |= getattr(os, "O_CLOEXEC", 0)
    try:
        descriptor = os.open(trellis_dir, flags)
    except OSError as error:
        raise OverlayError(
            f"cannot open project lock {trellis_dir}: {error}"
        ) from error

    try:
        descriptor_stat = os.fstat(descriptor)
        if not stat.S_ISDIR(descriptor_stat.st_mode):
            raise OverlayError(f"project lock target is not a directory: {trellis_dir}")
        fcntl.flock(descriptor, operation)
        entry_stat = os.stat(trellis_dir, follow_symlinks=False)
        if not stat.S_ISDIR(entry_stat.st_mode) or (
            entry_stat.st_dev,
            entry_stat.st_ino,
        ) != (descriptor_stat.st_dev, descriptor_stat.st_ino):
            raise OverlayError(
                f"project lock target changed while waiting: {trellis_dir}"
            )
    except (OSError, OverlayError) as error:
        os.close(descriptor)
        if isinstance(error, OverlayError):
            raise
        raise OverlayError(
            f"cannot acquire project lock {trellis_dir}: {error}"
        ) from error

    try:
        yield
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def normalize_patch_path(raw: str, prefix: str) -> str:
    value = raw.rstrip("\n")
    if not value.startswith(prefix):
        raise OverlayError(f"invalid unified patch path: {value}")
    relative = value[len(prefix) :]
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts:
        raise OverlayError(f"unsafe unified patch path: {relative}")
    return path.as_posix()


def parse_unified_patch(raw: str) -> dict[str, tuple[Hunk, ...]]:
    lines = raw.splitlines(keepends=True)
    parsed: dict[str, tuple[Hunk, ...]] = {}
    index = 0
    while index < len(lines):
        if not lines[index].startswith("--- a/"):
            raise OverlayError(
                f"unexpected patch content at line {index + 1}: {lines[index].rstrip()}"
            )
        old_path = normalize_patch_path(lines[index][4:], "a/")
        index += 1
        if index >= len(lines) or not lines[index].startswith("+++ b/"):
            raise OverlayError(f"missing new-file header for {old_path}")
        new_path = normalize_patch_path(lines[index][4:], "b/")
        index += 1
        if old_path != new_path:
            raise OverlayError(
                f"rename patches are unsupported: {old_path} -> {new_path}"
            )

        hunks: list[Hunk] = []
        while index < len(lines) and not lines[index].startswith("--- a/"):
            match = HUNK_HEADER.match(lines[index].rstrip("\n"))
            if not match:
                raise OverlayError(
                    f"invalid hunk header for {old_path} at line {index + 1}"
                )
            old_start = int(match.group(1))
            old_count = int(match.group(2) or "1")
            new_start = int(match.group(3))
            new_count = int(match.group(4) or "1")
            index += 1
            hunk_lines: list[str] = []
            while index < len(lines):
                line = lines[index]
                if line.startswith("@@ ") or line.startswith("--- a/"):
                    break
                if line.startswith("\\ No newline at end of file"):
                    raise OverlayError("patches without final newlines are unsupported")
                if not line or line[0] not in {" ", "+", "-"}:
                    raise OverlayError(
                        f"invalid hunk line for {old_path} at line {index + 1}"
                    )
                hunk_lines.append(line)
                index += 1
            hunks.append(
                Hunk(
                    old_start=old_start,
                    old_count=old_count,
                    new_start=new_start,
                    new_count=new_count,
                    lines=tuple(hunk_lines),
                )
            )
        if not hunks:
            raise OverlayError(f"patch has no hunks for {old_path}")
        if old_path in parsed:
            raise OverlayError(f"duplicate patch target: {old_path}")
        parsed[old_path] = tuple(hunks)
    return parsed


def apply_hunks(source: str, path: str, hunks: Sequence[Hunk]) -> str:
    source_lines = source.splitlines(keepends=True)
    output: list[str] = []
    cursor = 0

    for hunk in hunks:
        target_index = hunk.old_start - 1
        if target_index < cursor or target_index > len(source_lines):
            raise OverlayError(f"overlapping or out-of-range hunk for {path}")
        output.extend(source_lines[cursor:target_index])
        cursor = target_index
        old_seen = 0
        new_seen = 0

        for patch_line in hunk.lines:
            operation = patch_line[0]
            content = patch_line[1:]
            if operation in {" ", "-"}:
                if cursor >= len(source_lines) or source_lines[cursor] != content:
                    raise OverlayError(
                        f"patch context mismatch for {path} at source line {cursor + 1}"
                    )
                cursor += 1
                old_seen += 1
            if operation in {" ", "+"}:
                output.append(content)
                new_seen += 1

        if old_seen != hunk.old_count or new_seen != hunk.new_count:
            raise OverlayError(
                f"hunk count mismatch for {path}: "
                f"old {old_seen}/{hunk.old_count}, new {new_seen}/{hunk.new_count}"
            )

    output.extend(source_lines[cursor:])
    return "".join(output)


def load_patch_resource(
    patch_path: Path, expected_sha256: str
) -> dict[str, tuple[Hunk, ...]]:
    try:
        raw_bytes = patch_path.read_bytes()
    except OSError as error:
        raise OverlayError(
            f"cannot read patch resource {patch_path}: {error}"
        ) from error
    actual_sha256 = sha256_bytes(raw_bytes)
    if actual_sha256 != expected_sha256:
        raise OverlayError(
            f"patch resource fingerprint mismatch: expected {expected_sha256}, "
            f"got {actual_sha256}"
        )
    try:
        return parse_unified_patch(raw_bytes.decode("utf-8"))
    except UnicodeDecodeError as error:
        raise OverlayError(f"patch resource is not UTF-8: {patch_path}") from error


def load_patch_document(patch_set: PatchSet) -> dict[str, tuple[Hunk, ...]]:
    validate_patch_set(patch_set)
    parsed = load_patch_resource(patch_set.patch_path, patch_set.patch_sha256)

    expected_paths = {spec.path for spec in patch_set.files}
    actual_paths = set(parsed)
    if actual_paths != expected_paths:
        missing = sorted(expected_paths - actual_paths)
        extra = sorted(actual_paths - expected_paths)
        raise OverlayError(
            f"patch manifest mismatch; missing={missing or 'none'}, extra={extra or 'none'}"
        )
    return parsed


def load_migration_document(
    file_spec: FileSpec, migration: MigrationSpec
) -> tuple[Hunk, ...]:
    parsed = load_patch_resource(migration.patch_path, migration.patch_sha256)
    if set(parsed) != {file_spec.path}:
        raise OverlayError(
            f"migration patch target mismatch for {file_spec.path}: {sorted(parsed)}"
        )
    return parsed[file_spec.path]


def read_metadata_payload(
    project: Path,
) -> tuple[dict[str, object] | None, str | None]:
    path = project / METADATA_REL_PATH
    if has_symlink_component(project, path):
        return None, f"refusing symlinked overlay metadata: {path}"
    if not os.path.lexists(path):
        return None, None
    if not path.is_file():
        return None, f"overlay metadata is not a regular file: {path}"
    if path.stat().st_nlink != 1:
        return None, f"refusing hard-linked overlay metadata: {path}"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return None, f"cannot parse overlay metadata {path}: {error}"
    if not isinstance(payload, dict):
        return None, f"overlay metadata must be a JSON object: {path}"
    if payload.get("overlay_id") != OVERLAY_ID:
        return None, f"overlay metadata is owned by another tool: {path}"
    return payload, None


def inspect_metadata(
    project: Path, expected: dict[str, object]
) -> tuple[str, str | None]:
    payload, error = read_metadata_payload(project)
    if error:
        return "conflict", error
    if payload is None:
        return "missing", None
    if payload == expected:
        return "verified", None
    return "stale", None


def select_migration(
    file_spec: FileSpec,
    actual_sha256: str,
    source_overlay_version: str | None,
) -> MigrationSpec | None:
    candidates = [
        migration
        for migration in file_spec.migrations
        if migration.source_sha256 == actual_sha256
    ]
    if not candidates:
        return None
    if source_overlay_version is None:
        raise OverlayError(
            f"cannot migrate {file_spec.path} without a recorded source overlay version"
        )
    candidates = [
        migration
        for migration in candidates
        if migration.source_overlay_version == source_overlay_version
    ]
    if not candidates:
        raise OverlayError(
            f"no {source_overlay_version} migration matches {file_spec.path}"
        )
    if len(candidates) != 1:
        versions = sorted(
            {migration.source_overlay_version for migration in candidates}
        )
        raise OverlayError(
            f"cannot determine migration source version for {file_spec.path}; "
            f"candidates={versions or 'none'}"
        )
    return candidates[0]


def expected_metadata(
    patch_set: PatchSet, file_reports: Sequence[dict[str, object]]
) -> dict[str, object]:
    verified_files = [
        {
            "path": report["path"],
            "sha256": (
                report["sha256"]
                if report["status"] == "applied"
                else report["overlay_sha256"]
            ),
        }
        for report in file_reports
        if report["status"] != "missing_optional"
    ]
    return {
        "schema_version": METADATA_SCHEMA_VERSION,
        "overlay_id": OVERLAY_ID,
        "overlay_version": OVERLAY_VERSION,
        "trellis_version": patch_set.trellis_version,
        "verification": {
            "status": "verified",
            "files": verified_files,
        },
    }


def inspect_project(
    project: Path,
    patch_sets: dict[str, PatchSet] | None = None,
) -> dict[str, object]:
    supported = PATCH_SETS if patch_sets is None else patch_sets
    project = find_project_root(project)
    with project_lock(project, fcntl.LOCK_SH):
        return _inspect_project_locked(project, supported)


def _inspect_project_locked(
    project: Path,
    supported: dict[str, PatchSet],
) -> dict[str, object]:
    version = read_trellis_version(project)
    report: dict[str, object] = {
        "overlay_id": OVERLAY_ID,
        "overlay_version": OVERLAY_VERSION,
        "project": str(project),
        "trellis_version": version,
        "files": [],
        "errors": [],
    }
    patch_set = supported.get(version)
    if patch_set is None:
        report["status"] = "unsupported"
        report["errors"] = [
            f"unsupported Trellis version {version}; supported: "
            + (", ".join(sorted(supported)) or "none")
        ]
        report["metadata"] = {"status": "not_checked"}
        return report

    try:
        _ = load_patch_document(patch_set)
    except OverlayError as error:
        report["status"] = "conflict"
        report["errors"] = [str(error)]
        report["metadata"] = {"status": "not_checked"}
        return report

    metadata_payload, _metadata_read_error = read_metadata_payload(project)
    raw_source_overlay_version = (
        metadata_payload.get("overlay_version")
        if metadata_payload is not None
        else None
    )
    source_overlay_version = (
        raw_source_overlay_version
        if isinstance(raw_source_overlay_version, str)
        else None
    )

    file_reports: list[dict[str, object]] = []
    errors: list[str] = []
    active_optional_groups = {
        ".agents"
        for spec in patch_set.files
        if spec.path.startswith(".agents/") and (project / spec.path).exists()
    }
    active_optional_groups.update(
        ".omp"
        for spec in patch_set.files
        if spec.path.startswith(".omp/") and (project / spec.path).exists()
    )
    for spec in patch_set.files:
        target = project / spec.path
        file_report: dict[str, object] = {
            "path": spec.path,
            "required": spec.required,
            "baseline_sha256": spec.baseline_sha256,
            "overlay_sha256": spec.overlay_sha256,
            "compatible_overlay_sha256s": list(spec.compatible_overlay_sha256s),
            "migrations": [
                {
                    "source_overlay_version": migration.source_overlay_version,
                    "source_sha256": migration.source_sha256,
                }
                for migration in spec.migrations
            ],
        }
        if has_symlink_component(project, target):
            file_report["status"] = "conflict"
            file_report["sha256"] = None
            errors.append(f"refusing symlinked target: {spec.path}")
        elif not target.exists():
            file_report["sha256"] = None
            group = spec.path.split("/", maxsplit=1)[0]
            if spec.required or group in active_optional_groups:
                file_report["status"] = "missing_required"
                errors.append(f"missing required overlay target: {spec.path}")
            else:
                file_report["status"] = "missing_optional"
        elif not target.is_file():
            file_report["status"] = "conflict"
            file_report["sha256"] = None
            errors.append(f"target is not a regular file: {spec.path}")
        elif target.stat().st_nlink != 1:
            file_report["status"] = "conflict"
            file_report["sha256"] = None
            errors.append(f"refusing hard-linked target: {spec.path}")
        else:
            actual_sha256 = sha256_file(target)
            file_report["sha256"] = actual_sha256
            if actual_sha256 == spec.overlay_sha256:
                file_report["status"] = "applied"
                file_report["verification_kind"] = "canonical"
            elif actual_sha256 in spec.compatible_overlay_sha256s:
                file_report["status"] = "applied"
                file_report["verification_kind"] = "compatible"
            elif actual_sha256 == spec.baseline_sha256:
                file_report["status"] = "baseline"
            else:
                try:
                    migration = select_migration(
                        spec,
                        actual_sha256,
                        source_overlay_version,
                    )
                    if migration is None:
                        raise OverlayError(
                            f"local modification at {spec.path}; sha256={actual_sha256}"
                        )
                    source = target.read_text(encoding="utf-8")
                    migrated = apply_hunks(
                        source,
                        spec.path,
                        load_migration_document(spec, migration),
                    ).encode("utf-8")
                    if sha256_bytes(migrated) != spec.overlay_sha256:
                        raise OverlayError(
                            f"migration target fingerprint mismatch for {spec.path}"
                        )
                    file_report["status"] = "migration"
                    file_report["migration"] = {
                        "source_overlay_version": migration.source_overlay_version,
                        "source_sha256": migration.source_sha256,
                    }
                except (OSError, UnicodeDecodeError, OverlayError) as error:
                    file_report["status"] = "conflict"
                    errors.append(str(error))
        file_reports.append(file_report)

    metadata_expected = expected_metadata(patch_set, file_reports)
    metadata_status, metadata_error = inspect_metadata(project, metadata_expected)
    if metadata_error:
        errors.append(metadata_error)
    report["files"] = file_reports
    report["metadata"] = {
        "path": METADATA_REL_PATH.as_posix(),
        "status": metadata_status,
    }
    report["errors"] = errors

    if errors:
        report["status"] = "conflict"
    elif any(item["status"] in {"baseline", "migration"} for item in file_reports):
        report["status"] = "needs_apply"
    elif metadata_status != "verified":
        report["status"] = "needs_apply"
    else:
        report["status"] = "applied"
    return report


def read_file_state(path: Path) -> FileState | None:
    flags = os.O_RDONLY
    flags |= getattr(os, "O_NOFOLLOW", 0)
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NONBLOCK", 0)
    try:
        descriptor = os.open(path, flags)
    except FileNotFoundError:
        return None
    except OSError as error:
        raise OverlayError(f"cannot safely open {path}: {error}") from error

    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise OverlayError(f"refusing non-regular or linked file: {path}")
        with os.fdopen(descriptor, "rb", closefd=False) as file_handle:
            data = file_handle.read()
        after = os.fstat(descriptor)
        entry = os.stat(path, follow_symlinks=False)
        if (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
        ) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        ) or (entry.st_dev, entry.st_ino) != (after.st_dev, after.st_ino):
            raise OverlayError(f"file changed while reading: {path}")
        return FileState(
            data=data,
            mode=stat.S_IMODE(after.st_mode),
            device=after.st_dev,
            inode=after.st_ino,
        )
    except OSError as error:
        raise OverlayError(f"cannot safely read {path}: {error}") from error
    finally:
        os.close(descriptor)


def atomic_write(path: Path, data: bytes, mode: int) -> FileState:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            temporary_file.write(data)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
            os.fchmod(temporary_file.fileno(), mode)
            installed_stat = os.fstat(temporary_file.fileno())
        os.replace(temporary_path, path)
        temporary_path = None
        return FileState(
            data=data,
            mode=stat.S_IMODE(installed_stat.st_mode),
            device=installed_stat.st_dev,
            inode=installed_stat.st_ino,
        )
    except OSError as error:
        raise OverlayError(f"cannot atomically write {path}: {error}") from error
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink()
            except FileNotFoundError:
                pass


def atomic_create(path: Path, data: bytes, mode: int) -> FileState:
    """Publish a new file without replacing a concurrently created entry."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            temporary_file.write(data)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
            os.fchmod(temporary_file.fileno(), mode)
            installed_stat = os.fstat(temporary_file.fileno())
        installed = FileState(
            data=data,
            mode=stat.S_IMODE(installed_stat.st_mode),
            device=installed_stat.st_dev,
            inode=installed_stat.st_ino,
        )
        os.link(temporary_path, path)
        try:
            temporary_path.unlink()
        except OSError as error:
            published_temporary_path = temporary_path
            temporary_path = None
            raise PublishedCreateCleanupError(
                path,
                installed,
                published_temporary_path,
                error,
            ) from error
        temporary_path = None
        return installed
    except PublishedCreateCleanupError:
        raise
    except OSError as error:
        raise OverlayError(f"cannot atomically create {path}: {error}") from error
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink()
            except FileNotFoundError:
                pass


def restore_files(written: dict[Path, AppliedWrite]) -> list[str]:
    errors: list[str] = []
    for path, write in reversed(tuple(written.items())):
        try:
            current = read_file_state(path)
            if current is None:
                if write.original is not None:
                    errors.append(
                        f"preserved concurrent removal of {path}; current file is missing"
                    )
                continue
            if current != write.installed:
                errors.append(
                    f"preserved concurrent update to {path}; installed state no longer matches"
                )
                continue
            if write.original is None:
                entry = os.stat(path, follow_symlinks=False)
                if (entry.st_dev, entry.st_ino) != (
                    current.device,
                    current.inode,
                ):
                    errors.append(
                        f"preserved concurrent replacement of {path} before removal"
                    )
                    continue
                path.unlink()
            else:
                atomic_write(path, write.original.data, write.original.mode)
        except (OSError, OverlayError) as error:
            errors.append(f"failed to restore {path}: {error}")
    return errors


def apply_project(
    project: Path,
    patch_sets: dict[str, PatchSet] | None = None,
) -> dict[str, object]:
    supported = PATCH_SETS if patch_sets is None else patch_sets
    project = find_project_root(project)
    with project_lock(project, fcntl.LOCK_EX):
        return _apply_project_locked(project, supported)


def _apply_project_locked(
    project: Path,
    supported: dict[str, PatchSet],
) -> dict[str, object]:
    before = _inspect_project_locked(project, supported)
    status = before["status"]
    if status in {"unsupported", "conflict"}:
        errors = before.get("errors")
        error_messages = (
            [str(item) for item in errors] if isinstance(errors, list) else []
        )
        raise OverlayError("; ".join(error_messages))

    version = str(before["trellis_version"])
    patch_set = supported[version]
    patch_document = load_patch_document(patch_set)
    raw_file_reports = before["files"]
    if not isinstance(raw_file_reports, list):
        raise OverlayError("internal error: malformed inspection report")
    file_reports = cast(list[dict[str, object]], raw_file_reports)

    specs_by_path = {spec.path: spec for spec in patch_set.files}
    updates: dict[Path, bytes] = {}
    originals: dict[Path, FileState | None] = {}
    for item in file_reports:
        if not isinstance(item, dict) or item.get("status") not in {
            "baseline",
            "migration",
        }:
            continue
        relative_path = str(item["path"])
        target = project / relative_path
        original = read_file_state(target)
        if original is None:
            raise OverlayError(f"target changed during apply: {target}")
        actual_sha256 = sha256_bytes(original.data)
        if actual_sha256 != item.get("sha256"):
            raise OverlayError(f"target changed during apply: {target}")
        try:
            source = original.data.decode("utf-8")
        except UnicodeDecodeError as error:
            raise OverlayError(f"target is not UTF-8: {relative_path}") from error
        if item["status"] == "baseline":
            hunks = patch_document[relative_path]
        else:
            file_spec = specs_by_path[relative_path]
            migration_info = item.get("migration")
            if not isinstance(migration_info, dict):
                raise OverlayError(f"missing migration plan for {relative_path}")
            source_version = migration_info.get("source_overlay_version")
            migration = select_migration(
                file_spec,
                actual_sha256,
                source_version if isinstance(source_version, str) else None,
            )
            if migration is None:
                raise OverlayError(f"missing migration resource for {relative_path}")
            hunks = load_migration_document(file_spec, migration)
        patched = apply_hunks(source, relative_path, hunks)
        patched_data = patched.encode("utf-8")
        expected_sha256 = str(item["overlay_sha256"])
        if sha256_bytes(patched_data) != expected_sha256:
            raise OverlayError(
                f"patched fingerprint mismatch for {relative_path}; patch set is invalid"
            )
        updates[target] = patched_data
        originals[target] = original

    metadata_expected = expected_metadata(patch_set, file_reports)
    metadata_data = (
        json.dumps(metadata_expected, indent=2, sort_keys=True, ensure_ascii=False)
        + "\n"
    ).encode("utf-8")
    metadata_path = project / METADATA_REL_PATH
    originals[metadata_path] = read_file_state(metadata_path)

    if not updates and before["metadata"] == {
        "path": METADATA_REL_PATH.as_posix(),
        "status": "verified",
    }:
        return before

    written: dict[Path, AppliedWrite] = {}
    try:
        for target, patched_data in updates.items():
            original = originals[target]
            if original is None or read_file_state(target) != original:
                raise OverlayError(f"target changed during apply: {target}")
            installed = atomic_write(target, patched_data, original.mode)
            written[target] = AppliedWrite(original, installed)

        metadata_original = originals[metadata_path]
        if read_file_state(metadata_path) != metadata_original:
            raise OverlayError(f"metadata changed during apply: {metadata_path}")
        if metadata_original is None:
            try:
                metadata_installed = atomic_create(metadata_path, metadata_data, 0o644)
            except PublishedCreateCleanupError as error:
                written[metadata_path] = AppliedWrite(None, error.installed)
                cleanup_detail = ""
                try:
                    error.temporary_path.unlink()
                except FileNotFoundError:
                    pass
                except OSError as cleanup_error:
                    cleanup_detail = f"; temporary cleanup also failed: {cleanup_error}"
                raise OverlayError(
                    f"metadata publication cleanup failed: {metadata_path}"
                    f"{cleanup_detail}"
                ) from error
            except OverlayError as error:
                raise OverlayError(
                    f"metadata changed during apply: {metadata_path}"
                ) from error
        else:
            metadata_installed = atomic_write(metadata_path, metadata_data, 0o644)
        written[metadata_path] = AppliedWrite(
            metadata_original,
            metadata_installed,
        )

        after = _inspect_project_locked(project, supported)
        if after["status"] != "applied":
            errors = after.get("errors")
            error_messages = (
                [str(item) for item in errors] if isinstance(errors, list) else []
            )
            raise OverlayError(
                "post-apply verification failed: " + "; ".join(error_messages)
            )
        return after
    except (OSError, OverlayError) as error:
        rollback_errors = restore_files(written)
        if rollback_errors:
            detail = f"apply failed; rollback incomplete: {error}; " + "; ".join(
                rollback_errors
            )
        else:
            detail = f"apply failed and changes were rolled back: {error}"
        raise OverlayError(detail) from error


def apply_projects(
    projects: Iterable[Path],
    patch_sets: dict[str, PatchSet] | None = None,
) -> list[dict[str, object]]:
    """Preflight and apply several projects while retaining every project lock."""
    supported = PATCH_SETS if patch_sets is None else patch_sets
    canonical_projects = sorted(
        {find_project_root(project) for project in projects},
        key=str,
    )
    with ExitStack() as stack:
        for project in canonical_projects:
            stack.enter_context(project_lock(project, fcntl.LOCK_EX))
        reports = [
            _inspect_project_locked(project, supported)
            for project in canonical_projects
        ]
        if any(report["status"] in {"unsupported", "conflict"} for report in reports):
            return reports
        return [
            _apply_project_locked(project, supported) for project in canonical_projects
        ]


def discover_projects(roots: Iterable[Path]) -> list[Path]:
    projects: set[Path] = set()
    for raw_root in roots:
        root = raw_root.expanduser()
        if not root.exists():
            raise OverlayError(f"scan root does not exist: {root}")
        if root.is_file():
            raise OverlayError(f"scan root is not a directory: {root}")
        root = root.resolve()
        if (root / ".trellis/.version").is_file():
            projects.add(root)

        for current, directory_names, _ in os.walk(root, followlinks=False):
            directory_names[:] = [
                name
                for name in directory_names
                if name not in PRUNED_SCAN_DIRS
                and not (Path(current) / name).is_symlink()
            ]
            if ".trellis" not in directory_names:
                continue
            project = Path(current).resolve()
            if (project / ".trellis/.version").is_file():
                projects.add(project)
            directory_names.remove(".trellis")
    return sorted(projects, key=str)


def status_exit_code(reports: Sequence[dict[str, object]]) -> int:
    statuses = {str(report.get("status")) for report in reports}
    if statuses & {"unsupported", "conflict", "error"}:
        return 1
    if "needs_apply" in statuses:
        return 2
    return 0


def print_human(reports: Sequence[dict[str, object]]) -> None:
    for report in reports:
        project = report.get("project", "unknown")
        status = report.get("status", "error")
        version = report.get("trellis_version", "unknown")
        print(f"[{status}] {project} (Trellis {version})")
        errors = report.get("errors", [])
        if isinstance(errors, list):
            for error in errors:
                print(f"  - {error}")
        files = report.get("files", [])
        if isinstance(files, list):
            for item in files:
                if not isinstance(item, dict):
                    continue
                file_status = item.get("status")
                if file_status in {"conflict", "missing_required"}:
                    print(f"  - {item.get('path')}: {file_status}")


def print_reports(reports: Sequence[dict[str, object]], as_json: bool) -> None:
    if as_json:
        payload: object = reports[0] if len(reports) == 1 else {"projects": reports}
        print(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False))
    else:
        print_human(reports)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Audit or apply the Trellis task-reuse overlay."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    for command in ("check", "apply"):
        subparser = subparsers.add_parser(command)
        subparser.add_argument("--project", type=Path, required=True)
        subparser.add_argument("--json", action="store_true")

    scan_parser = subparsers.add_parser("scan")
    scan_parser.add_argument("--root", type=Path, action="append", required=True)
    scan_parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply after every discovered project passes preflight.",
    )
    scan_parser.add_argument("--json", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "check":
            reports = [inspect_project(args.project)]
        elif args.command == "apply":
            reports = [apply_project(args.project)]
        else:
            projects = discover_projects(args.root)
            if not projects:
                raise OverlayError(
                    "no Trellis projects found under the requested roots"
                )
            reports = [inspect_project(project) for project in projects]
            if args.apply:
                reports = apply_projects(projects)
        print_reports(reports, args.json)
        return status_exit_code(reports)
    except OverlayError as error:
        report: dict[str, object] = {
            "overlay_id": OVERLAY_ID,
            "overlay_version": OVERLAY_VERSION,
            "status": "error",
            "errors": [str(error)],
        }
        print_reports([report], getattr(args, "json", False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
