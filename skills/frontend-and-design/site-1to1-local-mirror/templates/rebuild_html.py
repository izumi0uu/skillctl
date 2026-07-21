#!/usr/bin/env python3
"""Escape-safe HTML rebuild skeleton.

Rules:
- Start from immutable crawl HTML.
- Do NOT rewrite /_next/static inside RSC flight payloads.
- Media URL rewrite must never consume trailing backslash escapes.
- Inject helpers only as a standalone script before </body>.
"""
from __future__ import annotations

import re
import subprocess
import tempfile
import urllib.parse
from pathlib import Path

SITE = Path(__file__).resolve().parent / "site"
CRAWL_PAGES = Path(__file__).resolve().parent.parent / "crawl-pages"  # adjust

# Only URL body chars. Never include \\ so flight escapes stay intact.
REMOTE_MEDIA_RE = re.compile(
    r"https://(?:www\.datocms-assets\.com|stream\.mux\.com|image\.mux\.com|cdn\.example\.com)/[A-Za-z0-9_./%-]+"
)

OFFLINE_BOOT = """
<script>
(function(){
  // Hydration-safe: avoid mutating text nodes during React hydrate window.
  try { document.documentElement.classList.add('local-mirror-offline'); } catch (e) {}
  function hideStuckLoader(){
    try {
      Array.from(document.querySelectorAll('body *')).forEach(function(el){
        var t = (el.textContent || '').trim();
        if (!(t === '0%' || /^\\d+%$/.test(t) || t.toLowerCase() === 'loading')) return;
        var p = el;
        for (var i = 0; i < 8 && p; i++) {
          var st = window.getComputedStyle(p);
          var zh = parseInt(st.zIndex || '0', 10);
          if ((st.position === 'fixed' || st.position === 'absolute') &&
              (zh > 5 || p.clientHeight > window.innerHeight * 0.4)) {
            p.style.opacity = '0';
            p.style.pointerEvents = 'none';
            break;
          }
          p = p.parentElement;
        }
      });
    } catch (e) {}
  }
  setTimeout(hideStuckLoader, 4000);
  setTimeout(hideStuckLoader, 7000);
})();
</script>
"""


def build_media_map() -> dict[str, str]:
    media: dict[str, str] = {}
    assets = SITE / "assets"
    if not assets.exists():
        return media
    for f in assets.rglob("*"):
        if not f.is_file():
            continue
        if f.suffix.lower() not in {
            ".jpg",
            ".jpeg",
            ".png",
            ".webp",
            ".avif",
            ".svg",
            ".gif",
            ".mp4",
            ".webm",
        }:
            continue
        rel = f.relative_to(SITE)
        enc = "/" + "/".join(
            urllib.parse.quote(urllib.parse.unquote(p), safe="@$&+,:=-._~()")
            for p in rel.parts
        )
        media[f.name] = enc
        parts = rel.parts
        # assets/{media|mux|other}/host/rest
        if len(parts) >= 4 and parts[1] in {"media", "mux", "other", "cdn"}:
            host = parts[2]
            rest = "/".join(parts[3:])
            media[f"https://{host}/{rest}"] = enc
    return media


def resolve_media(url: str, media: dict[str, str]) -> str | None:
    base = url.split("?")[0]
    if base in media:
        return media[base]
    fname = urllib.parse.unquote(base).split("/")[-1]
    return media.get(fname)


def check_inline_scripts(html: str) -> list[str]:
    fails: list[str] = []
    scripts = re.findall(r"<script(?![^>]*\bsrc=)([^>]*)>([\s\S]*?)</script>", html)
    for i, (_attrs, body) in enumerate(scripts):
        body = body.strip()
        if not body:
            continue
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
            fh.write(body)
            path = fh.name
        try:
            p = subprocess.run(["node", "--check", path], capture_output=True, text=True)
            if p.returncode != 0:
                fails.append(f"inline#{i}: {(p.stderr or p.stdout)[:200]}")
        finally:
            Path(path).unlink(missing_ok=True)
    return fails


def rewrite_html(html: str, media: dict[str, str]) -> str:
    def media_sub(m: re.Match[str]) -> str:
        local = resolve_media(m.group(0), media)
        return local if local else m.group(0)

    # Media only. Leave /_next/static untouched for server shim.
    html = REMOTE_MEDIA_RE.sub(media_sub, html)

    if "</body>" in html and "local-mirror-offline" not in html:
        html = html.replace("</body>", OFFLINE_BOOT + "\n</body>", 1)
    return html


def main() -> int:
    media = build_media_map()
    # Example mapping: adjust to your crawl layout
    pairs: list[tuple[Path, Path]] = []
    home = CRAWL_PAGES / "index.html"
    if home.exists():
        pairs.append((home, SITE / "index.html"))

    print(f"media_keys={len(media)} pages={len(pairs)}")
    bad = 0
    for src, dest in pairs:
        out = rewrite_html(src.read_text("utf-8", errors="replace"), media)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(out, encoding="utf-8")
        fails = check_inline_scripts(out)
        print(("OK" if not fails else "BAD"), dest, "inline_fail", len(fails))
        bad += len(fails)
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
