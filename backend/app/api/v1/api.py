"""Aggregate router for API v1.

Additional routers (dividends, analysis, valuation, fire, scenarios, ai, tax,
watchlists, alerts, notifications, reports, market) are mounted here as they are
implemented.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.routers import (
    ai,
    auth,
    dividends,
    fire,
    health,
    imports,
    portfolios,
    reports,
    tax,
    transactions,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(portfolios.router)
api_router.include_router(transactions.router)
api_router.include_router(imports.router)
api_router.include_router(ai.router)
api_router.include_router(dividends.router)
api_router.include_router(fire.router)
api_router.include_router(tax.router)
api_router.include_router(reports.router)
