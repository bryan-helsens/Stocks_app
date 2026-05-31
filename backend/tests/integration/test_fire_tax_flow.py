"""Integration tests for FIRE planning and the Belgian tax overview endpoints."""

from __future__ import annotations

import uuid

import pytest

pytestmark = pytest.mark.asyncio


async def _auth_headers(client) -> dict[str, str]:
    email = f"ft_{uuid.uuid4().hex[:8]}@example.com"
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "supersecret1"},
    )
    login = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "supersecret1"}
    )
    return {"Authorization": f"Bearer {login.json()['tokens']['access_token']}"}


async def test_fire_plan(app_client):
    headers = await _auth_headers(app_client)
    res = await app_client.post(
        "/api/v1/fire/plan",
        json={
            "annual_expenses": "30000",
            "swr": "0.04",
            "current_value": "100000",
            "monthly_contribution": "1000",
            "expected_return": "0.07",
        },
        headers=headers,
    )
    assert res.status_code == 200, res.text
    body = res.json()
    # 30000 / 0.04 = 750000 full number.
    assert body["targets"]["full_number"].startswith("750000")
    assert "disclaimer" in body
    assert body["projection"]  # year-by-year trace present


async def test_fire_scenario_crash_reduces_value(app_client):
    headers = await _auth_headers(app_client)
    base = await app_client.post(
        "/api/v1/fire/scenario",
        json={"name": "base", "initial_value": "100000", "monthly_contribution": "500",
              "annual_return": "0.07", "years": 10},
        headers=headers,
    )
    crash = await app_client.post(
        "/api/v1/fire/scenario",
        json={"name": "crash", "initial_value": "100000", "monthly_contribution": "500",
              "annual_return": "0.07", "years": 10, "crash_pct": "0.30", "crash_year": 5},
        headers=headers,
    )
    assert base.status_code == 200 and crash.status_code == 200
    base_final = float(base.json()["final_value"])
    crash_final = float(crash.json()["final_value"])
    assert crash_final < base_final


async def test_tax_report_empty_year_is_valid(app_client):
    headers = await _auth_headers(app_client)
    res = await app_client.get("/api/v1/tax/be/report", params={"year": 2024}, headers=headers)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["year"] == 2024
    assert "informatief" in body["disclaimer"].lower()
    # No dividends => zero totals, but a valid structured response.
    assert float(body["net_dividend_income"]) == 0.0
    assert float(body["tob_total"]) == 0.0
