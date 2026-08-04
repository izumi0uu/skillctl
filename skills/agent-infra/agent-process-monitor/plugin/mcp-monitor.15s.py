#!/usr/bin/env python3
# <xbar.title>Agent Process Monitor</xbar.title>
# <xbar.version>2.6.0</xbar.version>
# <xbar.author>Local</xbar.author>
# <xbar.desc>Agent processes, AI.INPUT.IM health, and Spotify Web controls.</xbar.desc>
# <xbar.dependencies>python3</xbar.dependencies>

"""macOS menu-bar monitor for agents, model health, and Spotify Web.

Every process is assigned to at most one top-level agent runtime by ancestry.
Session titles are shown only when a reliable PID/TTY mapping exists. The script
never sends signals, reads process environments, or writes agent runtime state.
It stores only its own model-status, notification, and Spotify mute state.
"""

from __future__ import annotations

import json
import os
import shlex
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from collections import defaultdict, deque
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import cast

REFRESH_SECONDS = 15
HOME = Path.home()
AI_INPUT_STATUS_URL = os.environ.get(
    "AI_INPUT_STATUS_URL", "https://status.input.im/api/status"
)
AI_INPUT_STATUS_PAGE_URL = os.environ.get(
    "AI_INPUT_STATUS_PAGE_URL", "https://status.input.im"
)
AI_INPUT_FETCH_TIMEOUT_SECONDS = 4.0
AI_INPUT_CACHE_SECONDS = 55
AI_INPUT_STALE_SECONDS = 180
AI_INPUT_UNREACHABLE_ALERT_THRESHOLD = 2
AI_INPUT_STATE_FILE = Path(
    os.environ.get(
        "AI_INPUT_MONITOR_STATE_FILE",
        HOME
        / "Library"
        / "Caches"
        / "skillctl"
        / "agent-process-monitor"
        / "ai-input-status.json",
    )
)
SPOTIFY_WEB_ENABLED = os.environ.get("SPOTIFY_WEB_ENABLED", "1") != "0"
SPOTIFY_WEB_AUTOMUTE = os.environ.get("SPOTIFY_WEB_AUTOMUTE", "1") != "0"
SPOTIFY_BROWSER_APP = os.environ.get("SPOTIFY_BROWSER_APP", "Google Chrome")
SPOTIFY_SCRIPT_TIMEOUT_SECONDS = 4.0
SPOTIFY_STATE_FILE = Path(
    os.environ.get(
        "SPOTIFY_WEB_STATE_FILE",
        HOME
        / "Library"
        / "Caches"
        / "skillctl"
        / "agent-process-monitor"
        / "spotify-web.json",
    )
)


@dataclass(frozen=True)
class AgentAdapter:
    key: str
    label: str
    executables: tuple[str, ...]


AGENT_ADAPTERS = (
    AgentAdapter("omp", "OMP", ("omp",)),
    AgentAdapter("codex", "Codex", ("codex",)),
    AgentAdapter("claude", "Claude Code", ("claude",)),
    AgentAdapter("opencode", "OpenCode", ("opencode",)),
    AgentAdapter("pi", "Pi", ("pi",)),
)
ADAPTER_BY_EXECUTABLE = {
    executable: adapter
    for adapter in AGENT_ADAPTERS
    for executable in adapter.executables
}
CODEX_ADAPTER = ADAPTER_BY_EXECUTABLE["codex"]

MCP_SIGNATURES = {
    "Chrome DevTools": ("chrome-devtools-mcp",),
    "Context7": ("@upstash/context7-mcp", "context7-mcp"),
    "AWS Docs": ("aws-documentation-mcp-server",),
    "AWS CloudWatch": ("cloudwatch-mcp-server",),
    "AWS Log Analyzer": ("cw-mcp-server", "log-analyzer-with-mcp"),
    "Figma": ("run-figma-mcp", "figma-developer-mcp"),
    "Jira": ("run-jira-mcp", "mcp-atlassian", "jira-mcp"),
    "Node REPL": ("node_repl",),
    "Playwright": ("@playwright/mcp", "playwright-mcp"),
    "Semble": ("semble[mcp]",),
    "LottieFiles": ("@lottiefiles/creator-mcp",),
    "MCP Remote": ("mcp-remote",),
}


@dataclass(frozen=True)
class Process:
    pid: int
    ppid: int
    cpu_percent: float
    rss_bytes: int
    elapsed_seconds: int
    tty: str | None
    executable: str
    command: str


@dataclass(frozen=True)
class Totals:
    process_count: int
    cpu_percent: float
    rss_bytes: int


@dataclass(frozen=True)
class AiInputService:
    model: str
    ok: bool | None
    latency_ms: int | None
    uptime_pct: float | None
    error: str | None = None


@dataclass(frozen=True)
class AiInputStatus:
    health: str
    generated_at: int | None
    services: tuple[AiInputService, ...]
    error: str | None = None


@dataclass(frozen=True)
class SpotifyStatus:
    health: str
    playback: str = "unknown"
    title: str | None = None
    artist: str | None = None
    is_ad: bool = False
    media_muted: bool | None = None
    auto_muted: bool = False
    error: str | None = None


@dataclass(frozen=True)
class TitleResolution:
    label: str
    session_titles: tuple[str, ...] = ()


@dataclass(frozen=True)
class ProcessGroup:
    process: Process | None
    label: str
    title_resolution: TitleResolution | None
    children: tuple[Process, ...]

    @property
    def totals(self) -> Totals:
        if self.process is None:
            return totals(self.children)
        return totals((self.process, *self.children))

@dataclass(frozen=True)
class McpInstance:
    family: str
    root: Process
    processes: tuple[Process, ...]

    @property
    def totals(self) -> Totals:
        return totals(self.processes)


@dataclass(frozen=True)
class Runtime:
    adapter: AgentAdapter
    root: Process
    label: str
    processes: tuple[Process, ...]

    @property
    def totals(self) -> Totals:
        return totals(self.processes)

    @property
    def mcp_processes(self) -> tuple[Process, ...]:
        return tuple(process for process in self.processes if classify_mcp(process.command))


def executable_name(command: str) -> str:
    first = command.strip().split(None, 1)[0] if command.strip() else ""
    return first.rsplit("/", 1)[-1].lower()


def parse_elapsed(value: str) -> int:
    days = 0
    if "-" in value:
        days_text, value = value.split("-", 1)
        days = int(days_text)
    parts = [int(part) for part in value.split(":")]
    if len(parts) == 3:
        hours, minutes, seconds = parts
    elif len(parts) == 2:
        hours, minutes, seconds = 0, *parts
    elif len(parts) == 1:
        hours, minutes, seconds = 0, 0, parts[0]
    else:
        raise ValueError(f"Unsupported elapsed time: {value}")
    return days * 86400 + hours * 3600 + minutes * 60 + seconds


def parse_ps_output(output: str) -> dict[int, Process]:
    rows: dict[int, Process] = {}
    for line in output.splitlines():
        fields = line.strip().split(None, 6)
        if len(fields) != 7:
            continue
        try:
            pid = int(fields[0])
            ppid = int(fields[1])
            cpu_percent = float(fields[2])
            rss_bytes = int(fields[3]) * 1024
            elapsed_seconds = parse_elapsed(fields[4])
        except ValueError:
            continue
        tty = None if fields[5] == "??" else fields[5].removeprefix("/dev/")
        command = fields[6]
        rows[pid] = Process(
            pid=pid,
            ppid=ppid,
            cpu_percent=cpu_percent,
            rss_bytes=rss_bytes,
            elapsed_seconds=elapsed_seconds,
            tty=tty,
            executable=executable_name(command),
            command=command,
        )
    return rows


def ps_rows() -> dict[int, Process]:
    output = subprocess.check_output(
        [
            "ps",
            "-ww",
            "-axo",
            "pid=,ppid=,%cpu=,rss=,etime=,tty=,command=",
        ],
        text=True,
    )
    return parse_ps_output(output)


def is_codex_desktop_host(process: Process) -> bool:
    command = process.command.lower()
    return "chatgpt.app/contents/macos/chatgpt" in command


def agent_adapter(process: Process) -> AgentAdapter | None:
    if is_codex_desktop_host(process):
        return CODEX_ADAPTER
    return ADAPTER_BY_EXECUTABLE.get(process.executable)


def classify_mcp(command: str) -> str | None:
    normalized = command.lower()
    for label, signatures in MCP_SIGNATURES.items():
        if any(signature in normalized for signature in signatures):
            return label
    return None


def runtime_root_for(process: Process, rows: dict[int, Process]) -> int | None:
    current: Process | None = process
    outermost_agent_pid: int | None = None
    seen: set[int] = set()

    while current is not None and current.pid not in seen:
        seen.add(current.pid)
        if agent_adapter(current) is not None:
            outermost_agent_pid = current.pid
        current = rows.get(current.ppid)

    return outermost_agent_pid


def ancestor_commands(process: Process, rows: dict[int, Process]) -> tuple[str, ...]:
    commands: list[str] = []
    current = rows.get(process.ppid)
    seen: set[int] = set()
    while current is not None and current.pid not in seen:
        seen.add(current.pid)
        commands.append(current.command.lower())
        current = rows.get(current.ppid)
    return tuple(commands)


def read_omp_title(tty: str | None, home: Path = HOME) -> str | None:
    if not tty:
        return None
    mapping_path = home / ".omp" / "agent" / "terminal-sessions" / tty
    try:
        mapping_lines = mapping_path.read_text(encoding="utf-8").splitlines()
        if len(mapping_lines) < 2:
            return None
        session_path = Path(mapping_lines[1]).expanduser()
        with session_path.open(encoding="utf-8") as session_file:
            for _ in range(12):
                line = session_file.readline()
                if not line:
                    break
                raw_record = cast(object, json.loads(line))
                if not isinstance(raw_record, dict):
                    continue
                record = cast(dict[str, object], raw_record)
                record_type = record.get("type")
                title = record.get("title")
                if record_type in {"title", "session"} and isinstance(title, str) and title:
                    return sanitize_text(title)
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    return None


def build_runtimes(
    rows: dict[int, Process],
    home: Path = HOME,
) -> tuple[tuple[Runtime, ...], tuple[Process, ...]]:
    owned: dict[int, list[Process]] = defaultdict(list)
    unattributed_mcp: list[Process] = []

    for process in rows.values():
        root_pid = runtime_root_for(process, rows)
        if root_pid is not None and root_pid in rows:
            owned[root_pid].append(process)
        elif classify_mcp(process.command):
            unattributed_mcp.append(process)

    runtimes: list[Runtime] = []
    for root_pid, processes in owned.items():
        root = rows[root_pid]
        adapter = agent_adapter(root)
        if adapter is None:
            continue
        runtimes.append(
            Runtime(
                adapter=adapter,
                root=root,
                label=runtime_label(adapter, root, rows, home),
                processes=tuple(sorted(processes, key=lambda process: process.pid)),
            )
        )

    runtimes.sort(key=lambda runtime: (runtime.adapter.label, -runtime.totals.rss_bytes, runtime.root.pid))
    return tuple(runtimes), tuple(sorted(unattributed_mcp, key=lambda process: process.pid))


def totals(processes: Iterable[Process]) -> Totals:
    process_list = tuple(processes)
    return Totals(
        process_count=len(process_list),
        cpu_percent=sum(process.cpu_percent for process in process_list),
        rss_bytes=sum(process.rss_bytes for process in process_list),
    )


def fmt_bytes(value: int) -> str:
    mib = value / 1024 / 1024
    if mib >= 1024:
        return f"{mib / 1024:.1f} GiB"
    return f"{mib:.0f} MiB"


def fmt_cpu(value: float) -> str:
    return f"{value:.1f}%"


def fmt_age(seconds: int) -> str:
    if seconds >= 86400:
        return f"{seconds // 86400}d {(seconds % 86400) // 3600}h"
    if seconds >= 3600:
        return f"{seconds // 3600}h {(seconds % 3600) // 60}m"
    return f"{seconds // 60}m"


def sanitize_text(value: str, max_length: int = 90) -> str:
    cleaned = " ".join(value.replace("|", "¦").split()).lstrip("-")
    if not cleaned:
        return "Untitled session"
    if len(cleaned) > max_length:
        return cleaned[: max_length - 1] + "…"
    return cleaned


def numeric_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return int(value)


def numeric_float(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def parse_ai_input_payload(
    payload: object,
    now_epoch: int | None = None,
) -> AiInputStatus:
    if not isinstance(payload, dict):
        raise ValueError("status payload must be an object")
    generated_at = numeric_int(payload.get("generated_at"))
    if generated_at is None:
        raise ValueError("status payload has no generated_at timestamp")
    raw_services = payload.get("services")
    if not isinstance(raw_services, list) or not raw_services:
        raise ValueError("status payload has no services")

    services: list[AiInputService] = []
    for raw_service in raw_services:
        if not isinstance(raw_service, dict):
            raise ValueError("status payload contains an invalid service")
        model_value = raw_service.get("model")
        if not isinstance(model_value, str) or not model_value.strip():
            raise ValueError("status service has no model name")
        raw_last = raw_service.get("last")
        ok: bool | None = None
        latency_ms: int | None = None
        error: str | None = None
        if isinstance(raw_last, dict):
            last_ok = raw_last.get("ok")
            ok = last_ok if isinstance(last_ok, bool) else None
            latency_ms = numeric_int(raw_last.get("latency_ms"))
            error_value = raw_last.get("error")
            if isinstance(error_value, str) and error_value.strip():
                error = sanitize_text(error_value, 140)
        services.append(
            AiInputService(
                model=sanitize_text(model_value, 60),
                ok=ok,
                latency_ms=latency_ms,
                uptime_pct=numeric_float(raw_service.get("uptime_pct")),
                error=error,
            )
        )

    now_value = int(time.time()) if now_epoch is None else now_epoch
    if now_value - generated_at > AI_INPUT_STALE_SECONDS:
        return AiInputStatus(
            health="unreachable",
            generated_at=generated_at,
            services=tuple(services),
            error="official status data is stale",
        )
    all_ok = payload.get("all_ok") is True and all(
        service.ok is True for service in services
    )
    return AiInputStatus(
        health="healthy" if all_ok else "degraded",
        generated_at=generated_at,
        services=tuple(services),
    )


def ai_input_status_payload(status: AiInputStatus) -> dict[str, object]:
    return {
        "health": status.health,
        "generated_at": status.generated_at,
        "error": status.error,
        "services": [
            {
                "model": service.model,
                "ok": service.ok,
                "latency_ms": service.latency_ms,
                "uptime_pct": service.uptime_pct,
                "error": service.error,
            }
            for service in status.services
        ],
    }


def ai_input_status_from_state(state: dict[str, object]) -> AiInputStatus | None:
    raw_status = state.get("status")
    if not isinstance(raw_status, dict):
        return None
    health = raw_status.get("health")
    raw_services = raw_status.get("services")
    if health not in {"healthy", "degraded", "unreachable"} or not isinstance(
        raw_services, list
    ):
        return None
    services: list[AiInputService] = []
    for raw_service in raw_services:
        if not isinstance(raw_service, dict):
            return None
        model = raw_service.get("model")
        if not isinstance(model, str):
            return None
        ok_value = raw_service.get("ok")
        services.append(
            AiInputService(
                model=model,
                ok=ok_value if isinstance(ok_value, bool) else None,
                latency_ms=numeric_int(raw_service.get("latency_ms")),
                uptime_pct=numeric_float(raw_service.get("uptime_pct")),
                error=(
                    raw_service.get("error")
                    if isinstance(raw_service.get("error"), str)
                    else None
                ),
            )
        )
    error_value = raw_status.get("error")
    return AiInputStatus(
        health=health,
        generated_at=numeric_int(raw_status.get("generated_at")),
        services=tuple(services),
        error=error_value if isinstance(error_value, str) else None,
    )


def read_ai_input_state(path: Path = AI_INPUT_STATE_FILE) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return cast(dict[str, object], payload) if isinstance(payload, dict) else {}


def write_ai_input_state(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            json.dump(payload, temporary_file, separators=(",", ":"))
            temporary_file.write("\n")
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        temporary_path.chmod(0o600)
        os.replace(temporary_path, path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink()
            except FileNotFoundError:
                pass


def fetch_ai_input_status(
    url: str = AI_INPUT_STATUS_URL,
    now_epoch: int | None = None,
) -> AiInputStatus:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "skillctl-agent-process-monitor/2.6.0",
        },
    )
    try:
        with urllib.request.urlopen(
            request,
            timeout=AI_INPUT_FETCH_TIMEOUT_SECONDS,
        ) as response:
            body = response.read(128 * 1024 + 1)
    except (OSError, urllib.error.URLError) as error:
        raise RuntimeError(sanitize_text(str(error), 140)) from error
    if len(body) > 128 * 1024:
        raise RuntimeError("status response is too large")
    try:
        payload = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeError("status response is not valid JSON") from error
    try:
        return parse_ai_input_payload(payload, now_epoch=now_epoch)
    except ValueError as error:
        raise RuntimeError(sanitize_text(str(error), 140)) from error


def ai_input_failure_summary(status: AiInputStatus) -> str:
    failing_models = [
        service.model for service in status.services if service.ok is not True
    ]
    if status.health == "degraded" and failing_models:
        return "Model probe failed: " + ", ".join(failing_models[:4])
    return "Official model monitor is unreachable"


def ai_input_notification_transition(
    previous: dict[str, object],
    status: AiInputStatus,
    checked_at: int,
) -> tuple[dict[str, object], str | None]:
    alerting = previous.get("alerting") is True
    previous_failures = numeric_int(previous.get("consecutive_fetch_failures")) or 0
    fetch_failures = previous_failures + 1 if status.health == "unreachable" else 0
    notification: str | None = None

    if status.health == "healthy":
        if alerting:
            notification = f"Recovered: {len(status.services)}/{len(status.services)} models online"
        alerting = False
    elif status.health == "degraded":
        if not alerting:
            notification = ai_input_failure_summary(status)
        alerting = True
    elif (
        not alerting
        and fetch_failures >= AI_INPUT_UNREACHABLE_ALERT_THRESHOLD
    ):
        notification = ai_input_failure_summary(status)
        alerting = True

    return (
        {
            "schema_version": 1,
            "checked_at": checked_at,
            "health": status.health,
            "alerting": alerting,
            "consecutive_fetch_failures": fetch_failures,
            "status": ai_input_status_payload(status),
        },
        notification,
    )


def apple_script_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def send_ai_input_notification(message: str) -> None:
    if os.environ.get("AI_INPUT_NOTIFICATIONS", "1") == "0":
        return
    script = (
        f'display notification "{apple_script_string(message)}" '
        'with title "Agent Process Monitor" subtitle "AI.INPUT.IM"'
    )
    try:
        _ = subprocess.run(
            ["/usr/bin/osascript", "-e", script],
            capture_output=True,
            timeout=3,
        )
    except (OSError, subprocess.TimeoutExpired):
        pass


def collect_ai_input_status(
    state_file: Path = AI_INPUT_STATE_FILE,
    now_epoch: int | None = None,
) -> AiInputStatus:
    now_value = int(time.time()) if now_epoch is None else now_epoch
    previous = read_ai_input_state(state_file)
    cached = ai_input_status_from_state(previous)
    checked_at = numeric_int(previous.get("checked_at"))
    if (
        cached is not None
        and checked_at is not None
        and 0 <= now_value - checked_at < AI_INPUT_CACHE_SECONDS
    ):
        return cached

    try:
        status = fetch_ai_input_status(now_epoch=now_value)
    except RuntimeError as error:
        status = AiInputStatus(
            health="unreachable",
            generated_at=cached.generated_at if cached else None,
            services=cached.services if cached else (),
            error=sanitize_text(str(error), 140),
        )
    next_state, notification = ai_input_notification_transition(
        previous,
        status,
        checked_at=now_value,
    )
    try:
        write_ai_input_state(state_file, next_state)
    except OSError:
        notification = None
    if notification:
        send_ai_input_notification(notification)
    return status


SPOTIFY_STATUS_JAVASCRIPT = r"""
(() => {
  const clean = (value) => (value || "").replace(/\s+/g, " ").trim();
  const playButton = document.querySelector(
    '[data-testid="control-button-playpause"], button[aria-label="Play"], button[aria-label="Pause"], button[aria-label="播放"], button[aria-label="暂停"], button[aria-label="暫停"]'
  );
  const playLabel = clean(playButton?.getAttribute("aria-label"));
  const playing = /^(pause|暂停|暫停|一時停止)/i.test(playLabel);
  const paused = /^(play|播放|再生)/i.test(playLabel);
  const titleElement = document.querySelector(
    '[data-testid="context-item-info-title"], [data-testid="track-info-name"], [data-testid="context-item-link"]'
  );
  const artistElement = document.querySelector(
    '[data-testid="context-item-info-subtitles"], [data-testid="track-info-artists"]'
  );
  const title = clean(titleElement?.textContent) || clean(document.title);
  const artist = clean(artistElement?.textContent);
  const nowPlaying = document.querySelector(
    '[data-testid="now-playing-widget"], [data-testid="now-playing-bar"]'
  );
  const adNode = nowPlaying?.querySelector(
    '[data-testid="ad-banner"], [data-testid*="advertisement"], [data-testid="track-info-advertiser"]'
  ) || document.querySelector('[data-testid="ad-banner"]');
  const adSignal = clean(`${nowPlaying?.textContent || ""} ${document.title}`);
  const media = [...document.querySelectorAll("audio, video")];
  return JSON.stringify({
    playback: playing ? "playing" : (paused ? "paused" : "unknown"),
    title,
    artist,
    is_ad: Boolean(adNode) || /advertisement|advertising|广告|廣告/i.test(adSignal),
    media_muted: media.length ? media.every((element) => element.muted) : null
  });
})()
"""

SPOTIFY_TOGGLE_JAVASCRIPT = r"""
(() => {
  const button = document.querySelector(
    '[data-testid="control-button-playpause"], button[aria-label="Play"], button[aria-label="Pause"], button[aria-label="播放"], button[aria-label="暂停"], button[aria-label="暫停"]'
  );
  if (!button) return JSON.stringify({ok: false, error: "playback control unavailable"});
  button.click();
  return JSON.stringify({ok: true});
})()
"""


def compact_javascript(source: str) -> str:
    return " ".join(line.strip() for line in source.splitlines() if line.strip())


def run_spotify_javascript(
    javascript: str,
    tab_id: int | None = None,
) -> tuple[int | None, str | None, str | None]:
    browser = apple_script_string(SPOTIFY_BROWSER_APP)
    source = apple_script_string(compact_javascript(javascript))
    tab_condition = 'URL of spotifyTab starts with "https://open.spotify.com/"'
    if tab_id is not None:
        tab_condition = f"id of spotifyTab is {tab_id} and {tab_condition}"
    script = "\n".join(
        (
            f'if application "{browser}" is not running then return "__NOT_RUNNING__"',
            f'tell application "{browser}"',
            "repeat with spotifyWindow in windows",
            "repeat with spotifyTab in tabs of spotifyWindow",
            f"if {tab_condition} then",
            f'set spotifyResult to execute spotifyTab javascript "{source}"',
            "return (id of spotifyTab as text) & tab & spotifyResult",
            "end if",
            "end repeat",
            "end repeat",
            'return "__NO_TAB__"',
            "end tell",
        )
    )
    try:
        completed = subprocess.run(
            ["/usr/bin/osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=SPOTIFY_SCRIPT_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return None, None, sanitize_text(str(error), 140)
    output = completed.stdout.strip()
    if completed.returncode != 0:
        detail = completed.stderr.strip() or "Chrome AppleScript failed"
        lowered = detail.lower()
        if (
            "allow javascript from apple events" in lowered
            or "javascript 的功能已关闭" in detail
            or "允许 Apple 事件中的 JavaScript" in detail
        ):
            return None, None, "permission"
        return None, None, sanitize_text(detail, 140)
    if output == "__NOT_RUNNING__":
        return None, None, "not-running"
    if output == "__NO_TAB__":
        return None, None, "not-found"
    tab_id_text, separator, payload = output.partition("\t")
    try:
        tab_id = int(tab_id_text)
    except ValueError:
        return None, None, "Chrome returned an invalid Spotify tab identifier"
    if not separator:
        return None, None, "Chrome returned no Spotify page result"
    return tab_id, payload, None


def parse_spotify_payload(payload: str) -> SpotifyStatus:
    try:
        raw = json.loads(payload)
    except json.JSONDecodeError as error:
        raise ValueError("Spotify returned invalid page data") from error
    if not isinstance(raw, dict):
        raise ValueError("Spotify page data is not an object")
    playback_value = raw.get("playback")
    playback = (
        playback_value
        if playback_value in {"playing", "paused", "unknown"}
        else "unknown"
    )
    title_value = raw.get("title")
    artist_value = raw.get("artist")
    muted_value = raw.get("media_muted")
    return SpotifyStatus(
        health="ready",
        playback=playback,
        title=title_value if isinstance(title_value, str) and title_value else None,
        artist=artist_value if isinstance(artist_value, str) and artist_value else None,
        is_ad=raw.get("is_ad") is True,
        media_muted=muted_value if isinstance(muted_value, bool) else None,
    )


def spotify_ad_mute_transition(
    previous: dict[str, object],
    *,
    tab_id: int,
    is_ad: bool,
    media_muted: bool | None,
    enabled: bool = SPOTIFY_WEB_AUTOMUTE,
) -> tuple[dict[str, object], bool | None]:
    inactive: dict[str, object] = {"schema_version": 1, "active": False}
    previous_tab_id = numeric_int(previous.get("tab_id"))
    same_active_tab = previous.get("active") is True and previous_tab_id == tab_id
    owned = same_active_tab and previous.get("owned") is True
    prior_muted = previous.get("prior_muted") is True

    if not enabled or not is_ad:
        desired_muted = prior_muted if owned else None
        return inactive, desired_muted

    if media_muted is None:
        return (previous if same_active_tab else inactive), None

    if same_active_tab:
        normalized = {
            "schema_version": 1,
            "active": True,
            "tab_id": tab_id,
            "owned": owned,
            "prior_muted": prior_muted,
        }
        return normalized, True if owned and not media_muted else None

    owns_mute = not media_muted
    return (
        {
            "schema_version": 1,
            "active": True,
            "tab_id": tab_id,
            "owned": owns_mute,
            "prior_muted": media_muted,
        },
        True if owns_mute else None,
    )


def set_spotify_media_muted(tab_id: int, muted: bool) -> str | None:
    value = "true" if muted else "false"
    javascript = (
        "(() => { const media = [...document.querySelectorAll(\"audio, video\")]; "
        f"media.forEach((element) => {{ element.muted = {value}; }}); "
        "return JSON.stringify({ok: true, count: media.length}); })()"
    )
    _, payload, error = run_spotify_javascript(javascript, tab_id=tab_id)
    if error:
        return error
    try:
        result = json.loads(payload or "")
    except json.JSONDecodeError:
        return "Spotify returned invalid mute confirmation"
    if not isinstance(result, dict) or result.get("ok") is not True:
        return "Spotify did not confirm the mute change"
    return None


def collect_spotify_status(
    state_file: Path = SPOTIFY_STATE_FILE,
) -> SpotifyStatus | None:
    if not SPOTIFY_WEB_ENABLED:
        return None
    tab_id, payload, error = run_spotify_javascript(SPOTIFY_STATUS_JAVASCRIPT)
    if error == "not-running":
        return SpotifyStatus(health="not-running")
    if error == "not-found":
        return SpotifyStatus(health="not-found")
    if error == "permission":
        return SpotifyStatus(health="permission")
    if error:
        return SpotifyStatus(health="error", error=error)
    if tab_id is None or payload is None:
        return SpotifyStatus(health="error", error="Spotify page returned no data")
    try:
        status = parse_spotify_payload(payload)
    except ValueError as parse_error:
        return SpotifyStatus(health="error", error=str(parse_error))

    previous = read_ai_input_state(state_file)
    next_state, desired_muted = spotify_ad_mute_transition(
        previous,
        tab_id=tab_id,
        is_ad=status.is_ad,
        media_muted=status.media_muted,
    )
    mutation_error = (
        set_spotify_media_muted(tab_id, desired_muted)
        if desired_muted is not None
        else None
    )
    if mutation_error:
        return SpotifyStatus(
            **{**status.__dict__, "error": mutation_error},
        )
    try:
        if next_state != previous:
            write_ai_input_state(state_file, next_state)
    except OSError as state_error:
        if desired_muted is True and previous.get("active") is not True:
            _ = set_spotify_media_muted(tab_id, False)
        return SpotifyStatus(
            **{**status.__dict__, "error": sanitize_text(str(state_error), 140)},
        )
    effective_muted = desired_muted if desired_muted is not None else status.media_muted
    return SpotifyStatus(
        **{
            **status.__dict__,
            "media_muted": effective_muted,
            "auto_muted": next_state.get("active") is True
            and next_state.get("owned") is True,
        },
    )


def send_spotify_notification(message: str) -> None:
    script = (
        f'display notification "{apple_script_string(message)}" '
        'with title "Agent Process Monitor" subtitle "Spotify Web"'
    )
    try:
        _ = subprocess.run(
            ["/usr/bin/osascript", "-e", script],
            capture_output=True,
            timeout=3,
        )
    except (OSError, subprocess.TimeoutExpired):
        pass


def toggle_spotify_playback() -> None:
    _, payload, error = run_spotify_javascript(SPOTIFY_TOGGLE_JAVASCRIPT)
    if error:
        send_spotify_notification(
            "Enable Chrome > View > Developer > Allow JavaScript from Apple Events"
            if error == "permission"
            else f"Playback control failed: {error}"
        )
        return
    try:
        result = json.loads(payload or "")
    except json.JSONDecodeError:
        result = {}
    if not isinstance(result, dict) or result.get("ok") is not True:
        detail = result.get("error") if isinstance(result, dict) else None
        send_spotify_notification(
            str(detail) if detail else "Playback control unavailable"
        )


def fmt_latency(value: int | None) -> str:
    if value is None:
        return "-"
    if value < 1000:
        return f"{value}ms"
    return f"{value / 1000:.1f}s"


def ai_input_counts(status: AiInputStatus) -> tuple[int, int]:
    return sum(service.ok is True for service in status.services), len(status.services)


def append_ai_input_lines(lines: list[str], status: AiInputStatus) -> None:
    healthy, total = ai_input_counts(status)
    if status.health == "healthy":
        max_latency = max(
            (
                service.latency_ms
                for service in status.services
                if service.latency_ms is not None
            ),
            default=None,
        )
        lines.append(
            f"AI.INPUT.IM: {healthy}/{total} online · max {fmt_latency(max_latency)}"
            " | color=green"
        )
    elif status.health == "degraded":
        lines.append(
            f"AI.INPUT.IM: {healthy}/{total} online · model failure | color=red"
        )
    else:
        known = f" · last known {healthy}/{total}" if total else ""
        lines.append(f"AI.INPUT.IM: monitor unreachable{known} | color=orange")

    for service in status.services:
        if service.ok is True:
            state_text, color = "online", "green"
        elif service.ok is False:
            state_text, color = "failing", "red"
        else:
            state_text, color = "pending", "orange"
        uptime = (
            f"{service.uptime_pct:.2f}% / 60m"
            if service.uptime_pct is not None
            else "uptime -"
        )
        lines.append(
            f"--{service.model} · {state_text} · {fmt_latency(service.latency_ms)}"
            f" · {uptime} | color={color}"
        )
        if service.error:
            lines.append(f"----{sanitize_text(service.error, 110)} | color=gray")
    if status.error:
        lines.append(f"--{sanitize_text(status.error, 110)} | color=gray")
    lines.append(
        "--Open official model monitor"
        f" | bash=/usr/bin/open param1={AI_INPUT_STATUS_PAGE_URL} terminal=false"
    )
    lines.append("---")


def append_spotify_lines(
    lines: list[str],
    status: SpotifyStatus,
    plugin_path: Path | None = None,
) -> None:
    if status.health == "not-running":
        lines.append("Spotify Web: Chrome not running | color=gray")
    elif status.health == "not-found":
        lines.append("Spotify Web: no open player tab | color=gray")
    elif status.health == "permission":
        lines.append("Spotify Web: Chrome permission required | color=orange")
        lines.append("--Chrome > View > Developer | color=gray")
        lines.append("--Enable Allow JavaScript from Apple Events | color=orange")
    elif status.health == "error":
        lines.append("Spotify Web: control unavailable | color=orange")
        if status.error:
            lines.append(f"--{sanitize_text(status.error, 110)} | color=gray")
    else:
        if status.is_ad:
            state_text = "Advertisement · auto-muted" if status.auto_muted else "Advertisement"
            color = "orange"
        elif status.playback == "playing":
            state_text, color = "Playing", "green"
        elif status.playback == "paused":
            state_text, color = "Paused", "gray"
        else:
            state_text, color = "Playback state unavailable", "orange"
        title = f" · {sanitize_text(status.title, 65)}" if status.title else ""
        lines.append(f"Spotify Web: {state_text}{title} | color={color}")
        if status.artist:
            lines.append(f"--{sanitize_text(status.artist, 80)} | color=gray")
        if status.error:
            lines.append(f"--Auto-mute warning: {sanitize_text(status.error, 95)} | color=orange")
        action = "Pause Spotify" if status.playback == "playing" else "Play Spotify"
        executable = shlex.quote(str((plugin_path or Path(__file__)).resolve()))
        lines.append(
            f"--{action} | bash={executable} param1=spotify-toggle"
            " terminal=false refresh=true"
        )
        automute_text = "on" if SPOTIFY_WEB_AUTOMUTE else "off"
        lines.append(f"--Advertisement auto-mute: {automute_text} | color=gray")
    lines.append(
        "--Open Spotify Web | bash=/usr/bin/open"
        " param1=https://open.spotify.com/ terminal=false"
    )
    lines.append("---")


def totals_text(value: Totals) -> str:
    noun = "process" if value.process_count == 1 else "processes"
    return (
        f"CPU {fmt_cpu(value.cpu_percent)} · {fmt_bytes(value.rss_bytes)}"
        f" · {value.process_count} {noun}"
    )


def group_mcp(processes: Iterable[Process]) -> dict[str, tuple[Process, ...]]:
    grouped: dict[str, list[Process]] = defaultdict(list)
    for process in processes:
        label = classify_mcp(process.command)
        if label:
            grouped[label].append(process)
    return {
        label: tuple(items)
        for label, items in sorted(
            grouped.items(),
            key=lambda item: (-totals(item[1]).rss_bytes, item[0]),
        )
    }


def title_color(cpu_percent: float, rss_bytes: int) -> str:
    if cpu_percent >= 400 or rss_bytes >= 8 * 1024**3:
        return "red"
    if cpu_percent >= 100 or rss_bytes >= 4 * 1024**3:
        return "orange"
    return "green"


def process_metrics_text(process: Process) -> str:
    return (
        f"PID {process.pid} · CPU {fmt_cpu(process.cpu_percent)}"
        f" · {fmt_bytes(process.rss_bytes)} · age {fmt_age(process.elapsed_seconds)}"
    )


def process_detail_text(process: Process) -> str:
    executable = sanitize_text(process.executable or "unknown")
    return f"{executable} · {process_metrics_text(process)}"


def append_process_group(
    lines: list[str],
    label: str,
    processes: Iterable[Process],
    prefix: str,
) -> None:
    ordered = tuple(
        sorted(
            processes,
            key=lambda process: (-process.rss_bytes, -process.cpu_percent, process.pid),
        )
    )
    if not ordered:
        return
    lines.append(f"{prefix}{label} · {totals_text(totals(ordered))}")
    child_prefix = prefix + "--"
    for process in ordered:
        lines.append(f"{child_prefix}{process_detail_text(process)}")


def runtime_title_resolution(
    adapter: AgentAdapter,
    root: Process,
    rows: dict[int, Process],
    home: Path = HOME,
) -> TitleResolution | None:
    pid_text = f"PID {root.pid}"

    if adapter.key == "omp":
        title = read_omp_title(root.tty, home)
        if title:
            return TitleResolution(f"{title} · {pid_text}")
        return None

    if adapter.key == "codex":
        shared = is_codex_desktop_host(root) or any(
            "chatgpt.app" in command for command in ancestor_commands(root, rows)
        )
        if shared:
            return TitleResolution(f"Codex Desktop · shared runtime · {pid_text}")
        return None

    return None


def runtime_label(
    adapter: AgentAdapter,
    root: Process,
    rows: dict[int, Process],
    home: Path = HOME,
) -> str:
    resolution = runtime_title_resolution(adapter, root, rows, home)
    if resolution is not None:
        return resolution.label

    pid_text = f"PID {root.pid}"
    tty_text = root.tty or "no TTY"
    kind = "CLI" if root.tty else "background runtime"
    return f"{adapter.label} {kind} · {tty_text} · {pid_text}"


def process_by_pid(runtime: Runtime) -> dict[int, Process]:
    return {process.pid: process for process in runtime.processes}


def child_process_index(
    processes: Iterable[Process],
) -> dict[int, tuple[Process, ...]]:
    grouped: defaultdict[int, list[Process]] = defaultdict(list)
    for process in processes:
        grouped[process.ppid].append(process)
    return {
        parent_pid: tuple(
            sorted(
                children,
                key=lambda child: (
                    -child.rss_bytes,
                    -child.cpu_percent,
                    child.pid,
                ),
            )
        )
        for parent_pid, children in grouped.items()
    }


def process_subtree(
    process: Process,
    children_by_parent: dict[int, tuple[Process, ...]],
) -> tuple[Process, ...]:
    subtree: list[Process] = []
    queue = deque((process,))
    seen: set[int] = set()
    while queue:
        current = queue.popleft()
        if current.pid in seen:
            continue
        seen.add(current.pid)
        subtree.append(current)
        queue.extend(children_by_parent.get(current.pid, ()))
    return tuple(subtree)


def descendant_processes(process: Process, runtime: Runtime) -> tuple[Process, ...]:
    children_by_parent = child_process_index(runtime.processes)
    return tuple(
        sorted(
            process_subtree(process, children_by_parent)[1:],
            key=lambda candidate: candidate.pid,
        )
    )


def codex_desktop_helper_role(process: Process) -> str:
    if process.executable == "codex-code-mode-host":
        return "Code mode host"
    if process.executable == "bare-modifier-monitor":
        return "Modifier monitor"
    return "Support helper"


def read_codex_session_handles_by_pid(
    pids: Iterable[int], home: Path = HOME
) -> dict[int, tuple[Path, ...]]:
    requested_pids = tuple(sorted(set(pids)))
    if not requested_pids:
        return {}

    empty_result: dict[int, tuple[Path, ...]] = dict.fromkeys(
        requested_pids, ()
    )
    try:
        result = subprocess.run(
            [
                "/usr/sbin/lsof",
                "-nP",
                "-Fpn",
                "-p",
                ",".join(str(pid) for pid in requested_pids),
            ],
            capture_output=True,
            text=True,
            timeout=1.5,
        )
        output = result.stdout
    except (OSError, subprocess.TimeoutExpired):
        return empty_result

    requested_pid_set = frozenset(requested_pids)
    session_root = (home / ".codex" / "sessions").resolve()
    session_paths: dict[int, set[Path]] = {
        pid: set() for pid in requested_pids
    }
    current_pid: int | None = None
    for line in output.splitlines():
        if line.startswith("p"):
            try:
                parsed_pid = int(line[1:])
            except ValueError:
                current_pid = None
                continue
            current_pid = (
                parsed_pid if parsed_pid in requested_pid_set else None
            )
            continue
        if current_pid is None or not line.startswith("n"):
            continue
        path_text = line[1:]
        if not path_text.endswith(".jsonl"):
            continue
        try:
            session_path = Path(path_text).resolve()
        except OSError:
            continue
        if session_root == session_path.parent or session_root in session_path.parents:
            session_paths[current_pid].add(session_path)
    return {
        pid: tuple(sorted(session_paths[pid]))
        for pid in requested_pids
    }


def read_codex_session_thread_id(
    session_path: Path,
) -> str | None:
    try:
        with session_path.open(encoding="utf-8") as session_file:
            for _ in range(4):
                line = session_file.readline()
                if not line:
                    break
                raw_record = cast(object, json.loads(line))
                if not isinstance(raw_record, dict):
                    continue
                record = cast(dict[str, object], raw_record)
                if record.get("type") != "session_meta":
                    continue
                payload = record.get("payload")
                if not isinstance(payload, dict):
                    continue
                payload_map = cast(dict[str, object], payload)
                for key in ("session_id", "id", "parent_thread_id"):
                    value = payload_map.get(key)
                    if isinstance(value, str) and value:
                        return value.lower()
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    return None


def read_codex_thread_titles(
    thread_ids: frozenset[str], home: Path = HOME
) -> dict[str, str]:
    if not thread_ids:
        return {}
    database_path = home / ".codex" / "state_5.sqlite"
    if not database_path.is_file():
        return {}

    placeholders = ",".join("?" for _ in thread_ids)
    query = (
        "SELECT id, title FROM threads "
        f"WHERE id IN ({placeholders}) AND archived = 0"
    )
    try:
        connection = sqlite3.connect(
            f"file:{database_path}?mode=ro&immutable=1", uri=True
        )
        try:
            cursor = connection.execute(query, tuple(sorted(thread_ids)))
            return {
                thread_id.lower(): title
                for thread_id, title in cast(list[tuple[str, str]], cursor.fetchall())
                if thread_id and title.strip()
            }
        finally:
            connection.close()
    except (OSError, sqlite3.Error):
        return {}


def resolve_codex_child_title(
    process: Process,
    runtime: Runtime,
    session_paths: tuple[Path, ...],
    home: Path = HOME,
) -> TitleResolution:
    if is_codex_desktop_host(process):
        return TitleResolution("Desktop host")
    if process.executable != "codex":
        return TitleResolution(codex_desktop_helper_role(process))

    handle_ids = frozenset(
        thread_id
        for path in session_paths
        if (thread_id := read_codex_session_thread_id(path)) is not None
    )
    session_titles = tuple(
        sorted(
            {
                sanitized
                for title in read_codex_thread_titles(handle_ids, home).values()
                if (sanitized := sanitize_text(title))
            }
        )
    )
    if len(session_titles) == 1:
        return TitleResolution(session_titles[0], session_titles)
    if session_titles:
        return TitleResolution(
            f"Session worker · {len(session_titles)} linked sessions",
            session_titles,
        )
    if handle_ids:
        return TitleResolution("Session worker (title unavailable)")

    descendants = descendant_processes(process, runtime)
    if any(candidate.executable == "codex" for candidate in descendants):
        return TitleResolution("Session renderer (unattributed)")
    if process.ppid == runtime.root.pid and process.executable == "codex":
        return TitleResolution("Codex worker")
    return TitleResolution("Generic worker")




def mcp_instance_for_root(
    root: Process,
    children_by_parent: dict[int, tuple[Process, ...]],
) -> McpInstance | None:
    processes = process_subtree(root, children_by_parent)
    families = tuple(
        sorted(
            {
                family
                for process in processes
                if (family := classify_mcp(process.command)) is not None
            }
        )
    )
    if not families:
        return None
    family = families[0] if len(families) == 1 else "Mixed MCP"
    return McpInstance(family, root, processes)


def group_mcp_instances(
    instances: Iterable[McpInstance],
) -> dict[str, tuple[McpInstance, ...]]:
    grouped: defaultdict[str, list[McpInstance]] = defaultdict(list)
    for instance in instances:
        grouped[instance.family].append(instance)
    return {
        family: tuple(
            sorted(
                family_instances,
                key=lambda instance: (
                    -instance.totals.rss_bytes,
                    -instance.totals.cpu_percent,
                    instance.root.pid,
                ),
            )
        )
        for family, family_instances in sorted(
            grouped.items(),
            key=lambda item: (
                -totals(
                    process
                    for instance in item[1]
                    for process in instance.processes
                ).rss_bytes,
                item[0],
            ),
        )
    }


def codex_tree_process_label(process: Process) -> str:
    if process.executable in {"codex-code-mode-host", "bare-modifier-monitor"}:
        return codex_desktop_helper_role(process)
    return sanitize_text(process.executable or "unknown")


def append_process_tree(
    lines: list[str],
    process: Process,
    children_by_parent: dict[int, tuple[Process, ...]],
    prefix: str,
    label: str | None = None,
) -> None:
    direct_children = children_by_parent.get(process.pid, ())
    details = process_metrics_text(process)
    if direct_children:
        details += (
            f" · subtree {totals_text(totals(process_subtree(process, children_by_parent)))}"
        )
    lines.append(
        f"{prefix}{sanitize_text(label or codex_tree_process_label(process))} · {details}"
    )
    child_prefix = prefix + "--"
    for child in direct_children:
        append_process_tree(lines, child, children_by_parent, child_prefix)


def append_mcp_instances(
    lines: list[str],
    instances: tuple[McpInstance, ...],
    children_by_parent: dict[int, tuple[Process, ...]],
    prefix: str,
) -> None:
    if not instances:
        return
    instance_processes = tuple(
        process for instance in instances for process in instance.processes
    )
    noun = "instance" if len(instances) == 1 else "instances"
    lines.append(
        f"{prefix}MCP instances · {len(instances)} {noun}"
        + f" · {totals_text(totals(instance_processes))}"
    )
    family_prefix = prefix + "--"
    instance_prefix = family_prefix + "--"
    for family, family_instances in group_mcp_instances(instances).items():
        family_processes = tuple(
            process
            for instance in family_instances
            for process in instance.processes
        )
        family_noun = "instance" if len(family_instances) == 1 else "instances"
        lines.append(
            f"{family_prefix}{family} · {len(family_instances)} {family_noun}"
            + f" · {totals_text(totals(family_processes))}"
        )
        for instance in family_instances:
            append_process_tree(
                lines,
                instance.root,
                children_by_parent,
                instance_prefix,
            )


def append_worker_process_groups(
    lines: list[str], group: ProcessGroup, prefix: str
) -> None:
    worker = group.process
    if worker is None or not group.children:
        return
    children_by_parent = child_process_index((worker, *group.children))
    instances: list[McpInstance] = []
    support_roots: list[Process] = []
    for root in children_by_parent.get(worker.pid, ()):
        instance = mcp_instance_for_root(root, children_by_parent)
        if instance is None:
            support_roots.append(root)
        else:
            instances.append(instance)
    append_mcp_instances(lines, tuple(instances), children_by_parent, prefix)
    if support_roots:
        support_processes = tuple(
            process
            for root in support_roots
            for process in process_subtree(root, children_by_parent)
        )
        lines.append(f"{prefix}Support · {totals_text(totals(support_processes))}")
        support_prefix = prefix + "--"
        for root in support_roots:
            append_process_tree(
                lines,
                root,
                children_by_parent,
                support_prefix,
            )


def codex_desktop_child_groups(
    runtime: Runtime, home: Path
) -> tuple[ProcessGroup, ...]:
    candidate_pids = tuple(
        process.pid
        for process in runtime.processes
        if process.ppid == runtime.root.pid and process.executable == "codex"
    )
    session_handles_by_pid = read_codex_session_handles_by_pid(
        candidate_pids, home
    )
    groups: list[ProcessGroup] = []
    groups.append(
        ProcessGroup(
            process=runtime.root,
            label="Desktop host",
            title_resolution=TitleResolution("Desktop host"),
            children=(),
        )
    )
    for process in runtime.processes:
        if process.ppid != runtime.root.pid or process.pid == runtime.root.pid:
            continue
        children = tuple(
            sorted(
                descendant_processes(process, runtime),
                key=lambda candidate: (
                    -candidate.rss_bytes,
                    -candidate.cpu_percent,
                    candidate.pid,
                ),
            )
        )
        if is_codex_desktop_host(process):
            resolution = TitleResolution("Desktop host")
        elif process.executable == "codex":
            session_paths = session_handles_by_pid.get(process.pid, ())
            resolution = resolve_codex_child_title(
                process, runtime, session_paths, home
            )
        else:
            resolution = TitleResolution(codex_desktop_helper_role(process))
        groups.append(
            ProcessGroup(
                process=process,
                label=resolution.label,
                title_resolution=resolution,
                children=children,
            )
        )
    return tuple(
        sorted(
            groups,
            key=lambda group: (
                0 if group.process is not None and is_codex_desktop_host(group.process) else 1,
                -group.totals.rss_bytes,
                -group.totals.cpu_percent,
                group.process.pid if group.process is not None else 0,
            ),
        )
    )


def is_codex_session_group(group: ProcessGroup) -> bool:
    resolution = group.title_resolution
    return resolution is not None and (
        bool(resolution.session_titles)
        or resolution.label.startswith("Session worker")
    )


def append_codex_session_worker(
    lines: list[str], group: ProcessGroup, prefix: str
) -> None:
    worker = group.process
    resolution = group.title_resolution
    if worker is None or resolution is None:
        return
    if resolution.session_titles:
        title_count = len(resolution.session_titles)
        title_noun = "session" if title_count == 1 else "sessions"
        source = "session-file" if title_count == 1 else "session-files"
        lines.append(
            f"{prefix}Sessions on worker PID {worker.pid} · {title_count} linked {title_noun}"
            + f" · resources shared · titles verified by state+{source} | color=gray"
        )
        for title in resolution.session_titles:
            lines.append(f"{prefix}Session: {title} | color=gray")
        worker_label = "Worker"
    else:
        worker_label = resolution.label

    details = process_metrics_text(worker)
    if group.children:
        details += f" · subtree {totals_text(group.totals)}"
    lines.append(f"{prefix}{sanitize_text(worker_label)} · {details}")
    append_worker_process_groups(lines, group, prefix + "--")


def append_other_codex_desktop_processes(
    lines: list[str], groups: tuple[ProcessGroup, ...], prefix: str
) -> None:
    if not groups:
        return
    owned_processes = tuple(
        process
        for group in groups
        for process in (
            *((group.process,) if group.process is not None else ()),
            *group.children,
        )
    )
    root_noun = "root" if len(groups) == 1 else "roots"
    lines.append(
        f"{prefix}Other Codex Desktop processes · {len(groups)} {root_noun}"
        + f" · {totals_text(totals(owned_processes))}"
    )
    root_prefix = prefix + "--"
    for group in groups:
        process = group.process
        if process is None:
            continue
        children_by_parent = child_process_index((process, *group.children))
        if process.executable == "codex":
            label = "Codex process"
        elif process.executable in {"codex-code-mode-host", "bare-modifier-monitor"}:
            label = group.label
        else:
            label = codex_tree_process_label(process)
        append_process_tree(
            lines,
            process,
            children_by_parent,
            root_prefix,
            label,
        )


def append_codex_desktop_details(
    lines: list[str], runtime: Runtime, prefix: str, home: Path = HOME
) -> None:
    lines.append(
        f"{prefix}Codex Desktop shared process tree · {totals_text(runtime.totals)}"
        + " · chats/tabs are not resource-attributed. | color=gray"
    )
    lines.append(f"{prefix}Desktop host · {process_metrics_text(runtime.root)}")

    groups = codex_desktop_child_groups(runtime, home)
    session_groups = tuple(
        group
        for group in groups
        if group.process is not None
        and group.process.pid != runtime.root.pid
        and is_codex_session_group(group)
    )
    other_groups = tuple(
        group
        for group in groups
        if group.process is not None
        and group.process.pid != runtime.root.pid
        and not is_codex_session_group(group)
    )
    for group in session_groups:
        append_codex_session_worker(lines, group, prefix)
    append_other_codex_desktop_processes(lines, other_groups, prefix)


def append_runtime_lines(
    lines: list[str], runtime: Runtime, prefix: str = "--", home: Path = HOME
) -> None:
    runtime_totals = runtime.totals
    child_prefix = prefix + "--"
    shared_codex = runtime.adapter.key == "codex" and is_codex_desktop_host(
        runtime.root
    )
    detail_prefix = prefix if shared_codex else child_prefix
    family_prefix = detail_prefix + "--"

    if shared_codex:
        append_codex_desktop_details(lines, runtime, detail_prefix, home)
    else:
        lines.append(
            f"{prefix}{sanitize_text(runtime.label)} · {totals_text(runtime_totals)}"
        )

    mcp_processes = runtime.mcp_processes
    if mcp_processes and not shared_codex:
        lines.append(
            f"{detail_prefix}MCP subtotal · {totals_text(totals(mcp_processes))}"
        )
        for family, family_processes in group_mcp(mcp_processes).items():
            oldest = max(process.elapsed_seconds for process in family_processes)
            lines.append(
                f"{family_prefix}{family} · {totals_text(totals(family_processes))}"
                + f" · oldest {fmt_age(oldest)}"
            )

    non_mcp_processes = tuple(
        process for process in runtime.processes if not classify_mcp(process.command)
    )
    if non_mcp_processes and not shared_codex:
        lines.append(
            f"{child_prefix}Other owned processes · {totals_text(totals(non_mcp_processes))}"
        )

    nested_agents = tuple(
        process
        for process in runtime.processes
        if process.pid != runtime.root.pid
        and agent_adapter(process) is not None
        and not (
            shared_codex
            and (nested_adapter := agent_adapter(process)) is not None
            and nested_adapter.key == "codex"
        )
    )
    if nested_agents:
        nested_names: defaultdict[str, int] = defaultdict(int)
        for process in nested_agents:
            nested_adapter = agent_adapter(process)
            if nested_adapter:
                nested_names[nested_adapter.label] += 1
        summary = ", ".join(
            f"{name} {count}" for name, count in sorted(nested_names.items())
        )
        lines.append(
            f"{detail_prefix}Nested agent processes: {summary} | color=gray"
        )

    if not shared_codex:
        tty = runtime.root.tty or "none"
        lines.append(
            f"{child_prefix}Root PID {runtime.root.pid} · TTY {tty}"
            + f" · age {fmt_age(runtime.root.elapsed_seconds)} | color=gray"
        )



def is_collapsible_background(runtime: Runtime) -> bool:
    return (
        runtime.root.tty is None
        and not runtime.mcp_processes
        and not is_codex_desktop_host(runtime.root)
    )


def render(
    rows: dict[int, Process],
    home: Path = HOME,
    now: str | None = None,
    ai_input_status: AiInputStatus | None = None,
    spotify_status: SpotifyStatus | None = None,
) -> str:
    runtimes, unattributed_mcp = build_runtimes(rows, home)
    runtime_processes = tuple(process for runtime in runtimes for process in runtime.processes)
    overall = totals((*runtime_processes, *unattributed_mcp))
    color = title_color(overall.cpu_percent, overall.rss_bytes)
    ai_input_title = ""
    if ai_input_status is not None:
        healthy, total = ai_input_counts(ai_input_status)
        count_text = f"{healthy}/{total}" if total else "?"
        ai_input_title = f" · API {count_text}"
        if ai_input_status.health == "degraded":
            color = "red"
        elif ai_input_status.health == "unreachable" and color == "green":
            color = "orange"
    spotify_title = ""
    if spotify_status is not None and spotify_status.health == "ready":
        if spotify_status.is_ad:
            spotify_title = " · SP ad"
            if color == "green":
                color = "orange"
        elif spotify_status.playback == "playing":
            spotify_title = " · SP play"
        elif spotify_status.playback == "paused":
            spotify_title = " · SP pause"
    lines = [
        f"AI {len(runtimes)} · CPU {fmt_cpu(overall.cpu_percent)}"
        f" · {fmt_bytes(overall.rss_bytes)}{ai_input_title}{spotify_title} | color={color}",
        "---",
        "Read-only agent process inventory | color=gray",
        f"Updated: {now or time.strftime('%H:%M:%S')} · refresh {REFRESH_SECONDS}s | color=gray",
        "CPU is recent; 100% equals one logical core. | color=gray",
        "RSS is summed per process; shared pages may be counted more than once. | color=gray",
        "---",
    ]

    if spotify_status is not None:
        append_spotify_lines(lines, spotify_status)

    if ai_input_status is not None:
        append_ai_input_lines(lines, ai_input_status)

    by_agent: dict[str, list[Runtime]] = defaultdict(list)
    for runtime in runtimes:
        by_agent[runtime.adapter.key].append(runtime)

    for adapter in AGENT_ADAPTERS:
        agent_runtimes = by_agent.get(adapter.key)
        if not agent_runtimes:
            continue
        agent_totals = totals(
            process
            for runtime in agent_runtimes
            for process in runtime.processes
        )
        runtime_noun = "runtime" if len(agent_runtimes) == 1 else "runtimes"
        lines.append(
            f"{adapter.label}: {len(agent_runtimes)} {runtime_noun} · {totals_text(agent_totals)}"
        )

        foreground_runtimes = [
            runtime for runtime in agent_runtimes if not is_collapsible_background(runtime)
        ]
        background_runtimes = [
            runtime for runtime in agent_runtimes if is_collapsible_background(runtime)
        ]

        for runtime in foreground_runtimes:
            append_runtime_lines(lines, runtime, home=home)

        if background_runtimes:
            background_totals = totals(
                process
                for runtime in background_runtimes
                for process in runtime.processes
            )
            lines.append(
                f"--Background runtimes: {len(background_runtimes)} · {totals_text(background_totals)}"
            )
            for runtime in background_runtimes:
                append_runtime_lines(lines, runtime, prefix="----", home=home)
        lines.append("---")

    if unattributed_mcp:
        unattributed_totals = totals(unattributed_mcp)
        lines.append(
            f"Unattributed MCP · {totals_text(unattributed_totals)} | color=orange"
        )
        for family, family_processes in group_mcp(unattributed_mcp).items():
            lines.append(f"--{family} · {totals_text(totals(family_processes))}")
        lines.append("These MCP processes have no recognized agent ancestor. | color=gray")
        lines.append("---")

    if not runtimes and not unattributed_mcp:
        lines.append("No active supported agent runtimes or MCP processes. | color=gray")
        lines.append("---")

    lines.append(
        "Open Activity Monitor | bash=/usr/bin/open param1=-a param2='Activity Monitor' terminal=false"
    )
    return "\n".join(lines)


def main() -> None:
    if sys.argv[1:] == ["spotify-toggle"]:
        toggle_spotify_playback()
        return
    ai_input_status = collect_ai_input_status()
    spotify_status = collect_spotify_status()
    try:
        rows = ps_rows()
        print(
            render(
                rows,
                ai_input_status=ai_input_status,
                spotify_status=spotify_status,
            )
        )
    except Exception as error:
        print("AI ? | color=red")
        print("---")
        print(f"Process scan failed: {sanitize_text(str(error))} | color=red")


if __name__ == "__main__":
    main()
