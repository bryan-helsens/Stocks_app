"""Import pipeline application service (M4).

Implements the generic pipeline described in the architecture:

    parse → normalize → classify → enrich (asset/FX) → deduplicate → stage → commit

A parser only extracts canonical drafts; everything else (dedup, staging,
commit) is broker-agnostic and lives here. Commit is idempotent (BR12): rows
already committed or detected as duplicates are skipped.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from app.core.errors import NotFoundError, ValidationError
from app.domain.entities import Asset, Transaction
from app.domain.ports.broker_parser import TransactionDraft
from app.domain.value_objects.enums import (
    AssetClass,
    ImportRowStatus,
    ImportStatus,
    TransactionSource,
    TransactionType,
)
from app.infrastructure.brokers import select_parser
from app.infrastructure.db import models
from app.infrastructure.db.repositories import SqlAssetRepository, SqlTransactionRepository
from app.infrastructure.db.repositories.users import SqlPortfolioRepository
from app.application.services.transactions import TransactionService


@dataclass(slots=True)
class ImportPreview:
    batch_id: UUID
    status: str
    row_count: int
    new_count: int
    dup_count: int
    invalid_count: int
    column_mapping: dict
    rows: list[dict]


class ImportService:
    def __init__(
        self,
        session,
        assets: SqlAssetRepository,
        transactions: SqlTransactionRepository,
        portfolios: SqlPortfolioRepository,
        tx_service: TransactionService,
    ) -> None:
        self._s = session
        self._assets = assets
        self._tx = transactions
        self._portfolios = portfolios
        self._tx_service = tx_service

    # ----- create / preview ---------------------------------------------
    async def create_batch(
        self,
        user_id: UUID,
        portfolio_id: UUID,
        filename: str,
        content: bytes,
        parser_key: str | None = None,
        column_mapping: dict | None = None,
    ) -> ImportPreview:
        """Parse an uploaded file into a staged, previewable import batch."""
        portfolio = await self._portfolios.get(portfolio_id, user_id)
        if portfolio is None:
            raise NotFoundError("Portfolio not found.")

        parser = select_parser(filename, content[:4096], parser_key)
        if parser is None:
            raise ValidationError("No parser could handle this file.")

        batch = models.ImportBatch(
            user_id=user_id,
            portfolio_id=portfolio_id,
            filename=filename,
            file_type=filename.rsplit(".", 1)[-1].lower() if "." in filename else None,
            status=ImportStatus.PARSING,
        )
        self._s.add(batch)
        await self._s.flush()

        try:
            result = parser.parse(content, column_mapping=column_mapping)
        except Exception as exc:  # noqa: BLE001
            batch.status = ImportStatus.FAILED
            batch.error = str(exc)
            await self._s.flush()
            raise ValidationError(f"Failed to parse file: {exc}") from exc

        batch.detected_columns = {"columns": result.detected_columns}
        batch.column_mapping = result.column_mapping
        batch.row_count = len(result.drafts)

        new_count = dup_count = invalid_count = 0
        rows_out: list[dict] = []
        seen_hashes: set[str] = set()

        for draft in result.drafts:
            normalized, dedup, status, error = await self._normalize_and_check(
                user_id, portfolio_id, draft, seen_hashes
            )
            if status == ImportRowStatus.NEW:
                new_count += 1
                seen_hashes.add(dedup)
            elif status == ImportRowStatus.DUPLICATE:
                dup_count += 1
            else:
                invalid_count += 1

            row = models.ImportRow(
                batch_id=batch.id,
                raw=draft.raw,
                normalized=normalized,
                suggested_type=draft.type,
                status=status,
                dedup_hash=dedup,
                error=error,
            )
            self._s.add(row)
            rows_out.append(
                {
                    "type": draft.type.value if draft.type else None,
                    "trade_date": draft.trade_date.isoformat(),
                    "ticker": draft.ticker,
                    "isin": draft.isin,
                    "quantity": str(draft.quantity) if draft.quantity is not None else None,
                    "price": str(draft.price) if draft.price is not None else None,
                    "gross_amount": str(draft.gross_amount) if draft.gross_amount is not None else None,
                    "fee": str(draft.fee),
                    "tax": str(draft.tax),
                    "currency": draft.currency,
                    "status": status.value,
                    "error": error,
                }
            )

        batch.dup_count = dup_count
        batch.status = ImportStatus.PREVIEWED
        await self._s.flush()

        return ImportPreview(
            batch_id=batch.id,
            status=batch.status.value,
            row_count=batch.row_count,
            new_count=new_count,
            dup_count=dup_count,
            invalid_count=invalid_count,
            column_mapping=result.column_mapping,
            rows=rows_out,
        )

    # ----- commit --------------------------------------------------------
    async def commit_batch(self, batch_id: UUID, user_id: UUID) -> dict:
        """Convert NEW rows into transactions (idempotent — BR12)."""
        batch = await self._s.get(models.ImportBatch, batch_id)
        if batch is None or batch.user_id != user_id:
            raise NotFoundError("Import batch not found.")
        if batch.status == ImportStatus.COMMITTED:
            return {"committed": 0, "message": "Batch already committed."}

        from sqlalchemy import select

        res = await self._s.execute(
            select(models.ImportRow).where(
                models.ImportRow.batch_id == batch_id,
                models.ImportRow.status == ImportRowStatus.NEW,
            )
        )
        rows = list(res.scalars().all())

        committed = 0
        for row in rows:
            norm = row.normalized or {}
            asset_id = await self._resolve_asset_id(norm)
            tx = self._draft_to_transaction(user_id, batch.portfolio_id, norm, asset_id, row.suggested_type)
            try:
                saved = await self._tx_service.add_transaction(tx)
            except Exception:  # noqa: BLE001 - skip rows that fail validation
                row.status = ImportRowStatus.INVALID
                row.error = "Failed to commit (validation)."
                continue
            row.transaction_id = saved.id
            row.status = ImportRowStatus.COMMITTED
            committed += 1

        batch.status = ImportStatus.COMMITTED
        batch.committed_at = datetime.now(UTC)
        await self._s.flush()
        return {"committed": committed, "message": f"Committed {committed} transactions."}

    # ----- helpers -------------------------------------------------------
    async def _normalize_and_check(
        self,
        user_id: UUID,
        portfolio_id: UUID,
        draft: TransactionDraft,
        seen_hashes: set[str],
    ) -> tuple[dict, str, ImportRowStatus, str | None]:
        normalized = {
            "trade_date": draft.trade_date.isoformat(),
            "type": draft.type.value if draft.type else None,
            "ticker": draft.ticker,
            "isin": draft.isin,
            "name": draft.name,
            "quantity": str(draft.quantity) if draft.quantity is not None else None,
            "price": str(draft.price) if draft.price is not None else None,
            "gross_amount": str(draft.gross_amount) if draft.gross_amount is not None else None,
            "fee": str(draft.fee),
            "tax": str(draft.tax),
            "currency": draft.currency,
            "fx_rate": str(draft.fx_rate) if draft.fx_rate is not None else None,
            "external_id": draft.external_id,
        }

        if draft.type is None:
            return normalized, "", ImportRowStatus.INVALID, "Could not determine transaction type."

        dedup = _draft_dedup_hash(user_id, portfolio_id, draft)
        if dedup in seen_hashes or await self._tx.exists_by_dedup(user_id, dedup):
            return normalized, dedup, ImportRowStatus.DUPLICATE, None
        return normalized, dedup, ImportRowStatus.NEW, None

    async def _resolve_asset_id(self, norm: dict) -> UUID | None:
        isin = norm.get("isin")
        ticker = norm.get("ticker")
        if isin:
            asset = await self._assets.get_by_isin(isin)
            if asset and asset.id:
                return asset.id
        if ticker:
            asset = await self._assets.get_by_ticker(ticker)
            if asset and asset.id:
                return asset.id
        # Create a minimal asset record so the transaction can reference it.
        if ticker or isin:
            created = await self._assets.upsert(
                Asset(
                    id=None,
                    ticker=ticker or (isin or "UNKNOWN"),
                    name=norm.get("name") or ticker or isin or "Unknown",
                    asset_class=AssetClass.STOCK,
                    isin=isin,
                )
            )
            return created.id
        return None

    def _draft_to_transaction(
        self,
        user_id: UUID,
        portfolio_id: UUID,
        norm: dict,
        asset_id: UUID | None,
        suggested_type: TransactionType | None,
    ) -> Transaction:
        from decimal import Decimal

        def dec(key: str) -> Decimal | None:
            v = norm.get(key)
            return Decimal(v) if v not in (None, "") else None

        tx_type = TransactionType(norm["type"]) if norm.get("type") else suggested_type
        return Transaction(
            id=None,
            user_id=user_id,
            portfolio_id=portfolio_id,
            type=tx_type or TransactionType.BUY,
            trade_date=datetime.fromisoformat(norm["trade_date"]),
            currency=norm.get("currency") or "EUR",
            asset_id=asset_id,
            quantity=dec("quantity"),
            price=dec("price"),
            gross_amount=dec("gross_amount") or Decimal(0),
            fee=dec("fee") or Decimal(0),
            tax=dec("tax") or Decimal(0),
            fx_rate=dec("fx_rate") or Decimal(1),
            source=TransactionSource.IMPORT_BUX,
            external_id=norm.get("external_id"),
        )


def _draft_dedup_hash(user_id: UUID, portfolio_id: UUID, draft: TransactionDraft) -> str:
    """Stable dedup hash for an import draft (BR7)."""
    key = "|".join(
        str(x)
        for x in (
            user_id,
            portfolio_id,
            draft.isin or draft.ticker or "",
            draft.type.value if draft.type else "",
            draft.trade_date.isoformat(),
            draft.quantity,
            draft.price,
            draft.gross_amount,
            draft.external_id or "",
        )
    )
    return hashlib.sha256(key.encode()).hexdigest()
