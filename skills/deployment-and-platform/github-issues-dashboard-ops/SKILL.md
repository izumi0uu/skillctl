---
name: github-issues-dashboard-ops
description: Operate, develop, deploy, and diagnose the GitHub Issues Dashboard project across its local repo and VPS service. Use when the task involves the dashboard codebase, its SQLite-backed FastAPI service, the `github-issues-dashboard.service` systemd unit, local-to-VPS sync, health checks, archive/reconcile behavior, or safe incident response without damaging dashboard data.
---

# GitHub Issues Dashboard Ops

Use this skill for the repo-specific maintenance loop around the GitHub Issues Dashboard.

## Canonical Facts

- Local repo: `/Users/idah/.hermes/services/github-issues-dashboard`
- VPS repo: `/home/ubuntu/.hermes/services/github-issues-dashboard`
- Canonical Git remote: `git@github.com:izumi0uu/github-issues-dashboard.git`
- Runtime port: `127.0.0.1:8765`
- Systemd unit: `github-issues-dashboard.service`
- Launcher: `run_dashboard.sh`
- Main app: `app.py`
- Primary test file: `tests/test_app.py`

Treat these as the starting assumptions unless fresh repo evidence shows they changed.

## Hard Boundaries

1. Treat `data/`, `dashboard.db`, `dashboard.db.*`, and historical restore snapshots as sensitive runtime state.
2. Do not delete, truncate, rebuild, or replace dashboard data unless the user explicitly asks for a recovery or migration operation.
3. Do not use `rm -rf` as a repair shortcut for dashboard data, service state, or the repo.
4. Prefer local validation first, then Git commit/push, then VPS sync, then service restart, then `/api/health` verification.
5. When debugging issue/archive/reconcile behavior, distinguish clearly between:
   - UI behavior
   - API behavior
   - SQLite data state
   - ingestion/reconcile pipeline behavior

## Standard Workflows

### 1. Local development and bug fixing

Use this path for UI, API, filtering, archive, reconcile, or data-shaping changes.

1. Inspect local repo state:
   - `git -C /Users/idah/.hermes/services/github-issues-dashboard status --short`
   - `git -C /Users/idah/.hermes/services/github-issues-dashboard remote -v`
2. Read the relevant code first:
   - `app.py`
   - `tests/test_app.py`
   - `README.md`
3. Make the smallest safe fix.
4. Validate locally before any VPS action.
5. Only after local proof, commit and push to `izumi0uu/github-issues-dashboard`.

### 2. Local validation

Prefer the smallest proof that matches the change:

- API or HTML behavior:
  - run the focused pytest case if it exists
  - otherwise add or run a targeted FastAPI `TestClient` test
- Basic app import / boot:
  - use the Hermes venv if project-local tooling is absent
- Manual smoke:
  - start the app locally
  - hit `/health`, `/api/health`, and the affected API route

Common checks:

```bash
cd /Users/idah/.hermes/services/github-issues-dashboard
python3 -m pytest tests/test_app.py
```

```bash
cd /Users/idah/.hermes/services/github-issues-dashboard
bash run_dashboard.sh
```

```bash
curl -fsS http://127.0.0.1:8765/health
curl -fsS http://127.0.0.1:8765/api/health
```

If `pytest` or FastAPI is not available globally, prefer the Hermes venv path discovered in `run_dashboard.sh`.

### 3. Safe deploy to VPS

Use this sequence unless the task is explicitly local-only:

1. Verify local repo is committed.
2. Push the intended branch or `main` to GitHub.
3. Connect to the VPS.
4. Confirm remote repo path, branch, and origin.
5. Pull the expected commit.
6. Restart `github-issues-dashboard.service`.
7. Verify:
   - `systemctl is-active github-issues-dashboard.service`
   - `curl -fsS http://127.0.0.1:8765/api/health`
8. If the change is user-visible, also check the affected endpoint or page.

Read `references/deploy-runbook.md` when you need the exact remote command sequence.

### 4. Service health and incident triage

When the user says the dashboard is down, stale, or behaving strangely, do not jump straight to code edits.

Check in this order:

1. Service state
2. Local port binding
3. `/health`
4. `/api/health`
5. Recent systemd logs
6. Repo drift or wrong commit on the VPS
7. SQLite counts and API-level symptoms

Read `references/incident-checklist.md` for the standard incident path.

## Repo-Specific Heuristics

- `app.py` currently contains both the FastAPI backend and embedded HTML/JS UI, so many UI changes are server-rendered string changes rather than a separate frontend build.
- `/api/health` is the best structured truth source for:
  - `events_count`
  - `issues_count`
  - `version`
  - `ui_build`
  - `full_reconcile`
  - `server_time`
- Archive actions are API-backed:
  - `/api/issues/{issue_number}/archive`
  - `/api/issues/archive-closed`
  - `/api/issues/archive-linked-pr`
  - `/api/issues/archive-duplicated`
- Full reconcile is long-running and should be treated as a service-side operation, not a front-end-only effect.

## When To Read References

- Read `references/topology.md` when you need the project map, runtime files, or canonical paths.
- Read `references/deploy-runbook.md` when you need the exact local-to-VPS ship path.
- Read `references/incident-checklist.md` when the service is down, stale, mismatched, or suspected to have data/API/UI drift.

## Success Condition

The task is complete only when:

- the intended dashboard code or ops change is in the canonical repo
- local validation matches the claimed fix
- VPS changes, if relevant, are synced to the correct repo and service
- `github-issues-dashboard.service` is healthy after deployment
- `/api/health` confirms the service is responding
- no dashboard data was modified destructively unless the user explicitly requested it
