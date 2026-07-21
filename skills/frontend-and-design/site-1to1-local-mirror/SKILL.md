---
name: site-1to1-local-mirror
description: "Reverse-engineer public website publish surfaces into runnable local 1:1 mirrors. Use for crawl-to-local clones, Webflow/Next visual parity, offline browse packages, stuck loaders, missing Three.js/R3F interactions, Mux/DatoCMS media localization, and diagnosing semi-finished local sites. Triggers: '1:1 local mirror', 'reverse engineer this site', 'clone site locally', 'why three.js not running', 'local offline site', 'webflow/next local package', 'Target A visual clone'."
---

# Site 1:1 Local Mirror

Build a **runnable local package** from a site's public publish surface — not a CMS admin clone, not a clean source rewrite by default.

This skill encodes lessons from multi-site reverse engineering (static/Webflow shells and hard Next.js + Mux + Three/R3F cases), including failures where assets looked complete but runtime effects were dead.

## Non-goals

- Reconstruct private CMS backends, auth walls, or paid content
- Claim full source-code recovery of Next/React apps
- Fully offline every adaptive streaming CDN by default
- "Looks open" without runtime proof when the user wants interactions

## Target contract (choose before editing)

| Target | Meaning | Done when |
|---|---|---|
| **A — Visual browseable** | Routes + CSS/JS chrome + still media local enough to browse | Main paths render; no hard broken layout |
| **A+ — Media** | A + progressive video/audio local | Key `<video>`/posters local 200/206 |
| **R — Runtime effects** | A/A+ + client interactions really run (Three/R3F/GSAP scenes) | Browser proof: no SyntaxError; canvas/video/WebGL mount signals |
| **S — Source-level** | Readable app rewrite | Explicit only; Path B fallback |

If the user says "互动 / threejs / 特效 / 半成品没动效", default to **Target R**, not A.

## Hard rules

1. **Publish surface only** unless user expands scope.
2. **Write a Target contract first** (A / A+ / R).
3. **Keep an immutable crawl original.** All rebuilds start from crawl, never from repeatedly patched broken HTML.
4. **Prefer server shims over rewriting framework runtime paths** (`/_next/static`, `/_next/image`).
5. **Never naive-replace inside RSC flight / `self.__next_f` strings.** Escapes (`\"`) are sacred.
6. **Two gates required:** static syntax gate + browser runtime gate.
7. **Loader failsafe ≠ success.** Hiding `0%` is not proof that Three/R3F mounted.
8. **Path A before Path B:** make compiled client runtime run first; only then extract shaders and rewrite a clean scene.

## Canonical case study (do not relearn the hard way)

### Failure mode: "assets 200, effects dead"

Symptoms:
- External JS chunks all `200` and `node --check` pass
- Console: `Uncaught SyntaxError: Invalid or unexpected token` on **inline** scripts
- Canvas stuck at default `300×150`
- `document.querySelectorAll('video').length === 0`

Root cause pattern:
- Naive rewrite of `/_next/static/chunks/...` inside RSC flight payloads
- Regex consumed trailing escape backslash before `"`
- Outer JS string terminated early → React hydration never started → R3F/Three never mounted

Fix pattern:
1. Rebuild HTML from crawl original
2. Leave `/_next/static` bare in flight; serve via server basename shim
3. Media rewrites must match only URL characters (`[A-Za-z0-9_./%-]+`), never `\`
4. `node --check` every inline script before browser claims
5. Browser-verify canvas size + video nodes

## Workflow

### 0) Intake

Collect:
- URL(s)
- Target: A / A+ / R
- Scope: whole site vs main publish surface only
- Offline purity requirement (strict offline vs LAN with residual social links OK)

Create package roots:
```text
{site}-1to1/     # immutable crawl
{site}-local/    # runnable package
  site/
  server.py
  rebuild_*.py
  accept_*.py
  meta/
```

### 1) Stack fingerprint

Detect and write `meta/stack.md`:
- Generator: Webflow / Next(RSC,Turbopack) / Nuxt / plain static
- Media: Mux / DatoCMS / Cloudinary / self-host
- Motion: Three / R3F / GSAP / Lenis / Lottie / custom

Route tactics:
- **Webflow/static** → attribute rewrites + asset mirror usually enough for A/A+
- **Next/RSC** → shim `/_next/*`; extreme caution on flight payloads; Target R needs browser gate
- **Three/R3F present** → plan models/textures/draco/image chrome assets early

### 2) Crawl publish surface

- Sitemap + internal links for HTML
- CSS/JS chunks referenced by pages
- Still images and progressive media URLs
- Do **not** discard original HTML after localization attempts

Suggested layout:
```text
{site}-1to1/
  pages/**.html
  assets/**
  meta/crawl-log.json
```

### 3) Local server first

Use or adapt `templates/server.py`:
- Serve `site/` root
- Basename resolve for `/_next/static/*` (strip query like `?dpl=`)
- `/_next/image?url=` → local media by filename/host path
- Range requests for mp4/webm/woff2
- Correct MIME types
- Tolerate BrokenPipe on cancelled media

Do not claim progress until home HTML returns 200 from this server.

### 4) Safe rewrite / rebuild

Use or adapt `templates/rebuild_html.py` principles:

**Allowed**
- Rewrite remote media absolute URLs → local `/assets/...`
- Rewrite HTML tag attributes carefully
- Inject a **standalone** offline/helper script before `</body>`

**Forbidden / high-risk**
- Global replace of `/_next/static` across whole HTML text
- Any replace that can consume trailing `\` in `\"...\"` flight strings
- Mutating visible text nodes during React hydration window (causes React #418)

If local HTML is already corrupted: **delete and rebuild from crawl**, do not stack more patches.

### 5) Static gate (must pass)

Run `templates/accept_static.py` or equivalent:
- All routes 200
- All inline scripts `node --check` PASS
- External critical chunks 200
- Optional: zero absolute remote media hosts (except allowed socials)

If inline syntax fails → stop; fix rebuild. Do not open browser and guess.

### 6) Browser runtime gate (required for Target R)

Using Chrome DevTools MCP / Playwright / manual DevTools:
1. Hard reload home
2. Console: no `SyntaxError`
3. Mount signals (any strong signal counts):
   - `canvas` width/height ≫ 300×150 and WebGL drawing buffer active, and/or
   - `video` nodes created for VideoTexture pipelines with `readyState >= 2`
4. Network: no hard 404 loop on scene assets
5. Interaction smoke: scroll/pointer produces visible response when original has it
6. Save screenshot + `meta/acceptance.json`

### 7) Asset hole-filling for 3D / motion

After hydration works, console 404s become the backlog:
- `/models/*.glb`
- `/textures/*` (incl `.ktx2`)
- `/draco/*`
- UI chrome `/images/*`

Fetch from origin public URLs into `site/` preserving path. Re-test mount.

### 8) Path B only if Path A fails cleanly

If SyntaxError is gone, chunks load, assets exist, but scene still cannot mount:
1. Extract GLSL/uniforms/video inputs from minified chunks
2. Rebuild a minimal local Three/R3F scene with local media
3. Label result as **behavioral approximation**, not claim of original source recovery

## Failure playbooks

Read `references/failure-playbooks.md` for F1–F5.

Quick map:
- Semi-finished shell / 0% forever → Target confusion or loader failsafe; re-gate A vs R
- Double path prefix / mass 404 → bad rewrite; rebuild from crawl
- Inline SyntaxError, dead Three → flight escape corruption; rebuild + shim
- Hydrated but black scene → missing glb/ktx2/draco/images
- Irreparable runtime → Path B shader extract

## Package outputs

When finished, report:
- Target chosen and whether met
- Local run command (`python3 server.py`, port)
- What is local vs residual remote
- Acceptance evidence paths
- Known gaps (adaptive streams, social links, Path B leftovers)

Suggested acceptance JSON fields:
```json
{
  "target": "R",
  "pass": true,
  "routes_ok": 9,
  "inline_script_syntax": "pass",
  "console_syntax_error": false,
  "canvas": {"w": 2850, "h": 1400},
  "videos_ready": 27,
  "remote_media_left": 0,
  "notes": []
}
```

## Templates

- `templates/server.py` — local static server with Next shims + Range
- `templates/rebuild_html.py` — crawl→local rebuild with escape-safe media rewrite
- `templates/accept_static.py` — route/shim/inline-syntax gate

## References

- `references/next-rsc.md` — Next/RSC/Turbopack tactics
- `references/three-r3f.md` — Three/R3F mount signals and asset lists
- `references/failure-playbooks.md` — F1–F5 detailed recovery

## Decision tree

```text
Stack?
  Webflow/static → A/A+ attribute rewrite + mirror
  Next/RSC → shim /_next; never naive flight rewrite

User wants interactions/Three?
  No  → stop at A/A+ static+browser smoke
  Yes → Target R
        Static inline syntax gate
        Browser gate
        If SyntaxError → rebuild from crawl (F3)
        If 404 scene assets → fill holes (F4)
        If still dead after clean hydration → Path B (F5)
```

## Success condition

Task is complete only when the chosen Target's gates pass with evidence:
- A/A+: routes + assets + no critical broken chrome
- R: above + runtime mount signals + no blocking SyntaxError

Do not call a local mirror "perfect reverse engineering" if only static assets exist and client runtime never mounted.
