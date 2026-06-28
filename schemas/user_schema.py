"""Pydantic v2 schemas for User."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class UserBase(BaseModel):
    """Shared fields for User schemas."""
    username: str
    email: str
    age: int


class UserCreate(UserBase):
    """Schema for creating a new User."""

    pass


class UserUpdate(BaseModel):
    """Schema for updating an existing User.

    All fields are optional to support partial updates (PATCH semantics).
    """
    username: Optional[str] = None
    email: Optional[str] = None
    age: Optional[int] = None


class UserResponse(UserBase):
    """Schema returned from API endpoints."""

    id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
