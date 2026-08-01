# Traceability Model

Use this model whenever the generated design document is refreshed during implementation or after requirements change.

## Invariants

1. Trellis decision artifacts authorize intent. The generated document never authorizes a requirement change.
2. Repository code and tests establish observed and verified behavior. They do not retroactively approve intent.
3. The document is a derived current/evolving view with a compact trace chain, not a full snapshot archive.
4. Evidence lane, claim lifecycle, and evidence freshness are independent axes.
5. A prior active claim never disappears silently.
6. Requirement-changing events without a Trellis decision anchor remain `OPEN — unrecorded requirement change`.

## Generation Identity

Each refresh creates one generation record:

| Field | Meaning |
|---|---|
| `generation_id` | Unique ID such as `G-20260721T153000Z-a1b2c3d` |
| `parent_generation_id` | Prior generation, `none`, or `broken` |
| `generated_at` | UTC timestamp |
| `task_revision` | Task status/revision or fingerprint of the decision artifacts |
| `workspace_basis` | `branch@HEAD` plus clean/dirty state |
| `previous_document` | Prior generated document path when refreshing |
| `trace_chain_status` | `new`, `continuous`, or `broken` |

A dirty-workspace generation is valid, but its basis must identify relevant changed and untracked files. Never imply it represents clean HEAD.

## Claim Identity

Assign `C-NNN` IDs on the first generation. On refresh, reuse IDs from the previous claim ledger; never renumber surviving claims for presentation.

Reuse an ID when:

- wording is clarified without changing behavioral meaning;
- a source path or symbol moves but still establishes the same claim;
- evidence is refreshed, becomes stale, or is invalidated;
- the claim is reclassified between evidence lanes without changing its meaning.

Create successor IDs when:

- accepted behavior, scope, invariant, default, error, or ownership materially changes;
- one claim splits into several independently enforceable rules;
- several claims merge into a different rule.

Record all predecessor/successor edges. Many-to-many lineage is allowed. A semantic hash or source fingerprint may help detect changes, but it must not replace human-readable identity rules.

## Three Independent Axes

| Axis | Values | Purpose |
|---|---|---|
| Evidence lane | `DECISION`, `OBSERVED`, `VERIFIED`, `HISTORICAL`, `INFERENCE`, `OPEN` | What kind of claim this is |
| Claim lifecycle | `active`, `superseded`, `retired`, `open` | Whether the claim remains part of the current contract/view |
| Evidence freshness | `current`, `stale`, `broken`, `not-run` | Whether its cited evidence still applies to this generation |

Do not encode two axes in one status. For example, a decision may remain `active` while its implementation evidence is `stale`.

## Semantic Events

Emit events only when a claim or its evidence meaningfully changes:

| Action | Identity rule | Required trace |
|---|---|---|
| `ADD` | New ID | New claim, requirement/decision anchor, reason |
| `CLARIFY` | Reuse ID | Before/after fingerprints and clarification reason |
| `RECLASSIFY` | Reuse ID | Previous/new lane and trigger source |
| `SUPERSEDE` | New successor ID | Predecessor, successor, decision anchor, rationale |
| `RETIRE` | Keep compact tombstone | Removal decision and rationale |
| `VERIFY` | Reuse ID | Current check receipt |
| `INVALIDATE` | Reuse ID | Evidence that no longer applies and why |
| `REOPEN` | Reuse ID or successor as semantics require | New conflict, failed check, or missing decision |

Do not emit one event per unchanged claim. Record only the unchanged count in the generation summary.

## Evidence Receipts

Evidence receipts are compact metadata, not copied logs or source text:

| Field | Meaning |
|---|---|
| `receipt_id` | Stable receipt handle |
| `claim_id` | Claim supported or challenged |
| `source_kind` | Trellis artifact, code, test, command, Git, or prior generation |
| `source_revision` | Commit, task revision/fingerprint, or command run boundary |
| `source_anchor` | Path plus symbol/test/decision handle |
| `first_seen_generation` | First generation that cited this source revision |
| `last_seen_generation` | Most recent generation that re-observed it |
| `freshness` | `current`, `stale`, `broken`, or `not-run` |

One receipt must not validate several unrelated claims merely because they share a command. Bind receipts to the exact claim or contract checked.

## Requirement Change Rule

For every material requirement change:

1. Locate the explicit Trellis decision and rationale.
2. Identify affected claims, implementation anchors, and verification receipts.
3. Create successor claim IDs for changed semantics.
4. Mark predecessor claims `superseded` and link both directions.
5. Mark affected verification `stale` or `invalidated` until rerun.
6. Emit one compact semantic event per affected claim.

If step 1 fails, do not synthesize approved intent. Preserve the observed change as an `OPEN` claim, record `Missing Trellis decision`, and name the evidence needed to close it.

## Refresh Algorithm

1. Read current Trellis artifacts and repository evidence.
2. Read the prior document's generation ledger, claim ledger, evidence receipts, and semantic change manifest.
3. Bind a new generation ID and parent generation.
4. Match current claims to prior stable IDs.
5. Classify added, clarified, reclassified, superseded, retired, verified, invalidated, reopened, and unchanged claims.
6. Validate requirement-changing events against explicit Trellis decisions.
7. Update the current-view prose and trace matrices.
8. Append one generation row and only semantic event rows.
9. Keep compact tombstones for non-active claims; never copy full prior prose.
10. Run the reconstruction checklist.

## Broken Chain Handling

If the previous generated document is missing or its ledgers are malformed:

- set `parent_generation_id: broken` and `trace_chain_status: broken`;
- do not guess old claim IDs or change rationale from Git alone;
- generate a fresh current ledger from authoritative sources;
- record which historical transitions can no longer be proven;
- continue producing a useful partial document.

## Compactness Rules

- Never append full generated-document snapshots.
- Never copy full test logs, diffs, or source files into trace tables.
- Never emit events for unchanged claims.
- Keep tombstones to IDs, transition, rationale, source handles, and generation IDs.
- Keep the current prose readable; detailed provenance belongs in ledgers.
- If the event history becomes large, move closed events to a linked trace archive while keeping claim lineage and generation continuity in the current document.
