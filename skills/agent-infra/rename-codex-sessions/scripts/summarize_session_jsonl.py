#!/usr/bin/env python3
"""Create compact, safe summaries for Codex JSONL session files."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_-]{16,}"),
    re.compile(r"(?i)(api[_-]?key|secret|token|password)\s*[:=]\s*\S+"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"data:image/[^,]+,[A-Za-z0-9+/=]{80,}"),
]


def scrub(text: str, limit: int = 240) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    for pattern in SECRET_PATTERNS:
        text = pattern.sub("[REDACTED]", text)
    if len(text) > limit:
        return text[: limit - 1].rstrip() + "..."
    return text


def iter_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def text_from_row(row: dict[str, Any]) -> tuple[str | None, str]:
    role = row.get("role") or row.get("type")
    parts: list[str] = []

    def collect(value: Any) -> None:
        if isinstance(value, str):
            parts.append(value)
        elif isinstance(value, list):
            for item in value:
                collect(item)
        elif isinstance(value, dict):
            if isinstance(value.get("text"), str):
                parts.append(value["text"])
            elif isinstance(value.get("content"), str):
                parts.append(value["content"])
            else:
                for key in ("message", "summary", "cmd", "output"):
                    if isinstance(value.get(key), str):
                        parts.append(value[key])

    for key in ("content", "message", "summary", "text"):
        if key in row:
            collect(row[key])
    return str(role) if role is not None else None, scrub(" ".join(parts))


def summarize(path: Path, max_messages: int) -> dict[str, Any]:
    rows = iter_jsonl(path)
    messages: list[dict[str, str]] = []
    for row in rows:
        role, text = text_from_row(row)
        if not text:
            continue
        if role and role not in {"user", "assistant", "system", "message", "response"}:
            if len(messages) >= max_messages:
                continue
        messages.append({"role": role or "unknown", "text": text})

    first = messages[: max_messages // 2]
    last = messages[-(max_messages - len(first)) :] if len(messages) > len(first) else []
    compact = first + [m for m in last if m not in first]
    return {
        "id": path.stem,
        "source": "codex-jsonl",
        "session_path": str(path),
        "old_title": "",
        "message_count": len(messages),
        "line_count": len(rows),
        "evidence": compact,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="+", help="JSONL files or directories to scan")
    parser.add_argument("--max-messages", type=int, default=12)
    args = parser.parse_args()

    files: list[Path] = []
    for raw in args.paths:
        path = Path(raw).expanduser()
        if path.is_dir():
            files.extend(sorted(path.rglob("*.jsonl")))
        elif path.suffix == ".jsonl":
            files.append(path)

    print(json.dumps({"sessions": [summarize(path, args.max_messages) for path in files]}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
