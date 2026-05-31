"""Integration test for the dividend calendar endpoint (M6)."""

from __future__ import annotations

import uuid

import pytest

pytestmark = pytest.mark.asyncio


async def _headers(client) -> dict[str, str]:
    email = f"cal_{uuid.uuid4().hex[:8]}@example.com"
    await client.post("/api/v1/auth/register", json={"email": email, "password": "supersecret1"})
    login = await client.post("/api/v1/auth/login", json={"email": email, "password": "supersecret1"})
    return {"Authorization": f"Bearer {login.json()['tokens']['access_token']}"}


async def test_calendar_empty_is_valid(app_client):
    headers = await _headers(app_client)
    res = await app_client.get(
        "/api/v1/dividends/calendar",
        params={"start": "2025-01-01", "end": "2025-12-31"},
        headers=headers,
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["events"] == []
    assert "schattingen" in body["note"].lower()
