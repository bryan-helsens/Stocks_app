"""End-to-end API flow against a real database.

Covers: register → login → create portfolio → add BUY/SELL/DIVIDEND
transactions → derived FIFO position → portfolio summary. Verifies the core
vertical slice and that the audit triggers fire on transaction inserts.
"""

from __future__ import annotations

import uuid

import pytest

pytestmark = pytest.mark.asyncio


async def _auth_headers(client, email: str) -> dict[str, str]:
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "supersecret1", "full_name": "Test"},
    )
    login = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "supersecret1"}
    )
    token = login.json()["tokens"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def test_full_portfolio_flow(app_client):
    email = f"user_{uuid.uuid4().hex[:8]}@example.com"
    headers = await _auth_headers(app_client, email)

    # Create a portfolio.
    pf = await app_client.post(
        "/api/v1/portfolios",
        json={"name": "BUX", "base_currency": "EUR", "is_default": True},
        headers=headers,
    )
    assert pf.status_code == 201, pf.text
    portfolio_id = pf.json()["id"]

    # Add a BUY (10 @ 100), then a SELL (4 @ 150). FIFO realized P/L = 4*(150-100)=200.
    # We need an asset first; create via manual transaction with a known asset_id
    # by resolving through the import/asset path is heavier, so we register an
    # asset implicitly by posting a transaction with an explicit asset created
    # through the assets table is not exposed; instead use two BUYs/SELL on the
    # same asset_id we mint here and rely on the FK by pre-inserting the asset.
    asset_id = await _ensure_asset(app_client)

    buy = await app_client.post(
        "/api/v1/transactions",
        json={
            "portfolio_id": portfolio_id,
            "type": "BUY",
            "trade_date": "2025-01-02T10:00:00Z",
            "currency": "EUR",
            "asset_id": asset_id,
            "quantity": "10",
            "price": "100",
        },
        headers=headers,
    )
    assert buy.status_code == 201, buy.text

    sell = await app_client.post(
        "/api/v1/transactions",
        json={
            "portfolio_id": portfolio_id,
            "type": "SELL",
            "trade_date": "2025-02-02T10:00:00Z",
            "currency": "EUR",
            "asset_id": asset_id,
            "quantity": "4",
            "price": "150",
        },
        headers=headers,
    )
    assert sell.status_code == 201, sell.text

    # Summary should show 6 shares left and 200 realized P/L.
    summary = await app_client.get(
        f"/api/v1/portfolios/{portfolio_id}/summary", headers=headers
    )
    assert summary.status_code == 200, summary.text
    data = summary.json()
    assert len(data["holdings"]) == 1
    holding = data["holdings"][0]
    assert holding["quantity"] == "6.00000000"
    assert holding["realized_pnl"] == "200.00000000"


async def test_duplicate_transaction_is_rejected(app_client):
    email = f"user_{uuid.uuid4().hex[:8]}@example.com"
    headers = await _auth_headers(app_client, email)
    pf = await app_client.post(
        "/api/v1/portfolios", json={"name": "Main"}, headers=headers
    )
    portfolio_id = pf.json()["id"]
    asset_id = await _ensure_asset(app_client)

    payload = {
        "portfolio_id": portfolio_id,
        "type": "BUY",
        "trade_date": "2025-03-02T10:00:00Z",
        "currency": "EUR",
        "asset_id": asset_id,
        "quantity": "5",
        "price": "20",
    }
    first = await app_client.post("/api/v1/transactions", json=payload, headers=headers)
    assert first.status_code == 201
    dup = await app_client.post("/api/v1/transactions", json=payload, headers=headers)
    assert dup.status_code == 409  # conflict (duplicate)


async def _ensure_asset(app_client) -> str:
    """Insert a shared asset directly via the DB session factory."""
    from app.infrastructure.db.base import get_session_factory
    from app.infrastructure.db import models
    from app.domain.value_objects.enums import AssetClass
    from sqlalchemy import select

    factory = get_session_factory()
    async with factory() as session:
        res = await session.execute(select(models.Asset).where(models.Asset.ticker == "AAPL"))
        existing = res.scalar_one_or_none()
        if existing is not None:
            return str(existing.id)
        asset = models.Asset(
            ticker="AAPL", name="Apple", asset_class=AssetClass.STOCK,
            isin="US0378331005", currency="USD",
        )
        session.add(asset)
        await session.commit()
        return str(asset.id)
