"""Schema and data validation abstraction module for Khaira framework."""

from __future__ import annotations

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

try:
    from pydantic import EmailStr
except ImportError:
    EmailStr = str  # type: ignore[misc,assignment]

# First-class alias for BaseModel
Schema = BaseModel

__all__ = [
    "BaseModel",
    "ConfigDict",
    "EmailStr",
    "Field",
    "Schema",
    "field_validator",
    "model_validator",
]
