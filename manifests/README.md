# manifests

Generated and tracked metadata for `skillctl`.

- `schemas/` contains JSON schemas for the public config and catalog interfaces.
- `skillctl.catalog.json` is the authoritative managed catalog.
- `skillctl.repo-references.json` tracks reference-only external repos that should stay outside managed install flows.
- local-only managed indexes stay under `.skillctl-local/` and are intentionally untracked.
