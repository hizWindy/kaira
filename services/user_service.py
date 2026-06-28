"""Service layer (business logic) for User."""

from __future__ import annotations

from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from models.user import User
from repositories.user_repository import UserRepository
from schemas.user_schema import UserCreate, UserUpdate, UserResponse


class UserService:
    """Business logic layer for :class:`User` operations."""

    def __init__(self, db: Session) -> None:
        self._repo = UserRepository(db)

    # ── Create ───────────────────────────────────────────────────────────────

    def create(self, data: UserCreate) -> UserResponse:
        """Create a new User.

        Parameters
        ----------
        data:
            Validated creation payload.

        Returns
        -------
        UserResponse
            The newly created record.
        """
        obj = self._repo.create(data)
        return UserResponse.model_validate(obj)

    # ── Read ─────────────────────────────────────────────────────────────────

    def get_by_id(self, record_id: int) -> UserResponse:
        """Retrieve a User by ID.

        Raises
        ------
        HTTPException
            404 if the record does not exist.
        """
        obj = self._repo.get_by_id(record_id)
        if obj is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User with id={record_id} not found.",
            )
        return UserResponse.model_validate(obj)

    def get_all(self, skip: int = 0, limit: int = 100) -> list[UserResponse]:
        """Return a paginated list of User records.

        Parameters
        ----------
        skip:
            Number of records to skip (offset).
        limit:
            Maximum number of records to return.
        """
        objects = self._repo.get_all(skip=skip, limit=limit)
        return [UserResponse.model_validate(o) for o in objects]

    # ── Update ───────────────────────────────────────────────────────────────

    def update(self, record_id: int, data: UserUpdate) -> UserResponse:
        """Update an existing User.

        Raises
        ------
        HTTPException
            404 if the record does not exist.
        """
        obj = self._repo.update(record_id, data)
        if obj is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User with id={record_id} not found.",
            )
        return UserResponse.model_validate(obj)

    # ── Delete ───────────────────────────────────────────────────────────────

    def delete(self, record_id: int) -> dict:
        """Delete a User by ID.

        Returns
        -------
        dict
            Confirmation message.

        Raises
        ------
        HTTPException
            404 if the record does not exist.
        """
        deleted = self._repo.delete(record_id)
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User with id={record_id} not found.",
            )
        return {"detail": f"User {record_id} deleted successfully."}
