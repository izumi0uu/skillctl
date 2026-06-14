---
name: thrive-local-db-restore-login
description: Restore AWS-Thrive PostgreSQL dumps into a local dev database and fix local login after restore by rebinding a restored prod user row to the current dev Cognito user ID. Use when Codex is asked about local DB restore, pg_restore of Thrive dumps, "User not found" after restoring a prod backup, or updating users.cognito_id for a high-permission email such as tli@idahtechs.com.
---

# Thrive Local DB Restore Login

## Purpose

Use this skill for the local-only workflow after restoring a Thrive database dump: verify the target is local, restore the dump if requested, then update `users.cognito_id` so the user's dev Cognito token can match a restored high-permission `users` row.

## Core Explanation

The backend authenticates the JWT with Cognito, then populates DB user context by looking up `users.cognito_id`, not by email.

Relevant code path:

- `backend/clinical/app/dependencies/cognito.py`
- `populate_cognito_token_db_entities()`
- Query condition: `User.cognito_id == token.cognito_id`

After a prod dump is restored locally, `users.cognito_id` values still point to prod Cognito User Pool IDs. A local/dev login token contains a dev Cognito User Pool ID, so the restored DB lookup fails with `User not found` until one restored user row is rebound:

```sql
update users
set cognito_id = '<dev-cognito-user-id>'
where email = '<prod-restored-high-permission-email>';
```

This must be repeated after each clean restore because `pg_restore --clean` replaces the `users` table with dump contents.

## Safety Rules

- Treat this as a local dev workflow only.
- Do not run the rebind update against QA or prod.
- Confirm the target database is local, normally `127.0.0.1:35432/thrive_dev`.
- Never update all users or clear `cognito_id` values.
- Prefer updating a specific email row, usually the restored high-permission user the developer wants to impersonate locally.
- Do not print or store passwords, JWTs, or Slack/webhook secrets.

## Restore Checklist

1. Verify the dump can be read by a compatible `pg_restore`.
   PostgreSQL custom dump version `1.15` requires a PostgreSQL 16+ client.

   ```bash
   /opt/homebrew/opt/postgresql@16/bin/pg_restore --version
   /opt/homebrew/opt/postgresql@16/bin/pg_restore -l /path/to/backup.dump | head
   ```

2. Restore only into the local dev database unless the user explicitly asks for another local target.

   Typical local target:

   ```text
   host=127.0.0.1
   port=35432
   db=thrive_dev
   user=postgres
   password=password
   ```

3. For a clean local restore:

   ```bash
   export PGPASSWORD=password
   /opt/homebrew/opt/postgresql@16/bin/psql -h 127.0.0.1 -p 35432 -U postgres -d postgres -v ON_ERROR_STOP=1 <<'SQL'
   SELECT pg_terminate_backend(pid)
   FROM pg_stat_activity
   WHERE datname = 'thrive_dev'
     AND pid <> pg_backend_pid();
   DROP DATABASE IF EXISTS thrive_dev WITH (FORCE);
   CREATE DATABASE thrive_dev;
   SQL

   /opt/homebrew/opt/postgresql@16/bin/pg_restore \
     -h 127.0.0.1 \
     -p 35432 \
     -U postgres \
     -d thrive_dev \
     --no-owner \
     --no-acl \
     /path/to/backup.dump
   ```

4. Rebind the local login user.

   Prefer the bundled helper:

   ```bash
   /Users/idah/.codex/skills/thrive-local-db-restore-login/scripts/rebind-local-cognito-user.sh \
     tli@idahtechs.com \
     '<dev-cognito-user-id>'
   ```

   The helper defaults to `127.0.0.1:35432/thrive_dev` and refuses non-local targets.

5. Verify the row:

   ```sql
   select id, email, status, is_current, is_tenant_owner, tenant_id, cognito_id
   from users
   where email = 'tli@idahtechs.com';
   ```

## Finding The Dev Cognito User ID

If the user does not provide the dev Cognito ID, inspect the local API/frontend login token or use existing AWS/Cognito tooling in the repo. The value needed is the Cognito username/sub that appears in the JWT and is passed into `token.cognito_id`.

Do not guess this value. If it cannot be derived from local context or a token, ask the user for the dev Cognito user ID.

## Common Failure Modes

- `User not found` after restore: `users.cognito_id` still points to prod Cognito.
- `pg_restore: unsupported version (1.15)`: local `pg_restore` is too old; use PostgreSQL 16+ client.
- Local restore succeeds but login still fails: the wrong email row was rebound, the row status is not `active`/`inviting`, or the token is from a different user pool.
