---
name: ui-ux-pro-max
description: Portable UI and UX review system for web and app interfaces. Use when designing new pages, choosing product style direction, tightening design systems, reviewing interaction quality, improving responsive layouts, checking accessibility and performance basics, or upgrading a rough interface into a more intentional product experience. Best for landing pages, dashboards, SaaS tools, mobile flows, forms, navigation, cards, tables, charts, and design-system decisions.
---

# UI UX Pro Max

Use this skill as a design decision router and review ladder, not as a giant dataset dump.

It is most useful when the user wants one of these outcomes:

- choose a coherent visual direction before implementation
- review an existing UI and identify the highest-impact fixes
- improve a page that feels generic, sloppy, or inconsistent
- define a lightweight design-system direction before building components
- sanity-check interaction, accessibility, responsive behavior, and motion

## Operating workflow

Follow this sequence:

1. Identify the surface.
   - landing page
   - dashboard or app shell
   - form-heavy workflow
   - content page
   - settings or admin area
   - mobile flow

2. Identify the real bottleneck.
   - weak hierarchy
   - weak visual identity
   - poor spacing rhythm
   - inconsistent tokens
   - confusing interaction states
   - responsiveness issues
   - accessibility gaps
   - too much decorative motion

3. Run the priority ladder first.
   - Read `references/priority-review.md`.
   - Fix the highest-severity issues before touching polish.

4. If the user needs a style direction, choose one intentionally.
   - Read `references/product-style-selection.md`.
   - Match style to product trust level, audience, and usage pattern.

5. If the user is building or refactoring a system, route through token thinking.
   - Read `references/design-system-routing.md`.
   - Prefer semantic tokens and repeatable component rules over one-off visual tweaks.

6. If the work is implementation-facing, apply component and layout guidance.
   - Read `references/ui-styling-patterns.md`.
   - Keep states, spacing, density, and responsive behavior consistent.

7. If motion or touch behavior matters, check interaction quality last.
   - Read `references/interaction-and-motion.md`.
   - Motion should clarify state, not decorate emptiness.

## Review ladder

Always review in this order:

1. Accessibility and readability
2. Interaction clarity and touch safety
3. Layout and responsive behavior
4. Information hierarchy
5. Visual system consistency
6. Performance-sensitive UI choices
7. Motion and polish

Do not start with gradients, shadows, or trendy visual effects if the interface is still failing at the first four levels.

## Decision rules

- Prefer one strong visual idea over many weak ones.
- Prefer semantic color and spacing tokens over hardcoded per-component values.
- Prefer consistent component states over individually styled buttons and cards.
- Prefer responsive simplification on small screens over squeezing everything in.
- Prefer obvious navigation and labels over cleverness.
- Prefer honest placeholders over fake polished content.
- Prefer reduced decorative complexity when the product needs trust, speed, or clarity.

## Anti-slop guardrails

- Do not default to purple gradients, glass cards, or vague SaaS hero sections.
- Do not mix multiple visual languages without a reason.
- Do not rely on color alone to communicate state.
- Do not hide primary actions inside weak contrast or overloaded toolbars.
- Do not add animation before the structure is working.
- Do not treat accessibility as a final QA pass only.

## Reference routing

- Use `references/priority-review.md` for triage and review order.
- Use `references/product-style-selection.md` when the user needs a visual direction.
- Use `references/design-system-routing.md` for tokens, components, and system rules.
- Use `references/ui-styling-patterns.md` for implementation-facing UI patterns.
- Use `references/interaction-and-motion.md` for touch, motion, feedback, and state changes.

## Output expectations

When using this skill, prefer outputs like:

- a ranked UI review with the top fixes first
- a proposed design direction with rationale
- a small design-system starter spec
- a component/state cleanup plan
- a responsive or interaction QA checklist

Keep recommendations concrete. Name exactly what to change and why it matters.

<!-- skillctl:source-attribution:start -->
## Source Attribution

- origin kind: derived-from-upstream
- upstream repo: nextlevelbuilder/ui-ux-pro-max-skill
- upstream path: .claude/skills/ui-ux-pro-max
- pinned ref: b7e3af80f6e331f6fb456667b82b12cade7c9d35
- source type: github
- source URL: https://github.com/nextlevelbuilder/ui-ux-pro-max-skill/tree/main/.claude/skills/ui-ux-pro-max
- imported at: 2026-06-14T14:45:55.384Z
- last verified ref: b7e3af80f6e331f6fb456667b82b12cade7c9d35
- local modifications: true
<!-- skillctl:source-attribution:end -->
