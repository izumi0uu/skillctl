---
name: codex-session-recovery
description: Use when Codex chats were accidentally archived and the user wants to find, unarchive, or restore local Codex conversation history from `~/.codex/archived_sessions` back into the visible session list.
---

# Codex Session Recovery

## Overview
- Use this skill for local Codex chat history recovery on this machine.
- The common case is accidental archive, not deletion.
- Archived conversations usually still exist as JSONL rollout files under `~/.codex/archived_sessions`.
- Visibility is controlled by both:
  - the rollout file path
  - `~/.codex/state_5.sqlite`, table `threads`, column `archived`

## When To Use
- The user says a Codex chat was archived by mistake.
- The user asks to recover recent Codex chats.
- The user asks where Codex local conversation history lives.
- The user asks to restore a specific Codex session ID.

## Boundaries
- Do not treat archive recovery as deletion recovery unless the rollout file is missing.
- Do not edit project repository files for this task.
- Prefer copying archived rollout files back into `sessions/YYYY/MM/DD` instead of moving them.
- Always back up `state_5.sqlite` before writing to it.
- If Codex/Cursor is open, tell the user the history list may require a restart or panel reload to refresh.

## Local Storage Model
- Main database:
  - `~/.codex/state_5.sqlite`
- Archived rollout files:
  - `~/.codex/archived_sessions/*.jsonl`
- Visible rollout files:
  - `~/.codex/sessions/YYYY/MM/DD/*.jsonl`
- Important table:
  - `threads`
- Important columns:
  - `id`
  - `title`
  - `created_at`
  - `updated_at`
  - `rollout_path`
  - `archived`
  - `archived_at`

## Workflow

### 1. Inspect Archived Candidates
- List archived threads before restoring:

```bash
sqlite3 ~/.codex/state_5.sqlite \
  "select id, title, datetime(created_at,'unixepoch','localtime'), rollout_path from threads where archived=1 order by created_at desc limit 20;"
```

- Prefer `created_at desc` for "recent chats".
- Be careful with `updated_at` if many sessions were archived in a batch; they can share the archive timestamp and produce a misleading order.

### 2. Restore With The Script
- Use the bundled script for normal recovery:

```bash
~/.codex/skills/codex-session-recovery/scripts/restore-codex-sessions.sh --last 3
```

- Restore a specific session:

```bash
~/.codex/skills/codex-session-recovery/scripts/restore-codex-sessions.sh --id 019dc807-6a03-7bb3-b32c-d278be243185
```

- Preview without writing:

```bash
~/.codex/skills/codex-session-recovery/scripts/restore-codex-sessions.sh --last 5 --dry-run
```

### 3. Verify
- Confirm restored sessions have `archived=0` and point to `~/.codex/sessions/...`:

```bash
sqlite3 ~/.codex/state_5.sqlite \
  "select id, title, archived, rollout_path from threads where archived=0 order by created_at desc limit 10;"
```

- Confirm the rollout files exist in `~/.codex/sessions/YYYY/MM/DD`.

### 4. Report Back
- Say which sessions were restored.
- Mention the SQLite backup path.
- Mention whether a Codex/Cursor panel restart may be needed.

## Failure Handling
- If `state_5.sqlite` is missing, stop and report that local Codex state was not found.
- If an archived rollout file is missing, do not update that row; report the missing path.
- If the database update fails, keep the backup and report the exact failure.
- If a previous partial restore copied a file but did not update SQLite, rerun the script; it handles existing destination files.

## Tiny But Important Details
- On macOS, `cp -n` can return a non-zero status when a destination file already exists, which can interrupt scripts under `set -e`.
- A fully visible restored session needs both:
  - `threads.archived = 0`
  - `threads.rollout_path` pointing to the visible `sessions/YYYY/MM/DD` path
- Copying the JSONL file alone may leave the chat hidden.
- Flipping `archived` alone while `rollout_path` still points at `archived_sessions` can leave future behavior confusing.
