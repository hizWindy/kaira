"""Khaira Framework custom exception hierarchy."""

from __future__ import annotations


class KairaError(Exception):
    """Base exception for all Kaira framework errors."""

    pass


class ConfigurationError(KairaError):
    """Raised when project configuration is missing, invalid, or corrupted."""

    pass


class ProviderError(KairaError):
    """Raised when a provider fails to register, initialize, or execute."""

    pass


class LayerViolationError(KairaError):
    """Raised when 5-layer pipeline separation is violated at runtime."""

    pass


class UpgradeError(KairaError):
    """Raised when tier upgrade or migration fails."""

    pass


class RollbackError(KairaError):
    """Raised when snapshot rollback fails."""

    pass


class VerificationError(KairaError):
    """Raised when project integrity verification fails post-upgrade."""

    pass


class MicroserviceError(KairaError):
    """Raised when microservice extraction fails."""

    pass
