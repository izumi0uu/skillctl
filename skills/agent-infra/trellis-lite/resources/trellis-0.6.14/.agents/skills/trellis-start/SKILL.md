---
name: trellis-start
description: "Load compact Trellis context and route work using the project's lite workflow. Use at session start or when task state needs to be re-established."
---

# Start Trellis Lite Session

## Load Compact Context

```bash
python3 ./.trellis/scripts/get_context.py
python3 ./.trellis/scripts/get_context.py --mode phase
```

Read only the spec indexes relevant to the user's request. Do not preload every
spec or task artifact.

## Route The Request

- Small question or isolated change: skip Trellis and proceed normally.
- One clear matching task: select it with `task.py use` and preserve its status.
- Several plausible tasks: ask which one owns the work.
- No match but durable planning/handoff is useful: ask before creating a task.
- `planning`: produce the minimum testable PRD; design/implement artifacts are optional.
- `in_progress`: resume the next incomplete requested item. Never infer that all
  implementation or verification must restart.

## Lite Defaults

- Small work stays in the main session.
- Normal tracked work: main implementation, then one report-only check agent.
- Complex separable work: parallel implement agents with disjoint ownership,
  main-session integration, then one report-only check agent.
- Unclear requirements: one bounded research agent when repository evidence can
  resolve the uncertainty and a durable task is active; product decisions remain
  with the main session/user.
- Sub-agents never dispatch nested workers.
- Only the main agent dispatches; every prompt names the active task, exact
  acceptance slice, and non-overlapping file or module ownership.
- Verify once, proportionally to risk.
- Reuse passing results while relevant code is unchanged.
- Checker findings end the pass; correction or recheck needs an explicit user follow-up.
- Spec update, commit, archive, release, and publication are explicit actions.

Read `.trellis/workflow.md` when detailed routing is needed.
