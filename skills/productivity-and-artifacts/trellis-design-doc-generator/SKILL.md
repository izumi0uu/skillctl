---
name: trellis-design-doc-generator
description: Use this skill to generate a concrete team-shared design document from an approved Trellis task, or to reconstruct, refresh, audit, and trace a current or evolving design view from Trellis and repository evidence. Shared design is the default; audit mode is explicit. Never invent or approve unrecorded product decisions.
---

# Trellis Design Document Generator

## Purpose

Generate evidence-backed design documentation from a native Trellis task and the relevant repository state.

The skill has two output modes:

| Mode | Audience and job | Output |
|---|---|---|
| `shared` | Product, frontend, backend, quality assurance, and reviewers need a design they can understand and implement | Standalone business and technical design contract |
| `audit` | Maintainers need reconstruction, drift analysis, provenance, verification freshness, or change lineage | Current, evolving, or historical evidence view |

`shared` is the default. Output mode changes presentation, not truth standards.

This skill writes documentation only. It must not modify product source or authorize requirement changes.

## Use this skill for

### Shared design

- Generating or refreshing a design document from an approved Trellis task
- Creating a team-facing, stakeholder-facing, Crit-style, or implementation-ready proposal
- Explaining business rules, user workflows, data relationships, APIs, lifecycle, edge cases, acceptance criteria, and implementation order
- Producing a handoff for product, frontend, backend, and quality assurance

### Audit design

- Rebuilding a deleted or disposable design document
- Refreshing after implementation drift or requirement changes
- Auditing whether Trellis and repository evidence can regenerate the design
- Producing a current, evolving, or historical view
- Preserving claim lineage, semantic changes, verification freshness, and unresolved drift

## Do not use this skill for

- Designing a new feature before its decisions are approved
- Exact byte-for-byte recovery of a deleted historical document
- Treating chat memory as the sole source of truth
- Hiding unresolved product decisions behind plausible prose
- Rewriting product code to make documentation appear consistent
- Publishing a document externally without user intent

## 1. Resolve the Trellis task

Use this order:

1. Task path explicitly supplied by the user
2. Active task supplied by the current Trellis or session context
3. A supported local Trellis command that lists or resolves tasks

Do not guess when multiple tasks could match. If no task can be identified, stop with a concrete blocker.

## 2. Select exactly one output mode

Resolve mode before loading a rendering template.

### Select `shared`

Use `shared` when the user asks to:

- generate, write, update, or refresh a design document without an audit qualifier
- share a design with a team or stakeholders
- create a Crit-style document
- create an implementation proposal or cross-functional handoff
- explain a feature's product and technical contract

If the request is ambiguous, select `shared`.

### Select `audit`

Use `audit` only when the user explicitly asks for:

- reconstruction or regeneration of a deleted or stale design
- a current, evolving, or historical evidence view
- implementation drift analysis
- provenance, traceability, claim lineage, or semantic history
- branch, HEAD, dirty-workspace, or verification-basis evidence
- proof that the design can be regenerated from Trellis

### Explicit override

An explicit `shared` or `audit` request wins. Never merge both templates into one hybrid document.

When the user requests both outputs, generate two separate artifacts with separate completion reports.

## 3. Load the common evidence basis

Read, when present:

1. `task.json`
2. `prd.md`
3. `design.md`
4. `implement.md`
5. every file listed in `implement.jsonl` and `check.jsonl`
6. relevant research artifacts
7. `relatedFiles` and source anchors named by task artifacts

A referenced source-design document is optional. If it is missing, continue from surviving evidence and record the missing source only in audit output or the internal research process.

Chat history may help locate evidence. It cannot be the only source for a durable product rule.

## 4. Research before writing

Use Trellis anchors to inspect only relevant surfaces:

- persisted data shape and migrations
- models, schemas, public interfaces, and events
- routes, services, repositories, lifecycle, and state transitions
- authorization, tenant, privacy, and destructive-operation boundaries
- async work, callbacks, storage, and external integrations
- frontend data flow and user interaction
- focused tests and fixtures
- Git history only when it explains a recorded decision or divergence

Prefer symbol-aware navigation for code relationships. Prefer test names and symbols over line-number-only references.

Record internally what was searched but not found. Absence is evidence only within an explicit search boundary.

## 5. Reconcile evidence before rendering

Keep these evidence meanings separate during research:

| Lane | Meaning | Typical sources |
|---|---|---|
| `DECISION` | Intended or approved product rule | Trellis PRD, design, accepted decision record |
| `OBSERVED` | Current implementation behavior | Models, schemas, routes, services, UI, migrations |
| `VERIFIED` | Behavior observed in a current check | Test or command output from this workspace |
| `HISTORICAL` | Earlier behavior or rationale | Git commits, archived evidence, journals |
| `INFERENCE` | Reasonable interpretation not directly established | Cross-source synthesis |
| `OPEN` | Missing evidence or unresolved conflict | Conflict and negative evidence |

A decision and current implementation may disagree. Preserve both during research. Tests establish observed behavior; they do not automatically approve intended semantics.

The current Trellis decision record remains authoritative intent. The generated document cannot approve a requirement change.

When sources conflict:

1. Identify each position and its evidence
2. Identify user or system impact
3. Check whether a later Trellis decision resolves the conflict
4. If unresolved, keep it open

In shared output, explain unresolved conflicts as reader-facing decisions without evidence handles. In audit output, retain the full evidence and conflict lineage.

## 6. Render `shared` mode

Read `references/shared-design-document-template.md`. Do not read or copy the audit template unless the user separately requested an audit artifact.

Write a self-contained design contract. Use the applicable sections:

- purpose, status, business goal, and user value
- user-visible workflow
- rules, options, defaults, composition, and precedence
- data relationships and domain model
- data model, constraints, retention, and migration
- API contracts with concise synthetic examples
- lifecycle, state transitions, transaction boundaries, retry, and concurrency
- scope or capability matrix
- security, tenant, privacy, logging, and destructive operations
- frontend behavior and failure states
- edge cases
- observable acceptance criteria
- dependency-ordered implementation sequence
- compatibility, cutover, and rollback
- open decisions only when unresolved

Prefer concrete examples, tables, state flows, and request/response shapes over abstract architecture prose.

### Shared-output boundary

Do not include:

- source maps, evidence receipts, claim IDs, or claim ledgers
- generation ledgers, semantic manifests, or regeneration instructions
- task paths, repository source/test paths, branch, HEAD, or dirty-workspace state
- Figma file IDs, node IDs, screenshot coordinates, or visual-evidence citations
- raw tool output, command receipts, or agent process notes

Keep domain identifiers that define the contract: API paths, table and field names, enums, states, event names, public types, limits, and error codes.

State whether the document describes target behavior, current behavior, or a mix. Do not cite internal evidence inline.

### Shared output location

Use this order:

1. Explicit user-provided path
2. Shared-document path recorded in the Trellis task
3. Requested replacement path
4. Otherwise `<task-path>/research/shared-design.md`

Do not overwrite an unrelated hand-written canonical contract.

### Shared validation

Before completion:

- every normative rule has an approved decision source
- current-behavior statements have repository evidence
- unresolved conflicts remain visible in reader language
- the document is concrete and self-contained
- no internal path, Figma identifier, evidence handle, or generation metadata appears
- API and domain identifiers remain intact
- examples are synthetic
- no protected health information, secrets, tokens, or sensitive fixtures appear
- external publication occurred only when requested

If one section lacks evidence, produce the remaining useful document and label only that section as open or partial.

## 7. Render `audit` mode

Read all audit references:

- `references/audit-design-document-template.md`
- `references/reconstruction-checklist.md`
- `references/traceability-model.md`

### Establish the generation basis

Record:

- repository root
- task path and status
- branch and HEAD
- clean or dirty workspace and relevant local changes
- generation timestamp and output path
- generation ID
- parent generation ID and prior generated document when refreshing
- submode: `current-view`, `evolving-view`, or `historical`

Use `current-view` by default within audit mode. Use `evolving-view` during implementation or when trace retention is requested. Use `historical` only when explicitly requested.

A dirty workspace is valid evidence, but the document must say that it represents the workspace snapshot rather than clean HEAD.

### Build the claim ledger before prose

For each design topic, collect:

- stable claim ID
- evidence lane
- lifecycle: active, superseded, retired, or open
- evidence freshness: current, stale, broken, or not-run
- concise current statement
- evidence handles and source revision or fingerprint
- first-seen and last-changed generation
- predecessor/successor and conflict-group IDs when relevant
- workspace freshness basis
- confidence or refusal note when evidence is incomplete

Keep contradictory claims. Do not overwrite one with another.

### Reconcile previous generations

When refreshing:

- read the previous generation ledger, claim ledger, and change trace
- reuse claim IDs when semantic meaning is unchanged
- create a successor ID when product or behavioral meaning changes
- record `supersedes` and `superseded_by`
- emit only `ADD`, `CLARIFY`, `RECLASSIFY`, `SUPERSEDE`, `RETIRE`, `VERIFY`, `INVALIDATE`, or `REOPEN`
- count unchanged claims without emitting one event per unchanged claim
- require a Trellis decision anchor for requirement changes
- preserve unrecorded changes as `OPEN — unrecorded requirement change`
- keep tombstones compact and never retain full prior prose snapshots

If a prior generated document is missing, start a new trace chain and mark the parent link broken.

### Audit output location

Use this order:

1. Explicit user-provided path
2. Audit output path recorded in the Trellis task
3. Requested replacement path
4. Otherwise `<task-path>/research/generated-design.md`

Do not overwrite an existing document unless the user asked to refresh or replace it.

### Audit validation

Enforce the reconstruction checklist. At minimum:

- normative, observed, verified, historical, inferred, and open statements retain their correct evidence meaning
- every `VERIFIED` claim has a current observed check
- contradictions and negative-evidence boundaries remain visible
- branch, HEAD, dirty state, generation identity, and parent chain are recorded
- stable claim IDs are reused or superseded correctly
- no prior active claim disappears without a trace event or broken-chain note
- no deleted source document is required to understand the output
- no protected health information, secrets, tokens, or sensitive fixture data are copied
- the document does not claim exact historical restoration

## 8. Evidence and safety rules for both modes

- Explicit Trellis decisions are intent, not proof of implementation
- Current code is implementation evidence, not automatic product approval
- Current tests are executable evidence, not universal coverage
- Git history explains change; it does not override current state
- Existing design documents are comparison inputs, not unquestioned authority
- A hash or path proves identity only while referenced content exists
- Provider-selected or user-selected values must not become free-form system instructions unless the product contract explicitly allows it
- Never copy protected health information, credentials, tokens, raw transcripts, or sensitive fixture data into generated documentation

## 9. Tools to prefer

- Supported Trellis lifecycle and context commands for task resolution
- Scoped file reads for task artifacts and named anchors
- Symbol-aware navigation for definitions, references, and call sites
- Structured search for plain-text facts
- Git history for dated rationale and implementation evolution
- Targeted verification only when claiming current behavior as verified

Avoid broad repository scans, speculative source discovery, and copying large source files into the document.

## 10. Completion report

### Shared

Return:

- generated document path
- whether it describes target, current, or mixed behavior
- major sections produced or refused
- unresolved decision count
- validation performed
- share URL only when publication was requested and completed

### Audit

Return:

- generated document path
- task and workspace basis
- sections produced or refused
- conflict/open-decision count
- verification performed
- whether the document is current, stale, or partial
- generation ID, parent generation ID, and trace-chain status
- counts of added, clarified, superseded, retired, reopened, invalidated, and unchanged claims
- exact blocker when full regeneration was not possible

## Quality bar

### Shared

A reader who did not participate in planning can:

- explain the business goal and user workflow
- understand the data relationships and public contracts
- implement the main flows and edge cases
- identify security, tenant, privacy, and failure boundaries
- verify observable acceptance criteria
- see unresolved decisions without reading agent evidence artifacts

### Audit

A maintainer who never saw the deleted source document can:

- understand intended and observed behavior separately
- locate implementation and tests
- see unresolved drift
- explain what changed, why it changed, and which decision authorized it
- regenerate the document from the same evidence class

The goal is trustworthy design communication. Shared mode optimizes for readers; audit mode optimizes for traceability.
