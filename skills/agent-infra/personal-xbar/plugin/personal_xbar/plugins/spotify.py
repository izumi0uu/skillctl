"""Spotify Web playback and advertisement auto-mute plugin."""

from __future__ import annotations

from collections.abc import Callable

from personal_xbar import runtime
from personal_xbar.registry import ExecutionContext


class SpotifyPlugin:
    plugin_id = "spotify"

    def actions(self) -> dict[str, Callable[[], None]]:
        return {
            "spotify-toggle": lambda: runtime.control_spotify_playback("toggle"),
            "spotify-previous": lambda: runtime.control_spotify_playback("previous"),
            "spotify-next": lambda: runtime.control_spotify_playback("next"),
        }

    def collect(self, context: ExecutionContext) -> None:
        context.values["spotify_status"] = runtime.collect_spotify_status()

    def render(self, context: ExecutionContext) -> str | None:
        return None
