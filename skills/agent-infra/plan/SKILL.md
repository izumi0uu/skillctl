---
name: plan
description: Create or revise a right-sized, implementation-ready Plan Bundle without starting execution. Use when the user asks to plan, scope, decompose, or clarify a development task. The output is a neutral plan-bundle/v1 contract that does not depend on any task manager or orchestration runtime.
metadata:
  short-description: Create a portable implementation contract
---

# Plan

Produce the smallest neutral contract that makes implementation predictable.
This skill plans and writes one neutral plan artifact; it does not persist task
runtime state or execute the plan.

## Route The Request

- Answer simple questions directly.
- Skip planning for a focused edit whose scope and verification are obvious.
- Use this skill for ordinary multi-file or multi-step work.
- Use `$ralplan` when failure could affect security, data integrity, public or
  shared contracts, migrations, production operations, compliance, or several
  independently owned modules.
- Use `$ralph` only after a task system has persisted and approved the contract.

## Pure Planning Boundary

During this skill:

- Inspect code, tests, configuration, documentation, and available history.
- Ask only for product intent or decisions that repository evidence cannot
  answer.
- Produce or revise a `plan-bundle/v1` JSON object.
- Write only the neutral Plan Bundle artifact described under Output And Stop.
- Do not create task IDs, task status, checkpoints, approval ledgers, or
  runtime-specific artifacts.
- Do not edit product source, run migrations, change external systems, commit,
  push, or start implementation.

An explicit `$plan` request is consent to plan, not consent to implement or to
create a task in any external system.

## Choose A Mode

### Direct

Use direct mode when outcome, scope, constraints, and success criteria are
already clear. Resolve repository facts and produce the bundle without an
interview.

### Interview

Use interview mode when a product, scope, compatibility, priority, or risk
decision would materially change the contract.

Before each question:

1. Search the repository and existing evidence first.
2. Ask one highest-value question at a time.
3. Explain why the decision matters.
4. Include a recommended answer and its trade-off.
5. Revise the bundle after the answer.

Use the surface's structured question UI when available. Do not depend on a
runtime-specific question command.

## Plan Bundle Contract

Produce valid JSON conforming to
`references/plan-bundle-v1.schema.json`. The top-level shape is:

```json
{
  "schema": "plan-bundle/v1",
  "bundle_id": "stable-id",
  "revision": 1,
  "mode": "plan",
  "status": "ready",
  "title": "Short task title",
  "goal": "Observable outcome",
  "context": {
    "repository": "repository name or path",
    "base_revision": "git revision or null",
    "generated_at": "ISO-8601 timestamp"
  },
  "facts": [],
  "scope": { "in": [], "out": [] },
  "constraints": [],
  "artifacts": [],
  "requirements": [],
  "acceptance_criteria": [],
  "design": null,
  "decision_record": null,
  "steps": [],
  "verification": [],
  "risks": [],
  "open_decisions": []
}
```

New producers must always emit `artifacts`, using an empty array when the plan
has no external contract artifact. The v1 schema accepts an omitted field only
so previously generated v1 bundles remain readable; omission is normalized to
an empty list by consumers and is not the current writer contract.

Use stable IDs such as `REQ-001`, `AC-001`, `STEP-001`, `VER-001`, and
`RISK-001`. Preserve `bundle_id` across revisions and increment `revision` for
every material contract change.

A blocked bundle may leave requirements, acceptance criteria, steps, or
verification incomplete. A ready bundle may not.

## Build The Contract

- `facts`: confirmed claims with concrete evidence such as file and line
  references.
- `scope`: explicit included and excluded outcomes.
- `constraints`: technical, product, compatibility, operational, and safety
  boundaries.
- `artifacts`: neutral, immutable contract inputs whose schemas, schema
  locators, schema digests, paths, content digests, revisions, measurement
  gates, and acceptance/verification coverage must be machine-checkable. Use
  this for approved visual baselines, migration maps, performance budgets, or
  similar domain contracts.
- `requirements`: independently testable obligations, not implementation
  narration.
- `acceptance_criteria`: observable proof linked to requirement IDs.
- `design`: boundaries, contracts, data flow, compatibility, rollout, rollback,
  and observability when the task needs design work; otherwise `null`.
- `steps`: ordered, right-sized implementation slices with dependencies,
  expected files, requirement coverage, and verification IDs.
- `verification`: concrete procedures or commands linked to acceptance IDs.
- `risks`: specific failure modes with triggers and mitigations.
- `open_decisions`: only unresolved choices that block a reliable contract.

Do not create a separate test specification. Behavioral expectations belong in
acceptance criteria; execution details belong in `verification`.

## Readiness Gate

Set `status` to `ready` only when:

- `open_decisions` is empty
- every requirement is covered by at least one acceptance criterion
- every acceptance criterion is covered by at least one verification entry
- every requirement maps to at least one implementation step
- every dependency references an existing step
- IDs are unique within their collections and the step dependency graph is
  acyclic
- every artifact and gate ID is unique, every artifact digest matches its
  schema-valid repo-relative file, every schema resolves through its declared
  `schema_ref` and matches `schema_digest`, and every gate references existing
  acceptance and verification IDs
- all referenced files and symbols were verified when the repository exists
- risks have concrete mitigations

Otherwise set `status` to `blocked` and preserve the blocking decisions. Never
label a partially specified bundle ready.

## Output And Stop

Unless the caller supplies another neutral path, write the Plan Bundle to:

```text
<project-root>/.tmp/plan/<bundle_id>.json
```

Resolve `<project-root>` as the active Git worktree root. When no Git worktree
exists, use the active workspace root or current working directory. Create the
`.tmp/plan` directory when needed.

Use the stable `bundle_id` as the filename. When revising an existing bundle at
that path, read it first, preserve its `bundle_id`, and increment `revision` for
every material contract change. A caller-supplied neutral path overrides the
default path.

After writing, read the file back and verify that it is valid JSON, conforms to
the Plan Bundle schema, and passes the readiness gate. Do not write task-system
state or invoke an adapter.

Return only:

1. a concise human summary
2. the absolute Plan Bundle file path
3. the bundle `status`
4. any blocking decision

Do not print the complete JSON Plan Bundle in the response unless the caller
explicitly requests inline JSON or response-only output. If the artifact cannot
be written or verified, report the attempted path and blocker without dumping
the JSON. Stop before implementation.

<!-- skillctl:source-attribution:start -->
## Source Attribution

- origin kind: derived-from-upstream
- upstream repo: Yeachan-Heo/oh-my-codex
- upstream path: skills/plan
- pinned ref: 456effa2afcb7967e8ba7130ee15b2835c235d72
- source type: github
- source URL: https://github.com/Yeachan-Heo/oh-my-codex/tree/v0.20.0/skills/plan
- imported at: 2026-07-13T11:50:36.134Z
- last verified ref: 456effa2afcb7967e8ba7130ee15b2835c235d72
- local modifications: true
<!-- skillctl:source-attribution:end -->
