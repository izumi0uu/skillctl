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
- MCP health: `http://127.0.0.1:8766/health`
- MCP endpoint: `http://127.0.0.1:8766/mcp`
- MCP systemd unit: `github-issues-dashboard-mcp.service`
- MCP launcher: `run_dashboard_mcp.sh`
- Preferred Codex MCP server name: `github_monitor`
- Codex config file: `~/.codex/config.toml`
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
6. Treat the dashboard app and MCP sidecar as separate restart domains. If only `github_monitor_mcp.py`, `run_dashboard_mcp.sh`, or the sidecar unit changed, restart only `github-issues-dashboard-mcp.service` unless evidence shows the app also needs a restart.
7. Prefer SSH local forwarding for Codex access to the remote MCP sidecar. Do not expose the sidecar publicly or bind it to `0.0.0.0` unless the user explicitly asks.
8. `issue_archive` is a live mutating action. Read the target issue first with `issue_get` or `issues_list`, and archive only when the task clearly intends state change.

## Standard Workflows

### 0. Codex MCP access

Use this path when the user wants Codex, not Hermes, to talk to the dashboard service.

1. Confirm the remote sidecar is healthy:
   - `systemctl is-active github-issues-dashboard-mcp.service`
   - `curl -fsS http://127.0.0.1:8766/health`
2. If the sidecar runs on the VPS, open a local tunnel:

```bash
ssh -N -L 8766:127.0.0.1:8766 -i ~/.ssh/smd.pem ubuntu@100.115.70.73
```

3. Ensure the local Codex config contains:

```toml
[mcp_servers.github_monitor]
url = "http://127.0.0.1:8766/mcp"
startup_timeout_sec = 60.0
tool_timeout_sec = 120.0
```

4. Validate the forwarded endpoint locally:
   - `curl -fsS http://127.0.0.1:8766/health`
5. Restart Codex or open a new Codex session so it reloads MCP servers.
6. Prefer the read-only tools first, then mutating tools:
   - `health_get`
   - `issues_list`
   - `issue_get`
   - `events_recent`
   - `full_reconcile_status`
   - `issue_archive`

If Codex is running on the same machine as the sidecar, skip the SSH tunnel and use the same localhost MCP URL directly.

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
6. Restart only the relevant service:
   - dashboard app changes: `github-issues-dashboard.service`
   - MCP sidecar changes: `github-issues-dashboard-mcp.service`
7. Verify the matching health endpoint:
   - app: `systemctl is-active github-issues-dashboard.service`
   - app: `curl -fsS http://127.0.0.1:8765/api/health`
   - sidecar: `systemctl is-active github-issues-dashboard-mcp.service`
   - sidecar: `curl -fsS http://127.0.0.1:8766/health`
8. If the change is user-visible, also check the affected endpoint, page, or MCP tool.

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

### 5. MCP sidecar and agent-access triage

When the dashboard works in a browser but Codex or Hermes cannot use it, check in this order:

1. `github-issues-dashboard-mcp.service`
2. local port binding on `127.0.0.1:8766`
3. `http://127.0.0.1:8766/health`
4. the SSH tunnel or private-network forwarding path
5. local MCP client config:
   - Codex: `~/.codex/config.toml`
   - Hermes: `~/.hermes/config.yaml`
6. tool behavior, starting with `health_get` and `issue_get`

## Repo-Specific Heuristics

- `app.py` currently contains both the FastAPI backend and embedded HTML/JS UI, so many UI changes are server-rendered string changes rather than a separate frontend build.
- The MCP sidecar serves Streamable HTTP on `/mcp`, backed by the same SQLite/API domain but on a separate process and port.
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
- Agent-facing MCP tools are currently:
  - `health_get`
  - `issues_list`
  - `issue_get`
  - `issue_archive`
  - `events_recent`
  - `full_reconcile_status`
- For a specified issue, the safest sequence is `issue_get` first, then `issue_archive` only if the user clearly wants that mutation.
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
- the relevant service is healthy after deployment:
  - `github-issues-dashboard.service` for the app
  - `github-issues-dashboard-mcp.service` for MCP access
- the matching health endpoint confirms the service is responding
- if agent access was in scope, the local Codex or Hermes MCP config points at the correct forwarded endpoint
- no dashboard data was modified destructively unless the user explicitly requested it
