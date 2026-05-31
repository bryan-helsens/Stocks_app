"""Analysis & valuation application service (M8/M9).

Wires the pure scoring and valuation domain services to stored fundamentals and
live prices. Valuation inputs may be supplied explicitly (so the feature works
without a fundamentals provider) or taken from the latest stored fundamentals.
All output is educational/informational.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError, ValidationError
from app.domain.entities import AssetScore, Valuation
from app.domain.ports.market_data import MarketDataProvider
from app.domain.services import scoring
from app.domain.services import valuation as val
from app.infrastructure.db import models
from app.infrastructure.db.repositories.mappers import fundamentals_to_entity


@dataclass(slots=True)
class AnalysisResult:
    ticker: str
    score: AssetScore | None
    has_fundamentals: bool


class AnalysisService:
    def __init__(self, session: AsyncSession, market: MarketDataProvider) -> None:
        self._s = session
        self._market = market

    async def _asset(self, asset_id: UUID) -> models.Asset:
        asset = await self._s.get(models.Asset, asset_id)
        if asset is None:
            raise NotFoundError("Asset not found.")
        return asset

    async def _latest_fundamentals(self, asset_id: UUID) -> models.Fundamentals | None:
        res = await self._s.execute(
            select(models.Fundamentals)
            .where(models.Fundamentals.asset_id == asset_id)
            .order_by(models.Fundamentals.as_of.desc())
            .limit(1)
        )
        return res.scalar_one_or_none()

    async def score(self, asset_id: UUID) -> AnalysisResult:
        asset = await self._asset(asset_id)
        fundamentals = await self._latest_fundamentals(asset_id)
        if fundamentals is None:
            return AnalysisResult(ticker=asset.ticker, score=None, has_fundamentals=False)
        score = scoring.score_asset(fundamentals_to_entity(fundamentals))
        return AnalysisResult(ticker=asset.ticker, score=score, has_fundamentals=True)

    async def valuation(
        self,
        asset_id: UUID,
        *,
        current_price: Decimal | None = None,
        # DCF inputs
        free_cash_flow: Decimal | None = None,
        shares_outstanding: Decimal | None = None,
        growth_rate: Decimal = Decimal("0.08"),
        discount_rate: Decimal = Decimal("0.10"),
        terminal_growth: Decimal = Decimal("0.025"),
        years: int = 10,
        # DDM inputs
        dividend_per_share: Decimal | None = None,
        dividend_growth: Decimal = Decimal("0.05"),
        required_return: Decimal = Decimal("0.09"),
        # Multiples inputs
        eps: Decimal | None = None,
        peer_pe: Decimal | None = None,
    ) -> list[Valuation]:
        """Run available valuation models and return them plus a blend.

        Missing model inputs are skipped gracefully. The current price is taken
        from the market provider when not supplied.
        """
        asset = await self._asset(asset_id)
        fundamentals = await self._latest_fundamentals(asset_id)

        if current_price is None:
            quote = await self._market.get_quote(asset.ticker)
            current_price = quote.price if quote else Decimal(0)

        # Fall back to stored fundamentals for unspecified inputs.
        if fundamentals is not None:
            eps = eps if eps is not None else fundamentals.eps
            free_cash_flow = free_cash_flow if free_cash_flow is not None else fundamentals.fcf

        results: list[Valuation] = []
        if free_cash_flow is not None and shares_outstanding is not None:
            results.append(
                val.dcf_fair_value(
                    free_cash_flow, shares_outstanding, growth_rate, discount_rate,
                    terminal_growth, years, current_price,
                )
            )
        if dividend_per_share is not None:
            results.append(
                val.ddm_fair_value(
                    dividend_per_share, dividend_growth, required_return, current_price,
                )
            )
        if eps is not None and peer_pe is not None:
            results.append(val.multiples_fair_value(eps, peer_pe, current_price))

        if not results:
            raise ValidationError(
                "Onvoldoende gegevens voor waardering. Geef DCF-, DDM- of multiples-inputs op."
            )
        if len(results) > 1:
            results.append(val.blended_valuation(results))
        return results
