# Project Evidence

Use these repo facts when you need technical backing tied to AWS-Thrive rather than generic PostgreSQL advice.

## Tunnel scripts

- `scripts/connect_dev_db.sh`
  - starts an SSM tunnel for the dev database
  - uses local port `25432`
- `scripts/connect_prod_db.sh`
  - starts an SSM tunnel for the prod database
  - uses local port `25433`
- `scripts/README.md`
  - documents both tunnel scripts and the local ports

## Backup and restore examples

- `scripts/backup_db_to_s3.sh`
  - creates a custom-format dump with `pg_dump`
  - prints `pg_dump --version` before running the backup
  - explicitly installs `postgresql16` on the bastion if needed
  - uses the bastion as the execution host for DB-reachable backup work
  - uploads the dump to S3 and prints a 1-hour presigned URL
  - demonstrates the key handoff pattern: once a dump is in S3 plus backed by a presigned URL, another host can fetch it without sharing the original filesystem
  - prints restore examples with `pg_restore`
  - shows the repo assumption that the restore file is already local
  - shows the repo reminder that local login may need a Cognito ID remap after restore

## Local restore path

- `backend/clinical/README.md`
  - shows the local restore flow against Docker Postgres on port `35432`
  - explicitly creates `thrive_dev` before running `pg_restore`
  - supports the rule that the database itself must exist first

## Client version expectation

- `docs/development-process.md`
  - lists `psql`, `pg_dump`, and `pg_restore` version `16.x`
  - supports recommending a modern Postgres client when restore or auth compatibility is in doubt

## Practical implication

When a user asks whether a one-line `pg_restore` command is enough, the repo evidence usually supports this answer:

1. it is enough only after the dump is local
2. it is enough only after the target DB exists
3. it must run from a host with network access to the DB endpoint
4. on AWS-Thrive, the easiest local path is usually one of the provided tunnel scripts
5. on AWS-Thrive bastions, verify `pg_restore` or `psql` version before restore because the bastion client may not match the machine that created the dump
6. if local-to-prod connectivity is unreliable, move the operation onto the bastion and stage dump artifacts under `/tmp/...` there
7. if the source database is local or only reachable from the laptop, the repo-backed handoff pattern is: local dump -> S3 upload -> presigned URL -> bastion `curl` download

## Historical AWS-Thrive failure mode

- In the May 25, 2026 rerun restore flow, a bastion with `pg_restore 16.12` failed on an older file with `unsupported version (1.16) in file header`
- The working replacement dump was regenerated as `thrive_dev_group_session_rerun_20260525_16_12.dump`
- This is strong project-specific evidence that the skill should tell the user to compare bastion PostgreSQL version against the dump source version before restore
- That same flow also exposed an operational pattern worth encoding: when local access is unreliable, use the bastion as the staging host, keep a rollback dump plus the incoming dump, and only then run `pg_restore`
- `scripts/backup_db_to_s3.sh` already embodies part of this handoff pattern by producing the S3 object and a presigned link; for truly local source DBs, the same handoff can be reproduced from the laptop with local `pg_dump` plus `aws s3 cp` and `aws s3 presign`
- Operationally, this means you can treat the laptop as the dump producer and S3 plus presign as the transport layer that turns the dump into a bastion-downloadable link
