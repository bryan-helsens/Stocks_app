"""Portfolio & holdings endpoints (M2/M7)."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.api.deps import CurrentUser, get_portfolio_service
from app.application.services.portfolio import PortfolioService
from app.schemas.portfolio import (
    AssetResponse,
    HoldingResponse,
    PortfolioCreate,
    PortfolioResponse,
    PortfolioSummaryResponse,
)

router = APIRouter(prefix="/portfolios", tags=["portfolios"])

PortfolioDep = Annotated[PortfolioService, Depends(get_portfolio_service)]


@router.post("", response_model=PortfolioResponse, status_code=status.HTTP_201_CREATED)
async def create_portfolio(
    body: PortfolioCreate, user: CurrentUser, svc: PortfolioDep
) -> PortfolioResponse:
    p = await svc.create(user.id, body.name, body.base_currency, body.is_default)
    return PortfolioResponse.model_validate(p)


@router.get("", response_model=list[PortfolioResponse])
async def list_portfolios(user: CurrentUser, svc: PortfolioDep) -> list[PortfolioResponse]:
    items = await svc.list(user.id)
    return [PortfolioResponse.model_validate(p) for p in items]


@router.get("/{portfolio_id}/summary", response_model=PortfolioSummaryResponse)
async def portfolio_summary(
    portfolio_id: UUID, user: CurrentUser, svc: PortfolioDep
) -> PortfolioSummaryResponse:
    s = await svc.summary(portfolio_id, user.id)
    holdings = [
        HoldingResponse(
            asset=AssetResponse(
                id=h.asset.id,
                ticker=h.asset.ticker,
                name=h.asset.name,
                asset_class=h.asset.asset_class,
                isin=h.asset.isin,
                sector=h.asset.sector,
                country=h.asset.country,
                currency=h.asset.currency,
            ),
            quantity=h.position.quantity,
            avg_cost=h.position.avg_cost,
            total_invested=h.position.total_invested,
            realized_pnl=h.position.realized_pnl,
            price=h.price,
            market_value=h.market_value,
            unrealized_pnl=h.unrealized_pnl,
            unrealized_pct=h.unrealized_pct,
        )
        for h in s.holdings
    ]
    return PortfolioSummaryResponse(
        portfolio_id=s.portfolio_id,
        name=s.name,
        base_currency=s.base_currency,
        total_value=s.total_value,
        total_invested=s.total_invested,
        total_unrealized=s.total_unrealized,
        realized_pnl=s.realized_pnl,
        holdings=holdings,
    )
