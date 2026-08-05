#!/usr/bin/env python3
"""Manage the canonical Personal xbar installation."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol, cast

SKILL_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = SKILL_ROOT / "plugin" / "personal-xbar.15s.py"
DEFAULT_VERIFIER = SKILL_ROOT / "scripts" / "verify_personal_xbar.py"
DEFAULT_TARGET = (
    Path.home()
    / "Library"
    / "Application Support"
    / "xbar"
    / "plugins"
    / "personal-xbar.15s.py"
)
LEGACY_TARGET = DEFAULT_TARGET.with_name("mcp-monitor.15s.py")
DEFAULT_CACHE_ROOT = Path.home() / "Library" / "Caches" / "skillctl" / "personal-xbar"
LEGACY_CACHE_ROOT = DEFAULT_CACHE_ROOT.with_name("agent-process-monitor")
DEFAULT_STATE_ROOT = (
    Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
    / "skillctl"
    / "personal-xbar"
)
METADATA_FILE = "install.json"
BACKUP_DIRECTORY = "backups"
METADATA_SCHEMA_VERSION = 1

VerifyPlugin = Callable[[Path], str]


class MonitorManagerError(RuntimeError):
    """A safe lifecycle operation could not be completed."""


class ParsedArgs(Protocol):
    source: Path
    target: Path
    state_root: Path
    command: str
    installed: bool
    backup_name: str


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source_file:
        for chunk in iter(lambda: source_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def plugin_version(path: Path) -> str:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise MonitorManagerError(f"cannot read plugin {path}: {error}") from error

    if not lines or lines[0] != "#!/usr/bin/env python3":
        raise MonitorManagerError(f"invalid plugin shebang: {path}")
    valid_titles = {
        "# <xbar.title>Personal xbar</xbar.title>",
        "# <xbar.title>Agent Process Monitor</xbar.title>",
    }
    if not valid_titles.intersection(lines[:12]):
        raise MonitorManagerError(f"missing Personal xbar title: {path}")
    for line in lines[:12]:
        prefix = "# <xbar.version>"
        suffix = "</xbar.version>"
        if line.startswith(prefix) and line.endswith(suffix):
            version = line.removeprefix(prefix).removesuffix(suffix).strip()
            if version:
                return version
    raise MonitorManagerError(f"missing xbar version: {path}")


def plugin_details(path: Path) -> dict[str, object]:
    file_stat = path.stat()
    return {
        "path": str(path),
        "version": plugin_version(path),
        "sha256": sha256_file(path),
        "mode": f"{stat.S_IMODE(file_stat.st_mode):04o}",
    }


def run_bundled_verifier(
    plugin: Path,
    verifier: Path = DEFAULT_VERIFIER,
) -> str:
    try:
        result = subprocess.run(
            [sys.executable, str(verifier), "--plugin", str(plugin)],
            capture_output=True,
            text=True,
            timeout=45,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise MonitorManagerError(f"verifier could not run: {error}") from error
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise MonitorManagerError(
            f"verification failed for {plugin}: {detail or f'exit {result.returncode}'}"
        )
    return result.stdout.strip()


def ensure_production_environment(target: Path) -> None:
    if sys.platform != "darwin":
        raise MonitorManagerError("Personal xbar installation requires macOS")
    if target == DEFAULT_TARGET:
        xbar_present = any(
            candidate.exists()
            for candidate in (
                Path("/Applications/xbar.app"),
                Path.home() / "Applications" / "xbar.app",
            )
        )
        if not xbar_present and not target.parent.is_dir():
            raise MonitorManagerError(
                "xbar is not installed and its plugin directory is absent"
            )


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def backup_directory(state_root: Path) -> Path:
    return state_root / BACKUP_DIRECTORY


def metadata_path(state_root: Path) -> Path:
    return state_root / METADATA_FILE


def atomic_copy(source: Path, target: Path, mode: int) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=target.parent,
            prefix=f".{target.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            with source.open("rb") as source_file:
                shutil.copyfileobj(source_file, temporary_file)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        temporary_path.chmod(mode)
        os.replace(temporary_path, target)
        temporary_path = None
    except OSError as error:
        raise MonitorManagerError(
            f"cannot atomically replace {target}: {error}"
        ) from error
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink()
            except FileNotFoundError:
                pass


def source_package(entrypoint: Path) -> Path | None:
    candidate = entrypoint.parent / "personal_xbar"
    return candidate if candidate.is_dir() else None


def installed_package(entrypoint: Path) -> Path:
    return entrypoint.parent / ".personal-xbar" / "personal_xbar"


def directory_hash(path: Path) -> str:
    digest = hashlib.sha256()
    for child in sorted(path.rglob("*")):
        if not child.is_file() or child.is_symlink() or "__pycache__" in child.parts:
            continue
        digest.update(str(child.relative_to(path)).encode())
        digest.update(b"\0")
        digest.update(child.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def atomic_copy_tree(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    staging_root = Path(tempfile.mkdtemp(prefix=f".{target.name}.", dir=target.parent))
    staged = staging_root / target.name
    displaced = staging_root / "previous"
    try:
        _ = shutil.copytree(source, staged)
        if target.exists():
            if target.is_symlink() or not target.is_dir():
                raise MonitorManagerError(f"invalid Personal xbar package target: {target}")
            os.replace(target, displaced)
        os.replace(staged, target)
    except OSError as error:
        if displaced.exists() and not target.exists():
            os.replace(displaced, target)
        raise MonitorManagerError(f"cannot replace Personal xbar package: {error}") from error
    finally:
        shutil.rmtree(staging_root, ignore_errors=True)


def remove_installed_package(entrypoint: Path) -> None:
    package = installed_package(entrypoint)
    if package.is_dir() and not package.is_symlink():
        shutil.rmtree(package)


def retire_legacy_target(state_root: Path) -> str | None:
    if not LEGACY_TARGET.is_file():
        return None
    backup = create_backup(LEGACY_TARGET, state_root, "legacy-migration")
    LEGACY_TARGET.unlink()
    return backup.name


def migrate_legacy_cache() -> list[str]:
    migrated: list[str] = []
    for name in ("ai-input-status.json", "spotify-web.json"):
        source = LEGACY_CACHE_ROOT / name
        target = DEFAULT_CACHE_ROOT / name
        if source.is_file() and not source.is_symlink() and not target.exists():
            atomic_copy(source, target, 0o600)
            migrated.append(name)
    return migrated


def atomic_write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    encoded = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode()
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            _ = temporary_file.write(encoded)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        temporary_path.chmod(0o600)
        os.replace(temporary_path, path)
        temporary_path = None
    except OSError as error:
        raise MonitorManagerError(f"cannot write metadata {path}: {error}") from error
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink()
            except FileNotFoundError:
                pass


def write_install_metadata(source: Path, target: Path, state_root: Path) -> None:
    details = plugin_details(target)
    package = installed_package(target)
    atomic_write_json(
        metadata_path(state_root),
        {
            "schema_version": METADATA_SCHEMA_VERSION,
            "installed_at": datetime.now(timezone.utc).isoformat(),
            "source": str(source),
            "target": str(target),
            "version": details["version"],
            "sha256": details["sha256"],
            "package_sha256": directory_hash(package) if package.is_dir() else None,
        },
    )


def create_backup(target: Path, state_root: Path, reason: str) -> Path:
    details = plugin_details(target)
    destination_directory = backup_directory(state_root)
    destination_directory.mkdir(parents=True, exist_ok=True)
    destination_directory.chmod(0o700)
    safe_reason = "".join(
        character if character.isalnum() or character in {"-", "_"} else "-"
        for character in reason
    )
    backup_name = (
        f"{utc_timestamp()}-{safe_reason}-v{details['version']}-"
        f"{str(details['sha256'])[:12]}.py"
    )
    destination = destination_directory / backup_name
    atomic_copy(target, destination, 0o755)
    package = installed_package(target)
    if package.is_dir() and not package.is_symlink():
        _ = shutil.copytree(package, destination.with_suffix(".bundle"))
    return destination


def latest_backup(state_root: Path) -> str | None:
    backups = list_backups(state_root)
    if not backups:
        return None
    name = backups[0].get("name")
    return name if isinstance(name, str) else None


def read_metadata(state_root: Path) -> dict[str, object] | None:
    path = metadata_path(state_root)
    if not path.is_file():
        return None
    try:
        raw = cast(object, json.loads(path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError):
        return None
    return cast(dict[str, object], raw) if isinstance(raw, dict) else None


def status(source: Path, target: Path, state_root: Path) -> dict[str, object]:
    result: dict[str, object] = {
        "source": str(source),
        "target": str(target),
        "state_root": str(state_root),
        "latest_backup": latest_backup(state_root),
        "metadata": read_metadata(state_root),
    }
    try:
        source_details = plugin_details(source)
    except (OSError, MonitorManagerError) as error:
        result.update({"status": "invalid", "error": str(error)})
        return result
    result["source_details"] = source_details

    if not target.exists():
        result["status"] = "not-installed"
        return result
    try:
        target_details = plugin_details(target)
    except (OSError, MonitorManagerError) as error:
        result.update({"status": "invalid", "error": str(error)})
        return result
    result["target_details"] = target_details
    source_bundle = source_package(source)
    target_bundle = installed_package(target)
    bundle_current = source_bundle is None or (
        target_bundle.is_dir()
        and directory_hash(source_bundle) == directory_hash(target_bundle)
    )
    result["package_current"] = bundle_current
    result["status"] = "current" if (
        source_details["sha256"] == target_details["sha256"] and bundle_current
    ) else "drifted"
    return result


def list_backups(state_root: Path) -> list[dict[str, object]]:
    directory = backup_directory(state_root)
    if not directory.is_dir():
        return []
    backups: list[dict[str, object]] = []
    for path in sorted(directory.iterdir(), reverse=True):
        if not path.is_file() or path.is_symlink():
            continue
        try:
            details = plugin_details(path)
        except (OSError, MonitorManagerError):
            continue
        backups.append({"name": path.name, **details})
    return backups


def normalized_operation_paths(
    source: Path,
    target: Path,
    state_root: Path,
) -> tuple[Path, Path, Path]:
    normalized_source = source.expanduser().resolve()
    normalized_target = target.expanduser().absolute()
    normalized_state_root = state_root.expanduser().absolute()
    if normalized_target.is_symlink():
        raise MonitorManagerError(
            f"refusing to replace symlinked xbar target: {normalized_target}"
        )
    return normalized_source, normalized_target, normalized_state_root


def install(
    source: Path,
    target: Path,
    state_root: Path,
    *,
    verify_plugin: VerifyPlugin = run_bundled_verifier,
    require_macos: bool = True,
) -> dict[str, object]:
    source, target, state_root = normalized_operation_paths(source, target, state_root)
    if source == target:
        raise MonitorManagerError("canonical source and installed target must differ")
    if require_macos:
        ensure_production_environment(target)

    source_details = plugin_details(source)
    verification = verify_plugin(source)
    canonical_package = source_package(source)
    target_package = installed_package(target)
    package_current = canonical_package is None or (
        target_package.is_dir()
        and directory_hash(canonical_package) == directory_hash(target_package)
    )
    if (
        target.is_file()
        and sha256_file(target) == source_details["sha256"]
        and package_current
    ):
        target.chmod(0o755)
        write_install_metadata(source, target, state_root)
        migrated_state = migrate_legacy_cache() if target == DEFAULT_TARGET else []
        return {
            "action": "noop",
            "backup": None,
            "legacy_backup": (
                retire_legacy_target(state_root) if target == DEFAULT_TARGET else None
            ),
            "migrated_state": migrated_state,
            "verification": verification,
            "target": plugin_details(target),
        }

    backup = (
        create_backup(target, state_root, "pre-install") if target.is_file() else None
    )
    try:
        if canonical_package is not None:
            atomic_copy_tree(canonical_package, target_package)
        atomic_copy(source, target, 0o755)
        installed_verification = verify_plugin(target)
        write_install_metadata(source, target, state_root)
    except (OSError, MonitorManagerError) as error:
        if backup is not None and backup.is_file():
            atomic_copy(backup, target, 0o755)
            backup_package = backup.with_suffix(".bundle")
            if backup_package.is_dir():
                atomic_copy_tree(backup_package, target_package)
            else:
                remove_installed_package(target)
            _ = verify_plugin(target)
        elif target.exists():
            target.unlink()
        if backup is None:
            remove_installed_package(target)
        raise MonitorManagerError(f"installation failed: {error}") from error

    migrated_state = migrate_legacy_cache() if target == DEFAULT_TARGET else []
    legacy_backup = retire_legacy_target(state_root) if target == DEFAULT_TARGET else None

    return {
        "action": "installed",
        "backup": backup.name if backup is not None else None,
        "legacy_backup": legacy_backup,
        "migrated_state": migrated_state,
        "verification": installed_verification,
        "target": plugin_details(target),
    }


def contained_backup(state_root: Path, backup_name: str) -> Path:
    if Path(backup_name).name != backup_name or backup_name in {"", ".", ".."}:
        raise MonitorManagerError("rollback requires one manager-owned backup basename")
    directory = backup_directory(state_root).resolve()
    backup_path = directory / backup_name
    if backup_path.is_symlink():
        raise MonitorManagerError(f"unknown manager-owned backup: {backup_name}")
    candidate = backup_path.resolve()
    if candidate.parent != directory or not candidate.is_file():
        raise MonitorManagerError(f"unknown manager-owned backup: {backup_name}")
    return candidate


def rollback(
    source: Path,
    target: Path,
    state_root: Path,
    backup_name: str,
    *,
    verify_plugin: VerifyPlugin = run_bundled_verifier,
    require_macos: bool = True,
) -> dict[str, object]:
    source, target, state_root = normalized_operation_paths(source, target, state_root)
    if require_macos:
        ensure_production_environment(target)
    backup = contained_backup(state_root, backup_name)
    _ = plugin_details(backup)
    _ = verify_plugin(backup)
    current_backup = (
        create_backup(target, state_root, "pre-rollback") if target.is_file() else None
    )
    try:
        atomic_copy(backup, target, 0o755)
        backup_package = backup.with_suffix(".bundle")
        if backup_package.is_dir():
            atomic_copy_tree(backup_package, installed_package(target))
        else:
            remove_installed_package(target)
        verification = verify_plugin(target)
        write_install_metadata(source, target, state_root)
    except (OSError, MonitorManagerError) as error:
        if current_backup is not None and current_backup.is_file():
            atomic_copy(current_backup, target, 0o755)
            current_package = current_backup.with_suffix(".bundle")
            if current_package.is_dir():
                atomic_copy_tree(current_package, installed_package(target))
            else:
                remove_installed_package(target)
            _ = verify_plugin(target)
        elif target.exists():
            target.unlink()
        raise MonitorManagerError(f"rollback failed: {error}") from error
    return {
        "action": "rolled-back",
        "restored": backup.name,
        "backup": current_backup.name if current_backup is not None else None,
        "verification": verification,
        "target": plugin_details(target),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Manage the skillctl-owned Personal xbar plugin bundle."
    )
    _ = parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    _ = parser.add_argument("--target", type=Path, default=DEFAULT_TARGET)
    _ = parser.add_argument("--state-root", type=Path, default=DEFAULT_STATE_ROOT)
    commands = parser.add_subparsers(dest="command", required=True)
    _ = commands.add_parser("status")
    verify_parser = commands.add_parser("verify")
    _ = verify_parser.add_argument("--installed", action="store_true")
    _ = commands.add_parser("install")
    _ = commands.add_parser("list-backups")
    rollback_parser = commands.add_parser("rollback")
    _ = rollback_parser.add_argument("backup_name")
    return parser


def main() -> int:
    args = cast(ParsedArgs, cast(object, build_parser().parse_args()))
    source = args.source
    target = args.target
    state_root = args.state_root
    try:
        if args.command == "status":
            output = status(source, target, state_root)
        elif args.command == "verify":
            plugin = target if args.installed else source
            output = {
                "status": "verified",
                "plugin": plugin_details(plugin),
                "verification": run_bundled_verifier(plugin),
            }
        elif args.command == "install":
            output = install(source, target, state_root)
        elif args.command == "list-backups":
            output = {"backups": list_backups(state_root)}
        elif args.command == "rollback":
            output = rollback(
                source,
                target,
                state_root,
                args.backup_name,
            )
        else:
            raise MonitorManagerError(f"unsupported command: {args.command}")
    except (OSError, MonitorManagerError) as error:
        print(json.dumps({"status": "error", "error": str(error)}, indent=2))
        return 1
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
