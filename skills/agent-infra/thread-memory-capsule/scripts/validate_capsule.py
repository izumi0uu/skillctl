#!/usr/bin/env python3
"""Validate a thread-memory-capsule manifest and markdown references."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


ALLOWED_STATUS = {
    "source-supported",
    "extraction-time-fact",
    "current-checkout-state",
    "historical-branch-state",
    "decision",
    "risk",
    "verified",
    "environment-gap",
    "needs-reinspection",
}

ALLOWED_PATH_STATUS = {
    "exists-current-checkout",
    "missing-current-checkout",
    "historical-only",
    "not-applicable",
}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def source_lines(path: Path | None) -> list[str]:
    if path is None or not path.exists():
        return []
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    return lines


def validate_line_ref(ref: str, line_count: int) -> str | None:
    match = re.fullmatch(r"L(\d+)(?:-L(\d+))?", ref)
    if not match:
        return f"bad line ref {ref}"
    start = int(match.group(1))
    end = int(match.group(2) or match.group(1))
    if start < 1 or end < start:
        return f"invalid line range {ref}"
    if line_count and end > line_count:
        return f"line ref out of range {ref} > {line_count}"
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--source")
    parser.add_argument("--markdown", action="append", default=[])
    parser.add_argument("--claim-prefix", default=None)
    args = parser.parse_args()

    manifest_path = Path(args.manifest)
    manifest = load_json(manifest_path)
    source_path = Path(args.source or manifest.get("source_transcript_path", "")).expanduser() if (args.source or manifest.get("source_transcript_path")) else None
    lines = source_lines(source_path)
    errors: list[str] = []

    claims = manifest.get("claims")
    if not isinstance(claims, list) or not claims:
        errors.append("manifest.claims must be a non-empty list")
        claims = []

    ids: set[str] = set()
    prefix = args.claim_prefix
    for index, claim in enumerate(claims):
        claim_id = str(claim.get("claim_id", ""))
        label = claim_id or f"claims[{index}]"
        if not claim_id:
            errors.append(f"{label}: missing claim_id")
        if prefix and not claim_id.startswith(prefix):
            errors.append(f"{label}: claim_id does not start with {prefix}")
        if claim_id in ids:
            errors.append(f"{label}: duplicate claim_id")
        ids.add(claim_id)
        if not str(claim.get("claim", "")).strip():
            errors.append(f"{label}: missing claim text")
        if claim.get("status") not in ALLOWED_STATUS:
            errors.append(f"{label}: invalid status {claim.get('status')!r}")
        if claim.get("repo_path_status") not in ALLOWED_PATH_STATUS:
            errors.append(f"{label}: invalid repo_path_status {claim.get('repo_path_status')!r}")
        refs = claim.get("transcript_line_refs")
        if not isinstance(refs, list):
            errors.append(f"{label}: transcript_line_refs must be a list")
            refs = []
        for ref in refs:
            error = validate_line_ref(str(ref), len(lines))
            if error:
                errors.append(f"{label}: {error}")
        if lines:
            for turn_id in claim.get("turn_ids", []) or []:
                found = False
                for ref in refs:
                    match = re.fullmatch(r"L(\d+)(?:-L(\d+))?", str(ref))
                    if not match:
                        continue
                    start = max(1, int(match.group(1)) - 5)
                    end = min(len(lines), int(match.group(2) or match.group(1)) + 5)
                    if any(str(turn_id) in lines[number - 1] for number in range(start, end + 1)):
                        found = True
                if not found:
                    errors.append(f"{label}: turn_id {turn_id} not found near cited refs")

    if lines:
        expected_lines = manifest.get("source_transcript_line_count")
        if isinstance(expected_lines, int) and expected_lines != len(lines):
            errors.append(f"source_transcript_line_count mismatch: {expected_lines} != {len(lines)}")
        expected_bytes = manifest.get("source_transcript_size_bytes")
        if isinstance(expected_bytes, int) and source_path and source_path.exists() and expected_bytes != source_path.stat().st_size:
            errors.append(f"source_transcript_size_bytes mismatch: {expected_bytes} != {source_path.stat().st_size}")

    markdown_refs: set[str] = set()
    for raw_path in args.markdown:
        md_path = Path(raw_path)
        text = md_path.read_text(encoding="utf-8")
        for match in re.finditer(r"\b[A-Z]{2,}-\d{3}\b", text):
            ref = match.group(0)
            markdown_refs.add(ref)
            if ref not in ids:
                errors.append(f"{md_path}: unknown claim ref {ref}")

    if args.markdown:
        missing = sorted(ids - markdown_refs)
        if missing:
            errors.append(f"claims not cited by markdown: {', '.join(missing)}")

    result = {
        "ok": not errors,
        "errors": errors,
        "claim_count": len(claims),
        "markdown_claim_refs": len(markdown_refs),
        "source_line_count": len(lines) if lines else None,
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
