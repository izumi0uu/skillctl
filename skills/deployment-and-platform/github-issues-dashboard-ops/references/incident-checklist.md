# Incident Checklist

Use this when the dashboard is unavailable, stale, drifting from GitHub truth, or behaving inconsistently.

## 1. Check service health first

```bash
systemctl is-active github-issues-dashboard.service
systemctl status github-issues-dashboard.service --no-pager -l
ss -tlnp | grep 8765
curl -fsS http://127.0.0.1:8765/health
curl -fsS http://127.0.0.1:8765/api/health
```

If these fail, inspect logs:

```bash
journalctl -u github-issues-dashboard.service -n 100 --no-pager
```

If the browser app is healthy but agent access is failing, also check:

```bash
systemctl is-active github-issues-dashboard-mcp.service
systemctl status github-issues-dashboard-mcp.service --no-pager -l
ss -tlnp | grep 8766
curl -fsS http://127.0.0.1:8766/health
journalctl -u github-issues-dashboard-mcp.service -n 100 --no-pager
```

## 2. Check repo drift before editing code

```bash
cd /home/ubuntu/.hermes/services/github-issues-dashboard
git status --short
git remote -v
git rev-parse HEAD
git log -1 --oneline
```

Confirm the VPS is actually on the expected commit.

## 3. Distinguish symptom type

### UI-only symptom

Examples:

- button behavior feels wrong
- popup behavior is inconsistent
- fresh bar flickers

Check:

- HTML/JS in `app.py`
- affected endpoint payload
- whether the VPS is serving the expected commit/UI build

### API/data symptom

Examples:

- issue counts wrong
- linked PR state stale
- archive result mismatched
- priorities mis-grouped

Check:

- `/api/health`
- `/api/issues`
- `/api/events`
- relevant normalization logic in `app.py`

If needed, inspect DB counts only. Do not mutate data casually:

```bash
sqlite3 /home/ubuntu/.hermes/services/github-issues-dashboard/data/dashboard.db 'select count(*) from issues; select count(*) from events;'
```

### Reconcile/ingest symptom

Examples:

- linked PRs not updating
- closed issues stay open for too long
- full reconcile appears stuck

Check:

- `/api/full-reconcile`
- `/api/health`
- latest events
- ingest and reconcile code paths in `app.py`

### Agent-access symptom

Examples:

- Codex cannot see the `github_monitor` MCP server
- Hermes MCP config works locally but Codex does not
- issue tools time out even though the dashboard page loads

Check:

- `github-issues-dashboard-mcp.service`
- `http://127.0.0.1:8766/health`
- the SSH tunnel or private-network forwarding path
- `~/.codex/config.toml` or `~/.hermes/config.yaml`
- `issue_get` behavior before trying `issue_archive`

## 4. Prefer non-destructive recovery

Use this order:

1. inspect service
2. inspect logs
3. inspect repo drift
4. inspect API output
5. inspect MCP sidecar and local forwarding if agent access is involved
6. inspect DB counts
7. patch code or restart service if justified

Avoid:

- deleting DB files
- replacing backups blindly
- mass-resetting runtime state without explicit user instruction

## 5. Close the incident with evidence

Before declaring the issue fixed, capture:

- service active state
- `/api/health` result
- `http://127.0.0.1:8766/health` result if agent access was involved
- affected endpoint result
- deployed commit hash if VPS was touched
