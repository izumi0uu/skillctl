"""macOS menu-bar monitor for agents, model health, and Spotify Web.

Every process is assigned to at most one top-level agent runtime by ancestry.
Session titles are shown only when a reliable PID/TTY mapping exists. The script
never sends signals, reads process environments, or writes agent runtime state.
It stores only its own model-status, subscription-quota, notification, and
Spotify mute state; rotating AI.INPUT.IM credentials remain in macOS Keychain.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import sqlite3
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict, deque
from collections.abc import Iterable
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import cast

from . import ai_input_auth

try:
    import fcntl
except ImportError:  # pragma: no cover - macOS and the verifier have fcntl.
    fcntl = None  # type: ignore[assignment]

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
        / "personal-xbar"
        / "ai-input-status.json",
    )
)
AI_INPUT_SUBSCRIPTIONS_ENABLED = (
    os.environ.get("AI_INPUT_SUBSCRIPTIONS_ENABLED", "1") != "0"
)
AI_INPUT_SUBSCRIPTIONS_DIRECT_ENABLED = (
    os.environ.get("AI_INPUT_SUBSCRIPTIONS_DIRECT", "1") != "0"
)
AI_INPUT_SUBSCRIPTIONS_ORIGIN = "https://ai.input.im/"
AI_INPUT_API_ORIGIN = "https://ai.input.im"
AI_INPUT_API_BASE = f"{AI_INPUT_API_ORIGIN}/api/v1"
AI_INPUT_API_TIMEOUT_SECONDS = 4.0
AI_INPUT_API_BODY_LIMIT = 1024 * 1024
AI_INPUT_REFRESH_LEAD_SECONDS = 120
AI_INPUT_REFRESH_LOCK_FILE = Path(
    os.environ.get(
        "AI_INPUT_REFRESH_LOCK_FILE",
        HOME
        / "Library"
        / "Caches"
        / "skillctl"
        / "personal-xbar"
        / ".ai-input-refresh.lock",
    )
)
AI_INPUT_SUBSCRIPTIONS_TAB_PREFIX = "https://ai.input.im/subscriptions"
AI_INPUT_SUBSCRIPTIONS_PAGE_URL = os.environ.get(
    "AI_INPUT_SUBSCRIPTIONS_PAGE_URL", "https://ai.input.im/subscriptions"
)
AI_INPUT_SUBSCRIPTIONS_BROWSER_APP = os.environ.get(
    "AI_INPUT_SUBSCRIPTIONS_BROWSER_APP", "Google Chrome"
)
AI_INPUT_SUBSCRIPTIONS_CACHE_SECONDS = 55
AI_INPUT_SUBSCRIPTIONS_SCRIPT_TIMEOUT_SECONDS = 5.0
AI_INPUT_SUBSCRIPTIONS_STATE_FILE = Path(
    os.environ.get(
        "AI_INPUT_SUBSCRIPTIONS_STATE_FILE",
        HOME
        / "Library"
        / "Caches"
        / "skillctl"
        / "personal-xbar"
        / "ai-input-subscriptions.json",
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
        / "personal-xbar"
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
class SubscriptionQuota:
    period: str
    used_cents: int
    limit_cents: int
    reset_at: int | None = None


@dataclass(frozen=True)
class SubscriptionPlan:
    plan_id: str
    name: str
    status: str
    expires_at: int | None
    quotas: tuple[SubscriptionQuota, ...]
    quota_state: str = "available"


@dataclass(frozen=True)
class SubscriptionQuotaStatus:
    health: str
    plans: tuple[SubscriptionPlan, ...] = ()
    error: str | None = None
    source: str | None = None


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
            "User-Agent": "skillctl-personal-xbar/3.0.0",
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
        'with title "Personal xbar" subtitle "AI.INPUT.IM"'
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


class AiInputApiError(RuntimeError):
    """A bounded, redacted error from the direct AI.INPUT.IM API."""

    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind


class ExactAiInputRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Allow redirects only when they remain on the exact HTTPS origin."""

    def redirect_request(
        self,
        request: urllib.request.Request,
        fp: object,
        code: int,
        msg: str,
        newurl: str,
    ) -> urllib.request.Request | None:
        target = urllib.parse.urlsplit(urllib.parse.urljoin(request.full_url, newurl))
        try:
            target_port = target.port
        except ValueError:
            raise AiInputApiError("redirect", "AI INPUT API redirect was rejected") from None
        if (
            target.scheme.lower() != "https"
            or target.hostname != "ai.input.im"
            or target_port not in (None, 443)
            or target.username is not None
            or target.password is not None
        ):
            raise AiInputApiError("redirect", "AI INPUT API redirect was rejected")
        return super().redirect_request(request, fp, code, msg, newurl)


def read_ai_input_credentials() -> ai_input_auth.AiInputCredentials | None:
    return ai_input_auth.read_credentials()


def write_ai_input_credentials(credentials: ai_input_auth.AiInputCredentials) -> None:
    ai_input_auth.write_credentials(credentials)


def delete_ai_input_credentials() -> None:
    ai_input_auth.delete_credentials()


def ai_input_credentials_summary(now_epoch: int | None = None) -> dict[str, object]:
    now_value = int(time.time()) if now_epoch is None else now_epoch
    credentials = read_ai_input_credentials()
    return ai_input_auth.credentials_summary(credentials, now_value)


def api_request_json(
    path: str,
    access_token: str | None = None,
    *,
    method: str = "GET",
    body: dict[str, object] | None = None,
) -> object:
    if not path.startswith("/") or path.startswith("//"):
        raise AiInputApiError("request", "AI INPUT API path is invalid")
    url = f"{AI_INPUT_API_BASE}{path}"
    headers = {
        "Accept": "application/json",
        "User-Agent": "Personal-xbar/3",
    }
    encoded_body: bytes | None = None
    if body is not None:
        encoded_body = json.dumps(body, separators=(",", ":")).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"
    request = urllib.request.Request(
        url,
        data=encoded_body,
        headers=headers,
        method=method,
    )
    opener = urllib.request.build_opener(ExactAiInputRedirectHandler())
    try:
        response = opener.open(request, timeout=AI_INPUT_API_TIMEOUT_SECONDS)
        with response:
            status_code = int(getattr(response, "status", 200))
            content_length = response.headers.get("Content-Length")
            if content_length:
                try:
                    if int(content_length) > AI_INPUT_API_BODY_LIMIT:
                        raise AiInputApiError("response", "AI INPUT API response is too large")
                except ValueError:
                    pass
            raw_body = response.read(AI_INPUT_API_BODY_LIMIT + 1)
    except AiInputApiError:
        raise
    except urllib.error.HTTPError as error:
        if error.code == 401:
            raise AiInputApiError("unauthorized", "AI INPUT API authorization expired") from None
        if error.code in (403, 407):
            raise AiInputApiError("forbidden", "AI INPUT API access was denied") from None
        raise AiInputApiError("http", f"AI INPUT API returned HTTP {error.code}") from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise AiInputApiError("network", "AI INPUT API network request failed") from None
    if status_code == 401:
        raise AiInputApiError("unauthorized", "AI INPUT API authorization expired")
    if status_code < 200 or status_code >= 300:
        raise AiInputApiError("http", f"AI INPUT API returned HTTP {status_code}")
    if len(raw_body) > AI_INPUT_API_BODY_LIMIT:
        raise AiInputApiError("response", "AI INPUT API response is too large")
    try:
        return json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise AiInputApiError("response", "AI INPUT API returned invalid JSON") from None


def _unwrap_ai_input_api_payload(payload: object) -> object:
    if not isinstance(payload, dict) or "code" not in payload:
        return payload
    code = payload.get("code")
    if code not in (0, "0", "success", "SUCCESS"):
        if code in (401, "401", "UNAUTHORIZED"):
            raise AiInputApiError("unauthorized", "AI INPUT API authorization expired")
        raise AiInputApiError("api", "AI INPUT API returned an error")
    return payload.get("data")


def _parse_api_epoch(value: object) -> int | None:
    integer = numeric_int(value)
    if integer is not None:
        return integer if integer > 0 else None
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return int(parsed.timestamp())
    except (TypeError, ValueError, OverflowError):
        return None


def _local_timezone_name() -> str | None:
    candidate = os.environ.get("TZ", "").strip()
    if not candidate:
        try:
            localtime = os.path.realpath("/etc/localtime")
            marker = "/zoneinfo/"
            if marker in localtime:
                candidate = localtime.split(marker, 1)[1]
        except OSError:
            candidate = ""
    if re.fullmatch(r"[A-Za-z0-9._+-]+(?:/[A-Za-z0-9._+-]+)+", candidate):
        return candidate
    return None


def _api_subscription_request_path() -> str:
    timezone_name = _local_timezone_name()
    if not timezone_name:
        return "/subscriptions"
    return "/subscriptions?timezone=" + urllib.parse.quote(timezone_name, safe="")


def _refresh_lock_path(state_file: Path) -> Path:
    configured = AI_INPUT_REFRESH_LOCK_FILE
    if configured == Path(
        os.environ.get(
            "AI_INPUT_REFRESH_LOCK_FILE",
            HOME
            / "Library"
            / "Caches"
            / "skillctl"
            / "personal-xbar"
            / ".ai-input-refresh.lock",
        )
    ):
        return state_file.parent / ".ai-input-refresh.lock"
    return configured


_AI_INPUT_REFRESH_THREAD_LOCK = threading.Lock()


@contextmanager
def ai_input_refresh_lock(state_file: Path) -> Iterable[None]:
    lock_path = _refresh_lock_path(state_file)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.parent.chmod(0o700)
    with _AI_INPUT_REFRESH_THREAD_LOCK:
        try:
            lock_file = lock_path.open("a+")
        except OSError as error:
            raise AiInputApiError("lock", "AI INPUT refresh lock is unavailable") from error
        try:
            lock_path.chmod(0o600)
            if fcntl is not None:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            yield
        finally:
            if fcntl is not None:
                try:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
                except OSError:
                    pass
            lock_file.close()


def refresh_ai_input_credentials(
    current: ai_input_auth.AiInputCredentials,
    state_file: Path,
    now_epoch: int,
    *,
    force: bool,
) -> ai_input_auth.AiInputCredentials:
    with ai_input_refresh_lock(state_file):
        latest = read_ai_input_credentials()
        if latest is None:
            raise ai_input_auth.MissingCredentials(
                "AI.INPUT.IM credentials are not configured"
            )
        if latest.access_token != current.access_token:
            if not force or not ai_input_auth.credentials_need_refresh(
                latest, now_epoch, AI_INPUT_REFRESH_LEAD_SECONDS
            ):
                return latest
        payload = _unwrap_ai_input_api_payload(
            api_request_json(
                "/auth/refresh",
                method="POST",
                body={"refresh_token": latest.refresh_token},
            )
        )
        if not isinstance(payload, dict):
            raise AiInputApiError("refresh", "AI INPUT refresh response is invalid")
        expires_in = numeric_int(payload.get("expires_in"))
        if expires_in is None or expires_in <= 0:
            raise AiInputApiError("refresh", "AI INPUT refresh response has no expiry")
        try:
            refreshed = ai_input_auth.make_credentials(
                payload.get("access_token"),
                payload.get("refresh_token"),
                now_epoch + expires_in,
            )
            write_ai_input_credentials(refreshed)
        except ai_input_auth.AuthError as error:
            raise AiInputApiError("refresh", "AI INPUT refresh response is invalid") from error
        return refreshed


def parse_subscription_api_payload(
    payload: object,
    now_epoch: int | None = None,
) -> SubscriptionQuotaStatus:
    raw = _unwrap_ai_input_api_payload(payload)
    if isinstance(raw, dict) and isinstance(raw.get("subscriptions"), list):
        raw_subscriptions = raw["subscriptions"]
    elif isinstance(raw, list):
        raw_subscriptions = raw
    else:
        raise ValueError("AI INPUT API returned no subscriptions")
    now_value = int(time.time()) if now_epoch is None else now_epoch
    plans: list[SubscriptionPlan] = []
    seen_ids: set[str] = set()
    for raw_subscription in raw_subscriptions:
        if not isinstance(raw_subscription, dict):
            raise ValueError("AI INPUT API returned an invalid subscription")
        raw_id = raw_subscription.get("id")
        if isinstance(raw_id, bool) or not isinstance(raw_id, (str, int)):
            raise ValueError("AI INPUT subscription has no id")
        plan_id = sanitize_text(str(raw_id), 100)
        if not plan_id or plan_id in seen_ids:
            raise ValueError("AI INPUT API returned duplicate subscriptions")
        raw_status = raw_subscription.get("status")
        if not isinstance(raw_status, str) or not raw_status.strip():
            raise ValueError("AI INPUT subscription has no status")
        status = normalize_subscription_plan_status(raw_status)
        expires_at = _parse_api_epoch(raw_subscription.get("expires_at"))
        if status == "active" and expires_at is not None and expires_at <= now_value:
            status = "inactive"
        group = raw_subscription.get("group")
        group_dict = group if isinstance(group, dict) else {}
        name_value = group_dict.get("name", raw_subscription.get("group_name"))
        if not isinstance(name_value, str) or not name_value.strip():
            name_value = raw_subscription.get("name")
        if not isinstance(name_value, str) or not name_value.strip():
            raise ValueError("AI INPUT subscription has no plan name")
        quotas: list[SubscriptionQuota] = []
        for period, usage_key, limit_key, window_key, window_seconds in (
            ("daily", "daily_usage_usd", "daily_limit_usd", "daily_window_start", 86400),
            ("weekly", "weekly_usage_usd", "weekly_limit_usd", "weekly_window_start", 604800),
            ("monthly", "monthly_usage_usd", "monthly_limit_usd", "monthly_window_start", 2592000),
        ):
            limit_value = group_dict.get(limit_key, raw_subscription.get(limit_key))
            limit_cents = usd_to_cents(limit_value)
            if limit_cents is None or limit_cents <= 0:
                continue
            used_cents = usd_to_cents(raw_subscription.get(usage_key))
            if used_cents is None or used_cents < 0:
                raise ValueError("AI INPUT subscription quota has invalid usage")
            reset_at = _parse_api_epoch(raw_subscription.get(window_key))
            if reset_at is not None:
                reset_at += window_seconds
                if expires_at is not None:
                    reset_at = min(reset_at, expires_at)
            quotas.append(
                SubscriptionQuota(
                    period=period,
                    used_cents=used_cents,
                    limit_cents=limit_cents,
                    reset_at=reset_at,
                )
            )
        quota_state = "available" if quotas else (
            "unlimited" if group or any(
                key in raw_subscription
                for key in ("daily_limit_usd", "weekly_limit_usd", "monthly_limit_usd")
            ) else "unavailable"
        )
        plans.append(
            SubscriptionPlan(
                plan_id=plan_id,
                name=sanitize_text(name_value, 80),
                status=status,
                expires_at=expires_at,
                quotas=tuple(quotas),
                quota_state=quota_state,
            )
        )
        seen_ids.add(plan_id)
    return SubscriptionQuotaStatus(
        health="ready",
        plans=tuple(plans),
        source="api",
    )


def _direct_subscription_status(
    state_file: Path,
    now_epoch: int,
) -> SubscriptionQuotaStatus:
    try:
        credentials = read_ai_input_credentials()
    except ai_input_auth.MissingCredentials:
        credentials = None
    except ai_input_auth.AuthError:
        return SubscriptionQuotaStatus(
            health="error", error="AI INPUT keychain unavailable", source="keychain"
        )
    if credentials is None:
        return SubscriptionQuotaStatus(health="not-configured", source="keychain")

    active_credentials = credentials
    try:
        if ai_input_auth.credentials_need_refresh(
            active_credentials, now_epoch, AI_INPUT_REFRESH_LEAD_SECONDS
        ):
            try:
                active_credentials = refresh_ai_input_credentials(
                    active_credentials, state_file, now_epoch, force=False
                )
            except AiInputApiError:
                if active_credentials.expires_at is None or active_credentials.expires_at <= now_epoch:
                    return SubscriptionQuotaStatus(
                        health="session-expired",
                        error="AI INPUT access token needs refresh",
                        source="api",
                    )
        try:
            payload = api_request_json(
                _api_subscription_request_path(), active_credentials.access_token
            )
        except AiInputApiError as error:
            if error.kind != "unauthorized":
                raise
            active_credentials = refresh_ai_input_credentials(
                active_credentials, state_file, now_epoch, force=True
            )
            payload = api_request_json(
                _api_subscription_request_path(), active_credentials.access_token
            )
        return parse_subscription_api_payload(payload, now_epoch=now_epoch)
    except ai_input_auth.AuthError:
        return SubscriptionQuotaStatus(
            health="error", error="AI INPUT keychain unavailable", source="keychain"
        )
    except AiInputApiError as error:
        if error.kind in {"unauthorized", "forbidden", "refresh"}:
            return SubscriptionQuotaStatus(
                health="session-expired",
                error="AI INPUT sign-in required; refresh token was rejected",
                source="api",
            )
        return SubscriptionQuotaStatus(
            health="error", error=str(error), source="api"
        )
    except ValueError as error:
        return SubscriptionQuotaStatus(
            health="error", error=sanitize_text(str(error), 140), source="api"
        )


def collect_subscription_quota_api_status(
    state_file: Path = AI_INPUT_SUBSCRIPTIONS_STATE_FILE,
    now_epoch: int | None = None,
) -> SubscriptionQuotaStatus:
    """Run the direct, browser-independent quota probe once."""

    return _direct_subscription_status(
        state_file,
        int(time.time()) if now_epoch is None else now_epoch,
    )


AI_INPUT_SUBSCRIPTIONS_JAVASCRIPT = r"""
(() => {
  /* The app renders data from its authenticated /api/v1/subscriptions request. */
  const clean = (value) => String(value || "").replace(/\s+/g, " ").trim();
  const parseExpiry = (text) => {
    const match = clean(text).match(
      /\(?(\d{4})[/-](\d{1,2})[/-](\d{1,2})\s+(\d{1,2}):(\d{2})\)?/
    );
    if (!match) return null;
    const milliseconds = new Date(
      Number(match[1]),
      Number(match[2]) - 1,
      Number(match[3]),
      Number(match[4]),
      Number(match[5])
    ).getTime();
    return Number.isFinite(milliseconds) ? Math.floor(milliseconds / 1000) : null;
  };
  const parseReset = (text, expiresAt) => {
    const value = clean(text);
    const days = Number((value.match(/(\d+)\s*d/i) || [0, 0])[1]);
    const hours = Number((value.match(/(\d+)\s*h/i) || [0, 0])[1]);
    const minutes = Number((value.match(/(\d+)\s*m/i) || [0, 0])[1]);
    if (!days && !hours && !minutes) return null;
    const resetAt = Math.floor(Date.now() / 1000) + days * 86400 + hours * 3600 + minutes * 60;
    return expiresAt && expiresAt < resetAt ? expiresAt : resetAt;
  };
  const periodFromLabel = (label) => {
    const value = clean(label).toLowerCase();
    if (/daily|\u6bcf\u65e5|\u65e5\u989d\u5ea6/.test(value)) return "daily";
    if (/weekly|\u6bcf\u5468|\u6bcf\u9031|\u5468\u989d\u5ea6|\u9031\u984d\u5ea6/.test(value)) return "weekly";
    if (/monthly|\u6bcf\u6708|\u6708\u989d\u5ea6/.test(value)) return "monthly";
    return null;
  };
  const parseDocument = (doc) => {
    if (!doc) return {ok: false, error: "loading"};
    const path = String(doc.location && doc.location.pathname || "");
    if (/\/login(?:\/|$)/i.test(path) || doc.querySelector('input[type="password"]')) {
      return {ok: false, error: "session-expired"};
    }
    const main = doc.querySelector("main");
    if (!main) return {ok: false, error: "loading"};
    const subscriptions = [];
    const headings = Array.from(main.querySelectorAll("h3"));
    for (let cardIndex = 0; cardIndex < headings.length; cardIndex++) {
      const heading = headings[cardIndex];
      const card = heading.closest("div.border");
      if (!card) continue;
      const name = clean(heading.textContent);
      if (!name) continue;
      const cardText = clean(card.innerText);
      const statusText = clean(card.querySelector("span.rounded-full")?.textContent);
      const expiresAt = parseExpiry(cardText);
      const quotas = [];
      const seenPeriods = new Set();
      for (const span of card.querySelectorAll("span")) {
        const amount = clean(span.textContent).match(
          /^\$\s*([\d,]+(?:\.\d+)?)\s*\/\s*\$\s*([\d,]+(?:\.\d+)?)$/
        );
        if (!amount) continue;
        const row = span.parentElement;
        const label = clean(row?.querySelector("span:first-child")?.textContent);
        const period = periodFromLabel(label);
        if (!period || seenPeriods.has(period)) continue;
        const resetText = clean(row?.parentElement?.querySelector("p")?.textContent);
        quotas.push({
          period,
          used_usd: amount[1].replace(/,/g, ""),
          limit_usd: amount[2].replace(/,/g, ""),
          reset_at: parseReset(resetText, expiresAt)
        });
        seenPeriods.add(period);
      }
      const quotaState = quotas.length
        ? "available"
        : (/\bunlimited\b|\u65e0\u9650|\u7121\u9650/i.test(cardText)
          ? "unlimited"
          : "unavailable");
      subscriptions.push({
        id: `dom:${cardIndex}:${name}:${expiresAt || "none"}`,
        name,
        status_text: statusText,
        expires_at: expiresAt,
        quota_state: quotaState,
        quotas
      });
    }
    if (subscriptions.length) return {ok: true, subscriptions, source: "rendered-page"};
    const text = clean(main.innerText);
    if (/no active subscriptions|\u6682\u65e0\u6709\u6548\u8ba2\u9605|\u66ab\u7121\u6709\u6548\u8a02\u95b1/i.test(text)) {
      return {ok: true, subscriptions: [], source: "rendered-page"};
    }
    return {ok: false, error: "loading"};
  };
  try {
    const selector = 'iframe[data-personal-xbar-quota-frame="1"]';
    const startedAtAttribute = "data-personal-xbar-quota-started-at";
    const nowMilliseconds = Date.now();
    let frame = document.querySelector(selector);
    let frameSnapshot = {ok: false, error: "loading"};
    if (frame) {
      try {
        if (frame.contentDocument) frameSnapshot = parseDocument(frame.contentDocument);
      } catch (_error) {
        frameSnapshot = {ok: false, error: "frame-unavailable"};
      }
    }
    const pageSnapshot = parseDocument(document);
    const snapshot = frameSnapshot.ok ? frameSnapshot : (
      pageSnapshot.ok ? pageSnapshot : (
        frameSnapshot.error === "session-expired" ? frameSnapshot : pageSnapshot
      )
    );
    const frameStartedAt = frame
      ? Number(frame.getAttribute(startedAtAttribute) || 0)
      : 0;
    const frameStale = !frameStartedAt || nowMilliseconds - frameStartedAt >= 30000;
    const shouldRefreshFrame = !frame || frameSnapshot.ok || frameStale ||
      frameSnapshot.error !== "loading";
    let appendFrame = false;
    if (!frame) {
      frame = document.createElement("iframe");
      frame.setAttribute("data-personal-xbar-quota-frame", "1");
      frame.setAttribute("aria-hidden", "true");
      frame.tabIndex = -1;
      frame.style.cssText = "position:absolute;width:1px;height:1px;left:-10000px;border:0;";
      appendFrame = true;
    }
    if (shouldRefreshFrame) {
      frame.setAttribute(startedAtAttribute, String(nowMilliseconds));
      frame.src = `/subscriptions?personal_xbar_quota=${nowMilliseconds}`;
    }
    if (appendFrame) {
      (document.body || document.documentElement).appendChild(frame);
    }
    return JSON.stringify(snapshot);
  } catch (error) {
    return JSON.stringify({ok: false, error: "render", detail: clean(error?.message || error)});
  }
})()
"""


def usd_to_cents(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    try:
        amount = Decimal(str(value))
        if not amount.is_finite() or amount < 0:
            return None
        rounded = amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except InvalidOperation:
        return None
    return int(rounded * 100)


def normalize_subscription_plan_status(value: object) -> str:
    if not isinstance(value, str):
        return "unknown"
    status = " ".join(value.split()).lower()
    if not status:
        return "unknown"
    if (
        re.search(r"\b(?:inactive|expired|cancelled|canceled|not\s+active)\b", status)
        or any(marker in status for marker in ("\u65e0\u6548", "\u7121\u6548", "\u8fc7\u671f", "\u904e\u671f", "\u5df2\u53d6\u6d88"))
    ):
        return "inactive"
    if re.search(r"\bactive\b", status) or any(
        marker in status for marker in ("\u6709\u6548", "\u751f\u6548", "\u4f7f\u7528\u4e2d")
    ):
        return "active"
    return "unknown"


def normalize_subscription_quota_state(value: object, has_quotas: bool) -> str:
    if has_quotas:
        return "available"
    if isinstance(value, str) and value.lower() == "unlimited":
        return "unlimited"
    return "unavailable"


def parse_subscription_quota_payload(payload: str) -> SubscriptionQuotaStatus:
    try:
        raw = json.loads(payload)
    except json.JSONDecodeError as error:
        raise ValueError("AI INPUT returned invalid subscription data") from error
    if not isinstance(raw, dict):
        raise ValueError("AI INPUT subscription data is not an object")
    if raw.get("ok") is not True:
        error_code = raw.get("error")
        if error_code == "session-expired":
            return SubscriptionQuotaStatus(health="session-expired")
        if error_code == "loading":
            return SubscriptionQuotaStatus(health="loading")
        detail = raw.get("detail")
        message = (
            sanitize_text(detail, 140)
            if isinstance(detail, str) and detail.strip()
            else "AI INPUT subscription page returned an error"
        )
        return SubscriptionQuotaStatus(health="error", error=message)

    raw_plans = raw.get("subscriptions")
    if not isinstance(raw_plans, list):
        raise ValueError("AI INPUT subscription data has no subscriptions")
    plans: list[SubscriptionPlan] = []
    seen_plan_ids: set[str] = set()
    for raw_plan in raw_plans:
        if not isinstance(raw_plan, dict):
            raise ValueError("AI INPUT subscription data contains an invalid plan")
        plan_id = raw_plan.get("id")
        name = raw_plan.get("name")
        status_value = raw_plan.get("status_text", raw_plan.get("status"))
        if not isinstance(plan_id, str) or not plan_id.strip():
            raise ValueError("AI INPUT subscription plan has no id")
        normalized_plan_id = sanitize_text(plan_id, 100)
        if normalized_plan_id in seen_plan_ids:
            raise ValueError("AI INPUT subscription data has duplicate plan ids")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("AI INPUT subscription plan has no name")
        if not isinstance(status_value, str) or not status_value.strip():
            raise ValueError("AI INPUT subscription plan has no status")
        raw_quotas = raw_plan.get("quotas")
        if not isinstance(raw_quotas, list):
            raise ValueError("AI INPUT subscription plan has invalid quotas")
        quotas: list[SubscriptionQuota] = []
        seen_periods: set[str] = set()
        for raw_quota in raw_quotas:
            if not isinstance(raw_quota, dict):
                raise ValueError("AI INPUT subscription quota is invalid")
            period = raw_quota.get("period")
            if period not in {"daily", "weekly", "monthly"} or period in seen_periods:
                raise ValueError("AI INPUT subscription quota has an invalid period")
            used_cents = usd_to_cents(raw_quota.get("used_usd"))
            limit_cents = usd_to_cents(raw_quota.get("limit_usd"))
            if used_cents is None or limit_cents is None or limit_cents <= 0:
                raise ValueError("AI INPUT subscription quota has invalid amounts")
            reset_at = numeric_int(raw_quota.get("reset_at"))
            quotas.append(
                SubscriptionQuota(
                    period=period,
                    used_cents=used_cents,
                    limit_cents=limit_cents,
                    reset_at=reset_at,
                )
            )
            seen_periods.add(period)
        plans.append(
            SubscriptionPlan(
                plan_id=normalized_plan_id,
                name=sanitize_text(name, 80),
                status=normalize_subscription_plan_status(status_value),
                expires_at=numeric_int(raw_plan.get("expires_at")),
                quotas=tuple(quotas),
                quota_state=normalize_subscription_quota_state(
                    raw_plan.get("quota_state"),
                    bool(quotas),
                ),
            )
        )
        seen_plan_ids.add(normalized_plan_id)
    return SubscriptionQuotaStatus(health="ready", plans=tuple(plans))


def subscription_quota_status_payload(
    status: SubscriptionQuotaStatus,
) -> dict[str, object]:
    return {
        "health": status.health,
        "error": status.error,
        "source": status.source,
        "plans": [
            {
                "id": plan.plan_id,
                "name": plan.name,
                "status": plan.status,
                "expires_at": plan.expires_at,
                "quota_state": plan.quota_state,
                "quotas": [
                    {
                        "period": quota.period,
                        "used_cents": quota.used_cents,
                        "limit_cents": quota.limit_cents,
                        "reset_at": quota.reset_at,
                    }
                    for quota in plan.quotas
                ],
            }
            for plan in status.plans
        ],
    }


def subscription_quota_status_from_state(
    state: dict[str, object],
) -> SubscriptionQuotaStatus | None:
    raw_status = state.get("status")
    if not isinstance(raw_status, dict):
        return None
    health = raw_status.get("health")
    if health not in {
        "ready",
        "not-running",
        "not-found",
        "automation-permission",
        "javascript-permission",
        "session-expired",
        "loading",
        "error",
        "not-configured",
    }:
        return None
    raw_plans = raw_status.get("plans")
    if not isinstance(raw_plans, list):
        return None
    plans: list[SubscriptionPlan] = []
    seen_plan_ids: set[str] = set()
    for raw_plan in raw_plans:
        if not isinstance(raw_plan, dict):
            return None
        plan_id = raw_plan.get("id")
        name = raw_plan.get("name")
        status_value = raw_plan.get("status")
        raw_quotas = raw_plan.get("quotas")
        if not all(isinstance(value, str) for value in (plan_id, name, status_value)):
            return None
        if cast(str, plan_id) in seen_plan_ids:
            return None
        if not isinstance(raw_quotas, list):
            return None
        quotas: list[SubscriptionQuota] = []
        seen_periods: set[str] = set()
        for raw_quota in raw_quotas:
            if not isinstance(raw_quota, dict):
                return None
            period = raw_quota.get("period")
            used_cents = numeric_int(raw_quota.get("used_cents"))
            limit_cents = numeric_int(raw_quota.get("limit_cents"))
            if (
                period not in {"daily", "weekly", "monthly"}
                or period in seen_periods
                or used_cents is None
                or used_cents < 0
                or limit_cents is None
                or limit_cents <= 0
            ):
                return None
            quotas.append(
                SubscriptionQuota(
                    period=period,
                    used_cents=used_cents,
                    limit_cents=limit_cents,
                    reset_at=numeric_int(raw_quota.get("reset_at")),
                )
            )
            seen_periods.add(cast(str, period))
        plans.append(
            SubscriptionPlan(
                plan_id=cast(str, plan_id),
                name=cast(str, name),
                status=normalize_subscription_plan_status(status_value),
                expires_at=numeric_int(raw_plan.get("expires_at")),
                quotas=tuple(quotas),
                quota_state=normalize_subscription_quota_state(
                    raw_plan.get("quota_state"),
                    bool(quotas),
                ),
            )
        )
        seen_plan_ids.add(cast(str, plan_id))
    error_value = raw_status.get("error")
    source_value = raw_status.get("source")
    return SubscriptionQuotaStatus(
        health=cast(str, health),
        plans=tuple(plans),
        error=error_value if isinstance(error_value, str) else None,
        source=source_value if isinstance(source_value, str) else None,
    )


def chrome_tab_apple_script(
    browser: str,
    url_prefix: str,
    javascript: str,
    tab_id: int | None = None,
) -> str:
    browser_literal = json.dumps(browser)
    prefix_literal = json.dumps(url_prefix)
    source_literal = json.dumps(compact_javascript(javascript))
    tab_id_literal = "null" if tab_id is None else json.dumps(str(tab_id))
    return "\n".join(
        (
            "(() => {",
            'ObjC.import("AppKit");',
            'ObjC.import("ScriptingBridge");',
            f"const browserName = {browser_literal};",
            f"const targetURL = {prefix_literal};",
            f"const source = {source_literal};",
            f"const requestedTabId = {tab_id_literal};",
            "const runningApps = $.NSWorkspace.sharedWorkspace.runningApplications;",
            "let browserFound = false;",
            "let matchingTabFound = false;",
            "let fallbackResult = null;",
            "for (let appIndex = 0; appIndex < runningApps.count; appIndex++) {",
            "const runningApp = runningApps.objectAtIndex(appIndex);",
            "const name = ObjC.unwrap(runningApp.localizedName);",
            "if (name !== browserName || Number(runningApp.activationPolicy) !== 0) continue;",
            "browserFound = true;",
            "const chrome = $.SBApplication.applicationWithProcessIdentifier(",
            "runningApp.processIdentifier",
            ");",
            'const windows = chrome.valueForKey("windows");',
            "for (let windowIndex = 0; windowIndex < windows.count; windowIndex++) {",
            'const tabs = windows.objectAtIndex(windowIndex).valueForKey("tabs");',
            "for (let tabIndex = 0; tabIndex < tabs.count; tabIndex++) {",
            "const targetTab = tabs.objectAtIndex(tabIndex);",
            'const url = ObjC.unwrap(targetTab.valueForKey("URL"));',
            'const uniqueId = String(ObjC.unwrap(targetTab.valueForKey("id")));',
            'const urlMatches = typeof url === "string" && (',
            "url === targetURL || url.startsWith(`${targetURL}?`) ||",
            "url.startsWith(`${targetURL}#`)",
            ");",
            "if (",
            "urlMatches &&",
            "(requestedTabId === null || uniqueId === requestedTabId)",
            ") {",
            "matchingTabFound = true;",
            "const rawResult = targetTab.performSelectorWithObject(",
            '"executeJavascript:",',
            "$(source)",
            ");",
            'const pageResult = rawResult ? String(ObjC.unwrap(rawResult)) : "";',
            'const combinedResult = `${uniqueId}\t${pageResult}`;',
            "if (requestedTabId !== null) return combinedResult;",
            "try {",
            "const parsedResult = JSON.parse(pageResult);",
            "if (parsedResult && parsedResult.ok === true) return combinedResult;",
            "} catch (_error) {}",
            "if (fallbackResult === null) fallbackResult = combinedResult;",
            "}",
            "}",
            "}",
            "}",
            "if (fallbackResult !== null) return fallbackResult;",
            'return browserFound && !matchingTabFound ? "__NO_TAB__" : "__NOT_RUNNING__";',
            "})()",
        )
    )


def classify_chrome_automation_error(detail: str) -> str:
    lowered = detail.lower()
    if (
        "not authorized to send apple events" in lowered
        or "not authorised to send apple events" in lowered
        or "-1743" in lowered
    ):
        return "automation-permission"
    if (
        "allow javascript from apple events" in lowered
        or "javascript 的功能已关闭" in detail
        or "允许 apple 事件中的 javascript" in lowered
    ):
        return "javascript-permission"
    return sanitize_text(detail, 140)


def run_chrome_tab_javascript(
    browser: str,
    url_prefix: str,
    javascript: str,
    timeout_seconds: float,
    tab_id: int | None = None,
) -> tuple[int | None, str | None, str | None]:
    script = chrome_tab_apple_script(
        browser,
        url_prefix,
        javascript,
        tab_id=tab_id,
    )
    try:
        completed = subprocess.run(
            ["/usr/bin/osascript", "-l", "JavaScript", "-e", script],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return None, None, sanitize_text(str(error), 140)
    output = completed.stdout.strip()
    if completed.returncode != 0:
        detail = completed.stderr.strip() or "Chrome JavaScript automation failed"
        return None, None, classify_chrome_automation_error(detail)
    if output == "__NOT_RUNNING__":
        return None, None, "not-running"
    if output == "__NO_TAB__":
        return None, None, "not-found"
    tab_id_text, separator, payload = output.partition("\t")
    try:
        result_tab_id = int(tab_id_text)
    except ValueError:
        return None, None, "Chrome returned an invalid tab identifier"
    if not separator:
        return None, None, "Chrome returned no page result"
    return result_tab_id, payload, None


def run_ai_input_subscriptions_javascript(
    javascript: str = AI_INPUT_SUBSCRIPTIONS_JAVASCRIPT,
) -> tuple[int | None, str | None, str | None]:
    return run_chrome_tab_javascript(
        AI_INPUT_SUBSCRIPTIONS_BROWSER_APP,
        AI_INPUT_SUBSCRIPTIONS_TAB_PREFIX,
        javascript,
        AI_INPUT_SUBSCRIPTIONS_SCRIPT_TIMEOUT_SECONDS,
    )


def subscription_quota_level(quota: SubscriptionQuota) -> int:
    if quota.used_cents >= quota.limit_cents:
        return 3
    if quota.used_cents * 100 >= quota.limit_cents * 90:
        return 2
    if quota.used_cents * 100 >= quota.limit_cents * 80:
        return 1
    return 0


def subscription_quota_key(plan: SubscriptionPlan, quota: SubscriptionQuota) -> str:
    return f"{plan.plan_id}:{quota.period}"


def subscription_quota_percent_label(quota: SubscriptionQuota) -> str:
    return f"{quota.used_cents * 100 // quota.limit_cents}%"


def format_subscription_quota_notice(
    plan: SubscriptionPlan,
    quota: SubscriptionQuota,
) -> str:
    return f"{plan.name} {quota.period} {subscription_quota_percent_label(quota)}"


def subscription_quota_notification_transition(
    previous: dict[str, object],
    status: SubscriptionQuotaStatus,
    checked_at: int,
) -> tuple[dict[str, object], tuple[str, ...]]:
    raw_previous_levels = previous.get("quota_levels")
    previous_levels = (
        {
            str(key): level
            for key, level in raw_previous_levels.items()
            if isinstance(key, str)
            and isinstance(level, int)
            and not isinstance(level, bool)
            and 0 <= level <= 3
        }
        if isinstance(raw_previous_levels, dict)
        else {}
    )
    next_levels = dict(previous_levels)
    notifications: list[str] = []
    if status.health == "ready":
        current_levels: dict[str, int] = {}
        alerts: list[tuple[int, SubscriptionPlan, SubscriptionQuota]] = []
        recoveries: list[tuple[SubscriptionPlan, SubscriptionQuota]] = []
        for plan in status.plans:
            if plan.status != "active":
                continue
            for quota in plan.quotas:
                key = subscription_quota_key(plan, quota)
                level = subscription_quota_level(quota)
                previous_level = previous_levels.get(key, 0)
                current_levels[key] = level
                if level > previous_level:
                    alerts.append((level, plan, quota))
                elif level == 0 and previous_level > 0:
                    recoveries.append((plan, quota))
        next_levels = current_levels
        if alerts:
            highest_level = max(item[0] for item in alerts)
            threshold = {1: "80%", 2: "90%", 3: "exhausted"}[highest_level]
            details = ", ".join(
                format_subscription_quota_notice(plan, quota)
                for _level, plan, quota in alerts
            )
            notifications.append(f"Quota {threshold}: {details}")
        if recoveries:
            details = ", ".join(
                format_subscription_quota_notice(plan, quota)
                for plan, quota in recoveries
            )
            notifications.append(f"Quota reset: {details}")

    return (
        {
            "schema_version": 1,
            "checked_at": checked_at,
            "health": status.health,
            "quota_levels": next_levels,
            "status": subscription_quota_status_payload(status),
        },
        tuple(notifications),
    )


def send_subscription_quota_notification(message: str) -> None:
    notifications_enabled = os.environ.get(
        "AI_INPUT_SUBSCRIPTIONS_NOTIFICATIONS",
        os.environ.get("AI_INPUT_NOTIFICATIONS", "1"),
    )
    if notifications_enabled == "0":
        return
    script = (
        f'display notification "{apple_script_string(message)}" '
        'with title "Personal xbar" subtitle "AI INPUT quota"'
    )
    try:
        _ = subprocess.run(
            ["/usr/bin/osascript", "-e", script],
            capture_output=True,
            timeout=3,
        )
    except (OSError, subprocess.TimeoutExpired):
        pass


def collect_subscription_quota_status(
    state_file: Path = AI_INPUT_SUBSCRIPTIONS_STATE_FILE,
    now_epoch: int | None = None,
) -> SubscriptionQuotaStatus | None:
    if not AI_INPUT_SUBSCRIPTIONS_ENABLED:
        return None
    now_value = int(time.time()) if now_epoch is None else now_epoch
    previous = read_ai_input_state(state_file)
    cached = subscription_quota_status_from_state(previous)
    checked_at = numeric_int(previous.get("checked_at"))
    if (
        cached is not None
        and checked_at is not None
        and 0 <= now_value - checked_at
        < (10 if cached.health == "loading" else AI_INPUT_SUBSCRIPTIONS_CACHE_SECONDS)
    ):
        return cached

    direct_status = (
        _direct_subscription_status(state_file, now_value)
        if AI_INPUT_SUBSCRIPTIONS_DIRECT_ENABLED
        else SubscriptionQuotaStatus(health="not-configured", source="keychain")
    )
    if direct_status.health == "ready":
        status = direct_status
    else:
        _, payload, runner_error = run_ai_input_subscriptions_javascript()
        if runner_error:
            health = (
                runner_error
                if runner_error
                in {
                    "not-running",
                    "not-found",
                    "automation-permission",
                    "javascript-permission",
                }
                else "error"
            )
            browser_status = SubscriptionQuotaStatus(
                health=health,
                error=None if health != "error" else sanitize_text(runner_error, 140),
                source="browser",
            )
        elif payload is None:
            browser_status = SubscriptionQuotaStatus(
                health="error",
                error="AI INPUT page returned no subscription data",
                source="browser",
            )
        else:
            try:
                browser_status = parse_subscription_quota_payload(payload)
                browser_status = SubscriptionQuotaStatus(
                    health=browser_status.health,
                    plans=browser_status.plans,
                    error=browser_status.error,
                    source="browser",
                )
            except ValueError as error:
                browser_status = SubscriptionQuotaStatus(
                    health="error",
                    error=sanitize_text(str(error), 140),
                    source="browser",
                )
        if browser_status.health == "ready":
            status = browser_status
        elif direct_status.health != "not-configured" and browser_status.health in {
            "not-running",
            "not-found",
        }:
            # A configured token is more actionable than a missing browser tab.
            status = direct_status
        else:
            status = browser_status

    next_state, notifications = subscription_quota_notification_transition(
        previous,
        status,
        checked_at=now_value,
    )
    try:
        write_ai_input_state(state_file, next_state)
    except OSError:
        notifications = ()
    for notification in notifications:
        send_subscription_quota_notification(notification)
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
  const muteButton = document.querySelector(
    '[data-testid="volume-bar-toggle-mute-button"], button[aria-label="Mute"], button[aria-label="Unmute"], button[aria-label="静音"], button[aria-label="取消静音"], button[aria-label="靜音"], button[aria-label="取消靜音"]'
  );
  const muteLabel = clean(muteButton?.getAttribute("aria-label"));
  const uiMuted = /^(unmute|取消静音|取消靜音|恢复声音|恢復聲音|开启声音|開啟聲音|ミュート解除)/i.test(muteLabel);
  const uiUnmuted = /^(mute|静音|靜音|关闭声音|關閉聲音|ミュート)/i.test(muteLabel);
  const mediaMuted = media.length ? media.every((element) => element.muted) : null;
  return JSON.stringify({
    playback: playing ? "playing" : (paused ? "paused" : "unknown"),
    title,
    artist,
    is_ad: Boolean(adNode) || /advertisement|advertising|广告|廣告/i.test(adSignal),
    media_muted: uiMuted ? true : (uiUnmuted ? false : mediaMuted)
  });
})()
"""

SPOTIFY_SET_MUTED_JAVASCRIPT = r"""
(() => {
  const desiredMuted = __DESIRED_MUTED__;
  const clean = (value) => (value || "").replace(/\s+/g, " ").trim();
  const button = document.querySelector(
    '[data-testid="volume-bar-toggle-mute-button"], button[aria-label="Mute"], button[aria-label="Unmute"], button[aria-label="静音"], button[aria-label="取消静音"], button[aria-label="靜音"], button[aria-label="取消靜音"]'
  );
  if (button) {
    const label = clean(button.getAttribute("aria-label"));
    const isMuted = /^(unmute|取消静音|取消靜音|恢复声音|恢復聲音|开启声音|開啟聲音|ミュート解除)/i.test(label);
    const isUnmuted = /^(mute|静音|靜音|关闭声音|關閉聲音|ミュート)/i.test(label);
    if (isMuted || isUnmuted) {
      const changed = isMuted !== desiredMuted;
      if (changed) button.click();
      return JSON.stringify({ok: true, method: "volume-button", changed});
    }
  }
  const media = [...document.querySelectorAll("audio, video")];
  if (!media.length) {
    return JSON.stringify({ok: false, error: "Spotify mute control unavailable"});
  }
  media.forEach((element) => { element.muted = desiredMuted; });
  return JSON.stringify({ok: true, method: "media-elements", count: media.length});
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

SPOTIFY_PREVIOUS_JAVASCRIPT = r"""
(() => {
  const button = document.querySelector(
    '[data-testid="control-button-skip-back"], button[aria-label="Previous"], button[aria-label="Previous track"], button[aria-label="上一首"], button[aria-label="上一曲"]'
  );
  if (!button || button.disabled) return JSON.stringify({ok: false, error: "previous track control unavailable"});
  button.click();
  return JSON.stringify({ok: true});
})()
"""

SPOTIFY_NEXT_JAVASCRIPT = r"""
(() => {
  const button = document.querySelector(
    '[data-testid="control-button-skip-forward"], button[aria-label="Next"], button[aria-label="Next track"], button[aria-label="下一首"], button[aria-label="下一曲"]'
  );
  if (!button || button.disabled) return JSON.stringify({ok: false, error: "next track control unavailable"});
  button.click();
  return JSON.stringify({ok: true});
})()
"""

SPOTIFY_ACTION_JAVASCRIPT = {
    "toggle": SPOTIFY_TOGGLE_JAVASCRIPT,
    "previous": SPOTIFY_PREVIOUS_JAVASCRIPT,
    "next": SPOTIFY_NEXT_JAVASCRIPT,
}


def compact_javascript(source: str) -> str:
    return " ".join(line.strip() for line in source.splitlines() if line.strip())


def spotify_apple_script(
    javascript: str,
    tab_id: int | None = None,
) -> str:
    browser = apple_script_string(SPOTIFY_BROWSER_APP)
    source = apple_script_string(compact_javascript(javascript))
    tab_condition = 'URL of spotifyTab starts with "https://open.spotify.com/"'
    if tab_id is not None:
        tab_condition = (
            f'(id of spotifyTab as text) is "{tab_id}" and {tab_condition}'
        )
    return "\n".join(
        (
            f'if application "{browser}" is not running then return "__NOT_RUNNING__"',
            f'tell application "{browser}"',
            "repeat with spotifyWindow in windows",
            "repeat with spotifyTab in tabs of spotifyWindow",
            f"if {tab_condition} then",
            f'set spotifyResult to execute spotifyTab javascript "{source}"',
            "return (id of spotifyTab as text) & (ASCII character 9) & spotifyResult",
            "end if",
            "end repeat",
            "end repeat",
            'return "__NO_TAB__"',
            "end tell",
        )
    )


def run_spotify_javascript(
    javascript: str,
    tab_id: int | None = None,
) -> tuple[int | None, str | None, str | None]:
    script = spotify_apple_script(javascript, tab_id=tab_id)
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


def spotify_mute_javascript(muted: bool) -> str:
    value = "true" if muted else "false"
    return SPOTIFY_SET_MUTED_JAVASCRIPT.replace("__DESIRED_MUTED__", value)


def set_spotify_media_muted(tab_id: int, muted: bool) -> str | None:
    _, payload, error = run_spotify_javascript(
        spotify_mute_javascript(muted),
        tab_id=tab_id,
    )
    if error:
        return error
    try:
        result = json.loads(payload or "")
    except json.JSONDecodeError:
        return "Spotify returned invalid mute confirmation"
    if not isinstance(result, dict) or result.get("ok") is not True:
        detail = result.get("error") if isinstance(result, dict) else None
        return str(detail) if detail else "Spotify did not confirm the mute change"
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
        'with title "Personal xbar" subtitle "Spotify Web"'
    )
    try:
        _ = subprocess.run(
            ["/usr/bin/osascript", "-e", script],
            capture_output=True,
            timeout=3,
        )
    except (OSError, subprocess.TimeoutExpired):
        pass


def control_spotify_playback(action: str) -> None:
    javascript = SPOTIFY_ACTION_JAVASCRIPT.get(action)
    if javascript is None:
        send_spotify_notification("Unknown playback action")
        return
    _, payload, error = run_spotify_javascript(javascript)
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


def toggle_spotify_playback() -> None:
    control_spotify_playback("toggle")


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


def fmt_money(cents: int) -> str:
    return f"${cents // 100}.{cents % 100:02d}"


def fmt_epoch_remaining(epoch: int, now_epoch: int | None = None) -> str:
    now_value = int(time.time()) if now_epoch is None else now_epoch
    remaining = epoch - now_value
    if remaining <= 0:
        return "now"
    days, remaining = divmod(remaining, 86400)
    hours, remaining = divmod(remaining, 3600)
    minutes = remaining // 60
    if days:
        return f"{days}d {hours}h"
    if hours:
        return f"{hours}h {minutes}m" if minutes else f"{hours}h"
    return f"{max(1, minutes)}m"


def active_subscription_plans(
    status: SubscriptionQuotaStatus,
) -> tuple[SubscriptionPlan, ...]:
    return tuple(plan for plan in status.plans if plan.status == "active")


def subscription_quota_max(
    status: SubscriptionQuotaStatus,
) -> SubscriptionQuota | None:
    quotas = [
        quota
        for plan in active_subscription_plans(status)
        for quota in plan.quotas
    ]
    highest: SubscriptionQuota | None = None
    for quota in quotas:
        if (
            highest is None
            or quota.used_cents * highest.limit_cents
            > highest.used_cents * quota.limit_cents
        ):
            highest = quota
    return highest


def subscription_quota_has_unavailable_plan(
    status: SubscriptionQuotaStatus,
) -> bool:
    return any(
        plan.quota_state == "unavailable"
        for plan in active_subscription_plans(status)
    )


def append_subscription_quota_lines(
    lines: list[str],
    status: SubscriptionQuotaStatus,
) -> None:
    if status.health == "not-running":
        lines.append("AI INPUT quota: Chrome not running | color=gray")
    elif status.health == "not-found":
        lines.append("AI INPUT quota: no open account tab | color=gray")
        lines.append("--Open ai.input.im and sign in | color=gray")
    elif status.health == "automation-permission":
        lines.append("AI INPUT quota: macOS Automation required | color=orange")
        lines.append("--System Settings > Privacy & Security > Automation | color=gray")
        lines.append("--Allow xbar to control Google Chrome | color=orange")
    elif status.health == "javascript-permission":
        lines.append("AI INPUT quota: Chrome JavaScript required | color=orange")
        lines.append("--Chrome > View > Developer | color=gray")
        lines.append("--Enable Allow JavaScript from Apple Events | color=orange")
    elif status.health == "loading":
        lines.append("AI INPUT quota: refreshing account view | color=gray")
    elif status.health == "not-configured":
        lines.append("AI INPUT quota: secure token not configured | color=gray")
        lines.append("--Run Personal xbar manager: auth set | color=gray")
    elif status.health == "session-expired":
        lines.append("AI INPUT quota: sign-in required | color=orange")
        lines.append("--Run Personal xbar manager: auth set, or sign in via Chrome | color=gray")
    elif status.health == "error":
        lines.append("AI INPUT quota: unavailable | color=orange")
        if status.error:
            lines.append(f"--{sanitize_text(status.error, 110)} | color=gray")
    else:
        active_plans = active_subscription_plans(status)
        max_quota = subscription_quota_max(status)
        has_unavailable = subscription_quota_has_unavailable_plan(status)
        if max_quota is None:
            if not active_plans:
                lines.append("AI INPUT quota: no active subscription | color=gray")
            elif has_unavailable:
                lines.append("AI INPUT quota: usage unavailable | color=orange")
            else:
                lines.append("AI INPUT quota: unlimited | color=green")
        else:
            level = subscription_quota_level(max_quota)
            color = "red" if level >= 2 else (
                "orange" if level == 1 or has_unavailable else "green"
            )
            suffix = " · some plans unavailable" if has_unavailable else ""
            lines.append(
                "AI INPUT quota: "
                f"{subscription_quota_percent_label(max_quota)} max{suffix}"
                f" | color={color}"
            )
        for plan in active_plans:
            lines.append(f"--{sanitize_text(plan.name, 75)}")
            if plan.quota_state == "unlimited":
                lines.append("----Unlimited | color=green")
            elif plan.quota_state == "unavailable":
                lines.append("----Usage unavailable | color=orange")
            for quota in plan.quotas:
                level = subscription_quota_level(quota)
                color = "red" if level >= 2 else "orange" if level == 1 else "green"
                period = quota.period.capitalize()
                lines.append(
                    f"----{period} · {fmt_money(quota.used_cents)} / "
                    f"{fmt_money(quota.limit_cents)} · "
                    f"{subscription_quota_percent_label(quota)} | color={color}"
                )
                if quota.reset_at is not None:
                    lines.append(
                        f"------Resets in {fmt_epoch_remaining(quota.reset_at)}"
                        " | color=gray"
                    )
            if plan.expires_at is not None:
                expires_text = time.strftime(
                    "%Y-%m-%d %H:%M",
                    time.localtime(plan.expires_at),
                )
                lines.append(
                    f"----Expires {expires_text} · in "
                    f"{fmt_epoch_remaining(plan.expires_at)} | color=gray"
                )
    lines.append(
        "--Open subscriptions"
        f" | bash=/usr/bin/open param1={AI_INPUT_SUBSCRIPTIONS_PAGE_URL} terminal=false"
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
            f"--Previous track | bash={executable} param1=spotify-previous"
            " terminal=false refresh=true"
        )
        lines.append(
            f"--{action} | bash={executable} param1=spotify-toggle"
            " terminal=false refresh=true"
        )
        lines.append(
            f"--Next track | bash={executable} param1=spotify-next"
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
    subscription_quota_status: SubscriptionQuotaStatus | None = None,
    spotify_status: SpotifyStatus | None = None,
    plugin_path: Path | None = None,
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
    subscription_quota_title = ""
    if subscription_quota_status is not None:
        if subscription_quota_status.health == "ready":
            max_quota = subscription_quota_max(subscription_quota_status)
            active_plans = active_subscription_plans(subscription_quota_status)
            has_unavailable = subscription_quota_has_unavailable_plan(
                subscription_quota_status
            )
            if max_quota is None:
                if not active_plans:
                    count_text = "none"
                elif has_unavailable:
                    count_text = "?"
                    if color == "green":
                        color = "orange"
                else:
                    count_text = "unlimited"
            else:
                count_text = subscription_quota_percent_label(max_quota)
                level = subscription_quota_level(max_quota)
                if level >= 2:
                    color = "red"
                elif (level == 1 or has_unavailable) and color == "green":
                    color = "orange"
            subscription_quota_title = f" · Q {count_text}"
        else:
            subscription_quota_title = " · Q ?"
            if subscription_quota_status.health != "loading" and color == "green":
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
        f" · {fmt_bytes(overall.rss_bytes)}{ai_input_title}"
        f"{subscription_quota_title}{spotify_title} | color={color}",
        "---",
        "Read-only agent process inventory | color=gray",
        f"Updated: {now or time.strftime('%H:%M:%S')} · refresh {REFRESH_SECONDS}s | color=gray",
        "CPU is recent; 100% equals one logical core. | color=gray",
        "RSS is summed per process; shared pages may be counted more than once. | color=gray",
        "---",
    ]

    if spotify_status is not None:
        append_spotify_lines(lines, spotify_status, plugin_path=plugin_path)

    if subscription_quota_status is not None:
        append_subscription_quota_lines(lines, subscription_quota_status)

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
