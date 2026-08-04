"""Local agent-process inventory plugin and menu renderer."""

from __future__ import annotations

from collections.abc import Callable
from typing import Optional, cast

from personal_xbar import runtime
from personal_xbar.registry import ExecutionContext


class ProcessInventoryPlugin:
    plugin_id = "processes"

    def actions(self) -> dict[str, Callable[[], None]]:
        return {}

    def collect(self, context: ExecutionContext) -> None:
        context.values["process_rows"] = runtime.ps_rows()

    def render(self, context: ExecutionContext) -> str | None:
        return runtime.render(
            cast(dict[int, runtime.Process], context.values["process_rows"]),
            ai_input_status=cast(
                Optional[runtime.AiInputStatus],
                context.values.get("ai_input_status"),
            ),
            spotify_status=cast(
                Optional[runtime.SpotifyStatus],
                context.values.get("spotify_status"),
            ),
            plugin_path=context.entrypoint,
        )
