#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import shlex
import stat
import subprocess
import tomllib
from pathlib import Path


CODEX_HOME = Path.home() / ".codex"
CONFIG_PATH = CODEX_HOME / "config.toml"
AUTH_PATH = CODEX_HOME / "auth.json"
COCKPIT_AUTH_PATH = CODEX_HOME / ".cockpit_codex_auth.json"
SHELL_FILES = [
    Path.home() / ".zshrc",
    Path.home() / ".zprofile",
    Path.home() / ".zshenv",
    Path.home() / ".bash_profile",
    Path.home() / ".bashrc",
]


def run(cmd: str) -> dict:
    proc = subprocess.run(
        cmd,
        shell=True,
        text=True,
        capture_output=True,
        timeout=60,
    )
    return {
        "cmd": cmd,
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }


def run_login_shell(cmd: str) -> dict:
    return run("zsh -lic " + shlex.quote(cmd))


def file_mode(path: Path) -> str | None:
    if not path.exists():
        return None
    return oct(stat.S_IMODE(path.stat().st_mode))


def scan_shell_secrets() -> list[dict]:
    findings: list[dict] = []
    patterns = ("ANTHROPIC_AUTH_TOKEN", "OPENAI_API_KEY", "sk-")
    for path in SHELL_FILES:
        if not path.exists():
            continue
        for lineno, line in enumerate(path.read_text().splitlines(), start=1):
            if any(p in line for p in patterns):
                findings.append(
                    {
                        "file": str(path),
                        "line": lineno,
                        "content": line.strip(),
                    }
                )
    return findings


def parse_config() -> dict:
    with CONFIG_PATH.open("rb") as handle:
        return tomllib.load(handle)


def summarize_doctor(doctor_json: dict) -> dict:
    checks = doctor_json.get("checks", {})
    failures = {
        key: value.get("summary", "")
        for key, value in checks.items()
        if value.get("status") == "fail"
    }
    return {
        "overallStatus": doctor_json.get("overallStatus"),
        "failures": failures,
    }


def main() -> int:
    report: dict = {
        "paths": {
            "config": str(CONFIG_PATH),
            "auth": str(AUTH_PATH),
            "cockpit_auth": str(COCKPIT_AUTH_PATH),
        }
    }

    config = parse_config()
    report["config"] = {
        "model_provider": config.get("model_provider"),
        "model": config.get("model"),
        "mcp_count": len(config.get("mcp_servers", {})),
        "plugin_count": len(config.get("plugins", {})),
    }

    report["file_modes"] = {
        "auth.json": file_mode(AUTH_PATH),
        ".cockpit_codex_auth.json": file_mode(COCKPIT_AUTH_PATH),
        "config.toml": file_mode(CONFIG_PATH),
    }

    report["shell_secret_hits"] = scan_shell_secrets()

    report["login_shell"] = run(
        "zsh -lic "
        + shlex.quote(
            "which codex; which npm; which node; npm prefix -g; node -v; codex --version"
        )
    )
    report["doctor"] = run_login_shell("codex doctor --json")
    if report["doctor"]["returncode"] in (0, 1) and report["doctor"]["stdout"].strip():
        try:
            doctor_json = json.loads(report["doctor"]["stdout"])
            report["doctor_summary"] = summarize_doctor(doctor_json)
        except json.JSONDecodeError:
            report["doctor_summary"] = {"parse_error": True}

    report["mcp_list"] = run_login_shell("codex mcp list")
    report["plugin_list"] = run_login_shell("codex plugin list")
    report["smoke_test"] = run_login_shell(
        "codex exec --skip-git-repo-check --ephemeral -C /tmp "
        "--output-last-message /tmp/codex-health-last.txt "
        + shlex.quote("Reply with the single word pong.")
    )

    last_path = Path("/tmp/codex-health-last.txt")
    report["smoke_last_message"] = last_path.read_text().strip() if last_path.exists() else None

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
