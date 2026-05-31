"""Dividend dashboard application service (M5/M6).

Aggregates received dividends into monthly/yearly income, per-sector and
per-country breakdowns, and computes portfolio-level yield metrics using the
pure dividend domain service. Projections are clearly labelled estimates (BR10).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.services import dividends as div_calc
from app.infrastructure.db import models


@dataclass(slots=True)
class DividendDashboard:
    total_received: Decimal
    by_month: dict[str, Decimal]
    by_year: dict[int, Decimal]
    by_sector: dict[str, Decimal]
    by_country: dict[str, Decimal]
    cagr: Decimal | None
    avg_monthly: Decimal
    projected_next_12m: Decimal
    currency: str = "EUR"
    note: str = "Verwachte dividenden zijn schattingen, geen garanties."


class DividendService:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def dashboard(self, user_id: UUID, base_currency: str = "EUR") -> DividendDashboard:
        res = await self._s.execute(
            select(models.Dividend, models.Asset)
            .join(models.Asset, models.Asset.id == models.Dividend.asset_id, isouter=True)
            .where(models.Dividend.user_id == user_id)
            .order_by(models.Dividend.pay_date)
        )
        rows = res.all()

        total = Decimal(0)
        by_month: dict[str, Decimal] = defaultdict(lambda: Decimal(0))
        by_year: dict[int, Decimal] = defaultdict(lambda: Decimal(0))
        by_sector: dict[str, Decimal] = defaultdict(lambda: Decimal(0))
        by_country: dict[str, Decimal] = defaultdict(lambda: Decimal(0))

        for div, asset in rows:
            net = div.net_amount or div.gross_amount or Decimal(0)
            total += net
            if div.pay_date:
                by_month[div.pay_date.strftime("%Y-%m")] += net
                by_year[div.pay_date.year] += net
            country = div.source_country or (asset.country if asset else None) or "Unknown"
            by_sector[(asset.sector if asset else None) or "Unknown"] += net
            by_country[country] += net

        # Dividend CAGR from yearly totals.
        cagr = div_calc.dividend_cagr(list(by_year.items()))

        months_count = len(by_month) or 1
        avg_monthly = total / Decimal(months_count)

        # Naive forward projection: last full year grown by the CAGR (or flat).
        last_year_total = by_year[max(by_year)] if by_year else Decimal(0)
        growth = cagr if cagr is not None else Decimal(0)
        projected = last_year_total * (Decimal(1) + growth)

        return DividendDashboard(
            total_received=total,
            by_month=dict(sorted(by_month.items())),
            by_year=dict(sorted(by_year.items())),
            by_sector=dict(by_sector),
            by_country=dict(by_country),
            cagr=cagr,
            avg_monthly=avg_monthly,
            projected_next_12m=projected,
            currency=base_currency,
        )
