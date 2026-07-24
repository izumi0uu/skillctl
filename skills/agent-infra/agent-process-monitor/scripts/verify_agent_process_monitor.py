#!/usr/bin/env python3
"""Verify the xbar agent-process monitor with deterministic process fixtures."""

from __future__ import annotations

import argparse
import importlib.util
import shlex
import subprocess
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Protocol, cast

DEFAULT_PLUGIN = Path(__file__).resolve().parents[1] / "plugin" / "mcp-monitor.15s.py"


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
    {"bash", "color", "param1", "param2", "terminal"}
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
    subprocess: PatchableSubprocess
    sqlite3: PatchableSqlite

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
    ) -> str: ...

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

live_output = subprocess.check_output([str(PLUGIN)], text=True)
live_lines = live_output.splitlines()
assert_supported_xbar_parameters(live_lines)
assert live_lines and live_lines[0].startswith("AI "), live_lines[:1]
assert "---" in live_lines
assert any(line.startswith("Open Activity Monitor") for line in live_lines)
version_line = next(
    line
    for line in PLUGIN.read_text(encoding="utf-8").splitlines()
    if line.startswith("# <xbar.version>")
)
version = version_line.removeprefix("# <xbar.version>").removesuffix(
    "</xbar.version>"
)
print(f"xbar agent process monitor contract passed: {PLUGIN} (v{version})")
