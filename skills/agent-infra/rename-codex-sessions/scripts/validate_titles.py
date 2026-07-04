#!/usr/bin/env python3
"""Validate a rename-codex-sessions manifest before applying titles."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


FORBIDDEN = [
    re.compile(r"sk-[A-Za-z0-9_-]{12,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"(?i)(password|secret|api[_-]?key)\s*[:=]"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._-]{12,}"),
    re.compile(r"data:image/"),
    re.compile(r"[A-Za-z0-9+/=]{120,}"),
]


ALLOWED_ACTIONS = {
    "rename",
    "skip-good-title",
    "skip-low-confidence",
    "skip-running",
    "skip-unsafe",
    "manual-review",
}


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest")
    parser.add_argument("--max-length", type=int, default=72)
    args = parser.parse_args()

    manifest = load(Path(args.manifest))
    errors: list[str] = []
    items = manifest.get("items")
    if not isinstance(items, list):
        errors.append("manifest.items must be a list")
        items = []

    final_titles: dict[str, str] = {}
    for index, item in enumerate(items):
        prefix = f"items[{index}]"
        item_id = str(item.get("id") or item.get("thread_id") or item.get("session_path") or "")
        action = item.get("action")
        final_title = str(item.get("final_title") or "")
        if not item_id:
            errors.append(f"{prefix}: missing id/thread_id/session_path")
        if action not in ALLOWED_ACTIONS:
            errors.append(f"{prefix}: invalid action {action!r}")
        if action == "rename":
            if not final_title.strip():
                errors.append(f"{prefix}: rename missing final_title")
            if len(final_title) > args.max_length:
                errors.append(f"{prefix}: title too long ({len(final_title)} > {args.max_length})")
            for pattern in FORBIDDEN:
                if pattern.search(final_title):
                    errors.append(f"{prefix}: forbidden sensitive pattern in title")
            key = final_title.strip().lower()
            if key in final_titles:
                errors.append(f"{prefix}: duplicate final_title also used by {final_titles[key]}")
            final_titles[key] = item_id or prefix
        if action and action.startswith("skip") and not item.get("reason"):
            errors.append(f"{prefix}: skipped item needs reason")

    result = {
        "ok": not errors,
        "errors": errors,
        "scanned": len(items),
        "rename_count": sum(1 for item in items if item.get("action") == "rename"),
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
