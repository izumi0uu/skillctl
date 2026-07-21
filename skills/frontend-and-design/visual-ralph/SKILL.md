---
name: visual-ralph
description: Execute an already approved Trellis-backed frontend task through Ralph using a typed visual-baseline artifact, deterministic screenshot cases, structured vision verdicts, and capture-time workspace evidence. Use for UI implementation, restyling, responsive matching, or authorized live-URL reconstruction when visual fidelity is an acceptance requirement.
metadata:
  short-description: Deliver approved UI with measured visual evidence
---

# Visual Ralph

Visual Ralph is a visual execution profile for `$ralph`. It adds deterministic
capture, comparison, and visual evidence gates; it does not plan, import tasks,
own lifecycle state, or replace Ralph's execution loop.

## Architecture Boundary

```text
Plan / Ralplan -> neutral Plan Bundle + visual-baseline/v1
Trellis adapter -> persistence, lifecycle, progress, evidence
Ralph -> implementation and completion loop
Visual Ralph -> visual-case execution and verdict quality
```

- `$plan` or `$ralplan` owns baseline authoring, user approval, requirements,
  artifact bindings, acceptance, and implementation sequencing.
- `$trellis-plan-adapter` exclusively owns Trellis persistence, progress,
  evidence, recovery, and lifecycle.
- `$ralph` owns implementation pressure, concurrency gates, and completion.
- Visual Ralph owns only deterministic visual capture and verdict production.

Load `$ralph` before any task action. Visual Ralph must not inspect Trellis
paths, task metadata, active-task pointers, evidence files, or lifecycle
scripts. It must not create checkpoints, ledgers, retry state, or a fallback
task system. All durable progress and evidence flow through Ralph's adapter
boundary.

## Use Visual Ralph When

- an approved UI reference must be implemented or matched
- responsive layouts require evidence at named viewports
- a component or page restyle needs measurable visual acceptance
- an authorized live URL supplied an immutable captured baseline
- reusable tokens or component variants are part of acceptance

Use a direct edit for a small visual fix that does not need a persistent task.
Use `$plan` or `$ralplan` when the visual artifact contract is missing, blocked,
or stale. Do not use this skill for backend-only work, design advice without
implementation, or deterministic vector-asset generation.

## Planning Prerequisite

Visual Ralph requires an imported, ready Plan Bundle containing an `artifacts`
entry with:

- `kind: visual-baseline`
- `schema: visual-baseline/v1`
- `schema_ref: { kind: skill, skill_id: visual-ralph, path:
  references/visual-baseline-v1.schema.json }` plus its RFC 8785 JCS SHA-256
  schema digest
- approved baseline ID, revision, repo-relative manifest path, and RFC 8785 JCS
  SHA-256 digest
- one artifact gate for every visual case
- `metric: visual-score`, `operator: gte`, and the approved threshold
- exact acceptance and verification coverage plus threshold rationale

The referenced manifest must conform to
`references/visual-baseline-v1.schema.json`. Its case keys, thresholds,
rationales, and coverage must match the Plan Bundle gates exactly.

If any prerequisite is missing, stop before source edits and return a planning
blocker. Visual Ralph does not generate references, request approval, invoke
`$plan` or `$ralplan`, create/import a task, or repair a planning artifact.

## Ralph Entry Gate

1. Run only the read portion of Ralph's entry gate through the adapter:
   `load_active_task()` followed by the approved-contract read. Do not start the
   task yet.
2. Retain task ID, revision, and digest as Ralph's concurrency token.
3. Validate the Plan Bundle artifact entry, baseline schema, manifest digest,
   approved status, case keys, artifact hashes, and gate coverage.
4. Require immutable captured references. A source URL alone is never a
   baseline.
5. If the baseline or Plan Bundle changed, request replan instead of repairing
   it during execution.
6. Continue with Ralph's start or resume gate only with its required execution
   authorization.

The approved contract and adapter-returned effective progress are the only
execution source of truth.

## Deterministic Case Contract

Each approved case fixes:

- reference artifact path, SHA-256, and dimensions
- route and named content state
- viewport and device scale factor
- browser name/version and platform name/version
- font policy, color scheme, locale, and timezone
- authentication and data fixtures
- readiness signal
- motion and network policies
- capture tool, procedure ID, command when applicable, mode, and clip geometry
- interaction states, exclusions, threshold, rationale, and AC/VER coverage

Reject unknown dynamic data, mutable assets, blank captures, unspecified fonts,
implicit viewport defaults, or undocumented environment substitutions.

## Visual Execution Loop

For each incomplete visual step:

1. Inspect the implementation and existing tests before editing.
2. Establish the approved route, fixtures, interaction state, network policy,
   and readiness signal.
3. Start the application using repository-supported commands.
4. Make one bounded implementation change through Ralph.
5. Re-read Ralph's normalized execution view immediately before capture and
   retain the adapter-reported relevant workspace fingerprint.
6. Capture the candidate with the exact approved environment and dimensions.
7. Reject blank, errored, redirected, loading, consent-blocked, or environment-
   incompatible captures as `inconclusive`.
8. Compare immutable reference and candidate hashes with a vision-capable
   evaluator.
9. Produce `visual-verdict/v1` using
   `references/visual-verdict-v1.schema.json`.
10. Ask Ralph to record the verdict through the adapter with artifact gate,
    acceptance, and verification IDs plus baseline, reference, candidate,
    verdict, and optional diff hashes.
11. If the case fails, turn the highest-severity differences into one bounded
    edit hypothesis and continue Ralph's loop.
12. Mark the step complete only after all assigned cases have current passing
    evidence.

The verdict must carry the fingerprint captured before the screenshot. The
adapter recomputes the fingerprint when recording evidence and rejects a
mismatch as replayed evidence. Never restamp an old screenshot or verdict with
a newer workspace fingerprint.

## Verdict Semantics

Validate the JSON schema, then have the adapter recompute these semantic gates:

- `threshold_met` equals `score >= threshold`.
- `threshold_met` is an untrusted derived claim; reject rather than rewrite a
  submitted value that differs from the recomputed result.
- `passed` requires `threshold_met: true`, `category_match: true`, exact
  baseline/environment binding, and no unresolved high-severity difference.
- `failed` means the capture is valid but one or more visual gates are unmet.
- `inconclusive` means capture or comparison cannot support a visual claim; it
  never satisfies acceptance.
- bundle ID/revision/digest and baseline ID/revision/digest match the approved
  Plan Bundle artifact contract.
- reference hash, case threshold, rationale, and coverage match the baseline.
- capture-time fingerprint equals the adapter's current relevant workspace
  fingerprint when evidence is recorded.

Use a fresh vision evaluator for the final verdict when supported. Record the
evaluator kind, identifier, and independence instead of inventing unavailable
independence.

The visual score does not prove functionality, accessibility, responsive
behavior outside approved cases, or interaction correctness. Keep those as
separate Plan Bundle acceptance criteria and evidence.

## Pixel Diff

Pixel diff is optional secondary diagnostic evidence. Use it only when
reference and candidate geometry and rendering conditions are comparable.

- Do not derive semantic score directly from mismatch ratio.
- Account for fonts, anti-aliasing, animations, dates, random data, and browser
  differences before interpreting hotspots.
- Record diff path, hash, and mismatch ratio when generated.
- Do not add an image-diff dependency unless the repository already uses it or
  the approved plan explicitly permits it.

## Reusable UI Output

Meet the target through existing component and token patterns. Extend approved
colors, spacing, typography, radii, shadows, and state variants when required.
Do not create a parallel design-system layer for a one-off match or rewrite
shared tokens without an approved contract change.

## Replan Conditions

Stop source edits and use Ralph's replan rule when:

- baseline, route, viewport, state, threshold, rationale, or exclusions change
- a reference conflicts with accessibility, functionality, or platform rules
- required fonts, assets, fixtures, credentials, or third-party states are
  unavailable
- scope expands to new pages, cases, breakpoints, or interaction parity
- implementation reveals an uncovered shared design-system or public component
  contract

Do not lower thresholds, crop away differences, hide content, replace
references, or narrow cases to obtain a pass.

## Completion Gate

Visual completion requires:

- every artifact gate has current-fingerprint passing verdict evidence
- baseline, reference, candidate, verdict, and optional pixel-diff hashes are
  recorded
- all non-visual acceptance criteria also pass
- required responsive and interaction states were captured
- repository build, lint, typecheck, and tests pass where applicable
- reusable UI deliverables required by the contract are present
- final diff contains no unrelated changes, debug overlays, or weakened tests
- remaining accepted differences are explicit in the approved contract

Build the visual portion of Ralph's completion audit, then let Ralph submit the
full audit through `finish_task()`. Visual Ralph never commits, pushes,
releases, archives, or finishes lifecycle state without Ralph's separate
authorization boundary.

## Output

Report the active case, latest score and semantic status, highest-severity
differences, evidence IDs, artifact paths, capture fingerprint, commands run,
and whether Ralph can continue, must replan, or is ready for completion. Do not
report success from visual score alone.

<!-- skillctl:source-attribution:start -->
## Source Attribution

- origin kind: derived-from-upstream
- upstream repo: Yeachan-Heo/oh-my-codex
- upstream path: skills/visual-ralph
- pinned ref: 456effa2afcb7967e8ba7130ee15b2835c235d72
- source type: github
- source URL: https://github.com/Yeachan-Heo/oh-my-codex/tree/v0.20.0/skills/visual-ralph
- imported at: 2026-07-14T00:44:11.266Z
- last verified ref: 456effa2afcb7967e8ba7130ee15b2835c235d72
- local modifications: true
<!-- skillctl:source-attribution:end -->
