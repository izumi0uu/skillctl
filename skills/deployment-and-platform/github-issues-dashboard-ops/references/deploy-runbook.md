# Deploy Runbook

Use this runbook when shipping dashboard changes from local to the VPS.

## Standard flow

### 1. Validate locally

```bash
cd /Users/idah/.hermes/services/github-issues-dashboard
python3 -m pytest tests/test_app.py
```

If needed, run a manual smoke:

```bash
cd /Users/idah/.hermes/services/github-issues-dashboard
bash run_dashboard.sh
```

Then check:

```bash
curl -fsS http://127.0.0.1:8765/health
curl -fsS http://127.0.0.1:8765/api/health
curl -fsS http://127.0.0.1:8766/health
```

### 2. Commit and push

```bash
cd /Users/idah/.hermes/services/github-issues-dashboard
git status --short
git add <intended-files>
git commit
git push origin <branch>
```

### 3. Sync the VPS repo

Once connected to the VPS:

```bash
cd /home/ubuntu/.hermes/services/github-issues-dashboard
git status --short
git remote -v
git branch --show-current
git fetch origin
git pull --ff-only
```

If a specific commit is required, verify it explicitly:

```bash
git rev-parse HEAD
git log -1 --oneline
```

### 4. Restart the relevant service

```bash
sudo systemctl restart github-issues-dashboard.service
systemctl is-active github-issues-dashboard.service
systemctl status github-issues-dashboard.service --no-pager -l
```

If the change only touched the MCP sidecar, restart that service instead:

```bash
sudo systemctl restart github-issues-dashboard-mcp.service
systemctl is-active github-issues-dashboard-mcp.service
systemctl status github-issues-dashboard-mcp.service --no-pager -l
```

### 5. Verify runtime health

```bash
curl -fsS http://127.0.0.1:8765/health
curl -fsS http://127.0.0.1:8765/api/health
curl -fsS http://127.0.0.1:8766/health
```

If the change touched archive/reconcile/UI behavior, also probe the affected API:

```bash
curl -fsS http://127.0.0.1:8765/api/issues | head
curl -fsS http://127.0.0.1:8765/api/events | head
curl -fsS http://127.0.0.1:8765/api/full-reconcile
```

If the change touched Codex or Hermes access, also verify the local forwarded MCP endpoint:

```bash
curl -fsS http://127.0.0.1:8766/health
```

## Safe rollback posture

- Prefer rolling back by Git commit, not by deleting runtime files.
- Do not replace `data/dashboard.db` unless the task is explicitly a recovery operation.
- If the service breaks after deploy, inspect logs first:

```bash
journalctl -u github-issues-dashboard.service -n 100 --no-pager
```

For sidecar-only failures:

```bash
journalctl -u github-issues-dashboard-mcp.service -n 100 --no-pager
```

## Definition of done

- intended commit is on the VPS repo
- the relevant service is active
- `/api/health` or `/health` returns healthy for the app
- `http://127.0.0.1:8766/health` returns healthy when MCP access was in scope
- the changed dashboard behavior is confirmed
