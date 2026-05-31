"""Dividend dashboard & calendar endpoints (M5/M6)."""

from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, SessionDep
from app.application.services.dividend_calendar_service import DividendCalendarService
from app.application.services.dividend_service import DividendService
from app.schemas.dividend import (
    CalendarEventResponse,
    DividendCalendarResponse,
    DividendDashboardResponse,
)

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


@router.get("/calendar", response_model=DividendCalendarResponse)
async def dividend_calendar(
    user: CurrentUser,
    session: SessionDep,
    start: date = Query(...),
    end: date = Query(...),
    portfolio_id: UUID | None = Query(default=None),
    include_projected: bool = Query(default=True),
) -> DividendCalendarResponse:
    """Confirmed + projected dividend events between *start* and *end* (M6)."""
    cal = await DividendCalendarService(session).calendar(
        user.id,
        start=start,
        end=end,
        portfolio_id=portfolio_id,
        include_projected=include_projected,
    )
    return DividendCalendarResponse(
        events=[
            CalendarEventResponse(
                date=e.date,
                kind=e.kind,
                event_type=e.event_type,
                ticker=e.ticker,
                name=e.name,
                amount=e.amount,
                currency=e.currency,
                portfolio_id=e.portfolio_id,
            )
            for e in cal.events
        ],
        note=cal.note,
    )
