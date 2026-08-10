#!/usr/bin/env python3
"""Audit and apply the versioned Trellis Lite workflow overlay."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import stat
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Sequence

OVERLAY_ID = "trellis-lite"
OVERLAY_VERSION = "1.0.11"
METADATA_REL_PATH = Path(".trellis/.overlays/trellis-lite.json")
SKILL_ROOT = Path(__file__).resolve().parents[1]
RESOURCE_ROOT_067 = SKILL_ROOT / "resources" / "trellis-0.6.7"
RESOURCE_ROOT_0614 = SKILL_ROOT / "resources" / "trellis-0.6.14"


class LiteError(RuntimeError):
    """The overlay cannot proceed without risking local project state."""


class UnsupportedVersionError(LiteError):
    """The project uses a Trellis version with no audited Lite patch set."""


@dataclass(frozen=True)
class ReplacementSpec:
    old: bytes
    new: bytes
    expected_count: int = 1


@dataclass(frozen=True)
class FileSpec:
    path: str
    baseline_sha256: str
    overlay_sha256: str
    required: bool = False
    upgrade_sha256s: tuple[str, ...] = ()
    replacements: tuple[ReplacementSpec, ...] = ()


@dataclass(frozen=True)
class PatchSet:
    trellis_version: str
    resource_root: Path
    files: tuple[FileSpec, ...]


FILE_SPECS_067 = (
    FileSpec(
        ".trellis/workflow.md",
        "6a0918bb68a5af1f6f0aba0efc004584d5819b36e2b84c093ea0dfdf1cc30ce6",
        "9cfb471130185643cc4b39849e8388bb560aaf7fdbffe4f35e1bec39e70cf0de",
        required=True,
        upgrade_sha256s=(
            "a9e2947a60ceab3acfd2d8c711323e72dbceaea9374e120a5dae1f98e254c54d",
            "e4b42a0232b2a70a67934dc51a7b66d7dc9cd4b920b2af14f19c052a4f8b06de",
        ),
    ),
    FileSpec(
        ".omp/extensions/trellis/index.ts",
        "10cb806e89ba7d0c1bdb0c56168ca5999a07d0ed05e45fb9282ad680f7c4ef4a",
        "1d49ce00a64bc1d5a4aeddfac2c0c9607b1ca530cef4d5134365d5dee9e510bb",
        upgrade_sha256s=(
            "7357b764398f648b44607c42b6033425aaad2b1d755a8df34586c6bb090a2a0c",
            "7009c8f32d4d8c38cc02fa7ec402a2f29c3d4722c147c5ad6121426c82a9c875",
            "62520c25f195678ebd4e8644e249b07595e9d8ce83df50d8f8bb2701944d3035",
            "f03f1d23b299a56ea9e5d88eafa962d252fe3a3eab7459a39bb79be111e11176",
            "d29bb4002d7bb09585fb137e46e2bc4440dc29b95bb9a850bc8158c1314dcf45",
            "9b09cb4fd14ad1ca429efa55547f76dd6837c72c9dd50571ae676b28d4d9e00f",
            "a5a7604b53b5ffdfa6039fe3531b41e2605f60d474a27271b4409aa9bb527e92",
        ),
    ),
    FileSpec(
        ".omp/skills/trellis-brainstorm/SKILL.md",
        "a01199832ee26b9449f02ce87b25cb8f6a7ac3aa7f6e92809a8eb1b638bbedf5",
        "040e9a60859e74b1ad0ff1c35fd6624eaeb3bd5dab3de692f6dbfc0fe41db1e4",
        upgrade_sha256s=(
            "6e7efcaa36fe205be9804ae35346395aea7aa024e9e0d63dec62d6651016cd5f",
        ),
    ),
    FileSpec(
        ".omp/skills/trellis-check/SKILL.md",
        "b21ff04b7680ebacb8c5ecbc48a22d627eb13e2b47fceb78c8ced0b43b60b282",
        "1edb6f13e28f22e4aa48e2d746e2ebe8f03f2d48b7373d8b4f4adc6a88de5a5e",
        upgrade_sha256s=(
            "384bd818238f9e539ee06a1240eedebc3a68b1642a800c2b199bf78307802127",
            "cddd39b6c660f1b44b6dc067153dcd366ee3597fa990f042a5c871d311d58da9",
        ),
    ),
    FileSpec(
        ".omp/agents/trellis-check.md",
        "617ffb65225b72e6023bf9c49328a1b851814c18f453cbb80923f0ef71e7fcd8",
        "efefa07348a5fe0165d6b6a6d861d33f64ba3d2d7a475b51a8e3566dd1922ebe",
        upgrade_sha256s=(
            "dd836976fa40fd8753e0a08e82d2f4fbf99edf0d2e6360b9fe6d8252bfd4e10e",
            "a03e2178e746cefe5b31f19b05d040bdc04f71e68279b38bb7392c45c323ef43",
            "3cd5b1991c4cd9955d27f3277b837d91e713671af10f022865ba906183d0ca69",
            "c2a06697136fc310189d9ffcb550fdc8452b5bdc7ae56976a7d363cdbba8b550",
            "cf85b24b8c38feb12489408f35a9cb8a1821be1cc9f14d690684db99fce9a4fc",
            "73c8b91f3b1487af5a084a4b23af72de526977b17aa8d56214107672116f0bd6",
        ),
    ),
    FileSpec(
        ".omp/commands/trellis-continue.md",
        "97e38675c1004b79ede3d25d2950cf5979637050f31394179bc7b830c648fb8d",
        "03de3c9f30fd23d98e50235ee64443a2acc293317b3b9e065fa08c73c17d5bfc",
        upgrade_sha256s=(
            "81bfd7538530ef0a2fd5c9d151191e800122cd205eb66ce9579d2e93ff20faf9",
        ),
    ),
    FileSpec(
        ".agents/skills/trellis-brainstorm/SKILL.md",
        "ed3a18999b561412741b8437867591773722fbc977f79d3e8199a635474c93ee",
        "040e9a60859e74b1ad0ff1c35fd6624eaeb3bd5dab3de692f6dbfc0fe41db1e4",
        upgrade_sha256s=(
            "6e7efcaa36fe205be9804ae35346395aea7aa024e9e0d63dec62d6651016cd5f",
        ),
    ),
    FileSpec(
        ".agents/skills/trellis-start/SKILL.md",
        "c2cf7022e1c00564bd3c1dd2fe1633d662f51c2ce240d10388da64de219459dc",
        "d23e0fa3970da633986c83e0e2ac244e3cb7331a1bd36a1c57a798e89693e42b",
        upgrade_sha256s=(
            "16ccf3fc6399893e4d51baf3c0bf31fc887c4d06bf6fa86f1a577e25d2f28076",
        ),
    ),
    FileSpec(
        ".agents/skills/trellis-check/SKILL.md",
        "b21ff04b7680ebacb8c5ecbc48a22d627eb13e2b47fceb78c8ced0b43b60b282",
        "1edb6f13e28f22e4aa48e2d746e2ebe8f03f2d48b7373d8b4f4adc6a88de5a5e",
        upgrade_sha256s=(
            "384bd818238f9e539ee06a1240eedebc3a68b1642a800c2b199bf78307802127",
            "cddd39b6c660f1b44b6dc067153dcd366ee3597fa990f042a5c871d311d58da9",
        ),
    ),
    FileSpec(
        ".agents/skills/trellis-continue/SKILL.md",
        "745d3811dad215d6c9055f54a4a5cd699844c6e93f86323cd7461f79ed0bd2dc",
        "482c4b70a7e3ddfe62b46d301046104b4d9719486bd463aa5b242e9212d51292",
        upgrade_sha256s=(
            "eede8d13227f98c81d40978d9258ea5f39b0b862cf6b56191c07851cdd3f28e5",
        ),
    ),
    FileSpec(
        ".codex/agents/trellis-check.toml",
        "372dbd32a68f156727fd9f5d755a184543db96013abfeaffb09974c78fd5b873",
        "0223c54d2fa4cdb62f70a522bc93aa3f9c432376121df8185f1165b2e16c3377",
        upgrade_sha256s=(
            "b4ed6a5da068ee50c534e404fbae5e62339881ef8fb7c46d29e205ddced61bff",
            "d3322d3387bac26e549835d6acc5892518f867cac74a152dfb356c17579c2787",
            "ef47f7d925f9c81e49cc49bd73aba72cd3b6cfbb6998bfbcd775c4c84a65c1f8",
            "b8d6b3cd391e6e61926b83e1e93f5d24c2ed529fc6bb96ee05e9161167d700d9",
        ),
    ),
    FileSpec(
        ".codex/hooks/inject-workflow-state.py",
        "0946e5b5c4c154538c1848c25c7f92a76c8ecc863b9a1c0f4b2e03bee071fcd0",
        "36cf03c1637a98bdb13b8714e8e93bbb3f744eb5c0027e938f28a625667c69dc",
        replacements=(
            ReplacementSpec(
                b"mode = \"inline\"",
                b"mode = \"sub-agent\"",
                expected_count=2,
            ),
            ReplacementSpec(
                b"`inline` when missing or invalid because Codex sub-agents run with\n"
                b"    `fork_turns=\"none\"` isolation and can't inherit the parent session's\n"
                b"    task context.",
                b"`sub-agent` when missing or invalid under Trellis Lite. Isolated workers\n"
                b"    recover context from the active task path and disk artifacts.",
            ),
            ReplacementSpec(
                b"Codex defaults to ``inline`` because sub-agents run with ``fork_turns=\"none\"``\n"
                b"    isolation and can't inherit the parent session's task context. Users can\n"
                b"    opt into ``codex.dispatch_mode: sub-agent`` in ``.trellis/config.yaml``",
                b"Trellis Lite defaults Codex to ``sub-agent``. Users can opt into\n"
                b"    ``codex.dispatch_mode: inline`` in ``.trellis/config.yaml``",
            ),
            ReplacementSpec(
                b"Invalid\n    or missing values fall back to inline.",
                b"Invalid or missing values fall back to sub-agent.",
            ),
        ),
    ),
    FileSpec(
        ".trellis/scripts/common/config.py",
        "f456a3bebdb9ebf873a835c849b0314c8ba46378549af97ccc4d99848b9ec12e",
        "137f6eade3d7195d99cefbad31f42708267f2fbec445bcada0cd387d11c9a79e",
        required=True,
        replacements=(
            ReplacementSpec(
                b"DEFAULT_CODEX_DISPATCH_MODE = \"inline\"",
                b"DEFAULT_CODEX_DISPATCH_MODE = \"sub-agent\"",
            ),
            ReplacementSpec(
                b"Default is ``inline``. ``sub-agent`` is an explicit opt-in because Codex\n"
                b"    sub-agents do not inherit the parent session context.",
                b"Default is ``sub-agent`` under Trellis Lite. Isolated workers recover\n"
                b"    context from the active task path and disk artifacts.",
            ),
        ),
    ),
    FileSpec(
        ".trellis/scripts/common/workflow_phase.py",
        "f2b5fcf0c40cedcf3d7d0ad8023d141fa4095caf0302d73f2a73e1bc04b5692b",
        "360826b9d3079546661fd0a4f585cfab35381503d4229e1874b94c8ea283ca4f",
        required=True,
        replacements=(
            ReplacementSpec(
                b"mode = \"inline\"",
                b"mode = \"sub-agent\"",
            ),
            ReplacementSpec(
                b"return ``\"codex-inline\"`` (default)\n"
                b"    or ``\"codex-sub-agent\"``",
                b"return ``\"codex-sub-agent\"`` (default)\n"
                b"    or ``\"codex-inline\"``",
            ),
            ReplacementSpec(
                b"Default is ``inline`` because Codex sub-agents run with ``fork_turns=\"none\"``\n"
                b"    isolation and can't inherit the parent session's task context \xe2\x80\x94 inline\n"
                b"    keeps the main agent in charge so context isn't lost. Invalid / missing\n"
                b"    values also fall back to inline.",
                b"Trellis Lite defaults to ``sub-agent`` because dispatch prompts name the\n"
                b"    active task and isolated workers recover authoritative context from disk.\n"
                b"    Invalid or missing values also fall back to sub-agent.",
            ),
        ),
    ),
)


FILE_SPECS_0614 = (
    FileSpec(
        ".trellis/workflow.md",
        "d2ea5e032b53bf7931074519b8110b924968a1b184dd7850b62777c4202462d2",
        "9cfb471130185643cc4b39849e8388bb560aaf7fdbffe4f35e1bec39e70cf0de",
        required=True,
        upgrade_sha256s=(
            "e4b42a0232b2a70a67934dc51a7b66d7dc9cd4b920b2af14f19c052a4f8b06de",
        ),
    ),
    FileSpec(
        ".omp/extensions/trellis/index.ts",
        "55caabda2b031fee56b4c628f170d79ce26ea1caf6c5a892038c7a2c3150f95a",
        "288785107d27f30efccc5590b205fb43ebfe95db3e3c1368404d229234df4dd4",
        upgrade_sha256s=(
            "396bda18236deb9e955ea280136be70d492a92cef51791b5b6828ace8f778d6b",
            "1a1f41bb1536148628821ea8286c0a370adb2563d27264f90c5608d9f95f59e1",
            "4b05099b16a243053b96d653a683359399cd04ec3bc6d9e65f71f761b150c4ba",
            "f563f175590b81374a518c54112558f4b4986024e6a5db2382db05847dcafad4",
            "c814c8d09cae79f3cc62328b1c19dd79d80694e622cec2c4227c194fd8ce3ca9",
            "4fbc341bc15ac3e1960abff788a4ab55d6fdb788755673ff8a741bc232ee9395",
        ),
    ),
    FileSpec(
        ".omp/skills/trellis-brainstorm/SKILL.md",
        "4571fc7b9253647f7e31cc0f51251e21b3447a9dcd478a62763b877eecf8f5e4",
        "040e9a60859e74b1ad0ff1c35fd6624eaeb3bd5dab3de692f6dbfc0fe41db1e4",
    ),
    FileSpec(
        ".omp/skills/trellis-check/SKILL.md",
        "b21ff04b7680ebacb8c5ecbc48a22d627eb13e2b47fceb78c8ced0b43b60b282",
        "1edb6f13e28f22e4aa48e2d746e2ebe8f03f2d48b7373d8b4f4adc6a88de5a5e",
        upgrade_sha256s=(
            "cddd39b6c660f1b44b6dc067153dcd366ee3597fa990f042a5c871d311d58da9",
        ),
    ),
    FileSpec(
        ".omp/agents/trellis-check.md",
        "6b9f25cea043374813692d99a216d3793c57a456bc32508c05c17d708c35dbb0",
        "4310d68c07ecdb8cf81602faced44e57907c9a036edd90925c63837482eea635",
        upgrade_sha256s=(
            "011657e453c80450de7c76da4be96c434be36878113c226aff091726949a9dd8",
            "399258f4b91db2b9fcd5a1e5f1b09aba394db1348f13d0bcdd4e52e5d20d0985",
            "e3c0765eeb824a80d9522e268f13867329d121600913c36ba01fccddf187fa4e",
            "1d16269e1fd711cf1d3042e225a725b7f2e263d236652b8f4f5dff0c3a9ae6fb",
            "21ec69b27deabced5472af66a9d463d17f001b4d71af03b4eb4f92b81ac7b946",
        ),
    ),
    FileSpec(
        ".omp/commands/trellis-continue.md",
        "d45eae4635bf37f41f5c2b49e87cd7e7623edebac6f9deb30ce41f6ecf7c9cc8",
        "03de3c9f30fd23d98e50235ee64443a2acc293317b3b9e065fa08c73c17d5bfc",
    ),
    FileSpec(
        ".agents/skills/trellis-brainstorm/SKILL.md",
        "ddb7f9b49966995f606cd212b9c3f891e986d343b9d461c23beb360cda644caf",
        "040e9a60859e74b1ad0ff1c35fd6624eaeb3bd5dab3de692f6dbfc0fe41db1e4",
    ),
    FileSpec(
        ".agents/skills/trellis-start/SKILL.md",
        "c2cf7022e1c00564bd3c1dd2fe1633d662f51c2ce240d10388da64de219459dc",
        "d23e0fa3970da633986c83e0e2ac244e3cb7331a1bd36a1c57a798e89693e42b",
    ),
    FileSpec(
        ".agents/skills/trellis-check/SKILL.md",
        "b21ff04b7680ebacb8c5ecbc48a22d627eb13e2b47fceb78c8ced0b43b60b282",
        "1edb6f13e28f22e4aa48e2d746e2ebe8f03f2d48b7373d8b4f4adc6a88de5a5e",
        upgrade_sha256s=(
            "cddd39b6c660f1b44b6dc067153dcd366ee3597fa990f042a5c871d311d58da9",
        ),
    ),
    FileSpec(
        ".agents/skills/trellis-continue/SKILL.md",
        "745d3811dad215d6c9055f54a4a5cd699844c6e93f86323cd7461f79ed0bd2dc",
        "482c4b70a7e3ddfe62b46d301046104b4d9719486bd463aa5b242e9212d51292",
    ),
    FileSpec(
        ".codex/agents/trellis-check.toml",
        "79070c63fa404fc53061cca5194bf66db839132b67a57b9c8d6a295037ba7308",
        "08847d928889cc63c6510979b10354b1dfe4b310aba141f20ba05d67d9765e6a",
        upgrade_sha256s=(
            "1bbd07802c97ba926df3c3bdbf1f0e010c89fe81e9c6208290e01e9399e4aa30",
            "d94c0719b7853ed54ae1d6b2faaa89f69385a3e4882cb7371389e47ca91d0640",
        ),
    ),
)


PATCH_SETS = {
    "0.6.7": PatchSet("0.6.7", RESOURCE_ROOT_067, FILE_SPECS_067),
    "0.6.14": PatchSet("0.6.14", RESOURCE_ROOT_0614, FILE_SPECS_0614),
}

# Preserve the original module-level names for existing imports and fixtures.
SUPPORTED_TRELLIS_VERSION = "0.6.7"
RESOURCE_ROOT = RESOURCE_ROOT_067
FILE_SPECS = FILE_SPECS_067


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def accepted_input_sha256s(spec: FileSpec) -> tuple[str, ...]:
    return (spec.baseline_sha256, *spec.upgrade_sha256s)


def build_overlay_bytes(
    spec: FileSpec,
    current: bytes,
    resource_root: Path,
) -> bytes:
    if not spec.replacements:
        resource = resource_root / spec.path
        desired = read_regular_file(resource)
        if desired is None:
            raise LiteError(f"missing overlay resource: {resource}")
    else:
        desired = current
        for replacement in spec.replacements:
            actual_count = desired.count(replacement.old)
            if actual_count != replacement.expected_count:
                raise LiteError(
                    f"replacement count mismatch for {spec.path}: "
                    f"expected {replacement.expected_count}, found {actual_count}"
                )
            desired = desired.replace(replacement.old, replacement.new)
    if sha256_bytes(desired) != spec.overlay_sha256:
        raise LiteError(f"overlay content hash mismatch: {spec.path}")
    return desired


def resolve_project(path: Path) -> Path:
    current = path.expanduser().resolve()
    if current.is_file():
        current = current.parent
    while current.parent != current:
        trellis = current / ".trellis"
        if trellis.is_dir():
            if trellis.is_symlink():
                raise LiteError(f"refusing symlinked Trellis directory: {trellis}")
            return current
        current = current.parent
    raise LiteError(f"no .trellis directory found from {path}")


@contextmanager
def project_lock(project: Path, operation: int) -> Iterator[None]:
    trellis = project / ".trellis"
    if has_symlink_component(project, trellis):
        raise LiteError(f"refusing symlinked Trellis directory: {trellis}")
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    descriptor = os.open(trellis, flags)
    try:
        fcntl.flock(descriptor, operation)
        yield
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def read_regular_file(path: Path) -> bytes | None:
    try:
        file_stat = path.lstat()
    except FileNotFoundError:
        return None
    if stat.S_ISLNK(file_stat.st_mode) or not stat.S_ISREG(file_stat.st_mode):
        raise LiteError(f"refusing non-regular file: {path}")
    if file_stat.st_nlink != 1:
        raise LiteError(f"refusing hard-linked file: {path}")
    return path.read_bytes()


def has_symlink_component(project: Path, path: Path) -> bool:
    try:
        relative = path.relative_to(project)
    except ValueError:
        return True
    current = project
    for part in relative.parts:
        current /= part
        try:
            entry = current.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(entry.st_mode):
            return True
    return False


def read_project_file(project: Path, path: Path) -> bytes | None:
    if has_symlink_component(project, path):
        raise LiteError(f"refusing symlinked project path: {path}")
    return read_regular_file(path)


def atomic_write(project: Path, path: Path, data: bytes, mode: int) -> None:
    if has_symlink_component(project, path):
        raise LiteError(f"refusing symlinked project path: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary_path = Path(temporary)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary_path, mode)
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def load_version(project: Path) -> str:
    version_path = project / ".trellis/.version"
    data = read_project_file(project, version_path)
    if data is None:
        raise LiteError(f"missing Trellis version file: {version_path}")
    return data.decode("utf-8").strip()


def expected_metadata(project: Path, patch_set: PatchSet) -> dict[str, object]:
    files: list[dict[str, str]] = []
    for spec in patch_set.files:
        data = read_project_file(project, project / spec.path)
        if data is not None:
            files.append({"path": spec.path, "sha256": sha256_bytes(data)})
    return {
        "overlay_id": OVERLAY_ID,
        "overlay_version": OVERLAY_VERSION,
        "schema_version": 1,
        "trellis_version": patch_set.trellis_version,
        "verification": {"files": files, "status": "verified"},
    }


def _inspect_unlocked(
    project: Path,
    patch_set: PatchSet,
    prerequisite_files: dict[str, str] | None = None,
) -> dict[str, object]:
    version = load_version(project)
    report: dict[str, object] = {
        "project": str(project),
        "overlay_id": OVERLAY_ID,
        "overlay_version": OVERLAY_VERSION,
        "trellis_version": version,
        "files": [],
    }
    if version != patch_set.trellis_version:
        report["status"] = "conflict"
        report["errors"] = [
            f"Trellis version changed during inspection: "
            f"expected {patch_set.trellis_version}, got {version}"
        ]
        return report

    errors: list[str] = []
    needs_apply = False
    file_reports: list[dict[str, str]] = []
    for spec in patch_set.files:
        try:
            data = read_project_file(project, project / spec.path)
        except LiteError as error:
            errors.append(str(error))
            continue
        if data is None:
            if spec.required:
                errors.append(f"missing required file: {spec.path}")
            else:
                file_reports.append({"path": spec.path, "status": "absent"})
            continue
        digest = sha256_bytes(data)
        if digest == spec.overlay_sha256:
            state = "applied"
        elif digest in accepted_input_sha256s(spec):
            state = "needs_apply"
            needs_apply = True
        elif prerequisite_files is not None and prerequisite_files.get(spec.path) == digest:
            state = "needs_apply"
            needs_apply = True
        else:
            state = "conflict"
            errors.append(f"unrecognized local content: {spec.path} ({digest})")
        file_reports.append({"path": spec.path, "sha256": digest, "status": state})
    report["files"] = file_reports

    if errors:
        report["status"] = "conflict"
        report["errors"] = errors
        return report
    if needs_apply:
        report["status"] = "needs_apply"
        return report

    try:
        expected = expected_metadata(project, patch_set)
        metadata_data = read_project_file(project, project / METADATA_REL_PATH)
    except LiteError as error:
        report["status"] = "conflict"
        report["errors"] = [str(error)]
        return report
    if metadata_data is None:
        report["status"] = "needs_apply"
        report["metadata"] = "missing"
        return report
    try:
        actual = json.loads(metadata_data)
    except (UnicodeDecodeError, json.JSONDecodeError):
        report["status"] = "conflict"
        report["errors"] = [f"invalid metadata: {METADATA_REL_PATH}"]
        return report
    if actual != expected:
        report["status"] = "needs_apply"
        report["metadata"] = "stale"
        return report
    report["status"] = "applied"
    report["metadata"] = "verified"
    return report


def inspect_project(
    project: Path,
    specs: Sequence[FileSpec] | None = None,
) -> dict[str, object]:
    root = resolve_project(project)
    with project_lock(root, fcntl.LOCK_SH):
        version = load_version(root)
        if specs is None:
            patch_set = PATCH_SETS.get(version)
            if patch_set is None:
                return {
                    "project": str(root),
                    "overlay_id": OVERLAY_ID,
                    "overlay_version": OVERLAY_VERSION,
                    "trellis_version": version,
                    "status": "unsupported",
                    "files": [],
                    "errors": [f"unsupported Trellis version: {version}"],
                }
        else:
            patch_set = PatchSet(version, RESOURCE_ROOT_067, tuple(specs))

    prerequisite_files: dict[str, str] | None = None
    if specs is None:
        try:
            prerequisite_files = recognized_task_reuse_files(
                inspect_task_reuse(root)
            )
        except UnsupportedVersionError as error:
            return {
                "project": str(root),
                "overlay_id": OVERLAY_ID,
                "overlay_version": OVERLAY_VERSION,
                "trellis_version": version,
                "status": "unsupported",
                "files": [],
                "errors": [str(error)],
            }
        except LiteError as error:
            return {
                "project": str(root),
                "overlay_id": OVERLAY_ID,
                "overlay_version": OVERLAY_VERSION,
                "trellis_version": version,
                "status": "conflict",
                "files": [],
                "errors": [str(error)],
            }

    with project_lock(root, fcntl.LOCK_SH):
        return _inspect_unlocked(root, patch_set, prerequisite_files)


def find_task_reuse_manager() -> Path:
    candidates = (
        SKILL_ROOT.parent / "trellis-task-reuse/scripts/manage_trellis_task_reuse.py",
        Path.home() / ".agents/skills/trellis-task-reuse/scripts/manage_trellis_task_reuse.py",
        Path.home() / ".codex/skills/trellis-task-reuse/scripts/manage_trellis_task_reuse.py",
        Path.home() / ".pi/agent/skills/trellis-task-reuse/scripts/manage_trellis_task_reuse.py",
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise LiteError("trellis-task-reuse manager is required but was not found")


def _task_reuse_command(project: Path, command: str) -> dict[str, object]:
    manager = find_task_reuse_manager()
    result = subprocess.run(
        [sys.executable, str(manager), command, "--project", str(project), "--json"],
        check=False,
        capture_output=True,
        text=True,
    )
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        detail = result.stderr.strip() or result.stdout.strip() or "unknown error"
        raise LiteError(
            f"task-reuse {command} returned invalid JSON: {detail}"
        ) from error
    if not isinstance(payload, dict):
        raise LiteError(f"task-reuse {command} returned a non-object report")
    report = {str(key): value for key, value in payload.items()}
    if command == "apply" and result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "unknown error"
        raise LiteError(f"task-reuse prerequisite failed: {detail}")
    if command == "check" and result.returncode not in {0, 1, 2}:
        detail = result.stderr.strip() or result.stdout.strip() or "unknown error"
        raise LiteError(f"task-reuse preflight failed: {detail}")
    return report


def inspect_task_reuse(project: Path) -> dict[str, object]:
    return _task_reuse_command(project, "check")


def apply_task_reuse(project: Path) -> dict[str, object]:
    return _task_reuse_command(project, "apply")


def report_errors(report: dict[str, object], fallback: str) -> list[str]:
    raw_errors = report.get("errors")
    if isinstance(raw_errors, list):
        return [str(error) for error in raw_errors]
    return [fallback]


def recognized_task_reuse_files(report: dict[str, object]) -> dict[str, str]:
    status = report.get("status")
    if status == "unsupported":
        raise UnsupportedVersionError(
            "; ".join(report_errors(report, "unsupported task-reuse prerequisite"))
        )
    if status not in {"applied", "needs_apply"}:
        raise LiteError(
            "task-reuse preflight failed: "
            + "; ".join(report_errors(report, f"status={status}"))
        )

    recognized: dict[str, str] = {}
    raw_files = report.get("files")
    if not isinstance(raw_files, list):
        raise LiteError("task-reuse preflight returned no file manifest")
    for item in raw_files:
        if not isinstance(item, dict):
            continue
        if item.get("status") not in {"applied", "baseline", "migration"}:
            continue
        path = item.get("path")
        digest = item.get("sha256")
        if isinstance(path, str) and isinstance(digest, str):
            recognized[path] = digest
    return recognized


def apply_project(
    project: Path,
    specs: Sequence[FileSpec] | None = None,
    resource_root: Path | None = None,
    *,
    run_prerequisite: bool = True,
) -> dict[str, object]:
    root = resolve_project(project)
    with project_lock(root, fcntl.LOCK_SH):
        version = load_version(root)
        if specs is None:
            patch_set = PATCH_SETS.get(version)
            if patch_set is None:
                raise UnsupportedVersionError(
                    f"unsupported Trellis version: {version}"
                )
        else:
            patch_set = PatchSet(
                version,
                resource_root or RESOURCE_ROOT_067,
                tuple(specs),
            )

    prerequisite_files: dict[str, str] | None = None
    if run_prerequisite:
        prerequisite_files = recognized_task_reuse_files(
            inspect_task_reuse(root)
        )

    with project_lock(root, fcntl.LOCK_SH):
        before = _inspect_unlocked(root, patch_set, prerequisite_files)
        if before["status"] == "conflict":
            raise LiteError(
                "; ".join(report_errors(before, "project is conflicted"))
            )

    if run_prerequisite:
        apply_task_reuse(root)

    with project_lock(root, fcntl.LOCK_EX):
        if load_version(root) != patch_set.trellis_version:
            raise LiteError("Trellis version changed during prerequisite application")
        before = _inspect_unlocked(root, patch_set)
        if before["status"] == "conflict":
            raise LiteError(
                "; ".join(
                    report_errors(
                        before,
                        "project changed after task-reuse prerequisite",
                    )
                )
            )

        originals: dict[Path, tuple[bytes | None, int]] = {}
        installed: dict[Path, bytes] = {}
        updates: list[tuple[Path, bytes, int]] = []
        for spec in patch_set.files:
            target = root / spec.path
            current = read_project_file(root, target)
            if current is None:
                continue
            current_digest = sha256_bytes(current)
            if current_digest == spec.overlay_sha256:
                continue
            if current_digest not in accepted_input_sha256s(spec):
                raise LiteError(f"file changed during preflight: {target}")
            desired = build_overlay_bytes(spec, current, patch_set.resource_root)
            mode = stat.S_IMODE(target.stat().st_mode)
            originals[target] = (current, mode)
            updates.append((target, desired, mode))

        metadata_path = root / METADATA_REL_PATH
        metadata_original = read_project_file(root, metadata_path)
        metadata_mode = (
            stat.S_IMODE(metadata_path.stat().st_mode)
            if metadata_original is not None
            else 0o644
        )
        originals[metadata_path] = (metadata_original, metadata_mode)

        try:
            for target, desired, mode in updates:
                atomic_write(root, target, desired, mode)
                installed[target] = desired

            metadata = expected_metadata(root, patch_set)
            metadata_bytes = (
                json.dumps(metadata, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
            ).encode("utf-8")
            if metadata_original != metadata_bytes:
                atomic_write(root, metadata_path, metadata_bytes, metadata_mode)
                installed[metadata_path] = metadata_bytes
        except Exception as error:
            rollback_errors: list[str] = []
            for path, desired in reversed(installed.items()):
                try:
                    current = read_project_file(root, path)
                    if current != desired:
                        rollback_errors.append(f"changed concurrently: {path}")
                        continue
                    original, mode = originals[path]
                    if original is None:
                        path.unlink(missing_ok=True)
                    else:
                        atomic_write(root, path, original, mode)
                except Exception as rollback_error:  # pragma: no cover - defensive
                    rollback_errors.append(f"{path}: {rollback_error}")
            suffix = (
                f"; rollback incomplete: {', '.join(rollback_errors)}"
                if rollback_errors
                else ""
            )
            raise LiteError(f"apply failed: {error}{suffix}") from error

        report = _inspect_unlocked(root, patch_set)
        if report["status"] != "applied":
            raise LiteError(f"post-apply verification failed: {report}")

    if run_prerequisite:
        apply_task_reuse(root)
        prerequisite_report = inspect_task_reuse(root)
        if prerequisite_report.get("status") != "applied":
            raise LiteError(
                "task-reuse metadata did not converge: "
                + "; ".join(
                    report_errors(
                        prerequisite_report,
                        f"status={prerequisite_report.get('status')}",
                    )
                )
            )

    with project_lock(root, fcntl.LOCK_SH):
        report = _inspect_unlocked(root, patch_set)
    if report["status"] != "applied":
        raise LiteError(f"final Lite verification failed: {report}")
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("check", "apply"):
        child = subparsers.add_parser(command)
        child.add_argument("--project", type=Path, required=True)
        child.add_argument("--json", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "apply":
            report = apply_project(args.project)
        else:
            report = inspect_project(args.project)
    except UnsupportedVersionError as error:
        report = {
            "overlay_id": OVERLAY_ID,
            "overlay_version": OVERLAY_VERSION,
            "status": "unsupported",
            "errors": [str(error)],
        }
    except LiteError as error:
        report = {
            "overlay_id": OVERLAY_ID,
            "overlay_version": OVERLAY_VERSION,
            "status": "conflict",
            "errors": [str(error)],
        }

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False))
    else:
        print(f"Trellis Lite: {report['status']}")
        raw_errors = report.get("errors")
        if isinstance(raw_errors, list):
            for error in raw_errors:
                print(f"- {error}", file=sys.stderr)
    if report["status"] == "applied":
        return 0
    if report["status"] == "needs_apply":
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
