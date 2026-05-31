"""Broker import endpoints (M4)."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, UploadFile

from app.api.deps import CurrentUser, SessionDep, get_transaction_service
from app.application.services.import_service import ImportService
from app.application.services.transactions import TransactionService
from app.core.config import settings
from app.core.errors import ValidationError
from app.infrastructure.brokers import available_parsers
from app.infrastructure.db.repositories import SqlAssetRepository, SqlTransactionRepository
from app.infrastructure.db.repositories.users import SqlPortfolioRepository
from app.schemas.import_ import ImportCommitResponse, ImportPreviewResponse

router = APIRouter(prefix="/imports", tags=["imports"])


def _import_service(session: SessionDep, tx: TransactionService) -> ImportService:
    return ImportService(
        session,
        SqlAssetRepository(session),
        SqlTransactionRepository(session),
        SqlPortfolioRepository(session),
        tx,
    )


@router.get("/parsers", response_model=list[str])
async def list_parsers(_: CurrentUser) -> list[str]:
    """Return the available broker parser keys (bux, csv_generic, excel, pdf)."""
    return available_parsers()


@router.post("", response_model=ImportPreviewResponse)
async def upload_import(
    user: CurrentUser,
    session: SessionDep,
    tx: Annotated[TransactionService, Depends(get_transaction_service)],
    portfolio_id: Annotated[UUID, Form()],
    file: Annotated[UploadFile, File()],
    parser_key: Annotated[str | None, Form()] = None,
) -> ImportPreviewResponse:
    content = await file.read()
    max_bytes = settings.MAX_UPLOAD_MB * 1024 * 1024
    if len(content) > max_bytes:
        raise ValidationError(f"File exceeds {settings.MAX_UPLOAD_MB} MB limit.")

    svc = _import_service(session, tx)
    preview = await svc.create_batch(
        user.id, portfolio_id, file.filename or "upload", content, parser_key
    )
    return ImportPreviewResponse(
        batch_id=preview.batch_id,
        status=preview.status,
        row_count=preview.row_count,
        new_count=preview.new_count,
        dup_count=preview.dup_count,
        invalid_count=preview.invalid_count,
        column_mapping=preview.column_mapping,
        rows=preview.rows,
    )


@router.post("/{batch_id}/commit", response_model=ImportCommitResponse)
async def commit_import(
    batch_id: UUID,
    user: CurrentUser,
    session: SessionDep,
    tx: Annotated[TransactionService, Depends(get_transaction_service)],
) -> ImportCommitResponse:
    svc = _import_service(session, tx)
    result = await svc.commit_batch(batch_id, user.id)
    return ImportCommitResponse(**result)
