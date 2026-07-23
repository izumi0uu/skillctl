# Reconstruction Checklist

Use this checklist before reporting a generated design document as complete.

## Task Resolution

- [ ] The Trellis task was explicitly supplied or resolved through supported context.
- [ ] No ambiguous active-task choice was guessed.
- [ ] `task.json` status and task path were recorded.

## Workspace Basis

- [ ] Repository, branch, HEAD, and generation time are recorded.
- [ ] Clean or dirty workspace state is explicit.
- [ ] Relevant local modifications and untracked files are included in the basis.
- [ ] The document states when it becomes stale.
- [ ] Generation ID, parent generation ID, previous document path, and trace-chain status are recorded.
- [ ] A missing parent document is reported as a broken chain rather than silently treated as a first generation.

## Trellis Coverage

- [ ] `task.json`, `prd.md`, `design.md`, and `implement.md` were read when present.
- [ ] Every entry in `implement.jsonl` and `check.jsonl` was considered.
- [ ] Relevant `research/` artifacts were read.
- [ ] `relatedFiles` and anchors named by the task were inspected or explicitly refused.
- [ ] Missing or deleted referenced documents are recorded as dangling references, not silently ignored.
- [ ] Every material requirement change has an explicit Trellis decision anchor and rationale, or is labeled `OPEN — unrecorded requirement change`.

## Repository Coverage

- [ ] Data model and persistence surfaces were checked when relevant.
- [ ] Public interfaces and call sites were checked when relevant.
- [ ] Lifecycle/service behavior was checked when relevant.
- [ ] Authorization, tenant, privacy, and destructive-operation boundaries were checked when relevant.
- [ ] Async, storage, callback, and integration boundaries were checked when relevant.
- [ ] Frontend behavior was checked when relevant.
- [ ] Focused tests and fixtures were located.
- [ ] Git history was used only where it adds historical rationale.

## Claim Integrity

- [ ] Every normative claim is backed by an explicit decision source.
- [ ] Every observed claim has a current repository anchor.
- [ ] Every `VERIFIED` claim has a check observed in the current workspace.
- [ ] `implemented-unverified` is used when code exists but current verification was not observed.
- [ ] Historical evidence is not presented as current behavior.
- [ ] Inference is labeled `INFERENCE` and has supporting evidence handles.
- [ ] Negative searches state their search boundary.
- [ ] No claim relies only on chat memory.
- [ ] Stable claim IDs were reused for semantically unchanged claims.
- [ ] Materially changed claims received successors with explicit supersession edges.
- [ ] Evidence lane, trace state, and verification freshness were not collapsed into one status.
- [ ] First-seen and last-changed generation IDs are present for current claims.
- [ ] Evidence receipts identify claim, source revision, first/last seen generation, and freshness.
- [ ] A verification receipt is scoped to the exact claim or contract it checked.

## Conflict Handling

- [ ] Contradictory claims remain visible.
- [ ] Decisions, implementation, and tests are not blended into false consensus.
- [ ] Each conflict states impact and the decision needed.
- [ ] Missing evidence causes a section-local refusal or open item, not invented prose.
- [ ] Superseded behavior is linked to its successor rather than silently erased.
- [ ] No previously active claim disappeared without `SUPERSEDE`, `RETIRE`, or an explicit broken-chain record.
- [ ] A generated trace event was not treated as approval for a requirement change.

## Output Quality

- [ ] The document is understandable without the deleted source-design document.
- [ ] It does not claim byte-for-byte historical restoration.
- [ ] It is labeled as generated and current-view, historical, partial, or stale.
- [ ] Source handles resolve to paths, symbols, tests, commands, or commits.
- [ ] Line numbers are not the only anchors.
- [ ] Irrelevant template sections were omitted.
- [ ] No PHI, secrets, tokens, credentials, or sensitive fixtures were copied.
- [ ] Product source was not modified.
- [ ] The generation ledger links to its parent and summarizes changed versus unchanged claims.
- [ ] The semantic change manifest contains deltas and compact tombstones, not full prior document prose.
- [ ] Requirement, claim, implementation, and verification links are navigable in both directions.

## Snapshot-Free Reconstruction Probe

When proving that a source design document can be deleted:

1. Exclude the source document from the reconstruction inputs.
2. Generate from Trellis task artifacts, repository code, tests, and Git evidence only.
3. Compare coverage against the expected design topics, not the original wording.
4. Confirm that missing intent appears as `OPEN` rather than being guessed.
5. Confirm that a new maintainer can locate implementation and verification anchors.
6. Record whether the result is complete or partial.

A failed probe means the durable Trellis evidence or repository anchors need enrichment. It does not mean a source-document snapshot must automatically be retained.
