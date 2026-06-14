# Issue Draft Scaffold

Use this as a scaffold after checking the target repo's issue style. Keep the final issue concrete and evidence-first.

## Title

`[Bug] <clear user-visible symptom>`

## Bug

Describe the observed behavior in one tight paragraph:
- what breaks
- where it happens
- why it is surprising

## Reproduction

1. State the real environment that matters.
2. Give the smallest rerunnable steps.
3. Call out the observable failure signal.

## Expected behavior

Describe the behavior that should happen instead.

## Root cause

Keep this source-level:
- file or subsystem involved
- what logic currently does
- why that produces the failure

## Fix direction

Describe the smallest correct repair direction. Do not over-design future architecture here.

## My environment

List only facts you actually observed, for example:
- OS / distro
- app or CLI version
- service manager version
- profile / runtime mode if relevant

## Why I believe this is upstream

This is the best place for personal voice plus careful AI polishing.

Good content:
- reproduced on a clean worktree
- reproduced on latest main or explain why not
- ruled out local config drift
- identified a concrete source-level cause

Bad content:
- vague confidence language
- unverified blame
- invented environment details

## Closing line

Use a human-sounding close such as:

`I'd like to contribute a fix if this approach makes sense.`
