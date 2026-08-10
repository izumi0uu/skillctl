---
name: trellis-check
description: "Run one proportional, scope-bounded read-only review after implementation. Reports findings and never edits or starts a fix/re-check loop."
---

# Trellis Lite Check

Use once after the requested implementation slice is complete, or when the user
explicitly asks for review.

The checker is a read-only evidence reviewer. The main session or implementer
owns commands that can change files, tests, task state, or release state.

## Scope

1. Read the current requested acceptance criteria.
2. Inspect only the relevant diff and directly affected code paths.
3. Do not treat unrelated dirty files, parent-epic criteria, release work, or
   newly discovered adjacent defects as part of this check.
4. Reuse exact passing results from implementers while relevant code is unchanged.

## Review Selection

- Inspect the relevant diff, acceptance criteria, and exact checks already
  reported by the main session or implementer.
- Read omitted or truncated task/spec entries from disk before relying on them.
- Use only the read-only inspection tools available to this agent. Do not run
  tests, builds, scripts, or shell commands from the checker.

## Findings

Report findings with severity, evidence, and scope. Never edit files or invoke
write-capable tools. Never change task/spec/session state, commit, finish,
archive, or dispatch another worker. In particular, never run `task.py finish`,
`task.py archive`, `task.py start`, `task.py use`, or equivalent lifecycle
commands. Findings end this pass; a correction or recheck is an explicit
main-session follow-up.

## Output

- Findings, or an explicit statement that none were found.
- Exact evidence inspected and checks reported by the implementation session.
- Verification commands intentionally skipped because this agent is read-only.
- Remaining blocker or deferred follow-up.
