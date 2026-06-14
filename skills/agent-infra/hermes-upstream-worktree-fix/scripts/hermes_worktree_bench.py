#!/usr/bin/env python3
"""Health and sync helpers for a local Hermes four-worktree bench."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_CONFIG_PATH = Path.home() / ".hermes" / "admin" / "worktree-bench.json"
DEFAULT_BRANCHES = ("main", "worktree/1", "worktree/2", "worktree/3")
DEFAULT_SUFFIXES = ("", "-1", "-2", "-3")
DEFAULT_REQUIRED_PATHS = {
    "venv": ".venv",
    "node_modules": "node_modules",
    "with_env": ".hermes/with-env.sh",
}
DEFAULT_GIT_SAFETY = {
    "tracking_remote": "upstream",
    "tracking_ref": "upstream/main",
    "merge_ref": "refs/heads/main",
    "push_remote": "origin",
    "push_default": "simple",
    "remote_push_default": "origin",
}


@dataclass(frozen=True)
class CheckoutSpec:
    label: str
    branch: str
    path: Path
    tracking_ref: str | None = None
    tracking_remote: str | None = None
    merge_ref: str | None = None
    push_remote: str | None = None
    check_tracking: bool = True
    enforce_branch_config: bool = True


def _allow_extra_worktrees(config: dict[str, Any]) -> bool:
    raw = config.get("allow_extra_worktrees")
    if raw is None:
        return False
    return bool(raw)


def _git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        ["git", *args],
        cwd=repo,
        text=True,
        capture_output=True,
    )
    if check and proc.returncode != 0:
        raise subprocess.CalledProcessError(
            proc.returncode,
            proc.args,
            output=proc.stdout,
            stderr=proc.stderr,
        )
    return proc


def _load_config(config_path: Path | None, *, explicit: bool) -> dict[str, Any]:
    if config_path is None:
        return {}
    if not config_path.exists():
        if explicit:
            raise FileNotFoundError(f"Bench config not found: {config_path}")
        return {}
    with config_path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"Bench config must be a JSON object: {config_path}")
    return data


def _resolve_root(root_arg: str | None, config: dict[str, Any]) -> Path:
    if root_arg and root_arg != "auto":
        base = Path(root_arg).expanduser().resolve()
    elif isinstance(config.get("root"), str) and config["root"].strip():
        base = Path(config["root"]).expanduser().resolve()
    elif isinstance(config.get("checkouts"), list) and config["checkouts"]:
        first = config["checkouts"][0]
        if not isinstance(first, dict) or "path" not in first:
            raise ValueError("Bench config checkouts[0] must include a path")
        base = Path(first["path"]).expanduser().resolve()
    else:
        proc = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            text=True,
            capture_output=True,
            check=True,
        )
        base = Path(proc.stdout.strip()).resolve()

    if "checkouts" not in config and re.fullmatch(r"hermes-agent-\d+", base.name):
        candidate = base.with_name("hermes-agent")
        if candidate.exists():
            return candidate.resolve()
    return base


def _checkout_specs(root: Path, config: dict[str, Any]) -> list[CheckoutSpec]:
    raw = config.get("checkouts")
    if isinstance(raw, list) and raw:
        specs: list[CheckoutSpec] = []
        for item in raw:
            if not isinstance(item, dict):
                raise ValueError("Every checkout entry must be an object")
            path = Path(str(item["path"])).expanduser().resolve()
            label = str(item.get("label") or item.get("branch") or path.name)
            branch = str(item.get("branch") or label)
            tracking_ref = item.get("tracking_ref")
            tracking_remote = item.get("tracking_remote")
            merge_ref = item.get("merge_ref")
            push_remote = item.get("push_remote")
            specs.append(
                CheckoutSpec(
                    label=label,
                    branch=branch,
                    path=path,
                    tracking_ref=(
                        str(tracking_ref).strip()
                        if isinstance(tracking_ref, str) and tracking_ref.strip()
                        else None
                    ),
                    tracking_remote=(
                        str(tracking_remote).strip()
                        if isinstance(tracking_remote, str) and tracking_remote.strip()
                        else None
                    ),
                    merge_ref=(
                        str(merge_ref).strip()
                        if isinstance(merge_ref, str) and merge_ref.strip()
                        else None
                    ),
                    push_remote=(
                        str(push_remote).strip()
                        if isinstance(push_remote, str) and push_remote.strip()
                        else None
                    ),
                    check_tracking=bool(item.get("check_tracking", True)),
                    enforce_branch_config=bool(item.get("enforce_branch_config", True)),
                )
            )
        return specs

    return [
        CheckoutSpec(label=branch, branch=branch, path=root.with_name(f"{root.name}{suffix}"))
        for branch, suffix in zip(DEFAULT_BRANCHES, DEFAULT_SUFFIXES, strict=True)
    ]


def _required_paths(config: dict[str, Any]) -> tuple[dict[str, str], str]:
    required = dict(DEFAULT_REQUIRED_PATHS)
    raw_required = config.get("required_paths")
    if isinstance(raw_required, dict):
        for key, value in raw_required.items():
            if isinstance(value, str) and value.strip():
                required[key] = value
    marker = str(config.get("with_env_must_contain") or "export HERMES_HOME=")
    return required, marker


def _git_safety_policy(config: dict[str, Any]) -> dict[str, str]:
    policy = dict(DEFAULT_GIT_SAFETY)
    raw_policy = config.get("git_safety")
    if isinstance(raw_policy, dict):
        for key, default in tuple(policy.items()):
            value = raw_policy.get(key)
            if isinstance(value, str) and value.strip():
                policy[key] = value
            else:
                policy[key] = default
    return policy


def _expected_policy_for_checkout(
    spec: CheckoutSpec,
    default_policy: dict[str, str],
) -> dict[str, str]:
    return {
        "tracking_ref": spec.tracking_ref or default_policy["tracking_ref"],
        "tracking_remote": spec.tracking_remote or default_policy["tracking_remote"],
        "merge_ref": spec.merge_ref or default_policy["merge_ref"],
        "push_remote": spec.push_remote or default_policy["push_remote"],
    }


def _ignored_branches(config: dict[str, Any]) -> set[str]:
    ignored = set()
    raw = config.get("ignored_branches")
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, str) and item.strip():
                ignored.add(item.strip())
    return ignored


def _branch_config(root: Path, branch: str) -> dict[str, str | None]:
    def _get(key: str) -> str | None:
        proc = _git(root, "config", "--get", key, check=False)
        value = proc.stdout.strip()
        return value or None

    return {
        "fetch_remote": _get(f"branch.{branch}.remote"),
        "merge_ref": _get(f"branch.{branch}.merge"),
        "push_remote": _get(f"branch.{branch}.pushRemote"),
    }


def _parse_worktree_list(root: Path) -> list[dict[str, str]]:
    proc = _git(root, "worktree", "list", "--porcelain")
    entries: list[dict[str, str]] = []
    entry: dict[str, str] = {}
    for raw_line in proc.stdout.splitlines():
        line = raw_line.strip()
        if not line:
            if entry:
                entries.append(entry)
                entry = {}
            continue
        key, _, value = line.partition(" ")
        if key == "worktree":
            entry["path"] = value
        elif key == "branch":
            entry["branch"] = value.removeprefix("refs/heads/")
        elif key == "HEAD":
            entry["head"] = value
        else:
            entry[key] = value
    if entry:
        entries.append(entry)
    return entries


def _tracking_head(root: Path, tracking_ref: str) -> str | None:
    proc = _git(root, "rev-parse", tracking_ref, check=False)
    value = proc.stdout.strip()
    return value or None


def _collect_checkout_status(
    spec: CheckoutSpec,
    tracking_ref: str,
    tracking_head: str | None,
    required_paths: dict[str, str],
    with_env_marker: str,
) -> dict[str, Any]:
    findings: list[dict[str, str]] = []
    status: dict[str, Any] = {
        "label": spec.label,
        "expected_branch": spec.branch,
        "path": str(spec.path),
        "exists": spec.path.exists(),
        "tracking_ref": tracking_ref,
        "tracking_head": tracking_head,
        "check_tracking": spec.check_tracking,
        "findings": findings,
    }
    if not spec.path.exists():
        findings.append({
            "severity": "blocker",
            "code": "missing_checkout",
            "message": f"Missing checkout: {spec.path}",
        })
        status["isolated_env"] = {
            "venv": False,
            "node_modules": False,
            "with_env": False,
            "with_env_sets_home": False,
        }
        return status

    actual_branch = _git(spec.path, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    head = _git(spec.path, "rev-parse", "HEAD").stdout.strip()
    porcelain = _git(spec.path, "status", "--porcelain").stdout.splitlines()
    clean = not porcelain
    if not clean:
        findings.append({
            "severity": "blocker",
            "code": "dirty_checkout",
            "message": f"Checkout has local changes: {spec.path}",
        })
    if actual_branch != spec.branch:
        findings.append({
            "severity": "warning",
            "code": "branch_mismatch",
            "message": f"Expected {spec.branch}, found {actual_branch}",
        })

    ahead = None
    behind = None
    if not spec.check_tracking:
        ahead = 0
        behind = 0
    elif tracking_head is None:
        findings.append({
            "severity": "blocker",
            "code": "missing_tracking_ref",
            "message": f"{tracking_ref} is not available locally",
        })
    else:
        counts = _git(spec.path, "rev-list", "--left-right", "--count", f"{tracking_ref}...{spec.branch}")
        behind_str, ahead_str = counts.stdout.strip().split("\t")
        behind = int(behind_str)
        ahead = int(ahead_str)
        if ahead > 0:
            findings.append({
                "severity": "blocker",
                "code": "ahead_of_tracking_ref",
                "message": f"{spec.branch} has {ahead} local commit(s) ahead of {tracking_ref}",
            })
        elif behind > 0:
            findings.append({
                "severity": "warning",
                "code": "behind_tracking_ref",
                "message": f"{spec.branch} is {behind} commit(s) behind {tracking_ref}",
            })

    with_env_path = spec.path / required_paths["with_env"]
    with_env_exists = with_env_path.exists()
    with_env_sets_home = False
    if with_env_exists:
        try:
            with_env_sets_home = with_env_marker in with_env_path.read_text(encoding="utf-8")
        except OSError:
            with_env_sets_home = False

    isolated_env = {
        "venv": (spec.path / required_paths["venv"]).exists(),
        "node_modules": (spec.path / required_paths["node_modules"]).exists(),
        "with_env": with_env_exists,
        "with_env_sets_home": with_env_sets_home,
    }
    for key, present in isolated_env.items():
        if not present:
            findings.append({
                "severity": "warning",
                "code": f"missing_{key}",
                "message": f"{spec.path} is missing {key}",
            })

    status.update({
        "actual_branch": actual_branch,
        "head": head,
        "clean": clean,
        "status_lines": porcelain,
        "ahead_of_tracking_ref": ahead,
        "behind_tracking_ref": behind,
        "isolated_env": isolated_env,
    })
    return status


def collect_bench_status(root: Path, config: dict[str, Any]) -> dict[str, Any]:
    policy = _git_safety_policy(config)
    allow_extra_worktrees = _allow_extra_worktrees(config)
    required_paths, with_env_marker = _required_paths(config)
    checkouts = _checkout_specs(root, config)
    tracking_ref = policy["tracking_ref"]
    tracking_heads: dict[str, str | None] = {}
    worktrees = []
    for spec in checkouts:
        expected_policy = _expected_policy_for_checkout(spec, policy)
        spec_tracking_ref = expected_policy["tracking_ref"]
        if spec_tracking_ref not in tracking_heads:
            tracking_heads[spec_tracking_ref] = _tracking_head(root, spec_tracking_ref)
        worktrees.append(
            _collect_checkout_status(
                spec,
                spec_tracking_ref,
                tracking_heads[spec_tracking_ref],
                required_paths,
                with_env_marker,
            )
        )

    expected_paths = {str(spec.path.resolve()) for spec in checkouts}
    worktree_entries = _parse_worktree_list(root)
    extra_worktrees = sorted(
        entry["path"]
        for entry in worktree_entries
        if str(Path(entry["path"]).resolve()) not in expected_paths
    )
    expected_branches = {spec.branch for spec in checkouts}
    ignored_branches = _ignored_branches(config)
    extra_branches = sorted(
        branch
        for branch in _git(root, "for-each-ref", "refs/heads", "--format=%(refname:short)").stdout.splitlines()
        if branch and branch not in expected_branches and branch not in ignored_branches
    )

    git_safety = {
        "push_default": (_git(root, "config", "--get", "push.default", check=False).stdout.strip() or None),
        "remote_push_default": (
            _git(root, "config", "--get", "remote.pushDefault", check=False).stdout.strip() or None
        ),
        "tracking_ref": tracking_ref,
        "branches": {
            spec.branch: {
                "actual": _branch_config(root, spec.branch),
                "expected": _expected_policy_for_checkout(spec, policy),
                "enforce": spec.enforce_branch_config,
            }
            for spec in checkouts
        },
    }

    findings: list[dict[str, str]] = []
    for worktree in worktrees:
        findings.extend(worktree["findings"])
    if extra_worktrees:
        findings.append({
            "severity": "warning" if allow_extra_worktrees else "blocker",
            "code": "extra_worktrees",
            "message": f"Extra worktrees present: {', '.join(extra_worktrees)}",
        })
    if extra_branches:
        findings.append({
            "severity": "warning",
            "code": "extra_branches",
            "message": f"Extra local branches present: {', '.join(extra_branches)}",
        })
    if git_safety["push_default"] != policy["push_default"]:
        findings.append({
            "severity": "warning",
            "code": "push_default_mismatch",
            "message": f"push.default should be set to {policy['push_default']}",
        })
    if git_safety["remote_push_default"] != policy["remote_push_default"]:
        findings.append({
            "severity": "warning",
            "code": "remote_push_default_mismatch",
            "message": f"remote.pushDefault should be set to {policy['remote_push_default']}",
        })
    for spec in checkouts:
        branch = spec.branch
        branch_entry = git_safety["branches"][branch]
        if not branch_entry["enforce"]:
            continue
        branch_config = branch_entry["actual"]
        expected_policy = branch_entry["expected"]
        if branch_config["fetch_remote"] != expected_policy["tracking_remote"]:
            findings.append({
                "severity": "warning",
                "code": "branch_fetch_remote_mismatch",
                "message": f"{branch} should fetch from {expected_policy['tracking_remote']}",
            })
        if branch_config["merge_ref"] != expected_policy["merge_ref"]:
            findings.append({
                "severity": "warning",
                "code": "branch_merge_ref_mismatch",
                "message": f"{branch} should merge against {expected_policy['merge_ref']}",
            })
        if branch_config["push_remote"] != expected_policy["push_remote"]:
            findings.append({
                "severity": "warning",
                "code": "branch_push_remote_mismatch",
                "message": f"{branch} should push to {expected_policy['push_remote']}",
            })

    blockers = sum(1 for finding in findings if finding["severity"] == "blocker")
    warnings = sum(1 for finding in findings if finding["severity"] == "warning")
    return {
        "root": str(root),
        "config_path": str(config.get("_config_path")) if config.get("_config_path") else None,
        "tracking_ref": tracking_ref,
        "tracking_head": tracking_heads.get(tracking_ref),
        "expected_checkouts": [
            {
                "label": spec.label,
                "branch": spec.branch,
                "path": str(spec.path),
                "tracking_ref": spec.tracking_ref,
                "tracking_remote": spec.tracking_remote,
                "merge_ref": spec.merge_ref,
                "push_remote": spec.push_remote,
                "check_tracking": spec.check_tracking,
                "enforce_branch_config": spec.enforce_branch_config,
            }
            for spec in checkouts
        ],
        "worktrees": worktrees,
        "extra_worktrees": extra_worktrees,
        "extra_branches": extra_branches,
        "git_safety": git_safety,
        "policy": {
            "allow_extra_worktrees": allow_extra_worktrees,
        },
        "findings": findings,
        "summary": {
            "healthy": blockers == 0 and warnings == 0,
            "blockers": blockers,
            "warnings": warnings,
        },
    }


def apply_git_safety(root: Path, config: dict[str, Any]) -> dict[str, Any]:
    policy = _git_safety_policy(config)
    _git(root, "config", "push.default", policy["push_default"])
    _git(root, "config", "remote.pushDefault", policy["remote_push_default"])
    _git(root, "config", "fetch.prune", "true")
    _git(root, "config", "pull.ff", "only")
    for spec in _checkout_specs(root, config):
        expected_policy = _expected_policy_for_checkout(spec, policy)
        _git(root, "config", f"branch.{spec.branch}.pushRemote", expected_policy["push_remote"])
        _git(root, "config", f"branch.{spec.branch}.remote", expected_policy["tracking_remote"])
        _git(root, "config", f"branch.{spec.branch}.merge", expected_policy["merge_ref"])
    report = collect_bench_status(root, config)
    report["action"] = "apply-git-safety"
    return report


def sync_bench(root: Path, config: dict[str, Any]) -> tuple[dict[str, Any], int]:
    policy = _git_safety_policy(config)
    remotes = {policy["tracking_remote"]}
    for spec in _checkout_specs(root, config):
        remotes.add(_expected_policy_for_checkout(spec, policy)["tracking_remote"])
    for remote in sorted(remotes):
        _git(root, "fetch", remote, "--prune")
    report = collect_bench_status(root, config)
    blockers = [finding for finding in report["findings"] if finding["severity"] == "blocker"]
    if blockers:
        report["action"] = "sync"
        report["sync_applied"] = False
        return report, 1

    operations: list[dict[str, str]] = []
    for spec in _checkout_specs(root, config):
        tracking_ref = _expected_policy_for_checkout(spec, policy)["tracking_ref"]
        tracking_head = _tracking_head(root, tracking_ref)
        assert tracking_head is not None
        _git(spec.path, "checkout", spec.branch)
        if spec.check_tracking:
            _git(
                spec.path,
                "branch",
                "--set-upstream-to",
                tracking_ref,
                spec.branch,
            )
        _git(spec.path, "reset", "--hard", tracking_head)
        operations.append(
            {
                "path": str(spec.path),
                "branch": spec.branch,
                "head": tracking_head,
                "tracking_ref": tracking_ref,
            }
        )

    updated = collect_bench_status(root, config)
    updated["action"] = "sync"
    updated["sync_applied"] = True
    updated["operations"] = operations
    return updated, 0


def _render_human(report: dict[str, Any]) -> str:
    lines = [
        f"Hermes worktree bench: {report['root']}",
        f"default tracking ref: {report['tracking_ref']} ({report['tracking_head'] or 'missing'})",
    ]
    if report["config_path"]:
        lines.append(f"config: {report['config_path']}")
    for worktree in report["worktrees"]:
        branch = worktree.get("actual_branch", "missing")
        head = worktree.get("head", "missing")
        lines.append(
            f"- {worktree['label']}: branch={branch} head={head} clean={worktree.get('clean', False)} "
            f"tracking={worktree.get('tracking_ref')} "
            f"ahead={worktree.get('ahead_of_tracking_ref')} behind={worktree.get('behind_tracking_ref')}"
        )
        isolated_env = worktree["isolated_env"]
        lines.append(
            "  env: "
            f".venv={isolated_env['venv']} node_modules={isolated_env['node_modules']} "
            f"with-env={isolated_env['with_env']} HERMES_HOME={isolated_env['with_env_sets_home']}"
        )
    if report["extra_worktrees"]:
        lines.append(f"extra worktrees: {', '.join(report['extra_worktrees'])}")
    if report["extra_branches"]:
        lines.append(f"extra branches: {', '.join(report['extra_branches'])}")
    lines.append(
        "git safety: "
        f"push.default={report['git_safety']['push_default']!r} "
        f"remote.pushDefault={report['git_safety']['remote_push_default']!r}"
    )
    if report["findings"]:
        lines.append("findings:")
        for finding in report["findings"]:
            lines.append(f"  - [{finding['severity']}] {finding['message']}")
    lines.append(
        f"summary: healthy={report['summary']['healthy']} "
        f"blockers={report['summary']['blockers']} warnings={report['summary']['warnings']}"
    )
    return "\n".join(lines)


def _config_path_from_args(raw_path: str | None) -> tuple[Path | None, bool]:
    if raw_path is None:
        return DEFAULT_CONFIG_PATH, False
    return Path(raw_path).expanduser().resolve(), True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Manage the local Hermes four-worktree development bench."
    )
    parser.add_argument(
        "--config",
        help=f"Bench config JSON path (default: {DEFAULT_CONFIG_PATH})",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    status_parser = subparsers.add_parser("status", help="Inspect worktree bench health")
    status_parser.add_argument("--root", default="auto", help="Path to the main Hermes checkout")
    status_parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    status_parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero on warnings as well as blockers",
    )

    sync_parser = subparsers.add_parser("sync", help="Sync all four worktrees to the tracking ref")
    sync_parser.add_argument("--root", default="auto", help="Path to the main Hermes checkout")
    sync_parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")

    safety_parser = subparsers.add_parser(
        "apply-git-safety",
        help="Configure local git push safety for the four-worktree bench",
    )
    safety_parser.add_argument("--root", default="auto", help="Path to the main Hermes checkout")
    safety_parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")

    args = parser.parse_args(argv)
    config_path, explicit = _config_path_from_args(args.config)
    config = _load_config(config_path, explicit=explicit)
    if config_path and config_path.exists():
        config["_config_path"] = str(config_path)
    root = _resolve_root(getattr(args, "root", "auto"), config)

    if args.command == "status":
        report = collect_bench_status(root, config)
        if args.json:
            print(json.dumps(report, indent=2, sort_keys=True))
        else:
            print(_render_human(report))
        if report["summary"]["blockers"] > 0:
            return 1
        if args.strict and report["summary"]["warnings"] > 0:
            return 1
        return 0

    if args.command == "sync":
        report, exit_code = sync_bench(root, config)
        if args.json:
            print(json.dumps(report, indent=2, sort_keys=True))
        else:
            print(_render_human(report))
        return exit_code

    report = apply_git_safety(root, config)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(_render_human(report))
    return 0 if report["summary"]["blockers"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
