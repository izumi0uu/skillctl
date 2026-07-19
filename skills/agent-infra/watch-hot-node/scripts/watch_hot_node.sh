#!/usr/bin/env bash
# Build and manage the Rust hot-process watcher. The persistent LaunchAgent
# executes the compiled daemon directly; this script is only lifecycle glue.

set -euo pipefail

HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
WATCH_LOG_ROOT="${WATCH_LOG_ROOT:-$HERMES_HOME/logs/node-hot-watch}"
WATCH_CPU_THRESHOLD="${WATCH_CPU_THRESHOLD:-80}"
WATCH_WINDOWSERVER_ENABLED="${WATCH_WINDOWSERVER_ENABLED:-1}"
WATCH_WINDOWSERVER_THRESHOLD="${WATCH_WINDOWSERVER_THRESHOLD:-50}"
WATCH_INTERVAL_SEC="${WATCH_INTERVAL_SEC:-2}"
WATCH_SAMPLE_DURATION_SEC="${WATCH_SAMPLE_DURATION_SEC:-5}"
WATCH_SAMPLE_INTERVAL_MS="${WATCH_SAMPLE_INTERVAL_MS:-10}"
WATCH_COOLDOWN_SEC="${WATCH_COOLDOWN_SEC:-120}"
WATCH_VERBOSE="${WATCH_VERBOSE:-0}"
WATCH_MAX_EVENTS="${WATCH_MAX_EVENTS:-200}"
WATCH_MAX_LOG_MB="${WATCH_MAX_LOG_MB:-200}"
WATCH_MAX_CAPTURE_WORKERS="${WATCH_MAX_CAPTURE_WORKERS:-2}"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SKILL_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
DAEMON_SOURCE_DIR="$SKILL_ROOT/daemon"
DAEMON_CACHE_ROOT="${WATCH_DAEMON_CACHE_ROOT:-${XDG_CACHE_HOME:-$HOME/.cache}/watch-hot-node}"
DAEMON_BIN="${WATCH_DAEMON_BIN:-$DAEMON_CACHE_ROOT/watch-hot-process}"
DAEMON_STAMP="$DAEMON_CACHE_ROOT/source.sha256"
PID_FILE="$WATCH_LOG_ROOT/watcher.pid"
LAUNCHD_LABEL="${LAUNCHD_LABEL:-dev.hermes.node-hot-watch}"
LAUNCHD_PLIST="${LAUNCHD_PLIST:-$HOME/Library/LaunchAgents/$LAUNCHD_LABEL.plist}"

usage() {
    cat <<'EOF'
Usage: scripts/watch_hot_node.sh [--once] [--build-daemon] [--install-launch-agent] [--stop] [--status]

The persistent watcher is implemented in Rust. This script builds the release
binary on source changes and manages its LaunchAgent lifecycle.

Environment overrides:
  WATCH_CPU_THRESHOLD       Node/codex CPU threshold (default: 80)
  WATCH_WINDOWSERVER_ENABLED
                            1 watches WindowServer; 0 disables it (default: 1)
  WATCH_WINDOWSERVER_THRESHOLD
                            WindowServer CPU threshold (default: 50)
  WATCH_INTERVAL_SEC        CPU sampling interval in seconds (default: 2)
  WATCH_SAMPLE_DURATION_SEC sample duration in seconds (default: 5)
  WATCH_SAMPLE_INTERVAL_MS  sample interval in milliseconds (default: 10)
  WATCH_COOLDOWN_SEC        Per-process cooldown (default: 120)
  WATCH_MAX_EVENTS          Maximum retained event directories (default: 200)
  WATCH_MAX_LOG_MB          Maximum retained event data in MB (default: 200)
  WATCH_MAX_CAPTURE_WORKERS Maximum concurrent capture workers (default: 2)
  WATCH_VERBOSE             1 logs idle scan results; 0 stays quiet
  WATCH_LOG_ROOT            Output directory (default: ~/.hermes/logs/node-hot-watch)
  WATCH_DAEMON_CACHE_ROOT   Compiled daemon cache (default: ~/.cache/watch-hot-node)
EOF
}

log_line() {
    printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"
}

is_running_pid() {
    local pid="${1:-}"
    [[ "$pid" =~ ^[0-9]+$ ]] || return 1
    kill -0 "$pid" 2>/dev/null
}

find_cargo() {
    if command -v cargo >/dev/null 2>&1; then
        command -v cargo
        return 0
    fi
    for candidate in "$HOME/.cargo/bin/cargo" /opt/homebrew/bin/cargo /usr/local/bin/cargo; do
        if [ -x "$candidate" ]; then
            printf '%s\n' "$candidate"
            return 0
        fi
    done
    return 1
}

source_hash() {
    /usr/bin/find "$DAEMON_SOURCE_DIR" -type f \
        \( -name Cargo.toml -o -name Cargo.lock -o -name '*.rs' \) -print0 \
        | /usr/bin/sort -z \
        | /usr/bin/xargs -0 /usr/bin/shasum -a 256 \
        | /usr/bin/shasum -a 256 \
        | /usr/bin/awk '{print $1}'
}

ensure_daemon_binary() {
    local cargo current_hash installed_hash target_bin temp_bin

    if ! cargo="$(find_cargo)"; then
        echo "Rust cargo was not found. Install Rust before building this watcher." >&2
        echo "Recommended: brew install rust" >&2
        return 1
    fi
    if [ ! -f "$DAEMON_SOURCE_DIR/Cargo.toml" ]; then
        echo "Rust daemon source is missing: $DAEMON_SOURCE_DIR" >&2
        return 1
    fi

    mkdir -p "$DAEMON_CACHE_ROOT"
    current_hash="$(source_hash)"
    installed_hash="$(cat "$DAEMON_STAMP" 2>/dev/null || true)"
    if [ -x "$DAEMON_BIN" ] && [ "$current_hash" = "$installed_hash" ]; then
        return 0
    fi

    log_line "Building Rust watcher daemon"
    CARGO_TARGET_DIR="$DAEMON_CACHE_ROOT/target" \
        "$cargo" build --release --locked --manifest-path "$DAEMON_SOURCE_DIR/Cargo.toml"
    target_bin="$DAEMON_CACHE_ROOT/target/release/watch-hot-process"
    temp_bin="$DAEMON_BIN.tmp.$$"
    /usr/bin/install -m 755 "$target_bin" "$temp_bin"
    /bin/mv -f "$temp_bin" "$DAEMON_BIN"
    printf '%s\n' "$current_hash" >"$DAEMON_STAMP"
    CARGO_TARGET_DIR="$DAEMON_CACHE_ROOT/target" \
        "$cargo" clean --manifest-path "$DAEMON_SOURCE_DIR/Cargo.toml" >/dev/null
    log_line "Installed Rust watcher binary at $DAEMON_BIN"
}

stop_watcher() {
    launchctl bootout "gui/$(id -u)" "$LAUNCHD_PLIST" >/dev/null 2>&1 || true
    launchctl remove "$LAUNCHD_LABEL" >/dev/null 2>&1 || true

    if [ ! -f "$PID_FILE" ]; then
        log_line "Watcher stopped"
        return 0
    fi
    local pid
    pid="$(cat "$PID_FILE" 2>/dev/null || true)"
    if is_running_pid "$pid"; then
        kill "$pid"
        log_line "Sent TERM to watcher PID $pid"
    else
        log_line "Removing stale pidfile for PID $pid"
        /bin/rm -f "$PID_FILE"
    fi
}

status_watcher() {
    if launchctl print "gui/$(id -u)/$LAUNCHD_LABEL" >/dev/null 2>&1; then
        local version="unknown"
        if [ -x "$DAEMON_BIN" ]; then
            version="$($DAEMON_BIN --version 2>/dev/null || echo unknown)"
        fi
        log_line "Watcher is loaded in launchd as $LAUNCHD_LABEL ($version)"
        return 0
    fi
    if [ ! -f "$PID_FILE" ]; then
        log_line "Watcher is not running"
        return 1
    fi
    local pid
    pid="$(cat "$PID_FILE" 2>/dev/null || true)"
    if is_running_pid "$pid"; then
        log_line "Watcher is running with PID $pid"
        return 0
    fi
    log_line "Watcher pidfile exists but PID $pid is not running"
    return 1
}

write_launch_agent_plist() {
    mkdir -p "$(dirname "$LAUNCHD_PLIST")" "$WATCH_LOG_ROOT"
    cat >"$LAUNCHD_PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$LAUNCHD_LABEL</string>
    <key>ProgramArguments</key>
    <array>
        <string>$DAEMON_BIN</string>
    </array>
    <key>EnvironmentVariables</key>
    <dict>
        <key>HOME</key><string>$HOME</string>
        <key>WATCH_VERBOSE</key><string>$WATCH_VERBOSE</string>
        <key>WATCH_LOG_ROOT</key><string>$WATCH_LOG_ROOT</string>
        <key>WATCH_CPU_THRESHOLD</key><string>$WATCH_CPU_THRESHOLD</string>
        <key>WATCH_WINDOWSERVER_ENABLED</key><string>$WATCH_WINDOWSERVER_ENABLED</string>
        <key>WATCH_WINDOWSERVER_THRESHOLD</key><string>$WATCH_WINDOWSERVER_THRESHOLD</string>
        <key>WATCH_INTERVAL_SEC</key><string>$WATCH_INTERVAL_SEC</string>
        <key>WATCH_SAMPLE_DURATION_SEC</key><string>$WATCH_SAMPLE_DURATION_SEC</string>
        <key>WATCH_SAMPLE_INTERVAL_MS</key><string>$WATCH_SAMPLE_INTERVAL_MS</string>
        <key>WATCH_COOLDOWN_SEC</key><string>$WATCH_COOLDOWN_SEC</string>
        <key>WATCH_MAX_EVENTS</key><string>$WATCH_MAX_EVENTS</string>
        <key>WATCH_MAX_LOG_MB</key><string>$WATCH_MAX_LOG_MB</string>
        <key>WATCH_MAX_CAPTURE_WORKERS</key><string>$WATCH_MAX_CAPTURE_WORKERS</string>
    </dict>
    <key>RunAtLoad</key><true/>
    <key>KeepAlive</key><true/>
    <key>ProcessType</key><string>Background</string>
    <key>StandardOutPath</key><string>$WATCH_LOG_ROOT/watcher.log</string>
    <key>StandardErrorPath</key><string>$WATCH_LOG_ROOT/watcher.log</string>
    <key>WorkingDirectory</key><string>$DAEMON_CACHE_ROOT</string>
</dict>
</plist>
EOF
}

install_launch_agent() {
    ensure_daemon_binary
    write_launch_agent_plist
    launchctl bootout "gui/$(id -u)" "$LAUNCHD_PLIST" >/dev/null 2>&1 || true
    launchctl bootstrap "gui/$(id -u)" "$LAUNCHD_PLIST"
    log_line "Installed Rust launchd watcher as $LAUNCHD_LABEL"
}

case "${1:-}" in
    --once)
        ensure_daemon_binary
        exec "$DAEMON_BIN" --once
        ;;
    --build-daemon)
        ensure_daemon_binary
        "$DAEMON_BIN" --version
        ;;
    --install-launch-agent)
        install_launch_agent
        ;;
    --stop)
        stop_watcher
        ;;
    --status)
        status_watcher
        ;;
    -h|--help)
        usage
        ;;
    "")
        ensure_daemon_binary
        exec "$DAEMON_BIN"
        ;;
    *)
        echo "Unknown option: $1" >&2
        usage >&2
        exit 1
        ;;
esac
