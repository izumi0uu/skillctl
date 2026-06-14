---
name: codex-config-health
description: Assess and repair Codex's own local configuration health. Use when the user wants to audit `~/.codex`, verify `config.toml` or `auth.json`, diagnose `codex doctor` failures, check PATH and install consistency, scan for leaked secrets in shell startup files, validate MCP wiring, or run a safe Codex smoke test.
---

# Codex Config Health

Use this skill only for Codex's own local setup.

Scope:
- `~/.codex/config.toml`
- `~/.codex/auth.json`
- Codex MCP and plugin configuration
- local shell PATH consistency for `codex`, `npm`, and `node`
- shell startup files that may leak Codex-adjacent secrets
- `codex doctor`, `codex mcp list`, and a minimal `codex exec` smoke test

Out of scope:
- Claude / AnyRouter / `cc switch`
- project application code
- unrelated shell cleanup not tied to Codex health

## Workflow

1. Inspect the active Codex state first.
   - Read `~/.codex/config.toml`.
   - Read `~/.codex/auth.json`.
   - Run `codex doctor --json` or `--summary --ascii`.
   - Run `codex mcp list`.
   - Run `codex plugin list` when plugin health matters.
2. Separate real failures from expected limitations.
   - `TERM=dumb` in non-interactive tool runs is usually an execution-environment artifact, not a persistent user config bug.
   - Curated plugin sync `401` under API-key auth is expected when ChatGPT auth is absent.
   - MCP HTTP `400 missing MCP session id` can still mean the local server is alive.
3. Check install consistency.
   - Compare `which codex`, `which npm`, `which node`, and `npm prefix -g` inside a login shell.
   - If `codex` and `npm` point at different Node installs, fix the PATH ordering with the smallest possible shell edit.
4. Check secret exposure around Codex.
   - Flag permissive auth file modes.
   - Scan shell startup files for hardcoded or commented secrets related to Codex-adjacent providers.
   - Prefer removing stale secret-bearing comments over broad shell refactors.
5. Validate MCP and provider basics.
   - Confirm `config.toml` parses.
   - Confirm configured MCP servers are listed by Codex.
   - For local HTTP MCPs, probe only enough to distinguish dead service vs protocol-required error.
6. Run a minimal smoke test.
   - Use `codex exec --skip-git-repo-check --ephemeral` with a tiny prompt such as `Reply with the single word pong.`
   - Treat a real model response as the final proof that the local Codex path is working.

## Safe Repair Rules

- Back up user files before edits.
- Prefer the smallest reversible repair:
  - tighten file permissions
  - remove stale secret comments
  - reorder PATH lines narrowly
  - leave unrelated shell customizations untouched
- Do not rewrite large shell profiles just to make them "cleaner".
- Do not claim a fix worked until the relevant check is re-run.

## Reporting

When reporting, group findings into:
- healthy
- repaired
- expected limitations
- remaining risks

Call out the exact evidence for any failure you classify as real.

## Bundled Resources

- Run `scripts/check_codex_health.py` for the repeatable health report.
- Read `references/interpretation.md` when you need help classifying doctor warnings vs real breakage.
