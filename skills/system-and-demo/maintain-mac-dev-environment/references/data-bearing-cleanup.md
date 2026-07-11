# Data-Bearing Cleanup Gates

Use these gates before proposing commands that can stop or remove a database, container runtime, or its private data.

## Backup Acceptance

- Store the backup independently from the software and data directory being removed.
- Verify destination capacity, access controls, encryption requirements, checksums, and retention.
- Test a restore into a disposable target and define application-level acceptance checks.
- Keep backup and quarantined data until an explicit retention deadline passes.
- Treat software uninstall and data deletion as separate approvals even when an uninstaller combines them. State that coupling before approval.

## PostgreSQL

- Identify the exact cluster major version, `PGDATA`, port, service owner, and every consumer.
- Drain application connections, scheduled jobs, replication, and maintenance processes before stopping a service.
- Include roles and other globals, extensions, large objects, ownership, configuration, and tablespaces in backup planning.
- Resolve symlinks and external tablespaces without following them into deletion. Report every external path separately.
- Do not call a backup verified until a test restore passes catalog checks and targeted application checks.
- Prefer uninstalling software while retaining or quarantining its cluster. Delete the cluster only in a later, separately approved step.

## Docker Desktop And OrbStack

- Inspect each runtime independently. The active context does not prove another runtime's store is disposable.
- Inventory containers, named and anonymous volumes, local-only images, builders, build cache, Kubernetes state, and context-specific scripts.
- Inspect CLI symlinks, credential helpers, buildx builders, and compose integrations that an uninstaller may remove or rewrite.
- Determine from the installed version's documentation whether uninstall also deletes the private VM store.
- Migrate or export protected volumes and verify a representative restore before uninstall.
- Keep the selected runtime context unchanged during evidence collection unless the user approves an exact context command.

## Command Packets

Prepare separate packets for service stop, software uninstall, data quarantine, and final data deletion. For each packet, include observed target identity, preconditions, exact commands, rollback, and verification. Re-check all observations immediately before execution and stop on drift.
