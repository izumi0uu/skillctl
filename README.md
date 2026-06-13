# skillctl

Portable skills control plane for Claude Code, Codex, Pi Agent, Hermes, and OpenCode.

`skillctl` treats a Git-tracked catalog as the source of truth for public-safe local skills, then delegates install/sync transport to the upstream `vercel-labs/skills` CLI through an embedded git submodule by default while keeping local ownership, health checks, and repair policy.

It is intentionally a control-plane wrapper around `vercel-labs/skills`, not a fork of `vercel-labs/agent-skills`. Skill content repositories remain upstream sources; `skillctl` owns policy, cataloging, health checks, and safe multi-agent mirroring.

## What It Does

- Tracks public-safe skills in Git under `skills/`
- Records managed metadata in `skillctl.catalog.json`
- Keeps machine-local state in `.skillctl-local/`
- Vendors `vercel-labs/skills` as a git submodule under `vendor/vercel-skills`
- Uses that embedded upstream as the default install and sync transport
- Syncs managed skills into 5 built-in adapters:
  - `claude-code`
  - `codex`
  - `pi`
  - `hermes`
  - `opencode`
- Detects drift, missing directories, and stale managed indexes with `doctor`
- Repairs managed installs with `repair`

## Workspace Layout

```text
packages/core      # Catalog, schema, adapters, doctor/repair engine, transport integration
packages/cli       # CLI entrypoint and repo-root resolution
apps/electron      # Future macOS shell; no duplicate core logic
skills/            # Public-safe managed skills committed to Git
manifests/         # Schemas and tracked metadata
vendor/vercel-skills # Embedded upstream skills CLI submodule
```

## Quick Start

```bash
git clone --recurse-submodules git@github.com:izumi0uu/skillctl.git
cd skillctl
pnpm install
pnpm build
pnpm bootstrap-upstream
pnpm --filter skillctl-cli exec tsx src/index.ts init
pnpm --filter skillctl-cli exec tsx src/index.ts discover
pnpm --filter skillctl-cli exec tsx src/index.ts sync
pnpm --filter skillctl-cli exec tsx src/index.ts doctor --json
```

Or after build:

```bash
node packages/cli/dist/index.js status
```

## Config Model

- `skillctl.config.json`: source roots, enabled adapters, private roots, excludes, live probe policy
- `transport`: which install/sync transport to use; default is `skills-cli` with `embeddedRepoPath` pointing at `vendor/vercel-skills`
- `skillctl.catalog.json`: managed catalog, hashes, targets, visibility
- `.skillctl-local/managed/*.json`: local managed indexes per adapter

By default only `./skills` is discovered as a managed public root. Use `skillctl.config.example.json` as a starting point for adding upstream or private local sources.

## Embedded Upstream Lifecycle

- `vendor/vercel-skills` is a git submodule pinned to the upstream `vercel-labs/skills` repo.
- `pnpm bootstrap-upstream` installs that submodule's dependencies with `pnpm install --ignore-workspace` and builds the upstream CLI if `dist/` is missing.
- `skillctl sync` and `skillctl doctor` prefer the embedded upstream when it is bootstrapped.
- If the submodule exists but is not bootstrapped, `doctor` returns a repairable warning instead of silently drifting.
- If the submodule is missing entirely, transport falls back to `npx --yes skills`.

## Safety Rules

- Sync uses the upstream `skills` CLI in copy mode by default; no symlinks
- `prune` only removes skills previously marked as managed by `skillctl`
- Unmanaged skills already present in agent directories are left alone
- Private skills can be indexed locally but are not copied into public agent directories
