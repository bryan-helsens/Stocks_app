"""FastAPI dependencies: current user resolution and service wiring.

These bind the request-scoped DB session to repositories and application
services, and resolve the authenticated user from the Bearer access token.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import security
from app.core.errors import AuthenticationError
from app.infrastructure.db import models
from app.infrastructure.db.base import get_session
from app.infrastructure.db.repositories import (
    SqlAssetRepository,
    SqlDividendRepository,
    SqlPositionRepository,
    SqlTransactionRepository,
)
from app.infrastructure.db.repositories.users import (
    SqlDeviceRepository,
    SqlPortfolioRepository,
    SqlUserRepository,
)
from app.infrastructure.market_data import get_market_data_provider

_bearer = HTTPBearer(auto_error=False)

SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def get_current_user(
    session: SessionDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> models.User:
    """Resolve and return the authenticated, active user, or raise 401."""
    if credentials is None:
        raise AuthenticationError("Missing bearer token.")
    try:
        payload = security.decode_token(credentials.credentials, expected_type="access")
    except security.TokenError as exc:
        raise AuthenticationError("Invalid or expired access token.") from exc

    user_id = UUID(payload["sub"])
    user = await SqlUserRepository(session).get(user_id)
    if user is None or not user.is_active:
        raise AuthenticationError("Account not found or inactive.")
    return user


CurrentUser = Annotated[models.User, Depends(get_current_user)]


# --------------------------------------------------------------------------- #
# Service factories
# --------------------------------------------------------------------------- #
def get_auth_service(session: SessionDep):
    from app.application.services.auth import AuthService

    return AuthService(SqlUserRepository(session), SqlDeviceRepository(session))


def get_transaction_service(session: SessionDep):
    from app.application.services.transactions import TransactionService

    return TransactionService(
        SqlTransactionRepository(session),
        SqlPositionRepository(session),
        SqlPortfolioRepository(session),
    )


def get_portfolio_service(session: SessionDep):
    from app.application.services.portfolio import PortfolioService

    return PortfolioService(
        SqlPortfolioRepository(session),
        SqlPositionRepository(session),
        SqlAssetRepository(session),
        get_market_data_provider(),
    )


def get_dividend_repo(session: SessionDep) -> SqlDividendRepository:
    return SqlDividendRepository(session)
