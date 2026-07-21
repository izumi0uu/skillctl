---
name: hermes-issue-triage
description: "Use when triaging a Hermes GitHub issue before any fix work: verify the issue against latest upstream/main, distinguish live bugs from already-fixed behavior, duplicates, wrong-premise reports, or local skew, and produce an evidence-backed verdict with concrete next steps."
---

# Hermes Issue Triage

## Overview

Use this skill when the user wants a fast, evidence-backed answer to questions like:
- "这个 issue 还成立吗"
- "有类似 issue / PR 吗"
- "已经修了吗"
- "值得提吗"
- "要不要继续 fix"

This skill is for deciding whether an issue is real on current `main`, not for doing the fix itself. Its job is to separate:
- still-live upstream bugs
- already-fixed behavior
- duplicates or overlapping reports
- wrong-premise reports
- reproduction blocked by local skew or missing environment

If the issue is worth fixing, hand off to `$hermes-upstream-worktree-fix` for clean-worktree reproduction, patching, validation, and PR preparation.

## Use When

- The user links a Hermes issue and wants a verdict before spending time on a fix.
- The user asks whether something is already fixed on latest `main`.
- The user asks whether an issue is duplicated, outdated, or based on a wrong premise.
- The user wants a short closing comment or rationale for closing an issue.

## Do Not Use When

- The user already wants implementation work, reproduction in a clean worktree, or a PR.
- The task is only Hermes worktree hygiene.
- The request is only to draft a PR or issue artifact after a fix is already known.

## Non-Negotiable Boundaries

- Do not call something an upstream bug until latest-`main` evidence rules out obvious version skew.
- Do not trust the issue body's root-cause narrative without checking current source.
- Every material claim must be direct evidence, a clearly labeled inference, or an explicit unknown.
- Prefer proving that a premise is wrong over "half-fixing" a bug report that no longer matches the code.
- If the issue is already fixed on `main`, say so plainly instead of searching for extra work to do.

## Triage Workflow

### 1. Capture the issue facts

- Read the issue title, body, labels, state, dates, and comments.
- Record the exact `upstream/main` commit used for triage.
- Extract the report into concrete claims:
  - user-visible symptom
  - claimed root cause
  - environment constraints
  - expected behavior

### 2. Search for overlap before reasoning too hard

- Check for similar open and closed issues.
- Check for similar open and merged PRs.
- Prefer narrow keyword searches based on the concrete symptom, not only the issue number.
- If a likely overlap exists, compare the actual code path before calling it a duplicate.

#### Existing-PR overlap gate

Before recommending or starting any new fix work, actively search for PRs that
already implement the same bug-class fix, even when they do **not** mention the
current issue number. A newer issue will often not appear in an older PR's body,
timeline, or `Fixes #...` footer, so issue-linked PR lookup is necessary but not
sufficient.

Run both kinds of search:

- Symptom search: use terms from the observed failure, provider/platform, and
  user-visible behavior.
- Code-site search: use implicated file names, function names, tests, and
  mechanisms from the issue or source trace.

#### Local PR-overlap MCP fast path

When the `pr-overlap-index` MCP tools are available, use them before broad
GitHub PR search as a fast local candidate generator:

For P2 triage or archive sweeps, check local index health before making
archive/close recommendations:

1. Call the MCP `health` tool, or run the read-only smoke command if operating
   against the VPS-hosted index:

   ```bash
   PYTHONPATH=<PR_OVERLAP_SERVICE_DIR> \
   PR_OVERLAP_DB=<PR_OVERLAP_DB> \
   python3 -m pr_overlap_index.smoke --runs 5 --top-k 5
   ```

   Confirm `ok`, `initialized`, `schema_version`, and a nonzero or explainable
   `indexed_pr_count`. Inspect `coverage_by_scope`, `archive_confidence_floor`,
   `last_run_by_scope`, `brownout_state`, and smoke `term_coverage` when
   present. Treat `coverage_denominator_kind: "unknown"`, hot-only coverage, or
   incomplete term coverage as a warning: absence from the MCP means "not found
   in the current local index", not "no PR exists in the repository." If the MCP
   is unavailable, uninitialized, stale, or not loaded in the current session,
   say so briefly and fall back to normal GitHub issue/PR search. Do not block
   triage on the MCP.
2. Call `search_pr_overlap` with `repo: "NousResearch/hermes-agent"` plus the
   issue title/body and any extracted files, symbols, provider names, platform
   names, and error messages. Keep `top_k` small (usually 5-10).
3. Inspect `candidate_prefilter` on search results. When
   `candidate_prefilter.reason == "term_match"` and
   `term_indexed_manifest_count == latest_manifest_count`, the candidate list is
   a higher-confidence local-index search because the term prefilter is active
   and complete. If the prefilter is disabled, incomplete, or falling back, keep
   recall concerns explicit and rely more heavily on normal GitHub PR search.
4. Treat MCP results as candidates, not verdicts. For each high-scoring result,
   inspect the PR diff/source path and compare the concrete failure chain before
   classifying the issue.
5. For archive/close decisions, require latest-live archive evidence. Only
   `archive_allowed: true` is direct local evidence that an issue can be
   archived from the MCP result. Prefer `require_fresh: true`; archive-class
   results should be backed by a live fresh lease and replay capsule.
6. `historical_overlap_only`, `needs-refresh`, `partial-cover`, and `adjacent`
   are leads for deeper PR/source review or the pending list. They are not
   direct archive authorization. Historical matches can explain why a bot or
   maintainer saw overlap, but the final decision must be based on current
   PR/source state.
7. `cold_archive` coverage is offline/advisory by default. Do not use a
   cold-only match as an archive basis unless a future explicit cold serving
   gate reports it as active and the result still satisfies the latest-live
   archive evidence rules above.
8. Smoke output is observability, not archive evidence. It proves the local
   index is healthy, fast, and covered enough to use as a candidate generator;
   archive evidence still comes from `search_pr_overlap` result fields such as
   `archive_allowed`, freshness, lease/capsule status, and the inspected PR diff.
9. When reporting MCP evidence, include the coverage scope in plain language
   (for example hot-only, hot+recent, or hot+cold). Do not present a hot-only
   negative result as a full-repository scan.

Keep the MCP query path bounded and local. Do not do an inline all-PR scan from
triage; larger backfills belong to the VPS indexer/scheduler, not to a single
issue-analysis turn.

For each candidate PR, compare:

- same files or functions
- same root cause / state transition / provider or platform boundary
- same failing behavior from the user's point of view
- same or stronger regression test coverage
- PR state: open, draft, blocked, merged, or closed

If an existing PR covers the same concrete failure chain, classify the issue as
`duplicate-or-overlap` or `already-fixed` as appropriate. Do not create or
recommend a new PR just because the existing PR does not reference the issue.

### 3. Read the current source, not just the issue theory

- Find the exact files, symbols, branches, and tests implicated by the report.
- Verify whether the functions, fields, or branches named in the issue still exist on current `main`.
- If the issue cites a control-flow story, trace that path line by line in current source.
- Search tests for the same behavior or a recent regression lock.

### 4. Classify the result

Prefer one of these verdicts:

- `still-live`
  The behavior reproduces on current `main`, or the source-level bug still clearly exists.
- `already-fixed`
  Current `main` contains the relevant guard, branch, or test, and the issue's failure chain no longer matches source.
- `wrong-premise`
  The issue's explanation depends on code paths that do not run, symbols that do not exist, or an incorrect model of current behavior.
- `duplicate-or-overlap`
  Another issue or PR already tracks the same concrete bug class.
- `blocked-on-environment`
  The claim may be real, but current triage cannot separate source from local or platform-specific skew yet.

If several labels apply, pick the strongest primary verdict and mention the secondary nuance.

### 5. Produce the smallest useful conclusion

The default useful output is:
- latest baseline commit
- relevant files and code paths checked
- whether similar issue/PR coverage exists
- the verdict
- what to do next

Good next steps:
- close as already fixed
- leave a comment requesting a refreshed repro on latest `main`
- open a narrower follow-up issue
- hand off to `$hermes-upstream-worktree-fix`

## What Good Evidence Looks Like

- A current-source guard that contradicts the issue's failure chain
- A removed or renamed function the issue still relies on
- A merged commit or test that explicitly covers the behavior
- An open or merged PR whose diff covers the same code site and concrete bug
  class, even if it does not mention the current issue number
- A targeted latest-`main` repro
- A direct code-path explanation showing why the bug class still exists

## What Not To Do

- Do not treat issue body prose as proof.
- Do not declare "cannot reproduce" just because the local environment differs.
- Do not drift into implementation work when the user only asked for triage.
- Do not call something duplicate without comparing the actual bug class.
- Do not rely only on issue timeline links, `Fixes #...`, or bot duplicate
  comments to find overlap. Search current open/merged PRs by symptom and code
  site before concluding that no existing fix exists.

## Handoff To Fix Work

If the verdict is `still-live` and the user wants a fix, switch to `$hermes-upstream-worktree-fix`.

That skill should own:
- numbered worktree selection
- clean-baseline reproduction
- patch implementation
- validation
- issue / PR drafting

This triage skill should stay lightweight and evidence-first.
