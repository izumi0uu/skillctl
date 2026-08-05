"""Small explicit registry for Personal xbar feature plugins."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


@dataclass
class ExecutionContext:
    entrypoint: Path
    values: dict[str, object] = field(default_factory=dict)


class XbarPlugin(Protocol):
    plugin_id: str

    def actions(self) -> dict[str, Callable[[], None]]: ...

    def collect(self, context: ExecutionContext) -> None: ...

    def render(self, context: ExecutionContext) -> str | None: ...


class PluginRegistry:
    def __init__(self) -> None:
        self._plugins: list[XbarPlugin] = []
        self._actions: dict[str, Callable[[], None]] = {}

    def register(self, plugin: XbarPlugin) -> None:
        if any(current.plugin_id == plugin.plugin_id for current in self._plugins):
            raise ValueError(f"duplicate Personal xbar plugin: {plugin.plugin_id}")
        actions = plugin.actions()
        duplicate_actions = self._actions.keys() & actions.keys()
        if duplicate_actions:
            duplicate = sorted(duplicate_actions)[0]
            raise ValueError(f"duplicate Personal xbar action: {duplicate}")
        self._plugins.append(plugin)
        self._actions.update(actions)

    @property
    def plugin_ids(self) -> tuple[str, ...]:
        return tuple(plugin.plugin_id for plugin in self._plugins)

    @property
    def action_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._actions))

    def execute(self, entrypoint: Path, arguments: list[str]) -> str | None:
        if arguments:
            if len(arguments) != 1 or arguments[0] not in self._actions:
                raise ValueError("unsupported Personal xbar action")
            self._actions[arguments[0]]()
            return None

        context = ExecutionContext(entrypoint=entrypoint)
        for plugin in self._plugins:
            plugin.collect(context)

        rendered = [
            output
            for plugin in self._plugins
            if (output := plugin.render(context)) is not None
        ]
        if len(rendered) != 1:
            raise RuntimeError("Personal xbar requires exactly one menu renderer")
        return rendered[0]
