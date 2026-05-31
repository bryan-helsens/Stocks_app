"""Integration test fixtures.

These tests run against a real PostgreSQL database (the app uses Postgres-only
features: enums, JSONB, CITEXT, ARRAY, triggers). They are skipped automatically
when ``TEST_DATABASE_URL`` is not set, so the unit suite stays dependency-free.

Set, e.g.::

    export TEST_DATABASE_URL="postgresql+asyncpg://postgres@127.0.0.1:5433/divtrack_test"
"""

from __future__ import annotations

import os

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

TEST_DB = os.getenv("TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(not TEST_DB, reason="TEST_DATABASE_URL not set")


@pytest_asyncio.fixture
async def app_client():
    """Yield an AsyncClient bound to the FastAPI app with a real DB session."""
    if not TEST_DB:
        pytest.skip("TEST_DATABASE_URL not set")

    # Point settings at the test DB before importing the app.
    os.environ["DATABASE_URL"] = TEST_DB
    from app.core.config import get_settings

    get_settings.cache_clear()  # type: ignore[attr-defined]

    # Force a fresh engine bound to the current event loop to avoid asyncpg
    # "event loop is closed" errors across pytest-asyncio's per-test loops.
    import app.infrastructure.db.base as db_base

    await db_base.dispose_engine()
    db_base._engine = None  # type: ignore[attr-defined]
    db_base._session_factory = None  # type: ignore[attr-defined]

    from app.main import create_app

    app = create_app()
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client
    finally:
        await db_base.dispose_engine()
