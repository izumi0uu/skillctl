# Trellis Lite Development Workflow

This project uses Trellis for durable task memory, not as an autonomous delivery
pipeline. The user's current request and repository instructions always outrank
workflow ceremony.

## Core Principles

1. **Keep scope fixed**: implement the accepted outcome only. New defects,
   release work, documentation, or cleanup outside that boundary become a
   follow-up unless the user explicitly expands the task.
2. **Use the lightest process that preserves useful memory**: small changes and
   conversations skip Trellis. Most tracked work needs only a concise `prd.md`.
3. **Implement once, verify once**: do not create an automatic
   implement/check/fix/re-check loop.
4. **Verification is proportional**: the main session or implementer runs the
   narrowest checks that establish the changed behavior. A checker only reviews
   the diff and reported evidence. Full suites, packaged runtime checks, and
   release gates are opt-in for release work, high-risk shared infrastructure,
   or explicit user requests.
5. **Do not repeat evidence**: a passing command remains valid while its relevant
   code is unchanged. Reuse exact results reported by a worker.
6. **Route sub-agents by task shape**: small work stays in the main session.
   Normal tracked work gets one report-only checker. Complex separable work
   defaults to parallel implementers with disjoint ownership, followed by one checker.
   For an active durable task, unclear requirements get one research agent when
   repository evidence can resolve them. Sub-agents never dispatch nested workers.
   Only the main agent dispatches, and every prompt names the active task, exact
   scope, and non-overlapping file or module ownership.
7. **No automatic fix/re-check loop**: checker findings end the verification
   pass. A correction or recheck is a separate main-session follow-up and needs
   explicit user authorization.

## Lite Task Profile

Every task that enters Build must have one user-selected `lite` profile in its
`task.json`. The profile separates implementation scope from verification cost;
do not infer one from the other. A missing or invalid profile blocks
implementation until the user chooses one.

```json
{
  "lite": {
    "change_mode": "P0",
    "verification_level": "V1",
    "checker": "off",
    "allowed_paths": ["frontend/**"],
    "forbidden_paths": ["backend/**", "db/**", "migrations/**", "auth/**"],
    "selected_by": "user"
  }
}
```

### Change modes

| Mode | Use for | Default boundary |
| --- | --- | --- |
| `P0` patch | Small UI, copy, or local behavior | Change the named layer only; reuse existing interfaces; no new backend, contract, dependency, guardrail, or test matrix |
| `P1` feature | A local feature within an existing interface | Allow related modules and a small local abstraction; no speculative cross-layer policy |
| `P2` cross-layer | API, persistence, or frontend/backend contract changes | Cross-layer edits are allowed only when named in the accepted scope |
| `P3` hardening | Auth, data safety, migration, shared core, or release work | Require explicit design, compatibility, rollback, and broad verification |

Existing security, authorization, and data invariants remain mandatory at every
mode. Only newly invented defensive rules are suppressed by `P0`/`P1`.
If the existing interface cannot satisfy a low-mode request, stop and ask to
upgrade the mode; do not silently edit another layer.

### Verification levels

| Level | Allowed evidence | Default checker policy |
| --- | --- | --- |
| `V0` | Diff and acceptance review only; no test command | No checker |
| `V1` | One focused test or static-check pass | No checker |
| `V2` | Focused tests plus affected-package static/build checks, once | One read-only checker when the profile enables it |
| `V3` | Explicit full, integration, E2E, runtime, or release gates, once | Checker only when explicitly selected |

Verification commands are not an invitation to create more scope. Never add a
test suite merely because a new backend guard was imagined. A passing command is
reused while its relevant code is unchanged. Do not automatically raise the
mode, level, checker, or command set after a failure.

The compact pre-start question is: `P0/P1/P2/P3` for change mode and
`V0/V1/V2/V3` for verification level. The user may accept the recommendation
with one reply. Record the answer once in `task.json`; resume the task with the
same profile unless the accepted scope changes.

## Durable State

### Tasks

Tasks live under `.trellis/tasks/`. The active task pointer is session-local.

```bash
python3 ./.trellis/scripts/task.py list
python3 ./.trellis/scripts/task.py current --source
python3 ./.trellis/scripts/task.py use <task>
python3 ./.trellis/scripts/task.py start <task>
```

- Search unarchived tasks before creating one.
- Reuse a task when its core outcome and acceptance boundary still match.
- Create a new task only for a materially different, independently reviewable
  deliverable.
- Small unrelated work that needs no durable handoff skips Trellis without a
  process question.
- A parent groups independently closable deliverables. It must not absorb every
  defect found during implementation.

### Planning Artifacts

- `prd.md`: concise goal, scope, acceptance criteria, and explicit non-goals.
- `design.md`: optional; use only when architecture, compatibility, migration,
  security, or rollback decisions need durable explanation.
- `implement.md`: optional; use only for genuinely ordered or multi-owner work.
- `implement.jsonl` / `check.jsonl`: optional lists of spec and task research
  files. Never list product source, generated output, or large test files.

Planning artifacts are editable. Remove obsolete requirements and superseded
evidence when scope changes; they are not append-only audit logs.

### Specifications And Journals

Read only the specs relevant to touched code. Update `.trellis/spec/` only when
the work creates a reusable convention or prevents a recurring mistake. Journal
and archive operations are explicit wrap-up actions, not prerequisites for
reporting that implementation is complete.

## Verification Budget

Default budget per requested change:

| Change risk | Default verification |
| --- | --- |
| Docs, copy, or configuration | Relevant syntax/static check only, when one exists |
| Small single-module behavior | Focused regression/unit test; relevant lint or type check when needed |
| Normal multi-file behavior | Focused tests plus the affected package's type/lint check |
| Shared core, migration, auth, data safety | Broader affected-package checks justified by the risk |
| Release candidate | Full release/runtime/package gates only after explicit release scope |

Rules:

- Do not run a full repository suite merely because Trellis is active.
- Do not rerun the same passing command unless relevant code changed.
- A check agent is runtime-read-only and reviews/reports only. It never edits,
  runs commands, or changes task/spec/session state.
- A failed check ends the pass and is reported. Do not fix or rerun until the
  user explicitly authorizes that follow-up.
- Newly discovered out-of-scope defects are recorded as follow-ups; they do not
  silently expand the current PRD.

## Phase Index

```text
Phase 1: Plan    -> reuse or create only when durable task memory is useful
Phase 2: Build   -> implement the requested change once, then verify once
Phase 3: Close   -> report; update spec, commit, or archive only when useful/requested
```

### Request Triage

- No selected task does not mean no matching task exists. Inspect unarchived
  tasks before proposing creation.
- If one task clearly owns the outcome, select it with `task.py use` and preserve
  its status.
- If several tasks plausibly match, ask which one owns the work.
- If no task matches, create one only when durable planning or handoff value
  justifies it and the user approves creation.
- For a small fix, direct question, or short isolated edit, skip Trellis.

[workflow-state:no_task]
No task is selected. For small work, proceed without Trellis. For durable work,
list unarchived tasks and reuse one clear match. Ask only when several tasks
match or a genuinely new task needs creation approval. Never create a task just
because this is a new session.
[/workflow-state:no_task]

### Phase 1: Plan

- 1.0 Resolve task `[optional - once]`
- 1.1 Define minimum scope `[required - once]`
- 1.2 Research `[on demand]`
- 1.3 Configure context `[optional - once]`
- 1.4 Activate task `[required when a task is used - once]`

[workflow-state:planning]
Keep planning proportional. A concise PRD is normally enough. Add design or an
implementation plan only for real architectural/order risk. JSONL context is
optional and may contain only spec/research files. When substantial repository
research can resolve uncertainty independently, dispatch one bounded research
agent by default after the durable task is selected; the main session owns
product questions and the final scope.
Before `task.py start`, ask once for the Lite profile: change mode (`P0`-`P3`),
verification level (`V0`-`V3`), and whether a read-only checker is wanted.
Write the selected profile under `task.json.lite` and include allowed and
forbidden path boundaries when the task is scoped to a layer. Do not start
implementation while the profile is missing or ambiguous.
Ask for implementation approval once the minimum scope is testable; do not keep
brainstorming after remaining questions no longer block the requested outcome.
[/workflow-state:planning]

[workflow-state:planning-inline]
Keep planning proportional. A concise PRD is normally enough. Add design or an
implementation plan only for real architectural/order risk. Inline mode does
not require JSONL curation. Use one bounded research agent when substantial
repository evidence can resolve uncertainty and a durable task is active; keep
product choices in the main session. Ask for implementation approval once the
minimum scope is testable.
Before editing, ask once for and record the Lite profile under `task.json.lite`:
change mode (`P0`-`P3`), verification level (`V0`-`V3`), checker choice, and
optional allowed/forbidden paths. Do not infer a cross-layer change from a
frontend-only request.
[/workflow-state:planning-inline]

### Phase 2: Build

- 2.1 Implement `[required - once per requested slice]`
- 2.2 Verify `[required - once after the slice is complete]`
- 2.3 Handle checker findings `[explicit user follow-up]`

[workflow-state:in_progress]
Resume the next incomplete requirement; do not restart completed work. Read and
obey the selected `task.json.lite` profile before every implementation turn.
The main session implements normal tracked work. For complex separable work, dispatch
parallel implementers by default only after assigning non-overlapping files or
modules; the main session integrates their results. After tracked implementation,
dispatch one report-only checker only when the profile allows it. P0/P1 work
must not add backend guards, API contracts, dependencies, broad refactors, or
test matrices outside the accepted scope. Reuse passing results while relevant
code is unchanged. The main session may make a targeted correction only after
the user explicitly authorizes a follow-up; it never starts another checker or
fix/re-check wave automatically. Then report. Spec updates, commits, release
gates, and archive are not automatic.
[/workflow-state:in_progress]

[workflow-state:in_progress-inline]
Resume the next incomplete requirement; do not restart completed work. Read and
obey `task.json.lite` before editing. Implement small inline work in the main
session. For normal or complex tracked work, use the same task-shape routing as
`in_progress`, but only dispatch the report-only checker when the selected
profile allows it. P0/P1 requests stay in their named layer and do not grow
speculative backend policy. Reuse passing results while relevant code is
unchanged. Checker findings end the pass; correction and recheck require an
explicit user follow-up. Then report. Spec updates, commits, release gates,
and archive are optional explicit actions.
[/workflow-state:in_progress-inline]

### Phase 3: Close

- 3.1 Report outcome `[required - once]`
- 3.2 Update durable spec `[optional]`
- 3.3 Commit or archive `[on user request]`

[workflow-state:completed]
Implementation has been reported. Do not run more checks or create more work
unless relevant code changed or the user requests another scope. Commit and
archive remain explicit actions.
[/workflow-state:completed]

## Phase 1: Plan

#### 1.0 Resolve task `[optional - once]`

Use Trellis only when the work benefits from durable scope or handoff.

1. Run `task.py current --source` and `task.py list`.
2. Reuse one clear outcome match with `task.py use <task>`.
3. Ask the user when several tasks plausibly match.
4. Create only a genuinely new durable task after consent.
5. Skip this step for small work.

#### 1.1 Define minimum scope `[required - once]`

Record only what is needed to implement and verify the requested outcome:

- goal and user-visible result;
- acceptance criteria;
- important constraints;
- explicit non-goals and deferred findings.

Do not preserve obsolete criteria merely because they appeared in an earlier
brainstorm. Do not turn implementation discoveries into new requirements
without user approval.

#### 1.2 Research `[on demand]`

Inspect repository evidence before asking the user. Persist research only when
another session or worker would otherwise repeat substantial work. Stop when the
decision needed for the current scope is supported. If the requirements are
unclear and repository research is a substantial independent slice, dispatch
one `trellis-research` agent by default after selecting the durable task. Before
task selection, the main session performs only the minimum research needed to
route the request. Do not delegate product choices or start multiple speculative
research branches.

#### 1.3 Configure context `[optional - once]`

Use JSONL context only for a delegated agent that needs durable spec/research
references. Entries must point under `.trellis/spec/` or the active task's
`research/` directory. Product code and tests are read on demand by the agent.

#### 1.4 Activate task `[required when a task is used - once]`

Review the minimum artifacts, then run:

```bash
python3 ./.trellis/scripts/task.py start <task>
```

Starting authorizes implementation of the accepted scope. It does not authorize
automatic release work, broad review, commits, or publication.

## Phase 2: Build

#### 2.1 Implement `[required - once per requested slice]`

Read the active task artifacts, relevant specs, and `task.json.lite`, then
implement the smallest coherent change allowed by the selected mode. The main
session owns integration. For normal tracked work the
main session implements. For complex work with two or more independent slices,
dispatch implementers in parallel by default only after naming non-overlapping
file or module ownership. Small work stays in the main session. No Trellis
sub-agent may dispatch another worker. Each dispatch names the active task,
acceptance slice, allowed ownership, and expected report.

P0/P1 implementers must not change paths outside the profile, broaden an API,
invent backend guardrails, add dependencies, or create a test matrix. If a
profile boundary blocks the requested outcome, stop and ask for a mode change.
Any verification command counts against the selected level and must be reported
exactly; do not repeat it unless relevant code changed and the user authorized a
follow-up.

#### 2.2 Verify `[required - once after the slice is complete]`

Choose checks from the selected verification level and the Verification Budget
in the main session or implementer. `V0` runs no commands; `V1` runs one
focused pass; `V2` runs the named affected-package checks once; `V3` runs only
the explicitly selected broad gates once. The checker reviews the current
requested slice, not every historical dirty path or every unchecked criterion
in a parent epic.

Default behavior:

1. Inspect the relevant diff and acceptance criteria.
2. Run the narrowest behavior test plus relevant static check in the main session
   or implementer.
3. Record exact commands and results before dispatching the checker.
4. Dispatch the checker for a read-only evidence review and report its findings.

For `V2` or an explicitly selected `V3` profile, dispatch at most one
`trellis-check` agent. It is runtime-read-only: the prompt must state the
profile, acceptance criteria, changed-path boundary, and exact checks already
run. It must not be given lifecycle commands or edit authority. `P0/P1` with
`V0/V1` remains main-agent-only. If the runtime has no sub-agent capability,
the main session performs the same single pass.

#### 2.3 Handle checker findings `[explicit user follow-up]`

When a required check fails, report it and stop the verification pass. If the
user explicitly asks to fix it:

1. diagnose the root cause;
2. make one targeted correction within the accepted scope;
3. rerun only the failed check and any directly invalidated focused check;
4. report the result without starting another loop.

The main session owns this correction. The checker cannot make it, even when a
dispatch prompt asks for a bounded fix. Do not weaken a check, broaden scope,
spawn another verification wave, or start release gates to obtain a green
result.

## Phase 3: Close

#### 3.1 Report outcome `[required - once]`

Report changed files, observable behavior, exact verification results, and any
remaining blocker or deferred follow-up. Completion does not require a clean
working tree when unrelated user work exists.

#### 3.2 Update durable spec `[optional]`

Update `.trellis/spec/` only for a reusable convention, invariant, or recurring
failure prevention rule. Task-specific evidence stays in the task. Skip this
step when no durable project guidance changed.

#### 3.3 Commit or archive `[on user request]`

Commit, archive, journal, push, and release operations require their normal
explicit authorization. They are not automatically implied by passing checks or
by the word `continue`.
