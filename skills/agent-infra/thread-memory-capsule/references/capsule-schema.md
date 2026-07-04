# Capsule Schema

## Manifest

Use JSON with these top-level fields:

```json
{
  "schema_version": "thread-memory-capsule/v1",
  "source_thread_id": "optional-thread-id",
  "source_transcript_path": "/absolute/path/to/source.jsonl",
  "source_transcript_size_bytes": 0,
  "source_transcript_line_count": 0,
  "source_branch": "optional-branch",
  "source_commit": "optional-commit",
  "current_checkout": "branch@commit",
  "extraction_timestamp": "YYYY-MM-DDTHH:MM:SSZ",
  "outputs": [],
  "safety_exclusions": [],
  "claims": []
}
```

## Claim

Each claim should contain:

```json
{
  "claim_id": "TC-001",
  "claim": "Concise durable fact.",
  "status": "source-supported",
  "source_thread_id": "optional-thread-id",
  "source_transcript_path": "/absolute/path/to/source.jsonl",
  "transcript_line_refs": ["L12", "L20-L24"],
  "turn_ids": [],
  "repo_paths": [],
  "repo_path_status": "not-applicable",
  "repo_path_statuses": {},
  "notes": "Boundary or caveat."
}
```

## Status Values

- `source-supported`: supported by cited transcript lines.
- `extraction-time-fact`: observed while creating the capsule.
- `current-checkout-state`: verified in the current working tree.
- `historical-branch-state`: true only for a cited historical branch or commit.
- `decision`: user/team/product decision captured in the source.
- `risk`: risk or warning captured from evidence.
- `verified`: verification result from cited evidence.
- `environment-gap`: failed or skipped verification due to local environment constraints.
- `needs-reinspection`: useful but not strong enough to rely on without checking again.

## Repo Path Status Values

- `exists-current-checkout`
- `missing-current-checkout`
- `historical-only`
- `not-applicable`

## Validation Expectations

- Claim IDs are unique and stable.
- Markdown files only cite known claim IDs.
- All important claims appear in at least one markdown file.
- Transcript line refs are in range when the source file is available.
- Turn IDs appear near cited line refs when possible.
- Source line count and byte size match the manifest when recorded.
- Safety scan finds no forbidden raw payloads or secrets.
