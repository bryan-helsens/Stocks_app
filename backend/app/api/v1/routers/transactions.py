"""Transaction endpoints (M3)."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.api.deps import CurrentUser, get_transaction_service
from app.application.services.transactions import TransactionService
from app.domain.entities import Transaction
from app.domain.value_objects.enums import TransactionSource
from app.schemas.common import Message
from app.schemas.transaction import TransactionCreate, TransactionResponse

router = APIRouter(prefix="/transactions", tags=["transactions"])

TxDep = Annotated[TransactionService, Depends(get_transaction_service)]


@router.post("", response_model=TransactionResponse, status_code=status.HTTP_201_CREATED)
async def create_transaction(
    body: TransactionCreate, user: CurrentUser, svc: TxDep
) -> TransactionResponse:
    tx = Transaction(
        id=None,
        user_id=user.id,
        portfolio_id=body.portfolio_id,
        type=body.type,
        trade_date=body.trade_date,
        currency=body.currency,
        asset_id=body.asset_id,
        quantity=body.quantity,
        price=body.price,
        gross_amount=body.gross_amount,
        fee=body.fee,
        tax=body.tax,
        fx_rate=body.fx_rate,
        split_ratio=body.split_ratio,
        source=TransactionSource.MANUAL,
        external_id=body.external_id,
        note=body.note,
    )
    saved = await svc.add_transaction(tx, allow_duplicate=body.allow_duplicate)
    return TransactionResponse(
        id=saved.id,
        portfolio_id=saved.portfolio_id,
        type=saved.type,
        trade_date=saved.trade_date,
        currency=saved.currency,
        asset_id=saved.asset_id,
        quantity=saved.quantity,
        price=saved.price,
        gross_amount=saved.gross_amount,
        fee=saved.fee,
        tax=saved.tax,
        net_amount=saved.net_amount,
        note=saved.note,
    )


@router.delete("/{tx_id}", response_model=Message)
async def delete_transaction(tx_id: UUID, user: CurrentUser, svc: TxDep) -> Message:
    await svc.delete_transaction(tx_id, user.id)
    return Message(message="Transaction deleted and position recomputed.")
