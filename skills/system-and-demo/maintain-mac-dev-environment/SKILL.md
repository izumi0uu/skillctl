---
name: maintain-mac-dev-environment
description: Audit, diagnose, plan, and safely maintain a personal macOS development environment across Homebrew, shells, PATH, language/version managers, global CLIs, background services, databases, containers, caches, and developer apps. Use when the user asks to inventory installed tools, find duplicate or conflicting versions, decide what can be removed, reclaim development-tool disk space, diagnose runtime ownership, or execute a reversible cleanup plan. Default to read-only auditing and require explicit approval before every mutation.
---

# Maintain Mac Dev Environment

Maintain a macOS development setup by separating observed facts, personal ownership policy, and explicitly approved changes. Treat duplicate installation as a finding, not as deletion permission.

## Workflow

1. Audit the machine with the bundled collector.
2. Classify each finding as `keep`, `consolidate`, `removable-after-checks`, `protected`, or `unknown`.
3. Produce a cleanup plan with evidence, expected benefit, preconditions, exact commands, and rollback steps.
4. Ask for approval of the exact mutating commands. Approval for one item does not authorize adjacent cleanup.
5. Apply one tool family at a time.
6. Re-run the collector and the affected tool checks before reporting success.

Set `SKILL_MD_PATH` to the absolute path of this loaded `SKILL.md` from the skill registry. Never infer it from the current working directory. Then run:

```bash
SKILL_DIR="$(cd -- "$(dirname -- "${SKILL_MD_PATH:?}")" && pwd)"
python3 "$SKILL_DIR/scripts/collect_inventory.py" --pretty
```

Use `--deep` when cache, application, runtime, or database-directory sizes are needed. Use `--output <path>` only when the user explicitly wants a local snapshot. The output must be an absolute regular-file path with no symlink component in its parent path; snapshots are written atomically with mode `0600`. The collector automatically reads `${XDG_CONFIG_HOME:-$HOME/.config}/skillctl/maintain-mac-dev-environment.json` when present.

Application inventory, including Homebrew cask names, is opt-in because installed application names can reveal personal or employer-specific activity. Treat every inventory as private metadata even after redaction.

Read [references/policy-schema.md](references/policy-schema.md) before creating or changing the local policy.

Read [references/data-bearing-cleanup.md](references/data-bearing-cleanup.md) before planning removal of PostgreSQL clusters, Docker/OrbStack data, or another stateful runtime.

Treat the collector as a baseline fact set. It does not replace manual reverse-dependency checks, project-specific runtime inspection, container-store inspection, or backup validation. Keep a removal recommendation `unknown` or `removable-after-checks` until those checks are complete.

## Evidence Rules

- Identify the active executable with PATH precedence, not package-manager receipts alone.
- Check reverse dependencies and global packages before removing a runtime.
- Scan configured project roots for version pins before removing language toolchains.
- Treat application metadata and last-used timestamps as hints, never proof of non-use.
- Distinguish an application, its CLI, its caches, and its data as separate removal surfaces.
- Report reclaimable cache size separately from installed-software size.
- Keep confidence explicit when evidence is incomplete.

Use this report shape:

| Item | Active source | Other sources | Dependency/data risk | Recommendation | Confidence | Required checks |
| --- | --- | --- | --- | --- | --- | --- |

## Ownership Policy

Prefer one declared owner per tool family while allowing package-manager dependencies:

- Homebrew: native libraries, native CLIs, services, and dependency-owned runtimes.
- Node: one version manager plus Corepack for project package managers.
- Python: one interpreter strategy; isolate project dependencies and CLI tools from the global interpreter.
- Rust: rustup; preserve project-pinned and ecosystem-specific toolchains.
- Go: choose Homebrew or a version manager, not both in PATH.
- Containers: choose one default runtime; inspect each runtime's private image and volume store before uninstalling.
- PostgreSQL: choose one default client and one explicit service or container target; treat every cluster directory as data-bearing.

Local policy is preference evidence, not mutation authorization.

## Safety Gates

Never perform these actions during audit:

- Run `sudo`, uninstall, cleanup, prune, stop, delete, or `rm` commands.
- Read `.env` files, Keychain, SSH keys, Git credentials, private remotes, database rows, or Docker volume contents.
- Collect full environment variables, process arguments, or process environments.
- Print hostnames, usernames, unredacted home paths, access tokens, API keys, passwords, or secrets.
- Infer a database, tenant, environment, date range, or target from a default.

Deep size measurement may traverse directory metadata with `du`, but it must not print internal filenames or read file contents.

Require exact approval before editing shell files, stopping services, changing links/defaults, clearing caches, or uninstalling software. Require a verified backup and restore path before touching PostgreSQL clusters, container volumes, or other user data.

Never automatically run:

- `brew autoremove`
- `brew bundle cleanup --force`
- `docker system prune`
- `pnpm store prune`
- `npm cache clean --force`
- `uv cache clean` or `uv cache prune`
- recursive deletion of package-manager, database, or container directories

Do not remove macOS-provided shells or runtimes. Do not change the default shell, Docker context, Homebrew link target, `PGDATA`, or proxy/VPN configuration unless the user names that exact change.

## Apply And Verify

Before each approved command, re-check that the active source, dependency state, service state, and target path still match the plan. Stop if they drift.

After a change:

1. Verify command resolution and version.
2. Verify affected projects with their version pins and targeted checks.
3. Verify services and container contexts where applicable.
4. Re-run the collector and compare the relevant facts.
5. Report actual disk change, remaining duplicates, and any validation gap.

Keep snapshots and reports under `${XDG_STATE_HOME:-$HOME/.local/state}/skillctl/maintain-mac-dev-environment/`. Never commit them with the skill.
