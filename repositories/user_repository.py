"""Repository (data access layer) for User."""

from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from models.user import User
from schemas.user_schema import UserCreate, UserUpdate


class UserRepository:
    """CRUD operations for :class:`User`."""

    def __init__(self, db: Session) -> None:
        self.db = db

    # ── Create ───────────────────────────────────────────────────────────────

    def create(self, data: UserCreate) -> User:
        """Persist a new User record."""
        obj = User(**data.model_dump())
        self.db.add(obj)
        self.db.commit()
        self.db.refresh(obj)
        return obj

    # ── Read ─────────────────────────────────────────────────────────────────

    def get_by_id(self, record_id: int) -> Optional[User]:
        """Return a User by primary key, or *None* if not found."""
        return self.db.query(User).filter(User.id == record_id).first()

    def get_all(self, skip: int = 0, limit: int = 100) -> list[User]:
        """Return a paginated list of all User records."""
        return (
            self.db.query(User)
            .offset(skip)
            .limit(limit)
            .all()
        )

    # ── Update ───────────────────────────────────────────────────────────────

    def update(self, record_id: int, data: UserUpdate) -> Optional[User]:
        """Update an existing User record.

        Only fields present in *data* (non-None) are updated.
        Returns the updated record, or *None* if not found.
        """
        obj = self.get_by_id(record_id)
        if obj is None:
            return None
        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(obj, key, value)
        self.db.commit()
        self.db.refresh(obj)
        return obj

    # ── Delete ───────────────────────────────────────────────────────────────

    def delete(self, record_id: int) -> bool:
        """Delete a User record by ID.

        Returns *True* if deleted, *False* if not found.
        """
        obj = self.get_by_id(record_id)
        if obj is None:
            return False
        self.db.delete(obj)
        self.db.commit()
        return True
