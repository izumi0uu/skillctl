---
name: trellis-lite
description: "Install, audit, and reapply the bounded Trellis Lite workflow for Codex and Oh My Pi projects. Use when Trellis should preserve task memory with proportional subagent routing, bounded recoverable context, and no repeated check/fix loops or mandatory release ceremony."
---

# Trellis Lite

Trellis Lite is a versioned local overlay, not a Trellis fork. It preserves
tasks, specs, session-local task selection, and cross-session recovery while
changing the workflow policy to:

- skip Trellis for small work;
- keep planning artifacts minimal;
- implement once and verify once;
- route sub-agents by task shape instead of a fixed pipeline;
- use one runtime-read-only checker by default for normal tracked work;
- parallelize only complex work with disjoint ownership;
- enforce an inspection-only checker allowlist across built-in, MCP, and
  extension-provided OMP tools; corrections stay in the main session;
- make every correction or recheck a separate, explicit user-authorized follow-up;
- reserve full suites/runtime/release gates for explicit high-risk or release scope;
- keep spec update, commit, archive, and release as explicit actions;
- bound OMP task context, expose every inline/truncated/omitted file, and reject
  source/test files from JSONL manifests.
- resolve stored active-task references through the project or explicit Trellis
  trust roots before reading task metadata or injecting task content.

## Supported Stack

- Trellis `0.6.7` and `0.6.14`
- `trellis-task-reuse` overlay `1.0.3` as the prerequisite baseline
- Codex and Oh My Pi project integrations

Unknown versions or locally modified managed files fail closed. The manager
never writes tasks, specs, workspace journals, runtime pointers, product code,
or the global Trellis npm package. Managed targets and overlay metadata reject
symlinked path components instead of following them outside the project.

OMP `17.2.12` does not treat an agent's `tools:` frontmatter as an exclusive
tool list: it may still advertise `hub`, MCP, custom, and extension-provided
tools. Trellis Lite therefore enforces the checker boundary in the project OMP
extension's pre-execution `tool_call` gate. Only `read`, `grep`, `glob`,
`ast_grep`, and the implicit `yield` result tool may execute; advertised tools
outside that set are blocked before approval or execution.

## Apply To One Project

Resolve this skill's installed directory, then run:

```bash
python3 <skill-dir>/scripts/manage_trellis_lite.py check --project <project-root>
python3 <skill-dir>/scripts/manage_trellis_lite.py apply --project <project-root>
python3 <skill-dir>/scripts/manage_trellis_lite.py check --project <project-root>
```

`check` also performs the sibling task-reuse manager's read-only preflight, so a
pristine supported Trellis project is reported as `needs_apply`, not as a Lite
conflict. `apply` validates both overlays before either can write, applies
task-reuse and Lite from exact audited hashes, then reconciles task-reuse
metadata once. One successful call leaves both managers at `status=applied` and
writes `.trellis/.overlays/trellis-lite.json`.

Exit code `0` means applied, `2` means a recognized baseline needs application,
and `1` means unsupported or conflicted state. Add `--json` for structured output.

## After Trellis Updates

Run `check`, `apply`, then `check` again. `trellis update` may restore official
files; the prerequisite task-reuse overlay and Trellis Lite are reapplied in
that order.

Do not bypass a conflict with manual anchor edits. Add a versioned baseline or
migration after reviewing the local difference.

## Verification

After changing this skill:

```bash
python3 -m unittest tests.test_trellis_lite tests.test_trellis_task_reuse
```

Then run the skillctl health flow before claiming distribution is current.
