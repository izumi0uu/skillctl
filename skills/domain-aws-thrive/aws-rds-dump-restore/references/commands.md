# Command Templates

Use these as templates. Replace placeholders instead of inventing new values.

## 1. Start an AWS-Thrive tunnel locally

Dev:

```bash
./scripts/connect_dev_db.sh
```

Prod:

```bash
./scripts/connect_prod_db.sh
```

Expected local ports:
- dev: `localhost:25432`
- prod: `localhost:25433`

## 2. Create the target database

If the database does not exist yet:

```bash
export PGPASSWORD='<db-password>'
createdb -h <host> -p <port> -U <db-user> <target_db>
```

Equivalent SQL:

```bash
export PGPASSWORD='<db-password>'
psql -h <host> -p <port> -U <db-user> -d postgres -c 'CREATE DATABASE "<target_db>";'
```

## 3. Create a bastion working directory

For bastion or SSM-shell restores, stage everything under a dedicated temp directory:

```bash
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
TMP_DIR="/tmp/thrive-rds-restore-${TIMESTAMP}"
ROLLBACK_DUMP="$TMP_DIR/current-target-before-restore.dump"
INCOMING_DUMP="$TMP_DIR/incoming-restore.dump"

mkdir -p "$TMP_DIR"
chmod 700 "$TMP_DIR"
ls -ld "$TMP_DIR"
```

## 4. Check PostgreSQL client compatibility on the restore host

Run this before restoring a custom-format dump on a bastion or tunnel host:

```bash
command -v pg_restore
pg_restore --version
command -v psql
psql --version
```

If multiple PostgreSQL clients may be installed on the bastion:

```bash
find /usr -name pg_restore -type f 2>/dev/null -exec {} --version \;
```

Important:
- Compare the restore host `pg_restore` major version with the `pg_dump` version that created the dump.
- If the dump file name already encodes the source version, use that clue. Example: `*_16_12.dump` strongly suggests PG `16.12`.
- If restore fails with `unsupported version (...) in file header`, regenerate the dump with a compatible or older major version instead of retrying the same file.

## 5. Create a rollback dump on the bastion before a risky restore

Use this when local-to-prod networking is unreliable and you want the bastion to produce the safety backup:

```bash
export PGPASSWORD='<db-password>'

PG_DUMP=$(command -v pg_dump 2>/dev/null || find /usr -name pg_dump -type f 2>/dev/null | head -1)
echo "Using pg_dump: $PG_DUMP"
$PG_DUMP --version

$PG_DUMP \
  -h <rds-host> \
  -p 5432 \
  -U <db-user> \
  -d <target_db> \
  --format=custom \
  --compress=9 \
  --no-owner \
  --no-acl \
  --file "$ROLLBACK_DUMP"

ls -lh "$ROLLBACK_DUMP"
```

## 6. Stage two dump artifacts on the bastion

The common high-risk pattern is:
- `ROLLBACK_DUMP`: backup of the current target DB state
- `INCOMING_DUMP`: the dump you intend to restore

If the rollback dump already exists in S3:

```bash
aws s3 cp s3://<bucket>/<rollback-key>.dump "$ROLLBACK_DUMP"
```

If the bastion cannot read S3 directly, download with a presigned URL from your local machine:

```bash
curl -L '<presigned-rollback-url>' -o "$ROLLBACK_DUMP"
```

Stage the incoming restore dump:

```bash
aws s3 cp s3://<bucket>/<incoming-key>.dump "$INCOMING_DUMP"
```

Or, if bastion S3 permissions are missing:

```bash
curl -L '<presigned-incoming-url>' -o "$INCOMING_DUMP"
```

Quick check:

```bash
ls -lh "$ROLLBACK_DUMP" "$INCOMING_DUMP"
pg_restore --list "$INCOMING_DUMP" >/dev/null
```

## 7. Hand off a local or tunnel-reachable dev dump to the bastion through S3

Use this when the source DB is reachable from your machine but prod restore should happen from the bastion.
This effectively turns the local dump into a temporary download link for the bastion.

Create the dump locally:

```bash
export PGPASSWORD='<source-db-password>'

pg_dump \
  -h <source-host> \
  -p <source-port> \
  -U <source-user> \
  -d <source-db> \
  --format=custom \
  --compress=9 \
  --no-owner \
  --no-acl \
  --file /tmp/local-dev-handoff.dump
```

Upload to S3:

```bash
aws s3 cp /tmp/local-dev-handoff.dump \
  s3://<bucket>/<key>.dump \
  --profile thrive \
  --region us-west-2
```

Generate a presigned URL from the local machine:

```bash
aws s3 presign \
  s3://<bucket>/<key>.dump \
  --expires-in 3600 \
  --profile thrive \
  --region us-west-2
```

Download on the bastion:

```bash
curl -L '<presigned-url>' -o "$INCOMING_DUMP"
ls -lh "$INCOMING_DUMP"
pg_restore --list "$INCOMING_DUMP" >/dev/null
```

If the source DB is AWS dev reachable through the repo tunnel, a typical local source shape is:

```bash
./scripts/connect_dev_db.sh

export PGPASSWORD='<source-db-password>'
pg_dump \
  -h localhost \
  -p 25432 \
  -U <source-user> \
  -d <source-db> \
  --format=custom \
  --compress=9 \
  --no-owner \
  --no-acl \
  --file /tmp/local-dev-handoff.dump
```

## 8. Restore a custom-format dump from a local file

Use this for dumps produced by `pg_dump -Fc` or equivalent custom-format output:

```bash
export PGPASSWORD='<db-password>'
pg_restore \
  -h <host> \
  -p <port> \
  -U <db-user> \
  -d <target_db> \
  --clean \
  --if-exists \
  --no-owner \
  --no-acl \
  /path/to/backup.dump
```

## 9. Restore a staged dump from the bastion working directory

```bash
export PGPASSWORD='<db-password>'

createdb -h <rds-host> -p 5432 -U <db-user> <target_db> || true

pg_restore \
  -h <rds-host> \
  -p 5432 \
  -U <db-user> \
  -d <target_db> \
  --clean \
  --if-exists \
  --no-owner \
  --no-acl \
  "$INCOMING_DUMP"
```

Important:
- Keep `ROLLBACK_DUMP` in place until the restore is verified.
- Restore the incoming dump, not the rollback dump.

## 10. Restore a custom-format dump from S3 through bastion or SSM shell

```bash
set -euo pipefail
export PGPASSWORD='<db-password>'

pg_restore --version
aws s3 cp s3://<bucket>/<key>.dump /tmp/restore.dump
createdb -h <rds-host> -p 5432 -U <db-user> <target_db> || true

pg_restore \
  -h <rds-host> \
  -p 5432 \
  -U <db-user> \
  -d <target_db> \
  --clean \
  --if-exists \
  --no-owner \
  --no-acl \
  /tmp/restore.dump
```

Important:
- `createdb ... || true` is only for the "create if missing" path. If the DB must be recreated from scratch, delete it intentionally first.
- `pg_restore` cannot consume `s3://...` directly.
- On AWS-Thrive bastions, check `pg_restore --version` before downloading a large dump so you do not waste time on a known-incompatible file.

## 11. Restore a plain SQL dump

If the dump is plain text SQL, use `psql`, not `pg_restore`:

```bash
export PGPASSWORD='<db-password>'
psql \
  -h <host> \
  -p <port> \
  -U <db-user> \
  -d <target_db> \
  -f /path/to/backup.sql
```

## 12. Restore to local AWS-Thrive dev via tunnel

```bash
./scripts/connect_dev_db.sh

export PGPASSWORD='<db-password>'
pg_restore --version
createdb -h localhost -p 25432 -U <db-user> <target_db> || true

pg_restore \
  -h localhost \
  -p 25432 \
  -U <db-user> \
  -d <target_db> \
  --clean \
  --if-exists \
  --no-owner \
  --no-acl \
  /path/to/backup.dump
```

## 13. Restore to local Docker Postgres used by clinical backend

```bash
docker-compose -f docker-compose.db-only.yml up -d --remove-orphans

export PGPASSWORD='password'
pg_restore --version
createdb -h localhost -p 35432 -U postgres thrive_dev || true

pg_restore \
  -h localhost \
  -p 35432 \
  -U postgres \
  -d thrive_dev \
  --clean \
  --if-exists \
  --no-owner \
  --no-acl \
  /path/to/backup.dump
```

## 14. Cleanup the bastion working directory

Only after the restore has been verified and you no longer need the rollback file:

```bash
rm -rf "$TMP_DIR"
```

## 15. Quick verification

List relations:

```bash
export PGPASSWORD='<db-password>'
psql -h <host> -p <port> -U <db-user> -d <target_db> -c '\dt'
```

Check connection target:

```bash
export PGPASSWORD='<db-password>'
psql -h <host> -p <port> -U <db-user> -d <target_db> -c 'select current_database(), current_user;'
```

If the user is restoring AWS-Thrive local auth data, remind them that they may also need the local Cognito ID remap step described in `scripts/backup_db_to_s3.sh`.
