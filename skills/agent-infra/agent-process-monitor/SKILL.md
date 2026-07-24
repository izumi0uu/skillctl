---
name: agent-process-monitor
description: Install, update, verify, diagnose, or roll back the macOS xbar Agent Process Monitor that attributes local OMP, Codex, Claude Code, OpenCode, Pi, and MCP process trees. Use when maintaining the menu-bar monitor, investigating its session/worker/MCP hierarchy, or shipping a new monitor version through skillctl.
---

# Agent Process Monitor

Own the local macOS Agent Process Monitor as a canonical `skillctl`-managed product. The monitor is a read-only xbar plugin: it samples process metadata, attributes each process to one agent runtime, and renders session, worker, MCP-instance, support, and other Desktop process hierarchy.

## Ownership Boundary

For monitor runtime behavior, `plugin/mcp-monitor.15s.py` is the sole canonical source. The lifecycle manager and deterministic verifier are supporting skill code.

Derived copies are not source:

- agent install mirrors such as `~/.codex/skills/agent-process-monitor/`;
- the live xbar plugin at `~/Library/Application Support/xbar/plugins/mcp-monitor.15s.py`;
- install metadata and backups under `~/.local/state/skillctl/agent-process-monitor/`.

Never hand-edit a derived copy. Change the canonical plugin, update its deterministic verifier, sync the skill, then install it through the lifecycle manager.

## Requirements

- macOS with xbar installed.
- Python 3.10 or newer available to xbar.
- `/usr/bin/ps` and `/usr/sbin/lsof`.
- Read access to local agent session metadata when evidence-backed titles are desired.

The plugin never sends signals, reads process environments, or writes agent runtime state.

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

Then allow one 15-second xbar refresh and inspect the live menu. Session rows must remain evidence-only; the Worker row owns MCP and Support submenus.

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
7. Verify direct output and at least two real xbar refreshes when hierarchy or session evidence changes.

Lifecycle-manager-only changes update the skill catalog hash but do not require a plugin version bump.

## Runtime Invariants

- Every process belongs to at most one top-level agent runtime.
- Session names are evidence associations, not resource owners.
- Shared Codex Desktop resources are never attributed per session.
- MCP instances are disjoint direct-child subtrees and preserve real PPID hierarchy.
- Session evidence is accepted only from requested PID records and canonical paths under `~/.codex/sessions`.
- Unknown xbar parameters are forbidden.
- Collection failures fail visibly without killing or cleaning processes.

## Safety

- Run `status` and `verify` before any install or rollback.
- Do not manually copy into xbar, agent mirrors, or state directories.
- Do not rename the live `mcp-monitor.15s.py` target without an explicit migration that prevents duplicate xbar plugins.
- Do not use this skill to kill, pool, or clean MCP processes.
- Preserve unrelated managed skills; use `skillctl` as the distribution control plane.
