---
name: agent-process-monitor
description: Install, update, verify, diagnose, or roll back the macOS xbar Agent Process Monitor that attributes local OMP, Codex, Claude Code, OpenCode, Pi, and MCP process trees and displays AI.INPUT.IM model health. Use when maintaining the menu-bar monitor, investigating its process hierarchy or model-status notifications, or shipping a new monitor version through skillctl.
---

# Agent Process Monitor

Own the local macOS Agent Process Monitor as a canonical `skillctl`-managed product. The monitor samples process metadata, attributes each process to one agent runtime, and renders session, worker, MCP-instance, support, and other Desktop process hierarchy. It also reads the public AI.INPUT.IM status API, caches the summarized response, and sends transition-only macOS notifications for model failure and recovery.

## Ownership Boundary

For monitor runtime behavior, `plugin/mcp-monitor.15s.py` is the sole canonical source. The lifecycle manager and deterministic verifier are supporting skill code.

Derived copies are not source:

- agent install mirrors such as `~/.codex/skills/agent-process-monitor/`;
- the live xbar plugin at `~/Library/Application Support/xbar/plugins/mcp-monitor.15s.py`;
- install metadata, transactional backups, and provenance-only legacy artifacts under `~/.local/state/skillctl/agent-process-monitor/`; legacy artifacts are not rollback candidates.
- the model-status cache and notification state under `~/Library/Caches/skillctl/agent-process-monitor/`.

Never hand-edit a derived copy. Change the canonical plugin, update its deterministic verifier, sync the skill, then install it through the lifecycle manager.

## Requirements

- macOS with xbar installed.
- Python 3.10 or newer available to xbar.
- `/usr/bin/ps` and `/usr/sbin/lsof`.
- Network access to `https://status.input.im/api/status` for model health.
- `/usr/bin/osascript` for failure and recovery notifications.
- Read access to local agent session metadata when evidence-backed titles are desired.

The plugin never sends signals, reads process environments, or writes agent runtime state. Its only write is its own mode-`0600` model-status cache. A status outage degrades visibly without hiding the local process inventory.

## Model Health Behavior

- The public official status API is polled at most once every 55 seconds, matching its approximately 60-second probe cadence.
- The xbar title shows `API healthy/total`; the submenu shows each model's latest state, latency, and 60-sample uptime.
- A reported model failure notifies once. Continued failures do not repeat the notification.
- Status API connectivity must fail twice consecutively before it notifies, while the menu reports the first failure immediately.
- Recovery notifies once only when a prior failure notification was active. Initial healthy startup stays quiet.
- The monitor does not call a paid completion endpoint and does not read or store an API key.

Optional environment overrides:

```text
AI_INPUT_NOTIFICATIONS=0
AI_INPUT_STATUS_URL=https://status.input.im/api/status
AI_INPUT_STATUS_PAGE_URL=https://status.input.im
AI_INPUT_MONITOR_STATE_FILE=/custom/cache/path.json
```

## Locate The Current Skill

Use the active agent's installed skill directory as `SKILL_DIR`. For Codex this is normally:

```bash
SKILL_DIR="$HOME/.codex/skills/agent-process-monitor"
```

For canonical development, use:

```bash
SKILL_DIR="<skillctl-repo>/skills/agent-infra/agent-process-monitor"
```

## Workflow

### 1. Inspect Without Mutating

```bash
python3 "$SKILL_DIR/scripts/manage_agent_process_monitor.py" status
```

Status reports canonical and installed versions, SHA-256 hashes, target mode, latest backup, and one of: `not-installed`, `current`, `drifted`, or `invalid`.

### 2. Verify Canonical Source

```bash
python3 "$SKILL_DIR/scripts/manage_agent_process_monitor.py" verify
```

This compiles the plugin and runs the bundled deterministic contract. Fix canonical source or verifier failures before installation.

### 3. Install Or Update

```bash
python3 "$SKILL_DIR/scripts/manage_agent_process_monitor.py" install
```

Installation is transactional: verify source, back up a changed target, atomically replace it with mode `0755`, verify the installed copy, write mode-`0600` metadata, and automatically restore the prior target if post-install verification fails. An already-current target is a no-op.

### 4. Verify The Installed Copy

```bash
python3 "$SKILL_DIR/scripts/manage_agent_process_monitor.py" verify --installed
```

Then allow one 15-second xbar refresh and inspect the live menu. Session rows must remain evidence-only; the Worker row owns MCP and Support submenus. The title must include the API healthy/total count, and the AI.INPUT.IM submenu must preserve process inventory when the status service is unavailable.

### 5. List And Restore Backups

```bash
python3 "$SKILL_DIR/scripts/manage_agent_process_monitor.py" list-backups
python3 "$SKILL_DIR/scripts/manage_agent_process_monitor.py" rollback '<backup-name>'
```

Rollback accepts only a manager-owned backup basename under the configured state root. It verifies the backup, backs up the current target, restores atomically, and verifies the result.

## Iterating On The Monitor

For every behavior change:

1. Edit `plugin/mcp-monitor.15s.py` in the canonical skillctl repository.
2. Bump the `<xbar.version>` header.
3. Extend `scripts/verify_agent_process_monitor.py` with an observable contract that would fail for a plausible regression.
4. Run canonical verification, Python compilation, Ruff, and relevant tests.
5. Run `skillctl discover`, inspect catalog provenance/taxonomy, then `skillctl sync`.
6. Install through the lifecycle manager.
7. Verify direct output and at least two real xbar refreshes when hierarchy, session evidence, model status, or notifications change.

Lifecycle-manager-only changes update the skill catalog hash but do not require a plugin version bump.

## Runtime Invariants

- Every process belongs to at most one top-level agent runtime.
- Session names are evidence associations, not resource owners.
- Shared Codex Desktop resources are never attributed per session.
- MCP instances are disjoint direct-child subtrees and preserve real PPID hierarchy.
- Session evidence is accepted only from requested PID records and canonical paths under `~/.codex/sessions`.
- Unknown xbar parameters are forbidden.
- Collection failures fail visibly without killing or cleaning processes.
- Model-status state contains no credentials and is written atomically with mode `0600`.
- Model failure and recovery notifications are transition-only; verifier runs disable notifications and use isolated state.

## Safety

- Run `status` and `verify` before any install or rollback.
- Do not manually copy into xbar, agent mirrors, or state directories.
- Do not rename the live `mcp-monitor.15s.py` target without an explicit migration that prevents duplicate xbar plugins.
- Do not use this skill to kill, pool, or clean MCP processes.
- Do not add an AI.INPUT.IM API key or replace the official public status feed with paid completion probes.
- Preserve unrelated managed skills; use `skillctl` as the distribution control plane.
