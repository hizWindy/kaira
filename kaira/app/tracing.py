"""OpenTelemetry distributed tracing setup (Enterprise Tier)."""

from __future__ import annotations

from typing import Any, Optional


class TracerManager:
    """Manages distributed tracing via OpenTelemetry when installed."""

    def __init__(
        self, service_name: str = "kaira-service", endpoint: Optional[str] = None
    ) -> None:
        self.service_name = service_name
        self.endpoint = endpoint
        self._tracer: Any = None
        self._enabled = False

    def init_tracing(self, app: Any = None) -> bool:
        """Initialize OpenTelemetry instrumentation if packages are present."""
        try:
            from opentelemetry import trace
            from opentelemetry.sdk.resources import Resource
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.export import (
                BatchSpanProcessor,
                ConsoleSpanExporter,
            )

            resource = Resource.create({"service.name": self.service_name})
            provider = TracerProvider(resource=resource)
            provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
            trace.set_tracer_provider(provider)

            if app is not None:
                from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

                FastAPIInstrumentor.instrument_app(app)

            self._tracer = trace.get_tracer(self.service_name)
            self._enabled = True
            return True
        except ImportError:
            self._enabled = False
            return False

    @property
    def is_enabled(self) -> bool:
        return self._enabled


# First-class alias
Tracer = TracerManager

__all__ = ["TracerManager", "Tracer"]
