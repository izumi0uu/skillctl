"""Persistent menu-bar title visibility settings."""

from __future__ import annotations

from collections.abc import Callable
from functools import partial
from pathlib import Path

from personal_xbar import runtime
from personal_xbar.registry import ExecutionContext


class TitleBarSettingsPlugin:
    plugin_id = "title-settings"

    def __init__(self, state_file: Path = runtime.TITLE_SETTINGS_FILE) -> None:
        self.state_file = state_file

    def actions(self) -> dict[str, Callable[[], None]]:
        return {
            f"title-toggle-{component}": partial(
                runtime.toggle_title_component,
                component,
                self.state_file,
            )
            for component, _label in runtime.TITLE_COMPONENTS
        }

    def collect(self, context: ExecutionContext) -> None:
        context.values["title_settings"] = runtime.read_title_bar_settings(
            self.state_file
        )

    def render(self, context: ExecutionContext) -> str | None:
        return None
