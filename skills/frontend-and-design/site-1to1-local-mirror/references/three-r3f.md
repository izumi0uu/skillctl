# Three.js / React Three Fiber mount guide

## Detection

Search local JS for:
- `WebGLRenderer`, `ShaderMaterial`, `VideoTexture`
- `@react-three/fiber`, `useFrame`
- Custom GLSL (`fragmentShader`, `barrel`, `uScrollVelocity`)

## Mount success signals (Target R)

Any strong signal:
- Canvas buffer significantly larger than default `300×150`
- WebGL `drawingBufferWidth/Height` active
- Hidden/real `video` elements created for `VideoTexture` with `readyState >= 2`
- Console shows THREE runtime warnings (Clock deprecation etc.) without SyntaxError

Failure signals:
- `videoCount === 0` while chunk contains VideoTexture setup
- Canvas remains 300×150 after several seconds
- SyntaxError in console

## Common public asset holes after hydration

Fetch from origin into same paths:
- `/models/*.glb`
- `/textures/*` (including `.ktx2`)
- `/draco/draco_decoder.js`, `draco_decoder.wasm`, `draco_wasm_wrapper.js`
- `/images/*` UI chrome used by scene/UI

## Path A vs Path B

- **Path A:** make original compiled chunks run (preferred)
- **Path B:** extract GLSL/uniforms/media inputs and rebuild a minimal local scene

Only escalate to B after A has clean syntax + assets and still cannot mount.
