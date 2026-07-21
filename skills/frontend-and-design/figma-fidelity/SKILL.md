---
name: figma-fidelity
description: Use when implementing, correcting, or reviewing UI against a Figma reference where visual fidelity matters. Requires the exact Figma node, real-component rendering, computed-style and bounding-box checks, UI-library precedence inspection, and separate interaction proof. Prevents parent-frame guesses, asset-only inference, and simplified mock harnesses from being accepted as visual evidence.
metadata:
  short-description: Match Figma with real-component evidence
---

# Figma Fidelity

Deliver Figma-driven UI changes from evidence, not approximation.

This skill applies to focused component fixes and larger Figma implementations. It is intentionally lighter than a durable visual-baseline workflow: no task system or pixel-diff dependency is required. The invariant is that visual acceptance must come from the exact reference node and the real rendered component.

## Use This Skill When

- implementing a component or page from a Figma URL
- correcting spacing, alignment, dimensions, color, radius, typography, or icon placement
- reviewing whether an existing implementation matches Figma
- diagnosing “looks close but not aligned” feedback
- a component library such as Ant Design, Material UI, Chakra, shadcn, or Bootstrap may override local CSS

Do not use it for design ideation without an accepted reference, backend-only work, or behavior-only testing.

## Non-Negotiable Evidence Rules

1. **Exact node, not nearby context.** Record the Figma file key and exact node ID. A page, dashboard frame, parent section, or visually similar sibling is not sufficient when a more specific component node exists.
2. **No inference after reference failure.** If Figma access fails, stop visual claims. Repair or reload credentials, use an authorized browser view of the exact node, or ask for a screenshot/export of that node. An icon asset alone does not define its container, offset, background, or alignment.
3. **Render the real component.** Visual evidence must use the production component and its actual UI-library styles. A simplified lookalike, static HTML copy, or custom mock button may test a concept but cannot prove implementation fidelity.
4. **Inspect computed output.** Source classes are intent; `getComputedStyle()` and `getBoundingClientRect()` are browser truth. Check them whenever alignment or CSS precedence is involved.
5. **Visual and behavioral proof are separate.** A click test proves interaction. A screenshot and geometry check prove appearance. Neither substitutes for the other.

## Workflow

### 1. Establish Reference Identity

From the Figma URL, capture:

- file key
- exact node ID
- node name or visible component identity
- relevant state or variant
- viewport or frame context

Confirm that the selected node visibly contains the target control. If the target is only visible inside a child node, navigate to that child before implementing.

If the user supplied a new node after work began, invalidate conclusions drawn from the old node and restart the reference inspection.

### 2. Acquire Reference Evidence

Prefer structured Figma data when available. Extract only the target component and relevant ancestors:

- width and height
- x/y relationship to the containing frame
- padding and gaps
- fill, stroke, opacity, and radius
- typography
- icon/vector dimensions
- auto-layout alignment and constraints
- visible interaction state

Also capture a screenshot of the exact node or pan/zoom the authorized Figma canvas until the target is legible.

If structured access returns an authentication or permission error:

1. verify the configured credential source without printing the secret
2. reload the MCP/tool process if configuration changed after process startup
3. retry the exact node once
4. fall back to an authorized browser view of the exact node
5. if neither path exposes the target clearly, report the reference blocker instead of guessing

### 3. Inspect The Existing Implementation

Before editing:

- locate the real component and rendered route/state
- identify the UI library and existing component primitives
- inspect imported SVGs/images and their intrinsic dimensions
- identify layout ancestors that establish positioning context
- inspect existing tests for behavior contracts
- preserve existing design-system and accessibility conventions

For exported symbols, inspect references before changing their public contract.

### 4. Write A Mismatch Ledger

Keep a short working ledger:

| Property | Figma evidence | Rendered evidence | Decision |
| --- | --- | --- | --- |
| node identity | exact node ID/name | route/component | match or blocker |
| container | size/padding/radius | bounding box/computed style | fix or intentional deviation |
| control | width/height/background | bounding box/computed style | fix |
| icon | intrinsic size/color | SVG box/computed color | fix |
| alignment | edge offsets/center line | measured offsets/centers | fix |

Do not fill unknown Figma values from memory. Mark them unknown until observed.

### 5. Make The Smallest Source Fix

Prefer existing components and assets. Change only properties proven mismatched.

When a UI library is involved:

- inspect the final `position`, dimensions, padding, margin, display, line-height, background, and transform
- check whether library selectors override utility classes
- use an important override only after computed styles prove precedence is the cause
- preserve focus visibility and an adequate hit target
- avoid replacing a library component with raw HTML solely to win CSS specificity

Do not broaden a local alignment fix into a design-system rewrite.

### 6. Render The Real Component

Use the normal application route when practical.

If authentication, backend data, or navigation blocks a focused component check, create a temporary browser-only harness that imports the **actual component** and actual UI library. The harness may provide deterministic props, form context, providers, or mocked network responses.

A valid fidelity harness:

- imports the production component
- uses the same React/runtime instance as the application
- loads production CSS and UI-library styles
- supplies realistic layout context
- mocks only external data or providers
- is not committed unless the repository already has a component-preview convention

An invalid fidelity harness:

- redraws the component with custom HTML
- replaces the target button/control with a simpler stand-in
- uses different spacing or wrapper structure
- proves only text presence or element counts

Behavior-only mocks remain useful, but label them behavior evidence—not visual evidence.

### 7. Measure Browser Truth

For the target and its key reference elements, collect:

- `x`, `y`, `width`, `height`
- edge offsets from the containing component
- horizontal or vertical center lines
- computed `position`, `top/right/bottom/left`
- computed padding, margin, background, radius, opacity, and line-height when relevant
- icon SVG bounding box

Useful alignment calculations:

```text
horizontal center = x + width / 2
vertical center   = y + height / 2
right inset       = container.right - element.right
top inset         = element.top - container.top
```

A source class such as `absolute` is not evidence if the browser computes `position: relative`.

### 8. Compare And Iterate

After every visual edit:

1. wait for hot reload or reload the route
2. re-render the same state
3. recapture the screenshot
4. remeasure the same elements
5. compare against the mismatch ledger
6. make one bounded follow-up change if needed

Do not switch nodes, viewport, data state, zoom basis, or component wrapper during comparison without recording the change.

### 9. Verify Interaction Separately

Exercise the affected action after visual alignment:

- click or keyboard activation works
- state updates correctly
- minimum/maximum item rules remain intact
- focus remains visible
- destructive controls retain an accessible name

Run the smallest existing automated test that covers the changed behavior. Do not add a source-text or class-name test solely to lock CSS; browser evidence is the primary proof for visual changes.

## Completion Gate

Do not claim Figma fidelity until all are true:

- the exact Figma node is identified
- the target is legible in reference evidence
- the production component—not a lookalike—is rendered
- the final screenshot visibly supports the match
- key dimensions and alignment are measured from the browser
- computed styles confirm library overrides are resolved
- the relevant interaction still works
- lint/type diagnostics for touched files are clean
- any unavailable reference detail or intentional deviation is explicit

## Common Failure Modes

### Parent Frame Substitution

**Failure:** using a dashboard or modal parent node when the target control has its own node.

**Repair:** navigate to the exact child node and invalidate earlier measurements.

### Stale MCP Credentials

**Failure:** editing configuration while the running MCP process continues using old credentials.

**Repair:** reload the MCP process, retry the exact node, then use authorized browser evidence if necessary.

### Asset-Only Inference

**Failure:** treating a `16×16` trash SVG as proof that the button container is also `16×16`, transparent, or aligned a certain way.

**Repair:** inspect the node’s container, background, radius, inset, and alignment separately.

### Simplified Harness False Positive

**Failure:** a mock control behaves correctly, so the production control is declared visually correct.

**Repair:** render the real component with actual library CSS and deterministic external-data mocks.

### CSS Intent Versus Computed CSS

**Failure:** a utility class says `absolute`, while a library rule computes `position: relative`.

**Repair:** measure computed styles, identify the winning rule, and apply the narrowest override.

### Screenshot Without Geometry

**Failure:** a screenshot looks plausible at one scale but alignment is still off.

**Repair:** record bounding boxes, insets, and center lines for the target and its anchor element.

## Output

Report:

- exact Figma file/node used
- reference acquisition path and any fallback
- mismatch found
- source change made
- before/after computed geometry for the target
- real-component screenshot evidence
- interaction check
- lint/type/test result
- remaining unverified states or intentional deviations
