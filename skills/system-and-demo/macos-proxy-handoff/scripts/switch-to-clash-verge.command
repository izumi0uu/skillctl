#!/bin/zsh

# Safely hand off from 自由猫 to Clash Verge. This script never force-kills a
# privileged core; cancellation leaves the source app untouched.

set -u

FREE_APP="${FREECAT_APP:-/Applications/自由猫.app}"
CLASH_APP="${CLASH_APP:-/Applications/Clash Verge.app}"
FREE_BUNDLE_ID="${FREECAT_BUNDLE_ID:-com.ziyoumao}"
CLASH_BUNDLE_ID="${CLASH_BUNDLE_ID:-io.github.clash-verge-rev.clash-verge-rev}"
FREE_GUI_PATTERN="${FREECAT_GUI_PATTERN:-$FREE_APP/Contents/MacOS/自由猫}"
FREE_CORE_PATTERN="${FREECAT_CORE_PATTERN:-$FREE_APP/Contents/MacOS/ziyoumaoCore}"
CLASH_GUI_PATTERN="${CLASH_GUI_PATTERN:-$CLASH_APP/Contents/MacOS/clash-verge}"
CLASH_CORE_PATTERN="${CLASH_CORE_PATTERN:-$CLASH_APP/Contents/MacOS/verge-mihomo}"
CLASH_PORT="${CLASH_PORT:-7891}"
CLASH_CONFIG="${CLASH_CONFIG:-${HOME:?}/Library/Application Support/io.github.clash-verge-rev.clash-verge-rev/verge.yaml}"
HEALTH_URL="${PROXY_HEALTH_URL:-https://cp.cloudflare.com/generate_204}"
DRY_RUN="${PROXY_HANDOFF_DRY_RUN:-0}"
LOG_FILE="${TMPDIR:-/tmp}/proxy-handoff-to-clash.log"

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

restore_freecat() {
  echo "Clash Verge did not pass validation; reopening 自由猫."
  /usr/bin/osascript -e "tell application id \"$CLASH_BUNDLE_ID\" to quit" >/dev/null 2>&1 || true
  wait_until_gone "$CLASH_CORE_PATTERN" || true
  /usr/bin/open -a "$FREE_APP"
  notify "Clash Verge failed; 自由猫 was reopened"
}

echo "Preparing a handoff from 自由猫 to Clash Verge."

if [[ ! -d "$FREE_APP" || ! -d "$CLASH_APP" ]]; then
  echo "An application bundle is missing. Nothing was changed."
  exit 1
fi

if [[ ! -r "$CLASH_CONFIG" ]]; then
  echo "Clash Verge configuration is not readable. Nothing was changed."
  exit 1
fi

if ! /usr/bin/grep -q "^verge_mixed_port: ${CLASH_PORT}$" "$CLASH_CONFIG" ||
   ! /usr/bin/grep -q '^enable_tun_mode: false$' "$CLASH_CONFIG" ||
   ! /usr/bin/grep -q '^enable_system_proxy: true$' "$CLASH_CONFIG"; then
  echo "Clash Verge is not prepared for port $CLASH_PORT with system proxy on and TUN off."
  echo "Nothing was changed."
  exit 1
fi

free_running="0"
clash_running="0"
if is_running "$FREE_GUI_PATTERN" || is_running "$FREE_CORE_PATTERN"; then free_running="1"; fi
if is_running "$CLASH_GUI_PATTERN" || is_running "$CLASH_CORE_PATTERN"; then clash_running="1"; fi

if [[ "$free_running" == "1" && "$clash_running" == "1" ]]; then
  echo "Both proxy applications are already active. Refusing an ambiguous handoff."
  exit 1
fi

if [[ "$clash_running" == "1" ]]; then
  echo "Clash Verge is already active; no handoff is needed."
  exit 0
fi

if [[ "$DRY_RUN" == "1" ]]; then
  echo "Dry run passed: app paths, Clash configuration, and process state are safe for a local handoff."
  exit 0
fi

if is_running "$FREE_GUI_PATTERN"; then
  echo "Confirm Quit in 自由猫 if it asks. Cancel leaves the current VPN unchanged."
  if ! /usr/bin/osascript -e "tell application id \"$FREE_BUNDLE_ID\" to quit"; then
    echo "自由猫 did not confirm Quit. The handoff was cancelled safely."
    exit 0
  fi
fi

if ! wait_until_gone "$FREE_GUI_PATTERN" || ! wait_until_gone "$FREE_CORE_PATTERN"; then
  echo "自由猫 did not shut down completely. Clash Verge will not be started."
  /usr/bin/open -a "$FREE_APP"
  exit 1
fi

echo "Starting Clash Verge on 127.0.0.1:$CLASH_PORT."
/usr/bin/open -a "$CLASH_APP"

if ! wait_for_port "$CLASH_PORT"; then
  restore_freecat
  exit 1
fi

if ! wait_for_system_proxy "$CLASH_PORT"; then
  echo "The core started, but macOS did not select proxy port $CLASH_PORT."
  restore_freecat
  exit 1
fi

http_code=$(/usr/bin/curl --silent --show-error --proxy "http://127.0.0.1:$CLASH_PORT" --max-time 15 --output /dev/null --write-out '%{http_code}' "$HEALTH_URL" 2>/dev/null || true)
if [[ "$http_code" != "204" && "$http_code" != "200" ]]; then
  restore_freecat
  exit 1
fi

echo "Handoff succeeded: Clash Verge passed proxy validation (HTTP $http_code)."
notify "Switched to Clash Verge"
