---
name: thread-memory-capsule
description: Distill oversized Codex threads, session JSONL files, or long agent transcripts into compact continuation memory capsules with claim IDs, provenance anchors, safety exclusions, and current-repo truth boundaries. Use when a session is too large to continue, fork, paste, or load directly, and the user needs reusable context for future work across projects.
---

# Thread Memory Capsule

Use this skill to preserve the useful working memory of a large agent thread without copying raw transcript payloads into future prompts. The output is a small set of files that a future agent can inspect quickly and verify mechanically.

## Resource Loading

- Read `references/capsule-schema.md` before writing a manifest.
- Use `scripts/validate_capsule.py` after creating or editing a capsule manifest and markdown files.
- Use `scripts/safety_scan.py` before reporting completion.

## Outputs

Create these files under `.omx/context/` by default, or under the user's requested output directory:

- `<topic>-memory-<short-id>.json`: machine-checkable manifest of claims.
- `<topic>-continuation-<short-id>.md`: short handoff brief for the next agent.
- `<topic>-audit-<short-id>.md`: fuller ADR, implementation, verification, and risk map.

For very small tasks, the continuation and audit files may be combined only if the manifest still exists.

## Workflow

1. Identify the source.
   - Prefer an explicit JSONL transcript path or thread ID.
   - Record source path, source thread ID, line count, byte size, extraction timestamp, current repo path, branch, and commit when available.
   - Do not open a huge source thread in the UI if the goal is to avoid loading it.

2. Create a context snapshot.
   - Record task statement, desired outcome, constraints, known facts, unknowns, and likely repo touchpoints.
   - Keep this separate from the capsule so future agents can distinguish extraction workflow facts from source-thread facts.

3. Extract claims, not raw history.
   - Convert each durable fact into a claim ID such as `TC-001`.
   - Attach transcript line refs, turn IDs, repo paths, and path status to each claim.
   - Use status values from `references/capsule-schema.md`.
   - Keep direct quotes short and rare; paraphrase by default.

4. Separate fact types.
   - Source-thread evidence: facts supported by transcript lines.
   - Extraction-time facts: path, file size, current checkout, generated artifact paths.
   - Current-checkout truth: files that exist or are absent now.
   - Historical-branch evidence: implementation or verification that happened on another branch or commit.
   - Policy decisions: no-fork/no-raw-history constraints from the extraction workflow or PRD, not from unrelated transcript metadata.

5. Write the manifest first.
   - Every meaningful continuation/audit statement should cite one or more claim IDs.
   - Do not let a claim overstate what its cited source line proves.
   - If a line only proves session metadata, do not use it to prove workflow policy.

6. Write the continuation brief.
   - Keep it short enough for a future prompt.
   - Include one-sentence state, core decisions, implementation map, verification memory, risks, and next actions.

7. Write the audit memory.
   - Preserve ADRs, risk decisions, migration/data warnings, verification boundaries, and source lookup anchors.
   - Clearly label historical evidence versus current checkout truth.

8. Validate and scan.
   - Run `validate_capsule.py --manifest <json> --markdown <brief.md> --markdown <audit.md> --source <source.jsonl>`.
   - Run `safety_scan.py <capsule-files...>`.
   - Re-check source transcript line count and byte size if the manifest records them.

9. Report completion.
   - List artifact paths.
   - Summarize claim count, validation result, safety scan result, and source integrity result.
   - State any truth boundary that future agents must respect.

## Safety Rules

- Never copy raw clinical data, credentials, API tokens, private keys, raw prompts, raw model responses, base64 images, long command output, or stack traces into the capsule.
- Do not treat current repo inspection as source-thread provenance.
- Do not treat historical implementation evidence as current checkout truth.
- If evidence is missing or weak, mark the claim as `needs-reinspection` or omit it.
- If the source transcript is too large to parse fully, sample line anchors deliberately and say what was not inspected.

## Naming

Use a topic slug plus a short source ID:

```text
prompt-versioning-memory-019e974b.json
prompt-versioning-continuation-019e974b.md
prompt-versioning-audit-019e974b.md
```

Prefer stable topic names over generic names like `summary` or `memory`.
