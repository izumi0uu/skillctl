---
name: trellis-task-reuse
description: Install, audit, and reapply the version-aware Trellis task-reuse overlay for Codex and Oh My Pi projects. Use when Trellis should search and reuse an existing task before creating another one, when `task.py use` is needed, or after `trellis update` may have restored upstream files.
---

# Trellis Task Reuse

This skill manages a local overlay on top of Trellis-generated project files. It keeps
`skillctl` as the canonical source while leaving the globally installed Trellis package
unchanged.

## Behavior

The overlay makes task identity follow the core outcome rather than the session or date:

- Search unarchived tasks before proposing a new task.
- Reuse the one clear match and revise its planning artifacts in place.
- Ask the user to choose when several tasks plausibly own the work.
- Offer `修改/补充现有任务`, `创建新任务`, and `暂不使用 Trellis` when a routing choice is needed.
- Create a new task only for a materially different, independently deliverable outcome.
- Use `task.py use <task>` to select an existing task without changing status or firing lifecycle hooks.
- Keep `task.py start <task>` as the reviewed transition into implementation.
- Keep known Codex/OMP sessions isolated instead of inheriting another window's sole task pointer.

## Supported Versions

- Trellis `0.6.7`
- Trellis `0.6.14`

Every managed file has an official-baseline fingerprint and one or more audited overlay
fingerprints. Compatible local variants are preserved and their exact hashes are recorded.
This includes audited Trellis Lite outputs, so applying either overlay does not turn the
other overlay's behavior-preserving files into conflicts. Optional platform files, including
the Trellis `0.6.14` Codex session-start hook, are patched when present and ignored when absent.
Older overlay content that needs a behavior or safety correction is declared as an explicit
source-version migration with its own patch and fingerprints; it is upgraded, never listed as
compatible. Unknown Trellis versions, undeclared overlay revisions, and locally modified files
fail closed. Add a new versioned patch set before using this skill with a later Trellis release.

## Agent Distribution

The `skillctl` catalog targets are `codex` and `pi`. Codex uses its normal managed skill
directory. OMP is a Pi-family runtime but discovers this skill through the shared
`~/.agents/skills` transport layer when `skills.enableAgentsUser` is enabled; its state
directory under `~/.omp/agent` is not the `skillctl` Pi mirror.

Verify OMP discovery is enabled without starting a model session:

```bash
omp config get skills.enableAgentsUser --json
```

Do not claim OMP installation from the `~/.pi/agent/skills` copy alone.

## Workflow

Resolve this skill's installed directory, then run its manager with `python3`.

1. Check one project without writing:

   ```bash
   python3 <skill-dir>/scripts/manage_trellis_task_reuse.py check --project <project-root>
   ```

2. Apply only when every present target is either the official baseline or already managed:

   ```bash
   python3 <skill-dir>/scripts/manage_trellis_task_reuse.py apply --project <project-root>
   ```

3. Run `check` again. Success means `status=applied` and every present target has its
   overlay fingerprint.

An older recognized overlay is reported as `needs_apply` with per-file `migration` state.
`apply` verifies the recorded source overlay version and exact source bytes before applying the
versioned migration patch.

4. After every `trellis update`, run `check` and then `apply` again. An update may restore
   official files; that is a recognized, safe reapply path.

For several project roots, scan first:

```bash
python3 <skill-dir>/scripts/manage_trellis_task_reuse.py scan \
  --root ~/projects \
  --root ~/AWS-Thrive
```

Bulk mutation requires the explicit `--apply` flag. The manager preflights all discovered
projects and writes none when any project is unsupported or conflicted.

```bash
python3 <skill-dir>/scripts/manage_trellis_task_reuse.py scan \
  --root ~/projects \
  --root ~/AWS-Thrive \
  --apply
```

Add `--json` to any command for machine-readable output. Exit code `0` is compliant or
successfully applied, `2` means a read-only check found recognized baseline drift, and `1`
means unsupported version, conflict, or another blocking error.

## Ownership And Safety

The manager may write only the versioned target files declared in its patch set and:

```text
.trellis/.overlays/trellis-task-reuse.json
```

The metadata records overlay version and verified file hashes. It is not Trellis task or
session lifecycle state. Read-only checks take a shared advisory lock and applies take an
exclusive advisory lock on the existing `.trellis` directory descriptor. The lock creates no
lock file or other project artifact. Bulk apply retains every project lock from all-project
preflight through the last write.

Writes are atomic. On failure, rollback restores a path only while its current inode, bytes,
and mode still match what that invocation installed. A concurrent update is preserved and the
manager reports `rollback incomplete` instead of overwriting it. Initially absent metadata is
published with no-replace semantics, so a concurrently created metadata entry is never replaced.

These concurrency guarantees apply to manager invocations that participate in the project lock.
Do not run `apply` while another tool that ignores the advisory lock is replacing target files or
their parent directories. Portable POSIX pathname APIs cannot make the final unlink or replace
conditional on a prior content comparison, and `O_NOFOLLOW` on a file does not pin every parent
directory. The manager detects non-participating changes that are visible when it re-reads a path,
but the project tree itself must be trusted for the final filesystem operation.

The manager must never write or remove:

- `.trellis/tasks/`
- `.trellis/spec/`
- `.trellis/workspace/`
- `.trellis/.runtime/`
- `.trellis/.template-hashes.json`
- the global Trellis package under `node_modules`

Do not bypass a conflict with an anchor-only edit. Inspect the local difference, decide
whether it belongs in a new versioned patch set, and update fingerprints and tests together.

## Overlay Maintenance

When supporting another Trellis version:

1. Generate a pristine Codex + OMP project with that exact Trellis release.
2. Port and review the task-reuse behavior against the new runtime and generated entry files.
3. Add a separate unified patch resource and exact pristine/overlay SHA-256 fingerprints.
4. If an already distributed overlay must change, add source-version migration resources and
   exact old/new fingerprints. Do not move the old hash into `compatible_overlay_sha256s`.
5. Run the manager tests, apply to a temporary pristine project, migrate every declared older
   overlay fixture, run `apply` twice, and
   verify the second run is a byte-for-byte no-op.
6. Leave `.trellis/.template-hashes.json` untouched so Trellis continues to recognize the
   overlay as a project customization.
