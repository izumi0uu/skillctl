---
name: ego-browser-guard
description: Install, audit, test, repair, or remove the temporary macOS guard that replaces Ego Lite's broadly triggered ego-browser skill with a narrow on-demand wrapper while keeping the ego-browser executable available.
---

# Ego Browser Guard

Use this skill to maintain the temporary workaround for Ego Lite versions that
install or restore a broadly triggered `ego-browser` skill. Do not use this
skill to operate websites; use the separately installed `ego-browser` wrapper
when a browser task actually meets its narrow trigger.

## What It Protects

The guard keeps Ego Lite available while preventing ordinary public web
research from selecting it by default:

- `~/.agents/skills/ego-browser` is kept as the bundled narrow wrapper.
- recognized Ego vendor copies or symlinks at that path are quarantined.
- recognized Ego vendor copies at `~/.codex/skills/ego-browser` are quarantined.
- a macOS LaunchAgent watches both skill roots and reapplies the policy when an
  Ego launch or update restores the vendor skill.
- the `ego-browser` executable and Ego application bundle are not removed or
  modified.

The workaround affects newly assembled agent context. A task that already
loaded the vendor skill can retain its old trigger language until a new task is
started.

## Trigger Policy Installed By The Guard

Ego Lite is allowed when:

- the user explicitly requests Ego Lite or `ego-browser`;
- authenticated or session-bound browser state is required;
- an interactive form or browser-only workflow must be submitted;
- browser visual verification is required;
- a Web App needs browser-based testing.

Public documentation, GitHub content, APIs, and other public static content do
not qualify merely because they are rendered with JavaScript. Use a connector,
CLI, API, or direct HTTP first.

## Workflow

Set `SKILL_DIR` to this installed skill directory. In Codex it is normally:

```bash
SKILL_DIR="$HOME/.codex/skills/ego-browser-guard"
```

For canonical development, use:

```bash
SKILL_DIR="<skillctl-repo>/skills/agent-infra/ego-browser-guard"
```

### 1. Run Offline Regression Tests

```bash
sh "$SKILL_DIR/scripts/test-ego-skill-guard.sh"
```

The test uses a temporary home and must pass before changing the live
installation.

### 2. Inspect The Live State

```bash
sh "$SKILL_DIR/scripts/manage-ego-skill-guard.sh" status
```

### 3. Install Or Repair

```bash
sh "$SKILL_DIR/scripts/manage-ego-skill-guard.sh" install
```

Installation is idempotent. Changed manager-owned runtime files and a legacy
LaunchAgent are backed up under `~/.local/share/ego-skill-guard/backups/`.

### 4. Verify After Installation

```bash
sh "$SKILL_DIR/scripts/manage-ego-skill-guard.sh" status
sh "$SKILL_DIR/scripts/test-ego-skill-guard.sh"
```

Confirm that status reports a local narrow wrapper, no Codex vendor copy, and
the `app.local.ego-skill-guard` LaunchAgent as loaded.

### 5. Remove The Temporary Workaround

Only remove it when Ego Lite no longer injects the broad skill:

```bash
sh "$SKILL_DIR/scripts/manage-ego-skill-guard.sh" uninstall
```

Uninstall removes only files carrying this guard's ownership marker. It keeps
quarantined vendor copies and backups for manual recovery.

## Safety

- Never edit the Ego application bundle; updates and code signing own it.
- Never quarantine an unknown `ego-browser` skill. The guard must fail closed
  when ownership cannot be recognized.
- Keep the quarantine until the upstream trigger bug is fixed and verified.
- Run `skillctl sync` before installing from an agent mirror so runtime files
  match the canonical skill.
- Do not infer success from a loaded LaunchAgent alone; verify wrapper state as
  well.
