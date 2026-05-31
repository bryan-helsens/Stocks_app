"""Auth request/response schemas."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from app.schemas.common import ORMModel


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str | None = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TwoFactorVerifyRequest(BaseModel):
    user_id: UUID
    code: str = Field(min_length=6, max_length=6)


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class LoginResponse(BaseModel):
    """Either tokens, or a 2FA challenge (tokens null, requires_2fa true)."""

    requires_2fa: bool
    user_id: UUID
    tokens: TokenResponse | None = None


class TwoFactorSetupResponse(BaseModel):
    secret: str
    otpauth_uri: str


class TwoFactorConfirmRequest(BaseModel):
    code: str = Field(min_length=6, max_length=6)


class UserResponse(ORMModel):
    id: UUID
    email: EmailStr
    full_name: str | None
    base_currency: str
    locale: str
    is_admin: bool
    totp_enabled: bool


class BindDeviceRequest(BaseModel):
    device_name: str
    platform: str
    refresh_token: str
