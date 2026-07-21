---
name: ralph
description: Execute and verify an approved Trellis task until every acceptance criterion has current evidence or a genuine blocker is reached. Use after explicit implementation intent. Ralph depends only on the trellis-plan-adapter lifecycle interface and never reads Trellis storage directly.
metadata:
  short-description: Complete an approved Trellis task with evidence
---

# Ralph

Ralph is an execution strategy. Trellis owns persistence and lifecycle through
`$trellis-plan-adapter`; Ralph owns implementation pressure and completion
proof.

## Required Adapter Boundary

Load `$trellis-plan-adapter` before any task action. Use only these operations:

- `load_active_task()`
- `read_approved_contract(task_id)`
- `start_task(task_id, expected_revision, expected_digest)`
- `update_step_progress(task_id, expected_revision, expected_digest, step_id, status)`
- `record_verification_evidence(task_id, expected_revision, expected_digest, evidence)`
- `request_replan(task_id, expected_revision, expected_digest, reason)`
- `finish_task(task_id, expected_revision, expected_digest, completion_audit, authorize_finish)`

Do not inspect or mutate Trellis paths, task metadata, runtime pointers,
artifacts, evidence files, or lifecycle scripts directly. If the adapter is
missing or returns an unsupported-operation blocker, stop rather than creating
a fallback state machine.

## Use Ralph When

- the user explicitly asks to implement an approved task
- an active task spans several implementation and verification passes
- work must resume from persisted task state after interruption
- the user says to finish, keep going, or continue until done

Use `$plan` or `$ralplan` before Ralph when the contract is missing, blocked, or
stale. Use a normal direct edit for a small one-shot fix that does not need a
persistent Trellis task.

## Authorization Boundary

An unambiguous execution request authorizes local, reversible implementation
within the approved task. This includes `$ralph`, "start implementation", or
"finish the active task". A bare "continue" authorizes resuming only when the
adapter reports the task already in progress.

Execution intent does not authorize:

- destructive or irreversible operations
- production changes or external side effects
- credential-gated actions not already authorized
- commits, pushes, pull requests, releases, or archival unless explicitly
  requested
- silent scope reduction or contract changes

Ask only at one of those boundaries or when a real product decision is required.

## Entry Gate

1. Call `load_active_task()`.
2. Call `read_approved_contract(task_id)` and retain the task ID, revision, and
   digest as one concurrency token.
3. Reject blocked, stale, missing-review, reduced-consensus, or unsupported
   contracts.
4. If the task is still planning, require unambiguous execution intent and call
   `start_task()` with the exact task ID, revision, and digest just read.
5. Re-read that task's approved contract after start before editing source.

Never infer readiness from conversation history or passing tests alone.

## Build The Completion View

From the normalized contract, map:

- each requirement to its owning steps
- each acceptance criterion to required evidence
- each step to dependencies, expected files, and verification procedures
- each neutral artifact gate to its contract ID, revision, digest, acceptance,
  and verification coverage
- each risk to its trigger and mitigation

Use the normalized step progress and revision-scoped evidence returned with the
approved contract as the only durable execution view. Do not create another
checklist or ledger.

Resume from persisted progress and evidence. Do not restart discovery or repeat
completed work unless new evidence invalidates it.

## Execution Loop

1. Select the next incomplete or adapter-reported stale step whose dependencies
   are complete.
2. Inspect the relevant code and tests before editing.
3. Implement the smallest coherent change that advances the step.
4. Run targeted verification and read the actual output.
5. Record evidence through `record_verification_evidence()` with the exact task
   ID, revision, and digest last read.
6. Mark progress through `update_step_progress()` with that same concurrency
   token only after the step's required checks pass.
7. Continue automatically while progress is measurable and no authorization or
   contract boundary is crossed.

Parallelize only independent steps with disjoint ownership. Each delegated
agent receives the normalized contract slice, exact write scope, applicable
constraints, and verification target. The main agent owns integration and final
evidence.

Do not delete or weaken tests, narrow requirements, or hide failures to obtain a
green result.

## Verification Loop

At candidate completion, run every applicable verification procedure in the
approved contract plus repository-required checks. A check implementation may
own a bounded local self-fix loop; Ralph must not wrap each internal retry in an
outer blind retry.

After a check returns:

- record the observed result through the adapter
- fix unresolved findings only with a new hypothesis or meaningful code change
- rerun affected checks after the candidate materially changes
- preserve failing evidence instead of overwriting history

Treat evidence from an older adapter-reported workspace fingerprint as history,
even when the contract revision is unchanged.

Passing tests are necessary but not sufficient when they do not cover the whole
contract.

## Contract Change Rule

Stop source edits and call `request_replan()` when implementation reveals a
missing or changed:

- shared or public interface
- security or privacy premise
- data migration or compatibility requirement
- destructive-operation boundary
- product decision that changes acceptance

Pass the exact task ID, revision, digest, and a concrete reason. Do not resume
until a new neutral contract is persisted and independently reviewed when its
risk class requires Ralplan.

## Stall Detection

A retry is justified only by a new hypothesis, code change, environment change,
or new evidence. If the same failure recurs 3 times without meaningful new
evidence:

1. record all attempts through the adapter
2. classify the blocker as code, environment, dependency, credential, external
   service, or unresolved requirement
3. report the smallest input or state change needed to resume
4. stop the loop

Do not consume iterations merely to restate the same failure.

## Completion Audit

Before completion:

- map every requirement to delivered artifacts
- map every acceptance criterion to fresh passing evidence
- map every artifact gate to exact-binding passing evidence for the current
  contract revision and workspace fingerprint
- confirm every step is complete
- run applicable tests, lint, typecheck, build, diagnostics, and observability
  checks
- inspect the final diff for unrelated changes, generated noise, debug code,
  and weakened tests
- use an independent verifier for security, data, public contracts, migrations,
  or broad cross-module work
- rerun affected checks after every post-verification edit

Build a structured completion audit containing requirement coverage, criterion
evidence IDs, final commands, results, changed files, and residual risks.

## Finish Boundary

Call `finish_task()` with the exact task ID, revision, digest, and audit.

- Set `authorize_finish: false` unless the user explicitly requested the
  lifecycle finish action.
- Treat `ready_for_finish` as verified implementation, not permission to commit,
  push, release, or archive.
- If the adapter rejects completion, continue only when its blocker is
  actionable within the existing contract.

Stop successfully only when the adapter accepts the completion audit. Stop as
blocked only for a genuine authorization, environment, dependency,
external-service, adapter, or requirements impasse. Stop immediately when the
user says to stop.

<!-- skillctl:source-attribution:start -->
## Source Attribution

- origin kind: derived-from-upstream
- upstream repo: Yeachan-Heo/oh-my-codex
- upstream path: skills/ralph
- pinned ref: 456effa2afcb7967e8ba7130ee15b2835c235d72
- source type: github
- source URL: https://github.com/Yeachan-Heo/oh-my-codex/tree/v0.20.0/skills/ralph
- imported at: 2026-07-13T11:50:55.660Z
- last verified ref: 456effa2afcb7967e8ba7130ee15b2835c235d72
- local modifications: true
<!-- skillctl:source-attribution:end -->
