# skillctl

Portable skills control plane for Claude Code, Codex, Pi Agent, Hermes, and OpenCode.

`skillctl` treats a Git-tracked catalog as the source of truth for public-safe local skills, then copies managed skills into each supported agent's local skills directory without touching unmanaged content.

## What It Does

- Tracks public-safe skills in Git under `skills/`
- Records managed metadata in `skillctl.catalog.json`
- Keeps machine-local state in `.skillctl-local/`
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
packages/core      # Catalog, schema, adapters, sync/doctor/repair engine
packages/cli       # CLI entrypoint and repo-root resolution
apps/electron      # Future macOS shell; no duplicate core logic
skills/            # Public-safe managed skills committed to Git
manifests/         # Schemas and tracked metadata
```

## Quick Start

```bash
pnpm install
pnpm build
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
- `skillctl.catalog.json`: managed catalog, hashes, targets, visibility
- `.skillctl-local/managed/*.json`: local managed indexes per adapter

By default only `./skills` is discovered as a managed public root. Use `skillctl.config.example.json` as a starting point for adding upstream or private local sources.

## Safety Rules

- Sync is copy-only in v1; no symlinks
- `prune` only removes skills previously marked as managed by `skillctl`
- Unmanaged skills already present in agent directories are left alone
- Private skills can be indexed locally but are not copied into public agent directories
