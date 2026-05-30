"""Belgian tax endpoints (M17) — informational/educational only."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import CurrentUser, SessionDep
from app.application.services.tax_service import TaxService
from app.schemas.tax import TaxLineResponse, TaxSummaryResponse

router = APIRouter(prefix="/tax/be", tags=["tax"])


@router.get("/report", response_model=TaxSummaryResponse)
async def belgian_tax_report(
    year: int, user: CurrentUser, session: SessionDep
) -> TaxSummaryResponse:
    """Indicative Belgian dividend/TOB/withholding overview for a year.

    ⚠️ Informatief en educatief — geen fiscaal advies (FR17.4).
    """
    summary = await TaxService(session).build_year_summary(user.id, year)
    return TaxSummaryResponse(
        year=summary.year,
        foreign_dividends_gross=summary.foreign_dividends_gross,
        belgian_dividends_gross=summary.belgian_dividends_gross,
        withholding_tax_foreign=summary.withholding_tax_foreign,
        belgian_rv=summary.belgian_rv,
        tob_total=summary.tob_total,
        fees_total=summary.fees_total,
        net_dividend_income=summary.net_dividend_income,
        reclaimable_exemption=summary.reclaimable_exemption,
        lines=[
            TaxLineResponse(
                asset=line.asset,
                source_country=line.source_country,
                gross=line.gross,
                foreign_withholding=line.foreign_withholding,
                belgian_rv=line.belgian_rv,
                net=line.net,
                is_foreign=line.is_foreign,
            )
            for line in summary.lines
        ],
        disclaimer=summary.disclaimer,
    )
