"""JWT token abstraction wrapping PyJWT and python-jose."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

try:
    import jwt  # PyJWT

    _HAS_PYJWT = True
except ImportError:
    _HAS_PYJWT = False

try:
    from jose import jwt as jose_jwt  # python-jose

    _HAS_JOSE = True
except ImportError:
    _HAS_JOSE = False


import base64
import hashlib
import hmac
import json


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("utf-8")


def _b64url_decode(data: str) -> bytes:
    rem = len(data) % 4
    if rem > 0:
        data += "=" * (4 - rem)
    return base64.urlsafe_b64decode(data.encode("utf-8"))


class JWTManager:
    """Manages JWT creation and validation."""

    def __init__(
        self, secret_key: Optional[str] = None, algorithm: str = "HS256"
    ) -> None:
        self.secret_key = secret_key or os.getenv(
            "JWT_SECRET_KEY", "default-32-char-secret-key-kaira!"
        )
        self.algorithm = algorithm

    def create_token(self, payload: Dict[str, Any], expires_minutes: int = 60) -> str:
        """Encode a dictionary payload into a signed JWT."""
        to_encode = payload.copy()
        exp = datetime.now(timezone.utc) + timedelta(minutes=expires_minutes)
        to_encode["exp"] = exp

        if _HAS_PYJWT:
            return jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)  # type: ignore[no-any-return]
        if _HAS_JOSE:
            return jose_jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)  # type: ignore[no-any-return]

        # Pure Python fallback using standard library HMAC + SHA256
        header = {"alg": "HS256", "typ": "JWT"}
        header_b64 = _b64url_encode(
            json.dumps(header, separators=(",", ":")).encode("utf-8")
        )
        serializable = {}
        for k, v in to_encode.items():
            if isinstance(v, datetime):
                serializable[k] = int(v.timestamp())
            else:
                serializable[k] = v
        payload_b64 = _b64url_encode(
            json.dumps(serializable, separators=(",", ":")).encode("utf-8")
        )
        msg = f"{header_b64}.{payload_b64}".encode("utf-8")
        sig = hmac.new(self.secret_key.encode("utf-8"), msg, hashlib.sha256).digest()
        sig_b64 = _b64url_encode(sig)
        return f"{header_b64}.{payload_b64}.{sig_b64}"

    def verify_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Decode and verify a JWT, returning payload or None if invalid/expired."""
        try:
            if _HAS_PYJWT:
                return jwt.decode(token, self.secret_key, algorithms=[self.algorithm])  # type: ignore[no-any-return]
            if _HAS_JOSE:
                return jose_jwt.decode(
                    token, self.secret_key, algorithms=[self.algorithm]
                )  # type: ignore[no-any-return]

            # Pure Python fallback verification
            parts = token.split(".")
            if len(parts) != 3:
                return None
            header_b64, payload_b64, sig_b64 = parts
            msg = f"{header_b64}.{payload_b64}".encode("utf-8")
            expected_sig = hmac.new(
                self.secret_key.encode("utf-8"), msg, hashlib.sha256
            ).digest()
            actual_sig = _b64url_decode(sig_b64)
            if not hmac.compare_digest(actual_sig, expected_sig):
                return None
            payload_json = _b64url_decode(payload_b64).decode("utf-8")
            payload_data = json.loads(payload_json)
            if "exp" in payload_data:
                now = int(datetime.now(timezone.utc).timestamp())
                if now > payload_data["exp"]:
                    return None
            return payload_data
        except Exception:
            return None


class JWT(JWTManager):
    """Framework-managed JWT alias."""

    pass
