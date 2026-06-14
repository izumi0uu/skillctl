---
name: repo-preflight
description: Use when the user says "run repo preflight", "sync develop first", "rebase onto develop before editing", asks you to prepare a branch before making file changes, or mentions pulling `develop` into a non-`develop` branch. This skill checks the git working tree, updates local `develop`, and rebases the current branch onto the latest `develop` to preserve a linear history.
---

# Repo Preflight

## Overview
- Use this skill before making file changes in a git repository that follows a linear-history policy.
- The goal is not "run `git pull` no matter what." The goal is to confirm that the working branch is safely based on the latest `develop` before editing begins.

## Core Rules
- Always preserve linear history. Use rebase-based sync only.
- On any development branch other than `develop`, treat `git pull origin develop` as a rebase operation: use `git pull --rebase origin develop` or the safer `git fetch origin develop` plus `git rebase origin/develop` / updated local `develop`.
- Never use merge-based sync for this workflow.
- Never run bare `git pull origin develop` from a non-`develop` branch, because Git may merge `develop` into the branch by default.
- Never pull blindly on a dirty working tree.
- Never auto-stash, reset, or discard local changes unless the user explicitly asks for it.
- Do not begin file edits until the branch baseline is confirmed.

## Trigger Phrases
- `Use $repo-preflight before editing`
- `Run repo preflight`
- `Sync develop first`
- `Rebase onto develop before making changes`
- `Pull latest develop into this branch`

## Workflow

### 1. Verify Repository Context
- Confirm the repo root.
- Confirm the current branch.
- Inspect the working tree with `git status --short`.
- If this is not a git repository, report that immediately and stop.

### 2. Handle Dirty Working Trees Safely
- If the working tree is dirty, stop before any sync operation.
- Report:
  - current branch
  - dirty files
  - why rebase or checkout is unsafe right now
- Do not run `git pull`, `git rebase`, `git checkout develop`, `git stash`, or `git reset` automatically.

### 3. Fetch Latest Remote State
- Fetch the latest remote refs before deciding whether the branch is current.
- Prefer fetching `origin` and updating knowledge of `develop` explicitly.

### 4. Update Local `develop`
- If already on `develop` and the tree is clean:
  - update it with rebase semantics, such as `git pull --rebase origin develop`
- If on a feature branch and the tree is clean:
  - update local `develop` first
  - then return to the working branch
- The important invariant is: local `develop` must represent the latest remote `develop` before rebasing the feature branch.

### 5. Rebase the Working Branch
- If the current branch is a feature branch:
  - rebase it onto the updated local `develop`
- If the user specifically asks for `git pull origin develop` while on a non-`develop` branch:
  - interpret that request as `git pull --rebase origin develop` or fetch-then-rebase
- If the current branch is already `develop`:
  - no extra branch rebase is needed after updating `develop`
- Never replace this with a merge-based sync.

### 6. Conflict and Failure Handling
- If fetch, checkout, pull-with-rebase, or rebase fails:
  - stop immediately
  - summarize the exact failure
  - do not improvise destructive recovery steps
- If conflicts appear during rebase:
  - report that the branch is blocked on conflict resolution
  - do not auto-resolve unless the user explicitly asks

### 7. Confirm Safe-to-Edit State
- Before editing files, summarize:
  - repo root
  - current branch
  - whether the working tree is clean
  - whether local `develop` is current
  - whether the current branch is rebased onto latest `develop`

## Recommended Command Shape
- Repository inspection:
  - `git rev-parse --show-toplevel`
  - `git branch --show-current`
  - `git status --short`
- Sync path:
  - `git fetch origin develop`
  - update local `develop`
  - rebase the current feature branch onto local `develop`
- Direct pull request on a non-`develop` branch:
  - `git pull --rebase origin develop`
  - never bare `git pull origin develop`

## Do Not Do These Things
- Do not start editing before the baseline is confirmed.
- Do not use merge commits to sync with `develop`.
- Do not run bare `git pull origin develop` from a non-`develop` branch.
- Do not pull on a dirty working tree.
- Do not auto-stash.
- Do not auto-reset.
- Do not silently continue after a failed rebase.

## Example Requests
- `Use $repo-preflight before making changes in this repo.`
- `Run repo preflight and sync develop first.`
- `Rebase this branch onto the latest develop before editing.`
- `Pull origin develop into this feature branch.`

## Success Condition
- The agent can state, before editing starts, that the branch is safely aligned with the latest `develop` under a rebase-only workflow.
