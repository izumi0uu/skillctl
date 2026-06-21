---
name: tailscale-vps-ops
description: Access and operate a Tailscale-reachable VPS by discovering SSH parameters at runtime, validating connectivity, checking Hermes and system health, and syncing files safely.
author: Hermes Agent
version: 1.0.0
license: MIT
---

# Tailscale VPS Ops

Use this skill when the user wants to inspect, troubleshoot, or operate a VPS that is reachable over Tailscale, especially when the VPS also runs Hermes jobs, gateway services, or cron workloads.

## Portability Rule

Treat all machine-specific values as runtime discoveries, not committed constants.

Do not hardcode or trust stale values for:

- Tailscale IP or hostname
- SSH user
- SSH key path
- SSH port
- Hermes home path
- Hermes binary path

Discover them from the current machine, reflect them in your response, and use them consistently for the rest of the session.

## When To Use

- Check whether a VPS is up or reachable over Tailscale
- Inspect remote Hermes gateway, cron, logs, sessions, disk, memory, or ports
- Sync files between local and remote Hermes homes
- Diagnose remote job failures, stalled outputs, or suspicious resource usage
- Open a local-only dashboard on the VPS through SSH forwarding or Tailscale

## Core Principles

1. Prefer Tailscale or other private-network addresses over public IPs.
2. Reuse already-validated SSH config instead of guessing credentials.
3. Run a minimal connectivity probe before heavier commands.
4. Summarize health in grouped sections instead of dumping raw command output.
5. Do not persist newly discovered private host details back into this canonical skill.
6. When the task follows a local code iteration, do not evaluate the remote service until you have confirmed the VPS is actually serving the latest intended code.

## Code Iteration Rule

If the user just changed code locally and then asks you to check, verify, or use a VPS-hosted service, assume the remote service may still be stale until proven otherwise.

Before trusting any remote UI, API, or systemd result:

1. identify whether the remote service is repo-backed
2. verify the local intended source of truth
3. verify the VPS repo path or deployed artifact path
4. sync or pull the intended version first
5. restart only the relevant service
6. verify both:
   - code identity
   - runtime health

Do not say "the VPS behavior is current" if you have only checked service health but not code freshness.

## Standard Flow

### 1. Discover local connection parameters

Check these sources first, in order:

- `~/.hermes/scripts/sync-sessions-pull.sh`
- other `~/.hermes/scripts/*sync*.sh` or deploy scripts
- `~/.ssh/config`
- cron helper scripts, backup scripts, bootstrap scripts, or shell history snippets the user points to

Extract:

- `VPS_HOST`
- `VPS_USER`
- `SSH_KEY`
- optional `SSH_PORT`
- optional `HERMES_HOME`
- optional `HERMES_BIN`
- optional local Tailscale IP to use for latency checks

If the user already gave exact parameters in the current session, use those as the source of truth.

### 2. Confirm the Tailscale node is online

```bash
tailscale status | head -20
```

Confirm the target node appears active before assuming SSH itself is broken.

### 3. Run a minimal SSH probe

Only continue to heavier checks after a cheap proof of connectivity succeeds:

```bash
ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 -i <KEY> <USER>@<VPS_HOST> "echo ok && uptime"
```

If a non-default port is needed:

```bash
ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 -p <PORT> -i <KEY> <USER>@<VPS_HOST> "echo ok && uptime"
```

### 4. Reuse one parameter set for all later commands

Once the probe works, keep using the same discovered:

- host
- user
- key
- port
- Hermes paths

Do not keep re-probing keys or switching users mid-session unless evidence shows the first working combination stopped working.

### 5. If the task is about a repo-backed service, discover the code path too

Extract, when relevant:

- remote repo path
- remote branch
- remote origin
- local canonical repo path
- relevant systemd unit or launcher

Typical proof commands:

```bash
ssh -o StrictHostKeyChecking=no -i <KEY> <USER>@<VPS_HOST> "
  cd <REMOTE_REPO> &&
  git status --short &&
  git branch --show-current &&
  git remote -v &&
  git rev-parse HEAD
"
```

Use this before claiming the VPS is on the expected code.

## VPS Health Overview

When the user says "check the VPS", "look at remote status", or "how is the server doing", do not stop at `uptime`.

Collect at least:

- system identity and uptime
- memory, disk, and load
- top memory-consuming processes
- listening ports
- optional private-network latency back to the local machine

Use a grouped command like:

```bash
ssh -o StrictHostKeyChecking=no -i <KEY> <USER>@<VPS_HOST> "
  echo '=== system ===' && uname -a && uptime &&
  echo '=== resources ===' && free -h && df -h / && cat /proc/loadavg &&
  echo '=== processes ===' && ps aux --sort=-%mem | head -10 &&
  echo '=== network ===' && ss -tulnp | grep LISTEN
"
```

If you know the local Tailscale IP and need RTT evidence:

```bash
ssh -o StrictHostKeyChecking=no -i <KEY> <USER>@<VPS_HOST> "
  ping -c 3 <LOCAL_TAILSCALE_IP> 2>&1 | tail -3
"
```

Present results as grouped findings instead of pasting a large unstructured block.

## Hermes-Specific Checks

If the VPS runs Hermes, prefer explicit gateway and cron evidence over generic system guesses.

If Hermes is not on the default shell `PATH`, either export it first or use the absolute binary path.

### Recommended runtime inspection

```bash
ssh -o StrictHostKeyChecking=no -i <KEY> <USER>@<VPS_HOST> "
  export PATH=<HERMES_BIN_DIR>:\$PATH
  echo '=== gateway ===' && <HERMES_BIN> gateway status --system &&
  echo '=== cron status ===' && <HERMES_BIN> cron status &&
  echo '=== cron list ===' && <HERMES_BIN> cron list &&
  echo '=== disk ===' && df -h / &&
  echo '=== hermes dirs ===' && du -sh <HERMES_HOME> <HERMES_HOME>/cron/output <HERMES_HOME>/logs <HERMES_HOME>/data 2>/dev/null
"
```

### Output freshness check

When the user asks whether jobs are really running today, inspect recent output artifacts rather than only process state:

```bash
ssh -o StrictHostKeyChecking=no -i <KEY> <USER>@<VPS_HOST> "
  for d in <HERMES_HOME>/cron/output/*/; do
    id=\$(basename \"\$d\")
    latest=\$(find \"\$d\" -maxdepth 1 -type f -printf '%T@ %p\n' 2>/dev/null | sort -rn | head -1 | cut -d' ' -f2-)
    echo \"\$id -> \$(basename \"\$latest\" 2>/dev/null || echo -)\"
  done
"
```

Prioritize interpretation in this order:

1. gateway
2. cron scheduler state
3. latest output artifacts
4. disk or memory pressure

## Dashboard Or Local Web Service Access

For an internal dashboard or local-only service on the VPS:

1. Keep the app bound to `127.0.0.1` on the VPS when possible.
2. Prefer SSH local forwarding first.

```bash
ssh -N -L 8765:127.0.0.1:8765 -i <KEY> <USER>@<VPS_HOST>
```

Then open `http://127.0.0.1:8765` locally.

If Tailscale `serve` is intentionally part of the setup, remember the first enablement may require elevated privileges or an operator assignment.

## Repo-Backed Service Deploy Loop

Use this when the VPS service is backed by a Git checkout or a synced local repo and the user expects the remote behavior to reflect fresh local edits.

### Standard sequence

1. validate the change locally first
2. determine the canonical local repo
3. determine the remote repo path and runtime unit
4. sync the intended code to the VPS
5. restart the relevant service
6. verify code identity and runtime health
7. only then inspect the user-visible behavior

### Minimum remote proof after sync

```bash
ssh -o StrictHostKeyChecking=no -i <KEY> <USER>@<VPS_HOST> "
  cd <REMOTE_REPO> &&
  git rev-parse HEAD &&
  systemctl is-active <SERVICE_NAME> &&
  curl -fsS http://127.0.0.1:<PORT>/api/health
"
```

If the service exposes a build id, commit hash, or UI build marker, verify that too. Prefer runtime truth over assuming a restart picked up the latest file.

### When Git pull is not the actual transport

Some services are updated by `scp` or `rsync` instead of `git pull`.

In that case:

- verify the exact remote file or directory changed
- capture a post-sync proof such as:
  - file timestamp
  - file hash
  - runtime `ui_build`
  - endpoint response containing version metadata

Do not stop after `systemctl restart` alone.

### GitHub Issues Dashboard pattern

For the dashboard service specifically, the safest verification chain is:

1. local repo passes focused validation
2. sync `app.py` and any relevant tests or support files to `/home/ubuntu/.hermes/services/github-issues-dashboard`
3. restart `github-issues-dashboard.service`
4. verify `/api/health`
5. verify `ui_build`
6. verify the changed HTML or API behavior

If local `127.0.0.1:8765` is an SSH tunnel to the VPS, remember that "local page still old" may simply mean the VPS service was not updated yet. Check remote `/api/health` first.

## Web Dashboard Troubleshooting Pitfall

If a FastAPI or SSE endpoint appears alive but real-time updates stall, inspect the app code for blocking calls inside async generators.

In particular, do not use `time.sleep()` inside `async def` event generators. Use `await asyncio.sleep(...)` instead.

For service health plus logs:

```bash
ssh -o StrictHostKeyChecking=no -i <KEY> <USER>@<VPS_HOST> "
  systemctl is-active hermes-gateway.service
  journalctl -u hermes-gateway.service -n 30 --no-pager | tail -30
"
```

## Cron-Focused Checks

```bash
ssh -o StrictHostKeyChecking=no -i <KEY> <USER>@<VPS_HOST> "
  export PATH=<HERMES_BIN_DIR>:\$PATH
  <HERMES_BIN> cron list
"
```

For a specific job:

```bash
ssh -o StrictHostKeyChecking=no -i <KEY> <USER>@<VPS_HOST> "
  ls -lt <HERMES_HOME>/cron/output/<job_id>/ 2>/dev/null | head -3
"
```

If rate limiting or delivery guards are suspected:

```bash
ssh -o StrictHostKeyChecking=no -i <KEY> <USER>@<VPS_HOST> "
  find <HERMES_HOME>/cron/delivery_rate_limit -type f 2>/dev/null
"
```

## File Sync

### Pull sessions

```bash
rsync -az --timeout=30 \
  -e "ssh -o ConnectTimeout=5 -o StrictHostKeyChecking=no -i <KEY>" \
  <USER>@<VPS_HOST>:<HERMES_HOME>/sessions/ \
  ~/.hermes/sessions/
```

### Pull skills

```bash
rsync -az --timeout=30 \
  -e "ssh -o ConnectTimeout=5 -o StrictHostKeyChecking=no -i <KEY>" \
  <USER>@<VPS_HOST>:<HERMES_HOME>/skills/ \
  ~/.hermes/skills/
```

### Pull logs

```bash
rsync -az --timeout=30 \
  -e "ssh -o ConnectTimeout=5 -o StrictHostKeyChecking=no -i <KEY>" \
  <USER>@<VPS_HOST>:<HERMES_HOME>/logs/ \
  /tmp/vps-logs/
```

Adjust the local destination if the user wants a different restore or archive path.

## Common Pitfalls

### Pitfall 1: Using the local macOS username for remote SSH

Do not assume the remote user matches the local machine user. Extract or verify the remote user from a known-good script or SSH config.

### Pitfall 2: Hermes is not on the remote PATH

Remote non-interactive shells often skip profile loading. Use either:

```bash
export PATH=<HERMES_BIN_DIR>:\$PATH
```

or:

```bash
<HERMES_BIN> version
```

### Pitfall 3: Host key changed after rebuild

If the VPS was rebuilt and SSH complains about host key mismatch:

```bash
ssh-keygen -R <VPS_HOST>
```

### Pitfall 4: Running a large command before proving auth works

Always start with:

```bash
ssh -o StrictHostKeyChecking=no -i <KEY> <USER>@<VPS_HOST> "echo ok"
```

### Pitfall 5: Not knowing which SSH key works

Use the probe pattern from `references/ssh-key-probe-pattern.md`. Start with `.pem` files, then `id_*`, and keep `BatchMode=yes` enabled to avoid hanging on password prompts.

### Pitfall 6: Mistaking Tailscale SSH availability for node availability

`tailscale ssh` may be disabled while ordinary SSH to the Tailscale IP still works fine. Confirm node activity first, then test standard SSH.

### Pitfall 7: Writing multi-line Python through SSH with fragile heredocs

See `references/ssh-heredoc-python-trap.md`. Prefer `echo` line-by-line, `python3 -c`, or `python3 -` through stdin instead of a brittle remote heredoc.

### Pitfall 8: Cron output blocked by invisible Unicode

If a Hermes cron run is blocked by prompt-injection scanning because of hidden Unicode, see `references/cron-prompt-injection-unicode-fix.md`.

### Pitfall 9: Treating a healthy service as proof of fresh code

`systemctl is-active` only proves the process is running. It does not prove the VPS is serving the latest intended code.

For repo-backed services, always verify one of:

- remote commit hash
- synced file hash
- runtime build marker
- endpoint version field

before concluding the deploy is current.

### Pitfall 10: Forgetting that localhost may be a tunnel to the VPS

If `http://127.0.0.1:<PORT>` on the Mac is forwarded over SSH, then browser results reflect remote state, not local source files.

When the browser still shows old behavior:

1. inspect the remote `/api/health`
2. inspect the remote build marker or file hash
3. only then blame browser cache

## Reporting Rule

When you finish, include:

- the discovered connection parameters you actually used
- whether the minimal SSH probe succeeded
- grouped health findings
- any concrete next action

Do not edit this canonical skill just because one session discovered a different IP, key, host name, or directory layout.

## Related Skills And References

- `references/ssh-key-probe-pattern.md`
- `references/cron-prompt-injection-unicode-fix.md`
- `references/ssh-heredoc-python-trap.md`
- `hermes-small-vps-operations`
- `remote-hermes-bootstrap`
- `hermes-home-portability`

<!-- skillctl:source-attribution:start -->
## Source Attribution

- origin kind: derived-from-upstream
- upstream repo: local://hermes
- upstream path: devops/tailscale-vps-ops
- pinned ref: 2026-06-10-local-hermes
- source type: local
- source URL: file:///Users/idah/.hermes/skills/devops/tailscale-vps-ops
- imported at: 2026-06-15T03:59:44.353Z
- last verified ref: 2026-06-10-local-hermes
- local modifications: true
<!-- skillctl:source-attribution:end -->
