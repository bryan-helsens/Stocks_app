"""FastAPI application factory.

Wires configuration, structured logging, CORS, the uniform error handlers, the
v1 API router and lifespan (engine disposal on shutdown). Run locally with::

    uvicorn app.main:app --reload
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.api import api_router
from app.core.config import settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging, get_logger

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None, None]:
    configure_logging()
    logger.info("startup", app=settings.APP_NAME, env=settings.ENV)
    if settings.SENTRY_DSN:  # pragma: no cover - optional
        import sentry_sdk

        sentry_sdk.init(dsn=settings.SENTRY_DSN, environment=settings.ENV)
    yield
    from app.infrastructure.db.base import dispose_engine

    await dispose_engine()
    logger.info("shutdown")


def create_app() -> FastAPI:
    app = FastAPI(
        title=f"{settings.APP_NAME} API",
        version="0.1.0",
        description=(
            "Portfolio, dividend, FIRE and Belgian tax management API. "
            "Educational/informational only — no financial, tax or legal advice."
        ),
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url=f"{settings.API_V1_PREFIX}/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_exception_handlers(app)
    app.include_router(api_router, prefix=settings.API_V1_PREFIX)

    @app.get("/", tags=["root"])
    async def root() -> dict:
        return {
            "app": settings.APP_NAME,
            "docs": "/docs",
            "api": settings.API_V1_PREFIX,
            "disclaimer": (
                "Informatief en educatief — geen financieel, fiscaal of "
                "juridisch advies."
            ),
        }

    return app


app = create_app()
