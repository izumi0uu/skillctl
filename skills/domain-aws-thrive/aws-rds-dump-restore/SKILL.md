---
name: aws-rds-dump-restore
description: Explain how to create PostgreSQL databases on AWS RDS or Aurora and restore dump files into them with AWS-Thrive-aware tunnel and script guidance. Use when the user asks whether a pg_restore one-liner is enough, needs a step-by-step runbook for bastion, SSM, or local tunnel restore, wants exact commands they can run themselves, needs a bastion-first workflow because local-to-prod networking is unreliable, or needs the agent to distinguish createdb, pg_restore, psql, S3 copy, and network-access prerequisites.
---

# AWS RDS Dump Restore

## Purpose

Use this skill when the goal is to help the user perform their own database restore.

Default posture:
- organize the restore path
- explain the technical constraints behind the answer
- give user-runnable commands
- prefer a bastion-first workflow when local access to prod is flaky
- avoid executing qa or prod restore commands unless the user explicitly asks

## Core Mental Model

1. Creating a database and restoring objects into it are different steps.
2. `createdb` or `CREATE DATABASE` creates the target database.
3. `pg_restore` restores schema and data into an existing database. `--clean --if-exists` replaces objects, not the database itself.
4. For custom-format dumps, the restore host's `pg_restore` version matters. Always compare the bastion or tunnel host version with the dump's source version before restore.
5. If `pg_restore` says `unsupported version (...) in file header`, the dump was usually created by a newer PostgreSQL major version than the restore client. Regenerate the dump with a matching or older major version instead of retrying blindly.
6. `pg_restore` cannot read `s3://...` directly. Copy the dump to a local file first, or stream bytes from another process.
7. The restore command must run from a host that can reach the RDS or Aurora endpoint: a local tunnel, a bastion shell, or SSM Run Command.
8. `pg_restore` is for custom, tar, or directory dumps. For a plain `.sql` dump, use `psql -f`.
9. For risky prod restores, think in two dump artifacts: a rollback dump of the current target DB state and the incoming dump you intend to restore.
10. If the user says local-to-prod connectivity is unreliable, use the bastion as the working host and stage files under a dedicated `/tmp/...` directory there.
11. A common AWS-Thrive handoff pattern is: dump locally or from a source bastion, upload to S3, generate a presigned URL, then let the target bastion download with `curl`.

## Repo-Aware Entry Points

- Use `scripts/connect_dev_db.sh` for the AWS-Thrive dev tunnel.
- Use `scripts/connect_prod_db.sh` for the AWS-Thrive prod tunnel.
- Use `scripts/backup_db_to_s3.sh` as the repo's backup and restore example source.
- Use `backend/clinical/README.md` for the local restore example that creates the DB before restore.
- Use `docs/development-process.md` for the repo's PostgreSQL client version expectation.

Important repo nuance:
- `scripts/backup_db_to_s3.sh` does not dump your laptop's local Postgres directly.
- It does show the AWS-Thrive pattern of running `pg_dump`, uploading the dump to S3, and emitting a presigned download URL that another host such as a bastion can fetch.
- If the source DB is local or only reachable through your laptop tunnel, mirror the script's S3 plus presign tail locally to turn that dump into a temporary download link the bastion can `curl`.

Read [references/commands.md](references/commands.md) for command templates.
Read [references/project-evidence.md](references/project-evidence.md) when you need repo-backed justification.

## Workflow

1. Identify the target shape:
   - environment: local, dev, qa, or prod
   - destination database already exists or must be created
   - execution surface: local tunnel, bastion shell, or SSM Run Command
   - dump format: custom or tar or directory vs plain SQL
   - dump location: local path vs S3
2. If the dump is custom-format, verify PostgreSQL client compatibility before giving restore commands:
   - check the bastion or restore host `pg_restore --version`
   - check the dump source `pg_dump --version` or filename clue if known
   - if the dump major version is newer than the bastion major version, tell the user to regenerate the dump with a compatible client first
   - on AWS-Thrive bastions, do not assume the installed client matches the machine that produced the dump
3. Choose the execution path:
   - local tunnel when connectivity is stable and the user wants local execution
   - bastion or SSM shell when prod connectivity from local is unreliable
4. If the path is bastion-first and the restore is risky, stage two artifacts in a temp directory:
   - rollback dump for the current target DB
   - incoming dump to restore
5. If the source DB is on the local machine or behind a local tunnel, consider the S3 handoff path:
   - create the dump locally
   - upload it to S3
   - generate a presigned URL
   - download it from the bastion with `curl`
6. State the main blocker if one exists:
   - no network path to the database
   - target database does not exist
   - wrong tool for the dump format
   - dump version newer than bastion `pg_restore`
   - bastion cannot read the S3 object directly
   - dump still lives only in S3
7. Give the shortest safe command sequence.
8. Explain why the user's proposed command is enough or not enough.
9. End with verification commands and stop conditions.

## Safety Rules

- Default to advisory mode and commands the user can run themselves.
- Treat `qa` and `prod` restore as high risk. Do not execute them unless the user explicitly asks for execution in the current thread.
- Prefer repo tunnel scripts over ad hoc port-forward instructions when the target is AWS-Thrive.
- Do not print secret values. Use placeholders for passwords, hosts, and DB names.
- If the dump format is unknown, tell the user how to inspect it before recommending `pg_restore` or `psql`.
- If the restore path uses a bastion or SSM shell, proactively include the version-check step instead of assuming the bastion client is compatible.
- For prod restores, bias toward a rollback-first sequence: create or stage the rollback dump before touching the target DB.

## Output Contract

When replying, use this order:

1. one-paragraph verdict
2. prerequisites
3. exact commands
4. why this toolchain is correct
5. quick verification
