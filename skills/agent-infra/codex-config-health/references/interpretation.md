# Interpretation Notes

Use these heuristics when reading Codex health output:

- `codex doctor` `install` fail:
  - Real issue when `codex` and `npm prefix -g` point at different package roots.
  - Usually fixable by making login-shell PATH prefer the same Node toolchain for `codex`, `npm`, and `node`.

- `codex doctor` `terminal` fail:
  - In non-interactive tool runs, `TERM=dumb` and `NO_COLOR=1` are often harness artifacts.
  - Treat as persistent only if the same values appear in the user's real login shell or app session.

- remote curated plugin `401`:
  - Expected under API-key-only auth.
  - Not a local configuration breakage by itself.

- local HTTP MCP `400`:
  - If the body indicates protocol expectations like missing session identifiers, the service is likely reachable.
  - Distinguish protocol errors from connection-refused or timeout failures.

- smoke test:
  - A real `codex exec` response beats most other indirect checks.
  - Record warnings, but do not call the whole config broken if smoke test succeeds and warnings are expected limitations.
