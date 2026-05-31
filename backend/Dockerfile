# syntax=docker/dockerfile:1
# ---------------------------------------------------------------------------
# DivTrack backend image (FastAPI + Celery).
# Multi-stage: a builder installs deps into a venv, the runtime stage is slim.
# WeasyPrint needs native libs (pango/cairo/gdk-pixbuf) for PDF generation.
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS builder

ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app

# Build deps for asyncpg / cryptography wheels.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy the whole backend (the package `app` must exist to build the project).
COPY backend/ /app/
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip \
    && /opt/venv/bin/pip install .

# ---------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH"

# Runtime native libraries for WeasyPrint + libpq for asyncpg.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 libpango-1.0-0 libpangocairo-1.0-0 libcairo2 libgdk-pixbuf-2.0-0 \
    libffi8 fonts-dejavu-core curl \
    && rm -rf /var/lib/apt/lists/*

# Non-root runtime user.
RUN useradd --create-home --uid 1000 appuser
WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY backend/ /app/
# The initial migration reads the canonical DDL from /app/db/schema.sql.
COPY db/ /app/db/

# Normalise the entrypoint's line endings (defensive: a CRLF checkout on
# Windows/WSL would otherwise break the shebang -> "env: 'sh\r'") and make it
# executable.
RUN sed -i 's/\r$//' /app/entrypoint.sh && chmod +x /app/entrypoint.sh \
    && mkdir -p /data/divtrack && chown -R appuser:appuser /app /data/divtrack
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8000/api/v1/health || exit 1

# Default: run the API. Compose overrides the command for worker/beat services.
CMD ["gunicorn", "app.main:app", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--workers", "4", "--bind", "0.0.0.0:8000", \
     "--access-logfile", "-", "--error-logfile", "-"]
