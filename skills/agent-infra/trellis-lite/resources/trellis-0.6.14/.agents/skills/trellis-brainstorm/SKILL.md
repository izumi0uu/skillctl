---
name: trellis-brainstorm
description: "Clarify only the product decisions that block implementation, reuse the correct Trellis task, and keep planning artifacts minimal. Use when requirements or scope are genuinely ambiguous."
---

# Trellis Lite Brainstorm

Use this skill to remove ambiguity, not to exhaust every possible design branch.

## Rules

1. Inspect code, tests, docs, existing tasks, and specs before asking the user.
2. Ask only about product intent, scope, risk, or trade-offs the repository cannot answer.
3. Prefer one short batch of tightly related questions. Ask one question only when later questions depend on its answer.
4. Include a recommended answer and the material trade-off.
5. Stop as soon as the requested outcome has testable acceptance criteria.
6. Do not expand the task with adjacent defects, release work, cleanup, or speculative flexibility.
7. When repository investigation is substantial and independently bounded,
   dispatch one `trellis-research` agent by default after selecting the durable
   task. Before task selection, research only enough in the main session to route
   the request. Do not delegate product choices, dispatch multiple speculative
   researchers, or allow nested workers.

## Task Routing

```bash
python3 ./.trellis/scripts/task.py current --source
python3 ./.trellis/scripts/task.py list
```

- Reuse one clear unarchived match with `task.py use <task>`.
- Ask which task to use when several match.
- Create only a materially different durable deliverable, after consent.
- Skip Trellis for small work that does not need durable planning.
- On OMP, use the `ask` tool only when an actual user choice remains.

## Minimum Planning Artifact

Most work needs only a concise `prd.md` containing:

- goal and user-visible result;
- acceptance criteria;
- important constraints;
- non-goals and deferred findings;
- genuinely blocking open questions.

Add `design.md` only for durable architecture, compatibility, migration, security,
or rollback decisions. Add `implement.md` only when ordering, ownership, or
multiple independently verifiable slices need to survive handoff.

JSONL manifests are optional. When delegation needs them, include only files
under `.trellis/spec/` or the active task's `research/` directory. Never include
product source, generated output, or large tests.

## Convergence

Before implementation:

- remove duplicated and superseded material;
- delete obsolete requirements and acceptance criteria;
- move adjacent findings outside the accepted outcome to follow-ups;
- keep only evidence needed to understand a current decision;
- confirm the remaining criteria can be verified proportionally.

Planning is not lossless archival. Git history, task research, and session logs
already preserve history; the current PRD should describe the current contract.

Do not start implementation until the user asks for it or approves the minimum
scope when approval is genuinely needed.
