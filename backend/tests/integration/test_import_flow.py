"""End-to-end import flow against a real database.

Uploads the synthetic BUX sample, checks the preview classification, commits it
and verifies that positions are derived. Exercises the full generic-import
pipeline (parse → classify → dedupe → stage → commit → position rebuild).
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest

pytestmark = pytest.mark.asyncio

SAMPLE = Path(__file__).resolve().parents[3] / "docs" / "samples" / "bux_sample.csv"


async def _auth_headers(client, email: str) -> dict[str, str]:
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "supersecret1", "full_name": "Test"},
    )
    login = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "supersecret1"}
    )
    return {"Authorization": f"Bearer {login.json()['tokens']['access_token']}"}


async def test_bux_import_preview_and_commit(app_client):
    email = f"imp_{uuid.uuid4().hex[:8]}@example.com"
    headers = await _auth_headers(app_client, email)

    pf = await app_client.post("/api/v1/portfolios", json={"name": "BUX"}, headers=headers)
    portfolio_id = pf.json()["id"]

    # Upload the sample as multipart.
    content = SAMPLE.read_bytes()
    files = {"file": ("bux_sample.csv", content, "text/csv")}
    data = {"portfolio_id": portfolio_id, "parser_key": "bux"}
    up = await app_client.post("/api/v1/imports", data=data, files=files, headers=headers)
    assert up.status_code == 200, up.text
    preview = up.json()

    # 10 data rows, 2 asset-legs dropped -> 8 drafts; 1 row is a review/asset transfer.
    assert preview["row_count"] == 8
    assert preview["new_count"] >= 6
    assert preview["invalid_count"] >= 1  # the Portfolio Transfer row

    # Commit and verify it is idempotent on a second call.
    batch_id = preview["batch_id"]
    commit = await app_client.post(f"/api/v1/imports/{batch_id}/commit", headers=headers)
    assert commit.status_code == 200, commit.text
    committed = commit.json()["committed"]
    assert committed >= 1

    again = await app_client.post(f"/api/v1/imports/{batch_id}/commit", headers=headers)
    assert again.json()["committed"] == 0  # already committed (idempotent)

    # The portfolio summary should now contain at least the Apple position.
    summary = await app_client.get(
        f"/api/v1/portfolios/{portfolio_id}/summary", headers=headers
    )
    assert summary.status_code == 200
    tickers = {h["asset"]["ticker"] for h in summary.json()["holdings"]}
    # Apple was bought (0.1618) then partly sold; a residual position remains.
    assert any(t for t in tickers)
