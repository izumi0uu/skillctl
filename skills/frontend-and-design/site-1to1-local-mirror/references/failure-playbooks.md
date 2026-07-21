# Failure Playbooks

## F1 — Semi-finished shell / stuck 0%

**Symptoms**
- Pages open, layout partially correct
- Loader stuck at `0%` or infinite loading chrome
- Videos remote or missing

**Diagnosis**
- Was Target A confused with Target R?
- Is loader failsafe hiding incomplete preload rather than fixing runtime?

**Fix**
1. Restate Target contract
2. Inventory local vs remote media
3. For A/A+: localize stills/progressive media; shim broken optimizer routes
4. For R: proceed to browser runtime gate; do not declare success on loader hide alone

## F2 — Double prefixes / mass asset 404

**Symptoms**
- Paths like `/assets/js/.../assets/js/...`
- `/_next/image` 404 storms
- CSS/JS request paths doubled after repeated rewrites

**Fix**
1. Stop patching current HTML
2. Rebuild from immutable crawl
3. Prefer server shims for framework paths
4. Attribute-level rewrites only where necessary

## F3 — Inline SyntaxError kills hydration (canonical hard case)

**Symptoms**
- External chunks `200` and `node --check` pass
- Console: `Uncaught SyntaxError: Invalid or unexpected token` (often multiple)
- Canvas default `300×150`
- `videoCount === 0` despite VideoTexture code existing in chunks

**Root cause pattern**
- Rewriting `/_next/static/...` inside `self.__next_f.push([1,"...\"..."])` flight strings
- Regex consumed trailing escape `\` before `"`
- Outer JS string terminated early

**Fix**
1. Compare crawl vs local flight snippet around first `I[<id>,[\"/_next/static`
2. Rebuild all HTML from crawl
3. Leave `/_next/static` paths for server shim
4. Media rewrite with URL-safe charset only (`[A-Za-z0-9_./%-]+`)
5. Gate: every inline script must `node --check` PASS
6. Browser: SyntaxError gone, then check mount signals

## F4 — Hydrated but scene assets missing

**Symptoms**
- No SyntaxError
- THREE warnings may appear
- 404 on `/models/*.glb`, `/textures/*`, `/draco/*`, `/images/*`
- Canvas may exist but black / incomplete

**Fix**
1. Collect console 404 list
2. Download public origin assets into same local paths
3. Ensure MIME + Range for media
4. Reload and re-check canvas dimensions / video readyState

## F5 — Path A exhausted → Path B approximation

**Symptoms**
- Clean hydration
- Assets present
- Still no stable interactive scene due to missing private runtime graph

**Fix**
1. Extract GLSL, uniforms, media inputs from minified chunks
2. Rebuild minimal Three/R3F scene with local media
3. Label as behavioral approximation
4. Do not claim original source recovery
