"""Authentication schemas."""

from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.schemas.user import UserRead


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def _lower(cls, value: str) -> str:
        return value.strip().lower()


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=16, max_length=512)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"  # noqa: S105 - a scheme name, not a secret
    expires_in: int = Field(description="Access-token lifetime in seconds.")
    refresh_token: str
    user: UserRead
