"""Background task provider wrapping Celery."""

from __future__ import annotations

import os
from typing import Any, Callable, Optional

from kaira.app.providers.base import KairaProvider


class TaskProvider(KairaProvider):
    """Background tasks provider integrating Celery."""

    name: str = "task"

    def __init__(self, broker_url: Optional[str] = None) -> None:
        self.broker_url = broker_url or os.getenv(
            "CELERY_BROKER_URL", "redis://localhost:6379/1"
        )
        self._celery_app: Any = None

    def register(self, app: Any) -> None:
        """Register task provider on app state."""
        app.state.task = self

    async def startup(self) -> None:
        """Initialize Celery application instance if library is available."""
        try:
            from celery import Celery

            self._celery_app = Celery("kaira_worker", broker=self.broker_url)
        except ImportError:
            self._celery_app = None

    def task(self, *args: Any, **kwargs: Any) -> Callable[..., Any]:
        """Decorator to define a Celery task, or a no-op passthrough if Celery is missing."""

        def decorator(fn: Callable[..., Any]) -> Any:
            if self._celery_app is not None:
                return self._celery_app.task(*args, **kwargs)(fn)
            return fn

        return decorator
