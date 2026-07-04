#!/usr/bin/env python3
"""Create a revert manifest from a rename-codex-sessions manifest."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    manifest: dict[str, Any] = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    backup = {
        "schema_version": "rename-codex-sessions-backup/v1",
        "source_run_id": manifest.get("run_id"),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "items": [],
    }
    for item in manifest.get("items", []):
        backup["items"].append(
            {
                "id": item.get("id") or item.get("thread_id") or item.get("session_path"),
                "source": item.get("source"),
                "host_id": item.get("host_id"),
                "session_path": item.get("session_path"),
                "old_title": item.get("old_title", ""),
                "applied_title": item.get("final_title", ""),
                "action": item.get("action"),
            }
        )
    output = Path(args.output).expanduser()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(backup, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "path": str(output), "items": len(backup["items"])}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
