---
name: rename-codex-sessions
description: Rename many Codex threads or local session files by summarizing their content into concise, unique, stable titles. Use when the user asks to rename all sessions, rescan unnamed sessions, deduplicate repeated session responsibilities with numbering, create a title manifest, preview/apply/revert batch Codex thread titles, or organize Codex session history across projects.
---

# Rename Codex Sessions

Use this skill to batch-name Codex conversations from their actual work content while preserving a manifest, backups, and safe rollback data. Keep it project-neutral: titles should describe the session's job, not only the current repository.

## Resource Loading

- Read `references/title-policy.md` before generating or validating titles.
- Use `scripts/summarize_session_jsonl.py` only for local JSONL session files. Prefer Codex App thread tools when they are available.
- Use `scripts/plan_titles.py` to normalize candidate manifests, deduplicate repeated responsibilities, and decide safe apply/skip actions.
- Use `scripts/validate_titles.py` before any batch apply.
- Use `scripts/make_backup.py` before any write path that can change persistent titles.

## Workflow

1. Choose the scan source.
   - Prefer Codex App tools for visible threads: `list_threads`, then `read_thread`, then `set_thread_title`.
   - Use local JSONL scanning only when the user asks for historical/all sessions, App tools are incomplete, or the target is outside the App thread list.
   - Do not mix sources in one manifest unless each item records its source.

2. Build a backup first.
   - Save `thread_id` or `session_path`, `old_title`, source, timestamp, and host when available.
   - For App threads, backup before calling `set_thread_title`.
   - For direct database or file writes, create a physical backup of the writable target before editing.

3. Gather compact evidence.
   - For App threads: read enough recent and older turns to recover the actual task, not just the final "continue".
   - For JSONL: extract user messages, assistant summaries, cwd/project hints, branch/tool hints, first/last timestamps, and any final completion report.
   - Do not include secrets, raw clinical payloads, long command output, image base64, or private environment values in the manifest.

4. Generate candidate titles.
   - Prefer concise noun or verb-object phrases.
   - Use the earliest clear user objective, final artifact, changed files, and project/domain hints.
   - Avoid generic titles such as `continue`, `start implementation`, `debug`, `fix`, or `review`.
   - Preserve a good existing human-written title unless the user explicitly requested overwrite.

5. Deduplicate responsibilities.
   - Normalize punctuation, whitespace, case, and numeric suffixes.
   - If several sessions share the same responsibility, append a plain numeric suffix: `Session Batch Naming`, `Session Batch Naming 2`, `Session Batch Naming 3`.
   - If sessions differ by phase, prefer phase titles over numbering: `Session Naming Plan`, `Session Naming Execution`, `Session Naming Rescan`.

6. Create a manifest.
   - Include every scanned item, even skipped ones.
   - Record `old_title`, `candidate_title`, `final_title`, `reason`, `confidence`, and `action`.
   - Use actions: `rename`, `skip-good-title`, `skip-low-confidence`, `skip-running`, `skip-unsafe`, `manual-review`.

7. Validate before applying.
   - Run `validate_titles.py` on the manifest.
   - Fix duplicate titles, empty titles, overlong titles, unsafe terms, or missing backup fields.
   - For large batches, sample-check low-confidence and high-impact titles before writeback.

8. Apply changes.
   - For App threads, call `set_thread_title` for manifest items whose action is `rename`.
   - For local database/file writes, write only after backup and validation; prefer official App tools when available.
   - Never rename a thread that is actively running unless the tool explicitly supports background title changes and the item is not being handed off or archived.

9. Verify and report.
   - Re-list or re-read a representative sample after applying.
   - Report scanned, renamed, skipped, duplicate-numbered, and manual-review counts.
   - Save the final manifest and backup paths.

## Manifest Shape

Use this JSON shape for tool interchange:

```json
{
  "schema_version": "rename-codex-sessions/v1",
  "run_id": "session-renaming-YYYYMMDDTHHMMSSZ",
  "source": "codex-app-threads",
  "created_at": "YYYY-MM-DDTHH:MM:SSZ",
  "items": [
    {
      "id": "thread-or-session-id",
      "source": "codex-app-thread",
      "host_id": "optional-host",
      "session_path": null,
      "old_title": "continue",
      "candidate_title": "Session Naming Rescan",
      "final_title": "Session Naming Rescan 2",
      "reason": "Rescanned unnamed sessions and numbered repeated responsibilities.",
      "confidence": "high",
      "action": "rename"
    }
  ],
  "summary": {
    "scanned": 1,
    "renamed": 1,
    "skipped": 0,
    "manual_review": 0,
    "duplicates_numbered": 0
  }
}
```

## Safety Rules

- Do not put PHI, secrets, auth tokens, full environment values, raw prompts, model responses, stack traces, or long shell output in titles.
- Prefer stable work intent over transient command text.
- Treat direct SQLite/database title updates as higher risk than App tool title updates.
- Keep all manifests and backups local to the active project or an explicit output directory.
- If a title cannot be inferred with confidence, mark `manual-review` instead of inventing one.

## Revert

To revert, use the backup manifest to apply `old_title` back to each item through the same write surface used for apply. Validate the backup before reverting and report any items that no longer exist.
