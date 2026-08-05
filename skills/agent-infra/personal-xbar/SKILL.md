---
name: personal-xbar
description: Install, update, verify, diagnose, or roll back the Personal xbar menu that combines local agent process inventory, AI.INPUT.IM model health and authenticated subscription quota, and Spotify Web playback controls with advertisement auto-mute. Use when maintaining this personal macOS menu-bar bundle, adding feature plugins, investigating notifications or browser integration, or shipping a version through skillctl.
---

# Personal xbar

Own the local Personal xbar bundle as a canonical `skillctl`-managed product. Its registered plugins inventory local agent processes, read the public AI.INPUT.IM status API, monitor authenticated AI.INPUT.IM subscription quota with transition-only notifications, and control Spotify Web playback while automatically muting advertisements.

## Ownership Boundary

`plugin/personal-xbar.15s.py` is the thin executable entrypoint. The `15s` suffix is xbar's refresh declaration, not the product or skill name. Feature plugins are registered only in `plugin/personal_xbar/app.py`:

- `plugins/processes.py` collects and renders the agent process inventory;
- `plugins/ai_input.py` collects model probe status and owns health transitions;
- `plugins/subscription_quota.py` collects authenticated subscription quota and owns its threshold transitions;
- `plugins/spotify.py` collects playback state and registers playback actions;
- `plugins/title_settings.py` reads persistent title preferences and registers the
  six fixed menu-bar toggle actions;
- `runtime.py` contains shared domain behavior retained by those plugins;
  `ai_input_auth.py` owns the Keychain credential record and refresh-safe locking.

Derived copies are not source:

- agent install mirrors such as `~/.codex/skills/personal-xbar/`;
- the live entrypoint at `~/Library/Application Support/xbar/plugins/personal-xbar.15s.py`;
- the hidden live package at `~/Library/Application Support/xbar/plugins/.personal-xbar/personal_xbar/`;
- install metadata and transactional backups under `~/.local/state/skillctl/personal-xbar/`;
- model-status, subscription-quota notification, and Spotify mute ownership state under `~/Library/Caches/skillctl/personal-xbar/`.
- title preferences and their lock under
  `~/Library/Application Support/skillctl/personal-xbar/`.

Never hand-edit a derived copy. Change the canonical plugin, update its deterministic verifier, sync the skill, then install it through the lifecycle manager.

## Requirements

- macOS with xbar installed.
- Python 3.9 or newer available to xbar.
- `/usr/bin/ps` and `/usr/sbin/lsof`.
- Network access to `https://status.input.im/api/status` for model health.
- `/usr/bin/osascript` for failure and recovery notifications.
- macOS Keychain access for the generic-password item used by the direct quota probe.
- Configure quota credentials locally with
  `/usr/bin/python3 scripts/manage_personal_xbar.py auth set`; do not put tokens in shell
  arguments or chat. The quota monitor never reads a Chrome login session.
- Google Chrome with an `open.spotify.com` tab is required only for Spotify Web controls.
- Multiple same-name Chrome processes are supported: Apple Events are sent directly to
  foreground browser process IDs, so a background headless Chrome cannot capture the probe.
- macOS `System Settings > Privacy & Security > Automation` permission for xbar to
  control Google Chrome when Spotify controls are used.
- Chrome menu `View > Developer > Allow JavaScript from Apple Events` enabled for
  Spotify playback inspection and page-local media control.
- Read access to local agent session metadata when evidence-backed titles are desired.

The plugin never sends signals, reads process environments, reads browser sessions,
or writes agent runtime state. Rotating access and refresh tokens are stored only as
one JSON value, together with the non-secret request User-Agent, in
the user's login Keychain item
`skillctl.personal-xbar.ai-input-auth` / `subscriptions`; they are never written to
the cache, command line, or logs. Its filesystem writes are limited to its own
mode-`0600` title-preference, model-status, subscription-quota, refresh-lock, and
Spotify mute-ownership state files. A status outage, expired token, or Spotify browser
permission failure degrades visibly without hiding the local process inventory.

## Menu Bar Title Behavior

- The `Menu bar fields` submenu provides persistent checkboxes for agent count,
  CPU, memory, model API health, subscription quota, and Spotify playback.
- A toggle changes only the compact menu-bar text. All collectors, submenu details,
  notifications, and Spotify advertisement auto-mute continue to run.
- Global title color continues to reflect monitored health even when the related text
  field is hidden, so hiding quota or API text does not silence a critical state.
- If all six fields are hidden, the title falls back to `PX` so the menu remains
  clickable and its fields can be restored.
- Preferences are schema-validated, atomically replaced with mode `0600`, and guarded
  by a separate process lock so rapid changes to different fields are not lost.
- Missing, damaged, partial, or older preference data fails open: every unspecified
  field remains visible. Newly introduced fields therefore appear by default.

Optional environment override:

```text
PERSONAL_XBAR_TITLE_SETTINGS_FILE=/custom/preferences/title-settings.json
```

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

## Subscription Quota Behavior

- Subscription quota is a separate registered plugin from public model health. Disabling it does not disable the public status probe or local process inventory.
- The monitor calls the official `https://ai.input.im/api/v1/subscriptions` endpoint
  directly with credentials from macOS Keychain. Chrome login state is never used.
- The direct request sends only `Authorization: Bearer <access_token>` and the
  configured request User-Agent to the exact HTTPS `ai.input.im` origin.
  Redirects to another origin are rejected and response bodies are bounded and
  never copied into errors.
- The access token is refreshed about 120 seconds before its server-provided
  `expires_in` deadline. A refresh atomically replaces the rotated access/refresh
  pair in Keychain; a 401 triggers one refresh-and-retry. There is deliberately no
  fixed three-day schedule because the service controls refresh-token TTL.
- Keychain credentials are the only quota identity. If they are absent, the menu shows
  `secure token not configured`; it does not inspect or fall back to any browser profile.
- Legacy browser-sourced cache entries are rejected immediately, so installing this
  version cannot continue displaying quota captured from Chrome during the old cache TTL.
- Successful quota results are cached for 55 seconds. The xbar 15-second refresh therefore does not repeatedly call the account endpoint.
- The menu summary combines usage and limits across active plans for each quota
  period, selects the highest-utilization period, and shows that period's remaining
  quota. This is limit-weighted, not a single-plan maximum or an unweighted average;
  daily, weekly, and monthly limits are never added together.
- The menu shows each active plan's status, expiration, and quota usage, including its reset time when supplied by the service.
- A plan is shown as unlimited only when the API supplies explicit limit fields with no
  finite limits. An active plan whose quota fields are incomplete is marked unavailable
  instead of silently disabling alerts.
- Plan usage percentages are rounded down. Summary remaining percentages are rounded
  up, so `99.99%` used shows `1%` left and only usage at or above the limit shows `0%`.
- Usage crossing 80%, 90%, or 100% (exhausted) sends one transition notification at each threshold. Continued refreshes in the same band stay quiet.
- A reset or recovery sends one notification after usage falls below 80%. Initial startup below 80% stays quiet.
- Missing credentials, a rejected refresh token, and API/network failures are reported
  as distinct unavailable quota states without suppressing other menu sections.

Optional environment overrides:

```text
AI_INPUT_SUBSCRIPTIONS_ENABLED=0
AI_INPUT_SUBSCRIPTIONS_NOTIFICATIONS=0
AI_INPUT_SUBSCRIPTIONS_PAGE_URL=https://ai.input.im/subscriptions
AI_INPUT_SUBSCRIPTIONS_STATE_FILE=/custom/cache/ai-input-subscriptions.json
AI_INPUT_REFRESH_LOCK_FILE=/custom/cache/ai-input-refresh.lock
```

The page URL override changes only the menu's Open action. Keychain service/account
names can be overridden for isolated testing with
`AI_INPUT_KEYCHAIN_SERVICE` and `AI_INPUT_KEYCHAIN_ACCOUNT`.

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

Then allow one 15-second xbar refresh and inspect the live menu. Session rows must remain evidence-only; the Worker row owns MCP and Support submenus. Enabled title fields must render without empty separators, and the `Menu bar fields` checkboxes must match their persisted state. The AI.INPUT.IM health and subscription submenus must preserve process inventory when either service is unavailable. Quota must come only from the direct API; without Keychain credentials it must show `secure token not configured`, regardless of Chrome state.

To manage the local credential record, use the lifecycle manager on the same Mac:

```bash
/usr/bin/python3 "$SKILL_DIR/scripts/manage_personal_xbar.py" auth set
/usr/bin/python3 "$SKILL_DIR/scripts/manage_personal_xbar.py" auth status
/usr/bin/python3 "$SKILL_DIR/scripts/manage_personal_xbar.py" auth test
/usr/bin/python3 "$SKILL_DIR/scripts/manage_personal_xbar.py" auth delete
```

`auth set` prompts for both tokens without echoing them and refuses a terminal that
cannot guarantee hidden input. The access-token prompt explicitly asks for the
token value only; do not include the `Bearer ` prefix from an HTTP header. It never
inspects Chrome. Supply the token's
non-secret request User-Agent with `auth set --user-agent '<value>'`, or enter it at
the plain-text prompt. It derives a JWT expiry when possible;
`auth set --expires-in <seconds>` can supply an opaque token's access expiry. The
refresh service's own `expires_in` replaces that estimate after the first rotation.
Use `/usr/bin/python3` for these auth commands so the Keychain item is created by
the same interpreter xbar normally launches on macOS.

Do not let another client actively use the same rotating refresh token. If the token
pair was obtained from a browser session, stop that session after extraction without
logging it out; otherwise either client may consume the next refresh token first.
When the service enables IP/User-Agent session binding, provide the issuing
User-Agent explicitly and keep the same outward network path.

### 5. List And Restore Backups

```bash
python3 "$SKILL_DIR/scripts/manage_personal_xbar.py" list-backups
python3 "$SKILL_DIR/scripts/manage_personal_xbar.py" rollback '<backup-name>'
```

Rollback accepts only a manager-owned backup basename under the configured state root. It verifies the backup, backs up the current target, restores atomically, and verifies the result.

## Iterating On The Monitor

For every behavior change:

1. Edit the relevant module under `plugin/personal_xbar/plugins/`, `runtime.py`, or `ai_input_auth.py`.
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
- Title visibility never disables collection, notifications, advertisement auto-mute,
  or submenu details; an all-hidden title retains the `PX` menu entry.
- Model-status, subscription-quota, refresh-lock, and Spotify mute-ownership state contain no credentials and are written atomically with mode `0600`; rotating tokens exist only in the Keychain item.
- Model failure and recovery notifications are transition-only; verifier runs disable notifications and use isolated state.
- Subscription quota alerts are transition-only at 80%, 90%, and exhausted; reset recovery occurs only below 80%.
- Authenticated subscription collection uses only the exact official API with
  Keychain tokens. It never reads a rendered browser view, switches browser profiles,
  or persists browser cookies or storage.
- Spotify auto-mute never restores a page that was already muted before the advertisement.

## Safety

- Run `status` and `verify` before any install or rollback.
- Do not manually copy into xbar, agent mirrors, or state directories.
- Do not remove `.15s` from the live entrypoint; xbar uses it to schedule refreshes. The manager migrates and backs up the legacy `mcp-monitor.15s.py` target to prevent duplicates.
- Do not use this skill to kill, pool, or clean MCP processes.
- Do not add an AI.INPUT.IM API key or replace the official public status feed with paid completion probes.
- Do not copy AI.INPUT.IM cookies, browser storage, or API keys into plugin state. User-supplied access/refresh tokens may be entered only through the manager's hidden `auth set` prompt and are kept in the macOS login Keychain, never in state JSON.
- Do not treat a fixed three-day timer as token validity. Use the server's `expires_in`, rotate the refresh token atomically, and require a new hidden `auth set` after a rejected refresh or session-binding failure.
- Do not let xbar and another client actively share one rotating refresh token.
  Supply `--user-agent` manually when the service binds a token to its issuing client.
- Keep Spotify JavaScript scoped to `open.spotify.com`; do not inspect unrelated Chrome tabs or browser history.
- Preserve unrelated managed skills; use `skillctl` as the distribution control plane.
