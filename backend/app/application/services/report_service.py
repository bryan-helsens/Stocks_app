"""Report application service (deliverable 12).

Builds :class:`ReportDocument` instances from portfolio / dividend / tax data and
renders them to the requested format. Synchronous building is used here; for
heavy PDFs a Celery task wraps the same builder (workers, deliverable 7).
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.application.services.dividend_service import DividendService
from app.application.services.portfolio import PortfolioService
from app.application.services.tax_service import TaxService
from app.domain.value_objects.enums import ReportFormat, ReportType
from app.infrastructure.reports.document import ReportDocument, Section, Table
from app.infrastructure.reports.renderers import render


class ReportService:
    def __init__(
        self,
        session: AsyncSession,
        portfolio_service: PortfolioService | None = None,
    ) -> None:
        self._s = session
        self._portfolio = portfolio_service

    async def generate(
        self,
        user_id: UUID,
        report_type: ReportType,
        fmt: ReportFormat,
        *,
        portfolio_id: UUID | None = None,
        year: int | None = None,
        base_currency: str = "EUR",
    ) -> tuple[bytes, str, str]:
        """Build and render a report. Returns (bytes, mime_type, filename)."""
        doc = await self._build(user_id, report_type, portfolio_id, year, base_currency)
        content, mime = render(doc, fmt)
        ext = str(fmt).lower() if str(fmt).upper() != "EXCEL" else "xlsx"
        filename = f"{report_type.value.lower()}_{datetime.utcnow():%Y%m%d_%H%M%S}.{ext}"
        return content, mime, filename

    async def _build(
        self,
        user_id: UUID,
        report_type: ReportType,
        portfolio_id: UUID | None,
        year: int | None,
        base_currency: str,
    ) -> ReportDocument:
        if report_type == ReportType.PORTFOLIO:
            return await self._portfolio_doc(user_id, portfolio_id, base_currency)
        if report_type == ReportType.DIVIDEND:
            return await self._dividend_doc(user_id, base_currency)
        if report_type == ReportType.TAX:
            return await self._tax_doc(user_id, year or datetime.utcnow().year)
        # Default placeholder for not-yet-specialised report types.
        return ReportDocument(
            title=f"{report_type.value} report",
            subtitle="DivTrack",
            sections=[Section(heading="Info", text="Dit rapporttype is nog in ontwikkeling.")],
        )

    async def _portfolio_doc(
        self, user_id: UUID, portfolio_id: UUID | None, base_currency: str
    ) -> ReportDocument:
        if self._portfolio is None or portfolio_id is None:
            raise ValueError("Portfolio report requires a portfolio service and id.")
        summary = await self._portfolio.summary(portfolio_id, user_id)
        doc = ReportDocument(title="Portefeuillerapport", subtitle=summary.name)
        doc.add_section(
            Section(
                heading="Overzicht",
                facts={
                    "Totale waarde": f"{summary.total_value:.2f} {summary.base_currency}",
                    "Totaal geïnvesteerd": f"{summary.total_invested:.2f} {summary.base_currency}",
                    "Onrealiseerde W/V": f"{summary.total_unrealized:.2f} {summary.base_currency}",
                    "Gerealiseerde W/V": f"{summary.realized_pnl:.2f} {summary.base_currency}",
                    "Aantal posities": str(len(summary.holdings)),
                },
            )
        )
        rows = [
            [
                h.asset.ticker,
                h.asset.name,
                f"{h.position.quantity:.4f}",
                f"{h.position.avg_cost:.2f}",
                f"{h.price:.2f}" if h.price is not None else "n.b.",
                f"{h.market_value:.2f}" if h.market_value is not None else "n.b.",
                f"{h.unrealized_pnl:.2f}" if h.unrealized_pnl is not None else "n.b.",
            ]
            for h in summary.holdings
        ]
        doc.add_section(
            Section(
                heading="Posities",
                tables=[
                    Table(
                        title="Holdings",
                        headers=["Ticker", "Naam", "Aantal", "Gem.kost", "Koers",
                                 "Marktwaarde", "Onreal. W/V"],
                        rows=rows,
                    )
                ],
            )
        )
        return doc

    async def _dividend_doc(self, user_id: UUID, base_currency: str) -> ReportDocument:
        dash = await DividendService(self._s).dashboard(user_id, base_currency)
        doc = ReportDocument(title="Dividendrapport", subtitle="DivTrack")
        doc.add_section(
            Section(
                heading="Samenvatting",
                facts={
                    "Totaal ontvangen": f"{dash.total_received:.2f} {dash.currency}",
                    "Gem. per maand": f"{dash.avg_monthly:.2f} {dash.currency}",
                    "CAGR": f"{dash.cagr:.2%}" if dash.cagr is not None else "n.b.",
                    "Projectie 12m": f"{dash.projected_next_12m:.2f} {dash.currency}",
                },
                text=dash.note,
            )
        )
        doc.add_section(
            Section(
                heading="Per jaar",
                tables=[
                    Table(
                        title="Jaarlijks dividend",
                        headers=["Jaar", f"Bedrag ({dash.currency})"],
                        rows=[[str(y), f"{v:.2f}"] for y, v in dash.by_year.items()],
                    )
                ],
            )
        )
        return doc

    async def _tax_doc(self, user_id: UUID, year: int) -> ReportDocument:
        summary = await TaxService(self._s).build_year_summary(user_id, year)
        doc = ReportDocument(title="Belastingoverzicht (BE)", subtitle=f"Jaar {year}")
        doc.add_section(
            Section(
                heading="Totalen",
                facts={
                    "Buitenlandse dividenden (bruto)": f"{summary.foreign_dividends_gross:.2f}",
                    "Belgische dividenden (bruto)": f"{summary.belgian_dividends_gross:.2f}",
                    "Buitenlandse bronbelasting": f"{summary.withholding_tax_foreign:.2f}",
                    "Roerende voorheffing (30%)": f"{summary.belgian_rv:.2f}",
                    "Beurstaks (TOB)": f"{summary.tob_total:.2f}",
                    "Transactiekosten": f"{summary.fees_total:.2f}",
                    "Netto dividendinkomen": f"{summary.net_dividend_income:.2f}",
                    "Vrijstelling (verrekenbaar)": f"{summary.reclaimable_exemption:.2f}",
                },
            )
        )
        doc.add_section(
            Section(
                heading="Detail per dividend",
                tables=[
                    Table(
                        title="Dividenden",
                        headers=["Asset", "Land", "Bruto", "Bronbel.", "RV", "Netto"],
                        rows=[
                            [
                                line.asset, line.source_country or "?",
                                f"{line.gross:.2f}", f"{line.foreign_withholding:.2f}",
                                f"{line.belgian_rv:.2f}", f"{line.net:.2f}",
                            ]
                            for line in summary.lines
                        ],
                    )
                ],
            )
        )
        doc.disclaimer = summary.disclaimer
        return doc
