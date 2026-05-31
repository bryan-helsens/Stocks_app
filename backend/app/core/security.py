"""Security primitives: password hashing, JWT, TOTP (2FA) and field encryption.

This module is intentionally framework-agnostic (no FastAPI imports) so it can
be unit-tested in isolation. FastAPI dependencies that *use* these helpers live
in :mod:`app.api.deps`.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import pyotp
from cryptography.fernet import Fernet, InvalidToken
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

# --------------------------------------------------------------------------- #
# Password hashing
# --------------------------------------------------------------------------- #
_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    """Return a bcrypt hash for *plain*."""
    return _pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Return True if *plain* matches the stored *hashed* value."""
    return _pwd_context.verify(plain, hashed)


# --------------------------------------------------------------------------- #
# JSON Web Tokens
# --------------------------------------------------------------------------- #
TokenType = Literal["access", "refresh"]


def _create_token(
    subject: str,
    token_type: TokenType,
    expires_delta: timedelta,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": subject,
        "type": token_type,
        "iat": int(now.timestamp()),
        "exp": int((now + expires_delta).timestamp()),
        "jti": secrets.token_urlsafe(16),
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_access_token(subject: str, extra_claims: dict[str, Any] | None = None) -> str:
    """Create a short-lived access token for *subject* (the user id)."""
    return _create_token(
        subject,
        "access",
        timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        extra_claims,
    )


def create_refresh_token(subject: str, device_id: str | None = None) -> str:
    """Create a long-lived refresh token, optionally bound to a device."""
    extra = {"device_id": device_id} if device_id else None
    return _create_token(
        subject,
        "refresh",
        timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        extra,
    )


def decode_token(token: str, expected_type: TokenType | None = None) -> dict[str, Any]:
    """Decode and validate a JWT.

    Raises :class:`TokenError` if the token is invalid, expired, or of an
    unexpected type.
    """
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
        )
    except JWTError as exc:  # expired, bad signature, malformed
        raise TokenError(str(exc)) from exc
    if expected_type is not None and payload.get("type") != expected_type:
        raise TokenError(
            f"Expected {expected_type} token, got {payload.get('type')!r}"
        )
    return payload


class TokenError(Exception):
    """Raised when a JWT cannot be validated."""


# --------------------------------------------------------------------------- #
# Refresh-token storage hashing (we store only a hash of refresh tokens)
# --------------------------------------------------------------------------- #
def hash_refresh_token(token: str) -> str:
    """Return a SHA-256 hex digest used to store refresh tokens at rest."""
    return hashlib.sha256(token.encode()).hexdigest()


# --------------------------------------------------------------------------- #
# TOTP (2FA)
# --------------------------------------------------------------------------- #
def generate_totp_secret() -> str:
    """Return a new base32 TOTP secret."""
    return pyotp.random_base32()


def totp_provisioning_uri(secret: str, account_name: str) -> str:
    """Return an otpauth:// URI suitable for QR-code generation."""
    return pyotp.TOTP(secret).provisioning_uri(
        name=account_name, issuer_name=settings.APP_NAME
    )


def verify_totp(secret: str, code: str, valid_window: int = 1) -> bool:
    """Verify a 6-digit TOTP *code* against *secret* (±1 step tolerance)."""
    return pyotp.TOTP(secret).verify(code, valid_window=valid_window)


# --------------------------------------------------------------------------- #
# App-level field encryption (for TOTP secrets, provider API keys, etc.)
# --------------------------------------------------------------------------- #
def _fernet() -> Fernet:
    """Derive a stable Fernet key from SECRET_KEY.

    Uses SHA-256 of the secret as the 32-byte key material. Rotating
    SECRET_KEY therefore invalidates existing ciphertexts — document this in
    operations runbooks before rotating in production.
    """
    digest = hashlib.sha256(settings.SECRET_KEY.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(plaintext: str) -> str:
    """Encrypt a sensitive value for at-rest storage."""
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt_secret(ciphertext: str) -> str:
    """Decrypt a value produced by :func:`encrypt_secret`."""
    try:
        return _fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken as exc:
        raise TokenError("Could not decrypt secret") from exc


def constant_time_compare(a: str, b: str) -> bool:
    """Timing-safe string comparison."""
    return secrets.compare_digest(a, b)
