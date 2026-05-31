"""Health & readiness endpoints (for load balancers and orchestration)."""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import text

from app.api.deps import SessionDep
from app.core.config import settings

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    """Liveness probe — always cheap, no external dependencies."""
    return {"status": "ok", "app": settings.APP_NAME, "env": settings.ENV}


@router.get("/ready")
async def ready(session: SessionDep) -> dict:
    """Readiness probe — verifies the database connection."""
    await session.execute(text("SELECT 1"))
    return {"status": "ready"}
