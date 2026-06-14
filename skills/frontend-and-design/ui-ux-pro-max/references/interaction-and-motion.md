# Interaction And Motion

Use this reference when behavior, feedback, or polish is part of the ask.

## Touch and pointer basics

- Interactive targets should be comfortably tappable.
- Adjacent destructive and primary actions need extra separation.
- Hover states can enrich desktop UIs but must not be required for comprehension.

## State feedback

Always show:

- press or hover response
- loading response
- success or completion feedback
- clear error recovery path

Users should never wonder whether an action registered.

## Motion principles

- Motion should explain what changed.
- Keep micro-interactions short and responsive.
- Use transform and opacity before layout-affecting animation.
- Respect reduced-motion preferences.

## Good motion jobs

- entering and exiting overlays
- expanding and collapsing regions
- confirming a pressed action
- preserving continuity between two related states

## Bad motion jobs

- decorating otherwise weak layouts
- hiding slow performance
- making dense tools feel heavier
- animating every element equally

## Practical thresholds

- Fast feedback is more important than theatrical feedback.
- Exit motion should usually feel faster than enter motion.
- Repeated-use tools should have less motion than storytelling surfaces.

## Mobile caution

On mobile, prioritize:

- gesture clarity
- obvious dismissal paths
- no accidental edge conflicts
- no motion that disrupts reading or causes disorientation
