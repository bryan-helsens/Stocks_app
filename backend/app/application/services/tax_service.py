"""Belgian tax application service (M17) — INFORMATIONAL ONLY.

Aggregates a user's dividends and tax/fee transactions for a calendar year into
an indicative Belgian tax overview using the pure :mod:`app.domain.services.tax_be`
calculations. This is **not** tax advice (FR17.4); the disclaimer is always
attached and surfaced in the UI and PDF export.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy import extract, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.services import tax_be
from app.domain.services.tax_be import TaxSummary
from app.domain.value_objects.enums import TransactionType
from app.infrastructure.db import models

# Default foreign withholding assumptions by source country (informational).
# Users can refine these; treaties and reclaim rules vary.
_DEFAULT_FOREIGN_WHT: dict[str, Decimal] = {
    "US": Decimal("0.15"),
    "FR": Decimal("0.128"),
    "DE": Decimal("0.26375"),
    "NL": Decimal("0.15"),
    "GB": Decimal("0.0"),
    "CH": Decimal("0.35"),
}


class TaxService:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def build_year_summary(self, user_id: UUID, year: int) -> TaxSummary:
        """Aggregate dividends, TOB and fees for *year* into a tax overview."""
        dividend_lines = await self._dividend_lines(user_id, year)
        tob_total = await self._sum_tax(user_id, year, tob_only=True)
        fees_total = await self._sum_fees(user_id, year)

        summary = tax_be.build_tax_summary(
            year=year,
            dividend_lines=dividend_lines,
            tob_total=tob_total,
            fees_total=fees_total,
        )
        return summary

    async def _dividend_lines(self, user_id: UUID, year: int) -> list[tax_be.DividendTaxLine]:
        # Prefer the dedicated dividends table; fall back to DIVIDEND transactions.
        res = await self._s.execute(
            select(models.Dividend, models.Asset)
            .join(models.Asset, models.Asset.id == models.Dividend.asset_id, isouter=True)
            .where(
                models.Dividend.user_id == user_id,
                extract("year", models.Dividend.pay_date) == year,
            )
        )
        lines: list[tax_be.DividendTaxLine] = []
        rows = res.all()
        if rows:
            for div, asset in rows:
                country = (div.source_country or (asset.country if asset else None) or "")
                fw_rate = _DEFAULT_FOREIGN_WHT.get(country.upper(), Decimal("0.15"))
                # If withholding already recorded, derive an effective rate.
                if div.gross_amount and div.withholding_tax and div.gross_amount > 0:
                    fw_rate = div.withholding_tax / div.gross_amount
                lines.append(
                    tax_be.compute_dividend_tax(
                        gross=div.gross_amount,
                        source_country=country or None,
                        foreign_withholding_rate=fw_rate,
                        asset_label=asset.ticker if asset else "",
                    )
                )
            return lines

        # Fallback: DIVIDEND transactions converted to base currency.
        res2 = await self._s.execute(
            select(models.Transaction, models.Asset)
            .join(models.Asset, models.Asset.id == models.Transaction.asset_id, isouter=True)
            .where(
                models.Transaction.user_id == user_id,
                models.Transaction.type == TransactionType.DIVIDEND,
                models.Transaction.deleted_at.is_(None),
                extract("year", models.Transaction.trade_date) == year,
            )
        )
        for tx, asset in res2.all():
            country = (asset.country if asset else None) or ""
            fw_rate = _DEFAULT_FOREIGN_WHT.get(country.upper(), Decimal("0.15"))
            gross_base = (tx.gross_amount or Decimal(0)) * (tx.fx_rate or Decimal(1))
            lines.append(
                tax_be.compute_dividend_tax(
                    gross=gross_base,
                    source_country=country or None,
                    foreign_withholding_rate=fw_rate,
                    asset_label=asset.ticker if asset else "",
                )
            )
        return lines

    async def _sum_tax(self, user_id: UUID, year: int, *, tob_only: bool) -> Decimal:
        res = await self._s.execute(
            select(models.Transaction).where(
                models.Transaction.user_id == user_id,
                models.Transaction.type == TransactionType.TAX,
                models.Transaction.deleted_at.is_(None),
                extract("year", models.Transaction.trade_date) == year,
            )
        )
        total = Decimal(0)
        for tx in res.scalars().all():
            amount = (tx.tax or tx.gross_amount or Decimal(0)) * (tx.fx_rate or Decimal(1))
            total += amount
        return total

    async def _sum_fees(self, user_id: UUID, year: int) -> Decimal:
        res = await self._s.execute(
            select(models.Transaction).where(
                models.Transaction.user_id == user_id,
                models.Transaction.type == TransactionType.FEE,
                models.Transaction.deleted_at.is_(None),
                extract("year", models.Transaction.trade_date) == year,
            )
        )
        total = Decimal(0)
        for tx in res.scalars().all():
            amount = (tx.fee or tx.gross_amount or Decimal(0)) * (tx.fx_rate or Decimal(1))
            total += amount
        return total
