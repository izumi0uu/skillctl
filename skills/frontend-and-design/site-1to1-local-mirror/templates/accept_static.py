#!/usr/bin/env python3
"""Static gate for local mirrors: routes, shims, inline script syntax."""
from __future__ import annotations

import json
import re
import subprocess
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SITE = ROOT / "site"
BASE = "http://127.0.0.1:4178"
OUT = ROOT / "meta" / "accept-static.json"

PAGES = ["/"]  # extend per project


def fetch(path: str) -> tuple[int, bytes]:
    try:
        with urllib.request.urlopen(BASE + path, timeout=20) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read() if e.fp else b""
    except Exception:
        return 0, b""


def inline_script_fails(html: str) -> list[str]:
    fails: list[str] = []
    for i, body in enumerate(
        re.findall(r"<script(?![^>]*\bsrc=)[^>]*>([\s\S]*?)</script>", html)
    ):
        body = body.strip()
        if not body:
            continue
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
            fh.write(body)
            path = fh.name
        try:
            p = subprocess.run(["node", "--check", path], capture_output=True, text=True)
            if p.returncode != 0:
                fails.append(f"inline#{i}: {(p.stderr or '')[:180]}")
        finally:
            Path(path).unlink(missing_ok=True)
    return fails


def main() -> int:
    report: dict = {"base": BASE, "pages": {}, "failures": [], "pass": False}
    for page in PAGES:
        st, body = fetch(page)
        text = body.decode("utf-8", "replace")
        fails = inline_script_fails(text) if st == 200 else [f"status {st}"]
        report["pages"][page] = {
            "status": st,
            "inline_fails": fails[:5],
            "remote_media": len(
                re.findall(
                    r"https://(?:www\.datocms-assets\.com|stream\.mux\.com)/",
                    text,
                )
            ),
        }
        if st != 200:
            report["failures"].append(f"{page} status {st}")
        if fails:
            report["failures"].append(f"{page} inline syntax fails: {len(fails)}")

    # Common Next shims (ignore if not Next)
    for path in [
        "/_next/static/chunks/",  # may 404 if empty path; customize per project
    ]:
        pass

    report["pass"] = len(report["failures"]) == 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"pass": report["pass"], "failures": report["failures"]}, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
