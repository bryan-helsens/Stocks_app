"""Dividend background tasks.

Materialises ``dividends`` rows from committed DIVIDEND transactions so the
dividend dashboard and tax module work off a clean, dedicated table. Idempotent:
a transaction is only materialised once (linked via transaction_id).
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select

from app.core.logging import get_logger
from app.domain.value_objects.enums import TransactionType
from app.infrastructure.db import models
from app.infrastructure.db.base import get_session_factory
from app.workers.celery_app import celery_app, run_async

logger = get_logger(__name__)


@celery_app.task(name="dividends.detect")
def detect() -> dict:
    """Create dividend records for DIVIDEND transactions not yet materialised."""
    return run_async(_detect())


async def _detect() -> dict:
    factory = get_session_factory()
    async with factory() as session:
        # DIVIDEND transactions that have no dividends row yet.
        existing = await session.execute(
            select(models.Dividend.transaction_id).where(
                models.Dividend.transaction_id.is_not(None)
            )
        )
        seen = {row[0] for row in existing.all()}

        res = await session.execute(
            select(models.Transaction).where(
                models.Transaction.type == TransactionType.DIVIDEND,
                models.Transaction.deleted_at.is_(None),
            )
        )
        created = 0
        for tx in res.scalars().all():
            if tx.id in seen or tx.asset_id is None:
                continue
            fx = tx.fx_rate or Decimal(1)
            gross_base = (tx.gross_amount or Decimal(0)) * fx
            tax_base = (tx.tax or Decimal(0)) * fx
            session.add(
                models.Dividend(
                    user_id=tx.user_id,
                    portfolio_id=tx.portfolio_id,
                    asset_id=tx.asset_id,
                    transaction_id=tx.id,
                    pay_date=tx.trade_date.date(),
                    gross_amount=gross_base,
                    withholding_tax=tax_base,
                    net_amount=gross_base - tax_base,
                    currency=tx.currency,
                )
            )
            created += 1
        await session.commit()
        logger.info("dividends_detected", created=created)
        return {"created": created}
