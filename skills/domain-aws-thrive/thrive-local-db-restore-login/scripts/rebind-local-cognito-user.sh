#!/usr/bin/env bash
set -euo pipefail

EMAIL="${1:-}"
COGNITO_ID="${2:-}"
DB_HOST="${DB_HOST:-127.0.0.1}"
DB_PORT="${DB_PORT:-35432}"
DB_NAME="${DB_NAME:-thrive_dev}"
DB_USER="${DB_USER:-postgres}"
PSQL_BIN="${PSQL_BIN:-psql}"

if [[ -z "$EMAIL" || -z "$COGNITO_ID" ]]; then
  echo "Usage: $0 <email> <dev-cognito-user-id>"
  echo ""
  echo "Optional env vars: DB_HOST DB_PORT DB_NAME DB_USER PGPASSWORD PSQL_BIN"
  exit 2
fi

if [[ "$DB_HOST" != "127.0.0.1" && "$DB_HOST" != "localhost" ]]; then
  echo "Refusing to update non-local DB_HOST: $DB_HOST" >&2
  exit 1
fi

if [[ "$DB_NAME" == "thrive-prod" || "$DB_NAME" == "thrive-qa" ]]; then
  echo "Refusing to update non-local-looking DB_NAME: $DB_NAME" >&2
  exit 1
fi

"$PSQL_BIN" \
  -h "$DB_HOST" \
  -p "$DB_PORT" \
  -U "$DB_USER" \
  -d "$DB_NAME" \
  -v ON_ERROR_STOP=1 \
  -v email="$EMAIL" \
  -v cognito_id="$COGNITO_ID" <<'SQL'
select
  current_database() as database,
  inet_server_addr() as server_addr,
  inet_server_port() as server_port;

select id, email, status, is_current, is_tenant_owner, tenant_id, cognito_id as old_cognito_id
from users
where email = :'email'
order by is_current desc, updated_at desc;

update users
set cognito_id = :'cognito_id'
where email = :'email';

select id, email, status, is_current, is_tenant_owner, tenant_id, cognito_id as new_cognito_id
from users
where email = :'email'
order by is_current desc, updated_at desc;
SQL
