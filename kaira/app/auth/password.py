"""Password hashing abstraction — Argon2-cffi (primary) with bcrypt and hashlib fallbacks."""

from __future__ import annotations

import hashlib
import secrets

try:
    from argon2 import PasswordHasher
    from argon2.exceptions import VerifyMismatchError

    _HAS_ARGON2 = True
    _argon2_hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4)
except ImportError:
    _HAS_ARGON2 = False
    _argon2_hasher = None  # type: ignore[assignment]

try:
    import bcrypt

    _HAS_BCRYPT = True
except ImportError:
    _HAS_BCRYPT = False


def hash_password(password: str) -> str:
    """Hash a plaintext password with the strongest available algorithm."""
    if _HAS_ARGON2 and _argon2_hasher is not None:
        return _argon2_hasher.hash(password)
    if _HAS_BCRYPT:
        salt = bcrypt.gensalt()
        return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")

    # Safe fallback using standard library pbkdf2_hmac
    salt_hex = secrets.token_hex(16)
    derived = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt_hex.encode("utf-8"), 100_000
    ).hex()
    return f"pbkdf2_sha256${salt_hex}${derived}"


def verify_password(password: str, hashed: str) -> bool:
    """Verify password against hashed string."""
    if hashed.startswith("$argon2"):
        if _HAS_ARGON2 and _argon2_hasher is not None:
            try:
                return _argon2_hasher.verify(hashed, password)
            except VerifyMismatchError:
                return False
        return False

    if (
        hashed.startswith("$2a$")
        or hashed.startswith("$2b$")
        or hashed.startswith("$2y$")
    ):
        if _HAS_BCRYPT:
            try:
                return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
            except Exception:
                return False
        return False

    if hashed.startswith("pbkdf2_sha256$"):
        parts = hashed.split("$")
        if len(parts) == 3:
            _, salt_hex, expected_hex = parts
            derived = hashlib.pbkdf2_hmac(
                "sha256", password.encode("utf-8"), salt_hex.encode("utf-8"), 100_000
            ).hex()
            return secrets.compare_digest(derived, expected_hex)

    return False
