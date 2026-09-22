"""Product and user analytics abstraction module."""

from __future__ import annotations

from typing import Any, Dict, Optional

try:
    from mixpanel import Mixpanel

    _HAS_MIXPANEL = True
except ImportError:
    _HAS_MIXPANEL = False

try:
    from amplitude import AmplitudeClient

    _HAS_AMPLITUDE = True
except ImportError:
    _HAS_AMPLITUDE = False


class Analytics:
    """Analytics tracking wrapper (Mixpanel, Amplitude, etc.)."""

    def __init__(
        self, provider: str = "mixpanel", api_key: str | None = None
    ) -> None:
        self.provider = provider
        self.api_key = api_key or __import__("os").environ.get(
            f"{provider.upper()}_API_KEY"
        )
        self._client: Any = None
        self._enabled = False

    def _init_client(self) -> None:
        if self.provider == "mixpanel" and _HAS_MIXPANEL and self.api_key:
            self._client = Mixpanel(self.api_key)
            self._enabled = True
        elif self.provider == "amplitude" and _HAS_AMPLITUDE and self.api_key:
            self._client = AmplitudeClient(api_key=self.api_key)
            self._enabled = True

    def track(
        self, event_name: str, properties: dict[str, Any] | None = None
    ) -> None:
        """Track an analytics event."""
        if not self._enabled:
            self._init_client()
        if self._enabled and self._client:
            if self.provider == "mixpanel":
                self._client.track(
                    distinct_id=properties.get("user_id", "anonymous")
                    if properties
                    else "anonymous",
                    event=event_name,
                    properties=properties or {},
                )
            elif self.provider == "amplitude":
                self._client.log_event(event_name, properties or {})

    def page(self, page_name: str, properties: dict[str, Any] | None = None) -> None:
        """Track a page view."""
        self.track(f"page:{page_name}", properties)


__all__ = ["Analytics"]
