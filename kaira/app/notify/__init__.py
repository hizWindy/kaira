"""Notification abstraction module (Email / SMS)."""

from __future__ import annotations

from typing import List


class Email:
    """Email dispatching abstraction."""

    def __init__(self, provider: str = "smtp") -> None:
        self.provider = provider

    async def send(self, to: str | List[str], subject: str, body: str) -> bool:
        return True


class SMS:
    """SMS notification abstraction."""

    def __init__(self, provider: str = "twilio") -> None:
        self.provider = provider

    async def send(self, to: str, message: str) -> bool:
        return True


__all__ = ["Email", "SMS"]
