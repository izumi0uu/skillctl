---
name: skillctl-control-plane
description: Use when the task is to operate, extend, audit, or repair the skillctl repository or its managed multi-agent skills estate. This skill covers discovery, adoption, provenance, taxonomy, sync, health checks, repair, prune, and shared transport behavior across Claude Code, Codex, Pi Agent, Hermes, and OpenCode.
---

# Skillctl Control Plane

## Overview

Use this skill for work inside the `skillctl` repository and for machine-level skill management that should flow through `skillctl` as the canonical control plane.

`skillctl` is not just a folder of skills. It is a Git-tracked control plane with:

- canonical skill content under `skills/`
- catalog metadata in `skillctl.catalog.json`
- local machine state in `.skillctl-local/`
- adapter-aware sync targets for 5 agents
- provenance and taxonomy generation
- README source and taxonomy sections that are owned by `skillctl`
- an embedded `vercel-skills/` submodule used as the default upstream transport

In normal `skills-cli` mode, the transport path is:

```text
skillctl canonical source
  -> embedded vercel-skills CLI
  -> ~/.agents/skills
  -> per-agent install directories
```

Treat that shared layer as part of the design, not as accidental temporary output.

## Use This Skill When

- the user wants to add or import a new skill into `skillctl`
- the user wants to classify or reclassify managed skills
- the user wants to track provenance for an external skill
- the user wants to sync managed skills to agent directories
- the user wants to run a health check or repair drift
- the user wants to verify upstream references
- the user wants to understand what `skillctl` manages and where
- the user wants to prune only `skillctl`-managed installs
- the user wants to work on the `skillctl` repository itself

## Repo Map

- `packages/core`
  - catalog, schema, adapters, transport, doctor, repair, attribution, taxonomy
- `packages/cli`
  - command entrypoint and CLI wiring
- `apps/electron`
  - future UI shell; should reuse core logic instead of reimplementing it
- `skills/`
  - canonical managed skill sources committed to Git
- `manifests/`
  - schemas and manifest docs
- `vercel-skills/`
  - embedded upstream CLI submodule
- `skillctl.config.json`
  - local control-plane config
- `skillctl.catalog.json`
  - managed catalog

## Core Commands

- `skillctl init`
  - initialize config, catalog, and schemas
- `skillctl discover`
  - scan configured roots and persist managed catalog state
- `skillctl adopt --source <path> ...`
  - import an existing skill into canonical `skills/` with provenance
- `skillctl status`
  - summarize adapters, catalog counts, taxonomy, and sources
- `skillctl diff`
  - compare current catalog to on-disk discovery
- `skillctl sources --json`
  - print the provenance registry
- `skillctl taxonomy --json`
  - print the grouped category tree
- `skillctl verify-sources --json`
  - verify upstream source metadata
- `skillctl sync`
  - distribute managed public skills to agent install locations
- `pnpm health-suite`
  - canonical end-to-end health suite for local runs and CI
- `skillctl doctor --json`
  - detect drift, missing dirs, unreadable skills, malformed attribution, README drift, and transport readiness
- `skillctl repair --json`
  - repair managed state by re-syncing and rechecking
- `skillctl prune`
  - remove only skills previously marked as managed by `skillctl`
- `skillctl bootstrap-upstream`
  - install and build the embedded `vercel-skills/` transport if needed

## Decision Rules

### 1. Adding A New Self-Authored Skill

- Create the canonical directory under `skills/<category>/<skill-id>/`.
- Add `SKILL.md` and any portable supporting files.
- Prefer standard portable skill structure first.
- Run:
  - `skillctl discover`
  - `skillctl doctor --json`
  - `skillctl sync`

Set provenance as local:

- `origin_kind = local-authored`
- no fake upstream metadata

### 2. Importing An Existing External Skill

If the skill came from another repo or was previously installed by another agent, do not just copy it in and call it local. Use `adopt`.

Preferred command shape:

```bash
skillctl adopt \
  --source <existing-skill-dir> \
  --into <category/path> \
  --from-repo <owner/repo-or-url> \
  --skill-path <path-within-upstream> \
  --ref <commit-tag-or-branch> \
  --source-type <github|git|local> \
  --source-url <url> \
  --origin-kind <imported-upstream|derived-from-upstream>
```

Use:

- `imported-upstream` when the canonical copy is intended to match upstream closely
- `derived-from-upstream` when local changes are already part of the managed copy
- `--local-modifications` when the managed copy intentionally diverges

After adoption:

- run `skillctl sources --json`
- run `skillctl doctor --json`
- run `skillctl sync`

### 3. Reclassifying Or Reorganizing Skills

- Move the canonical directory under `skills/` to the correct category path.
- Keep the `skill_id` stable unless there is a real rename decision.
- Re-run:
  - `skillctl discover`
  - `skillctl taxonomy --json`
  - `skillctl doctor --json`
  - `skillctl sync`

Do not edit generated taxonomy or README registry sections by hand.

### 4. Auditing Managed State

Use:

- `skillctl status`
- `skillctl sources --json`
- `skillctl taxonomy --json`
- `skillctl doctor --json`
- `skillctl verify-sources --json`

This is the right path when the user asks:

- what skills exist
- where they came from
- what category they belong to
- whether installs are healthy
- whether upstream references are still valid

### 5. Repairing Drift

When health is degraded:

1. Run `skillctl doctor --json`.
2. Distinguish:
   - transport readiness problems
   - missing directories
   - malformed attribution
   - README drift
   - managed install drift
   - provenance gaps
3. If the issue is repairable, run `skillctl repair --json`.
4. Re-run `skillctl doctor --json`.
5. Only claim success after the second doctor pass.

### 6. Pruning Managed Installs

Use `skillctl prune` only when the goal is to remove installs that were previously managed by `skillctl`.

Guardrails:

- unmanaged skills must be preserved
- project-local skills that are intentionally out of scope must not be removed
- do not manually delete arbitrary agent skill trees and call it a prune

## Provenance Rules

`skillctl` treats provenance as first-class metadata.

For any externally sourced skill, record:

- `origin_kind`
- `upstream.repo`
- `upstream.ref`
- `upstream.skillPath`
- `upstream.sourceType`
- `upstream.sourceUrl`
- `upstream.imported_at`
- `upstream.last_verified_ref`
- `upstream.local_modifications`

The attribution footer in each managed `SKILL.md` and the `Managed Skill Sources` section in `README.md` are owned by `skillctl`.

Do not manually edit those owned sections unless you are explicitly changing the renderer implementation.

## Category Rules

Current first-class categories are:

- `agent-infra`
- `knowledge-and-research`
- `frontend-and-design`
- `deployment-and-platform`
- `productivity-and-artifacts`
- `domain-aws-thrive`
- `system-and-demo`

Prefer categorizing by primary use, not by source repo.

If a skill feels cross-cutting, choose the category that best matches the user-facing job it performs.

## Transport And Adapter Rules

- Default transport mode is `skills-cli`.
- The embedded upstream under `vercel-skills/` is the preferred transport executor when bootstrapped.
- In this mode, `~/.agents/skills` is expected shared state.
- Per-agent install directories are mirror targets, not canonical sources.
- `skillctl` is the canonical manager; direct edits inside agent install directories should be treated as drift unless explicitly unmanaged.
- `targets` in the catalog describe intended distribution, but final sync still applies portability policy.
- Default portability gate is:
  - `portable` -> distribute to declared `targets`
  - `codex-enhanced` -> distribute to declared `targets`
  - `claude-only` -> distribute only to `claude-code` unless explicitly allowed in `distribution.portability_allow_targets`
  - `needs-review` -> do not distribute
- Portability overrides are per-skill catalog metadata, not ad hoc agent-directory edits.

Do not assume agent directories themselves are the source of truth.

## Safety Rules

- Do not claim a skill is managed unless it exists in `skillctl.catalog.json`.
- Do not treat imported upstream work as `local-authored` just to avoid filling provenance.
- Do not hand-edit generated attribution blocks or generated README sections.
- Do not prune unmanaged skills.
- Do not rewrite unrelated user modifications in the repo.
- Do not run `sync` and `doctor` in parallel; finish sync first, then validate.
- Do not claim a repair worked until `doctor --json` confirms the resulting state.
- Do not discard `~/.agents/skills` casually while transport mode is still `skills-cli`.

## Recommended Workflow

For most real requests, follow this order:

1. Inspect repo state.
   - check `git status --short`
   - read `skillctl.config.json`
   - read `skillctl.catalog.json` when provenance or targets matter
2. Choose the right control-plane action.
   - new local skill -> `discover`
   - existing external skill -> `adopt`
   - state audit -> `status` / `sources` / `taxonomy`
   - distribution -> `sync`
   - health -> `pnpm health-suite` first, then inspect `doctor --json` or `verify-sources --json` directly only if deeper debugging is needed
   - fix -> `repair`
3. Re-run health checks after any mutating operation.
4. Report:
   - what changed
   - what category and provenance were recorded
   - whether sync ran
   - whether doctor passed

## Example Requests

- `Use $skillctl-control-plane to import this skill into the repo and sync it everywhere.`
- `Audit the skillctl repository and tell me whether the managed installs are healthy.`
- `Adopt this third-party skill with its real upstream source and classify it correctly.`
- `Rebuild the managed agent copies from the canonical repo.`
- `Show me what skillctl manages, where each skill came from, and which categories are getting crowded.`

## Standard Health Flow

Prefer this command for a complete health pass:

```bash
pnpm health-suite
```

This is the standard ordered flow:

1. `discover`
2. `sync`
3. `doctor --json`
4. `verify-sources --json`

Use direct subcommands when the task is intentionally narrow, but do not invert this sequence for a full estate audit.

## Success Condition

The task is complete only when:

- the canonical repo content is correct
- catalog metadata is coherent
- provenance is explicit where needed
- generated attribution and README sections are in sync
- managed distribution has been updated when relevant
- a final `skillctl doctor --json` result supports the conclusion
