# Local Policy

Store machine-specific preferences at:

```text
${XDG_CONFIG_HOME:-$HOME/.config}/skillctl/maintain-mac-dev-environment.json
```

Keep this file outside the skill repository with mode `0600`. It can contain project roots and personal preferences, but must not contain credentials, environment values, database names, connection strings, or private Git remotes.

## Fields

```json
{
  "schema_version": 1,
  "project_roots": ["~/code"],
  "preferred_owners": {
    "node": "nvm",
    "python_runtime": "pyenv",
    "python_projects": "uv",
    "go": "version-manager",
    "rust": "rustup",
    "containers": "orbstack"
  },
  "postgres_target_major": 16,
  "protected_items": ["redis"],
  "scan_project_pins": true,
  "include_application_inventory": false,
  "include_disk_usage": false,
  "exclude_paths": []
}
```

- `schema_version`: Require `1`.
- `project_roots`: Scan only these explicit absolute or home-relative roots for version-pin files. Reject relative paths, symlink roots, `/`, the users directory, and the whole home directory.
- `preferred_owners`: Record the desired owner for a tool family. Treat values as preferences, not deletion permission.
- `postgres_target_major`: Record the desired major version or `null`. Never use it as permission to migrate or delete clusters.
- `protected_items`: Never recommend automatic removal of these names.
- `scan_project_pins`: Enable bounded scans for `.nvmrc`, `.node-version`, `.python-version`, `.tool-versions`, `rust-toolchain`, and `rust-toolchain.toml`.
- `include_application_inventory`: Opt in to Homebrew cask names plus application names and versions. It defaults to `false`; last-used timestamps are never collected.
- `include_disk_usage`: Measure known development caches, runtimes, applications, and PostgreSQL cluster directories. This can take several minutes.
- `exclude_paths`: Skip matching absolute or home-relative paths during project-pin scans.

Unknown top-level fields are rejected so misspelled privacy controls cannot silently fall back.

## Privacy Invariants

- Keep real policies and inventory snapshots out of Git.
- Treat every inventory as private metadata even after redaction. Application names, private package names, versions, and relative project paths can still identify a person, employer, or project.
- Replace the home directory with `$HOME` and the hostname with `$HOST` in output.
- Redact credential assignments and common token formats if a controlled command unexpectedly emits them.
- Treat command execution as best-effort read-only inspection, not a sandbox. The collector rejects PATH wrappers outside fixed system, Homebrew-link, and supported application roots, but a compromised installed executable remains outside its threat model.
- Never inspect process command lines or environments to discover services.
- Never read project files other than the supported version-pin filenames.
- Represent configured project roots as `root-1`, `root-2`, and so on in inventory output.
- Treat deep `du` scans as metadata-only size traversal. Do not emit internal filenames or read file contents.
