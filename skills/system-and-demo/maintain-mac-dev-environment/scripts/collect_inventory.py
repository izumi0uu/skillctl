#!/usr/bin/env python3
# pyright: basic
"""Collect a sanitized, read-only macOS development environment inventory."""

from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import fnmatch
import getpass
import json
import os
import platform
import plistlib
import re
import secrets
import shutil
import socket
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable


SAFE_EXECUTABLES = {
    "aws",
    "bash",
    "brew",
    "cargo",
    "clang",
    "cmake",
    "codex",
    "docker",
    "du",
    "ffmpeg",
    "gh",
    "git",
    "go",
    "java",
    "just",
    "node",
    "npm",
    "pnpm",
    "psql",
    "pyenv",
    "python",
    "python3",
    "rg",
    "rustc",
    "rustup",
    "stripe",
    "sw_vers",
    "tmux",
    "uname",
    "uv",
    "wget",
    "yarn",
    "zsh",
}

VERSION_COMMANDS: dict[str, list[str]] = {
    "aws": ["--version"],
    "bash": ["--version"],
    "cargo": ["--version"],
    "clang": ["--version"],
    "cmake": ["--version"],
    "codex": ["--version"],
    "docker": ["--version"],
    "ffmpeg": ["-version"],
    "gh": ["--version"],
    "git": ["--version"],
    "go": ["version"],
    "java": ["-version"],
    "just": ["--version"],
    "node": ["--version"],
    "npm": ["--version"],
    "pnpm": ["--version"],
    "psql": ["--version"],
    "pyenv": ["--version"],
    "python": ["--version"],
    "python3": ["--version"],
    "rg": ["--version"],
    "rustc": ["--version"],
    "rustup": ["--version"],
    "stripe": ["--version"],
    "tmux": ["-V"],
    "uv": ["--version"],
    "wget": ["--version"],
    "yarn": ["--version"],
    "zsh": ["--version"],
}

READ_ONLY_INVOCATIONS = {
    ("brew", "--version"),
    ("brew", "--prefix"),
    ("brew", "leaves"),
    ("brew", "list", "--cask"),
    ("brew", "list", "--formula"),
    ("brew", "services", "list"),
    ("docker", "context", "show"),
    ("pyenv", "versions", "--bare"),
    ("rustup", "toolchain", "list"),
    ("sw_vers", "-productVersion"),
    ("uv", "python", "list", "--only-installed"),
    *((name, *arguments) for name, arguments in VERSION_COMMANDS.items()),
}

PIN_FILES = {
    ".nvmrc",
    ".node-version",
    ".python-version",
    ".tool-versions",
    "rust-toolchain",
    "rust-toolchain.toml",
}

PRUNED_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "Library",
    "build",
    "dist",
    "node_modules",
    "target",
    "vendor",
}

DEFAULT_POLICY: dict[str, Any] = {
    "schema_version": 1,
    "project_roots": [],
    "preferred_owners": {},
    "postgres_target_major": None,
    "protected_items": [],
    "scan_project_pins": False,
    "include_application_inventory": False,
    "include_disk_usage": False,
    "exclude_paths": [],
}

CREDENTIAL_ASSIGNMENT = re.compile(
    r"(?i)\b(?P<key>[A-Z0-9_]*(?:API_KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL))\s*=\s*"
    r"(?P<value>\"[^\"\r\n]*\"|'[^'\r\n]*'|[^\s]+)"
)
COMMON_TOKEN = re.compile(
    r"\b(?:AKIA[0-9A-Z]{16}|github_pat_[A-Za-z0-9_]{20,}|gh[oprsu]_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9_-]{20,})\b"
)
CREDENTIAL_JSON = re.compile(
    r"(?i)(?P<prefix>[\"']?[A-Z0-9_]*(?:API_KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL)[\"']?\s*:\s*)"
    r"(?P<quote>[\"'])(?P<value>.*?)(?P=quote)"
)
CREDENTIAL_COLON = re.compile(
    r"(?i)\b(?P<key>[A-Z0-9_]*(?:API_KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL))\s*:\s*(?P<value>[^\s,}]+)"
)
BEARER_TOKEN = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{8,}")
DSN_PASSWORD = re.compile(r"([A-Za-z][A-Za-z0-9+.-]*://[^:/@\s]+:)[^@\s/]+(@)")

SYSTEM_EXECUTABLE_DIRS = tuple(
    Path(item)
    for item in (
        "/bin",
        "/Library/Developer/CommandLineTools/usr/bin",
        "/Applications/Xcode.app/Contents/Developer/usr/bin",
        "/sbin",
        "/usr/bin",
        "/usr/sbin",
    )
)
HOMEBREW_LINK_DIRS = tuple(
    Path(item)
    for item in (
        "/opt/homebrew/bin",
        "/opt/homebrew/sbin",
        "/usr/local/bin",
        "/usr/local/sbin",
    )
)
HOMEBREW_CELLAR_ROOTS = tuple(
    Path(item)
    for item in (
        "/opt/homebrew/Cellar",
        "/usr/local/Cellar",
    )
)
HOMEBREW_FORMULA_PATTERNS: dict[str, tuple[str, ...]] = {
    "aws": ("awscli",),
    "bash": ("bash",),
    "cargo": ("rust",),
    "clang": ("llvm",),
    "cmake": ("cmake",),
    "codex": ("codex",),
    "docker": ("docker",),
    "ffmpeg": ("ffmpeg", "ffmpeg@*"),
    "gh": ("gh",),
    "git": ("git",),
    "go": ("go",),
    "java": ("openjdk", "openjdk@*"),
    "just": ("just",),
    "node": ("node", "node@*"),
    "npm": ("node", "node@*"),
    "pnpm": ("pnpm",),
    "psql": ("libpq", "postgresql", "postgresql@*"),
    "pyenv": ("pyenv",),
    "python": ("python", "python@*"),
    "python3": ("python", "python@*"),
    "rg": ("ripgrep",),
    "rustc": ("rust",),
    "rustup": ("rustup",),
    "stripe": ("stripe", "stripe-cli"),
    "tmux": ("tmux",),
    "uv": ("uv",),
    "wget": ("wget",),
    "yarn": ("yarn",),
    "zsh": ("zsh",),
}
HOMEBREW_BREW_PATHS = {
    Path("/opt/homebrew/bin/brew"),
    Path("/usr/local/bin/brew"),
}
ORBSTACK_DOCKER_TARGET = Path("/Applications/OrbStack.app/Contents/MacOS/xbin/docker-tools")
DOCKER_DESKTOP_TARGETS = frozenset(
    {
        Path("/Applications/Docker.app/Contents/Resources/bin/docker"),
        Path("/Applications/Docker.app/Contents/Resources/bin/com.docker.cli"),
    }
)
APP_EXECUTABLE_MAPPINGS: dict[str, dict[Path, frozenset[Path]]] = {
    "docker": {
        Path("/usr/local/bin/docker"): DOCKER_DESKTOP_TARGETS | {ORBSTACK_DOCKER_TARGET},
        Path("/opt/homebrew/bin/docker"): DOCKER_DESKTOP_TARGETS | {ORBSTACK_DOCKER_TARGET},
        Path.home() / ".orbstack" / "bin" / "docker": frozenset({ORBSTACK_DOCKER_TARGET}),
        Path("/Applications/OrbStack.app/Contents/MacOS/xbin/docker"): frozenset({ORBSTACK_DOCKER_TARGET}),
        **{
            target: frozenset({target})
            for target in DOCKER_DESKTOP_TARGETS
        },
    },
}


def xdg_path(env_name: str, fallback: Path) -> Path:
    value = os.environ.get(env_name)
    if not value:
        return fallback
    candidate = Path(value).expanduser()
    return candidate if candidate.is_absolute() else fallback


def default_policy_path() -> Path:
    return xdg_path("XDG_CONFIG_HOME", Path.home() / ".config") / "skillctl" / "maintain-mac-dev-environment.json"


def redact_text(
    value: str,
    home: Path | None = None,
    hostname: str | None = None,
    username: str | None = None,
) -> str:
    redacted = value
    actual_home = str(home or Path.home())
    if actual_home:
        redacted = redacted.replace(actual_home, "$HOME")
    actual_hostname = hostname if hostname is not None else socket.gethostname()
    if actual_hostname:
        redacted = redacted.replace(actual_hostname, "$HOST")
    actual_username = username if username is not None else getpass.getuser()
    if len(actual_username) >= 3:
        redacted = re.sub(
            rf"(?<![A-Za-z0-9_-]){re.escape(actual_username)}(?![A-Za-z0-9_-])",
            "$USER",
            redacted,
        )
    redacted = CREDENTIAL_ASSIGNMENT.sub(lambda match: f"{match.group('key')}=<redacted>", redacted)
    redacted = CREDENTIAL_JSON.sub(lambda match: f"{match.group('prefix')}{match.group('quote')}<redacted>{match.group('quote')}", redacted)
    redacted = CREDENTIAL_COLON.sub(lambda match: f"{match.group('key')}: <redacted>", redacted)
    redacted = BEARER_TOKEN.sub("Bearer <redacted>", redacted)
    redacted = DSN_PASSWORD.sub(r"\1<redacted>\2", redacted)
    return COMMON_TOKEN.sub("<redacted-token>", redacted)


def redact_data(value: object) -> object:
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, list):
        return [redact_data(item) for item in value]
    if isinstance(value, dict):
        return {redact_text(str(key)): redact_data(item) for key, item in value.items()}
    return value


def safe_environment() -> dict[str, str]:
    allowed = ("HOME", "LANG", "LC_ALL", "TMPDIR")
    env = {key: os.environ[key] for key in allowed if key in os.environ}
    env["PATH"] = "/opt/homebrew/bin:/opt/homebrew/sbin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
    env["HOMEBREW_NO_AUTO_UPDATE"] = "1"
    env["HOMEBREW_NO_ANALYTICS"] = "1"
    return env


def path_is_within(path: Path, roots: Iterable[Path]) -> bool:
    return any(path == root or root in path.parents for root in roots)


def executable_names_match(command_name: str, resolved_name: str) -> bool:
    return resolved_name == command_name or resolved_name.startswith(f"{command_name}.") or resolved_name.startswith(
        f"{command_name}-"
    )


def homebrew_formula_for_path(path: Path) -> str | None:
    for root in HOMEBREW_CELLAR_ROOTS:
        try:
            relative = path.relative_to(root)
        except ValueError:
            continue
        return relative.parts[0] if len(relative.parts) >= 3 else None
    return None


def homebrew_formula_matches(command_name: str, path: Path) -> bool:
    formula = homebrew_formula_for_path(path)
    patterns = HOMEBREW_FORMULA_PATTERNS.get(command_name, ())
    return formula is not None and any(fnmatch.fnmatchcase(formula, pattern) for pattern in patterns)


def trusted_executable_path(candidate: Path, resolved: Path, command_name: str) -> bool:
    try:
        metadata = resolved.stat()
    except OSError:
        return False
    if not stat.S_ISREG(metadata.st_mode):
        return False
    if metadata.st_uid not in {0, os.getuid()}:
        return False
    if metadata.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
        return False
    if resolved.parent in SYSTEM_EXECUTABLE_DIRS:
        return executable_names_match(command_name, resolved.name)
    if command_name == "brew" and candidate in HOMEBREW_BREW_PATHS:
        return resolved == candidate and resolved.name == "brew"
    if (
        candidate.parent in HOMEBREW_LINK_DIRS
        and candidate.is_symlink()
        and homebrew_formula_matches(command_name, resolved)
    ):
        return executable_names_match(command_name, resolved.name)
    allowed_targets = APP_EXECUTABLE_MAPPINGS.get(command_name, {}).get(candidate, frozenset())
    return resolved in allowed_targets


def trusted_executable(command: str) -> Path | None:
    discovered = command if Path(command).is_absolute() else shutil.which(command)
    if not discovered:
        return None
    candidate = Path(discovered).expanduser()
    if not candidate.is_absolute() or not candidate.exists():
        return None
    try:
        resolved = candidate.resolve(strict=True)
    except OSError:
        return None
    return resolved if trusted_executable_path(candidate, resolved, Path(command).name) else None


def run_safe(args: list[str], timeout: int = 20) -> dict[str, Any]:
    if not args:
        raise ValueError("command cannot be empty")
    executable_name = Path(args[0]).name
    if executable_name not in SAFE_EXECUTABLES:
        raise ValueError(f"executable is not allowlisted: {executable_name}")
    invocation = (executable_name, *args[1:])
    is_directory_size = executable_name == "du" and len(args) == 3 and args[1] == "-sk"
    if invocation not in READ_ONLY_INVOCATIONS and not is_directory_size:
        raise ValueError(f"command is not an approved read-only invocation: {' '.join(invocation)}")

    discovered = args[0] if Path(args[0]).is_absolute() else shutil.which(args[0])
    if not discovered:
        return {"ok": False, "status": "not-found", "returncode": None, "stdout": ""}
    executable = trusted_executable(args[0])
    if executable is None:
        return {"ok": False, "status": "untrusted-path", "returncode": None, "stdout": ""}

    try:
        completed = subprocess.run(
            [str(executable), *args[1:]],
            check=False,
            capture_output=True,
            env=safe_environment(),
            shell=False,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "status": "timeout", "returncode": None, "stdout": ""}
    except OSError:
        return {"ok": False, "status": "os-error", "returncode": None, "stdout": ""}

    combined = completed.stdout or completed.stderr
    return {
        "ok": completed.returncode == 0,
        "status": "ok" if completed.returncode == 0 else "nonzero-exit",
        "returncode": completed.returncode,
        "stdout": redact_text(combined.strip()),
    }


def first_line(result: dict[str, Any]) -> str | None:
    output = result.get("stdout", "")
    return output.splitlines()[0] if output else None


def directory_size(path: Path) -> int | None:
    if not path.exists():
        return None
    result = run_safe(["/usr/bin/du", "-sk", str(path)], timeout=180)
    if not result["ok"]:
        return None
    first = result["stdout"].split(maxsplit=1)[0]
    return int(first) * 1024 if first.isdigit() else None


def path_has_symlink_component(path: Path) -> bool:
    absolute = Path(os.path.abspath(path))
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        if current.is_symlink():
            return True
    return False


def read_bounded_regular_bytes(path: Path, max_bytes: int) -> bytes | None:
    if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_NONBLOCK"):
        return None
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | getattr(os, "O_CLOEXEC", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError:
        return None
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > max_bytes:
            return None
        chunks: list[bytes] = []
        remaining = max_bytes + 1
        while remaining:
            chunk = os.read(descriptor, remaining)
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        return raw if len(raw) <= max_bytes else None
    finally:
        os.close(descriptor)


def read_bounded_regular_text(path: Path, max_bytes: int, encoding: str = "utf-8") -> str | None:
    raw = read_bounded_regular_bytes(path, max_bytes)
    return raw.decode(encoding, errors="replace") if raw is not None else None


def absolute_policy_path(value: str, field: str) -> Path:
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        raise ValueError(f"{field} entries must be absolute or home-relative paths")
    return candidate


def validated_project_root(value: str) -> Path:
    candidate = absolute_policy_path(value, "project_roots")
    if path_has_symlink_component(candidate):
        raise ValueError("project_roots entries must not contain symlink components")
    resolved = candidate.resolve()
    home = Path.home().resolve()
    if resolved in {Path("/"), home, home.parent}:
        raise ValueError("project_roots entries must be narrower than the filesystem, home, or users directory")
    return resolved


def load_policy(path: Path) -> dict[str, Any]:
    if path_has_symlink_component(path):
        raise ValueError("policy path must not contain symlink components")
    if not path.exists():
        return dict(DEFAULT_POLICY)
    policy_text = read_bounded_regular_text(path, max_bytes=65_536)
    if policy_text is None:
        raise ValueError("policy must be a bounded regular file")
    loaded = json.loads(policy_text)
    if not isinstance(loaded, dict):
        raise ValueError("policy must be a JSON object")
    unknown = set(loaded) - set(DEFAULT_POLICY)
    if unknown:
        raise ValueError(f"unknown policy fields: {', '.join(sorted(unknown))}")
    policy = {**DEFAULT_POLICY, **loaded}
    if not isinstance(policy["schema_version"], int) or isinstance(policy["schema_version"], bool) or policy["schema_version"] != 1:
        raise ValueError("unsupported policy schema_version")
    for field in ("project_roots", "protected_items", "exclude_paths"):
        if not isinstance(policy[field], list) or not all(isinstance(item, str) for item in policy[field]):
            raise ValueError(f"{field} must be an array of strings")
    if not isinstance(policy["preferred_owners"], dict):
        raise ValueError("preferred_owners must be an object")
    if not all(isinstance(key, str) and isinstance(value, str) for key, value in policy["preferred_owners"].items()):
        raise ValueError("preferred_owners keys and values must be strings")
    for field in ("scan_project_pins", "include_application_inventory", "include_disk_usage"):
        if not isinstance(policy[field], bool):
            raise ValueError(f"{field} must be a boolean")
    for project_root in policy["project_roots"]:
        validated_project_root(project_root)
    for excluded_path in policy["exclude_paths"]:
        absolute_policy_path(excluded_path, "exclude_paths")
    target_major = policy["postgres_target_major"]
    if target_major is not None and (not isinstance(target_major, int) or isinstance(target_major, bool)):
        raise ValueError("postgres_target_major must be an integer or null")
    return policy


def executable_occurrences(name: str) -> list[str]:
    found: list[str] = []
    for raw_dir in os.environ.get("PATH", "").split(os.pathsep):
        if not raw_dir:
            continue
        candidate = Path(raw_dir).expanduser() / name
        if candidate.exists() and os.access(candidate, os.X_OK):
            rendered = redact_text(str(candidate))
            if rendered not in found:
                found.append(rendered)
    return found


def collect_system() -> dict[str, Any]:
    product = run_safe(["sw_vers", "-productVersion"])
    shell = os.environ.get("SHELL", "")
    shell_name = Path(shell).name if shell else None
    shell_version = run_safe([shell_name, "--version"]) if shell_name in {"bash", "zsh"} else None
    return {
        "product": "macOS",
        "version": first_line(product),
        "architecture": platform.machine(),
        "shell": redact_text(shell) if shell else None,
        "shell_version": first_line(shell_version) if shell_version else None,
    }


def collect_path_audit() -> dict[str, Any]:
    entries = [Path(item).expanduser() for item in os.environ.get("PATH", "").split(os.pathsep) if item]
    rendered = [redact_text(str(item)) for item in entries]
    duplicate_entries = sorted({item for item in rendered if rendered.count(item) > 1})
    missing_entries = sorted({redact_text(str(item)) for item in entries if not item.is_dir()})
    return {
        "entry_count": len(entries),
        "duplicates": duplicate_entries,
        "missing": missing_entries,
    }


def collect_commands() -> dict[str, Any]:
    commands: dict[str, Any] = {}
    for name, version_args in VERSION_COMMANDS.items():
        occurrences = executable_occurrences(name)
        if not occurrences:
            continue
        version_result = run_safe([name, *version_args])
        commands[name] = {
            "active_path": occurrences[0],
            "all_paths": occurrences,
            "version": first_line(version_result),
            "version_status": version_result["status"],
        }
    return commands


def lines(result: dict[str, Any]) -> list[str]:
    return [line.strip() for line in result.get("stdout", "").splitlines() if line.strip()]


def collect_brew(include_applications: bool) -> dict[str, Any]:
    if not shutil.which("brew"):
        return {"available": False}
    version = run_safe(["brew", "--version"])
    prefix = run_safe(["brew", "--prefix"])
    formulae = run_safe(["brew", "list", "--formula"])
    casks = run_safe(["brew", "list", "--cask"]) if include_applications else None
    leaves = run_safe(["brew", "leaves"])
    services = run_safe(["brew", "services", "list"])

    parsed_services: list[dict[str, str]] = []
    for line in lines(services)[1:]:
        fields = line.split()
        if len(fields) >= 2:
            parsed_services.append({"name": fields[0], "status": fields[1]})

    return {
        "available": True,
        "version": first_line(version),
        "prefix": first_line(prefix),
        "formulae": sorted(lines(formulae)) if formulae["ok"] else [],
        "formulae_status": formulae["status"],
        "casks": sorted(lines(casks)) if casks and casks["ok"] else [],
        "casks_status": casks["status"] if casks else "not-requested",
        "leaves": sorted(lines(leaves)) if leaves["ok"] else [],
        "services": parsed_services,
    }


def child_directory_versions(root: Path) -> list[str]:
    if path_has_symlink_component(root) or not root.is_dir():
        return []
    return sorted(
        item.name
        for item in root.iterdir()
        if item.is_dir() and not item.is_symlink() and not item.name.startswith(".")
    )


def node_packages_in_prefix(prefix: Path) -> list[dict[str, str | None]]:
    modules_root = prefix / "lib" / "node_modules"
    if path_has_symlink_component(modules_root) or not modules_root.is_dir():
        return []
    package_dirs: list[Path] = []
    for item in modules_root.iterdir():
        if item.is_symlink() or not item.is_dir() or item.name.startswith("."):
            continue
        if item.name.startswith("@"):
            package_dirs.extend(child for child in item.iterdir() if child.is_dir() and not child.is_symlink())
        else:
            package_dirs.append(item)

    packages: list[dict[str, str | None]] = []
    for package_dir in package_dirs:
        package_text = read_bounded_regular_text(package_dir / "package.json", max_bytes=1_000_000)
        if package_text is None:
            continue
        try:
            metadata = json.loads(package_text)
        except json.JSONDecodeError:
            continue
        if not isinstance(metadata, dict):
            continue
        name = metadata.get("name")
        version = metadata.get("version")
        if isinstance(name, str):
            packages.append({"name": name, "version": str(version) if version is not None else None})
    return sorted(packages, key=lambda item: item["name"] or "")


def collect_global_node_packages() -> list[dict[str, Any]]:
    sources: list[tuple[str, Path]] = [
        ("homebrew-arm-prefix", Path("/opt/homebrew")),
        ("homebrew-intel-prefix", Path("/usr/local")),
        ("user-prefix", Path.home() / ".local"),
    ]
    nvm_root = Path.home() / ".nvm" / "versions" / "node"
    if not path_has_symlink_component(nvm_root) and nvm_root.is_dir():
        sources.extend(
            (f"nvm:{item.name}", item)
            for item in sorted(nvm_root.iterdir())
            if item.is_dir() and not item.is_symlink()
        )
    return [
        {"source": label, "packages": packages}
        for label, prefix in sources
        if (packages := node_packages_in_prefix(prefix))
    ]


def collect_runtimes() -> dict[str, Any]:
    pyenv = run_safe(["pyenv", "versions", "--bare"]) if shutil.which("pyenv") else None
    rustup = run_safe(["rustup", "toolchain", "list"]) if shutil.which("rustup") else None
    uv_python = run_safe(["uv", "python", "list", "--only-installed"]) if shutil.which("uv") else None
    uv_versions = sorted({line.split()[0] for line in lines(uv_python)}) if uv_python and uv_python["ok"] else []
    return {
        "nvm_node_versions": child_directory_versions(Path.home() / ".nvm" / "versions" / "node"),
        "pyenv_versions": lines(pyenv) if pyenv and pyenv["ok"] else [],
        "rustup_toolchains": lines(rustup) if rustup and rustup["ok"] else [],
        "uv_python_versions": uv_versions,
    }


def collect_runtime_sizes() -> list[dict[str, Any]]:
    paths: list[tuple[str, Path]] = []
    roots = {
        "nvm": Path.home() / ".nvm" / "versions" / "node",
        "pyenv": Path.home() / ".pyenv" / "versions",
        "rustup": Path.home() / ".rustup" / "toolchains",
    }
    for family, root in roots.items():
        if not path_has_symlink_component(root) and root.is_dir():
            paths.extend(
                (f"{family}:{item.name}", item)
                for item in sorted(root.iterdir())
                if item.is_dir() and not item.is_symlink()
            )
    for label, path in (
        ("go:version-manager", Path.home() / ".go"),
        ("go:homebrew-arm", Path("/opt/homebrew/Cellar/go")),
        ("go:homebrew-intel", Path("/usr/local/Cellar/go")),
    ):
        if path.exists():
            paths.append((label, path))

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        sizes = list(executor.map(lambda pair: directory_size(pair[1]), paths))
    return [
        {"name": label, "size_bytes": size}
        for (label, _), size in zip(paths, sizes)
    ]


def application_version(app_path: Path) -> str | None:
    info_path = app_path / "Contents" / "Info.plist"
    if path_has_symlink_component(info_path):
        return None
    raw = read_bounded_regular_bytes(info_path, max_bytes=2_000_000)
    if raw is None:
        return None
    try:
        info = plistlib.loads(raw)
    except (plistlib.InvalidFileException, TypeError, ValueError):
        return None
    if not isinstance(info, dict):
        return None
    value = info.get("CFBundleShortVersionString")
    return str(value) if value is not None else None


def collect_applications(include_sizes: bool) -> list[dict[str, Any]]:
    paths: list[Path] = []
    for root in (Path("/Applications"), Path.home() / "Applications"):
        if not path_has_symlink_component(root) and root.is_dir():
            paths.extend(
                app
                for app in sorted(root.glob("*.app"))
                if app.is_dir() and not app.is_symlink()
            )
    sizes: dict[Path, int | None] = {}
    if include_sizes:
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            sizes = dict(zip(paths, executor.map(directory_size, paths)))
    return [
        {
            "name": app.stem,
            "version": application_version(app),
            "size_bytes": sizes.get(app),
        }
        for app in paths
    ]


def excluded(path: Path, excluded_paths: Iterable[str]) -> bool:
    resolved = path.resolve()
    for item in excluded_paths:
        candidate = absolute_policy_path(item, "exclude_paths").resolve()
        if resolved == candidate or candidate in resolved.parents:
            return True
    return False


def collect_project_pins(policy: dict[str, Any]) -> list[dict[str, str]]:
    if not policy["scan_project_pins"]:
        return []
    findings: list[dict[str, str]] = []
    for index, configured_root in enumerate(policy["project_roots"], start=1):
        root = validated_project_root(configured_root)
        if not root.is_dir() or excluded(root, policy["exclude_paths"]):
            continue
        for current, dirnames, filenames in os.walk(root):
            current_path = Path(current)
            dirnames[:] = [
                name
                for name in dirnames
                if name not in PRUNED_DIRS and not excluded(current_path / name, policy["exclude_paths"])
            ]
            for filename in sorted(PIN_FILES.intersection(filenames)):
                pin_path = current_path / filename
                value = read_bounded_regular_text(pin_path, max_bytes=1000)
                if value is None:
                    continue
                findings.append(
                    {
                        "root": f"root-{index}",
                        "relative_path": str(pin_path.relative_to(root)),
                        "value": redact_text(value.strip()),
                    }
                )
    return findings


def collect_cache_sizes() -> list[dict[str, Any]]:
    paths = {
        "brew": Path.home() / "Library" / "Caches" / "Homebrew",
        "cargo-registry": Path.home() / ".cargo" / "registry",
        "npm": Path.home() / ".npm",
        "pip": Path.home() / "Library" / "Caches" / "pip",
        "pnpm": Path.home() / "Library" / "pnpm",
        "uv": Path.home() / ".cache" / "uv",
    }
    existing = [(name, path) for name, path in paths.items() if path.exists()]
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        sizes = list(executor.map(lambda pair: directory_size(pair[1]), existing))
    return [
        {"name": name, "path": redact_text(str(path)), "size_bytes": size}
        for (name, path), size in zip(existing, sizes)
    ]


def collect_container_state(include_sizes: bool) -> dict[str, Any]:
    current_context = run_safe(["docker", "context", "show"]) if shutil.which("docker") else None
    data_paths: list[tuple[str, Path]] = []
    for label, path in (
        ("docker-desktop-app", Path("/Applications/Docker.app")),
        ("docker-desktop-data", Path.home() / "Library" / "Containers" / "com.docker.docker"),
        ("orbstack-app", Path("/Applications/OrbStack.app")),
    ):
        if path.exists():
            data_paths.append((label, path))
    group_root = Path.home() / "Library" / "Group Containers"
    if group_root.is_dir():
        data_paths.extend(
            ("orbstack-data", item)
            for item in group_root.iterdir()
            if "orbstack" in item.name.lower()
        )

    sizes: dict[Path, int | None] = {}
    if include_sizes:
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            sizes = dict(
                zip(
                    (path for _, path in data_paths),
                    executor.map(lambda pair: directory_size(pair[1]), data_paths),
                )
            )
    return {
        "current_context": first_line(current_context) if current_context else None,
        "data_locations": [
            {"name": label, "size_bytes": sizes.get(path)} for label, path in data_paths
        ],
    }


def collect_postgres(include_sizes: bool) -> list[dict[str, Any]]:
    roots: list[Path] = []
    for var_root in (Path("/opt/homebrew/var"), Path("/usr/local/var")):
        if not var_root.is_dir():
            continue
        roots.extend(var_root.glob("postgresql@*"))
        roots.extend(path for name in ("postgres", "postgresql") if (path := var_root / name).is_dir())
    roots = sorted(set(roots))
    findings: list[dict[str, Any]] = []
    for root in roots:
        version_text = read_bounded_regular_text(root / "PG_VERSION", max_bytes=32, encoding="ascii")
        version = version_text.strip() if version_text is not None else None
        findings.append(
            {
                "cluster": root.name,
                "major_version": version,
                "data_directory_present": root.is_dir(),
                "size_bytes": directory_size(root) if include_sizes else None,
            }
        )
    return findings


def collect_inventory(policy: dict[str, Any], deep: bool = False) -> dict[str, Any]:
    include_sizes = deep or bool(policy["include_disk_usage"])
    inventory: dict[str, Any] = {
        "schema_version": 1,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "privacy": {
            "home_redacted": True,
            "hostname_redacted": True,
            "username_redacted": True,
            "environment_values_collected": False,
            "process_arguments_collected": False,
            "dotenv_files_read": False,
            "database_contents_read": False,
            "git_remotes_read": False,
        },
        "limitations": [
            "No removal is authorized by this inventory.",
            "Reverse dependencies and project-specific compatibility require follow-up checks.",
            "Container contents, database contents, launch agents, login items, and process arguments are not inspected.",
            "Missing values can mean unavailable, untrusted, unsupported, or not requested; inspect status fields before concluding absence.",
            "Read-only arguments reduce accidental mutation risk but cannot make a compromised installed executable trustworthy.",
        ],
        "policy_summary": {
            "preferred_owners": policy["preferred_owners"],
            "postgres_target_major": policy["postgres_target_major"],
            "protected_items": policy["protected_items"],
            "configured_project_root_count": len(policy["project_roots"]),
        },
        "system": collect_system(),
        "path": collect_path_audit(),
        "commands": collect_commands(),
        "homebrew": collect_brew(bool(policy["include_application_inventory"])),
        "runtimes": collect_runtimes(),
        "global_node_packages": collect_global_node_packages(),
        "project_pins": collect_project_pins(policy),
        "postgres_clusters": collect_postgres(include_sizes),
        "containers": collect_container_state(include_sizes),
    }
    if policy["include_application_inventory"]:
        inventory["applications"] = collect_applications(include_sizes)
    if include_sizes:
        inventory["cache_sizes"] = collect_cache_sizes()
        inventory["runtime_sizes"] = collect_runtime_sizes()
    redacted = redact_data(inventory)
    if not isinstance(redacted, dict):
        raise RuntimeError("inventory redaction produced an invalid result")
    return redacted


def validate_output_entry(parent_descriptor: int, name: str) -> None:
    try:
        metadata = os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
    except FileNotFoundError:
        return
    if not stat.S_ISREG(metadata.st_mode):
        raise ValueError("snapshot output must be a regular file")
    if metadata.st_nlink != 1:
        raise ValueError("snapshot output must not be hard-linked")


def write_private_output(path: Path, rendered: str) -> None:
    if not path.is_absolute() or not path.name:
        raise ValueError("snapshot output must be an absolute file path")
    if path_has_symlink_component(path.parent):
        raise ValueError("snapshot output parent must not contain symlink components")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path_has_symlink_component(path.parent):
        raise ValueError("snapshot output parent must not contain symlink components")
    parent = path.parent.resolve(strict=True)
    if not parent.is_dir():
        raise ValueError("snapshot output parent must be a directory")
    if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
        raise OSError("secure snapshot output is not supported on this platform")

    parent_descriptor = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    descriptor = -1
    temporary_name: str | None = None
    try:
        validate_output_entry(parent_descriptor, path.name)
        for _ in range(10):
            candidate = f".{path.name}.{secrets.token_hex(8)}.tmp"
            try:
                descriptor = os.open(
                    candidate,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                    0o600,
                    dir_fd=parent_descriptor,
                )
            except FileExistsError:
                continue
            temporary_name = candidate
            break
        if temporary_name is None:
            raise OSError("could not allocate a private temporary snapshot")

        os.fchmod(descriptor, 0o600)
        handle = os.fdopen(descriptor, "w", encoding="utf-8")
        descriptor = -1
        with handle:
            handle.write(f"{rendered}\n")
            handle.flush()
            os.fsync(handle.fileno())

        validate_output_entry(parent_descriptor, path.name)
        os.replace(
            temporary_name,
            path.name,
            src_dir_fd=parent_descriptor,
            dst_dir_fd=parent_descriptor,
        )
        temporary_name = None
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary_name is not None:
            try:
                os.unlink(temporary_name, dir_fd=parent_descriptor)
            except FileNotFoundError:
                pass
        os.close(parent_descriptor)


class PrivateArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise ValueError("invalid inventory arguments") from None


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = PrivateArgumentParser(description=__doc__)
    parser.add_argument("--policy", type=Path, default=default_policy_path())
    parser.add_argument("--output", type=Path)
    parser.add_argument("--deep", action="store_true", help="Measure directory sizes; this can take several minutes")
    parser.add_argument("--pretty", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    try:
        args = parse_args(argv or sys.argv[1:])
        policy = load_policy(args.policy.expanduser())
        inventory = collect_inventory(policy, deep=args.deep)
        rendered = json.dumps(inventory, indent=2 if args.pretty else None, sort_keys=True)
        if args.output:
            write_private_output(args.output.expanduser(), rendered)
        else:
            print(rendered)
    except Exception:
        print("inventory error: operation failed safely; local details withheld", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
