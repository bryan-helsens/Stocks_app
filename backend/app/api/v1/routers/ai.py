"""AI analyst & Koop/Houd/Verkoop endpoints (M12/M13).

The route builds a deterministic context with the domain/portfolio services,
then asks the chosen LLM provider to interpret it. The analysis is persisted to
``ai_analyses`` for auditability and always carries the educational disclaimer.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import CurrentUser, SessionDep, get_portfolio_service
from app.application.services.ai_analysis import AIAnalysisService
from app.application.services.ai_context import build_portfolio_context, build_position_context
from app.application.services.portfolio import PortfolioService
from app.core.errors import NotFoundError
from app.domain.value_objects.enums import AIProvider
from app.infrastructure.ai import get_llm_provider
from app.infrastructure.db import models
from app.infrastructure.db.repositories import SqlAssetRepository
from app.infrastructure.db.repositories.mappers import fundamentals_to_entity
from app.schemas.ai import (
    PortfolioAnalysisRequest,
    PortfolioAnalysisResponse,
    PositionAnalysisRequest,
    PositionAnalysisResponse,
)

router = APIRouter(prefix="/ai", tags=["ai"])

PortfolioDep = Annotated[PortfolioService, Depends(get_portfolio_service)]


async def _resolve_provider(session, user_id, requested: AIProvider | None) -> AIProvider:
    if requested is not None:
        return requested
    settings_row = await session.get(models.UserSettings, user_id)
    return settings_row.ai_provider if settings_row else AIProvider.OLLAMA


async def _persist(session, user, scope, provider, result, *, portfolio_id=None, asset_id=None,
                   recommendation=None) -> None:
    data = result.data
    session.add(
        models.AIAnalysis(
            user_id=user.id,
            scope=scope,
            portfolio_id=portfolio_id,
            asset_id=asset_id,
            provider=AIProvider(result.provider),
            model=result.model,
            recommendation=recommendation,
            confidence=Decimal(str(data.get("confidence", 0))) if "confidence" in data else None,
            risk_score=Decimal(str(data.get("risk_score", 0))),
            strengths=data.get("strengths"),
            weaknesses=data.get("weaknesses"),
            opportunities=data.get("opportunities"),
            threats=data.get("threats"),
            summary=data.get("summary"),
            context_snapshot=result.context,
            raw_response=result.raw,
            disclaimer=data["disclaimer"],
        )
    )


@router.post("/analyze/portfolio", response_model=PortfolioAnalysisResponse)
async def analyze_portfolio(
    body: PortfolioAnalysisRequest,
    user: CurrentUser,
    session: SessionDep,
    portfolios: PortfolioDep,
) -> PortfolioAnalysisResponse:
    summary = await portfolios.summary(body.portfolio_id, user.id)
    context = build_portfolio_context(summary)

    provider = await _resolve_provider(session, user.id, body.provider)
    service = AIAnalysisService(get_llm_provider(provider))
    result = await service.analyze_portfolio(context)
    await _persist(session, user, "portfolio", provider, result, portfolio_id=body.portfolio_id)

    d = result.data
    return PortfolioAnalysisResponse(
        provider=result.provider, model=result.model,
        summary=d["summary"], risk_score=d["risk_score"],
        concentration_note=d["concentration_note"],
        strengths=d["strengths"], weaknesses=d["weaknesses"],
        opportunities=d["opportunities"], threats=d["threats"],
        disclaimer=d["disclaimer"],
    )


@router.post("/analyze/position", response_model=PositionAnalysisResponse)
async def analyze_position(
    body: PositionAnalysisRequest,
    user: CurrentUser,
    session: SessionDep,
    portfolios: PortfolioDep,
) -> PositionAnalysisResponse:
    summary = await portfolios.summary(body.portfolio_id, user.id)
    holding = next((h for h in summary.holdings if h.asset.id == body.asset_id), None)
    if holding is None:
        raise NotFoundError("Position not found in this portfolio.")

    # Latest fundamentals (if available) feed the quality score in the context.
    fund_row = None
    from sqlalchemy import select

    res = await session.execute(
        select(models.Fundamentals)
        .where(models.Fundamentals.asset_id == body.asset_id)
        .order_by(models.Fundamentals.as_of.desc())
        .limit(1)
    )
    fund_model = res.scalar_one_or_none()
    if fund_model is not None:
        fund_row = fundamentals_to_entity(fund_model)

    total = summary.total_value if summary.total_value > 0 else summary.total_invested
    weight = float(
        round((holding.market_value or holding.position.total_invested) / total, 4)
    ) if total > 0 else 0.0

    context = build_position_context(
        ticker=holding.asset.ticker,
        name=holding.asset.name,
        quantity=holding.position.quantity,
        avg_cost=holding.position.avg_cost,
        price=holding.price,
        fundamentals=fund_row,
        portfolio_weight=weight,
    )

    provider = await _resolve_provider(session, user.id, body.provider)
    service = AIAnalysisService(get_llm_provider(provider))
    result = await service.analyze_position(context)

    d = result.data
    from app.domain.value_objects.enums import Recommendation

    await _persist(
        session, user, "position", provider, result,
        portfolio_id=body.portfolio_id, asset_id=body.asset_id,
        recommendation=Recommendation(d["recommendation"]),
    )
    return PositionAnalysisResponse(
        provider=result.provider, model=result.model,
        recommendation=d["recommendation"], confidence=d["confidence"],
        risk_score=d["risk_score"], summary=d["summary"],
        strengths=d["strengths"], weaknesses=d["weaknesses"],
        opportunities=d["opportunities"], threats=d["threats"],
        disclaimer=d["disclaimer"],
    )


# Unused import guard for asset repo (kept for symmetry/future use).
_ = SqlAssetRepository
