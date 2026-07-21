#!/usr/bin/env python3
"""Local static server skeleton for publish-surface mirrors.

Features:
- Serves ./site as root
- Basename shim for /_next/static/*
- /_next/image?url=... -> local media by filename
- HTTP Range for video/font
- BrokenPipe-safe writes
"""
from __future__ import annotations

import mimetypes
import re
import urllib.parse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent / "site"
PORT = 4178

CHUNK: dict[str, Path] = {}
MEDIA: dict[str, Path] = {}
for f in (ROOT / "assets").rglob("*") if (ROOT / "assets").exists() else []:
    if not f.is_file():
        continue
    suf = f.suffix.lower()
    if suf in {".js", ".css", ".mjs"}:
        CHUNK[f.name] = f
    if suf in {".jpg", ".jpeg", ".png", ".webp", ".avif", ".svg", ".gif", ".webm", ".mp4"}:
        MEDIA[f.name] = f


class Handler(SimpleHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def log_message(self, format, *args):  # noqa: A003
        print("[server]", args[0] if args else format)

    def _send_bytes(
        self,
        path: Path,
        data: bytes,
        status: int = 200,
        start: int | None = None,
        end: int | None = None,
    ) -> None:
        ctype = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        size = path.stat().st_size
        try:
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(len(data)))
            if start is not None and end is not None:
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.send_header(
                "Cache-Control",
                "no-cache" if path.suffix.lower() == ".html" else "public, max-age=3600",
            )
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            return

    def _send_file(self, path: Path) -> None:
        if not path.is_file():
            self.send_error(404, f"missing {path}")
            return
        size = path.stat().st_size
        rng = self.headers.get("Range")
        if rng and path.suffix.lower() in {".mp4", ".webm", ".woff2", ".woff"}:
            m = re.match(r"bytes=(\d*)-(\d*)", rng)
            if m:
                start = int(m.group(1) or 0)
                end = int(m.group(2) or size - 1)
                end = min(end, size - 1)
                if start > end or start >= size:
                    self.send_error(416, "Invalid Range")
                    return
                with path.open("rb") as fh:
                    fh.seek(start)
                    data = fh.read(end - start + 1)
                self._send_bytes(path, data, status=206, start=start, end=end)
                return
        self._send_bytes(path, path.read_bytes(), status=200)

    def do_HEAD(self) -> None:  # noqa: N802
        self.do_GET()

    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlsplit(self.path)
        raw = urllib.parse.unquote(parsed.path)
        qs = urllib.parse.parse_qs(parsed.query)

        if raw.startswith("/_next/image"):
            url = urllib.parse.unquote((qs.get("url") or [""])[0])
            fname = url.split("?")[0].split("/")[-1]
            f = MEDIA.get(fname)
            if not f:
                for k, v in MEDIA.items():
                    if fname and fname in k:
                        f = v
                        break
            if f:
                self._send_file(f)
                return
            self.send_error(404, f"image not local: {fname}")
            return

        if raw.startswith("/_next/static/"):
            fname = raw.split("/")[-1]
            f = CHUNK.get(fname) or CHUNK.get(fname.replace("..", "."))
            if f:
                self._send_file(f)
                return
            self.send_error(404, f"chunk not local: {fname}")
            return

        # Normal path resolution
        parts = [p for p in raw.split("/") if p not in ("", ".")]
        safe: list[str] = []
        for p in parts:
            if p == "..":
                if safe:
                    safe.pop()
                continue
            safe.append(p)
        full = ROOT.joinpath(*safe) if safe else ROOT
        if full.is_file():
            self._send_file(full)
            return
        if full.is_dir() and (full / "index.html").is_file():
            self._send_file(full / "index.html")
            return
        html = full.with_suffix(".html")
        if html.is_file():
            self._send_file(html)
            return

        # Basename fallback
        fname = raw.split("/")[-1]
        if fname in MEDIA:
            self._send_file(MEDIA[fname])
            return
        if fname in CHUNK:
            self._send_file(CHUNK[fname])
            return

        self.send_error(404, raw)


def main() -> None:
    mimetypes.add_type("application/javascript", ".js")
    mimetypes.add_type("text/css", ".css")
    mimetypes.add_type("image/avif", ".avif")
    mimetypes.add_type("image/webp", ".webp")
    mimetypes.add_type("image/svg+xml", ".svg")
    mimetypes.add_type("font/woff2", ".woff2")
    mimetypes.add_type("video/webm", ".webm")
    mimetypes.add_type("video/mp4", ".mp4")
    httpd = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"Serving {ROOT}")
    print(f"Open http://127.0.0.1:{PORT}/")
    print(f"Indexed chunks={len(CHUNK)} media={len(MEDIA)}")
    httpd.serve_forever()


if __name__ == "__main__":
    main()
