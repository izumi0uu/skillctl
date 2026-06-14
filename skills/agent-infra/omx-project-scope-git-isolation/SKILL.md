---
name: omx-project-scope-git-isolation
description: Use when working with oh-my-codex project-scope installs inside Git repositories, especially when the user wants repo-local isolation without overwriting ~/.codex/AGENTS.md, wants to keep project `.codex/`, `.omx/`, and `AGENTS.md` out of Git via `.git/info/exclude`, or launches with `CODEX_HOME="$HOME/.codex" omx --madmax --high` to reuse the same local Codex login credentials.
metadata:
  short-description: Keep project-scope OMX installs local-only in Git repos
---

# OMX Project-Scope Git Isolation

## Intent

Preserve the user's preferred setup:

- Use `omx setup --scope project` for per-project isolation so OMX does not overwrite or mutate the user's `~/.codex/AGENTS.md`.
- In Git repositories, keep project-local OMX/Codex artifacts out of worktree status using repo-local excludes, not committed `.gitignore` changes.
- Launch with `CODEX_HOME="$HOME/.codex" omx --madmax --high` when the session should reuse the same local Codex login credentials from `~/.codex`.

## Default policy

When a Git repo becomes dirty because of project-scope OMX installation:

1. Do **not** delete files first.
2. Prefer `.git/info/exclude` over editing committed `.gitignore`.
3. Add local-only ignore rules for:
   - `.omx/`
   - `.codex/`
   - `AGENTS.md`
4. Restore accidental committed `.gitignore` changes if they only contain local OMX/Codex ignore rules.
5. Verify `git status --short` is clean or report remaining non-OMX changes separately.

## Standard cleanup commands

Run from the repository root:

```bash
# Add repo-local ignore rules that are not committed.
EXCLUDE=.git/info/exclude
add_rule() { grep -qxF "$1" "$EXCLUDE" || printf '%s\n' "$1" >> "$EXCLUDE"; }
grep -qxF '# Local-only oh-my-codex / Codex artifacts' "$EXCLUDE" \
  || printf '\n# Local-only oh-my-codex / Codex artifacts\n' >> "$EXCLUDE"
add_rule '.omx/'
add_rule '.codex/'
add_rule 'AGENTS.md'

# If .gitignore was only changed to hide local OMX artifacts, restore it.
git diff -- .gitignore
git restore -- .gitignore

git status --short
```

Only run `git restore -- .gitignore` when the diff is just local OMX/Codex ignore rules. If `.gitignore` has user/business changes too, preserve them and remove only the OMX/Codex lines.

## Project-scope install preference

Use project scope when the user wants isolation from global `~/.codex/AGENTS.md`:

```bash
omx setup --scope project
```

This may create project-local artifacts such as:

- `.codex/agents/`
- `.codex/prompts/`
- `.codex/skills/`
- `.codex/config.toml`
- `.codex/hooks.json`
- `.omx/`
- `AGENTS.md`

In Git repos, these should normally be local-only via `.git/info/exclude` unless the user explicitly wants to commit them.

## Launch preference

When launching OMX for this user's local sessions, preserve credential reuse:

```bash
CODEX_HOME="$HOME/.codex" omx --madmax --high
```

Rationale: project scope gives repo isolation, while `CODEX_HOME="$HOME/.codex"` points Codex/OMX at the same local login credential store.

## If the user wants removal instead of hiding

Preview first:

```bash
omx uninstall --scope project --dry-run --verbose
```

Remove project-local OMX artifacts but keep `.omx` cache unless purging is requested:

```bash
omx uninstall --scope project
```

Remove project-local OMX artifacts and `.omx` state/cache:

```bash
omx uninstall --scope project --purge
```

Warn before purging because `.omx/` may contain useful interview transcripts, plans, specs, and session state.

## Safety boundaries

- Never modify `~/.codex/AGENTS.md` for this workflow unless the user explicitly asks.
- Never commit `.codex/`, `.omx/`, or project-local `AGENTS.md` unless the user explicitly asks.
- Never delete `.omx/` without warning that it may contain plans/interviews/specs.
- Treat `.git/info/exclude` as the preferred local-only mechanism in Git repos.
