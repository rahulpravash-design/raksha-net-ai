"""Persistence for users and refresh tokens.

No business rules live here — see ``CLAUDE.md`` section 4, rule 3.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Select, delete, func, or_, select, update
from sqlalchemy.orm import Session

from app.models.enums import UserRole
from app.models.user import MfaRecoveryCode, PasswordResetToken, RefreshToken, User

#: Key of the advisory lock that serialises creation of the first administrator.
#: Any constant will do, as long as nothing else in the database uses it.
ADMIN_BOOTSTRAP_LOCK_KEY = 0x52414B5348410001


class UserRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def lock_admin_bootstrap(self) -> None:
        """Hold a transaction-scoped lock until commit or rollback, so two processes
        deciding whether an administrator exists cannot both decide "none"."""
        self.session.execute(select(func.pg_advisory_xact_lock(ADMIN_BOOTSTRAP_LOCK_KEY)))

    def administrator_count(self) -> int:
        """Every administrator account, active or not: a deactivated one is still one."""
        stmt = (
            select(func.count())
            .select_from(User)
            .where(User.role.in_((UserRole.ADMIN, UserRole.SUPER_ADMIN)))
        )
        return int(self.session.scalar(stmt) or 0)

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


class PasswordResetRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, token: PasswordResetToken) -> PasswordResetToken:
        self.session.add(token)
        self.session.flush()
        return token

    def get_by_hash(self, token_hash: str) -> PasswordResetToken | None:
        stmt = select(PasswordResetToken).where(
            PasswordResetToken.token_hash == token_hash
        )
        return self.session.scalars(stmt).first()

    def count_since(self, user_id: uuid.UUID, since: datetime) -> int:
        stmt = (
            select(func.count())
            .select_from(PasswordResetToken)
            .where(
                PasswordResetToken.user_id == user_id,
                PasswordResetToken.created_at >= since,
            )
        )
        return self.session.scalar(stmt) or 0

    def invalidate_unused(self, user_id: uuid.UUID, now: datetime) -> int:
        """Spend every outstanding token for the account (a newer link, or a
        completed reset, replaces them)."""
        stmt = select(PasswordResetToken).where(
            PasswordResetToken.user_id == user_id,
            PasswordResetToken.used_at.is_(None),
        )
        tokens = list(self.session.scalars(stmt))
        for token in tokens:
            token.used_at = now
        return len(tokens)


class MfaRecoveryRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def replace_all(self, user_id: uuid.UUID, code_hashes: list[str]) -> None:
        """Make ``code_hashes`` the user's whole set: any earlier code stops working."""
        self.delete_all(user_id)
        for code_hash in code_hashes:
            self.session.add(MfaRecoveryCode(user_id=user_id, code_hash=code_hash))
        self.session.flush()

    def delete_all(self, user_id: uuid.UUID) -> None:
        self.session.execute(
            delete(MfaRecoveryCode).where(MfaRecoveryCode.user_id == user_id)
        )

    def consume(self, user_id: uuid.UUID, code_hash: str, now: datetime) -> bool:
        """Spend a code, once. The conditional UPDATE is the single-use guarantee:
        two requests presenting the same code cannot both succeed."""
        result = self.session.execute(
            update(MfaRecoveryCode)
            .where(
                MfaRecoveryCode.user_id == user_id,
                MfaRecoveryCode.code_hash == code_hash,
                MfaRecoveryCode.used_at.is_(None),
            )
            .values(used_at=now)
        )
        return bool(getattr(result, "rowcount", 0))

    def remaining(self, user_id: uuid.UUID) -> int:
        stmt = (
            select(func.count())
            .select_from(MfaRecoveryCode)
            .where(
                MfaRecoveryCode.user_id == user_id,
                MfaRecoveryCode.used_at.is_(None),
            )
        )
        return self.session.scalar(stmt) or 0
