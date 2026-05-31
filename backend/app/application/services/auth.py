"""Authentication & account application service.

Orchestrates registration, login (with optional 2FA), token refresh, device
binding and 2FA setup. Security primitives come from :mod:`app.core.security`;
persistence from the user/device repositories. Rate-limiting and lockout are
enforced at the API/middleware layer; this service focuses on credential and
token logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from app.core import security
from app.core.errors import AuthenticationError, ConflictError, ValidationError
from app.infrastructure.db import models
from app.infrastructure.db.repositories.users import SqlDeviceRepository, SqlUserRepository


@dataclass(slots=True)
class TokenPair:
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


@dataclass(slots=True)
class LoginResult:
    """Either a token pair, or a signal that 2FA is required."""

    tokens: TokenPair | None
    requires_2fa: bool
    user_id: UUID


class AuthService:
    def __init__(self, users: SqlUserRepository, devices: SqlDeviceRepository) -> None:
        self._users = users
        self._devices = devices

    # ----- registration --------------------------------------------------
    async def register(
        self, email: str, password: str, full_name: str | None = None
    ) -> models.User:
        if len(password) < 8:
            raise ValidationError("Password must be at least 8 characters.")
        existing = await self._users.get_by_email(email)
        if existing is not None:
            raise ConflictError("An account with this email already exists.")
        user = models.User(
            email=email,
            password_hash=security.hash_password(password),
            full_name=full_name,
        )
        await self._users.create(user)
        await self._users.ensure_settings(user.id)
        return user

    # ----- login ---------------------------------------------------------
    async def authenticate(self, email: str, password: str) -> LoginResult:
        user = await self._users.get_by_email(email)
        # Always verify against a hash to reduce user-enumeration timing leaks.
        valid = (
            user is not None
            and user.is_active
            and security.verify_password(password, user.password_hash)
        )
        if not valid or user is None:
            raise AuthenticationError("Invalid email or password.")

        if user.totp_enabled:
            return LoginResult(tokens=None, requires_2fa=True, user_id=user.id)

        return LoginResult(tokens=self._issue_tokens(user.id), requires_2fa=False, user_id=user.id)

    async def verify_2fa(self, user_id: UUID, code: str) -> TokenPair:
        user = await self._users.get(user_id)
        if user is None or not user.totp_enabled or not user.totp_secret:
            raise AuthenticationError("2FA is not enabled for this account.")
        secret = security.decrypt_secret(user.totp_secret)
        if not security.verify_totp(secret, code):
            raise AuthenticationError("Invalid 2FA code.")
        return self._issue_tokens(user.id)

    # ----- refresh -------------------------------------------------------
    async def refresh(self, refresh_token: str) -> TokenPair:
        try:
            payload = security.decode_token(refresh_token, expected_type="refresh")
        except security.TokenError as exc:
            raise AuthenticationError("Invalid or expired refresh token.") from exc
        user_id = UUID(payload["sub"])
        user = await self._users.get(user_id)
        if user is None or not user.is_active:
            raise AuthenticationError("Account no longer active.")
        device_id = payload.get("device_id")
        return self._issue_tokens(user_id, device_id=device_id)

    # ----- 2FA setup -----------------------------------------------------
    async def begin_2fa_setup(self, user_id: UUID) -> tuple[str, str]:
        """Generate a TOTP secret, store it (encrypted) and return (secret, otpauth_uri)."""
        user = await self._users.get(user_id)
        if user is None:
            raise AuthenticationError("Unknown user.")
        secret = security.generate_totp_secret()
        user.totp_secret = security.encrypt_secret(secret)
        # Not enabled until the user confirms a valid code.
        uri = security.totp_provisioning_uri(secret, user.email)
        return secret, uri

    async def confirm_2fa(self, user_id: UUID, code: str) -> None:
        user = await self._users.get(user_id)
        if user is None or not user.totp_secret:
            raise ValidationError("Start 2FA setup first.")
        secret = security.decrypt_secret(user.totp_secret)
        if not security.verify_totp(secret, code):
            raise AuthenticationError("Invalid 2FA code.")
        user.totp_enabled = True

    async def disable_2fa(self, user_id: UUID) -> None:
        user = await self._users.get(user_id)
        if user is not None:
            user.totp_enabled = False
            user.totp_secret = None

    # ----- device binding ------------------------------------------------
    async def bind_device(
        self, user_id: UUID, device_name: str, platform: str, refresh_token: str
    ) -> models.Device:
        device = models.Device(
            user_id=user_id,
            device_name=device_name,
            platform=platform,
            refresh_token_hash=security.hash_refresh_token(refresh_token),
            biometric_enabled=True,
            last_seen_at=datetime.now(UTC),
        )
        return await self._devices.add(device)

    # ----- helpers -------------------------------------------------------
    def _issue_tokens(self, user_id: UUID, device_id: str | None = None) -> TokenPair:
        return TokenPair(
            access_token=security.create_access_token(str(user_id)),
            refresh_token=security.create_refresh_token(str(user_id), device_id=device_id),
        )
