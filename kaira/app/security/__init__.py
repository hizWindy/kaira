"""Security and encryption abstraction module."""

from __future__ import annotations

import base64
from typing import Any, Optional


class Fernet:
    """Symmetric encryption wrapper using cryptography Fernet when available."""

    def __init__(self, key: Optional[bytes] = None) -> None:
        self._fernet: Any = None
        try:
            from cryptography.fernet import Fernet as _Fernet

            self._fernet = _Fernet(key or _Fernet.generate_key())
        except ImportError:
            self._fernet = None

    def encrypt(self, data: bytes) -> bytes:
        if self._fernet:
            return self._fernet.encrypt(data)
        return base64.b64encode(data)

    def decrypt(self, token: bytes) -> bytes:
        if self._fernet:
            return self._fernet.decrypt(token)
        return base64.b64decode(token)


__all__ = ["Fernet"]
