# Topology

## Canonical locations

- Local repo: `/Users/idah/.hermes/services/github-issues-dashboard`
- VPS repo: `/home/ubuntu/.hermes/services/github-issues-dashboard`
- Git remote: `git@github.com:izumi0uu/github-issues-dashboard.git`
- Local/VPS runtime bind: `127.0.0.1:8765`
- systemd unit: `github-issues-dashboard.service`

## Key files

- `app.py`
  - FastAPI app
  - embedded HTML/CSS/JS UI
  - archive endpoints
  - full reconcile endpoints and manager
  - ingest endpoint
  - SSE stream endpoint
- `run_dashboard.sh`
  - launches `uvicorn app:app --host 127.0.0.1 --port 8765`
  - prefers `~/.hermes/hermes-agent/venv/bin/python`
  - falls back to `python3`
- `github-issues-dashboard.service`
  - runs the launcher through systemd
  - restarts automatically
- `tests/test_app.py`
  - targeted behavior checks for ingest, health, UI HTML, and reconcile surfaces
- `data/dashboard.db`
  - live SQLite state

## Important API surfaces

- `GET /health`
- `GET /api/health`
- `GET /api/events`
- `GET /api/issues`
- `POST /api/issues/{issue_number}/archive`
- `POST /api/issues/archive-closed`
- `POST /api/issues/archive-linked-pr`
- `POST /api/issues/archive-duplicated`
- `GET /api/full-reconcile`
- `POST /api/full-reconcile`
- `POST /ingest`
- `GET /stream`

## Operational boundaries

- The dashboard repo is application code.
- The SQLite files under `data/` are runtime state.
- Backups and `*.before-*` files are recovery artifacts and should not be casually modified.
- If the UI looks wrong, the root cause may still be:
  - API shape
  - SQLite contents
  - reconcile state
  - stale VPS code

## Typical maintenance split

- Code/design behavior: inspect `app.py` and tests first.
- Deploy/runtime behavior: inspect `run_dashboard.sh`, `github-issues-dashboard.service`, remote git state, and `/api/health`.
- Data correctness behavior: compare API responses, DB counts, and reconcile/ingest logic before changing anything.
