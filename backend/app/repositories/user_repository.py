"""Persistence for users and refresh tokens.

No business rules live here — see ``CLAUDE.md`` section 4, rule 3.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.models.enums import UserRole
from app.models.user import RefreshToken, User


class UserRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, user_id: uuid.UUID) -> User | None:
        return self.session.get(User, user_id)

    def get_by_email(self, email: str) -> User | None:
        stmt = select(User).where(func.lower(User.email) == email.strip().lower())
        return self.session.scalars(stmt).first()

    def email_exists(self, email: str) -> bool:
        stmt = (
            select(func.count())
            .select_from(User)
            .where(func.lower(User.email) == email.strip().lower())
        )
        return bool(self.session.scalar(stmt))

    def add(self, user: User) -> User:
        self.session.add(user)
        self.session.flush()
        return user

    def list_paginated(
        self,
        *,
        offset: int,
        limit: int,
        role: UserRole | None = None,
        is_active: bool | None = None,
        query: str | None = None,
    ) -> tuple[list[User], int]:
        stmt: Select[tuple[User]] = select(User)
        if role is not None:
            stmt = stmt.where(User.role == role)
        if is_active is not None:
            stmt = stmt.where(User.is_active.is_(is_active))
        if query:
            pattern = f"%{query.strip()}%"
            stmt = stmt.where(
                or_(User.full_name.ilike(pattern), User.email.ilike(pattern))
            )

        total = (
            self.session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        )
        rows = list(
            self.session.scalars(
                stmt.order_by(User.created_at.desc()).offset(offset).limit(limit)
            )
        )
        return rows, total


class RefreshTokenRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, token: RefreshToken) -> RefreshToken:
        self.session.add(token)
        self.session.flush()
        return token

    def get_by_hash(self, token_hash: str) -> RefreshToken | None:
        stmt = select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        return self.session.scalars(stmt).first()

    def revoke_chain(self, token: RefreshToken, now: datetime) -> int:
        """Revoke a token and every descendant in its rotation chain.

        Called when a revoked token is presented again — the signature of a
        stolen credential (``docs/SECURITY.md`` section 2).
        """
        revoked = 0
        current: RefreshToken | None = token
        seen: set[uuid.UUID] = set()

        while current is not None and current.id not in seen:
            seen.add(current.id)
            if current.revoked_at is None:
                current.revoked_at = now
                revoked += 1
            next_id = current.replaced_by_id
            current = self.session.get(RefreshToken, next_id) if next_id else None

        return revoked

    def revoke_all_for_user(self, user_id: uuid.UUID, now: datetime) -> int:
        stmt = select(RefreshToken).where(
            RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None)
        )
        tokens = list(self.session.scalars(stmt))
        for token in tokens:
            token.revoked_at = now
        return len(tokens)
