"""Authentication endpoints (M1)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.deps import CurrentUser, get_auth_service
from app.application.services.auth import AuthService
from app.schemas.auth import (
    BindDeviceRequest,
    LoginRequest,
    LoginResponse,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    TwoFactorConfirmRequest,
    TwoFactorSetupResponse,
    TwoFactorVerifyRequest,
    UserResponse,
)
from app.schemas.common import Message

router = APIRouter(prefix="/auth", tags=["auth"])

AuthDep = Annotated[AuthService, Depends(get_auth_service)]


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, auth: AuthDep) -> UserResponse:
    user = await auth.register(body.email, body.password, body.full_name)
    return UserResponse.model_validate(user)


@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest, auth: AuthDep) -> LoginResponse:
    result = await auth.authenticate(body.email, body.password)
    tokens = (
        TokenResponse(
            access_token=result.tokens.access_token,
            refresh_token=result.tokens.refresh_token,
        )
        if result.tokens
        else None
    )
    return LoginResponse(requires_2fa=result.requires_2fa, user_id=result.user_id, tokens=tokens)


@router.post("/2fa/verify", response_model=TokenResponse)
async def verify_2fa(body: TwoFactorVerifyRequest, auth: AuthDep) -> TokenResponse:
    pair = await auth.verify_2fa(body.user_id, body.code)
    return TokenResponse(access_token=pair.access_token, refresh_token=pair.refresh_token)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest, auth: AuthDep) -> TokenResponse:
    pair = await auth.refresh(body.refresh_token)
    return TokenResponse(access_token=pair.access_token, refresh_token=pair.refresh_token)


@router.get("/me", response_model=UserResponse)
async def me(user: CurrentUser) -> UserResponse:
    return UserResponse.model_validate(user)


@router.post("/2fa/setup", response_model=TwoFactorSetupResponse)
async def setup_2fa(user: CurrentUser, auth: AuthDep) -> TwoFactorSetupResponse:
    secret, uri = await auth.begin_2fa_setup(user.id)
    return TwoFactorSetupResponse(secret=secret, otpauth_uri=uri)


@router.post("/2fa/confirm", response_model=Message)
async def confirm_2fa(body: TwoFactorConfirmRequest, user: CurrentUser, auth: AuthDep) -> Message:
    await auth.confirm_2fa(user.id, body.code)
    return Message(message="2FA enabled.")


@router.post("/devices", response_model=Message, status_code=status.HTTP_201_CREATED)
async def bind_device(body: BindDeviceRequest, user: CurrentUser, auth: AuthDep) -> Message:
    await auth.bind_device(user.id, body.device_name, body.platform, body.refresh_token)
    return Message(message="Device bound for biometric login.")
