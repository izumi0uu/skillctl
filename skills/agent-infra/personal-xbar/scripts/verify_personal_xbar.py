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
from contextlib import contextmanager
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
            key, assignment, _value = parameter.partition("=")
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
    source: str | None


class SpotifyStatusLike(Protocol):
    health: str
    playback: str
    title: str | None
    artist: str | None
    is_ad: bool
    media_muted: bool | None
    auto_muted: bool
    error: str | None


class TitleBarSettingsLike(Protocol):
    hidden: frozenset[str]

    def is_visible(self, component: str) -> bool: ...


class RegistryLike(Protocol):
    plugin_ids: tuple[str, ...]
    action_ids: tuple[str, ...]

    def execute(self, entrypoint: Path, arguments: list[str]) -> str | None: ...


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
    SPOTIFY_ACTION_JAVASCRIPT: dict[str, str]
    TITLE_COMPONENTS: tuple[tuple[str, str], ...]
    TitleBarSettings: Callable[..., TitleBarSettingsLike]
    subprocess: PatchableSubprocess
    sqlite3: PatchableSqlite
    ai_input_auth: object

    def build_registry(
        self,
        title_settings_file: Path | None = None,
    ) -> RegistryLike: ...

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
        plugin_path: Path | None = None,
        title_settings: TitleBarSettingsLike | None = None,
    ) -> str: ...

    def read_title_bar_settings(self, path: Path) -> TitleBarSettingsLike: ...

    def write_title_bar_settings(
        self,
        settings: TitleBarSettingsLike,
        path: Path,
    ) -> None: ...

    def toggle_title_component(self, component: str, path: Path) -> None: ...

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

    def subscription_quota_level(self, quota: SubscriptionQuotaLike) -> int: ...

    def subscription_quota_percent_label(
        self,
        quota: SubscriptionQuotaLike,
    ) -> str: ...

    def subscription_quota_remaining_percent(
        self,
        quota: SubscriptionQuotaLike,
    ) -> int: ...

    def subscription_quota_remaining_percent_label(
        self,
        quota: SubscriptionQuotaLike,
    ) -> str: ...

    def subscription_quota_total(
        self,
        status: SubscriptionQuotaStatusLike,
    ) -> SubscriptionQuotaLike | None: ...

    def subscription_quota_notification_transition(
        self,
        previous: dict[str, object],
        status: SubscriptionQuotaStatusLike,
        checked_at: int,
    ) -> tuple[dict[str, object], tuple[str, ...]]: ...

    def parse_spotify_payload(self, payload: str) -> SpotifyStatusLike: ...

    def spotify_jxa_script(
        self,
        javascript: str,
        tab_id: int | None = None,
    ) -> str: ...

    def run_spotify_javascript(
        self,
        javascript: str,
        tab_id: int | None = None,
    ) -> tuple[int | None, str | None, str | None]: ...

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
    "title-settings",
    "processes",
)
assert monitor.build_registry().action_ids == (
    "spotify-next",
    "spotify-previous",
    "spotify-toggle",
    "title-toggle-agents",
    "title-toggle-api",
    "title-toggle-cpu",
    "title-toggle-memory",
    "title-toggle-quota",
    "title-toggle-spotify",
)
for removed_browser_quota_api in (
    "AI_INPUT_SUBSCRIPTIONS_JAVASCRIPT",
    "parse_subscription_quota_payload",
    "run_ai_input_subscriptions_javascript",
):
    assert not hasattr(monitor, removed_browser_quota_api), removed_browser_quota_api

manager_path = Path(__file__).resolve().with_name("manage_personal_xbar.py")
manager_spec = importlib.util.spec_from_file_location("personal_xbar_manager", manager_path)
assert manager_spec is not None and manager_spec.loader is not None
manager_module = importlib.util.module_from_spec(manager_spec)
sys.modules[manager_spec.name] = manager_module
manager_spec.loader.exec_module(manager_module)
parsed_auth_set = manager_module.build_parser().parse_args(
    [
        "auth",
        "set",
        "--expires-in",
        "900",
        "--user-agent",
        "Fixture Client/123",
    ]
)
assert parsed_auth_set.command == "auth"
assert parsed_auth_set.auth_command == "set"
assert parsed_auth_set.expires_in == 900
assert parsed_auth_set.user_agent == "Fixture Client/123"

auth_module_for_manager = monitor.ai_input_auth
original_manager_loader = manager_module.load_auth_modules
original_getpass = manager_module.getpass.getpass
original_manager_writer = auth_module_for_manager.write_credentials
original_manager_deleter = auth_module_for_manager.delete_credentials
original_manager_lock = monitor.ai_input_refresh_lock
manager_inputs = iter(("manager-access-secret", "manager-refresh-secret"))
manager_written: list[object] = []
manager_events: list[str] = []
manager_prompts: list[str] = []


def fake_manager_getpass(prompt: str) -> str:
    manager_prompts.append(prompt)
    manager_events.append("prompt")
    return next(manager_inputs)


def fake_manager_writer(credentials: object) -> None:
    manager_events.append("write")
    manager_written.append(credentials)


def fake_manager_deleter() -> None:
    manager_events.append("delete")


@contextmanager
def fake_manager_lock(_state_file: Path) -> object:
    manager_events.append("lock-enter")
    try:
        yield
    finally:
        manager_events.append("lock-exit")


try:
    manager_module.load_auth_modules = lambda: (auth_module_for_manager, monitor)
    manager_module.getpass.getpass = fake_manager_getpass
    auth_module_for_manager.write_credentials = fake_manager_writer
    auth_module_for_manager.delete_credentials = fake_manager_deleter
    monitor.ai_input_refresh_lock = fake_manager_lock
    manager_auth_output = manager_module.auth_set(900, "Fixture Client/123")
    manager_delete_output = manager_module.auth_delete()
finally:
    manager_module.load_auth_modules = original_manager_loader
    manager_module.getpass.getpass = original_getpass
    auth_module_for_manager.write_credentials = original_manager_writer
    auth_module_for_manager.delete_credentials = original_manager_deleter
    monitor.ai_input_refresh_lock = original_manager_lock
assert len(manager_written) == 1
assert manager_events == [
    "prompt",
    "prompt",
    "lock-enter",
    "write",
    "lock-exit",
    "lock-enter",
    "delete",
    "lock-exit",
]
manager_auth_text = json.dumps(manager_auth_output)
assert "manager-access-secret" not in manager_auth_text
assert "manager-refresh-secret" not in manager_auth_text
assert manager_auth_output["status"] == "configured"
assert manager_auth_output["credentials"]["has_user_agent"] is True
assert manager_delete_output["status"] == "deleted"
assert manager_prompts == [
    "AI.INPUT.IM access token (paste value only; omit 'Bearer ' prefix, hidden): ",
    "AI.INPUT.IM refresh token (paste value only, hidden): ",
]

try:
    manager_module.getpass.getpass = lambda _prompt: "Bearer manager-access-secret"
    try:
        manager_module.auth_set(900, "Fixture Client/123")
    except manager_module.MonitorManagerError as error:
        assert str(error) == (
            "paste the access token value only; omit the 'Bearer ' prefix"
        )
    else:
        raise AssertionError("Bearer access-token prefix was accepted")
finally:
    manager_module.getpass.getpass = original_getpass


def warning_getpass(_prompt: str) -> str:
    manager_module.warnings.warn(
        "Password input may be echoed",
        manager_module.getpass.GetPassWarning,
    )
    return "must-not-be-read"


try:
    manager_module.getpass.getpass = warning_getpass
    try:
        _ = manager_module.hidden_credential("fixture: ")
    except manager_module.MonitorManagerError:
        pass
    else:
        raise AssertionError("getpass echo fallback was accepted")
finally:
    manager_module.getpass.getpass = original_getpass

with tempfile.TemporaryDirectory() as temporary_directory:
    home = Path(temporary_directory)
    title_settings_path = home / "preferences" / "title-settings.json"
    title_settings_path.parent.mkdir()
    title_components = tuple(
        component for component, _label in monitor.TITLE_COMPONENTS
    )
    assert title_components == (
        "agents",
        "cpu",
        "memory",
        "api",
        "quota",
        "spotify",
    )
    default_title_settings = monitor.read_title_bar_settings(title_settings_path)
    assert all(
        default_title_settings.is_visible(component)
        for component in title_components
    )

    for invalid_state in (
        "{",
        "[]",
        '{"schema_version":2,"title_visibility":{"cpu":false}}',
        '{"schema_version":1,"title_visibility":[]}',
    ):
        _ = title_settings_path.write_text(invalid_state, encoding="utf-8")
        invalid_settings = monitor.read_title_bar_settings(title_settings_path)
        assert all(
            invalid_settings.is_visible(component)
            for component in title_components
        )

    _ = title_settings_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "title_visibility": {
                    "cpu": False,
                    "memory": 0,
                    "future-field": False,
                },
            }
        ),
        encoding="utf-8",
    )
    partial_title_settings = monitor.read_title_bar_settings(title_settings_path)
    assert partial_title_settings.is_visible("cpu") is False
    assert partial_title_settings.is_visible("memory") is True
    assert partial_title_settings.is_visible("api") is True

    title_settings_path.chmod(0o644)
    monitor.toggle_title_component("cpu", title_settings_path)
    assert monitor.read_title_bar_settings(title_settings_path).is_visible("cpu")
    assert title_settings_path.stat().st_mode & 0o777 == 0o600
    title_lock_path = title_settings_path.with_name(
        f".{title_settings_path.name}.lock"
    )
    assert title_lock_path.stat().st_mode & 0o777 == 0o600
    normalized_title_payload = json.loads(
        title_settings_path.read_text(encoding="utf-8")
    )
    assert set(normalized_title_payload["title_visibility"]) == set(
        title_components
    )
    assert not list(title_settings_path.parent.glob("*.tmp"))

    try:
        monitor.toggle_title_component("unknown", title_settings_path)
    except ValueError as error:
        assert str(error) == "unsupported title component"
    else:
        raise AssertionError("unknown title component was accepted")

    registry_settings_path = home / "registry-preferences.json"
    title_registry = monitor.build_registry(registry_settings_path)
    assert title_registry.execute(PLUGIN, ["title-toggle-cpu"]) is None
    assert (
        monitor.read_title_bar_settings(registry_settings_path).is_visible("cpu")
        is False
    )
    reloaded_title_registry = monitor.build_registry(registry_settings_path)
    assert reloaded_title_registry.execute(PLUGIN, ["title-toggle-cpu"]) is None
    assert monitor.read_title_bar_settings(registry_settings_path).is_visible("cpu")
    for invalid_arguments in (
        ["title-toggle-unknown"],
        ["title-toggle-cpu", "unexpected"],
    ):
        try:
            title_registry.execute(PLUGIN, invalid_arguments)
        except ValueError as error:
            assert str(error) == "unsupported Personal xbar action"
        else:
            raise AssertionError("unsupported title action was accepted")

    concurrent_settings_path = home / "concurrent-preferences.json"
    concurrent_barrier = threading.Barrier(3)

    def concurrent_toggle(component: str) -> None:
        concurrent_barrier.wait()
        monitor.toggle_title_component(component, concurrent_settings_path)

    concurrent_threads = [
        threading.Thread(target=concurrent_toggle, args=(component,))
        for component in ("cpu", "quota")
    ]
    for thread in concurrent_threads:
        thread.start()
    concurrent_barrier.wait()
    for thread in concurrent_threads:
        thread.join()
    concurrent_settings = monitor.read_title_bar_settings(
        concurrent_settings_path
    )
    assert concurrent_settings.is_visible("cpu") is False
    assert concurrent_settings.is_visible("quota") is False

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

    subscription_status = monitor.parse_subscription_api_payload(
        {
            "code": 0,
            "data": [
                {
                    "id": "fixture-plan",
                    "status": "ACTIVE",
                    "expires_at": 4_102_444_800,
                    "daily_usage_usd": "79.995",
                    "weekly_usage_usd": "231.275",
                    "monthly_usage_usd": 0,
                    "group": {
                        "name": "Fixture CodeX Plan",
                        "daily_limit_usd": "100.00",
                        "weekly_limit_usd": "300.00",
                        "monthly_limit_usd": None,
                    },
                }
            ],
        },
        now_epoch=2_000_000,
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
    fixture_total = monitor.subscription_quota_total(subscription_status)
    assert fixture_total is not None
    assert fixture_total.period == "daily"
    assert fixture_total.used_cents == 8_000
    assert fixture_total.limit_cents == 10_000

    weighted_total_status = monitor.parse_subscription_api_payload(
        {
            "code": 0,
            "data": [
                {
                    "id": "small-exhausted-plan",
                    "status": "active",
                    "daily_usage_usd": 100,
                    "group": {
                        "name": "Small Exhausted Plan",
                        "daily_limit_usd": 100,
                    },
                },
                {
                    "id": "large-unused-plan",
                    "status": "active",
                    "daily_usage_usd": 0,
                    "group": {
                        "name": "Large Unused Plan",
                        "daily_limit_usd": 300,
                    },
                },
            ],
        },
        now_epoch=2_000_000,
    )
    weighted_total = monitor.subscription_quota_total(weighted_total_status)
    assert weighted_total is not None
    assert weighted_total.period == "daily"
    assert weighted_total.used_cents == 10_000
    assert weighted_total.limit_cents == 40_000
    assert monitor.subscription_quota_percent_label(weighted_total) == "25%"
    assert monitor.subscription_quota_remaining_percent(weighted_total) == 75
    weighted_total_lines = monitor.render(
        fixture_rows,
        home,
        now="12:34:56",
        subscription_quota_status=weighted_total_status,
    ).splitlines()
    assert "· Q 75% | color=" in weighted_total_lines[0]
    assert "AI INPUT quota: 75% left | color=green" in weighted_total_lines

    exhausted_total_status = monitor.parse_subscription_api_payload(
        {
            "code": 0,
            "data": [
                {
                    "id": "codex-plus-plan",
                    "status": "active",
                    "daily_usage_usd": "500.49",
                    "group": {
                        "name": "CodeX Plus",
                        "daily_limit_usd": "500.00",
                    },
                },
                {
                    "id": "codex-air-plan",
                    "status": "active",
                    "daily_usage_usd": "300.33",
                    "group": {
                        "name": "CodeX Air",
                        "daily_limit_usd": "300.00",
                    },
                },
            ],
        },
        now_epoch=2_000_000,
    )
    exhausted_total = monitor.subscription_quota_total(exhausted_total_status)
    assert exhausted_total is not None
    assert exhausted_total.used_cents == 80_082
    assert exhausted_total.limit_cents == 80_000
    assert monitor.subscription_quota_remaining_percent(exhausted_total) == 0
    exhausted_total_lines = monitor.render(
        fixture_rows,
        home,
        now="12:34:56",
        subscription_quota_status=exhausted_total_status,
    ).splitlines()
    assert "\u00b7 Q 0% | color=red" in exhausted_total_lines[0]
    assert "AI INPUT quota: 0% left | color=red" in exhausted_total_lines

    original_quota_collector = monitor.collect_subscription_quota_api_status
    try:
        manager_module.load_auth_modules = lambda: (auth_module_for_manager, monitor)
        monitor.collect_subscription_quota_api_status = (
            lambda _state_file, now_epoch=None: weighted_total_status
        )
        manager_auth_test_output = manager_module.auth_test()
    finally:
        manager_module.load_auth_modules = original_manager_loader
        monitor.collect_subscription_quota_api_status = original_quota_collector
    assert manager_auth_test_output["remaining_percent"] == 75
    assert manager_auth_test_output["total_period"] == "daily"
    assert "total_percent" not in manager_auth_test_output
    assert "max_percent" not in manager_auth_test_output

    direct_subscription_payload = {
        "code": 0,
        "message": "success",
        "data": [
            {
                "id": 42,
                "status": "active",
                "expires_at": "2030-01-02T00:00:00Z",
                "daily_window_start": "2029-12-31T12:00:00Z",
                "weekly_window_start": None,
                "monthly_window_start": "2029-12-20T00:00:00Z",
                "daily_usage_usd": 79.995,
                "weekly_usage_usd": 0,
                "monthly_usage_usd": 231.275,
                "group": {
                    "name": "Direct API Plan",
                    "daily_limit_usd": 100,
                    "weekly_limit_usd": None,
                    "monthly_limit_usd": 300,
                },
            }
        ],
    }
    direct_status = monitor.parse_subscription_api_payload(
        direct_subscription_payload,
        now_epoch=1_700_000_000,
    )
    assert direct_status.health == "ready"
    assert direct_status.source == "api"
    assert len(direct_status.plans) == 1
    direct_plan = direct_status.plans[0]
    assert direct_plan.plan_id == "42"
    assert direct_plan.name == "Direct API Plan"
    assert direct_plan.status == "active"
    assert [quota.period for quota in direct_plan.quotas] == ["daily", "monthly"]
    assert [quota.used_cents for quota in direct_plan.quotas] == [8_000, 23_128]
    assert [quota.limit_cents for quota in direct_plan.quotas] == [10_000, 30_000]
    assert direct_plan.quotas[0].reset_at == 1_893_499_200
    assert direct_plan.quotas[1].reset_at == direct_plan.expires_at

    unlimited_direct_status = monitor.parse_subscription_api_payload(
        {
            "code": 0,
            "data": [
                {
                    "id": "unlimited-api",
                    "status": "active",
                    "expires_at": None,
                    "daily_usage_usd": 0,
                    "weekly_usage_usd": 0,
                    "monthly_usage_usd": 0,
                    "group": {
                        "name": "Unlimited API Plan",
                        "daily_limit_usd": None,
                        "weekly_limit_usd": None,
                        "monthly_limit_usd": None,
                    },
                }
            ],
        },
        now_epoch=1_700_000_000,
    )
    assert unlimited_direct_status.plans[0].quota_state == "unlimited"
    partial_group_status = monitor.parse_subscription_api_payload(
        {
            "code": 0,
            "data": [
                {
                    "id": "partial-api",
                    "status": "active",
                    "expires_at": None,
                    "group": {"name": "Partial API Plan"},
                }
            ],
        },
        now_epoch=1_700_000_000,
    )
    assert partial_group_status.plans[0].quota_state == "unavailable"

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
    jwt_access = "e30.eyJleHAiOjIwMDAwMDAwMDB9.fixture"
    keychain_credentials = auth_module.make_credentials(
        jwt_access,
        "refresh-fixture-secret",
        user_agent="Fixture Client/123",
    )
    try:
        _ = auth_module.make_credentials(
            "access-fixture\ninjected-header",
            "refresh-fixture-secret",
        )
    except auth_module.AuthError:
        pass
    else:
        raise AssertionError("credential header injection was accepted")
    try:
        _ = auth_module.make_credentials(
            "access-fixture",
            "refresh-fixture-secret",
            user_agent="Fixture Client\ninjected-header",
        )
    except auth_module.AuthError:
        pass
    else:
        raise AssertionError("user-agent header injection was accepted")
    non_finite_jwt = "e30.eyJleHAiOk5hTn0.fixture"
    assert auth_module.make_credentials(
        non_finite_jwt,
        "refresh-fixture-secret",
    ).expires_at is None
    assert keychain_credentials.expires_at == 2_000_000_000
    assert keychain_credentials.user_agent == "Fixture Client/123"
    auth_module.write_credentials(keychain_credentials, memory_keychain)
    assert auth_module.read_credentials(memory_keychain) == keychain_credentials
    redacted_representation = repr(keychain_credentials)
    assert jwt_access not in redacted_representation
    assert "refresh-fixture-secret" not in redacted_representation
    assert "Fixture Client/123" not in redacted_representation
    redacted_summary = auth_module.credentials_summary(
        keychain_credentials, 1_999_999_900
    )
    assert "access_token" not in redacted_summary
    assert "refresh_token" not in redacted_summary
    assert redacted_summary["has_user_agent"] is True
    auth_module.delete_credentials(memory_keychain)
    assert auth_module.read_credentials(memory_keychain) is None

    redirect_handler = monitor.ExactAiInputRedirectHandler()
    redirect_request = urllib.request.Request(
        "https://ai.input.im/api/v1/subscriptions"
    )
    try:
        _ = redirect_handler.redirect_request(
            redirect_request,
            None,
            302,
            "Found",
            {},
            "https://example.invalid/capture",
        )
    except monitor.AiInputApiError as error:
        assert error.kind == "redirect"
    else:
        raise AssertionError("cross-origin AI INPUT redirect was accepted")
    same_origin_redirect = redirect_handler.redirect_request(
        redirect_request,
        None,
        302,
        "Found",
        {},
        "https://ai.input.im/api/v1/subscriptions?next=1",
    )
    assert same_origin_redirect is not None
    assert same_origin_redirect.full_url.startswith("https://ai.input.im/api/v1/")

    captured_api_requests: list[urllib.request.Request] = []

    class FixtureApiResponse:
        status = 200
        headers = {"Content-Length": "20"}

        def __enter__(self) -> FixtureApiResponse:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def read(self, _limit: int) -> bytes:
            return b'{"code":0,"data":[]}'

    class FixtureApiOpener:
        def open(
            self,
            request: urllib.request.Request,
            timeout: float,
        ) -> FixtureApiResponse:
            assert timeout == monitor.AI_INPUT_API_TIMEOUT_SECONDS
            captured_api_requests.append(request)
            return FixtureApiResponse()

    original_build_opener = urllib.request.build_opener
    try:
        urllib.request.build_opener = lambda *_handlers: FixtureApiOpener()
        _ = monitor.api_request_json(
            "/subscriptions",
            "fixture-access-secret",
            user_agent="Fixture Client/123",
        )
    finally:
        urllib.request.build_opener = original_build_opener
    assert len(captured_api_requests) == 1
    captured_request = captured_api_requests[0]
    assert captured_request.full_url == "https://ai.input.im/api/v1/subscriptions"
    assert captured_request.get_header("User-agent") == "Fixture Client/123"
    assert captured_request.get_header("Authorization") == (
        "Bearer fixture-access-secret"
    )

    direct_globals = monitor.collect_subscription_quota_api_status.__globals__
    original_credential_reader = direct_globals["read_ai_input_credentials"]
    original_credential_writer = direct_globals["write_ai_input_credentials"]
    original_api_request = direct_globals["api_request_json"]
    original_refresh_lock_file = direct_globals["AI_INPUT_REFRESH_LOCK_FILE"]
    credential_box = {
        "value": auth_module.make_credentials(
            "access-before-refresh",
            "refresh-before-rotation",
            2_001_900,
            "Fixture Client/123",
        )
    }
    written_credentials: list[object] = []
    direct_api_calls: list[str] = []

    def fake_credential_reader() -> object:
        return credential_box["value"]

    def fake_credential_writer(credentials: object) -> None:
        credential_box["value"] = credentials
        written_credentials.append(credentials)

    def retrying_api_request(
        path: str,
        access_token: str | None = None,
        *,
        method: str = "GET",
        body: dict[str, object] | None = None,
        user_agent: str | None = None,
    ) -> object:
        assert user_agent == "Fixture Client/123"
        if path == "/auth/refresh":
            direct_api_calls.append("refresh")
            assert method == "POST"
            assert body == {"refresh_token": "refresh-before-rotation"}
            return {
                "code": 0,
                "data": {
                    "access_token": "access-after-refresh",
                    "refresh_token": "refresh-after-rotation",
                    "expires_in": 600,
                    "token_type": "Bearer",
                },
            }
        assert path.startswith("/subscriptions")
        direct_api_calls.append(f"subscriptions:{access_token}")
        if access_token == "access-before-refresh":
            return {"code": 401, "message": "authorization expired", "data": None}
        assert access_token == "access-after-refresh"
        return direct_subscription_payload

    try:
        direct_globals["read_ai_input_credentials"] = fake_credential_reader
        direct_globals["write_ai_input_credentials"] = fake_credential_writer
        direct_globals["api_request_json"] = retrying_api_request
        direct_globals["AI_INPUT_REFRESH_LOCK_FILE"] = home / "api-refresh.lock"
        retried_direct_status = monitor.collect_subscription_quota_api_status(
            home / "direct-api-state.json",
            now_epoch=2_001_000,
        )
        assert retried_direct_status.health == "ready"
        assert direct_api_calls == [
            "subscriptions:access-before-refresh",
            "refresh",
            "subscriptions:access-after-refresh",
        ]
        assert len(written_credentials) == 1
        rotated = credential_box["value"]
        assert rotated.access_token == "access-after-refresh"
        assert rotated.refresh_token == "refresh-after-rotation"
        assert rotated.expires_at == 2_001_600
        assert rotated.user_agent == "Fixture Client/123"
        persisted_status, _ = monitor.subscription_quota_notification_transition(
            {}, retried_direct_status, checked_at=2_001_000
        )
        persisted_text = json.dumps(persisted_status)
        assert not any(
            secret in persisted_text
            for secret in (
                "access-before-refresh",
                "refresh-before-rotation",
                "access-after-refresh",
                "refresh-after-rotation",
            )
        )

        credential_box["value"] = auth_module.make_credentials(
            "proactive-old-access",
            "proactive-old-refresh",
            2_002_060,
            "Fixture Client/123",
        )
        written_credentials.clear()
        proactive_calls: list[str] = []

        def proactive_api_request(
            path: str,
            access_token: str | None = None,
            *,
            method: str = "GET",
            body: dict[str, object] | None = None,
            user_agent: str | None = None,
        ) -> object:
            assert user_agent == "Fixture Client/123"
            if path == "/auth/refresh":
                proactive_calls.append("refresh")
                assert body == {"refresh_token": "proactive-old-refresh"}
                return {
                    "code": 0,
                    "data": {
                        "access_token": "proactive-new-access",
                        "refresh_token": "proactive-new-refresh",
                        "expires_in": 900,
                    },
                }
            proactive_calls.append(f"subscriptions:{access_token}")
            return direct_subscription_payload

        direct_globals["api_request_json"] = proactive_api_request
        proactive_status = monitor.collect_subscription_quota_api_status(
            home / "proactive-api-state.json",
            now_epoch=2_002_000,
        )
        assert proactive_status.health == "ready"
        assert proactive_calls == ["refresh", "subscriptions:proactive-new-access"]
        assert len(written_credentials) == 1

        expired_credentials = auth_module.make_credentials(
            "concurrent-old-access",
            "concurrent-old-refresh",
            2_003_000,
            "Fixture Client/123",
        )
        credential_box["value"] = expired_credentials
        written_credentials.clear()
        concurrent_refresh_calls: list[str] = []

        def concurrent_api_request(
            path: str,
            access_token: str | None = None,
            *,
            method: str = "GET",
            body: dict[str, object] | None = None,
            user_agent: str | None = None,
        ) -> object:
            assert user_agent == "Fixture Client/123"
            assert path == "/auth/refresh"
            assert body == {"refresh_token": "concurrent-old-refresh"}
            concurrent_refresh_calls.append("refresh")
            time.sleep(0.03)
            return {
                "code": 0,
                "data": {
                    "access_token": "concurrent-new-access",
                    "refresh_token": "concurrent-new-refresh",
                    "expires_in": 900,
                },
            }

        direct_globals["api_request_json"] = concurrent_api_request
        refresh_function = direct_globals["refresh_ai_input_credentials"]
        concurrent_results: list[object] = []

        def refresh_worker() -> None:
            concurrent_results.append(
                refresh_function(
                    expired_credentials,
                    home / "concurrent-api-state.json",
                    2_003_000,
                    force=False,
                )
            )

        workers = [threading.Thread(target=refresh_worker) for _ in range(2)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(timeout=2)
            assert not worker.is_alive()
        assert concurrent_refresh_calls == ["refresh"]
        assert len(written_credentials) == 1
        assert len(concurrent_results) == 2
        assert all(
            result.access_token == "concurrent-new-access"
            for result in concurrent_results
        )
        invalid_lock_parent = home / "refresh-lock-parent-file"
        _ = invalid_lock_parent.write_text("not a directory", encoding="utf-8")
        direct_globals["AI_INPUT_REFRESH_LOCK_FILE"] = invalid_lock_parent / "lock"
        try:
            with monitor.ai_input_refresh_lock(home / "unused-state.json"):
                pass
        except monitor.AiInputApiError as error:
            assert error.kind == "lock"
        else:
            raise AssertionError("refresh lock setup failure escaped redaction")
    finally:
        direct_globals["read_ai_input_credentials"] = original_credential_reader
        direct_globals["write_ai_input_credentials"] = original_credential_writer
        direct_globals["api_request_json"] = original_api_request
        direct_globals["AI_INPUT_REFRESH_LOCK_FILE"] = original_refresh_lock_file

    def threshold_status(used_usd: str) -> SubscriptionQuotaStatusLike:
        return monitor.parse_subscription_api_payload(
            {
                "code": 0,
                "data": [
                    {
                        "id": "threshold-plan",
                        "status": "active",
                        "expires_at": None,
                        "daily_usage_usd": used_usd,
                        "group": {
                            "name": "Threshold Plan",
                            "daily_limit_usd": 100,
                        },
                    }
                ],
            },
            now_epoch=2_000_000,
        )

    status_79_99 = threshold_status("79.99")
    status_80 = threshold_status("80")
    status_90 = threshold_status("90")
    status_99_99 = threshold_status("99.99")
    status_100 = threshold_status("100")
    status_over_limit = threshold_status("100.01")
    assert monitor.subscription_quota_level(status_79_99.plans[0].quotas[0]) == 0
    assert monitor.subscription_quota_level(status_80.plans[0].quotas[0]) == 1
    assert monitor.subscription_quota_level(status_90.plans[0].quotas[0]) == 2
    assert monitor.subscription_quota_level(status_99_99.plans[0].quotas[0]) == 2
    assert monitor.subscription_quota_level(status_100.plans[0].quotas[0]) == 3
    assert (
        monitor.subscription_quota_percent_label(status_99_99.plans[0].quotas[0])
        == "99%"
    )
    assert (
        monitor.subscription_quota_remaining_percent_label(
            status_99_99.plans[0].quotas[0]
        )
        == "1%"
    )
    assert (
        monitor.subscription_quota_remaining_percent(
            status_100.plans[0].quotas[0]
        )
        == 0
    )
    assert (
        monitor.subscription_quota_remaining_percent(
            status_over_limit.plans[0].quotas[0]
        )
        == 0
    )

    for status_text in ("Inactive", "Not active", "\u65e0\u6548"):
        inactive_status = monitor.parse_subscription_api_payload(
            {
                "code": 0,
                "data": [
                    {
                        "id": f"inactive-{status_text}",
                        "name": "Inactive Fixture",
                        "status": status_text,
                        "expires_at": None,
                    }
                ],
            },
            now_epoch=2_000_000,
        )
        assert inactive_status.plans[0].status == "inactive"

    duplicate_plan_status = monitor.parse_subscription_api_payload(
        {
            "code": 0,
            "data": [
                {
                    "id": "duplicate-plan-0",
                    "name": "Duplicate Plan",
                    "status": "active",
                    "expires_at": 4_102_444_800,
                    "daily_usage_usd": 90,
                    "group": {"daily_limit_usd": 100},
                },
                {
                    "id": "duplicate-plan-1",
                    "name": "Duplicate Plan",
                    "status": "active",
                    "expires_at": 4_102_444_800,
                    "daily_usage_usd": 70,
                    "group": {"daily_limit_usd": 100},
                },
            ],
        },
        now_epoch=2_000_000,
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
    _, exhausted_notice = monitor.subscription_quota_notification_transition(
        {},
        status_100,
        checked_at=2_000_451,
    )
    assert exhausted_notice == (
        "Quota exhausted: Threshold Plan daily 100%",
    )
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
    assert "· Q 20% | color=" in subscription_lines[0]
    assert "AI INPUT quota: 20% left | color=orange" in subscription_lines
    assert "--Fixture CodeX Plan" in subscription_lines
    assert (
        "----Daily · $80.00 / $100.00 · 80% used | color=orange"
        in subscription_lines
    )
    assert (
        "----Weekly · $231.28 / $300.00 · 77% used | color=green"
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
    assert "\u00b7 Q 1% | color=red" in near_exhausted_lines[0]
    assert "AI INPUT quota: 1% left | color=red" in near_exhausted_lines
    assert any(
        "$99.99 / $100.00 \u00b7 99% used" in line
        for line in near_exhausted_lines
    )

    for exhausted_status in (status_100, status_over_limit):
        exhausted_lines = monitor.render(
            fixture_rows,
            home,
            now="12:34:56",
            subscription_quota_status=exhausted_status,
        ).splitlines()
        assert "\u00b7 Q 0% | color=red" in exhausted_lines[0]
        assert "AI INPUT quota: 0% left | color=red" in exhausted_lines
        assert any(
            "$100.00 / $100.00 \u00b7 100% used" in line
            or "$100.01 / $100.00 \u00b7 100% used" in line
            for line in exhausted_lines
        )
    assert not any("$99.99 / $100.00 \u00b7 100%" in line for line in near_exhausted_lines)

    unavailable_quota_status = monitor.parse_subscription_api_payload(
        {
            "code": 0,
            "data": [
                {
                    "id": "unparsed-plan",
                    "name": "Partial API Plan",
                    "status": "active",
                    "expires_at": None,
                    "group": {},
                }
            ],
        },
        now_epoch=2_000_000,
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

    unlimited_quota_status = monitor.parse_subscription_api_payload(
        {
            "code": 0,
            "data": [
                {
                    "id": "unlimited-plan",
                    "name": "Explicit Unlimited Plan",
                    "status": "active",
                    "expires_at": None,
                    "group": {
                        "daily_limit_usd": None,
                        "weekly_limit_usd": None,
                        "monthly_limit_usd": None,
                    },
                }
            ],
        },
        now_epoch=2_000_000,
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
        (
            "not-configured",
            None,
            "AI INPUT quota: secure token not configured | color=gray",
        ),
        (
            "session-expired",
            None,
            "AI INPUT quota: token refresh required | color=orange",
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
        if error is not None:
            assert f"--{error} | color=gray" in failure_lines

    collector_globals = monitor.collect_subscription_quota_status.__globals__
    original_subscription_enabled = collector_globals[
        "AI_INPUT_SUBSCRIPTIONS_ENABLED"
    ]
    original_direct_collector = collector_globals["_direct_subscription_status"]
    original_subscription_notifier = collector_globals[
        "send_subscription_quota_notification"
    ]
    collector_calls: list[tuple[Path, int]] = []

    def fake_direct_collector(
        state_file: Path,
        now_epoch: int,
    ) -> SubscriptionQuotaStatusLike:
        collector_calls.append((state_file, now_epoch))
        return subscription_status

    quota_state_file = home / "subscription-quota-state.json"
    _ = quota_state_file.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "checked_at": 2_001_000,
                "health": "ready",
                "quota_levels": {"legacy-browser-plan:daily": 2},
                "status": {
                    "health": "ready",
                    "error": None,
                    "source": "browser",
                    "plans": [
                        {
                            "id": "legacy-browser-plan",
                            "name": "Legacy Browser Plan",
                            "status": "active",
                            "expires_at": None,
                            "quota_state": "available",
                            "quotas": [
                                {
                                    "period": "daily",
                                    "used_cents": 9_000,
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
    try:
        collector_globals["AI_INPUT_SUBSCRIPTIONS_ENABLED"] = True
        collector_globals["_direct_subscription_status"] = fake_direct_collector
        collector_globals["send_subscription_quota_notification"] = (
            lambda _message: None
        )
        collected_status = monitor.collect_subscription_quota_status(
            quota_state_file,
            now_epoch=2_001_000,
        )
        assert collected_status is not None and collected_status.health == "ready"
        assert collected_status.source == "api"
        assert collector_calls == [(quota_state_file, 2_001_000)]
        cached_status = monitor.collect_subscription_quota_status(
            quota_state_file,
            now_epoch=2_001_030,
        )
        assert cached_status is not None and cached_status.health == "ready"
        assert cached_status.source == "api"
        assert collector_calls == [(quota_state_file, 2_001_000)]
        assert quota_state_file.stat().st_mode & 0o777 == 0o600
        quota_state_text = quota_state_file.read_text(encoding="utf-8")
        quota_state_payload = cast(object, json.loads(quota_state_text))
        assert isinstance(quota_state_payload, dict)
        assert cast(dict[str, object], quota_state_payload)["checked_at"] == 2_001_000
        assert '"source":"api"' in quota_state_text
        assert "legacy-browser-plan" not in quota_state_text
        assert not any(
            secret in quota_state_text.lower()
            for secret in ("authorization", "bearer", "cookie", "localstorage")
        )
        refreshed_status = monitor.collect_subscription_quota_status(
            quota_state_file,
            now_epoch=2_001_056,
        )
        assert refreshed_status is not None and refreshed_status.health == "ready"
        assert collector_calls == [
            (quota_state_file, 2_001_000),
            (quota_state_file, 2_001_056),
        ]

        def fake_direct_failure(
            state_file: Path,
            now_epoch: int,
        ) -> SubscriptionQuotaStatusLike:
            collector_calls.append((state_file, now_epoch))
            return subscription_status_type(
                health="session-expired",
                error="AI INPUT sign-in required; refresh token was rejected",
                source="api",
            )

        collector_globals["_direct_subscription_status"] = fake_direct_failure
        direct_failure_state_file = home / "direct-failure-state.json"
        direct_failure_status = monitor.collect_subscription_quota_status(
            direct_failure_state_file,
            now_epoch=2_001_100,
        )
        assert direct_failure_status is not None
        assert direct_failure_status.health == "session-expired"
        assert collector_calls[-1] == (direct_failure_state_file, 2_001_100)
    finally:
        collector_globals["AI_INPUT_SUBSCRIPTIONS_ENABLED"] = (
            original_subscription_enabled
        )
        collector_globals["_direct_subscription_status"] = original_direct_collector
        collector_globals["send_subscription_quota_notification"] = (
            original_subscription_notifier
        )

    spotify_playing = monitor.parse_spotify_payload(
        '{"playback":"playing","title":"Fixture Song",'
        '"artist":"Fixture Artist","is_ad":false,"media_muted":false}'
    )
    spotify_script = monitor.spotify_jxa_script("return JSON.stringify({ok: true})")
    assert 'ObjC.import("AppKit")' in spotify_script
    assert "descriptorWithProcessIdentifier(pid)" in spotify_script
    assert "sendEventWithOptionsTimeoutError(19, 3, null)" in spotify_script
    assert "Number(application.activationPolicy) === 0" in spotify_script
    assert "Application(browserName)" not in spotify_script
    assert r"^https:\/\/open\.spotify\.com(?:[/?#]|$)" in spotify_script
    assert 'identifiedElement("cwin", windowId, root)' in spotify_script
    assert 'identifiedElement("CrTb", tabId, stableWindow)' in spotify_script
    assert 'spotifyUrl(stringProperty(pid, "URL ", stableTab))' in spotify_script
    assert "const requestedTabId = null;" in spotify_script
    scoped_spotify_script = monitor.spotify_jxa_script("return 1", tab_id=17)
    assert 'const requestedTabId = "17";' in scoped_spotify_script
    assert "if (tabId !== requestedTabId) continue;" in scoped_spotify_script
    assert "[\"-l\", \"JavaScript\"]" not in scoped_spotify_script

    original_spotify_subprocess_run = monitor.subprocess.run
    captured_spotify_commands: list[tuple[str, ...]] = []

    class SpotifyCompleted:
        def __init__(
            self,
            returncode: int,
            stdout: str,
            stderr: str = "",
        ) -> None:
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = stderr

    spotify_completed = SpotifyCompleted(
        0,
        '17\t{"playback":"paused"}\n',
    )

    def fake_spotify_subprocess_run(
        args: object,
        **kwargs: object,
    ) -> CompletedProcessLike:
        assert isinstance(args, list)
        command = tuple(str(item) for item in args)
        captured_spotify_commands.append(command)
        assert command[:4] == (
            "/usr/bin/osascript",
            "-l",
            "JavaScript",
            "-e",
        )
        assert "descriptorWithProcessIdentifier(pid)" in command[4]
        assert kwargs["capture_output"] is True
        assert kwargs["text"] is True
        return spotify_completed

    try:
        monitor.subprocess.run = fake_spotify_subprocess_run
        assert monitor.run_spotify_javascript("return 1") == (
            17,
            '{"playback":"paused"}',
            None,
        )
        spotify_completed = SpotifyCompleted(0, "__NO_TAB__\n")
        assert monitor.run_spotify_javascript("return 1") == (
            None,
            None,
            "not-found",
        )
        spotify_completed = SpotifyCompleted(
            1,
            "",
            "Not authorized to send Apple events (-1743)",
        )
        assert monitor.run_spotify_javascript("return 1") == (
            None,
            None,
            "permission",
        )
    finally:
        monitor.subprocess.run = original_spotify_subprocess_run
    assert len(captured_spotify_commands) == 3
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

    spaced_entrypoint = home / "Plugin With Spaces.15s.py"
    partial_title_settings = monitor.TitleBarSettings(
        hidden=frozenset({"cpu", "api", "spotify"})
    )
    partial_title_lines = monitor.render(
        fixture_rows,
        home,
        now="12:34:56",
        ai_input_status=healthy_status,
        subscription_quota_status=exhausted_total_status,
        spotify_status=spotify_playing,
        plugin_path=spaced_entrypoint,
        title_settings=partial_title_settings,
    ).splitlines()
    assert_supported_xbar_parameters(partial_title_lines)
    partial_title = partial_title_lines[0].partition(" | ")[0]
    assert partial_title.startswith("AI ")
    assert "CPU " not in partial_title
    assert "API " not in partial_title
    assert "SP play" not in partial_title
    assert "Q 0%" in partial_title
    assert not partial_title.startswith(" · ")
    assert not partial_title.endswith(" · ")
    assert " ·  · " not in partial_title
    partial_setting_lines = [
        line
        for line in partial_title_lines
        if line.startswith("--") and "param1=title-toggle-" in line
    ]
    assert len(partial_setting_lines) == len(title_components)
    assert any(
        line.startswith("--☐ CPU | ")
        and f"bash={shlex.quote(str(spaced_entrypoint.resolve()))}" in line
        and "param1=title-toggle-cpu" in line
        and "terminal=false" in line
        and "refresh=true" in line
        for line in partial_setting_lines
    )
    assert any(
        line.startswith("--☑ Agent count | ")
        for line in partial_setting_lines
    )

    all_hidden_title_settings = monitor.TitleBarSettings(
        hidden=frozenset(title_components)
    )
    all_hidden_lines = monitor.render(
        fixture_rows,
        home,
        now="12:34:56",
        ai_input_status=healthy_status,
        subscription_quota_status=exhausted_total_status,
        spotify_status=spotify_playing,
        plugin_path=PLUGIN,
        title_settings=all_hidden_title_settings,
    ).splitlines()
    assert all_hidden_lines[0] == "PX | color=red"
    assert "AI INPUT quota: 0% left | color=red" in all_hidden_lines
    assert any(line.startswith("AI.INPUT.IM:") for line in all_hidden_lines)
    assert any(line.startswith("Spotify Web: Playing") for line in all_hidden_lines)
    assert any(line.startswith("OMP:") for line in all_hidden_lines)
    assert sum(
        line.startswith("--☐ ") and "param1=title-toggle-" in line
        for line in all_hidden_lines
    ) == len(title_components)

    isolated_settings_path = home / "isolated-title-settings.json"
    monitor.write_title_bar_settings(
        all_hidden_title_settings,
        isolated_settings_path,
    )
    runtime_globals = monitor.render.__globals__
    collector_names = (
        "collect_ai_input_status",
        "collect_subscription_quota_status",
        "collect_spotify_status",
        "ps_rows",
    )
    original_collectors = {
        name: runtime_globals[name]
        for name in collector_names
    }
    collector_calls: list[str] = []
    try:
        runtime_globals["collect_ai_input_status"] = lambda: (
            collector_calls.append("ai-input") or healthy_status
        )
        runtime_globals["collect_subscription_quota_status"] = lambda: (
            collector_calls.append("subscription-quota")
            or exhausted_total_status
        )
        runtime_globals["collect_spotify_status"] = lambda: (
            collector_calls.append("spotify") or spotify_playing
        )
        runtime_globals["ps_rows"] = lambda: (
            collector_calls.append("processes") or fixture_rows
        )
        isolated_output = monitor.build_registry(
            isolated_settings_path
        ).execute(PLUGIN, [])
    finally:
        runtime_globals.update(original_collectors)
    assert collector_calls == [
        "ai-input",
        "subscription-quota",
        "spotify",
        "processes",
    ]
    assert isolated_output is not None
    isolated_lines = isolated_output.splitlines()
    assert isolated_lines[0] == "PX | color=red"
    assert "AI INPUT quota: 0% left | color=red" in isolated_lines
    assert any(line.startswith("AI.INPUT.IM:") for line in isolated_lines)
    assert any(line.startswith("Spotify Web: Playing") for line in isolated_lines)
    assert any(line.startswith("OMP:") for line in isolated_lines)

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
    fixture_bin = Path(status_state_directory) / "bin"
    fixture_bin.mkdir()
    fixture_ps = fixture_bin / "ps"
    _ = fixture_ps.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    fixture_ps.chmod(0o755)
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
                    "source": "api",
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
    live_environment["PATH"] = (
        str(fixture_bin) + os.pathsep + live_environment.get("PATH", "")
    )
    live_environment["AI_INPUT_NOTIFICATIONS"] = "0"
    live_environment["AI_INPUT_SUBSCRIPTIONS_ENABLED"] = "1"
    live_environment["AI_INPUT_SUBSCRIPTIONS_NOTIFICATIONS"] = "0"
    live_environment["AI_INPUT_SUBSCRIPTIONS_STATE_FILE"] = str(quota_cache_path)
    live_environment["SPOTIFY_WEB_ENABLED"] = "0"
    live_environment["AI_INPUT_MONITOR_STATE_FILE"] = str(
        Path(status_state_directory) / "ai-input-status.json"
    )
    live_environment["PERSONAL_XBAR_TITLE_SETTINGS_FILE"] = str(
        Path(status_state_directory) / "title-settings.json"
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
assert "AI INPUT quota: 50% left | color=green" in live_lines
assert any("$50.00 / $100.00 · 50% used" in line for line in live_lines)
assert sum(
    line.startswith("--☑ ") and "param1=title-toggle-" in line
    for line in live_lines
) == len(monitor.TITLE_COMPONENTS)
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
