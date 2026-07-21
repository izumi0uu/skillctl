#!/usr/bin/env python3
"""Normalize a rename manifest and add stable duplicate numbering."""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


GENERIC_TITLES = {
    "",
    "continue",
    "继续",
    "start implementation",
    "开始实现",
    "debug",
    "fix",
    "review",
    "untitled",
    "new chat",
}


def normalize_key(title: str) -> str:
    title = re.sub(r"\s+", " ", title.strip().lower())
    title = re.sub(r"\s+\d+$", "", title)
    title = re.sub(r"[^\w\u4e00-\u9fff]+", " ", title)
    return re.sub(r"\s+", " ", title).strip()


def title_quality(title: str) -> bool:
    return normalize_key(title) not in GENERIC_TITLES and len(title.strip()) >= 3


def load_manifest(path: str | None) -> dict[str, Any]:
    if path:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    return json.load(open(0, encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", nargs="?")
    parser.add_argument("--overwrite-good", action="store_true")
    args = parser.parse_args()

    manifest = load_manifest(args.manifest)
    manifest.setdefault("schema_version", "rename-codex-sessions/v1")
    manifest.setdefault("run_id", "session-renaming-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    manifest.setdefault("created_at", datetime.now(timezone.utc).isoformat())
    items = manifest.setdefault("items", [])

    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in items:
        old_title = str(item.get("old_title") or "")
        candidate = str(item.get("candidate_title") or item.get("final_title") or "").strip()
        if not candidate:
            item["action"] = "manual-review"
            item["reason"] = item.get("reason") or "No candidate title was provided."
            continue
        if title_quality(old_title) and not args.overwrite_good:
            item["final_title"] = old_title
            item["action"] = "skip-good-title"
            item["reason"] = item.get("reason") or "Existing title is already specific."
            continue
        item["candidate_title"] = candidate
        item["action"] = item.get("action") or "rename"
        item["confidence"] = item.get("confidence") or "medium"
        groups[normalize_key(candidate)].append(item)

    duplicate_count = 0
    for group in groups.values():
        if len(group) == 1:
            group[0]["final_title"] = group[0].get("final_title") or group[0]["candidate_title"]
            continue
        for index, item in enumerate(group, start=1):
            suffix = "" if index == 1 else f" {index}"
            item["final_title"] = item["candidate_title"] + suffix
            if index > 1:
                duplicate_count += 1

    summary = {
        "scanned": len(items),
        "renamed": sum(1 for item in items if item.get("action") == "rename"),
        "skipped": sum(1 for item in items if str(item.get("action", "")).startswith("skip-")),
        "manual_review": sum(1 for item in items if item.get("action") == "manual-review"),
        "duplicates_numbered": duplicate_count,
    }
    manifest["summary"] = summary
    print(json.dumps(manifest, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
