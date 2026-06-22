---
name: hermes-upstream-worktree-fix
description: "Use when working on Hermes upstream fixes or maintaining the standardized local Hermes worktree bench after issue triage is already done: keep the main checkout plus three intentionally retained numbered worktrees clean and isolated for parallel upstream development, reuse only those numbered lanes by switching branches inside them, sync the needed lanes to latest upstream/main before development, reproduce on a clean baseline, implement the smallest fix, validate locally, and draft issue/PR artifacts without publishing until explicitly confirmed."
---

# Hermes Upstream Worktree Fix

## Overview

Use this skill when Hermes fix work should happen on a clean, standardized local bench instead of an ad-hoc checkout. It covers two related jobs:
- keep the local Hermes bench healthy
- reproduce and land minimal upstream fixes from that clean bench

Use `$hermes-issue-triage` first when the issue itself still needs to be judged as live, fixed, duplicate, or wrong-premise.

Default posture:
- safe local inspect/sync/rebase/worktree/venv/node_modules setup, editing, testing, branching, and drafting are allowed
- `git push`, `gh issue create`, and `gh pr create` require explicit user confirmation
- issue and PR text may be drafted automatically, but publication stays human-gated
- if the task is only worktree hygiene, stop after reporting topology, sync status, and any blockers
- treat `~/.hermes/hermes-agent` as the user's local-experience lane, not the default upstream bugfix/feature lane
- treat the three numbered worktrees as the normal retained parallel-development bench, not as accidental clutter to collapse by default
- never create a new ad-hoc or temporary Hermes worktree when lane `1-3` can be reused by switching branches inside an existing lane

## Use When

- The user wants to reproduce or fix a Hermes upstream bug after triage says it is worth pursuing.
- The user wants the Hermes local workspace normalized before starting development.
- The bug may depend on stale branches, shared state, profile contamination, packaging, or version skew.
- The user wants issue and PR drafts rooted in clean-worktree evidence.

## Do Not Use When

- The request is only a quick local hotfix with no need for clean-baseline proof.
- The user wants fully automatic GitHub publishing with no confirmation gates.
- The task is only code review or explanation with no workspace maintenance or patching.
- The main open question is still whether the issue is real on current `main`; use `$hermes-issue-triage` first.

## Non-Negotiable Boundaries

- Do not skip issue triage when the main uncertainty is whether the report is still valid on current `main`.
- Do not call something an upstream bug until clean-baseline checks rule out local skew.
- Keep exactly four retained local Hermes checkouts unless the user explicitly asks for a different topology.
- Do not use `~/.hermes/hermes-agent` as the default checkout for upstream bugfix or feature development. Reserve it for local usage, personal workflow tuning, and experience testing unless the user explicitly overrides that policy.
- Keep the three numbered worktrees available for concurrent upstream investigations or fixes unless the user explicitly wants a slimmer bench. Their existence is intentional and should be reflected in the skill/config, not treated as maintenance debt by default.
- Do not create extra Hermes worktrees outside the retained four just because the current branch in lane `1-3` is inconvenient. Reuse lane `1-3` by switching branches inside those lanes.
- If all three numbered lanes contain active work that cannot safely be repurposed, surface that as a blocker instead of creating a fifth upstream-development worktree.
- Do not delete extra worktrees or branches if they contain dirty changes or unique commits; surface that as a blocker first.
- Keep fixes minimal and issue-scoped. Do not mix in unrelated cleanup or architecture work.
- Every material claim in the final write-up must be either direct evidence, a clearly labeled inference, or an explicit unknown.
- Drafting is allowed. Publishing is not allowed without explicit user confirmation.

## Hermes Local Worktree Policy

Default topology:
- `~/.hermes/hermes-agent` on a local-only branch such as `izumi/local` for day-to-day usage and local UX validation
- `~/.hermes/hermes-agent-1` on `worktree/1`
- `~/.hermes/hermes-agent-2` on `worktree/2`
- `~/.hermes/hermes-agent-3` on `worktree/3`

Topology note:
- The path slots are canonical even when the branch names are not. If `~/.hermes/admin/worktree-bench.json` is present, treat that config as the source of truth for which active branch currently occupies each numbered lane.

Role split:
- `~/.hermes/hermes-agent` is the personal/local lane. It may carry local config-adjacent tweaks, convenience patches, or experience-testing changes that are not part of an upstream-ready clean bench.
- `~/.hermes/hermes-agent-{1,2,3}` are the only upstream-development lanes. Use them for reproduction, clean-baseline verification, bugfixes, features, and PR preparation.
- When a numbered lane's current branch is no longer the right fit, switch that lane to a new branch in place. Do not solve branch mismatch by creating another worktree elsewhere.

Why retain three numbered lanes:
- They allow multiple upstream tasks to stay isolated and runnable in parallel while reusing the same three physical lane directories instead of repeatedly creating temporary worktrees.
- The maintenance burden is acceptable when each lane is explicitly tracked in the bench config and validated by the shared health script.
- This retained topology is preferred over ad-hoc simplification unless the user explicitly wants fewer standing lanes.

Isolation requirements for every retained checkout:
- dedicated `.venv`
- dedicated `node_modules`
- isolated runtime entrypoint such as `.hermes/with-env.sh` so each checkout uses its own `HERMES_HOME`
- development commands must run from the intended checkout, not a sibling tree

Sync rule before upstream development:
- fetch latest `upstream/main`
- align the numbered upstream-development worktrees to the latest `upstream/main` head before starting new upstream work or fresh baseline verification
- when starting a different upstream task, repurpose one of lanes `1-3` by switching its branch in place instead of creating a new worktree
- do not auto-reset, auto-rebase, or auto-repoint `~/.hermes/hermes-agent` to `upstream/main` as part of bench hygiene; preserve its local-experience branch unless the user explicitly asks to repurpose it
- prefer the shared skill script or shared admin wrappers over ad-hoc shell loops:
  - `~/.codex/skills/hermes-upstream-worktree-fix/scripts/hermes_worktree_bench.py`
  - `~/.hermes/admin/worktree-health.sh`
  - `~/.hermes/admin/sync-four-worktrees.sh`
  - `~/.hermes/admin/apply-git-safety.sh`
  - `~/.hermes/admin/worktree-bench.json`

Cleanup rule:
- prune unnecessary Hermes worktrees and local branches beyond the retained four after confirming they are clean and merged or otherwise disposable
- extra temporary Hermes worktrees are drift from policy; clean them up and restore the bench to the retained four whenever it is safe to do so
- if a numbered slot is recycled, either restore the canonical `worktree/<n>` mapping or update `~/.hermes/admin/worktree-bench.json` so the lane-to-branch ownership stays explicit before new development starts

## Workflow

### 1. Normalize the local bench

- Confirm repo root, current branch, remotes, and worktree list.
- If present, load `~/.hermes/admin/worktree-bench.json` first so the bench topology is explicit.
- Check the retained-four topology and branch mapping.
- Confirm whether `~/.hermes/hermes-agent` is serving the local-experience lane (expected) or has been intentionally repurposed by the user.
- Verify each retained checkout has its own `.venv`, `node_modules`, and isolated runtime-state entrypoint.
- If the user asked for hygiene or the upstream baseline looks stale, sync the numbered upstream-development worktrees to latest `upstream/main` without disturbing the main local-experience checkout.
- If extra Hermes worktrees or branches exist, remove only the clearly disposable ones and report anything that needs human review.
- If a lane's current branch is the wrong task, switch that lane's branch in place rather than creating a new worktree.
- If lanes `1-3` are all occupied by active work that cannot be safely repurposed, stop and report that blocker instead of creating another worktree.

If you need a reusable gate list, load `references/checklist.md`.

### 2. Read local repo rules

- Read the target repo's local rules before editing:
  - `AGENTS.md` if present
  - `CONTRIBUTING.md`
  - `.github/PULL_REQUEST_TEMPLATE.md` if a PR is likely
- If issue validity is still uncertain, stop and run `$hermes-issue-triage` before doing fix work.
- Resolve artifact-style precedence before you commit or publish:
  - for external GitHub artifacts, prefer the target repo's observed upstream conventions
  - if local workspace rules add extra commit structure, keep it only when compatible with upstream style
  - if they conflict, preserve the target repo's outward-facing style first
  - inspect recent merged/open PRs and recent issues so you copy the repo's real naming pattern
- Before creating an issue, verify the repo's actual label names with GitHub (`gh label list` or equivalent). Do not assume the template's human wording maps 1:1 to a real label.

### 3. Reproduce on a clean baseline

- Assume issue triage already established that the report is worth pursuing.
- Record the exact baseline commit used for reproduction.
- Capture the real environment that matters:
  - OS / distro
  - app version / CLI version
  - `systemd`, `launchd`, Electron/Desktop, profile, or proxy details if relevant
- Reproduce on the latest clean baseline whenever feasible.
- Prefer reproduction on one of the synced numbered worktrees by switching that lane to a clean branch from the baseline, not on `~/.hermes/hermes-agent` unless the bug is specific to the user's local-experience lane.
- If the bug disappears on latest main, treat that as version skew until proven otherwise.
- If useful, compare behavior on:
  - current clean baseline
  - the parent commit before the fix
  - the user's older local branch or installed version
- If repeated evidence capture will help, use `scripts/collect-evidence.sh` to snapshot repo state, environment facts, and optional read-only validation commands into one local bundle.

Success condition for this step:
- there is a minimal, rerunnable reproduction
- or there is a concrete reason why reproduction is blocked

### 4. Prove the root cause is in source

- Trace the exact code path that explains the observed behavior.
- Isolate local-environment noise before blaming source.
- Prefer the smallest direct proof available:
  - a targeted failing test
  - a minimal script
  - a before/after function-level probe
  - a log + code-path comparison
- Separate evidence from inference in notes and drafts.

Do not say "this is definitely upstream" unless the source-level explanation survives clean-baseline checks.

### 5. Implement the smallest fix

- Create a fresh bugfix branch inside one of lanes `1-3` from the clean baseline if needed.
- Prefer implementing upstream-facing fixes in a numbered upstream-development worktree, not in `~/.hermes/hermes-agent`.
- Do not create a new temporary worktree just because a numbered lane is on the wrong branch; switch that lane to the needed branch in place.
- If no numbered lane can be repurposed safely, treat that as a blocker to surface, not as permission to add a fourth upstream-development lane.
- Match the target repo's branch naming and commit conventions.
- For commit messages, match the target repo's **subject-line** convention first.
  - Example: if upstream PRs and commits are using `fix(desktop): ...`, do not substitute a local freeform subject like `Keep desktop ...`
  - If you also need local decision-record metadata, keep it in the commit body/trailers instead of changing the subject style.
- Keep the patch narrowly tied to the issue.
- Add or update tests close to the changed behavior.
- If the problem is compatibility-related, prefer feature detection or explicit version-bound behavior over broad guesswork.

### 6. Build a before/after validation chain

- Preserve evidence of pre-fix failure whenever possible.
- Run the smallest useful validation set first:
  - targeted tests
  - focused lint / typecheck
  - narrow runtime probes
- If the fix claims compatibility across versions or runtimes, validate the relevant branches explicitly:
  - old supported path
  - new supported path
  - unknown / probe-failure fallback if applicable
- If full validation is not practical, record the exact gap instead of hand-waving.

### 7. Draft issue and PR artifacts

Before drafting:
- inspect the target repo's actual issue / PR patterns
- use nearby merged PRs or recent issues as style anchors
- use the local reference files in this skill as scaffolds, not as replacements for repo-specific rules
- explicitly resolve:
  - PR title format from recent upstream PRs
  - commit subject format from recent upstream commits/PRs
  - issue title style from recent issues
  - real label names from the repo's current labels

When in doubt, prefer these priorities for public artifacts:
1. target repo's current observed GitHub conventions
2. target repo templates / contributing docs
3. local workspace conventions that can fit without changing 1 or 2

Load these references as needed:
- `references/issue-template.md`
- `references/pr-template.md`
- `references/checklist.md`

Allow AI-authored writing in sections like:
- root cause summary
- why this is upstream
- why this fix is the right scope
- compatibility notes
- remaining risks

But keep those sections evidence-backed. Do not invent logs, environments, counts, or guarantees.

### 8. Respect manual publish gates

The agent may prepare commands and drafts, but must stop for explicit confirmation before:
- `git push`
- `gh issue create`
- `gh pr create`

This gate is intentionally narrow. Do not stop for ordinary safe local work just because this skill is active.

If the user asks only for drafts, stop at markdown text and command suggestions.
If the user asks only for worktree maintenance, stop at topology, sync, isolation, and cleanup status.

## Output Contract

When this skill is active, the useful default output is:

1. Worktree topology and sync status
2. Triage prerequisite status
3. Baseline commit and checkout used
4. Reproduction status
5. Source-level root cause
6. Minimal fix summary
7. Validation evidence
8. Issue draft or issue link
9. PR draft or PR link
10. Clear publish status or cleanup blockers

## Reference Files

- `references/checklist.md`
  Use for go/no-go gates during worktree hygiene, investigation, validation, and publishing.
- `scripts/hermes_worktree_bench.py`
  Use for machine-readable bench health, safe sync, and Git push-safety setup. Prefer `--config ~/.hermes/admin/worktree-bench.json` when the local bench has an explicit config file. By default, extra Hermes worktrees outside the retained bench are treated as blockers unless the config explicitly opts out.
- `references/issue-template.md`
  Use when drafting a repo-style issue with personal environment details and evidence-backed AI polishing.
- `references/pr-template.md`
  Use when drafting a repo-style PR that links to the issue, relates to earlier PRs when relevant, and shows before/after validation.
- `scripts/collect-evidence.sh`
  Use to capture a local evidence bundle with repo metadata, runtime facts, and optional extra command outputs. This helper is read-only by default and never pushes or publishes artifacts.
