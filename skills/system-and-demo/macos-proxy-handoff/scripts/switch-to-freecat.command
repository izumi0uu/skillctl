#!/bin/zsh

# Safely hand off from Clash Verge to 自由猫.

set -u

FREE_APP="${FREECAT_APP:-/Applications/自由猫.app}"
CLASH_APP="${CLASH_APP:-/Applications/Clash Verge.app}"
CLASH_BUNDLE_ID="${CLASH_BUNDLE_ID:-io.github.clash-verge-rev.clash-verge-rev}"
FREE_CORE_PATTERN="${FREECAT_CORE_PATTERN:-$FREE_APP/Contents/MacOS/ziyoumaoCore}"
CLASH_GUI_PATTERN="${CLASH_GUI_PATTERN:-$CLASH_APP/Contents/MacOS/clash-verge}"
CLASH_CORE_PATTERN="${CLASH_CORE_PATTERN:-$CLASH_APP/Contents/MacOS/verge-mihomo}"
FREE_PORT="${FREECAT_PORT:-7890}"
HEALTH_URL="${PROXY_HEALTH_URL:-https://cp.cloudflare.com/generate_204}"
DRY_RUN="${PROXY_HANDOFF_DRY_RUN:-0}"
LOG_FILE="${TMPDIR:-/tmp}/proxy-handoff-to-freecat.log"

exec > >(tee -a "$LOG_FILE") 2>&1

notify() {
  /usr/bin/osascript -e "display notification \"$1\" with title \"VPN handoff\"" >/dev/null 2>&1 || true
}

is_running() {
  /usr/bin/pgrep -f "$1" >/dev/null 2>&1
}

wait_until_gone() {
  local pattern="$1"
  local attempts="60"
  while (( attempts > 0 )); do
    if ! is_running "$pattern"; then
      return 0
    fi
    /bin/sleep 0.5
    (( attempts-- ))
  done
  return 1
}

wait_for_port() {
  local port="$1"
  local attempts="60"
  while (( attempts > 0 )); do
    if /usr/bin/nc -z 127.0.0.1 "$port" >/dev/null 2>&1; then
      return 0
    fi
    /bin/sleep 0.5
    (( attempts-- ))
  done
  return 1
}

wait_for_system_proxy() {
  local port="$1"
  local attempts="30"
  while (( attempts > 0 )); do
    if /usr/sbin/scutil --proxy | /usr/bin/awk -v expected="$port" '
      $1 == "HTTPEnable" && $3 == "1" { enabled = 1 }
      $1 == "HTTPPort" && $3 == expected { matched = 1 }
      END { exit !(enabled && matched) }
    '; then
      return 0
    fi
    /bin/sleep 0.5
    (( attempts-- ))
  done
  return 1
}

restore_clash() {
  echo "自由猫 did not pass validation; reopening Clash Verge."
  /usr/bin/open -a "$CLASH_APP"
  notify "自由猫 failed; Clash Verge was reopened"
}

echo "Preparing a handoff from Clash Verge to 自由猫."

if [[ ! -d "$FREE_APP" || ! -d "$CLASH_APP" ]]; then
  echo "An application bundle is missing. Nothing was changed."
  exit 1
fi

free_running="0"
clash_running="0"
if is_running "$FREE_CORE_PATTERN"; then free_running="1"; fi
if is_running "$CLASH_GUI_PATTERN" || is_running "$CLASH_CORE_PATTERN"; then clash_running="1"; fi

if [[ "$free_running" == "1" && "$clash_running" == "1" ]]; then
  echo "Both proxy applications are already active. Refusing an ambiguous handoff."
  exit 1
fi

if [[ "$free_running" == "1" ]]; then
  echo "自由猫 is already active; no handoff is needed."
  exit 0
fi

if [[ "$DRY_RUN" == "1" ]]; then
  echo "Dry run passed: app paths and process state are safe for a local handoff."
  exit 0
fi

if is_running "$CLASH_GUI_PATTERN"; then
  if ! /usr/bin/osascript -e "tell application id \"$CLASH_BUNDLE_ID\" to quit"; then
    echo "Clash Verge did not confirm Quit. The handoff was cancelled safely."
    exit 0
  fi
fi

if ! wait_until_gone "$CLASH_CORE_PATTERN"; then
  echo "Clash Verge did not shut down completely. 自由猫 will not be started."
  exit 1
fi

echo "Starting 自由猫 on 127.0.0.1:$FREE_PORT."
/usr/bin/open -a "$FREE_APP"

if ! wait_for_port "$FREE_PORT"; then
  restore_clash
  exit 1
fi

if ! wait_for_system_proxy "$FREE_PORT"; then
  echo "The core started, but macOS did not select proxy port $FREE_PORT."
  restore_clash
  exit 1
fi

http_code=$(/usr/bin/curl --silent --show-error --proxy "http://127.0.0.1:$FREE_PORT" --max-time 15 --output /dev/null --write-out '%{http_code}' "$HEALTH_URL" 2>/dev/null || true)
if [[ "$http_code" != "204" && "$http_code" != "200" ]]; then
  restore_clash
  exit 1
fi

echo "Handoff succeeded: 自由猫 passed proxy validation (HTTP $http_code)."
notify "Switched to 自由猫"
