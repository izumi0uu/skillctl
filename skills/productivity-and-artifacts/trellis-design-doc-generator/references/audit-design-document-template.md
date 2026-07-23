# Audit Design Document Template

Use this rendering guide only in `audit` mode. It produces a current, evolving, or historical reconstruction with evidence lineage. Omit sections that do not apply. Never fill a missing section with invented content.

```markdown
# <Feature> Design — Generated Current/Evolving View

> Generated from Trellis and repository evidence.
> This document is a derived view with compact claim lineage; Trellis remains the authority for approved intent.

## Basis And Freshness

- Generated at:
- Repository:
- Trellis task:
- Task status:
- Branch:
- HEAD:
- Workspace: clean | dirty
- Relevant local changes:
- Mode: current-view | evolving-view | historical
- Generation ID:
- Parent generation ID: none | `<generation-id>` | broken
- Previous generated document: none | `<path>` | missing
- Trace-chain status: new | continuous | broken
- Freshness rule: regenerate when the task decisions, branch, HEAD, verification basis, or relevant dirty files change.

## Source Map

| Handle | Lane | Source | Scope |
|---|---|---|---|
| D1 | DECISION | `<task>/prd.md` | Approved product behavior |
| O1 | OBSERVED | `path :: Symbol` | Current implementation |
| V1 | VERIFIED | `<command or procedure>` | Current observed result |
| H1 | HISTORICAL | `<commit or journal>` | Earlier behavior/rationale |
| N1 | OPEN | `<search boundary>` | Evidence searched but not found |
| P1 | PRIOR | `<previous generated document>` | Parent claim ledger and trace chain only |

## Evidence Receipts

| Receipt | Claim | Source kind/revision | Anchor | First seen | Last seen | Freshness |
|---|---|---|---|---|---|---|
| ER-001 | C-001 | test / `<run-boundary>` | `<test or command>` | G-001 | G-002 | current |

## Requirement Traceability

| Requirement | Current decision | Claims | Implementation | Verification | Status |
|---|---|---|---|---|---|
| R-001 | D1 | C-001 C-002 | O1 O2 | V1 | aligned | drift | open |

## Goal

Human-facing purpose and who benefits. [D1]

## Scope And Non-Goals

In scope:

- ... [D2]

Out of scope:

- ... [D3]

## Architecture And Domain Model

Describe major entities, ownership, boundaries, and data flow.

### Target Decision

... [D4]

### Observed Implementation

... [O1 O2]

### Drift Or Unknowns

... [OPEN-1]

## Data Model And Persistence

Tables/documents, relationships, constraints, indexes, retention, migrations, and cleanup behavior. [O3 O4]

## Public Interfaces

Routes, events, function contracts, request/response shapes, errors, defaults, and compatibility boundaries. [D5 O5 V2]

## Lifecycle And Workflows

State transitions, creation/update/delete flows, recurrence, retries, and transaction boundaries. [D6 O6]

## Invariants And Concurrency

Locking, idempotency, uniqueness, ordering, stale-write handling, and shared-resource rules. [D7 O7 V3]

## Authorization, Tenant, Privacy, And Destructive Operations

Who may act, how data ownership is enforced, what is sensitive, and what deletion or irreversible actions do. [D8 O8 V4]

## Async Processing And Integrations

Jobs, callbacks, storage, external APIs, retry/failure behavior, and eventual consistency. [O9]

## Frontend Behavior

User-visible flow, interaction boundaries, loading/error states, accessibility, and responsive behavior. [D9 O10]

## Failures And Edge Cases

| Scenario | Target behavior | Observed behavior | Evidence | Status |
|---|---|---|---|---|
| ... | ... | ... | D10 O11 V5 | aligned | drift | open |

## Verification Coverage

| Contract | Status | Evidence | Gap |
|---|---|---|---|
| ... | verified | V6 | — |
| ... | implemented-unverified | O12 | Current check not run |
| ... | gap | OPEN-2 | Product decision needed |
| ... | historical-only | H2 | Not established in current workspace |

## Conflicts And Open Decisions

### OPEN-1: <Topic>

- Decision evidence: ... [D11]
- Current implementation: ... [O13]
- Test evidence: ... [V7]
- Historical context: ... [H3]
- Impact:
- Required decision:

## Claim Ledger

| Claim | Lane | Lifecycle | Evidence freshness | Current statement | Evidence | First seen | Last changed | Supersedes | Conflict group |
|---|---|---|---|---|---|---|---|---|---|
| C-001 | DECISION | active | current | ... | D1 | G-001 | G-002 | — | — |
| C-002 | OBSERVED | superseded | stale | ... | O1 | G-001 | G-003 | — | OPEN-1 |
| C-003 | INFERENCE | open | not-run | ... | D1 O1 | G-003 | G-003 | — | OPEN-1 |

## Evolution Trace

### Generation Ledger

| Generation | Parent | Generated at | Task/revision | Workspace basis | Change summary |
|---|---|---|---|---|---|
| G-001 | — | ... | ... | `branch@HEAD`, clean/dirty | Initial generation |
| G-002 | G-001 | ... | ... | `branch@HEAD`, clean/dirty | `+2 ~1 >1 -0; 14 unchanged` |

### Semantic Change Manifest

| Event | Generation | Action | Claim | Successor | Requirement/decision | Rationale | Evidence impact |
|---|---|---|---|---|---|---|---|
| E-001 | G-002 | CLARIFY | C-001 | — | R-001 / D2 | Approved requirement clarification | O2 refreshed; V1 stale |
| E-002 | G-002 | SUPERSEDE | C-002 | C-004 | R-002 / D3 | Behavioral contract changed | V2 invalidated; V3 required |

Allowed actions: `ADD`, `CLARIFY`, `RECLASSIFY`, `SUPERSEDE`, `RETIRE`, `VERIFY`, `INVALIDATE`, `REOPEN`.

For an unrecorded requirement change, use `OPEN` as the claim lane/state, cite the observed delta, and set the rationale to `Missing Trellis decision`; do not represent it as approved intent.

## Negative Evidence

| Question | Search boundary | Result | Consequence |
|---|---|---|---|
| ... | files/symbols/history checked | Not found | Section remains open |

## Regeneration

- Resolve the same Trellis task.
- Read the prior generated document's generation ledger, claim ledger, and change trace when refreshing.
- Re-read the listed task artifacts and manifests.
- Re-inspect current source/test anchors.
- Re-run only the checks needed for `VERIFIED` claims.
- Rebuild the claim ledger, preserve or supersede stable IDs, then append one generation row and only semantic change events before updating prose.
```

## Rendering Guidance

- Keep prose readable; use compact handles rather than full citations after every sentence.
- Resolve every handle in the source map or claim ledger.
- Prefer symbols and test names over line-only anchors.
- Keep decisions and observations in separate paragraphs when they differ.
- A generated document may be complete, partial, or stale; state which one it is.
- Do not include hidden reasoning. Record claims, sources, conflicts, and observed checks only.
- Preserve compact lineage, not full prior prose or document snapshots.
- Do not invent a rationale: requirement-changing events without a Trellis decision remain `OPEN`.
- Keep evidence lane, trace state, and verification freshness as separate fields.
