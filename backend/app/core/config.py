"""Application configuration (12-factor).

All runtime configuration is read from environment variables (or a local
``.env`` file during development) and validated by Pydantic. Secrets are never
hard-coded. Import the singleton :func:`get_settings` everywhere instead of
reading ``os.environ`` directly.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, PostgresDsn, RedisDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Strongly-typed application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ----- General -------------------------------------------------------
    APP_NAME: str = "DivTrack"
    ENV: Literal["development", "staging", "production", "test"] = "development"
    DEBUG: bool = False
    API_V1_PREFIX: str = "/api/v1"
    # Comma-separated list of allowed CORS origins.
    CORS_ORIGINS: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])

    # ----- Security ------------------------------------------------------
    # Used to sign JWTs and as the root for app-level encryption. MUST be set
    # to a strong random value in production (>= 32 chars).
    SECRET_KEY: str = "change-me-in-production-please-32chars-min"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    # Lockout after this many failed logins within the window.
    LOGIN_MAX_ATTEMPTS: int = 5
    LOGIN_LOCKOUT_SECONDS: int = 900
    # Default per-user/per-IP request budget (requests per minute).
    RATE_LIMIT_PER_MINUTE: int = 120
    AUTH_RATE_LIMIT_PER_MINUTE: int = 10

    # ----- Database ------------------------------------------------------
    DATABASE_URL: PostgresDsn = Field(
        default="postgresql+asyncpg://divtrack:divtrack@localhost:5432/divtrack",
    )
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_ECHO: bool = False

    # ----- Redis / Celery ------------------------------------------------
    REDIS_URL: RedisDsn = Field(default="redis://localhost:6379/0")
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"

    # ----- Money / locale ------------------------------------------------
    BASE_CURRENCY: str = "EUR"
    DEFAULT_LOCALE: str = "nl-BE"

    # ----- Market data ---------------------------------------------------
    # Which adapter to use: "yfinance" | "fmp" | "alphavantage" | "eod".
    MARKET_DATA_PROVIDER: str = "yfinance"
    FMP_API_KEY: str | None = None
    ALPHAVANTAGE_API_KEY: str | None = None
    EOD_API_KEY: str | None = None
    QUOTE_CACHE_TTL_SECONDS: int = 300

    # ----- AI providers --------------------------------------------------
    # Default provider when the user has no preference: "ollama" keeps data local.
    AI_PROVIDER: Literal["openai", "claude", "ollama"] = "ollama"
    OPENAI_API_KEY: str | None = None
    OPENAI_MODEL: str = "gpt-4o-mini"
    ANTHROPIC_API_KEY: str | None = None
    CLAUDE_MODEL: str = "claude-sonnet-4-6"
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "llama3.1"
    AI_REQUEST_TIMEOUT_SECONDS: int = 60

    # ----- Notifications -------------------------------------------------
    SMTP_HOST: str | None = None
    SMTP_PORT: int = 587
    SMTP_USER: str | None = None
    SMTP_PASSWORD: str | None = None
    SMTP_FROM: str = "DivTrack <noreply@divtrack.local>"
    TELEGRAM_BOT_TOKEN: str | None = None

    # ----- Storage -------------------------------------------------------
    # "local" | "s3" (MinIO-compatible).
    STORAGE_BACKEND: Literal["local", "s3"] = "local"
    STORAGE_LOCAL_PATH: str = "/data/divtrack"
    S3_ENDPOINT_URL: str | None = None
    S3_BUCKET: str = "divtrack"
    S3_ACCESS_KEY: str | None = None
    S3_SECRET_KEY: str | None = None
    MAX_UPLOAD_MB: int = 25

    # ----- Observability -------------------------------------------------
    LOG_LEVEL: str = "INFO"
    LOG_JSON: bool = True
    SENTRY_DSN: str | None = None

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def _split_cors(cls, v: str | list[str]) -> list[str]:
        """Allow CORS origins to be provided as a comma-separated string."""
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    @property
    def is_production(self) -> bool:
        return self.ENV == "production"

    @property
    def sync_database_url(self) -> str:
        """Alembic uses a synchronous driver; swap asyncpg for psycopg."""
        return str(self.DATABASE_URL).replace("+asyncpg", "+psycopg")


@lru_cache
def get_settings() -> Settings:
    """Return the cached settings singleton."""
    return Settings()


settings = get_settings()
