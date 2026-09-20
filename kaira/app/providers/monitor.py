"""Monitoring provider for Prometheus metrics and system probes."""

from __future__ import annotations

from typing import Any
from starlette.responses import JSONResponse, Response

from kaira.app.providers.base import KairaProvider


class MonitorProvider(KairaProvider):
    """Provides /metrics and /healthz /readyz probe endpoints."""

    name: str = "monitor"

    def __init__(self, metrics_path: str = "/metrics") -> None:
        self.metrics_path = metrics_path

    def register(self, app: Any) -> None:
        """Register monitoring and probe routes."""

        @app.get(self.metrics_path, include_in_schema=False)
        async def metrics_endpoint() -> Response:
            try:
                from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

                return Response(
                    content=generate_latest(), media_type=CONTENT_TYPE_LATEST
                )
            except ImportError:
                return Response(
                    content="# Prometheus client not installed\n",
                    media_type="text/plain",
                )

        @app.get("/healthz", include_in_schema=False)
        async def liveness_probe() -> JSONResponse:
            return JSONResponse(content={"status": "live"})

        @app.get("/readyz", include_in_schema=False)
        async def readiness_probe() -> JSONResponse:
            return JSONResponse(content={"status": "ready"})

        app.state.monitor = self
