#!/usr/bin/env python3
"""Verify Personal xbar with deterministic process and service fixtures."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shlex
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Protocol, cast

DEFAULT_PLUGIN = Path(__file__).resolve().parents[1] / "plugin" / "personal-xbar.15s.py"


def plugin_argument() -> Path:
    parser = argparse.ArgumentParser(
        description="Verify the deterministic and live xbar monitor contract."
    )
    _ = parser.add_argument(
        "--plugin",
        type=Path,
        default=DEFAULT_PLUGIN,
        help="Plugin file to verify (default: canonical bundled plugin)",
    )
    return cast(Path, parser.parse_args().plugin).expanduser().resolve()


PLUGIN = plugin_argument()
assert PLUGIN.is_file(), PLUGIN

SUPPORTED_XBAR_PARAMETERS = frozenset(
    {"bash", "color", "param1", "param2", "refresh", "terminal"}
)


def assert_supported_xbar_parameters(lines: list[str]) -> None:
    for line in lines:
        _, separator, parameters = line.partition("|")
        if not separator:
            continue
        for parameter in shlex.split(parameters):
            key, assignment, _ = parameter.partition("=")
            assert assignment and key in SUPPORTED_XBAR_PARAMETERS, (
                line,
                parameter,
            )


class TotalsLike(Protocol):
    cpu_percent: float
    rss_bytes: int


class AdapterLike(Protocol):
    key: str
    label: str


class ProcessLike(Protocol):
    pid: int
    ppid: int
    cpu_percent: float
    rss_bytes: int
    elapsed_seconds: int
    tty: str | None
    executable: str
    command: str


class RuntimeLike(Protocol):
    adapter: AdapterLike
    root: ProcessLike
    label: str
    processes: tuple[ProcessLike, ...]
    totals: TotalsLike


class AiInputStatusLike(Protocol):
    health: str
    services: tuple[object, ...]


class SubscriptionQuotaLike(Protocol):
    period: str
    used_cents: int
    limit_cents: int
    reset_at: int | None


class SubscriptionPlanLike(Protocol):
    plan_id: str
    name: str
    status: str
    expires_at: int | None
    quotas: tuple[SubscriptionQuotaLike, ...]
    quota_state: str


class SubscriptionQuotaStatusLike(Protocol):
    health: str
    plans: tuple[SubscriptionPlanLike, ...]
    error: str | None


class SpotifyStatusLike(Protocol):
    health: str
    playback: str
    title: str | None
    artist: str | None
    is_ad: bool
    media_muted: bool | None
    auto_muted: bool
    error: str | None


class RegistryLike(Protocol):
    plugin_ids: tuple[str, ...]


class CompletedProcessLike(Protocol):
    stdout: str


class PatchableSubprocess(Protocol):
    check_output: Callable[..., str]
    run: Callable[..., CompletedProcessLike]


class SqliteConnectionLike(Protocol):
    def execute(self, *args: object, **kwargs: object) -> object: ...

    def executemany(self, *args: object, **kwargs: object) -> object: ...


class PatchableSqlite(Protocol):
    connect: Callable[..., SqliteConnectionLike]


class MonitorModule(Protocol):
    AGENT_ADAPTERS: tuple[AdapterLike, ...]
    AI_INPUT_SUBSCRIPTIONS_JAVASCRIPT: str
    AI_INPUT_SUBSCRIPTIONS_ORIGIN: str
    AI_INPUT_SUBSCRIPTIONS_TAB_PREFIX: str
    AI_INPUT_API_BASE: str
    SPOTIFY_ACTION_JAVASCRIPT: dict[str, str]
    subprocess: PatchableSubprocess
    sqlite3: PatchableSqlite

    def build_registry(self) -> RegistryLike: ...

    def parse_ps_output(self, output: str) -> dict[int, ProcessLike]: ...

    def build_runtimes(
        self,
        rows: dict[int, ProcessLike],
        home: Path,
    ) -> tuple[tuple[RuntimeLike, ...], tuple[ProcessLike, ...]]: ...

    def render(
        self,
        rows: dict[int, ProcessLike],
        home: Path,
        now: str | None = None,
        ai_input_status: AiInputStatusLike | None = None,
        subscription_quota_status: SubscriptionQuotaStatusLike | None = None,
        spotify_status: SpotifyStatusLike | None = None,
    ) -> str: ...

    def parse_ai_input_payload(
        self,
        payload: object,
        now_epoch: int | None = None,
    ) -> AiInputStatusLike: ...

    def ai_input_notification_transition(
        self,
        previous: dict[str, object],
        status: AiInputStatusLike,
        checked_at: int,
    ) -> tuple[dict[str, object], str | None]: ...

    def parse_subscription_quota_payload(
        self,
        payload: str,
    ) -> SubscriptionQuotaStatusLike: ...

    def parse_subscription_api_payload(
        self,
        payload: object,
        now_epoch: int | None = None,
    ) -> SubscriptionQuotaStatusLike: ...

    def collect_subscription_quota_api_status(
        self,
        state_file: Path,
        now_epoch: int | None = None,
    ) -> SubscriptionQuotaStatusLike: ...

    def collect_subscription_quota_status(
        self,
        state_file: Path,
        now_epoch: int | None = None,
    ) -> SubscriptionQuotaStatusLike | None: ...

    def chrome_tab_apple_script(
        self,
        browser: str,
        url_prefix: str,
        javascript: str,
        tab_id: int | None = None,
    ) -> str: ...

    def subscription_quota_level(self, quota: SubscriptionQuotaLike) -> int: ...

    def subscription_quota_percent_label(
        self,
        quota: SubscriptionQuotaLike,
    ) -> str: ...

    def classify_chrome_automation_error(self, detail: str) -> str: ...

    def subscription_quota_notification_transition(
        self,
        previous: dict[str, object],
        status: SubscriptionQuotaStatusLike,
        checked_at: int,
    ) -> tuple[dict[str, object], tuple[str, ...]]: ...

    def parse_spotify_payload(self, payload: str) -> SpotifyStatusLike: ...

    def spotify_apple_script(
        self,
        javascript: str,
        tab_id: int | None = None,
    ) -> str: ...

    def spotify_ad_mute_transition(
        self,
        previous: dict[str, object],
        *,
        tab_id: int,
        is_ad: bool,
        media_muted: bool | None,
        enabled: bool = True,
    ) -> tuple[dict[str, object], bool | None]: ...

    def spotify_mute_javascript(self, muted: bool) -> str: ...

    def set_spotify_media_muted(self, tab_id: int, muted: bool) -> str | None: ...

    def read_codex_session_handles_by_pid(
        self,
        pids: tuple[int, ...],
        home: Path,
    ) -> dict[int, tuple[Path, ...]]: ...

    def runtime_label(
        self,
        adapter: AdapterLike,
        root: ProcessLike,
        rows: dict[int, ProcessLike],
        home: Path,
    ) -> str: ...


def load_plugin() -> MonitorModule:
    spec = importlib.util.spec_from_file_location("agent_process_monitor", PLUGIN)
    assert spec is not None and spec.loader is not None
    module: ModuleType = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return cast(MonitorModule, cast(object, module))


monitor = load_plugin()
assert monitor.build_registry().plugin_ids == (
    "ai-input",
    "subscription-quota",
    "spotify",
    "processes",
)

with tempfile.TemporaryDirectory() as temporary_directory:
    home = Path(temporary_directory)
    session = home / "session.jsonl"
    _ = session.write_text(
        "\n".join(
            [
                '{"type":"title","title":"Fixture OMP session"}',
                '{"type":"session","title":"Ignored older title"}',
                "",
            ]
        ),
        encoding="utf-8",
    )
    mapping_dir = home / ".omp" / "agent" / "terminal-sessions"
    mapping_dir.mkdir(parents=True)
    _ = (mapping_dir / "ttys001").write_text(
        f"/fixture/project\n{session}\n",
        encoding="utf-8",
    )

    codex_home = home / ".codex"
    session_dir = codex_home / "sessions" / "2026" / "07" / "24"
    session_dir.mkdir(parents=True)
    single_thread_id = "019f5728-6ebf-70c1-8b8f-8fc4b2a4c3db"
    linked_thread_id = "019f5728-6ebf-70c1-8b8f-8fc4b2a4c3dc"
    unavailable_thread_id = "019f5728-6ebf-70c1-8b8f-8fc4b2a4c3dd"
    single_session = session_dir / f"rollout-2026-07-24T12-00-00-{single_thread_id}.jsonl"
    linked_session = session_dir / f"rollout-2026-07-24T12-01-00-{linked_thread_id}.jsonl"
    unavailable_session = session_dir / (
        f"rollout-2026-07-24T12-02-00-{unavailable_thread_id}.jsonl"
    )
    for session_path, session_id in (
        (single_session, single_thread_id),
        (linked_session, linked_thread_id),
        (unavailable_session, unavailable_thread_id),
    ):
        _ = session_path.write_text(
            f'{{"type":"session_meta","payload":{{"session_id":"{session_id}"}}}}\n',
            encoding="utf-8",
        )
    fake_lsof = home / "fake-lsof"
    _ = fake_lsof.write_text(
        "\n".join(
            (
                "#!/bin/sh",
                'printf "%s\\n" \\',
                f'  "p201" "n{single_session}" "n{home / "outside.jsonl"}" \\',
                f'  "p203" "n{single_session}" "n{linked_session}" \\',
                f'  "p205" "n{unavailable_session}" "p212" \\',
                f'  "p999" "n{single_session}"',
                "exit 0",
                "",
            )
        ),
        encoding="utf-8",
    )
    _ = fake_lsof.chmod(0o755)
    _ = (codex_home / "state_5.sqlite").write_bytes(b"fixture")

    original_run = monitor.subprocess.run
    original_sqlite_connect = monitor.sqlite3.connect
    lsof_commands: list[tuple[str, ...]] = []

    class FakeCompleted:
        def __init__(self, stdout: str):
            self.stdout: str = stdout

    def fake_subprocess_run(
        args: object,
        bufsize: int = -1,
        executable: object = None,
        stdin: object = None,
        stdout: object = None,
        stderr: object = None,
        preexec_fn: object = None,
        close_fds: bool = True,
        shell: bool = False,
        cwd: object = None,
        env: object = None,
        universal_newlines: bool | None = None,
        startupinfo: object = None,
        creationflags: int = 0,
        restore_signals: bool = True,
        start_new_session: bool = False,
        pass_fds: object = (),
        *,
        capture_output: bool = False,
        timeout: float | None = None,
        check: bool = False,
        encoding: str | None = None,
        errors: str | None = None,
        text: bool | None = None,
        **kwargs: object,
    ) -> CompletedProcessLike:
        if isinstance(args, list):
            command_items = tuple(str(item) for item in cast(list[object], args))
            if command_items and command_items[0] == "/usr/sbin/lsof":
                lsof_commands.append(command_items)
                assert command_items[1:] == (
                    "-nP",
                    "-Fpn",
                    "-p",
                    "201,203,205,212",
                )
                assert capture_output and text and timeout == 1.5 and not check
                output = subprocess.check_output(
                    [str(fake_lsof), *command_items[1:]],
                    text=True,
                )
                return FakeCompleted(output)
        return original_run(
            args,
            bufsize,
            executable,
            stdin,
            stdout,
            stderr,
            preexec_fn,
            close_fds,
            shell,
            cwd,
            env,
            universal_newlines,
            startupinfo,
            creationflags,
            restore_signals,
            start_new_session,
            pass_fds,
            capture_output=capture_output,
            timeout=timeout,
            check=check,
            encoding=encoding,
            errors=errors,
            text=text,
            **kwargs,
        )

    def fake_sqlite_connect(
        *args: object, **kwargs: object
    ) -> SqliteConnectionLike:
        uri = args[0] if args else ""
        if isinstance(uri, str) and uri.startswith("file:"):
            memory = original_sqlite_connect(":memory:")
            _ = memory.execute("CREATE TABLE threads (id TEXT, title TEXT, archived INTEGER)")
            _ = memory.executemany(
                "INSERT INTO threads VALUES (?, ?, 0)",
                [
                    (single_thread_id, "Fixture Codex session title"),
                    (linked_thread_id, "Fixture linked session title"),
                ],
            )
            return memory
        return original_sqlite_connect(*args, **kwargs)

    monitor.subprocess.run = fake_subprocess_run
    monitor.sqlite3.connect = fake_sqlite_connect
    assert monitor.read_codex_session_handles_by_pid((), home) == {}
    assert not lsof_commands
    try:
        fixture_rows = monitor.parse_ps_output(
            "\n".join(
            [
                "1 0 0.0 10240 01:00 ?? /sbin/launchd",
                "10 1 0.0 2048 01:00 ttys001 -zsh",
                "100 10 10.0 102400 02:00:00 ttys001 omp",
                "101 100 20.0 51200 01:00 ttys001 uvx awslabs.cloudwatch-mcp-server@latest",
                "102 101 30.0 40960 01:00 ttys001 python awslabs.cloudwatch-mcp-server",
                "103 100 5.0 20480 01:00 ?? codex",
                "104 103 10.0 30720 01:00 ?? node nested-worker",
                "200 1 15.0 204800 01:00:00 ?? /Applications/ChatGPT.app/Contents/MacOS/ChatGPT",
                "201 200 25.0 102400 01:00 ?? /Applications/ChatGPT.app/Contents/Resources/codex app-server",
                "203 200 5.0 51200 01:00 ?? /Applications/ChatGPT.app/Contents/Resources/codex app-server",
                "205 200 3.0 40960 01:00 ?? /Applications/ChatGPT.app/Contents/Resources/codex app-server",
                "204 200 2.0 10240 01:00 ?? /Applications/ChatGPT.app/Contents/Resources/codex-code-mode-host",
                "202 203 35.0 92160 01:00 ?? npm exec @playwright/mcp",
                "206 202 6.0 30720 01:00 ?? node playwright-wrapper",
                "207 206 4.0 20480 01:00 ?? node playwright-server",
                "208 203 8.0 40960 01:00 ?? npm exec @playwright/mcp",
                "209 208 3.0 20480 01:00 ?? node playwright-wrapper",
                "210 209 2.0 10240 01:00 ?? node playwright-server",
                "211 203 1.0 10240 01:00 ?? /Applications/ChatGPT.app/Contents/Resources/codex-code-mode-host",
                "212 200 4.0 30720 01:00 ?? /Applications/ChatGPT.app/Contents/Resources/codex app-server",
                "213 200 9.0 30720 01:00 ?? npm exec @playwright/mcp",
                "214 213 1.0 10240 01:00 ?? node desktop-mcp-child",
                "300 1 7.0 25600 01:00 ?? npm exec @lottiefiles/creator-mcp",
            ]
            )
        )
        runtimes, unattributed = monitor.build_runtimes(fixture_rows, home)
        rendered = monitor.render(fixture_rows, home, now="12:34:56")
        expected_lsof_command = (
            "/usr/sbin/lsof",
            "-nP",
            "-Fpn",
            "-p",
            "201,203,205,212",
        )
        assert lsof_commands == [expected_lsof_command]
        assert monitor.render(fixture_rows, home, now="12:34:56") == rendered
        assert lsof_commands == [expected_lsof_command, expected_lsof_command]
    finally:
        monitor.subprocess.run = original_run
        monitor.sqlite3.connect = original_sqlite_connect
    assert len(runtimes) == 2, [
        (runtime.adapter.label, runtime.root.pid) for runtime in runtimes
    ]
    assert [process.pid for process in unattributed] == [300]

    owned_pid_sets: list[set[int]] = [
        {process.pid for process in runtime.processes} for runtime in runtimes
    ]
    assert owned_pid_sets[0].isdisjoint(owned_pid_sets[1]), owned_pid_sets
    assert owned_pid_sets[0].union(owned_pid_sets[1]).isdisjoint(
        {process.pid for process in unattributed}
    )

    omp_runtime = next(runtime for runtime in runtimes if runtime.adapter.key == "omp")
    codex_runtime = next(
        runtime for runtime in runtimes if runtime.adapter.key == "codex"
    )
    assert omp_runtime.root.pid == 100
    assert {process.pid for process in omp_runtime.processes} == {100, 101, 102, 103, 104}
    assert omp_runtime.label.startswith("Fixture OMP session · PID 100")
    assert omp_runtime.totals.cpu_percent == 75
    assert omp_runtime.totals.rss_bytes == 240 * 1024 * 1024
    assert codex_runtime.root.pid == 200
    assert {process.pid for process in codex_runtime.processes} == {
        200,
        201,
        202,
        203,
        204,
        205,
        206,
        207,
        208,
        209,
        210,
        211,
        212,
        213,
        214,
    }
    assert "shared runtime" in codex_runtime.label

    lines = rendered.splitlines()
    assert_supported_xbar_parameters(lines)
    assert lines[0].startswith("AI 2 · CPU 205.0% · 955 MiB"), lines[0]
    assert "---" in lines
    assert any(line.startswith("OMP: 1 runtime") for line in lines)
    assert any(line.startswith("--Fixture OMP session") for line in lines)
    assert not any(line.startswith("--Codex Desktop · shared runtime") for line in lines)
    assert any(line.startswith("--Codex Desktop shared process tree") for line in lines)
    assert not any(line.startswith("--MCP subtotal") for line in lines)
    assert any(line.startswith("------Playwright · 2 instances") for line in lines)
    assert any(
        line.startswith("--Desktop host · PID 200 · CPU 15.0% · 200 MiB")
        for line in lines
    )
    assert any(
        line.startswith("--Sessions on worker PID 201 · 1 linked session")
        for line in lines
    )
    assert any(line.startswith("--Worker · PID 201 · CPU 25.0% · 100 MiB") for line in lines)
    session_summary_index = next(
        index
        for index, line in enumerate(lines)
        if line.startswith("--Sessions on worker PID 203 · 2 linked sessions")
    )
    session_indices = [
        index
        for index, line in enumerate(lines)
        if line.startswith("--Session: ") and index > session_summary_index
    ][:2]
    worker_index = next(
        index
        for index, line in enumerate(lines)
        if index > session_summary_index
        and line.startswith("--Worker · PID 203 · CPU 5.0% · 50 MiB")
    )
    mcp_index = next(
        index
        for index, line in enumerate(lines)
        if index > worker_index and line.startswith("----MCP instances")
    )
    assert len(session_indices) == 2, session_indices
    assert session_summary_index < min(session_indices)
    assert max(session_indices) < worker_index < mcp_index
    assert "subtree CPU 64.0% · 270 MiB · 8 processes" in lines[worker_index]
    assert any(
        line.startswith(
            "----MCP instances · 2 instances · CPU 58.0% · 210 MiB · 6 processes"
        )
        for line in lines
    )
    assert any(
        line.startswith(
            "------Playwright · 2 instances · CPU 58.0% · 210 MiB · 6 processes"
        )
        for line in lines
    )
    first_instance = next(
        line for line in lines if line.startswith("--------npm · PID 202 · CPU 35.0% · 90 MiB")
    )
    assert "subtree CPU 45.0% · 140 MiB · 3 processes" in first_instance
    wrapper = next(
        line for line in lines if line.startswith("----------node · PID 206 · CPU 6.0% · 30 MiB")
    )
    assert "subtree CPU 10.0% · 50 MiB · 2 processes" in wrapper
    assert any(
        line.startswith("------------node · PID 207 · CPU 4.0% · 20 MiB")
        for line in lines
    )
    assert any(
        line.startswith("--------npm · PID 208 · CPU 8.0% · 40 MiB")
        and "subtree CPU 13.0% · 70 MiB · 3 processes" in line
        for line in lines
    )
    assert not any(line.startswith("------node · PID 207") for line in lines)
    assert any(
        line.startswith("----Support · CPU 1.0% · 10 MiB · 1 process")
        for line in lines
    )
    assert any(
        line.startswith("------Code mode host · PID 211 · CPU 1.0% · 10 MiB")
        for line in lines
    )
    assert any(
        line.startswith(
            "--Session worker (title unavailable) · PID 205 · CPU 3.0% · 40 MiB"
        )
        for line in lines
    )
    assert any(
        line.startswith(
            "--Other Codex Desktop processes · 3 roots · CPU 16.0% · 80 MiB · 4 processes"
        )
        for line in lines
    )
    assert any(
        line.startswith("----Code mode host · PID 204 · CPU 2.0% · 10 MiB")
        for line in lines
    )
    assert any(
        line.startswith("----Codex process · PID 212 · CPU 4.0% · 30 MiB")
        for line in lines
    )
    desktop_mcp_root = next(
        line for line in lines if line.startswith("----npm · PID 213 · CPU 9.0% · 30 MiB")
    )
    assert "subtree CPU 10.0% · 40 MiB · 2 processes" in desktop_mcp_root
    assert any(
        line.startswith("------node · PID 214 · CPU 1.0% · 10 MiB")
        for line in lines
    )
    assert not any(line.startswith("--Generic worker") for line in lines)
    assert not any(line.startswith("----Desktop host") for line in lines)
    assert "app-server" not in rendered
    assert any(line.startswith("Unattributed MCP") for line in lines)
    assert not any(line.startswith("Claude Code:") for line in lines)
    assert not any(line.startswith("OpenCode:") for line in lines)
    assert not any(line.startswith("Pi:") for line in lines)
    assert any(line.startswith("Open Activity Monitor") for line in lines)

    healthy_payload = {
        "all_ok": True,
        "generated_at": 2_000_000,
        "services": [
            {
                "model": "gpt-fixture-fast",
                "uptime_pct": 99.5,
                "last": {"ok": True, "latency_ms": 750, "error": None},
            },
            {
                "model": "gpt-fixture-slow",
                "uptime_pct": 98.25,
                "last": {"ok": True, "latency_ms": 2450, "error": None},
            },
        ],
    }
    healthy_status = monitor.parse_ai_input_payload(
        healthy_payload,
        now_epoch=2_000_010,
    )
    assert healthy_status.health == "healthy"
    healthy_rendered = monitor.render(
        fixture_rows,
        home,
        now="12:34:56",
        ai_input_status=healthy_status,
    )
    healthy_lines = healthy_rendered.splitlines()
    assert_supported_xbar_parameters(healthy_lines)
    assert "· API 2/2 | color=" in healthy_lines[0]
    assert any(
        line.startswith("AI.INPUT.IM: 2/2 online · max 2.5s | color=green")
        for line in healthy_lines
    )
    assert any(
        line.startswith("--gpt-fixture-fast · online · 750ms · 99.50% / 60m")
        for line in healthy_lines
    )
    assert any(line.startswith("--Open official model monitor") for line in healthy_lines)

    degraded_payload = {
        **healthy_payload,
        "all_ok": False,
        "services": [
            healthy_payload["services"][0],
            {
                "model": "gpt-fixture-slow",
                "uptime_pct": 95.0,
                "last": {
                    "ok": False,
                    "latency_ms": None,
                    "error": "HTTP 503 | upstream unavailable",
                },
            },
        ],
    }
    degraded_status = monitor.parse_ai_input_payload(
        degraded_payload,
        now_epoch=2_000_010,
    )
    assert degraded_status.health == "degraded"
    degraded_lines = monitor.render(
        fixture_rows,
        home,
        now="12:34:56",
        ai_input_status=degraded_status,
    ).splitlines()
    assert degraded_lines[0].endswith("· API 1/2 | color=red")
    assert any(
        line.startswith("AI.INPUT.IM: 1/2 online · model failure | color=red")
        for line in degraded_lines
    )
    assert "| upstream" not in "\n".join(degraded_lines)

    healthy_state, initial_notification = monitor.ai_input_notification_transition(
        {}, healthy_status, checked_at=2_000_010
    )
    assert initial_notification is None
    degraded_state, failure_notification = monitor.ai_input_notification_transition(
        healthy_state, degraded_status, checked_at=2_000_070
    )
    assert failure_notification == "Model probe failed: gpt-fixture-slow"
    repeated_state, repeated_notification = monitor.ai_input_notification_transition(
        degraded_state, degraded_status, checked_at=2_000_130
    )
    assert repeated_notification is None
    _, recovery_notification = monitor.ai_input_notification_transition(
        repeated_state, healthy_status, checked_at=2_000_190
    )
    assert recovery_notification == "Recovered: 2/2 models online"

    stale_status = monitor.parse_ai_input_payload(
        healthy_payload,
        now_epoch=2_000_181,
    )
    assert stale_status.health == "unreachable"
    try:
        _ = monitor.parse_ai_input_payload({"all_ok": True}, now_epoch=2_000_181)
    except ValueError as error:
        assert "generated_at" in str(error)
    else:
        raise AssertionError("malformed AI.INPUT.IM status payload was accepted")
    unreachable_state, first_unreachable_notification = (
        monitor.ai_input_notification_transition(
            {}, stale_status, checked_at=2_000_181
        )
    )
    assert first_unreachable_notification is None
    _, second_unreachable_notification = monitor.ai_input_notification_transition(
        unreachable_state, stale_status, checked_at=2_000_241
    )
    assert second_unreachable_notification == "Official model monitor is unreachable"

    subscription_status = monitor.parse_subscription_quota_payload(
        """{
          "ok": true,
          "subscriptions": [
            {
              "id": "fixture-plan",
              "name": "Fixture CodeX Plan",
              "status": "ACTIVE",
              "expires_at": 4102444800,
              "quotas": [
                {
                  "period": "daily",
                  "used_usd": "79.995",
                  "limit_usd": "100.00",
                  "reset_at": 4102358400
                },
                {
                  "period": "weekly",
                  "used_usd": "231.275",
                  "limit_usd": "300.00",
                  "reset_at": 4102444800
                }
              ]
            }
          ]
        }"""
    )
    assert subscription_status.health == "ready"
    assert len(subscription_status.plans) == 1
    fixture_plan = subscription_status.plans[0]
    assert fixture_plan.plan_id == "fixture-plan"
    assert fixture_plan.name == "Fixture CodeX Plan"
    assert fixture_plan.status == "active"
    assert fixture_plan.quota_state == "available"
    assert fixture_plan.expires_at == 4_102_444_800
    assert [quota.period for quota in fixture_plan.quotas] == ["daily", "weekly"]
    assert [quota.used_cents for quota in fixture_plan.quotas] == [8_000, 23_128]
    assert [quota.limit_cents for quota in fixture_plan.quotas] == [10_000, 30_000]

    # Direct API schema, Keychain record hygiene, and refresh rotation contract.
    api_status = monitor.parse_subscription_api_payload(
        {
            "code": 0,
            "message": "success",
            "data": [
                {
                    "id": 41,
                    "status": "active",
                    "expires_at": "2030-01-01T00:00:00Z",
                    "daily_usage_usd": 79.995,
                    "weekly_usage_usd": 120,
                    "monthly_usage_usd": 0,
                    "daily_window_start": "2026-08-05T00:00:00Z",
                    "weekly_window_start": None,
                    "monthly_window_start": None,
                    "group": {
                        "name": "Direct Fixture Plan",
                        "daily_limit_usd": 100,
                        "weekly_limit_usd": 300,
                        "monthly_limit_usd": None,
                    },
                }
            ],
        },
        now_epoch=1_700_000_000,
    )
    assert api_status.source == "api"
    assert api_status.plans[0].plan_id == "41"
    assert api_status.plans[0].name == "Direct Fixture Plan"
    assert [quota.period for quota in api_status.plans[0].quotas] == [
        "daily",
        "weekly",
    ]
    assert api_status.plans[0].quotas[0].used_cents == 8_000
    assert api_status.plans[0].quotas[0].reset_at == 1_785_974_400
    assert api_status.plans[0].quotas[1].reset_at is None

    unlimited_api_status = monitor.parse_subscription_api_payload(
        {
            "code": 0,
            "data": [
                {
                    "id": 42,
                    "status": "active",
                    "expires_at": None,
                    "group": {
                        "name": "Unlimited Direct Fixture",
                        "daily_limit_usd": None,
                        "weekly_limit_usd": 0,
                        "monthly_limit_usd": None,
                    },
                    "daily_usage_usd": 0,
                    "weekly_usage_usd": 0,
                    "monthly_usage_usd": 0,
                }
            ],
        }
    )
    assert unlimited_api_status.plans[0].quota_state == "unlimited"
    assert not unlimited_api_status.plans[0].quotas

    auth_module = monitor.ai_input_auth

    class MemoryKeychain:
        def __init__(self) -> None:
            self.value: str | None = None

        def read(self) -> str | None:
            return self.value

        def write(self, value: str) -> None:
            self.value = value

        def delete(self) -> None:
            self.value = None

    memory_keychain = MemoryKeychain()
    fixture_credentials = auth_module.make_credentials(
        "access-fixture-secret", "refresh-fixture-secret", 2_000_001_000
    )
    auth_module.write_credentials(fixture_credentials, memory_keychain)
    assert auth_module.read_credentials(memory_keychain) == fixture_credentials
    assert "access-fixture-secret" not in repr(fixture_credentials)
    assert "refresh-fixture-secret" not in repr(fixture_credentials)
    assert auth_module.credentials_summary(fixture_credentials, 2_000_000_000)[
        "refresh_due"
    ] is False
    jwt_fixture = (
        "eyJhbGciOiJub25lIiwidHlwIjoiSldUIn0."
        "eyJleHAiOjIwMDAwMDAxMjN9.signature"
    )
    assert auth_module.jwt_expiry(jwt_fixture) == 2_000_000_123

    redirect_handler = monitor.ExactAiInputRedirectHandler()
    try:
        _ = redirect_handler.redirect_request(
            urllib.request.Request(monitor.AI_INPUT_API_BASE + "/subscriptions"),
            None,
            302,
            "redirect",
            "https://example.invalid/collect",
        )
    except monitor.AiInputApiError as error:
        assert error.kind == "redirect"
    else:
        raise AssertionError("cross-origin API redirect was accepted")

    direct_globals = monitor.collect_subscription_quota_api_status.__globals__
    original_api_reader = direct_globals["read_ai_input_credentials"]
    original_api_writer = direct_globals["write_ai_input_credentials"]
    original_api_request = direct_globals["api_request_json"]
    rotating_credentials = [
        auth_module.make_credentials("old-access", "old-refresh", 2_100_000_000)
    ]
    api_calls: list[tuple[str, str | None]] = []
    refresh_calls = [0]
    refresh_call_lock = threading.Lock()

    def fake_api_reader() -> object:
        return rotating_credentials[0]

    def fake_api_writer(value: object) -> None:
        assert isinstance(value, auth_module.AiInputCredentials)
        rotating_credentials[0] = value

    def fake_api_request(
        path: str,
        access_token: str | None = None,
        **kwargs: object,
    ) -> object:
        api_calls.append((path, access_token))
        if path == "/auth/refresh":
            with refresh_call_lock:
                refresh_calls[0] += 1
            time.sleep(0.03)
            return {
                "code": 0,
                "data": {
                    "access_token": "new-access",
                    "refresh_token": "new-refresh",
                    "expires_in": 3_600,
                },
            }
        if access_token == "old-access":
            raise monitor.AiInputApiError("unauthorized", "fixture unauthorized")
        return {
            "code": 0,
            "data": [
                {
                    "id": 43,
                    "status": "active",
                    "expires_at": None,
                    "daily_usage_usd": 1,
                    "group": {
                        "name": "Retry Fixture",
                        "daily_limit_usd": 10,
                        "weekly_limit_usd": None,
                        "monthly_limit_usd": None,
                    },
                }
            ],
        }

    try:
        direct_globals["read_ai_input_credentials"] = fake_api_reader
        direct_globals["write_ai_input_credentials"] = fake_api_writer
        direct_globals["api_request_json"] = fake_api_request
        direct_state_file = home / "direct-api-state.json"
        direct_result = monitor.collect_subscription_quota_api_status(
            direct_state_file, now_epoch=2_000_000_000
        )
        assert direct_result.health == "ready"
        assert direct_result.source == "api"
        assert direct_result.plans[0].name == "Retry Fixture"
        assert any(path == "/auth/refresh" for path, _token in api_calls)
        assert api_calls[-1][0].startswith("/subscriptions")
        assert api_calls[-1][1] == "new-access"

        rotating_credentials[0] = auth_module.make_credentials(
            "expired-access", "rotating-refresh", 1
        )
        api_calls.clear()
        refresh_calls[0] = 0
        results: list[auth_module.AiInputCredentials] = []

        def refresh_worker() -> None:
            results.append(
                direct_globals["refresh_ai_input_credentials"](
                    rotating_credentials[0],
                    direct_state_file,
                    2_000_000_000,
                    force=False,
                )
            )

        workers = [threading.Thread(target=refresh_worker) for _ in range(2)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join()
        assert refresh_calls[0] == 1, refresh_calls[0]
        assert len(results) == 2
        assert all(item.access_token == "new-access" for item in results)
    finally:
        direct_globals["read_ai_input_credentials"] = original_api_reader
        direct_globals["write_ai_input_credentials"] = original_api_writer
        direct_globals["api_request_json"] = original_api_request

    subscription_javascript = monitor.AI_INPUT_SUBSCRIPTIONS_JAVASCRIPT
    assert "/api/v1/subscriptions" in subscription_javascript
    lowered_subscription_javascript = subscription_javascript.lower()
    assert "document.cookie" not in lowered_subscription_javascript
    assert "localstorage" not in lowered_subscription_javascript
    assert "sessionstorage" not in lowered_subscription_javascript
    assert "new xmlhttprequest" not in lowered_subscription_javascript
    assert "fetch(" not in lowered_subscription_javascript
    assert 'data-personal-xbar-quota-frame="1"' in subscription_javascript
    assert "data-personal-xbar-quota-started-at" in subscription_javascript
    assert "frameStale" in subscription_javascript
    assert 'frameSnapshot.error !== "loading"' in subscription_javascript
    assert "frame-unavailable" in subscription_javascript
    assert "status_text: statusText" in subscription_javascript
    assert 'id: `dom:${cardIndex}:${name}:${expiresAt || "none"}`' in (
        subscription_javascript
    )
    assert 'quota_state: quotaState' in subscription_javascript
    assert "/active|" not in subscription_javascript
    assert monitor.AI_INPUT_SUBSCRIPTIONS_ORIGIN == "https://ai.input.im/"
    assert (
        monitor.AI_INPUT_SUBSCRIPTIONS_TAB_PREFIX
        == "https://ai.input.im/subscriptions"
    )
    scoped_subscription_script = monitor.chrome_tab_apple_script(
        "Google Chrome",
        monitor.AI_INPUT_SUBSCRIPTIONS_TAB_PREFIX,
        "return 1",
    )
    assert (
        'const targetURL = "https://ai.input.im/subscriptions"'
        in scoped_subscription_script
    )
    assert "url === targetURL" in scoped_subscription_script
    assert "url.startsWith(`${targetURL}?`)" in scoped_subscription_script
    assert "url.startsWith(`${targetURL}#`)" in scoped_subscription_script
    assert "url.startsWith(urlPrefix)" not in scoped_subscription_script
    assert "fallbackResult" in scoped_subscription_script
    assert "JSON.parse(pageResult)" in scoped_subscription_script
    assert "parsedResult.ok === true" in scoped_subscription_script
    assert "runningApp.processIdentifier" in scoped_subscription_script
    assert "Number(runningApp.activationPolicy) !== 0" in scoped_subscription_script
    assert 'const targetURL = "http://ai.input.im/' not in scoped_subscription_script
    assert (
        monitor.classify_chrome_automation_error(
            "Not authorized to send Apple events. (-1743)"
        )
        == "automation-permission"
    )
    assert (
        monitor.classify_chrome_automation_error(
            "Allow JavaScript from Apple Events is disabled"
        )
        == "javascript-permission"
    )

    def threshold_status(used_usd: str) -> SubscriptionQuotaStatusLike:
        return monitor.parse_subscription_quota_payload(
            """{
              "ok": true,
              "subscriptions": [{
                "id": "threshold-plan",
                "name": "Threshold Plan",
                "status": "active",
                "expires_at": null,
                "quotas": [{
                  "period": "daily",
                  "used_usd": %s,
                  "limit_usd": 100,
                  "reset_at": null
                }]
              }]
            }"""
            % used_usd
        )

    status_79_99 = threshold_status("79.99")
    status_80 = threshold_status("80")
    status_90 = threshold_status("90")
    status_99_99 = threshold_status("99.99")
    status_100 = threshold_status("100")
    assert monitor.subscription_quota_level(status_79_99.plans[0].quotas[0]) == 0
    assert monitor.subscription_quota_level(status_80.plans[0].quotas[0]) == 1
    assert monitor.subscription_quota_level(status_90.plans[0].quotas[0]) == 2
    assert monitor.subscription_quota_level(status_99_99.plans[0].quotas[0]) == 2
    assert monitor.subscription_quota_level(status_100.plans[0].quotas[0]) == 3
    assert (
        monitor.subscription_quota_percent_label(status_99_99.plans[0].quotas[0])
        == "99%"
    )

    for status_text in ("Inactive", "Not active", "\u65e0\u6548"):
        inactive_status = monitor.parse_subscription_quota_payload(
            json.dumps(
                {
                    "ok": True,
                    "subscriptions": [
                        {
                            "id": f"inactive-{status_text}",
                            "name": "Inactive Fixture",
                            "status_text": status_text,
                            "expires_at": None,
                            "quotas": [],
                        }
                    ],
                }
            )
        )
        assert inactive_status.plans[0].status == "inactive"

    duplicate_plan_status = monitor.parse_subscription_quota_payload(
        """{
          "ok": true,
          "subscriptions": [
            {
              "id": "duplicate-plan-0",
              "name": "Duplicate Plan",
              "status": "active",
              "expires_at": 4102444800,
              "quotas": [{
                "period": "daily",
                "used_usd": 90,
                "limit_usd": 100,
                "reset_at": null
              }]
            },
            {
              "id": "duplicate-plan-1",
              "name": "Duplicate Plan",
              "status": "active",
              "expires_at": 4102444800,
              "quotas": [{
                "period": "daily",
                "used_usd": 70,
                "limit_usd": 100,
                "reset_at": null
              }]
            }
          ]
        }"""
    )
    duplicate_state, duplicate_notice = (
        monitor.subscription_quota_notification_transition(
            {}, duplicate_plan_status, checked_at=2_000_290
        )
    )
    assert duplicate_notice == ("Quota 90%: Duplicate Plan daily 90%",)
    duplicate_levels = duplicate_state.get("quota_levels")
    assert isinstance(duplicate_levels, dict) and len(duplicate_levels) == 2
    _, repeated_duplicate_notice = monitor.subscription_quota_notification_transition(
        duplicate_state,
        duplicate_plan_status,
        checked_at=2_000_295,
    )
    assert repeated_duplicate_notice == ()

    warning_state, initial_warning = (
        monitor.subscription_quota_notification_transition(
            {}, status_80, checked_at=2_000_300
        )
    )
    assert initial_warning == ("Quota 80%: Threshold Plan daily 80%",)
    repeated_warning_state, repeated_warning = (
        monitor.subscription_quota_notification_transition(
            warning_state, status_80, checked_at=2_000_360
        )
    )
    assert repeated_warning == ()
    escalation_state, escalation = monitor.subscription_quota_notification_transition(
        repeated_warning_state,
        status_90,
        checked_at=2_000_420,
    )
    assert escalation == ("Quota 90%: Threshold Plan daily 90%",)
    _, near_exhausted_notice = monitor.subscription_quota_notification_transition(
        {},
        status_99_99,
        checked_at=2_000_450,
    )
    assert near_exhausted_notice == ("Quota 90%: Threshold Plan daily 99%",)
    _, reset_notice = monitor.subscription_quota_notification_transition(
        escalation_state,
        threshold_status("0"),
        checked_at=2_000_480,
    )
    assert reset_notice == ("Quota reset: Threshold Plan daily 0%",)

    subscription_lines = monitor.render(
        fixture_rows,
        home,
        now="12:34:56",
        subscription_quota_status=subscription_status,
    ).splitlines()
    assert_supported_xbar_parameters(subscription_lines)
    assert "· Q 80% | color=" in subscription_lines[0]
    assert "AI INPUT quota: 80% max | color=orange" in subscription_lines
    assert "--Fixture CodeX Plan" in subscription_lines
    assert (
        "----Daily · $80.00 / $100.00 · 80% | color=orange"
        in subscription_lines
    )
    assert (
        "----Weekly · $231.28 / $300.00 · 77% | color=green"
        in subscription_lines
    )
    assert any(
        line.startswith("--Open subscriptions | bash=/usr/bin/open ")
        and "param1=https://ai.input.im/subscriptions" in line
        for line in subscription_lines
    )

    near_exhausted_lines = monitor.render(
        fixture_rows,
        home,
        now="12:34:56",
        subscription_quota_status=status_99_99,
    ).splitlines()
    assert "\u00b7 Q 99% | color=red" in near_exhausted_lines[0]
    assert any("$99.99 / $100.00 \u00b7 99%" in line for line in near_exhausted_lines)
    assert not any("$99.99 / $100.00 \u00b7 100%" in line for line in near_exhausted_lines)

    unavailable_quota_status = monitor.parse_subscription_quota_payload(
        """{
          "ok": true,
          "subscriptions": [{
            "id": "unparsed-plan",
            "name": "Changed DOM Plan",
            "status_text": "Active",
            "quota_state": "unavailable",
            "expires_at": null,
            "quotas": []
          }]
        }"""
    )
    unavailable_quota_lines = monitor.render(
        fixture_rows,
        home,
        now="12:34:56",
        subscription_quota_status=unavailable_quota_status,
    ).splitlines()
    assert unavailable_quota_lines[0].endswith("\u00b7 Q ? | color=orange")
    assert "AI INPUT quota: usage unavailable | color=orange" in (
        unavailable_quota_lines
    )
    assert "----Usage unavailable | color=orange" in unavailable_quota_lines
    assert "----Unlimited | color=green" not in unavailable_quota_lines

    unlimited_quota_status = monitor.parse_subscription_quota_payload(
        """{
          "ok": true,
          "subscriptions": [{
            "id": "unlimited-plan",
            "name": "Explicit Unlimited Plan",
            "status": "active",
            "quota_state": "unlimited",
            "expires_at": null,
            "quotas": []
          }]
        }"""
    )
    unlimited_quota_lines = monitor.render(
        fixture_rows,
        home,
        now="12:34:56",
        subscription_quota_status=unlimited_quota_status,
    ).splitlines()
    assert "\u00b7 Q unlimited | color=" in unlimited_quota_lines[0]
    assert "----Unlimited | color=green" in unlimited_quota_lines

    subscription_status_type = type(subscription_status)
    subscription_failure_expectations = (
        ("not-running", None, "AI INPUT quota: Chrome not running | color=gray"),
        ("not-found", None, "AI INPUT quota: no open account tab | color=gray"),
        (
            "automation-permission",
            None,
            "AI INPUT quota: macOS Automation required | color=orange",
        ),
        (
            "javascript-permission",
            None,
            "AI INPUT quota: Chrome JavaScript required | color=orange",
        ),
        (
            "session-expired",
            None,
            "AI INPUT quota: sign-in required | color=orange",
        ),
        ("error", "fixture quota failure", "AI INPUT quota: unavailable | color=orange"),
    )
    for health, error, expected_line in subscription_failure_expectations:
        failure_lines = monitor.render(
            fixture_rows,
            home,
            now="12:34:56",
            subscription_quota_status=subscription_status_type(
                health=health,
                error=error,
            ),
        ).splitlines()
        assert_supported_xbar_parameters(failure_lines)
        assert failure_lines[0].endswith("· Q ? | color=orange")
        assert expected_line in failure_lines
        if health == "automation-permission":
            assert any("Privacy & Security > Automation" in line for line in failure_lines)
        if health == "javascript-permission":
            assert any("Allow JavaScript from Apple Events" in line for line in failure_lines)
        if error is not None:
            assert f"--{error} | color=gray" in failure_lines

    collector_globals = monitor.collect_subscription_quota_status.__globals__
    original_subscription_runner = collector_globals[
        "run_ai_input_subscriptions_javascript"
    ]
    original_subscription_enabled = collector_globals[
        "AI_INPUT_SUBSCRIPTIONS_ENABLED"
    ]
    original_subscription_direct_enabled = collector_globals[
        "AI_INPUT_SUBSCRIPTIONS_DIRECT_ENABLED"
    ]
    original_subscription_notifier = collector_globals[
        "send_subscription_quota_notification"
    ]
    collector_calls: list[str] = []
    collector_payload = """{
      "ok": true,
      "subscriptions": [{
        "id": "collector-plan",
        "name": "Collector Plan",
        "status_text": "Active",
        "quota_state": "available",
        "expires_at": null,
        "quotas": [{
          "period": "daily",
          "used_usd": 50,
          "limit_usd": 100,
          "reset_at": null
        }]
      }]
    }"""

    def fake_subscription_runner(
        javascript: str = subscription_javascript,
    ) -> tuple[int | None, str | None, str | None]:
        collector_calls.append(javascript)
        return 77, collector_payload, None

    quota_state_file = home / "subscription-quota-state.json"
    try:
        collector_globals["AI_INPUT_SUBSCRIPTIONS_ENABLED"] = True
        # Keep this browser fixture deterministic even when the host Keychain
        # contains real AI.INPUT.IM credentials.  Direct API behavior is
        # covered separately above with explicit fakes.
        collector_globals["AI_INPUT_SUBSCRIPTIONS_DIRECT_ENABLED"] = False
        collector_globals["run_ai_input_subscriptions_javascript"] = (
            fake_subscription_runner
        )
        collector_globals["send_subscription_quota_notification"] = (
            lambda _message: None
        )
        collected_status = monitor.collect_subscription_quota_status(
            quota_state_file,
            now_epoch=2_001_000,
        )
        assert collected_status is not None and collected_status.health == "ready"
        assert len(collector_calls) == 1
        cached_status = monitor.collect_subscription_quota_status(
            quota_state_file,
            now_epoch=2_001_030,
        )
        assert cached_status is not None and cached_status.health == "ready"
        assert len(collector_calls) == 1
        assert quota_state_file.stat().st_mode & 0o777 == 0o600
        quota_state_text = quota_state_file.read_text(encoding="utf-8")
        quota_state_payload = cast(object, json.loads(quota_state_text))
        assert isinstance(quota_state_payload, dict)
        assert cast(dict[str, object], quota_state_payload)["checked_at"] == 2_001_000
        assert not any(
            secret in quota_state_text.lower()
            for secret in ("authorization", "bearer", "cookie", "localstorage")
        )
        refreshed_status = monitor.collect_subscription_quota_status(
            quota_state_file,
            now_epoch=2_001_056,
        )
        assert refreshed_status is not None and refreshed_status.health == "ready"
        assert len(collector_calls) == 2
    finally:
        collector_globals["run_ai_input_subscriptions_javascript"] = (
            original_subscription_runner
        )
        collector_globals["AI_INPUT_SUBSCRIPTIONS_ENABLED"] = (
            original_subscription_enabled
        )
        collector_globals["AI_INPUT_SUBSCRIPTIONS_DIRECT_ENABLED"] = (
            original_subscription_direct_enabled
        )
        collector_globals["send_subscription_quota_notification"] = (
            original_subscription_notifier
        )

    spotify_playing = monitor.parse_spotify_payload(
        '{"playback":"playing","title":"Fixture Song",'
        '"artist":"Fixture Artist","is_ad":false,"media_muted":false}'
    )
    spotify_script = monitor.spotify_apple_script("return JSON.stringify({ok: true})")
    assert "(ASCII character 9)" in spotify_script
    assert " & tab & " not in spotify_script
    scoped_spotify_script = monitor.spotify_apple_script("return 1", tab_id=17)
    assert '(id of spotifyTab as text) is "17"' in scoped_spotify_script
    assert "id of spotifyTab is 17" not in scoped_spotify_script
    assert set(monitor.SPOTIFY_ACTION_JAVASCRIPT) == {"toggle", "previous", "next"}
    assert "control-button-skip-back" in monitor.SPOTIFY_ACTION_JAVASCRIPT["previous"]
    assert "control-button-skip-forward" in monitor.SPOTIFY_ACTION_JAVASCRIPT["next"]
    mute_script = monitor.spotify_mute_javascript(True)
    unmute_script = monitor.spotify_mute_javascript(False)
    assert 'data-testid="volume-bar-toggle-mute-button"' in mute_script
    assert "const desiredMuted = true" in mute_script
    assert "const desiredMuted = false" in unmute_script
    assert "if (changed) button.click()" in mute_script
    assert "Spotify mute control unavailable" in mute_script

    mute_globals = monitor.set_spotify_media_muted.__globals__
    original_spotify_runner = mute_globals["run_spotify_javascript"]
    captured_mute_scripts: list[tuple[str, int | None]] = []

    def confirm_volume_button(
        javascript: str,
        tab_id: int | None = None,
    ) -> tuple[int | None, str | None, str | None]:
        captured_mute_scripts.append((javascript, tab_id))
        return tab_id, '{"ok":true,"method":"volume-button","changed":true}', None

    try:
        mute_globals["run_spotify_javascript"] = confirm_volume_button
        assert monitor.set_spotify_media_muted(17, True) is None
        assert captured_mute_scripts[-1][1] == 17
        assert "const desiredMuted = true" in captured_mute_scripts[-1][0]

        mute_globals["run_spotify_javascript"] = (
            lambda javascript, tab_id=None: (
                tab_id,
                '{"ok":false,"error":"Spotify mute control unavailable"}',
                None,
            )
        )
        assert (
            monitor.set_spotify_media_muted(17, True)
            == "Spotify mute control unavailable"
        )
    finally:
        mute_globals["run_spotify_javascript"] = original_spotify_runner
    spotify_playing_lines = monitor.render(
        fixture_rows,
        home,
        now="12:34:56",
        spotify_status=spotify_playing,
    ).splitlines()
    assert_supported_xbar_parameters(spotify_playing_lines)
    assert "· SP play | color=" in spotify_playing_lines[0]
    assert any(
        line.startswith("Spotify Web: Playing · Fixture Song | color=green")
        for line in spotify_playing_lines
    )
    assert any(
        line.startswith("--Pause Spotify | bash=")
        and "param1=spotify-toggle" in line
        and "refresh=true" in line
        for line in spotify_playing_lines
    )
    assert any(
        line.startswith("--Previous track | bash=")
        and "param1=spotify-previous" in line
        and "refresh=true" in line
        for line in spotify_playing_lines
    )
    assert any(
        line.startswith("--Next track | bash=")
        and "param1=spotify-next" in line
        and "refresh=true" in line
        for line in spotify_playing_lines
    )

    spotify_paused = monitor.parse_spotify_payload(
        '{"playback":"paused","title":"Fixture Song",'
        '"artist":"Fixture Artist","is_ad":false,"media_muted":false}'
    )
    spotify_paused_lines = monitor.render(
        fixture_rows,
        home,
        now="12:34:56",
        spotify_status=spotify_paused,
    ).splitlines()
    assert "· SP pause | color=" in spotify_paused_lines[0]
    assert any(line.startswith("--Play Spotify | bash=") for line in spotify_paused_lines)

    spotify_status_type = type(spotify_playing)
    permission_lines = monitor.render(
        fixture_rows,
        home,
        now="12:34:56",
        spotify_status=spotify_status_type(health="permission"),
    ).splitlines()
    assert any(
        line == "Spotify Web: Chrome permission required | color=orange"
        for line in permission_lines
    )
    assert any(
        "Allow JavaScript from Apple Events" in line for line in permission_lines
    )
    missing_lines = monitor.render(
        fixture_rows,
        home,
        now="12:34:56",
        spotify_status=spotify_status_type(health="not-found"),
    ).splitlines()
    assert any(line.startswith("Spotify Web: no open player tab") for line in missing_lines)
    error_lines = monitor.render(
        fixture_rows,
        home,
        now="12:34:56",
        spotify_status=spotify_status_type(
            health="error", error="fixture AppleScript failure"
        ),
    ).splitlines()
    assert any("fixture AppleScript failure" in line for line in error_lines)

    ad_started, mute_action = monitor.spotify_ad_mute_transition(
        {}, tab_id=17, is_ad=True, media_muted=False
    )
    assert mute_action is True
    assert ad_started == {
        "schema_version": 1,
        "active": True,
        "tab_id": 17,
        "owned": True,
        "prior_muted": False,
    }
    ad_continued, repeated_mute_action = monitor.spotify_ad_mute_transition(
        ad_started, tab_id=17, is_ad=True, media_muted=True
    )
    assert ad_continued == ad_started
    assert repeated_mute_action is None
    ad_ended, restore_action = monitor.spotify_ad_mute_transition(
        ad_continued, tab_id=17, is_ad=False, media_muted=True
    )
    assert ad_ended == {"schema_version": 1, "active": False}
    assert restore_action is False

    premuted_ad, premuted_action = monitor.spotify_ad_mute_transition(
        {}, tab_id=18, is_ad=True, media_muted=True
    )
    assert premuted_ad["owned"] is False
    assert premuted_action is None
    _, premuted_restore_action = monitor.spotify_ad_mute_transition(
        premuted_ad, tab_id=18, is_ad=False, media_muted=True
    )
    assert premuted_restore_action is None
    _, disabled_restore_action = monitor.spotify_ad_mute_transition(
        ad_started,
        tab_id=17,
        is_ad=True,
        media_muted=True,
        enabled=False,
    )
    assert disabled_restore_action is False

    spotify_ad = spotify_status_type(
        health="ready",
        playback="playing",
        title="Advertisement",
        is_ad=True,
        media_muted=True,
        auto_muted=True,
    )
    spotify_ad_lines = monitor.render(
        fixture_rows,
        home,
        now="12:34:56",
        spotify_status=spotify_ad,
    ).splitlines()
    assert "· SP ad | color=orange" in spotify_ad_lines[0]
    assert any(
        line.startswith("Spotify Web: Advertisement · auto-muted")
        for line in spotify_ad_lines
    )

    missing_mapping_home = home / "missing"
    fallback = monitor.runtime_label(
        monitor.AGENT_ADAPTERS[0],
        fixture_rows[100],
        fixture_rows,
        missing_mapping_home,
    )
    assert fallback == "OMP CLI · ttys001 · PID 100", fallback

sample = " 42 1 123.4 2048 01:02 ttys009 /opt/homebrew/bin/omp --flag\n"
parsed = monitor.parse_ps_output(sample)
assert parsed[42].cpu_percent == 123.4
assert parsed[42].rss_bytes == 2 * 1024 * 1024
assert parsed[42].elapsed_seconds == 62
assert parsed[42].tty == "ttys009"
assert parsed[42].executable == "omp"

support_root = next(
    root
    for root in (PLUGIN.parent, PLUGIN.parent / ".personal-xbar")
    if (root / "personal_xbar").is_dir()
)
system_python_render = subprocess.check_output(
    [
        "/usr/bin/python3",
        "-c",
        (
            "import sys; from pathlib import Path; "
            "sys.path.insert(0, sys.argv[1]); "
            "from personal_xbar.plugins.processes import ProcessInventoryPlugin; "
            "from personal_xbar.registry import ExecutionContext; "
            "context = ExecutionContext(entrypoint=Path(sys.argv[2]), "
            "values={'process_rows': {}}); "
            "print(ProcessInventoryPlugin().render(context))"
        ),
        str(support_root),
        str(PLUGIN),
    ],
    text=True,
)
assert system_python_render.startswith("AI "), system_python_render.splitlines()[:1]

with tempfile.TemporaryDirectory() as status_state_directory:
    quota_cache_path = Path(status_state_directory) / "subscription-quota.json"
    _ = quota_cache_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "checked_at": int(time.time()),
                "health": "ready",
                "quota_levels": {"entry-plan:daily": 0},
                "status": {
                    "health": "ready",
                    "error": None,
                    "plans": [
                        {
                            "id": "entry-plan",
                            "name": "Entrypoint Plan",
                            "status": "active",
                            "expires_at": None,
                            "quota_state": "available",
                            "quotas": [
                                {
                                    "period": "daily",
                                    "used_cents": 5_000,
                                    "limit_cents": 10_000,
                                    "reset_at": None,
                                }
                            ],
                        }
                    ],
                },
            },
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
    )
    quota_cache_path.chmod(0o600)
    live_environment = os.environ.copy()
    live_environment["AI_INPUT_NOTIFICATIONS"] = "0"
    live_environment["AI_INPUT_SUBSCRIPTIONS_ENABLED"] = "1"
    live_environment["AI_INPUT_SUBSCRIPTIONS_NOTIFICATIONS"] = "0"
    live_environment["AI_INPUT_SUBSCRIPTIONS_STATE_FILE"] = str(quota_cache_path)
    live_environment["SPOTIFY_WEB_ENABLED"] = "0"
    live_environment["AI_INPUT_MONITOR_STATE_FILE"] = str(
        Path(status_state_directory) / "ai-input-status.json"
    )
    live_output = subprocess.check_output(
        [str(PLUGIN)],
        text=True,
        env=live_environment,
    )
live_lines = live_output.splitlines()
assert_supported_xbar_parameters(live_lines)
assert live_lines and live_lines[0].startswith("AI "), live_lines[:1]
assert "· API " in live_lines[0], live_lines[:1]
assert "· Q 50%" in live_lines[0], live_lines[:1]
assert "---" in live_lines
assert any(line.startswith("AI.INPUT.IM:") for line in live_lines)
assert "AI INPUT quota: 50% max | color=green" in live_lines
assert any("$50.00 / $100.00 · 50%" in line for line in live_lines)
assert any(line.startswith("Open Activity Monitor") for line in live_lines)
version_line = next(
    line
    for line in PLUGIN.read_text(encoding="utf-8").splitlines()
    if line.startswith("# <xbar.version>")
)
version = version_line.removeprefix("# <xbar.version>").removesuffix(
    "</xbar.version>"
)
print(f"Personal xbar contract passed: {PLUGIN} (v{version})")
