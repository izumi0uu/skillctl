# Design System Routing

Use this reference when the task needs more than one-off page cleanup.

## Start with tokens

Prefer a three-layer model:

1. Primitive values
   - raw colors
   - type sizes
   - spacing steps
   - radius values
   - shadow levels

2. Semantic tokens
   - `color-primary`
   - `surface-muted`
   - `text-secondary`
   - `space-section`
   - `radius-card`

3. Component tokens or rules
   - button primary background
   - card border treatment
   - input focus ring
   - modal elevation

## When to systematize

Route into system work when you see:

- repeated hardcoded hex values
- inconsistent spacing between similar sections
- multiple button styles with unclear ownership
- cards, tables, and forms that feel like unrelated mini-designs

## Minimum starter spec

For lightweight systemization, define:

- 1 typography scale
- 1 spacing scale
- 1 surface hierarchy
- 1 border-radius policy
- 1 elevation or border policy
- 1 component state model for button, input, card, and modal

## Component state checklist

For each reusable component, define:

- default
- hover
- pressed
- focus
- disabled
- error or destructive, when relevant

If the component appears in multiple contexts, keep the logic the same and vary only what must change.

## Implementation rule

When refactoring code, prefer:

- shared tokens
- shared primitives
- small variant systems

Avoid:

- component-specific magic numbers
- one-off overrides for every screen
- state styling that exists only in CSS comments or visual memory
