# UI Styling Patterns

Use this reference for implementation-facing cleanup.

## Layout patterns

- Use one consistent container strategy per surface.
- Keep section spacing larger than intra-component spacing.
- Let dense dashboards use tighter rhythms than marketing pages.
- On mobile, collapse complexity before shrinking everything.

## Card and panel rules

- Cards should represent a meaningful grouping, not just decoration.
- Use either elevation-driven grouping or border-driven grouping, not both everywhere.
- Keep padding and heading treatment consistent across sibling panels.

## Typography patterns

- Use a clear title, section, body, metadata hierarchy.
- Let weight and spacing create structure before adding more color.
- Use tabular numerals for metrics and data-heavy tables when alignment matters.

## Form patterns

- Keep labels persistent.
- Put errors near the field.
- Differentiate disabled, read-only, and loading.
- Use helper text for inputs that require precision or formatting.

## Navigation patterns

- Top-level navigation should be easy to scan and hard to misread.
- Secondary actions should not visually compete with the primary route.
- Back behavior, tabs, drawers, and breadcrumbs should match the product depth.

## Data and dashboard patterns

- Reserve the loudest colors for states that truly matter.
- Do not make every chart a hero.
- Use whitespace and ordering to show what needs attention first.
- Keep filters, sorting, and bulk actions visually grouped.

## Theming rule

If dark mode exists, design it intentionally.

- Do not invert everything.
- Re-check contrast.
- Soften saturation where needed.
- Keep shadows, borders, and overlays believable in both themes.
