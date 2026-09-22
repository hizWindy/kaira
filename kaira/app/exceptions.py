"""Khaira Framework custom exception hierarchy."""

from __future__ import annotations


class KairaError(Exception):
    """Base exception for all Kaira framework errors."""



class ConfigurationError(KairaError):
    """Raised when project configuration is missing, invalid, or corrupted."""



class ProviderError(KairaError):
    """Raised when a provider fails to register, initialize, or execute."""



class LayerViolationError(KairaError):
    """Raised when 5-layer pipeline separation is violated at runtime."""



class UpgradeError(KairaError):
    """Raised when tier upgrade or migration fails."""



class RollbackError(KairaError):
    """Raised when snapshot rollback fails."""



class VerificationError(KairaError):
    """Raised when project integrity verification fails post-upgrade."""



class MicroserviceError(KairaError):
    """Raised when microservice extraction fails."""

