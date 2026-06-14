#!/usr/bin/env bash

set -u
set -o pipefail

usage() {
  cat <<'EOF'
Usage:
  collect-evidence.sh [--repo PATH] [--output DIR] [--label NAME] [--command '...']

Read-only helper for the hermes-upstream-worktree-fix skill. It captures:
  - git repo/worktree metadata
  - local runtime/environment facts
  - optional extra command outputs

Defaults:
  --repo    current git repo root, or current working directory if not in git
  --output  $TMPDIR/hermes-evidence or /tmp/hermes-evidence
  --label   evidence

Examples:
  collect-evidence.sh --repo ~/.hermes/hermes-agent-1
  collect-evidence.sh --label systemd-stale \
    --command 'python -m pytest tests/hermes_cli/test_gateway_service.py -k restart_backoff' \
    --command 'ruff check hermes_cli/gateway.py tests/hermes_cli/test_gateway_service.py'

Notes:
  - This script is intentionally local/read-only by default.
  - It does not fetch, push, create issues, or create PRs.
  - Avoid passing commands that print secrets or dump private config.
EOF
}

die() {
  printf 'error: %s\n' "$*" >&2
  exit 1
}

sanitize_label() {
  local raw="$1"
  local sanitized
  sanitized="$(printf '%s' "$raw" | tr -c 'A-Za-z0-9._-' '-')"
  sanitized="${sanitized#-}"
  sanitized="${sanitized%-}"
  if [[ -z "$sanitized" ]]; then
    sanitized="evidence"
  fi
  printf '%s' "$sanitized"
}

append_header() {
  local file="$1"
  local title="$2"
  {
    printf '# %s\n\n' "$title"
    printf 'Generated at: %s\n\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
  } >"$file"
}

run_capture() {
  local file="$1"
  shift
  local title="$1"
  shift

  append_header "$file" "$title"
  {
    printf '$'
    printf ' %q' "$@"
    printf '\n\n'
  } >>"$file"

  if "$@" >>"$file" 2>&1; then
    printf '\n[exit 0]\n' >>"$file"
  else
    local rc=$?
    printf '\n[exit %s]\n' "$rc" >>"$file"
  fi
}

run_shell_capture() {
  local file="$1"
  local title="$2"
  local command_string="$3"

  append_header "$file" "$title"
  printf '$ %s\n\n' "$command_string" >>"$file"

  if bash -lc "$command_string" >>"$file" 2>&1; then
    printf '\n[exit 0]\n' >>"$file"
  else
    local rc=$?
    printf '\n[exit %s]\n' "$rc" >>"$file"
  fi
}

repo_arg=""
default_tmp_root="${TMPDIR:-/tmp}"
default_tmp_root="${default_tmp_root%/}"
output_root="${default_tmp_root}/hermes-evidence"
label="evidence"
declare -a extra_commands=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo)
      [[ $# -ge 2 ]] || die "--repo requires a path"
      repo_arg="$2"
      shift 2
      ;;
    --output)
      [[ $# -ge 2 ]] || die "--output requires a path"
      output_root="$2"
      shift 2
      ;;
    --label)
      [[ $# -ge 2 ]] || die "--label requires a value"
      label="$2"
      shift 2
      ;;
    --command)
      [[ $# -ge 2 ]] || die "--command requires a shell command string"
      extra_commands+=("$2")
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die "unknown argument: $1"
      ;;
  esac
done

if [[ -n "$repo_arg" ]]; then
  repo_root="$repo_arg"
else
  if repo_root="$(git rev-parse --show-toplevel 2>/dev/null)"; then
    :
  else
    repo_root="$PWD"
  fi
fi

[[ -d "$repo_root" ]] || die "repo path does not exist: $repo_root"

label="$(sanitize_label "$label")"
timestamp="$(date -u '+%Y%m%dT%H%M%SZ')"
bundle_dir="${output_root%/}/${label}-${timestamp}"
commands_dir="$bundle_dir/commands"
mkdir -p "$commands_dir"

repo_root="$(cd "$repo_root" && pwd)"
cwd_before="$PWD"
cd "$repo_root" || die "failed to enter repo path: $repo_root"

is_git_repo="false"
if git rev-parse --show-toplevel >/dev/null 2>&1; then
  is_git_repo="true"
fi

manifest="$bundle_dir/manifest.txt"
{
  printf 'bundle_dir=%s\n' "$bundle_dir"
  printf 'repo_root=%s\n' "$repo_root"
  printf 'created_at_utc=%s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
  printf 'collected_from=%s\n' "$cwd_before"
  printf 'is_git_repo=%s\n' "$is_git_repo"
  printf 'extra_command_count=%s\n' "${#extra_commands[@]}"
} >"$manifest"

run_capture "$bundle_dir/repo-status.txt" "Git Status" git status --short --branch
run_capture "$bundle_dir/repo-remotes.txt" "Git Remotes" git remote -v
run_capture "$bundle_dir/repo-branches.txt" "Git Branches" git branch -vv
run_capture "$bundle_dir/repo-worktrees.txt" "Git Worktrees" git worktree list
run_capture "$bundle_dir/repo-log.txt" "Recent Commits" git log --oneline --decorate -10
run_capture "$bundle_dir/repo-diff-stat.txt" "Working Tree Diff Stat" git diff --stat
run_capture "$bundle_dir/repo-cached-diff-stat.txt" "Staged Diff Stat" git diff --cached --stat

run_shell_capture "$bundle_dir/repo-refs.txt" "Useful Git Refs" '
git rev-parse HEAD
git rev-parse --abbrev-ref HEAD
git rev-parse --show-toplevel
git rev-parse upstream/main 2>/dev/null || true
git rev-parse origin/main 2>/dev/null || true
'

run_shell_capture "$bundle_dir/repo-rules.txt" "Repo Rule File Presence" '
pwd
find . -maxdepth 3 \( -name AGENTS.md -o -name CONTRIBUTING.md -o -path "./.github/PULL_REQUEST_TEMPLATE.md" \) | sort
'

run_shell_capture "$bundle_dir/environment.txt" "Runtime Environment" '
printf "date_utc=%s\n" "$(date -u "+%Y-%m-%dT%H:%M:%SZ")"
printf "hostname=%s\n" "$(hostname 2>/dev/null || true)"
printf "shell=%s\n" "${SHELL:-unknown}"
printf "pwd=%s\n" "$PWD"
printf "uname=%s\n" "$(uname -a 2>/dev/null || true)"
if command -v sw_vers >/dev/null 2>&1; then
  sw_vers
fi
if command -v lsb_release >/dev/null 2>&1; then
  lsb_release -a
elif [[ -f /etc/os-release ]]; then
  cat /etc/os-release
fi
if command -v systemctl >/dev/null 2>&1; then
  systemctl --version
fi
if command -v launchctl >/dev/null 2>&1; then
  launchctl version
fi
if command -v python3 >/dev/null 2>&1; then
  python3 --version
fi
if command -v node >/dev/null 2>&1; then
  node --version
fi
if command -v npm >/dev/null 2>&1; then
  npm --version
fi
if command -v gh >/dev/null 2>&1; then
  gh --version
fi
if command -v hermes >/dev/null 2>&1; then
  hermes --version
fi
'

if [[ "${#extra_commands[@]}" -gt 0 ]]; then
  i=1
  for command_string in "${extra_commands[@]}"; do
    file="$(printf '%s/extra-%02d.txt' "$commands_dir" "$i")"
    title="$(printf 'Extra Command %02d' "$i")"
    run_shell_capture "$file" "$title" "$command_string"
    i=$((i + 1))
  done
fi

{
  printf '\nfiles:\n'
  find "$bundle_dir" -maxdepth 2 -type f | sort
} >>"$manifest"

printf '%s\n' "$bundle_dir"
