---
name: dap-handoff-writer
description: Write lightweight DAP handoff documents for a feature module, commit range, local diff, PR, or bug surface. Use when Codex should turn implementation context into a debugger-agent handoff with invariants, phase probes, watchpoints, fixtures, expected states, and acceptance criteria, without modifying product source.
---

# DAP Handoff Writer

## Purpose

Create a concise debugger-agent handoff for a specific feature module.

This skill does not implement fixes. It writes a DAP-oriented document that helps another agent inspect runtime state, set breakpoints/watchpoints, reproduce boundary cases, and report first-divergence evidence.

## Inputs To Gather

Prefer concrete anchors:

- Feature or module name.
- Relevant files or directories.
- Commit range, PR, branch, or current local diff.
- Known bug, suspicion, or behavior to verify.
- Existing tests or fixtures.
- Expected product semantics if available.

If the user gives only a module name, inspect the repo enough to identify likely entry points, data flow, tests, and recent commits.

## Output Location

If the user specifies a path, write there.

Otherwise create a markdown file under a local planning/docs area if one exists, preferring:

1. `.omx/plans/dap-<module>-handoff-<timestamp>.md` if the repo already uses `.omx`.
2. `docs/dap/<module>-handoff.md` if `docs/` exists.
3. Return the document in chat if no obvious docs/plans directory exists.

Do not modify product source.

## Workflow

### 1. Establish The Basis

- Record branch, HEAD, commit range, and whether the worktree is clean or dirty.
- If dirty, list changed files and untracked files relevant to the module.
- If a reference commit is supplied, distinguish the reference implementation from later drift.

### 2. Map The Module

- Identify source files, tests, data models, storage/sync/API/UI boundaries, and public entry points.
- Prefer symbol/function names over line numbers because line numbers drift.
- Separate product semantics from implementation guesses.

### 3. Define Invariants

- State what must always be true.
- Include data shape, lifecycle, cache, concurrency, error, and UI-state invariants where relevant.
- Mark uncertain product semantics as questions for DAP instead of pretending they are settled facts.

### 4. Build Phase Probes

Split the feature into runtime phases. For each phase include:

- Primary files.
- Entry points.
- Fixture or scenario.
- Watch values.
- Expected result.
- Likely first-divergence signal.

### 5. Add DAP Watchpoints

- Use function/symbol breakpoints when possible.
- Include variables, refs, snapshots, state machines, cache keys, timestamps, ids, flags, and pending async state.
- Avoid vague instructions like "step through the code" or "inspect state."

### 6. Add Verification Commands

- Start with targeted tests.
- Then add broader regression/typecheck commands only if useful.
- If tests are not known, say how to discover them.

### 7. Define Acceptance Criteria

Require the DAP agent to report:

- Exact commit/worktree basis.
- Scenario or fixture used.
- First divergent function, or "no divergence found."
- Before/after watch values.
- Classification: implementation bug, product semantics question, test gap, or doc drift.
- Minimal suggested fix scope.

The DAP pass should not include product-source patches unless the user explicitly asks for implementation.

## Handoff Template

Use this structure:

````md
# DAP Handoff: <Feature Or Module>

## Basis

- Workspace:
- Branch:
- HEAD:
- Commit range:
- Worktree state:
- Relevant changed files:

## Goal

What the DAP agent should prove or disprove.

## Scope

In scope:

- ...

Out of scope:

- Product-source edits unless explicitly authorized.
- Unrelated refactors.
- Broad exploratory debugging without invariants.

## Module Map

Source:

- ...

Tests:

- ...

Runtime boundaries:

- ...

## Invariants

- ...

## Phase Probes

### Phase 1: <Name>

Primary files:

- ...

Entry points:

- ...

Fixture/scenario:

- ...

Watch values:

- ...

Expected:

- ...

First-divergence signal:

- ...

## DAP Watchpoints

- `<functionOrSymbol>`: watch `<values>`.
- ...

## Suggested Test Commands

```bash
...
````

## Acceptance Criteria

The DAP agent should return:

- Commit/worktree basis.
- Exact fixture/scenario.
- First divergent function, or no divergence found.
- Before/after watch values.
- Classification.
- Minimal suggested fix scope.

## Follow-Up

- Use debugger for diagnosis.
- Use test-engineer only if missing fixtures are needed.
- Use executor only after first-divergence evidence exists.
```

## Quality Bar

A good handoff is executable by another agent without asking "where do I start?"

Avoid:

- Long design history.
- Unverified assumptions stated as facts.
- Line-number-only breakpoints.
- Generic advice like "inspect the state."
- Mixing implementation patches into the DAP handoff.
