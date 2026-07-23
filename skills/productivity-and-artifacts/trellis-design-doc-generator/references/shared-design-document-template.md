# Shared Design Document Template

Use this rendering guide only in `shared` mode. The document is a standalone design contract for product, frontend, backend, quality assurance, and reviewers. Follow the user's language.

Do not copy every section mechanically. Keep only sections that help a reader understand, implement, or review the feature. Never invent content to fill the template.

```markdown
# <Feature> design

This document defines <what the feature does>, <who it serves>, and <which behavior is target versus already live>.

## 1. Business goal

Explain the problem, user value, and product boundary in direct language.

- What the user can do
- What changes
- What must not change

## 2. User workflow

Describe the user-visible sequence as numbered steps.

1. The user starts from ...
2. The system ...
3. The user confirms ...
4. The system persists or returns ...

## 3. Rules and options

Use tables for controlled choices, defaults, precedence, and composition.

| Option | Meaning | Applies to |
|---|---|---|
| ... | ... | ... |

Include concrete combination examples when independent settings can interact.

## 4. Defaults and ownership

State:

- product defaults
- who owns the data
- whether missing data means default behavior
- whether tenant, user, record, or operation overrides exist

## 5. Data relationships

Use a compact text or Mermaid diagram.

```text
Parent
└── Owned record
    ├── Child A
    └── Child B
```

Explain what each entity represents and how readers query or identify it.

## 6. Data model

Show only contract-relevant columns and constraints.

```sql
CREATE TABLE example (
    id         uuid PRIMARY KEY,
    tenant_id  uuid NOT NULL,
    created_at timestamptz NOT NULL
);
```

Explain uniqueness, indexes, retention, migration, and cleanup behavior when relevant.

## 7. API

List the public surface first.

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/v1/example` | Read the effective state |
| PUT | `/api/v1/example` | Replace the state |

For each non-trivial endpoint, include:

- request example
- response example
- defaults
- validation
- authorization
- error behavior

Keep examples synthetic and omit irrelevant fields.

## 8. Lifecycle and state transitions

Describe creation, update, retry, regeneration, deletion, or recurrence as a flow.

```text
Start
  ↓
Validate
  ↓
Persist
  ↓
Trigger dependent work
```

State transaction boundaries and irreversible steps.

## 9. Concurrency, retry, and consistency

Define:

- stale-write or last-write behavior
- idempotency
- snapshot timing
- retry reuse versus re-resolution
- atomic versus eventually consistent work

## 10. Scope or capability matrix

Use a matrix when behavior differs by report type, role, state, provider, platform, or integration.

| Scope | Capability A | Capability B | Exception |
|---|---:|---:|---|
| ... | yes | no | ... |

## 11. Security, tenant, privacy, and destructive operations

State:

- who may act
- how tenant and owner boundaries are enforced
- what data is sensitive
- what may enter logs
- what deletion removes
- what failure must leave unchanged

## 12. Frontend behavior

Define behavior, not design-tool provenance.

Include the applicable states:

- loading
- empty
- dirty and clean
- save success and failure
- reset or delete confirmation
- navigation with unsaved changes
- permissions and role visibility
- accessibility
- mobile and desktop semantics

Do not include Figma file IDs, node IDs, screenshot coordinates, or pixel evidence unless the user explicitly requests a visual implementation specification.

## 13. Errors and edge cases

| Scenario | Expected behavior |
|---|---|
| Missing record | ... |
| Invalid input | ... |
| Concurrent update | ... |
| Downstream failure | ... |
| Wrong tenant | ... |

## 14. Acceptance criteria

Group observable outcomes by surface.

### Domain or backend

- ...

### Frontend

- ...

### Security and privacy

- ...

### End to end

- ...

## 15. Implementation order

List the dependency-ordered delivery sequence.

1. Persisted model and constraints
2. Domain service and API
3. Runtime integration
4. Frontend behavior
5. End-to-end verification and rollout

## 16. Future compatibility or migration

Describe cutover gates, compatibility promises, rollback, and what stays stable.

## 17. Open decisions

Include this section only when a real product decision remains unresolved.

| Decision | Why it matters | Recommended option | Alternatives |
|---|---|---|---|
| ... | ... | ... | ... |
```

## Rendering rules

- Write a design contract, not a reconstruction report.
- Prefer concrete workflows, examples, tables, state transitions, and request/response shapes.
- State whether the document describes target behavior, current behavior, or a mix.
- Use product and domain vocabulary consistently.
- Keep API paths, table names, fields, enums, state names, event names, and public type names when they define the contract.
- Translate headings and prose into the user's requested language.
- Omit irrelevant sections instead of adding placeholder prose.
- Keep unresolved decisions visible in reader language.
- Do not claim implementation or verification that was not observed.

## Forbidden shared-output content

Do not include these unless the user explicitly asks for an internal evidence appendix:

- Trellis task paths or artifact filenames
- repository source or test file paths
- Figma file IDs, node IDs, or visual-evidence coordinates
- branch, HEAD, dirty-workspace, or generation metadata
- source maps, evidence receipts, claim IDs, claim ledgers, or negative-evidence ledgers
- generation ledgers, semantic change manifests, or regeneration instructions
- tool transcripts, command output, or agent process notes

Do not remove contract identifiers merely because they look technical. API routes, database identifiers, enums, state names, limits, and error codes belong in a shared technical design when they affect implementation.

## Shared-mode self-check

Before reporting completion, confirm:

- The opening tells readers what the feature does and whether it is target or live behavior.
- A new reader can explain the user workflow and main domain relationships.
- Every normative rule comes from an approved decision.
- Current-behavior claims are grounded in repository evidence.
- Examples are synthetic and contain no protected health information, secrets, or tokens.
- No internal path, evidence handle, Figma identifier, or generation metadata appears.
- The document contains concrete edge cases and observable acceptance criteria.
- External publication occurred only when the user requested it.
