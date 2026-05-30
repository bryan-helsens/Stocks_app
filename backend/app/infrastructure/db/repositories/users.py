"""User, settings and portfolio repositories (work directly with ORM models).

Auth and portfolio CRUD operate close to the persistence model, so these
repositories return ORM instances rather than domain entities.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.db import models


class SqlUserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def get(self, user_id: UUID) -> models.User | None:
        return await self._s.get(models.User, user_id)

    async def get_by_email(self, email: str) -> models.User | None:
        res = await self._s.execute(select(models.User).where(models.User.email == email))
        return res.scalar_one_or_none()

    async def create(self, user: models.User) -> models.User:
        self._s.add(user)
        await self._s.flush()
        return user

    async def get_settings(self, user_id: UUID) -> models.UserSettings | None:
        return await self._s.get(models.UserSettings, user_id)

    async def ensure_settings(self, user_id: UUID) -> models.UserSettings:
        existing = await self.get_settings(user_id)
        if existing is not None:
            return existing
        s = models.UserSettings(user_id=user_id)
        self._s.add(s)
        await self._s.flush()
        return s


class SqlDeviceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def add(self, device: models.Device) -> models.Device:
        self._s.add(device)
        await self._s.flush()
        return device

    async def get(self, device_id: UUID) -> models.Device | None:
        return await self._s.get(models.Device, device_id)

    async def list_for_user(self, user_id: UUID) -> list[models.Device]:
        res = await self._s.execute(
            select(models.Device).where(
                models.Device.user_id == user_id, models.Device.revoked_at.is_(None)
            )
        )
        return list(res.scalars().all())


class SqlPortfolioRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def get(self, portfolio_id: UUID, user_id: UUID) -> models.Portfolio | None:
        res = await self._s.execute(
            select(models.Portfolio).where(
                models.Portfolio.id == portfolio_id,
                models.Portfolio.user_id == user_id,
                models.Portfolio.deleted_at.is_(None),
            )
        )
        return res.scalar_one_or_none()

    async def list_for_user(self, user_id: UUID) -> list[models.Portfolio]:
        res = await self._s.execute(
            select(models.Portfolio)
            .where(models.Portfolio.user_id == user_id, models.Portfolio.deleted_at.is_(None))
            .order_by(models.Portfolio.created_at)
        )
        return list(res.scalars().all())

    async def create(self, portfolio: models.Portfolio) -> models.Portfolio:
        self._s.add(portfolio)
        await self._s.flush()
        return portfolio

    async def default_for_user(self, user_id: UUID) -> models.Portfolio | None:
        res = await self._s.execute(
            select(models.Portfolio).where(
                models.Portfolio.user_id == user_id,
                models.Portfolio.is_default.is_(True),
                models.Portfolio.deleted_at.is_(None),
            )
        )
        return res.scalar_one_or_none()
