---
name: thrive-billing-claim-cleanup-diagnostics
description: Review AWS-Thrive billing claims created from non-billable treatment-session attendance before cleanup. Use when checking existing `billing_claims` status, Availity responses, payer responses, remittance/ERA records, and deciding whether a claim is a cleanup candidate or needs human review.
metadata:
  short-description: Re-check Thrive billing claim cleanup candidates and Availity/ERA state
---

# Thrive Billing Claim Cleanup Diagnostics

Use this skill when investigating AWS-Thrive clinical production data where `billing_claims` were created for treatment sessions that should not have been billable, especially sessions whose `attendance_status` is:

- `absent`
- `student_unavailable`
- `provider_unavailable`

The goal is to produce a cleanup decision aid, not to delete data automatically.

## Safety Boundary

Production work is read-only by default.

Allowed without additional approval:

- `SELECT` queries.
- Local CSV/text exports.
- Reading local code.
- Reading CloudWatch logs if the user provides log exports or asks for log query guidance.

Not allowed unless the user explicitly authorizes a write/remediation step:

- `UPDATE`, `DELETE`, `INSERT`, DDL, migrations, or DB write queries.
- Creating backup tables in production.
- Deleting `billing_claims`, `billing_claim_lines`, `audits`, S3 CMS-1500/837 files, or remittance rows.
- Changing `billing_claims.status`.
- Marking treatment sessions as drafted, not drafted, done, or in progress.

When connecting to prod, force read-only:

```bash
PGOPTIONS='-c default_transaction_read_only=on'
```

If the user says "check", "review", "analyze", "can I delete", "需要再看", or similar, do not write to prod.

## Read First

Read these files before answering repository-specific questions:

- `backend/clinical/app/constants/billing_claim.py`
- `backend/clinical/app/models/billing_claim.py`
- `backend/clinical/app/models/billing_claim_line.py`
- `backend/clinical/app/models/treatment_session.py`
- `backend/clinical/app/tasks/medicaid/billing_claim_processing.py`
- `backend/clinical/app/tasks/medicaid/edi_inbound_processing.py`
- `backend/clinical/app/services/billing_claim_service.py`

Read these when the question asks "why was this created":

- `backend/clinical/app/routes/treatment_session.py`
- `backend/clinical/app/services/treatment_session_service.py`
- `frontend/src/pages/TreatmentSessionDetailsV2/components/Header.tsx`
- `frontend/src/pages/TreatmentSessionDetailsV2/components/AutoSave.tsx`
- `frontend/src/pages/TreatmentSessionDetailsV2/hooks/useUpdateTreatmentSession.ts`
- `frontend/src/pages/TreatmentSessionDetailsV2/hooks/useTreatmentSessionStore.ts`

If available, combine this skill with `medicaid-ledger-expert` for EDI family semantics and claim lifecycle details.

## Incident Background To Remember

The historical incident pattern was:

1. Frontend treatment-session detail page autosave sent `attendance_status` updates.
2. Non-present attendance values such as `absent`, `student_unavailable`, and `provider_unavailable` were treated as completion-like states.
3. Backend service set the session to `done`.
4. Historical billing claim creation logic treated `done` as enough, or almost enough, to create a claim.
5. For older production periods, claim creation did not hard-gate on `attendance_status in ('fully_present', 'partially_present')`.
6. Some claims were later submitted via Celery/old Lambda flows and received Availity or payer response files.

Important time-boundary notes from the prior analysis:

- `is_drafted` validation was added later than many affected records.
- A current `treatment_sessions.is_drafted = false` value does not prove the claim was impossible historically.
- Some older sessions may have received claims through backfill-like scanning of old `done` sessions.
- `treatment_sessions.updated_at` is not always the claim creation timestamp.
- `accepted` in this repo does not mean paid. It means an inbound response parser treated the latest response as passed.

## Status Semantics For Cleanup

Use exact enum values from `app.constants.billing_claim.BillingClaimStatus`.

Treat these as lower-risk cleanup candidates if there is no later contradictory evidence:

- `need_review`: created internally but not submitted.
- `rejected_internal`: internally rejected/manual workflow state.
- `rejected_by_availity`: rejected by a non-DPT inbound response.
- `rejected_by_payer`: DPT failure/payer-side rejection in this implementation.

Treat these as hold or human-review states:

- `submitted`: outbound submission happened; response may still be pending.
- `accepted`: Availity/inbound response passed, but this is not payment.
- `remittance_received`: ERA/835 remittance has been posted or linked.
- `completed`: final/manual workflow state; do not clean without explicit business sign-off.

Escalate to human review if any of these are present, regardless of current status:

- `first_accepted_by_payer_at` or `second_accepted_by_payer_at` is not null.
- `response_file_path` or `response_at` exists and status is `accepted`.
- `remittance_received`, `completed`, or linked `remittance_lines` exist.
- `remittance_amount`, `remittance_status`, or `remittance_date` is populated.
- Claim has a second submission attempt.
- Claim has payer control numbers on the claim or claim lines.

## Standard Review Workflow

### 1. Normalize The Candidate Set

Start from one of:

- A CSV exported from Logs Insights or SQL containing `treatment_session_id` and `billing_claim_id`.
- A raw list of `billing_claim_id` values.
- A SQL predicate for affected sessions, such as non-billable attendance plus existing billing claim.

For ad hoc review, prefer a CTE with explicit IDs. Avoid temp tables in prod unless the user authorizes writes.

```sql
WITH candidates(treatment_session_id, billing_claim_id) AS (
  VALUES
    ('00000000-0000-0000-0000-000000000000'::uuid, '11111111-1111-1111-1111-111111111111'::uuid)
)
SELECT *
FROM candidates;
```

### 2. Re-check Current Claim State

Use this query shape to see whether cleanup is still reasonable.

```sql
WITH candidates(treatment_session_id, billing_claim_id) AS (
  VALUES
    -- Replace with candidate pairs.
    ('00000000-0000-0000-0000-000000000000'::uuid, '11111111-1111-1111-1111-111111111111'::uuid)
),
claim_review AS (
  SELECT
    c.treatment_session_id AS candidate_treatment_session_id,
    c.billing_claim_id AS candidate_billing_claim_id,
    ts.id AS treatment_session_id,
    ts.status AS treatment_session_status,
    ts.attendance_status,
    ts.is_drafted,
    ts.is_make_up,
    ts.start_time,
    ts.end_time,
    ts.updated_at AS treatment_session_updated_at,
    bc.id AS billing_claim_id,
    bc.status AS billing_claim_status,
    bc.source AS billing_claim_source,
    bc.reference_type,
    bc.reference_id,
    bc.created_at AS billing_claim_created_at,
    bc.updated_at AS billing_claim_updated_at,
    bc.submitted_at,
    bc.response_at,
    bc.response_file_path,
    bc.submitted_837p_file_path,
    bc.interchange_control_number,
    bc.transaction_control_number,
    bc.payer_control_number,
    bc.first_submitted_to_payer_at,
    bc.first_accepted_by_payer_at,
    bc.first_rejected_by_payer_at,
    bc.second_submitted_to_payer_at,
    bc.second_accepted_by_payer_at,
    bc.second_rejected_by_payer_at,
    bc.remittance_amount,
    bc.remittance_status,
    bc.remittance_date,
    count(distinct bcl.id) AS billing_claim_line_count,
    count(distinct rl.id) AS remittance_line_count,
    count(distinct rl.id) FILTER (WHERE rl.paid_cents <> 0) AS paid_remittance_line_count,
    count(distinct rl.id) FILTER (WHERE rl.adjustment_cents <> 0) AS adjusted_remittance_line_count
  FROM candidates c
  LEFT JOIN treatment_sessions ts
    ON ts.id = c.treatment_session_id
  LEFT JOIN billing_claims bc
    ON bc.id = c.billing_claim_id
       OR (
         bc.reference_type = 'treatment_session'
         AND bc.reference_id = c.treatment_session_id
       )
  LEFT JOIN billing_claim_lines bcl
    ON bcl.billing_claim_id = bc.id
  LEFT JOIN remittance_lines rl
    ON rl.billing_claim_id = bc.id
       OR rl.billing_claim_line_id = bcl.id
  GROUP BY
    c.treatment_session_id,
    c.billing_claim_id,
    ts.id,
    bc.id
)
SELECT
  *,
  CASE
    WHEN billing_claim_id IS NULL THEN 'already_missing_or_no_claim'
    WHEN billing_claim_status IN ('remittance_received', 'completed') THEN 'hold_remittance_or_completed'
    WHEN remittance_line_count > 0 THEN 'hold_has_remittance_lines'
    WHEN first_accepted_by_payer_at IS NOT NULL OR second_accepted_by_payer_at IS NOT NULL THEN 'hold_has_accepted_timestamp'
    WHEN billing_claim_status = 'accepted' THEN 'hold_accepted_by_inbound_response'
    WHEN billing_claim_status = 'submitted' THEN 'hold_submitted_pending_or_no_response'
    WHEN billing_claim_status IN ('rejected_by_availity', 'rejected_by_payer', 'rejected_internal', 'need_review') THEN 'cleanup_candidate_if_business_agrees'
    ELSE 'review_unknown_status'
  END AS cleanup_bucket
FROM claim_review
ORDER BY cleanup_bucket, treatment_session_updated_at, billing_claim_created_at;
```

### 3. Summarize Counts By Cleanup Bucket

```sql
WITH reviewed AS (
  -- Paste the claim_review SELECT from the previous query here.
  SELECT
    bc.id AS billing_claim_id,
    bc.status AS billing_claim_status,
    bc.first_accepted_by_payer_at,
    bc.second_accepted_by_payer_at,
    count(distinct rl.id) AS remittance_line_count
  FROM billing_claims bc
  LEFT JOIN billing_claim_lines bcl ON bcl.billing_claim_id = bc.id
  LEFT JOIN remittance_lines rl ON rl.billing_claim_id = bc.id OR rl.billing_claim_line_id = bcl.id
  WHERE false
  GROUP BY bc.id
),
bucketed AS (
  SELECT
    *,
    CASE
      WHEN billing_claim_status IN ('remittance_received', 'completed') THEN 'hold_remittance_or_completed'
      WHEN remittance_line_count > 0 THEN 'hold_has_remittance_lines'
      WHEN first_accepted_by_payer_at IS NOT NULL OR second_accepted_by_payer_at IS NOT NULL THEN 'hold_has_accepted_timestamp'
      WHEN billing_claim_status = 'accepted' THEN 'hold_accepted_by_inbound_response'
      WHEN billing_claim_status = 'submitted' THEN 'hold_submitted_pending_or_no_response'
      WHEN billing_claim_status IN ('rejected_by_availity', 'rejected_by_payer', 'rejected_internal', 'need_review') THEN 'cleanup_candidate_if_business_agrees'
      ELSE 'review_unknown_status'
    END AS cleanup_bucket
  FROM reviewed
)
SELECT cleanup_bucket, billing_claim_status, count(*) AS claim_count
FROM bucketed
GROUP BY cleanup_bucket, billing_claim_status
ORDER BY cleanup_bucket, billing_claim_status;
```

The second query has a deliberate `WHERE false` placeholder. Replace it with a real reviewed CTE or candidate predicate before using it.

### 4. Check Whether "Rejected" Later Became Accepted Or Remitted

Do not trust an old CSV status by itself. Always re-query current state.

```sql
SELECT
  bc.id,
  bc.status,
  bc.response_at,
  bc.response_file_path,
  bc.first_submitted_to_payer_at,
  bc.first_accepted_by_payer_at,
  bc.first_rejected_by_payer_at,
  bc.second_submitted_to_payer_at,
  bc.second_accepted_by_payer_at,
  bc.second_rejected_by_payer_at,
  count(distinct rl.id) AS remittance_line_count,
  sum(coalesce(rl.paid_cents, 0)) AS paid_cents,
  sum(coalesce(rl.adjustment_cents, 0)) AS adjustment_cents
FROM billing_claims bc
LEFT JOIN billing_claim_lines bcl ON bcl.billing_claim_id = bc.id
LEFT JOIN remittance_lines rl ON rl.billing_claim_id = bc.id OR rl.billing_claim_line_id = bcl.id
WHERE bc.id = ANY(:billing_claim_ids)
GROUP BY bc.id
ORDER BY bc.updated_at DESC;
```

If a claim was `rejected_by_availity` in an old export but now has `accepted`, accepted timestamps, or remittance lines, move it to "needs review".

## Decision Language

Use this language in conclusions:

- "Cleanup candidate" means the data looks safe to propose for deletion, not that deletion is automatically authorized.
- "Hold" means do not delete without billing/business sign-off.
- "Accepted" means accepted by an inbound response in this repo; it does not mean paid.
- "Remittance received" means ERA/835 data has been linked or posted; this is higher risk than simple Availity rejection.
- "Submitted with no response" is ambiguous; do not delete until the user confirms how to treat pending outbound submissions.

Suggested bucket wording:

- `cleanup_candidate_if_business_agrees`: current status is still rejected/internal/need_review and no remittance or accepted evidence exists.
- `hold_accepted_by_inbound_response`: current status is `accepted`; needs business review.
- `hold_submitted_pending_or_no_response`: outbound submission exists; response may be missing or pending.
- `hold_has_remittance_lines`: ERA/835 linkage exists; do not delete casually.
- `hold_remittance_or_completed`: later workflow state; requires explicit sign-off.
- `already_missing_or_no_claim`: claim may already have been cleaned, or the candidate pair is wrong.

## Report Format

When the user asks for an analysis report, include:

1. Candidate source and row count.
2. Current status counts.
3. Cleanup bucket counts.
4. A table of hold items with reasons.
5. A table of cleanup candidates with the exact evidence fields.
6. Any mismatches:
   - candidate `billing_claim_id` does not match `treatment_sessions.id`
   - claim `reference_id` differs from candidate treatment session
   - missing claim
   - non-billable attendance changed to `fully_present` or `partially_present`
7. Recommended next action, still read-only unless the user authorizes remediation.

## Guardrails

- Do not flatten Availity acceptance, payer adjudication, and ERA payment into one concept.
- Do not say `accepted` means paid.
- Do not delete claims with `accepted`, `remittance_received`, `completed`, remittance lines, or accepted timestamps without explicit business sign-off.
- Do not assume a row from an old export still has the same current status.
- Do not assume `treatment_sessions.updated_at` equals `billing_claims.created_at`.
- Do not use UI terms such as "archived page" as proof that the backend did not receive an autosave request.
- Do not treat `is_drafted=false` as proof that historical claim creation was impossible.
- Prefer concrete IDs, timestamps, statuses, response file paths, and SQL evidence over narrative guesses.
