---
name: personal-xbar
description: Install, update, verify, diagnose, or roll back the Personal xbar menu that combines local agent process inventory, AI.INPUT.IM model health, and Spotify Web playback controls with advertisement auto-mute. Use when maintaining this personal macOS menu-bar bundle, adding feature plugins, investigating notifications or Spotify behavior, or shipping a version through skillctl.
---

# Personal xbar

Own the local Personal xbar bundle as a canonical `skillctl`-managed product. Its registered plugins inventory local agent processes, read the public AI.INPUT.IM status API with transition-only failure and recovery notifications, and control Spotify Web playback while automatically muting advertisements.

## Ownership Boundary

`plugin/personal-xbar.15s.py` is the thin executable entrypoint. The `15s` suffix is xbar's refresh declaration, not the product or skill name. Feature plugins are registered only in `plugin/personal_xbar/app.py`:

- `plugins/processes.py` collects and renders the agent process inventory;
- `plugins/ai_input.py` collects model probe status and owns health transitions;
- `plugins/spotify.py` collects playback state and registers playback actions;
- `runtime.py` contains shared domain behavior retained by those plugins.

Derived copies are not source:

- agent install mirrors such as `~/.codex/skills/personal-xbar/`;
- the live entrypoint at `~/Library/Application Support/xbar/plugins/personal-xbar.15s.py`;
- the hidden live package at `~/Library/Application Support/xbar/plugins/.personal-xbar/personal_xbar/`;
- install metadata and transactional backups under `~/.local/state/skillctl/personal-xbar/`;
- model-status, notification, and Spotify mute ownership state under `~/Library/Caches/skillctl/personal-xbar/`.

Never hand-edit a derived copy. Change the canonical plugin, update its deterministic verifier, sync the skill, then install it through the lifecycle manager.

## Requirements

- macOS with xbar installed.
- Python 3.10 or newer available to xbar.
- `/usr/bin/ps` and `/usr/sbin/lsof`.
- Network access to `https://status.input.im/api/status` for model health.
- `/usr/bin/osascript` for failure and recovery notifications.
- Google Chrome for Spotify Web controls.
- Chrome menu `View > Developer > Allow JavaScript from Apple Events` enabled for Spotify playback inspection and page-local media control.
- Read access to local agent session metadata when evidence-backed titles are desired.

The plugin never sends signals, reads process environments, or writes agent runtime state. Its only filesystem writes are its own mode-`0600` model-status and Spotify mute-ownership state files. A status outage or missing Chrome permission degrades visibly without hiding the local process inventory.

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

## Spotify Web Behavior

- The menu-bar title and Spotify submenu show playing, paused, advertisement, or unavailable state.
- The submenu actions control previous track, play/pause, and next track without activating the browser window.
- Advertisement detection and mute enforcement run on the xbar 15-second refresh, so a transition can take up to one refresh cycle to be applied.
- Auto-mute first toggles Spotify's own mute button inside the first open `https://open.spotify.com/` Chrome tab, with `audio` and `video` element `muted` properties as a fallback. It does not change the saved Spotify volume value or mute other tabs.
- Mute ownership is persisted. A page that was already muted before an advertisement remains muted afterward; only a mute initiated by the monitor is restored.
- If Chrome is closed, no Spotify tab is open, page controls change, or JavaScript from Apple Events is disabled, the menu reports the condition and leaves playback untouched.

Optional environment overrides:

```text
SPOTIFY_WEB_ENABLED=0
SPOTIFY_WEB_AUTOMUTE=0
SPOTIFY_BROWSER_APP=Google Chrome
SPOTIFY_WEB_STATE_FILE=/custom/cache/spotify-web.json
```

## Locate The Current Skill

Use the active agent's installed skill directory as `SKILL_DIR`. For Codex this is normally:

```bash
SKILL_DIR="$HOME/.codex/skills/personal-xbar"
```

For canonical development, use:

```bash
SKILL_DIR="<skillctl-repo>/skills/agent-infra/personal-xbar"
```

## Workflow

### 1. Inspect Without Mutating

```bash
python3 "$SKILL_DIR/scripts/manage_personal_xbar.py" status
```

Status reports canonical and installed versions, SHA-256 hashes, target mode, latest backup, and one of: `not-installed`, `current`, `drifted`, or `invalid`.

### 2. Verify Canonical Source

```bash
python3 "$SKILL_DIR/scripts/manage_personal_xbar.py" verify
```

This compiles the plugin and runs the bundled deterministic contract. Fix canonical source or verifier failures before installation.

### 3. Install Or Update

```bash
python3 "$SKILL_DIR/scripts/manage_personal_xbar.py" install
```

Installation is transactional: verify source, back up a changed target, atomically replace it with mode `0755`, verify the installed copy, write mode-`0600` metadata, and automatically restore the prior target if post-install verification fails. An already-current target is a no-op.

### 4. Verify The Installed Copy

```bash
python3 "$SKILL_DIR/scripts/manage_personal_xbar.py" verify --installed
```

Then allow one 15-second xbar refresh and inspect the live menu. Session rows must remain evidence-only; the Worker row owns MCP and Support submenus. The title must include the API healthy/total count, and the AI.INPUT.IM submenu must preserve process inventory when the status service is unavailable.

### 5. List And Restore Backups

```bash
python3 "$SKILL_DIR/scripts/manage_personal_xbar.py" list-backups
python3 "$SKILL_DIR/scripts/manage_personal_xbar.py" rollback '<backup-name>'
```

Rollback accepts only a manager-owned backup basename under the configured state root. It verifies the backup, backs up the current target, restores atomically, and verifies the result.

## Iterating On The Monitor

For every behavior change:

1. Edit the relevant module under `plugin/personal_xbar/plugins/` or shared `runtime.py`.
2. Bump the `<xbar.version>` header.
3. Extend `scripts/verify_personal_xbar.py` with an observable contract that would fail for a plausible regression.
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
- Model-status and Spotify mute-ownership state contain no credentials and are written atomically with mode `0600`.
- Model failure and recovery notifications are transition-only; verifier runs disable notifications and use isolated state.
- Spotify auto-mute never restores a page that was already muted before the advertisement.

## Safety

- Run `status` and `verify` before any install or rollback.
- Do not manually copy into xbar, agent mirrors, or state directories.
- Do not remove `.15s` from the live entrypoint; xbar uses it to schedule refreshes. The manager migrates and backs up the legacy `mcp-monitor.15s.py` target to prevent duplicates.
- Do not use this skill to kill, pool, or clean MCP processes.
- Do not add an AI.INPUT.IM API key or replace the official public status feed with paid completion probes.
- Keep Spotify JavaScript scoped to `open.spotify.com`; do not inspect unrelated Chrome tabs or browser history.
- Preserve unrelated managed skills; use `skillctl` as the distribution control plane.
