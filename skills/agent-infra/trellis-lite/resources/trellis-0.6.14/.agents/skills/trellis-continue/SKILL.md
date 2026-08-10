---
name: trellis-continue
description: "Resume the next incomplete item in an existing Trellis task without restarting completed implementation or verification."
---

# Continue Trellis Lite Task

## Load State

```bash
python3 ./.trellis/scripts/get_context.py
```

If no task is selected, list unarchived tasks and reuse one clear match. Do not
create a task implicitly. If none matches, report that there is no resumable task.

Read the selected task's `task.json`, `prd.md`, and only the optional artifacts
needed to identify the next incomplete requested item. Inspect the current diff
and recent worker reports before deciding that work is missing.

## Resume Rules

- `planning`: resolve only blocking scope decisions, then request start approval.
- `in_progress`: continue the next incomplete acceptance criterion or explicit
  implementation-plan checkbox.
- Do not restart completed code, re-dispatch completed workers, or rerun passing
  checks while relevant code is unchanged.
- Small work stays in the main session. For normal tracked work, implement in
  the main session and then dispatch one report-only checker. For complex
  separable work, parallel implementers require disjoint ownership; integrate
  once, then dispatch one report-only checker.
- If requirements are unclear, use one bounded research agent when repository
  evidence can resolve them; do not delegate product choices.
- Only the main agent dispatches. Every worker prompt names the active task,
  exact scope, and non-overlapping file or module ownership.
- If implementation is complete and no proportional verification has run,
  dispatch the single checker now. Never dispatch nested workers or a second
  verification wave.
- If a required check failed, report it and stop. A correction or recheck is a
  separate main-session follow-up that requires explicit user authorization.
- If implementation and verification are complete, report the outcome. Spec
  update, commit, archive, release, and publication require explicit intent.

The word `continue` authorizes only the next incomplete item inside the accepted
scope. It does not authorize scope expansion or a fresh workflow cycle.
