#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Restore local Codex sessions that were accidentally archived.

Usage:
  restore-codex-sessions.sh [--last N] [--id SESSION_ID ...] [--dry-run] [--codex-home PATH]

Examples:
  restore-codex-sessions.sh --last 3
  restore-codex-sessions.sh --id 019dc807-6a03-7bb3-b32c-d278be243185
  restore-codex-sessions.sh --last 5 --dry-run

Notes:
  --last N selects archived threads by created_at descending, which is usually what
  "recent chats" means. Batch archive operations can make updated_at misleading.
USAGE
}

codex_home="${CODEX_HOME:-$HOME/.codex}"
last_count=""
dry_run=0
ids_text=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --last)
      [[ $# -ge 2 ]] || { echo "Missing value for --last" >&2; exit 2; }
      last_count="$2"
      shift 2
      ;;
    --id)
      [[ $# -ge 2 ]] || { echo "Missing value for --id" >&2; exit 2; }
      ids_text="${ids_text}${2}"$'\n'
      shift 2
      ;;
    --dry-run)
      dry_run=1
      shift
      ;;
    --codex-home)
      [[ $# -ge 2 ]] || { echo "Missing value for --codex-home" >&2; exit 2; }
      codex_home="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ -z "$last_count" && -z "$ids_text" ]]; then
  last_count=3
fi

if [[ -n "$last_count" && ! "$last_count" =~ ^[0-9]+$ ]]; then
  echo "--last must be a non-negative integer" >&2
  exit 2
fi

db="$codex_home/state_5.sqlite"
sessions_dir="$codex_home/sessions"

if [[ ! -f "$db" ]]; then
  echo "Missing Codex state database: $db" >&2
  exit 1
fi

sql_quote() {
  printf "'%s'" "$(printf '%s' "$1" | sed "s/'/''/g")"
}

tmp_ids="$(mktemp)"
trap 'rm -f "$tmp_ids"' EXIT

if [[ -n "$last_count" && "$last_count" -gt 0 ]]; then
  sqlite3 -noheader -batch "$db" \
    "select id from threads where archived=1 order by created_at desc limit $last_count;" \
    >> "$tmp_ids"
fi

if [[ -n "$ids_text" ]]; then
  printf '%s' "$ids_text" >> "$tmp_ids"
fi

awk 'NF && !seen[$0]++' "$tmp_ids" > "$tmp_ids.dedup"
mv "$tmp_ids.dedup" "$tmp_ids"

if [[ ! -s "$tmp_ids" ]]; then
  echo "No archived sessions matched the request."
  exit 0
fi

backup=""
if [[ "$dry_run" -eq 0 ]]; then
  backup="$db.bak-$(date +%Y%m%d-%H%M%S)-before-session-restore"
  cp -a "$db" "$backup"
  echo "BACKUP	$backup"
fi

while IFS= read -r id; do
  [[ -n "$id" ]] || continue

  id_sql="$(sql_quote "$id")"
  row="$(sqlite3 -separator $'\t' -noheader -batch "$db" \
    "select coalesce(title,''), rollout_path, archived from threads where id=$id_sql;")"

  if [[ -z "$row" ]]; then
    echo "SKIP	$id	not found in threads table"
    continue
  fi

  title="$(printf '%s' "$row" | awk -F $'\t' '{print $1}')"
  src="$(printf '%s' "$row" | awk -F $'\t' '{print $2}')"
  archived="$(printf '%s' "$row" | awk -F $'\t' '{print $3}')"

  if [[ "$archived" != "1" ]]; then
    echo "SKIP	$id	already visible	$title"
    continue
  fi

  if [[ ! -f "$src" ]]; then
    echo "SKIP	$id	missing rollout file: $src"
    continue
  fi

  base="$(basename "$src")"
  if [[ ! "$base" =~ ^rollout-([0-9]{4})-([0-9]{2})-([0-9]{2})T.*\.jsonl$ ]]; then
    echo "SKIP	$id	unrecognized rollout filename: $base"
    continue
  fi

  year="${BASH_REMATCH[1]}"
  month="${BASH_REMATCH[2]}"
  day="${BASH_REMATCH[3]}"
  dst="$sessions_dir/$year/$month/$day/$base"

  if [[ "$dry_run" -eq 1 ]]; then
    echo "DRY-RUN	$id	$title	$dst"
    continue
  fi

  mkdir -p "$(dirname "$dst")"
  if [[ ! -e "$dst" ]]; then
    cp "$src" "$dst"
  fi

  dst_sql="$(sql_quote "$dst")"
  sqlite3 -batch "$db" \
    "update threads set archived=0, archived_at=NULL, rollout_path=$dst_sql where id=$id_sql;"

  echo "RESTORED	$id	$title	$dst"
done < "$tmp_ids"

if [[ "$dry_run" -eq 0 ]]; then
  echo "VERIFY"
  while IFS= read -r id; do
    [[ -n "$id" ]] || continue
    id_sql="$(sql_quote "$id")"
    sqlite3 -separator $'\t' -noheader -batch "$db" \
      "select id, archived, rollout_path from threads where id=$id_sql;"
  done < "$tmp_ids"
fi
