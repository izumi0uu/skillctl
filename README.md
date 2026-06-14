# skillctl

Portable skills control plane for Claude Code, Codex, Pi Agent, Hermes, and OpenCode.

`skillctl` treats a Git-tracked catalog as the source of truth for public-safe local skills, then delegates install/sync transport to the upstream `vercel-labs/skills` CLI through an embedded git submodule by default while keeping local ownership, health checks, and repair policy.

It is intentionally a control-plane wrapper around `vercel-labs/skills`, not a fork of `vercel-labs/agent-skills`. Skill content repositories remain upstream sources; `skillctl` owns policy, cataloging, health checks, and safe multi-agent mirroring.

## What It Does

- Tracks public-safe skills in Git under `skills/`
- Records managed metadata in `skillctl.catalog.json`
- Keeps machine-local state in `.skillctl-local/`
- Vendors `vercel-labs/skills` as a git submodule under `vercel-skills/`
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
vercel-skills/      # Embedded upstream skills CLI submodule
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
node packages/cli/dist/index.js taxonomy --json
node packages/cli/dist/index.js sources --json
```

## Config Model

- `skillctl.config.json`: source roots, enabled adapters, private roots, excludes, live probe policy
- `transport`: which install/sync transport to use; default is `skills-cli` with `embeddedRepoPath` pointing at `vercel-skills/`
- `skillctl.catalog.json`: managed catalog, hashes, targets, visibility
- `.skillctl-local/managed/*.json`: local managed indexes per adapter
- `skillctl taxonomy --json`: canonical grouped category tree for CLI tooling and future Electron surfaces
- `skillctl sources --json`: provenance registry plus category/source summary for audits and UI consumption

By default only `./skills` is discovered as a managed public root. Use `skillctl.config.example.json` as a starting point for adding upstream or private local sources.

## Transport Topology

`skillctl` intentionally keeps the default sync path as:

```text
skillctl catalog + skills/ canonical source
  -> embedded vercel-skills CLI
  -> ~/.agents/skills
  -> per-agent install directories
```

Per-agent install directories currently include:

- `~/.claude/skills`
- `~/.codex/skills`
- `~/.pi/agent/skills`
- `~/.hermes/skills`
- `~/.opencode/skills`

This means `~/.agents/skills` is not accidental temporary output. In `skills-cli` mode it is the shared upstream install layer that `skillctl` mirrors into each managed agent adapter.

## Why The Shared Layer Stays

- `skillctl` is intentionally a control plane around the upstream `vercel-skills` installer, not a replacement for its install semantics
- the embedded CLI remains the first transport executor, while `skillctl` adds catalog ownership, provenance, health checks, repair rules, and multi-agent mirroring
- keeping `~/.agents/skills` preserves predictable behavior across adapters when the upstream CLI is the transport authority
- if you manually remove `~/.agents/skills`, it may be recreated on the next `skillctl sync` while `transport.mode` remains `skills-cli`

## Embedded Upstream Lifecycle

- `vercel-skills/` is a git submodule pinned to the upstream `vercel-labs/skills` repo.
- `pnpm bootstrap-upstream` installs that submodule's dependencies with `pnpm install --ignore-workspace` and builds the upstream CLI if `dist/` is missing.
- `skillctl sync` and `skillctl doctor` prefer the embedded upstream when it is bootstrapped.
- If the submodule exists but is not bootstrapped, `doctor` returns a repairable warning instead of silently drifting.
- If the submodule is missing entirely, transport falls back to `npx --yes skills`.

## Safety Rules

- Sync uses the upstream `skills` CLI in copy mode by default; no symlinks
- In `skills-cli` mode, do not treat `~/.agents/skills` as disposable if you want transport behavior to stay stable
- `prune` only removes skills previously marked as managed by `skillctl`
- Unmanaged skills already present in agent directories are left alone
- Private skills can be indexed locally but are not copied into public agent directories

<!-- skillctl:managed-skill-sources:start -->
## Managed Skill Sources

| Skill | Category | Origin | Upstream Repo | Upstream Path | Ref | Source URL | Local Modifications |
| --- | --- | --- | --- | --- | --- | --- | --- |
| agents-best-practices | Knowledge And Research | derived-from-upstream | DenisSergeevitch/agents-best-practices | . | main | https://github.com/DenisSergeevitch/agents-best-practices | yes |
| anyrouter-config | Agent Infra | local-authored | n/a | n/a | n/a | n/a | no |
| aws-rds-dump-restore | Domain AWS-Thrive | local-authored | n/a | n/a | n/a | n/a | no |
| codex-config-health | Agent Infra | local-authored | n/a | n/a | n/a | n/a | no |
| codex-session-recovery | Agent Infra | local-authored | n/a | n/a | n/a | n/a | no |
| deploy-to-vercel | Deployment And Platform | derived-from-upstream | vercel-labs/agent-skills | skills/deploy-to-vercel | main | https://github.com/vercel-labs/agent-skills | yes |
| excalidraw-diagram | Productivity And Artifacts | derived-from-upstream | coleam00/excalidraw-diagram-skill | . | main | https://github.com/coleam00/excalidraw-diagram-skill | yes |
| google-sheets-editor | Productivity And Artifacts | local-authored | n/a | n/a | n/a | n/a | no |
| hermes-upstream-worktree-fix | Agent Infra | local-authored | n/a | n/a | n/a | n/a | no |
| karpathy-guidelines | Knowledge And Research | derived-from-upstream | multica-ai/andrej-karpathy-skills | . | main | https://github.com/multica-ai/andrej-karpathy-skills | yes |
| local-portable-demo | System And Demo | local-authored | n/a | n/a | n/a | n/a | no |
| motion-design | Frontend And Design | derived-from-upstream | lottiefiles/motion-design-skill | skills/motion-design | main | https://github.com/lottiefiles/motion-design-skill | yes |
| obsidian-llm-wiki | Knowledge And Research | derived-from-upstream | https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f.git | . | main | https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f | yes |
| omx-project-scope-git-isolation | Agent Infra | local-authored | n/a | n/a | n/a | n/a | no |
| recruitflow-project-ops | Domain AWS-Thrive | local-authored | n/a | n/a | n/a | n/a | no |
| repo-preflight | Agent Infra | local-authored | n/a | n/a | n/a | n/a | no |
| thrive-billing-claim-cleanup-diagnostics | Domain AWS-Thrive | local-authored | n/a | n/a | n/a | n/a | no |
| thrive-local-db-restore-login | Domain AWS-Thrive | local-authored | n/a | n/a | n/a | n/a | no |
| thrive-therapy-session-diagnostics | Domain AWS-Thrive | local-authored | n/a | n/a | n/a | n/a | no |
| vercel-cli-with-tokens | Deployment And Platform | derived-from-upstream | vercel-labs/agent-skills | skills/vercel-cli-with-tokens | main | https://github.com/vercel-labs/agent-skills | yes |
| vercel-composition-patterns | Frontend And Design | derived-from-upstream | vercel-labs/agent-skills | skills/composition-patterns | main | https://github.com/vercel-labs/agent-skills | yes |
| vercel-optimize | Deployment And Platform | derived-from-upstream | vercel-labs/agent-skills | skills/vercel-optimize | main | https://github.com/vercel-labs/agent-skills | yes |
| vercel-react-best-practices | Frontend And Design | derived-from-upstream | vercel-labs/agent-skills | skills/react-best-practices | main | https://github.com/vercel-labs/agent-skills | yes |
| vercel-react-native-skills | Frontend And Design | derived-from-upstream | vercel-labs/agent-skills | skills/react-native-skills | main | https://github.com/vercel-labs/agent-skills | yes |
| vercel-react-view-transitions | Frontend And Design | derived-from-upstream | vercel-labs/agent-skills | skills/react-view-transitions | main | https://github.com/vercel-labs/agent-skills | yes |
| web-design-guidelines | Frontend And Design | derived-from-upstream | vercel-labs/agent-skills | skills/web-design-guidelines | main | https://github.com/vercel-labs/agent-skills | yes |
| writing-guidelines | Knowledge And Research | derived-from-upstream | vercel-labs/agent-skills | skills/writing-guidelines | main | https://github.com/vercel-labs/agent-skills | yes |
<!-- skillctl:managed-skill-sources:end -->

<!-- skillctl:managed-skill-taxonomy:start -->
## Managed Skill Taxonomy

Canonical skill sources live under `skills/` and are grouped by usage-oriented category.

| Category | Purpose | Skills |
| --- | --- | --- |
| Agent Infra | Agent runtime, configuration, recovery, and operational control-plane skills | `anyrouter-config`, `codex-config-health`, `codex-session-recovery`, `hermes-upstream-worktree-fix`, `omx-project-scope-git-isolation`, `repo-preflight` |
| Knowledge And Research | Knowledge workflows, learning systems, and reusable research guidance | `agents-best-practices`, `karpathy-guidelines`, `obsidian-llm-wiki`, `writing-guidelines` |
| Frontend And Design | Frontend architecture, design systems, UI patterns, and motion guidance | `motion-design`, `vercel-composition-patterns`, `vercel-react-best-practices`, `vercel-react-native-skills`, `vercel-react-view-transitions`, `web-design-guidelines` |
| Deployment And Platform | Deployment, cloud platform, and environment optimization workflows | `deploy-to-vercel`, `vercel-cli-with-tokens`, `vercel-optimize` |
| Productivity And Artifacts | General artifact creation and productivity-oriented tool workflows | `excalidraw-diagram`, `google-sheets-editor` |
| Domain AWS-Thrive | AWS-Thrive and related domain-specific operational workflows | `aws-rds-dump-restore`, `recruitflow-project-ops`, `thrive-billing-claim-cleanup-diagnostics`, `thrive-local-db-restore-login`, `thrive-therapy-session-diagnostics` |
| System And Demo | Portable demos, fixtures, and system validation helpers | `local-portable-demo` |
<!-- skillctl:managed-skill-taxonomy:end -->
