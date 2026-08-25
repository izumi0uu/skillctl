"""Personal xbar application composition root."""

from __future__ import annotations

from personal_xbar import runtime
from personal_xbar.plugins.ai_input import AiInputPlugin
from personal_xbar.plugins.processes import ProcessInventoryPlugin
from personal_xbar.plugins.spotify import SpotifyPlugin
from personal_xbar.plugins.subscription_quota import SubscriptionQuotaPlugin
from personal_xbar.registry import PluginRegistry


def build_registry() -> PluginRegistry:
    registry = PluginRegistry()
    registry.register(AiInputPlugin())
    registry.register(SubscriptionQuotaPlugin())
    registry.register(SpotifyPlugin())
    registry.register(ProcessInventoryPlugin())
    return registry


def main(entrypoint: Path, arguments: list[str]) -> None:
    try:
        output = build_registry().execute(entrypoint, arguments)
        if output is not None:
            print(output)
    except Exception as error:
        print("PX ? | color=red")
        print("---")
        print(f"Personal xbar failed: {runtime.sanitize_text(str(error))} | color=red")
