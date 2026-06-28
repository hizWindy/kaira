"""FastAPI router for User endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from database import get_db
from schemas.user_schema import (
    UserCreate,
    UserUpdate,
    UserResponse,
)
from services.user_service import UserService


router = APIRouter(
    prefix="/users",
    tags=["User"],
)


def get_service(db: Session = Depends(get_db)) -> UserService:
    """Dependency that provides a :class:`UserService` instance."""
    return UserService(db)


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.post(
    "/",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create User",
    description="Create a new User record.",
)
def create_user(
    data: UserCreate,
    service: UserService = Depends(get_service),
) -> UserResponse:
    """Create a new **User**."""
    return service.create(data)


@router.get(
    "/",
    response_model=list[UserResponse],
    summary="List Users",
    description="Retrieve a paginated list of User records.",
)
def list_users(
    skip: int = Query(default=0, ge=0, description="Records to skip"),
    limit: int = Query(default=100, ge=1, le=1000, description="Maximum records to return"),
    service: UserService = Depends(get_service),
) -> list[UserResponse]:
    """Return a paginated list of **User** records."""
    return service.get_all(skip=skip, limit=limit)


@router.get(
    "/{record_id}",
    response_model=UserResponse,
    summary="Get User",
    description="Retrieve a single User by ID.",
)
def get_user(
    record_id: int,
    service: UserService = Depends(get_service),
) -> UserResponse:
    """Return a single **User** by primary key."""
    return service.get_by_id(record_id)


@router.put(
    "/{record_id}",
    response_model=UserResponse,
    summary="Update User",
    description="Update an existing User record.",
)
def update_user(
    record_id: int,
    data: UserUpdate,
    service: UserService = Depends(get_service),
) -> UserResponse:
    """Update an existing **User** by primary key."""
    return service.update(record_id, data)


@router.delete(
    "/{record_id}",
    summary="Delete User",
    description="Delete a User record by ID.",
    status_code=status.HTTP_200_OK,
)
def delete_user(
    record_id: int,
    service: UserService = Depends(get_service),
) -> dict:
    """Delete a **User** by primary key."""
    return service.delete(record_id)
