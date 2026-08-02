# Hermes Upstream Worktree Fix Checklist

## Worktree Baseline

- Retain exactly four Hermes lanes total:
  - lane `0`: `~/.hermes/hermes-agent`, preserving its local-experience branch
  - lane `1`: `~/.hermes/hermes-agent-1`, canonically `worktree/1`
  - lane `2`: `~/.hermes/hermes-agent-2`, canonically `worktree/2`
  - lane `3`: `~/.hermes/hermes-agent-3`, canonically `worktree/3`
- Only lanes `1-3` are upstream-development lanes; do not describe the whole topology as "three lanes."
- Verify each retained checkout has its own `.venv`, `node_modules`, and isolated runtime launcher such as `.hermes/with-env.sh`.
- Health-check all four lanes. Sync only upstream-development lanes `1-3` to latest `upstream/main` before new upstream development or fresh baseline verification.
- Do not auto-reset, auto-rebase, or auto-repoint lane `0` to `upstream/main`; preserve its local-experience branch unless the user explicitly asks to repurpose it.
- Prefer the shared bench helpers over ad-hoc shell loops:
  - `~/.codex/skills/hermes-upstream-worktree-fix/scripts/hermes_worktree_bench.py`
  - `~/.hermes/admin/worktree-health.sh`
  - `~/.hermes/admin/sync-four-worktrees.sh`
  - `~/.hermes/admin/apply-git-safety.sh`
- Do not delete extra worktrees or branches until you check for dirty changes and unique commits.

## Preflight

- Confirm repo root, branch, remotes, and working-tree state.
- Read repo-local `AGENTS.md`, `CONTRIBUTING.md`, and `.github/PULL_REQUEST_TEMPLATE.md` before editing or drafting.
- Prefer a clean worktree from `upstream/main` when the current tree is dirty or already dedicated to another task.

## Source-Proof Gates

- Reproduce on latest clean baseline whenever feasible.
- If the issue only reproduces on an old local install or stale branch, do not call it an upstream bug yet.
- Check for:
  - local config drift
  - profile-specific contamination
  - cache or persisted-state pollution
  - Desktop wrapper / packaging issues
  - service-manager or OS-version differences
- Identify the exact source file and code path that explains the behavior.
- Keep evidence and inference separate in notes and drafts.

## Fix Gates

- Keep the change minimal and issue-scoped.
- Do not mix unrelated cleanup, refactors, or product redesign into the patch.
- Match branch naming, commit style, and test conventions used by the target repo.

## Validation Gates

- Preserve at least one concrete pre-fix failure signal when possible.
- Capture at least one concrete post-fix success signal.
- Run targeted tests close to the changed behavior.
- Run focused lint / typecheck checks when applicable.
- For compatibility fixes, validate the relevant runtime/version branches explicitly.
- If something was not tested, name it plainly.

## Publish Gates

Explicit user confirmation is required before:
- `git push`
- `gh issue create`
- `gh pr create`

If the user only wants drafts:
- stop at markdown text
- provide suggested commands only

If the user only wants workspace hygiene:
- stop at topology, sync, isolation, and cleanup status
- report extra branches or worktrees that still need human judgment

## AI-Written Sections Allowed

AI may polish or draft:
- root cause summary
- why this is upstream
- why the patch is the right scope
- compatibility notes
- remaining risks

AI must not invent:
- environment facts
- logs
- exact test counts
- guarantees that were not validated
