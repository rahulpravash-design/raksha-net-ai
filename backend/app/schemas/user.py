"""User request and response schemas."""

from __future__ import annotations

import re
import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.models.enums import UserRole
from app.schemas.common import ORMModel

#: E.164-ish. Deliberately permissive — a wrong number is better than a rejected
#: emergency report.
PHONE_PATTERN = re.compile(r"^\+?[0-9][0-9\s\-()]{6,30}$")


def _normalise_phone(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    if not stripped:
        return None
    if not PHONE_PATTERN.match(stripped):
        raise ValueError("Phone number format is not recognised.")
    return re.sub(r"[\s\-()]", "", stripped)


class UserBase(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=160)
    phone: str | None = Field(default=None, max_length=32)

    @field_validator("email")
    @classmethod
    def _lower_email(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("phone")
    @classmethod
    def _check_phone(cls, value: str | None) -> str | None:
        return _normalise_phone(value)


class UserRegister(UserBase):
    """Self-registration. The role is always ``CITIZEN``; any supplied role is
    ignored rather than honoured."""

    password: str = Field(min_length=1, max_length=128)


class UserCreate(UserBase):
    """Administrative creation, where the role is chosen."""

    password: str = Field(min_length=1, max_length=128)
    role: UserRole = UserRole.CITIZEN
    is_active: bool = True


class UserUpdateSelf(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=160)
    phone: str | None = Field(default=None, max_length=32)

    @field_validator("phone")
    @classmethod
    def _check_phone(cls, value: str | None) -> str | None:
        return _normalise_phone(value)


class UserUpdateAdmin(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=160)
    phone: str | None = Field(default=None, max_length=32)
    role: UserRole | None = None
    is_active: bool | None = None

    @field_validator("phone")
    @classmethod
    def _check_phone(cls, value: str | None) -> str | None:
        return _normalise_phone(value)


class UserRead(ORMModel):
    id: uuid.UUID
    email: EmailStr
    full_name: str
    phone: str | None
    role: UserRole
    is_active: bool
    is_verified: bool
    created_at: datetime
    last_login_at: datetime | None


class UserSummary(ORMModel):
    """The reduced view embedded in incident responses."""

    id: uuid.UUID
    full_name: str
    role: UserRole
