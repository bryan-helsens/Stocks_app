"""Asynchronous report generation task (M18 / deliverable 12).

Generates a report off the request path, writes it to file storage and marks the
``reports`` row READY (or FAILED). The synchronous API endpoint covers small
reports; this task is used for large/scheduled exports.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from app.core.logging import get_logger
from app.application.services.portfolio import PortfolioService
from app.application.services.report_service import ReportService
from app.domain.value_objects.enums import ReportStatus
from app.infrastructure.db.base import get_session_factory
from app.infrastructure.db import models
from app.infrastructure.db.repositories import SqlAssetRepository, SqlPositionRepository
from app.infrastructure.db.repositories.users import SqlPortfolioRepository
from app.infrastructure.market_data import get_market_data_provider
from app.infrastructure.storage import get_file_storage
from app.workers.celery_app import celery_app, run_async

logger = get_logger(__name__)


@celery_app.task(name="reports.generate")
def generate_report(report_id: str) -> dict:
    return run_async(_generate_report(UUID(report_id)))


async def _generate_report(report_id: UUID) -> dict:
    factory = get_session_factory()
    async with factory() as session:
        report = await session.get(models.Report, report_id)
        if report is None:
            return {"status": "missing"}
        report.status = ReportStatus.GENERATING
        await session.commit()

        try:
            portfolio_service = PortfolioService(
                SqlPortfolioRepository(session),
                SqlPositionRepository(session),
                SqlAssetRepository(session),
                get_market_data_provider(),
            )
            service = ReportService(session, portfolio_service)
            params = report.params or {}
            content, _mime, filename = await service.generate(
                report.user_id,
                report.type,
                report.format,
                portfolio_id=UUID(params["portfolio_id"]) if params.get("portfolio_id") else None,
                year=params.get("year"),
            )
            storage = get_file_storage()
            path = await storage.save(f"reports/{report_id}/{filename}", content, _mime)
            report.file_path = path
            report.file_size = len(content)
            report.status = ReportStatus.READY
            report.completed_at = datetime.now(UTC)
        except Exception as exc:  # noqa: BLE001
            report.status = ReportStatus.FAILED
            report.error = str(exc)
            logger.exception("report_generation_failed", report_id=str(report_id))
        await session.commit()
        return {"status": report.status.value}
