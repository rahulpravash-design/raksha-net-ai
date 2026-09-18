"""User profile and administration endpoints."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import AdminUser, AppSettings, Context, CurrentUser, DbSession
from app.core.errors import ForbiddenError, NotFoundError, ValidationError
from app.models.enums import UserRole
from app.repositories.user_repository import UserRepository
from app.schemas.common import Page
from app.schemas.user import (
    UserCreate,
    UserRead,
    UserUpdateAdmin,
    UserUpdateSelf,
)
from app.services.audit_service import AuditAction, AuditService
from app.services.auth_service import AuthService

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserRead, summary="Own profile")
def read_me(user: CurrentUser) -> UserRead:
    return UserRead.model_validate(user)


@router.patch("/me", response_model=UserRead, summary="Update own profile")
def update_me(payload: UserUpdateSelf, user: CurrentUser, session: DbSession) -> UserRead:
    """Update own contact details.

    Deliberately cannot change ``role`` or ``is_active`` — self-promotion is not
    a supported feature.
    """
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise ValidationError("No fields were supplied to update.")

    for field, value in changes.items():
        setattr(user, field, value)
    session.commit()
    session.refresh(user)
    return UserRead.model_validate(user)


@router.get("", response_model=Page[UserRead], summary="List users")
def list_users(
    _: AdminUser,
    session: DbSession,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
    role: UserRole | None = None,
    is_active: bool | None = None,
    q: Annotated[str | None, Query(max_length=120)] = None,
) -> Page[UserRead]:
    rows, total = UserRepository(session).list_paginated(
        offset=(page - 1) * page_size,
        limit=page_size,
        role=role,
        is_active=is_active,
        query=q,
    )
    return Page.build(
        [UserRead.model_validate(row) for row in rows], total, page, page_size
    )


@router.post(
    "",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a user with a role",
)
def create_user(
    payload: UserCreate,
    admin: AdminUser,
    session: DbSession,
    settings: AppSettings,
    context: Context,
) -> UserRead:
    user = AuthService(session, settings).create_user(
        payload, actor=admin, context=context
    )
    return UserRead.model_validate(user)


@router.get("/{user_id}", response_model=UserRead, summary="Read a user")
def read_user(user_id: uuid.UUID, _: AdminUser, session: DbSession) -> UserRead:
    user = UserRepository(session).get(user_id)
    if user is None:
        raise NotFoundError("User not found.")
    return UserRead.model_validate(user)


@router.patch("/{user_id}", response_model=UserRead, summary="Update a user")
def update_user(
    user_id: uuid.UUID,
    payload: UserUpdateAdmin,
    admin: AdminUser,
    session: DbSession,
    context: Context,
) -> UserRead:
    """Update another user's profile, role or active flag.

    An administrator cannot change their own role or deactivate themselves —
    that is how an organisation loses its last administrator, and how a
    compromised session escalates quietly.
    """
    target = UserRepository(session).get(user_id)
    if target is None:
        raise NotFoundError("User not found.")

    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise ValidationError("No fields were supplied to update.")

    if target.id == admin.id and ("role" in changes or "is_active" in changes):
        raise ForbiddenError("You cannot change your own role or active status.")

    new_role = changes.get("role")
    if (
        UserRole.SUPER_ADMIN in (new_role, target.role)
        and admin.role is not UserRole.SUPER_ADMIN
    ):
        raise ForbiddenError("Only a super administrator may manage one.")

    previous_role = target.role
    for field, value in changes.items():
        setattr(target, field, value)

    audit = AuditService(session)
    if new_role is not None and new_role != previous_role:
        audit.record(
            AuditAction.USER_ROLE_CHANGED,
            actor_id=admin.id,
            actor_role=admin.role,
            entity_type="user",
            entity_id=target.id,
            ip_address=context.ip_address,
            user_agent=context.user_agent,
            metadata={"from": previous_role.value, "to": new_role.value},
        )
    if changes.get("is_active") is False:
        audit.record(
            AuditAction.USER_DEACTIVATED,
            actor_id=admin.id,
            actor_role=admin.role,
            entity_type="user",
            entity_id=target.id,
            ip_address=context.ip_address,
            user_agent=context.user_agent,
        )
    audit.record(
        AuditAction.USER_UPDATED,
        actor_id=admin.id,
        actor_role=admin.role,
        entity_type="user",
        entity_id=target.id,
        ip_address=context.ip_address,
        user_agent=context.user_agent,
        metadata={"fields": sorted(changes)},
    )

    session.commit()
    session.refresh(target)
    return UserRead.model_validate(target)
