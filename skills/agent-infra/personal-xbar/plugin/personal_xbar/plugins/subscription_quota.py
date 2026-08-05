"""Authenticated AI.INPUT.IM subscription-quota plugin."""

from __future__ import annotations

from collections.abc import Callable

from personal_xbar import runtime
from personal_xbar.registry import ExecutionContext


class SubscriptionQuotaPlugin:
    plugin_id = "subscription-quota"

    def actions(self) -> dict[str, Callable[[], None]]:
        return {}

    def collect(self, context: ExecutionContext) -> None:
        context.values["subscription_quota_status"] = (
            runtime.collect_subscription_quota_status()
        )

    def render(self, context: ExecutionContext) -> str | None:
        return None
