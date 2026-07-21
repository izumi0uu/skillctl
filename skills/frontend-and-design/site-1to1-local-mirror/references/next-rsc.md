# Next.js / RSC / Turbopack tactics

## What ships on the publish surface

- HTML with inline `self.__next_f.push(...)` flight payloads
- `/_next/static/chunks/*` JS/CSS
- Optional `/_next/image?url=...` optimizer URLs
- Deploy query strings like `?dpl=...`

## Safe local strategy

1. **Serve `/_next/static/*` via basename shim**
   Map `.../chunks/foo.js` → local file by `foo.js`, ignore `?dpl=`.
2. **Do not rewrite `/_next/static` inside flight strings**
   Those strings are nested JS string literals with `\"` escapes.
3. **Rewrite remote media carefully**
   Use URL-safe charset only. Never let regex include `\`.
4. **`/_next/image`**
   Either shim to local media by filename/host path, or rewrite only in HTML attributes after escape-safe analysis.

## Validation order

1. External chunk `node --check` (usually already fine)
2. **Inline script** `node --check` (this catches flight corruption)
3. Browser console for SyntaxError
4. Only then evaluate hydration/effects

## Signals of corruption

Broken flight often looks like:
```js
// bad: unescaped quote ends outer string
self.__next_f.push([1,"...[\"/assets/js/.../foo.js","/assets/..."])

// good: escapes preserved
self.__next_f.push([1,"...[\"/_next/static/chunks/foo.js?dpl=...\",\"/_next/..."])
```
