"""AI.INPUT.IM model-health plugin."""

from __future__ import annotations

from collections.abc import Callable

from personal_xbar import runtime
from personal_xbar.registry import ExecutionContext


class AiInputPlugin:
    plugin_id = "ai-input"

    def actions(self) -> dict[str, Callable[[], None]]:
        return {}

    def collect(self, context: ExecutionContext) -> None:
        context.values["ai_input_status"] = runtime.collect_ai_input_status()

    def render(self, context: ExecutionContext) -> str | None:
        return None
