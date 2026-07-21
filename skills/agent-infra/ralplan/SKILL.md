---
name: ralplan
description: Create or independently challenge a high-confidence Plan Bundle before implementation. Use for security, data, migration, public-contract, production, compliance, destructive, or broad cross-module work that needs sequential Architect and Critic review. The output remains task-system neutral.
metadata:
  short-description: Independently review a high-risk plan contract
---

# Ralplan

Ralplan is a confidence gate over `plan-bundle/v1`, not a task runtime. It
produces a revised Plan Bundle plus a detached `plan-review/v1` receipt.

## Use Ralplan When

- authentication, authorization, secrets, privacy, or compliance is involved
- data migration, destructive change, or difficult rollback is possible
- a public or shared interface may break consumers
- production infrastructure or an operational incident is involved
- several modules, packages, services, or owners must agree on one contract
- multiple viable designs have materially different consequences

Use `$plan` for ordinary work. Ralplan's isolated reviewers are an intentional
cost and must add independent challenge.

## Pure Planning Boundary

During this skill:

- Read repository evidence and neutral planning artifacts.
- Produce only a revised `plan-bundle/v1` and `plan-review/v1` receipt.
- Do not create or mutate task IDs, status, lifecycle, checkpoints, approval
  ledgers, or runtime-specific files.
- Do not edit product source, run migrations, change external systems, commit,
  push, or start implementation.
- Run Architect and Critic sequentially, never in parallel and never as one
  combined self-approval.

An explicit `$ralplan` request is consent to plan and review, not consent to
persist or execute the result.

## Establish The Bundle

Start from a valid `plan-bundle/v1` produced by `$plan`. If none exists, perform
the same evidence-first planning work and create one before review.

Before Architect review:

- set bundle `mode` to `ralplan`
- increment `revision` for every material change
- ensure `status` is `ready`
- preserve the stable `bundle_id`
- populate `design`
- populate `decision_record`

The decision record must contain:

- 3-5 governing principles
- the top 3 decision drivers
- at least 2 options with bounded benefits and costs
- an invalidation reason for every non-viable option
- the chosen option and consequences

Every Ralplan contract also requires:

- 3 concrete pre-mortem scenarios
- applicable unit, integration, end-to-end, and observability verification
- migration, rollback, and operator recovery criteria when those concerns apply

## Sequential Review

### 1. Architect

Launch a fresh role-specific Architect through the platform's isolated review
surface. Pass the task statement, repository evidence, and exact Plan Bundle,
but not hidden Planner reasoning.

Require:

- the strongest steelman counterargument to the chosen design
- at least one real trade-off tension
- contract, boundary, compatibility, and rollback findings
- a synthesis or narrower alternative when possible
- verdict: `APPROVE` or `REVISE`, with concrete required changes

Wait for Architect to finish before starting Critic.

### 2. Critic

Launch a separate fresh Critic with the exact bundle and completed Architect
result. Require it to verify:

- principles, drivers, and chosen option agree
- alternatives were explored fairly
- every requirement maps to steps, acceptance, and verification
- every neutral artifact digest, schema, gate, and coverage binding is valid
- acceptance criteria are observable and complete
- risks have concrete mitigations and rollback behavior
- evidence references are real
- required pre-mortem and verification layers are adequate

Critic verdict must be `APPROVE`, `REVISE`, or `REJECT`. Architect approval
cannot substitute for Critic approval.

If isolated reviewers are unavailable, report `consensus_strength: reduced`.
Reduced review may improve a bundle but cannot approve high-risk work. A task
may use the ordinary `$plan` gate only after an explicit evidence-backed risk
and scope reclassification; platform limitations never justify downgrade.

## Revision Budget

- Prefer at most 1 revision and 2 complete review cycles.
- Allow at most 2 revisions and 3 complete review cycles for destructive,
  production, migration, regulated-data, or public-contract work.
- Re-run both Architect and Critic after every material revision.
- If Critic still does not approve, return the best blocked bundle and a
  non-approved receipt. Never drift into implementation.

Merge accepted feedback into the Plan Bundle. Do not leave the final contract
split across reviewer transcripts.

## Detached Review Receipt

Validate the final bundle against `plan-bundle/v1`, then canonicalize the parsed
object with RFC 8785 JSON Canonicalization Scheme (JCS). Hash the canonical
UTF-8 bytes with SHA-256 and prefix the lowercase hex digest with `sha256:`.
Use a conforming structured serializer, not text replacement or ordinary
pretty-printed JSON.

Return a receipt conforming to
`references/plan-review-v1.schema.json`:

```json
{
  "schema": "plan-review/v1",
  "bundle_id": "stable-id",
  "bundle_revision": 2,
  "plan_digest": "sha256:<digest>",
  "status": "approved",
  "consensus_strength": "independent",
  "architect": {
    "verdict": "APPROVE",
    "required_changes": [],
    "findings": []
  },
  "critic": {
    "verdict": "APPROVE",
    "required_changes": [],
    "findings": []
  },
  "reviewed_at": "<ISO-8601 timestamp>"
}
```

`status: approved` requires independent consensus and both verdicts to be
`APPROVE`. A revised bundle invalidates every older receipt, even if the task
title and intent remain unchanged.

## Output And Stop

Return:

1. chosen option and main consequence
2. the complete revised Plan Bundle
3. the detached Review Receipt
4. revision count, consensus strength, and unresolved objections

Write these neutral artifacts only to caller-supplied paths. Do not invoke a
task adapter or implementation workflow. Stop after review.

<!-- skillctl:source-attribution:start -->
## Source Attribution

- origin kind: derived-from-upstream
- upstream repo: Yeachan-Heo/oh-my-codex
- upstream path: skills/ralplan
- pinned ref: 456effa2afcb7967e8ba7130ee15b2835c235d72
- source type: github
- source URL: https://github.com/Yeachan-Heo/oh-my-codex/tree/v0.20.0/skills/ralplan
- imported at: 2026-07-13T11:50:45.211Z
- last verified ref: 456effa2afcb7967e8ba7130ee15b2835c235d72
- local modifications: true
<!-- skillctl:source-attribution:end -->
