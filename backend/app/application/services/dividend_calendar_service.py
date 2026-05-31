"""Dividend calendar application service (M6).

Combines two sources into a single dated calendar:
  * **Confirmed** events — dividends the user actually received (from ``dividends``).
  * **Projected** events — upcoming pay/ex dates from ``dividend_schedule`` for
    assets the user currently holds, with the expected amount estimated from the
    held quantity. Projections are clearly labelled estimates (BR10).

Supports filtering by portfolio, month and kind (confirmed/projected).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.value_objects.enums import DividendKind
from app.infrastructure.db import models


@dataclass(slots=True)
class CalendarEvent:
    date: date
    kind: str  # "CONFIRMED" | "PROJECTED"
    event_type: str  # "PAID" | "EX_DIVIDEND" | "PAY_DATE"
    ticker: str
    name: str
    amount: Decimal | None
    currency: str
    portfolio_id: UUID | None = None


@dataclass(slots=True)
class DividendCalendar:
    events: list[CalendarEvent] = field(default_factory=list)
    note: str = "Verwachte dividenden zijn schattingen, geen garanties."


class DividendCalendarService:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def calendar(
        self,
        user_id: UUID,
        *,
        start: date,
        end: date,
        portfolio_id: UUID | None = None,
        include_projected: bool = True,
    ) -> DividendCalendar:
        events: list[CalendarEvent] = []
        events.extend(await self._confirmed(user_id, start, end, portfolio_id))
        if include_projected:
            events.extend(await self._projected(user_id, start, end, portfolio_id))
        events.sort(key=lambda e: e.date)
        return DividendCalendar(events=events)

    async def _confirmed(
        self, user_id: UUID, start: date, end: date, portfolio_id: UUID | None
    ) -> list[CalendarEvent]:
        stmt = (
            select(models.Dividend, models.Asset)
            .join(models.Asset, models.Asset.id == models.Dividend.asset_id, isouter=True)
            .where(
                models.Dividend.user_id == user_id,
                models.Dividend.pay_date.is_not(None),
                models.Dividend.pay_date >= start,
                models.Dividend.pay_date <= end,
            )
        )
        if portfolio_id is not None:
            stmt = stmt.where(models.Dividend.portfolio_id == portfolio_id)
        res = await self._s.execute(stmt)
        out: list[CalendarEvent] = []
        for div, asset in res.all():
            out.append(
                CalendarEvent(
                    date=div.pay_date,
                    kind=DividendKind.CONFIRMED.value,
                    event_type="PAID",
                    ticker=asset.ticker if asset else "?",
                    name=asset.name if asset else "?",
                    amount=div.net_amount or div.gross_amount,
                    currency=div.currency,
                    portfolio_id=div.portfolio_id,
                )
            )
        return out

    async def _projected(
        self, user_id: UUID, start: date, end: date, portfolio_id: UUID | None
    ) -> list[CalendarEvent]:
        # Held quantity per asset (optionally within one portfolio).
        pos_stmt = select(models.Position).where(models.Position.user_id == user_id)
        if portfolio_id is not None:
            pos_stmt = pos_stmt.where(models.Position.portfolio_id == portfolio_id)
        pos_res = await self._s.execute(pos_stmt)
        held: dict[UUID, Decimal] = {}
        for p in pos_res.scalars().all():
            if p.quantity and p.quantity > 0:
                held[p.asset_id] = held.get(p.asset_id, Decimal(0)) + p.quantity
        if not held:
            return []

        sched_res = await self._s.execute(
            select(models.DividendSchedule, models.Asset)
            .join(models.Asset, models.Asset.id == models.DividendSchedule.asset_id, isouter=True)
            .where(
                models.DividendSchedule.asset_id.in_(list(held.keys())),
                models.DividendSchedule.pay_date.is_not(None),
                models.DividendSchedule.pay_date >= start,
                models.DividendSchedule.pay_date <= end,
            )
        )
        out: list[CalendarEvent] = []
        for sched, asset in sched_res.all():
            shares = held.get(sched.asset_id, Decimal(0))
            expected = (sched.amount_per_share or Decimal(0)) * shares
            if sched.ex_date and start <= sched.ex_date <= end:
                out.append(
                    CalendarEvent(
                        date=sched.ex_date,
                        kind=DividendKind.PROJECTED.value,
                        event_type="EX_DIVIDEND",
                        ticker=asset.ticker if asset else "?",
                        name=asset.name if asset else "?",
                        amount=None,
                        currency=sched.currency,
                    )
                )
            out.append(
                CalendarEvent(
                    date=sched.pay_date,
                    kind=DividendKind.PROJECTED.value,
                    event_type="PAY_DATE",
                    ticker=asset.ticker if asset else "?",
                    name=asset.name if asset else "?",
                    amount=expected,
                    currency=sched.currency,
                )
            )
        return out
