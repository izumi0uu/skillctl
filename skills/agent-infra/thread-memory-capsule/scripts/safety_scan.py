#!/usr/bin/env python3
"""Scan capsule files for raw payloads, secrets, and bulky transcript residue."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


PATTERNS = {
    "data-image": re.compile(r"data:image/"),
    "openai-key": re.compile(r"sk-[A-Za-z0-9_-]{16,}"),
    "private-key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "secret-assignment": re.compile(r"(?i)(password|secret|api[_-]?key|auth[_-]?token)\s*[:=]\s*\S+"),
    "traceback": re.compile(r"Traceback \(most recent call last\):"),
    "long-base64-like": re.compile(r"[A-Za-z0-9+/=]{500,}"),
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="+")
    args = parser.parse_args()

    findings: list[dict[str, object]] = []
    for raw_path in args.paths:
        path = Path(raw_path)
        text = path.read_text(encoding="utf-8", errors="replace")
        for name, pattern in PATTERNS.items():
            for match in pattern.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                findings.append({"path": str(path), "line": line, "pattern": name})

    result = {"ok": not findings, "findings": findings}
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if not findings else 1


if __name__ == "__main__":
    raise SystemExit(main())
