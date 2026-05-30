#!/usr/bin/env sh
# Entrypoint for the API container: wait for Postgres, run migrations, then start.
set -e

echo "[entrypoint] waiting for database..."
python - <<'PY'
import os, time, socket, urllib.parse as up
url = os.environ.get("DATABASE_URL", "")
# Extract host/port from postgresql+asyncpg://user:pass@host:port/db
parsed = up.urlparse(url.replace("+asyncpg", ""))
host, port = parsed.hostname or "postgres", parsed.port or 5432
for _ in range(60):
    try:
        with socket.create_connection((host, port), timeout=2):
            print(f"[entrypoint] database reachable at {host}:{port}")
            break
    except OSError:
        time.sleep(1)
else:
    raise SystemExit("[entrypoint] database not reachable in time")
PY

echo "[entrypoint] applying migrations..."
alembic upgrade head

echo "[entrypoint] starting: $*"
exec "$@"
