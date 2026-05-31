# 15 — Deployment Handleiding

> Installatie & uitrol van DivTrack op **Linux**, **Windows** (ontwikkeling) en een **VPS** (productie). De volledige stack draait via Docker Compose: `postgres`, `redis`, `minio`, `api`, `worker`, `beat` (+ optioneel `ollama`, `flower`).

> ⚠️ Wijzig vóór productie minstens `SECRET_KEY`, `POSTGRES_PASSWORD` en de S3/MinIO-credentials in `.env`.

---

## 0. Vereisten

| Component | Versie |
|-----------|--------|
| Docker Engine | ≥ 24 |
| Docker Compose plugin | ≥ 2.20 |
| (lokaal backend dev) Python | 3.12 |
| (frontend) Flutter SDK | ≥ 3.27 (Dart ≥ 3.6) |
| Vrije poorten | 8000 (API), 5432, 6379, 9000/9001 (MinIO) |

---

## 1. Linux — productie/zelf-host (aanbevolen)

```bash
# 1. Code ophalen
git clone https://github.com/bryan-helsens/Stocks_app.git
cd Stocks_app

# 2. Configuratie
cp .env.example .env
# Genereer een sterke SECRET_KEY:
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
# Plak die in .env (SECRET_KEY=...), zet sterke POSTGRES_PASSWORD en S3-keys.
nano .env

# 3. Bouwen & starten (migraties draaien automatisch via entrypoint)
make up           # of: docker compose up -d --build

# 4. Referentiedata seeden (systeembrokers + demo-assets)
make seed         # of: docker compose exec api python -m scripts.seed_db

# 5. Status & logs
make ps
make logs
```

- API: `http://<server-ip>:8000` · Swagger: `http://<server-ip>:8000/docs`
- Health: `curl http://localhost:8000/api/v1/health`

**Optionele services**
```bash
# Lokale AI (Ollama) — privacy, geen externe API
docker compose --profile ai-local up -d
docker compose exec ollama ollama pull llama3.1

# Celery-monitoring (Flower op :5555)
docker compose --profile extras up -d flower
```

**Updaten naar een nieuwe versie**
```bash
git pull
docker compose up -d --build   # entrypoint draait `alembic upgrade head`
```

---

## 2. Windows — ontwikkeling

1. Installeer **Docker Desktop** (met WSL2-backend) en **Git for Windows**.
2. In PowerShell:
   ```powershell
   git clone https://github.com/bryan-helsens/Stocks_app.git
   cd Stocks_app
   copy .env.example .env
   # Bewerk .env (SECRET_KEY etc.) in een editor
   docker compose up -d --build
   docker compose exec api python -m scripts.seed_db
   ```
3. Open `http://localhost:8000/docs`.

> `make` is niet standaard op Windows; gebruik de `docker compose …`-commando's rechtstreeks, of installeer `make` via Chocolatey (`choco install make`).

**Backend lokaal zonder Docker (optioneel)**
```powershell
cd backend
python -m venv .venv ; .venv\Scripts\activate
pip install -e ".[dev]"
# Zet DATABASE_URL/REDIS_URL naar je lokale of Docker-instanties
alembic upgrade head
uvicorn app.main:app --reload
```

---

## 3. VPS — productie met TLS (Ubuntu 22.04+)

```bash
# 1. Docker installeren
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER && newgrp docker

# 2. Repo + config
git clone https://github.com/bryan-helsens/Stocks_app.git && cd Stocks_app
cp .env.example .env && nano .env   # SECRET_KEY, wachtwoorden, ENV=production

# 3. Start
docker compose up -d --build
docker compose exec api python -m scripts.seed_db
```

### 3.1 Reverse proxy + HTTPS (Caddy — eenvoudigst)

`/etc/caddy/Caddyfile`:
```
api.jouwdomein.be {
    reverse_proxy localhost:8000
}
```
```bash
sudo apt install -y caddy
sudo systemctl reload caddy   # Caddy regelt Let's Encrypt-certificaten automatisch
```
Zet in `.env`: `CORS_ORIGINS=https://app.jouwdomein.be` en `ENV=production`.

> Alternatief (Nginx + certbot): proxy `proxy_pass http://127.0.0.1:8000;` en `certbot --nginx`.

### 3.2 Firewall
```bash
sudo ufw allow OpenSSH
sudo ufw allow 80,443/tcp
sudo ufw enable
# Stel Postgres/Redis/MinIO NIET bloot aan het internet (alleen interne Docker-netwerk).
```
Voor productie: verwijder de host-`ports`-mappings van `postgres`, `redis` en `minio` uit `docker-compose.yml` zodat ze enkel intern bereikbaar zijn.

---

## 4. Back-ups

**Dagelijkse Postgres-dump (cron)**
```bash
# /etc/cron.daily/divtrack-backup
#!/bin/sh
cd /opt/Stocks_app
docker compose exec -T postgres pg_dump -U divtrack divtrack \
  | gzip > /var/backups/divtrack-$(date +%F).sql.gz
find /var/backups -name 'divtrack-*.sql.gz' -mtime +30 -delete
```
```bash
sudo chmod +x /etc/cron.daily/divtrack-backup
```

**Herstellen**
```bash
gunzip -c /var/backups/divtrack-2026-05-31.sql.gz \
  | docker compose exec -T postgres psql -U divtrack -d divtrack
```

Back-up ook de volumes `minio_data` (rapporten/uploads) en `report_data`.

---

## 5. CI/CD

`.github/workflows/ci.yml` draait bij elke push:
- **backend**: ruff (lint) → mypy (types) → `alembic upgrade` → `pytest` (met Postgres+Redis services)
- **frontend**: `flutter analyze` + `flutter test`
- **docker**: bouwt de backend-image

Voor automatische uitrol: voeg een `deploy`-job toe die de image naar je registry pusht en op de VPS `docker compose pull && up -d` draait (via SSH-action of een webhook).

---

## 6. Observability & beheer

| Wat | Hoe |
|-----|-----|
| Logs | `docker compose logs -f api worker beat` (JSON, structlog) |
| Health/Ready | `/api/v1/health`, `/api/v1/ready` |
| Celery-monitoring | Flower-profiel op `:5555` |
| Errors | Zet `SENTRY_DSN` in `.env` |
| DB-shell | `make psql` |
| Migratie | `make migrate` (of automatisch bij `up`) |

---

## 7. Frontend uitrollen (Flutter)

```bash
cd frontend
flutter pub get

# Web-build (host de map build/web achter je proxy)
flutter build web --dart-define=API_BASE_URL=https://api.jouwdomein.be

# Desktop
flutter build linux      # of: windows / macos

# Mobiel
flutter build apk        # Android
flutter build ipa        # iOS (vereist macOS + Xcode)
```
De `API_BASE_URL` dart-define wijst de app naar je productie-API.

---

## 8. Productie-checklist

- [ ] `SECRET_KEY` sterk & uniek; `ENV=production`; `DEBUG=false`
- [ ] Sterke `POSTGRES_PASSWORD` en S3/MinIO-credentials
- [ ] `CORS_ORIGINS` beperkt tot je frontend-domein
- [ ] Postgres/Redis/MinIO niet publiek (host-poorten verwijderd)
- [ ] HTTPS via reverse proxy actief
- [ ] Dagelijkse back-ups + getest herstel
- [ ] `SENTRY_DSN` ingesteld (optioneel)
- [ ] Firewall (ufw) actief

---

*Einde deliverable 15 — Deployment. Volgende: deliverable 16 (gebruikershandleiding).*
