# PR Draft Scaffold

Use the target repo's real PR template first. Use this file to shape the content and keep the evidence chain strong.

## What does this PR do?

Answer three things:
- what user-visible bug this fixes
- why the old behavior was wrong
- why this approach is the right scope

## Related Issue

Prefer:

`Fixes #<issue-number>`

Add extra references only when genuinely useful.

## Type of Change

Mark the smallest honest category:
- bug fix
- tests
- docs
- refactor

## Why this is the right fix

This is a good place for bounded AI-authored writing.

Focus on:
- why the bug is in source, not just environment
- why the patch is minimal
- why the compatibility behavior is safe for old/new runtimes

## Changes Made

List concrete code changes in flat bullets.

## How to Test

Include:
1. stable reproduction steps
2. what failed before
3. what passes now
4. exact targeted validation commands

## Compatibility Notes

If the bug is version- or runtime-specific, describe:
- old-runtime behavior
- new-runtime behavior
- unknown-runtime fallback

Do not claim universal compatibility unless you actually validated it. Prefer precise scope over bold guarantees.

## Validation Logs

Keep this tight and factual, for example:

```text
Parent-commit repro:
- <signal>

Post-fix checks:
- <signal>

Automated checks:
- <command> -> passed
```

## Remaining Risks

State the real residual uncertainty, if any:
- untested platform
- broader suite not run
- behavior inferred but not exhaustively validated

Good PRs sound confident where evidence exists and careful where it does not.
