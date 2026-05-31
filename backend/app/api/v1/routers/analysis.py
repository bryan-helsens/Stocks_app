"""Stock analysis & valuation endpoints (M8/M9) — educational only."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter

from app.api.deps import CurrentUser, SessionDep
from app.application.services.analysis_service import AnalysisService
from app.infrastructure.market_data import get_market_data_provider
from app.schemas.analysis import (
    ScoreResponse,
    ValuationItem,
    ValuationRequest,
    ValuationResponse,
)

router = APIRouter(prefix="/analysis", tags=["analysis"])


@router.get("/asset/{asset_id}/score", response_model=ScoreResponse)
async def asset_score(asset_id: UUID, _: CurrentUser, session: SessionDep) -> ScoreResponse:
    service = AnalysisService(session, get_market_data_provider())
    result = await service.score(asset_id)
    s = result.score
    return ScoreResponse(
        ticker=result.ticker,
        has_fundamentals=result.has_fundamentals,
        total=s.total if s else None,
        valuation=s.valuation if s else None,
        growth=s.growth if s else None,
        health=s.health if s else None,
        dividend=s.dividend if s else None,
        breakdown=s.breakdown if s else None,
    )


@router.post("/asset/{asset_id}/valuation", response_model=ValuationResponse)
async def asset_valuation(
    asset_id: UUID, body: ValuationRequest, _: CurrentUser, session: SessionDep
) -> ValuationResponse:
    service = AnalysisService(session, get_market_data_provider())
    results = await service.valuation(
        asset_id,
        current_price=body.current_price,
        free_cash_flow=body.free_cash_flow,
        shares_outstanding=body.shares_outstanding,
        growth_rate=body.growth_rate,
        discount_rate=body.discount_rate,
        terminal_growth=body.terminal_growth,
        years=body.years,
        dividend_per_share=body.dividend_per_share,
        dividend_growth=body.dividend_growth,
        required_return=body.required_return,
        eps=body.eps,
        peer_pe=body.peer_pe,
    )
    return ValuationResponse(
        items=[
            ValuationItem(
                method=v.method,
                fair_value=v.fair_value,
                current_price=v.current_price,
                margin_of_safety=v.margin_of_safety,
                verdict=v.verdict,
                assumptions=v.assumptions,
            )
            for v in results
        ],
    )
