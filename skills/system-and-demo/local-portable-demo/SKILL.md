---
name: local-portable-demo
description: Minimal public-safe demo skill for validating the skillctl portable catalog, sync, and doctor flows.
---

# Local Portable Demo

Use this skill when you want a tiny managed skill that is safe to commit publicly and useful for smoke-testing a multi-agent skill distribution pipeline.

## Workflow

1. Confirm the destination agent can see `SKILL.md`.
2. Read the frontmatter name and description.
3. Return the single line: `local-portable-demo loaded`.
