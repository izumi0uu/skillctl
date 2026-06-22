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
- A targeted latest-`main` repro
- A direct code-path explanation showing why the bug class still exists

## What Not To Do

- Do not treat issue body prose as proof.
- Do not declare "cannot reproduce" just because the local environment differs.
- Do not drift into implementation work when the user only asked for triage.
- Do not call something duplicate without comparing the actual bug class.

## Handoff To Fix Work

If the verdict is `still-live` and the user wants a fix, switch to `$hermes-upstream-worktree-fix`.

That skill should own:
- numbered worktree selection
- clean-baseline reproduction
- patch implementation
- validation
- issue / PR drafting

This triage skill should stay lightweight and evidence-first.
