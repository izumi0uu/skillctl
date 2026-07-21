---
name: trellis-plan-adapter
description: Internal adapter for importing neutral plan-bundle/v1 and plan-review/v1 artifacts into Trellis, loading approved contracts, starting or replanning tasks, recording verification evidence, and enforcing completion. Use when a planning result must cross into Trellis or when $ralph needs task lifecycle operations.
metadata:
  short-description: Bridge neutral plan contracts into Trellis
---

# Trellis Plan Adapter

This skill is the only layer that may know Trellis storage and lifecycle
details. It does not create plans or implement product code. It translates
neutral contracts into Trellis and exposes a narrow operation interface to
execution workflows.

## Required Inputs

- Plan Bundle conforming to `$plan`'s `plan-bundle/v1` schema.
- For `mode: ralplan`, Review Receipt conforming to `$ralplan`'s
  `plan-review/v1` schema.
- Expected task ID, contract revision, and digest for every mutating execution
  operation after import.

Load the schema references from the installed `$plan` and `$ralplan` skills
when exact validation is needed. Reject malformed or unsupported schema
versions; never guess a migration silently.

For compatibility with plan bundles produced before neutral artifacts were
added to v1, accept an omitted `artifacts` field as an empty list in the
normalized operation view. Preserve and hash the exact input bundle; do not
insert the field into persisted bytes. Current Plan and Ralplan producers must
emit `artifacts`, including an explicit empty list when unused.

## Ownership Boundary

- Trellis owns task identity, lifecycle status, active-task recovery, progress,
  evidence, and archival.
- `plan.bundle.json` is the adapter-owned machine contract inside a task.
- `prd.md`, `design.md`, and `implement.md` are generated human-readable
  projections of that contract.
- Trellis task status remains the only lifecycle status.
- Verification records are evidence, not a second task state machine.
- `$ralph` receives normalized operation results and must not read or mutate
  Trellis files directly.

## Discover The Local Trellis Contract

Before an operation:

1. Locate the repository-local Trellis root.
2. Read its local workflow, configuration, task schema, and lifecycle scripts.
3. Prefer the local project implementation over remembered global behavior.
4. Use structured JSON parsing and writing for task metadata.
5. Do not parse hidden runtime pointers when an injected active-task context or
   supported local command is available.

If the installed Trellis version cannot provide a required operation, return a
typed blocker. Do not bypass lifecycle behavior with an unrelated state file.

## Adapter Operations

Expose these conceptual operations. Return structured results with `ok`,
`operation`, `task_id`, `contract_revision`, `bundle_digest`, and either `data`
or a typed `blocker`. Treat task ID, revision, and digest together as the
execution concurrency token.

### `import_contract(bundle, review?, task_id?, authorize_create=false)`

1. Validate the bundle schema, unique IDs, acyclic step graph, and every
   requirement, acceptance criterion, artifact gate, step, dependency, and
   verification cross-reference. Resolve every artifact schema only through its
   typed `schema_ref`:
   - `kind: repository` resolves `path` from the repository root.
   - `kind: skill` resolves `path` from the installed skill named by `skill_id`.
   - reject absolute paths, traversal, symlink escape, missing skills, unknown
     locator kinds, malformed schemas, and unsupported schema drafts.
   Canonicalize the parsed JSON Schema with RFC 8785 JCS and require its digest
   to equal `schema_digest`. Then validate the repo-relative artifact file,
   recompute its digest, and require its schema identifier, contract ID,
   revision, and gates to match the Plan Bundle exactly. Unknown schemas fail
   closed; do not search arbitrary agent directories or the network.
2. Canonicalize the parsed bundle with RFC 8785 JCS. Hash the canonical UTF-8
   bytes with SHA-256 and prefix the lowercase hex digest with `sha256:`.
3. Require `status: ready` and no open decisions.
4. For `mode: ralplan`, require an independent approved receipt whose
   `bundle_id`, revision, and digest match exactly.
5. Use the explicit task ID, otherwise the active planning task. Create a task
   only when neither exists and `authorize_create` is true.
6. For an existing adapter contract, require the same `bundle_id`. Treat an
   exact revision-and-digest replay as idempotent, reject a changed digest at
   the same or lower revision, and accept a changed contract only at a higher
   revision.
7. Persist the exact bundle as `plan.bundle.json`; persist the required Ralplan
   receipt as `plan.review.json`. Omit a receipt for ordinary Plan mode.
8. Generate:
   - `prd.md` from goal, facts, scope, constraints, requirements, and acceptance
   - `design.md` from design and decision record when present
   - `implement.md` from steps, dependencies, verification, risks, and stop
     conditions
9. Map Plan Bundle steps to Trellis subtasks using stable step IDs. During a
   re-import, preserve completed progress only when the step ID and normalized
   step content are unchanged; reset changed steps and dependents.
10. Preserve project-owned context manifests and populate them only according to
   the local Trellis workflow. They are context manifests, never progress.
11. Store adapter metadata under `task.json.meta.plan_adapter`:
    - `adapter_schema: trellis-plan-adapter/v1`
    - `status: ready`
    - `contract_revision`
    - `bundle_digest`
    - `mode`
    - `base_revision`
    - projection hashes
    - review status and review digest when applicable
    - artifact contract IDs, revisions, digests, and gate hashes
12. Keep the Trellis task in planning. Import does not authorize execution.

Any direct change to the persisted bundle or generated projections makes the
contract stale until it is re-imported and, for Ralplan, re-reviewed.

### `load_active_task()`

Resolve the active task through injected context or the local supported task
interface. Return normalized task identity, lifecycle status, adapter status,
contract revision, and bundle digest. Do not return storage internals unless the
caller explicitly needs diagnostics.

### `read_approved_contract(task_id)`

1. Load the named task and adapter metadata. Do not silently follow a changed
   active-task pointer.
2. Recompute bundle and projection hashes.
3. Validate schema, readiness, step graph, acceptance coverage, artifact files,
   artifact schemas, digests, and gate bindings.
4. For Ralplan mode, validate the detached review receipt and independent
   approval.
5. Return a normalized contract containing goal, requirements, acceptance
   criteria, artifacts and gates, steps, verification procedures, risks,
   revision, and digest, plus normalized step progress, current workspace
   fingerprint, and evidence IDs/outcomes/fingerprints for the current revision.

Derive `effective_status: stale` for a persisted completed step when its
required passing evidence does not match the current relevant workspace
fingerprint. This is a read-time validity result, not a second persisted task
status; callers must treat it as incomplete.

Return `stale_contract`, `missing_review`, `reduced_consensus`,
`projection_drift`, or `unsupported_schema` instead of a contract when a gate
fails.

### `start_task(task_id, expected_revision, expected_digest)`

Use optimistic concurrency:

1. Re-read the approved contract immediately before start.
2. Require the expected revision and digest to match.
3. Require the named task to match the contract just read.
4. Compare the bundle's base repository revision with the current repository.
   If relevant code changed and compatibility cannot be proved, require replan.
   If the base revision is null in a Git repository, require replan rather than
   guessing a baseline.
5. Invoke the local Trellis start transition and return the resulting lifecycle
   status.

Never start from a stale read and never treat import as execution approval.

### `record_verification_evidence(task_id, expected_revision, expected_digest, evidence)`

Require the full concurrency token to match the approved contract. Validate
that referenced artifact gates, verification IDs, and acceptance IDs exist and
agree with the contract's coverage map. Compute the current
implementation-workspace fingerprint, assign an immutable evidence ID, and
append the record to
`verification.jsonl`. Exclude adapter-owned task artifacts from the fingerprint
according to the local Trellis workflow. Each record must include:

- evidence ID and timestamp
- contract revision and bundle digest
- adapter-computed workspace fingerprint
- verification procedure IDs
- acceptance criterion IDs
- evidence kind and `passed`, `failed`, or `inconclusive` outcome
- command or procedure when applicable
- exit status when applicable
- concise observed result
- relevant artifact or diff hashes when useful

Artifact-backed evidence must also persist an `artifact_binding` containing the
Plan Bundle artifact ID, artifact contract ID and revision, artifact digest,
schema identifier and schema digest, gate ID, submitted evidence digest, and
adapter-recomputed semantic outcome. For `visual-verdict/v1`, `case_id` and the
RFC 8785 JCS SHA-256 `verdict_digest` are additionally required. These fields
are immutable evidence bindings, not display metadata.

For `visual-verdict/v1` evidence, validate the verdict schema and recompute its
semantic gates. Treat submitted `threshold_met` as an untrusted derived claim:
recompute `score >= threshold` and reject the verdict as `invalid_evidence` if
the values differ; never silently rewrite it. Require bundle, baseline,
artifact, gate, and case bindings to match the approved artifact contract.
Reject the evidence as `replayed_evidence` unless the verdict's capture-time
workspace fingerprint equals the adapter's current relevant workspace
fingerprint at record time.

Regenerate `verification.md` as a human-readable projection when the local
workflow uses it. Old-revision evidence remains historical and cannot satisfy a
new contract automatically. Evidence whose workspace fingerprint no longer
matches the relevant current source state also remains historical.

### `update_step_progress(task_id, expected_revision, expected_digest, step_id, status)`

Update the Trellis-owned subtask corresponding to the stable Plan Bundle step
ID. Normalize status to `pending`, `in_progress`, `completed`, or `blocked`, then
map it to the local lifecycle. Reject unknown steps, invalid transitions, stale
concurrency tokens, and completion when required predecessor steps are
incomplete. Before accepting `completed`, require current-fingerprint passing
evidence for every verification procedure and acceptance criterion assigned to
that step. Also require exact-binding passing evidence for every artifact gate
whose acceptance or verification coverage intersects the step's assigned
coverage. The evidence must match the current contract revision, workspace
fingerprint, artifact contract, gate, and case when applicable; otherwise
return `stale_evidence`.

### `request_replan(task_id, expected_revision, expected_digest, reason)`

Require the full concurrency token to match, then fail closed before further
source edits:

1. Mark adapter status `drafting` and review status `invalidated`.
2. Record the reason and prior contract revision.
3. Invoke the local transition back to planning.
4. Preserve prior evidence as revision-scoped history.

If the local transition is unavailable or fails, return a blocker while leaving
the approval invalidated.

### `finish_task(task_id, expected_revision, expected_digest, completion_audit, authorize_finish)`

Require:

- task ID, current revision, and digest still match
- every Plan Bundle step is complete
- every acceptance criterion has passing evidence for this revision and the
  current relevant workspace fingerprint
- every artifact gate has exact-binding passing semantic evidence for this
  revision and the current relevant workspace fingerprint
- required repository verification has passed
- no unresolved blocker or stale projection exists

Persist the completion audit under adapter metadata. Without
`authorize_finish`, return `ready_for_finish` and perform no lifecycle side
effect. With authorization, invoke only the local Trellis finish behavior whose
prerequisites are satisfied. Commit, push, release, and archive remain separate
authorization boundaries.

## Failure Rules

- Never repair a malformed bundle by silently dropping fields.
- Never accept a Ralplan receipt for a different digest or revision.
- Never reuse passing evidence across revisions without explicit revalidation.
- Never accept a changed bundle at the same or a lower contract revision.
- Never follow an active-task pointer after the caller has bound a task ID.
- Never update progress and evidence as one ambiguous status.
- Never claim success when the local lifecycle operation did not run.
- Preserve unrelated task metadata and unrelated working-tree changes.

## Output

Return a concise structured adapter result and enough evidence for the caller to
decide whether to continue, replan, or stop. Do not produce product code or
planning content in this skill.
