"""Dividend dashboard endpoints (M5/M6)."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import CurrentUser, SessionDep
from app.application.services.dividend_service import DividendService
from app.schemas.dividend import DividendDashboardResponse

router = APIRouter(prefix="/dividends", tags=["dividends"])


@router.get("/dashboard", response_model=DividendDashboardResponse)
async def dividend_dashboard(user: CurrentUser, session: SessionDep) -> DividendDashboardResponse:
    dash = await DividendService(session).dashboard(user.id, user.base_currency)
    return DividendDashboardResponse(
        total_received=dash.total_received,
        by_month=dash.by_month,
        by_year=dash.by_year,
        by_sector=dash.by_sector,
        by_country=dash.by_country,
        cagr=dash.cagr,
        avg_monthly=dash.avg_monthly,
        projected_next_12m=dash.projected_next_12m,
        currency=dash.currency,
        note=dash.note,
    )
