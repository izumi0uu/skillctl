---
name: thrive-therapy-session-diagnostics
description: Diagnose Thrive Therapy treatment sessions with incorrect treatment_session_iep_goals records, affected students/providers, and related audio/S3 retention or corruption issues. Use for AWS-Thrive clinical production or exported CSV investigations involving wrong IEP goals, treatment_sessions.audio_id/group_session_audio_id, audios.files JSON, 30-day raw audio retention/Glacier, or 0-byte/blob compatibility audio files.
metadata:
  short-description: Diagnose wrong IEP-goal treatment sessions and audio/S3 retention issues
---

# Thrive Therapy Session Diagnostics

Use this skill when investigating Thrive Therapy clinical data where a treatment session has an IEP goal associated with the wrong student, and where audio evidence may need to be checked in S3 for 30-day retention/Glacier state or corruption.

This is a business-diagnostic skill for the AWS-Thrive clinical app. It combines:

- Treatment session to student/provider attribution.
- `treatment_session_iep_goals` correctness checks.
- Treatment session status and drafted state review.
- `audios.files` JSON expansion to locate physical S3 audio keys.
- S3 `head-object` review for age, `StorageClass`, existence, and object size.
- Interpretation of no-key, group session/shared audio, Glacier, and 0-byte compatibility cases.

## Safety Boundary

Production work is read-only by default.

Allowed without additional approval:

- `SELECT` queries.
- Local CSV/text exports.
- `aws s3api head-object`.
- Reading SSM parameters and Secrets Manager values needed to connect.
- Inspecting local code and local generated CSVs.

Not allowed unless the user explicitly authorizes a write/remediation step:

- `UPDATE`, `DELETE`, `INSERT`, DDL, migrations, or DB write queries.
- `aws s3api restore-object`, `copy-object`, `put-object`, `delete-object`, object tagging, or lifecycle changes.
- Marking audio file items as deleted in `audios.files`.
- Changing treatment-session IEP goal records.

When connecting to prod, force read-only:

```bash
PGOPTIONS='-c default_transaction_read_only=on'
```

If the user says only "query", "confirm", "analyze", "diagnose", or similar, do not write to prod.

## Prod Environment Notes

Do not use local/felix `.env` bucket values for prod investigations.

Known prod references:

```text
AWS_PROFILE=thrive
AWS_REGION=us-west-2
DB tunnel host=127.0.0.1
DB tunnel port=25433
DB name containing clinical prod data=thrive-prod
Prod DB secret SSM path=/thrive/prod/database/secret/arn
Prod audio bucket SSM path=/thrive/prod/s3/audio_bucket/name
Prod audio bucket=thriveback-prod-audiobucket96beecba-hejju9f4fmui
```

Important database boundary:

- The prod DB secret may report default `dbname=thrive`.
- The clinical production data is in database `thrive-prod`.
- Always double-check with row counts before trusting a database connection.

Quick prod sanity query:

```sql
SELECT current_database(), current_setting('transaction_read_only');

SELECT relname, n_live_tup
FROM pg_stat_user_tables
WHERE relname IN (
  'treatment_sessions',
  'treatment_session_iep_goals',
  'iep_goals',
  'audios',
  'patient_providers',
  'students'
)
ORDER BY relname;
```

## Data Model

Current production schema for this diagnosis:

```text
treatment_sessions.patient_provider_id -> patient_providers.id
patient_providers.patient_profile_id -> patient_profiles.id
patient_profiles.student_id -> students.id
treatment_sessions.audio_id -> audios.id
treatment_sessions.group_session_audio_id -> audios.id
treatment_session_iep_goals.treatment_session_id -> treatment_sessions.id
treatment_session_iep_goals.iep_goal_id -> iep_goals.id
iep_goals.patient_profile_id -> patient_profiles.id
audios.files -> JSON array of audio file items
audio file item -> file_key
```

The core correctness check:

```sql
iep_goals.patient_profile_id <> patient_providers.patient_profile_id
```

This means the IEP goal attached to the treatment session belongs to a different student profile than the treatment session's current student.

Older historical schema note:

- Some old/non-prod databases may have `iep_goals.patient_provider_id` and `audios.paths`.
- If a query fails with missing `iep_goals.patient_profile_id` or `audios.files`, inspect `information_schema.columns` and adapt. Do not assume that old schema is the current clinical prod data.

## Diagnostic Workflow

### 1. Confirm the Wrong IEP Treatment Sessions

Start by identifying affected sessions with student, provider, status, and draft state.

```sql
SELECT
  ts.id AS treatment_session_id,
  ts.start_time,
  ts.end_time,
  ts.status AS treatment_session_status,
  ts.is_drafted AS treatment_session_is_drafted,

  pp.id AS patient_provider_id,
  pp.patient_profile_id AS session_patient_profile_id,
  ss.id AS affected_student_id,
  concat_ws(' ', ss.first_name, ss.last_name) AS affected_student_name,

  p.id AS provider_id,
  concat_ws(' ', prof.first_name, prof.last_name) AS provider_name,
  p.npi AS provider_npi,
  p.provider_type,

  count(DISTINCT tsig.id) AS wrong_treatment_session_iep_goal_count,
  count(DISTINCT ig.id) AS wrong_iep_goal_count
FROM treatment_sessions ts
JOIN patient_providers pp
  ON pp.id = ts.patient_provider_id
JOIN patient_profiles spp
  ON spp.id = pp.patient_profile_id
JOIN students ss
  ON ss.id = spp.student_id
JOIN providers p
  ON p.id = pp.provider_id
JOIN profiles prof
  ON prof.id = p.profile_id
JOIN treatment_session_iep_goals tsig
  ON tsig.treatment_session_id = ts.id
JOIN iep_goals ig
  ON ig.id = tsig.iep_goal_id
WHERE ig.patient_profile_id <> pp.patient_profile_id
GROUP BY
  ts.id, ts.start_time, ts.end_time, ts.status, ts.is_drafted,
  pp.id, pp.patient_profile_id, ss.id, ss.first_name, ss.last_name,
  p.id, prof.first_name, prof.last_name, p.npi, p.provider_type
ORDER BY ts.start_time DESC;
```

For one provider, add:

```sql
AND p.id = '<provider uuid>'::uuid
```

### 2. Expand Audio References

A treatment session may have:

- `audio_id`: its ordinary/session audio.
- `group_session_audio_id`: shared group-session audio.

Build `audio_refs` from both IDs. Keep `audio_source` in outputs.

Important business nuance:

- Group/shared audio does not always show up as `audio_source='group_session_audio'`.
- Group logic can reassign member sessions' `audio_id` to the same audio record.
- Therefore, fewer unique S3 keys than affected treatment sessions is expected.
- Deduplicate S3 work by physical `file_key`, not by `treatment_session_id`.

### 3. Expand `audios.files`

`audios.files` is a JSON text array. An audio row can exist without any physical S3 key.

Interpretation:

```text
audio row exists, files NULL/[]:
  audio shell/place-holder exists, but no uploaded/attached file was recorded in DB.

file item exists and file_key present:
  physical S3 object can be checked with head-object.

file item exists and is_deleted=true:
  business-deleted file, do not treat as active audio evidence.
```

Suggested action categories:

```text
NO_AUDIO_ID:
  No audio reference on treatment session.

AUDIO_ROW_MISSING:
  treatment_sessions.audio_id points to a missing audios row.

NO_AUDIO_FILE_IN_DB:
  audio row exists but no active audios.files[].file_key exists.
  This is not an S3-missing case; DB has no key to follow.

ALREADY_MARKED_DELETED:
  file item is business-deleted.

S3_HEAD_AND_EXTEND_RETENTION:
  DB has a key and audio.updated_at is older than 30 days.
  Check S3 StorageClass/existence/size. In prod, raw audio lifecycle moves to Glacier after 30 days.

S3_HEAD_CHECK_OBJECT_SIZE:
  DB has a key and audio is recent enough to check for object size/compatibility.
```

### 4. Diagnose `NO_AUDIO_FILE_IN_DB`

Do not assume these are missing S3 files.

Business interpretation:

- Treatment session creation creates an `audios` placeholder.
- Recurring treatment-session creation creates many future session/audio shells at once.
- `audios.files` is only populated after the provider records/uploads audio and the backend `/audios/{id}/files` call succeeds.
- If `upload_status='pending'` and `transcribe_status='not_started'`, the audio workflow never reached uploaded/transcription.

Useful query:

```sql
WITH wrong_sessions AS (
  SELECT DISTINCT ts.id AS treatment_session_id
  FROM treatment_sessions ts
  JOIN patient_providers pp ON pp.id = ts.patient_provider_id
  JOIN treatment_session_iep_goals tsig ON tsig.treatment_session_id = ts.id
  JOIN iep_goals ig ON ig.id = tsig.iep_goal_id
  WHERE ig.patient_profile_id <> pp.patient_profile_id
),
audio_refs AS (
  SELECT
    ts.id AS treatment_session_id,
    ts.status,
    ts.is_drafted,
    ts.recurring_schedule_id,
    ts.audio_id AS audio_id,
    'session_audio' AS audio_source
  FROM wrong_sessions ws
  JOIN treatment_sessions ts ON ts.id = ws.treatment_session_id
  WHERE ts.audio_id IS NOT NULL

  UNION ALL

  SELECT
    ts.id,
    ts.status,
    ts.is_drafted,
    ts.recurring_schedule_id,
    ts.group_session_audio_id,
    'group_session_audio'
  FROM wrong_sessions ws
  JOIN treatment_sessions ts ON ts.id = ws.treatment_session_id
  WHERE ts.group_session_audio_id IS NOT NULL
    AND ts.group_session_audio_id <> ts.audio_id
),
no_file AS (
  SELECT ar.*, a.files, a.upload_status, a.transcribe_status
  FROM audio_refs ar
  JOIN audios a ON a.id = ar.audio_id
  WHERE NOT EXISTS (
    SELECT 1
    FROM jsonb_array_elements(
      CASE
        WHEN a.files IS NULL OR btrim(a.files) = '' THEN '[]'::jsonb
        ELSE a.files::jsonb
      END
    ) f(item)
    WHERE coalesce((item ->> 'is_deleted')::boolean, false) = false
  )
)
SELECT
  count(*) AS no_file_refs,
  count(DISTINCT treatment_session_id) AS no_file_unique_sessions,
  count(*) FILTER (WHERE files IS NULL) AS files_null,
  count(*) FILTER (WHERE files IS NOT NULL AND files::jsonb = '[]'::jsonb) AS files_empty_array,
  count(*) FILTER (WHERE files IS NOT NULL AND files::jsonb <> '[]'::jsonb) AS files_only_deleted_or_invalid,
  count(DISTINCT treatment_session_id) FILTER (WHERE recurring_schedule_id IS NOT NULL) AS with_recurring_schedule,
  count(DISTINCT treatment_session_id) FILTER (WHERE recurring_schedule_id IS NULL) AS without_recurring_schedule
FROM no_file;
```

If most/all no-key sessions have `recurring_schedule_id`, report that they are likely recurring schedule audio shells, not S3 retention cases.

### 5. Generate S3 Key List

Only active `file_key` values can be checked in S3.

Deduplicate keys before calling S3:

```sql
SELECT DISTINCT file_item ->> 'file_key' AS audio_s3_key
FROM audio_files
WHERE file_item ->> 'file_key' IS NOT NULL
  AND coalesce((file_item ->> 'is_deleted')::boolean, false) = false;
```

Business explanation:

- A report may contain many treatment sessions but far fewer physical keys.
- Reasons:
  - many sessions have no DB file key,
  - several treatment sessions can share one audio row,
  - one audio row can contain multiple file chunks/items,
  - group session behavior can share/reassign audio.

### 6. S3 Read-Only Check

Resolve prod bucket from SSM:

```bash
BUCKET=$(AWS_PROFILE=thrive AWS_REGION=us-west-2 aws ssm get-parameter \
  --name /thrive/prod/s3/audio_bucket/name \
  --query Parameter.Value \
  --output text)
```

For each unique key:

```bash
AWS_PROFILE=thrive AWS_REGION=us-west-2 aws s3api head-object \
  --bucket "$BUCKET" \
  --key "$AUDIO_S3_KEY" \
  --query '{ContentLength:ContentLength,StorageClass:StorageClass,LastModified:LastModified,Restore:Restore,ContentType:ContentType,ETag:ETag}' \
  --output json
```

Interpretation:

```text
NoSuchKey / exists=false:
  DB references an object that S3 cannot find.

ContentLength = 0:
  Corrupted/empty audio object, often compatible with blob/file-size-zero issue.

StorageClass = GLACIER:
  Object exists but is archived by lifecycle. It must be restored before download/transcription.

StorageClass missing or STANDARD and ContentLength > 0:
  Object exists and is not archived. If transcription failed, investigate file format/codec/processing compatibility.
```

### 7. 30-Day Retention / Glacier

Infrastructure rule:

- `raw/` audio transitions to Glacier after 30 days.
- It is not deleted solely because it is older than 30 days.

Business wording:

```text
"Older than the 30-day retention period" means the raw audio may no longer be immediately readable because lifecycle transitions it to Glacier.
```

To make it readable, a remediation step must be chosen and explicitly approved:

- Restore object temporarily via `restore-object`.
- Restore then copy to a retained/non-raw prefix.
- Restore then copy over same key to reset lifecycle age.
- Change lifecycle policy/tag strategy for future cases.

Do not perform these operations in this skill unless the user explicitly authorizes writes.

### 8. Corrupted / 0-Byte Audio

If S3 `head-object` confirms `ContentLength=0`, classify it as a corrupted/empty file candidate.

Business remediation after approval:

- Mark that file item in `audios.files` with `is_deleted=true`.
- Do not delete the `audios` row unless product/business asks.
- Do not remove the treatment session.

The business field is `is_deleted`, not `is_delete`.

Template for a post-approval DB update:

```sql
WITH corrupt_files(file_key) AS (
  VALUES
    ('raw/<tenant_id>/<object>.mp4')
),
updated_audio_files AS (
  SELECT
    a.id AS audio_id,
    jsonb_agg(
      CASE
        WHEN cf.file_key IS NOT NULL
          THEN elem.file_item || jsonb_build_object('is_deleted', true)
        ELSE elem.file_item
      END
      ORDER BY elem.ord
    ) AS new_files
  FROM audios a
  CROSS JOIN LATERAL jsonb_array_elements(a.files::jsonb) WITH ORDINALITY AS elem(file_item, ord)
  LEFT JOIN corrupt_files cf ON cf.file_key = elem.file_item ->> 'file_key'
  WHERE cf.file_key IS NOT NULL
  GROUP BY a.id
)
UPDATE audios a
SET
  files = updated_audio_files.new_files::text,
  updated_at = now()
FROM updated_audio_files
WHERE a.id = updated_audio_files.audio_id
RETURNING a.id, a.files;
```

Only use this after explicit write approval.

## Reporting Guidance

When summarizing a diagnosis, include:

- Number of expanded rows.
- Number of unique treatment sessions.
- Number of affected students.
- Number of affected providers.
- Number of wrong IEP goal links.
- Number of unique S3 keys.
- Count by suggested action.
- Count by treatment session status.
- Count by `is_drafted`.
- Provider distribution.
- S3 result counts:
  - exists/missing,
  - Glacier/Standard,
  - zero-byte count,
  - missing/error count.
- Explicit distinction between:
  - DB no-key sessions,
  - S3 archived objects,
  - S3 0-byte corrupted objects,
  - shared/group audio reducing unique key count.

Use business language:

```text
NO_AUDIO_FILE_IN_DB does not mean the S3 file is missing.
It means the DB has no active file_key to follow.
```

```text
The unit of S3 remediation is the physical S3 key, not the treatment session.
```

```text
Group sessions/shared audio can make multiple treatment sessions point to the same audio_id or file_key.
```

## Known Case Pattern From April 27, 2026 Investigation

In the investigated prod case:

- `84` unique affected treatment sessions.
- `174` wrong treatment-session IEP-goal links.
- `64` unique sessions had no active DB `file_key`.
- Those no-key sessions were all tied to recurring schedules.
- `19` unique S3 keys existed for the sessions that had DB file keys.
- `19/19` S3 keys existed in prod audio bucket.
- `18` were in Glacier.
- `1` was in Standard.
- `0` were 0-byte.

This historical pattern is not a universal rule, but it is a useful comparison point.
