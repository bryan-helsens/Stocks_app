"""Report generation & export endpoints (deliverable 12 / M18).

Generates a report on demand and streams it back as a downloadable file.
Supported formats: PDF, CSV, Excel, JSON. For very large reports this would be
offloaded to a Celery task; the synchronous path here covers typical sizes.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response

from app.api.deps import CurrentUser, SessionDep, get_portfolio_service
from app.application.services.portfolio import PortfolioService
from app.application.services.report_service import ReportService
from app.domain.value_objects.enums import ReportFormat, ReportType

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/generate")
async def generate_report(
    user: CurrentUser,
    session: SessionDep,
    portfolios: Annotated[PortfolioService, Depends(get_portfolio_service)],
    type: ReportType,
    format: ReportFormat = ReportFormat.PDF,
    portfolio_id: UUID | None = Query(default=None),
    year: int | None = Query(default=None),
) -> Response:
    service = ReportService(session, portfolios)
    content, mime, filename = await service.generate(
        user.id, type, format,
        portfolio_id=portfolio_id, year=year, base_currency=user.base_currency,
    )
    return Response(
        content=content,
        media_type=mime,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
