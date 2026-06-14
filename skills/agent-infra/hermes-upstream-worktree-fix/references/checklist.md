# Hermes Upstream Worktree Fix Checklist

## Worktree Baseline

- Retain exactly four Hermes checkouts:
  - `~/.hermes/hermes-agent`
  - `~/.hermes/hermes-agent-1`
  - `~/.hermes/hermes-agent-2`
  - `~/.hermes/hermes-agent-3`
- Map them to `main`, `worktree/1`, `worktree/2`, and `worktree/3`.
- Verify each retained checkout has its own `.venv`, `node_modules`, and isolated runtime launcher such as `.hermes/with-env.sh`.
- Sync all four to latest `upstream/main` before new upstream development or fresh baseline verification.
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
