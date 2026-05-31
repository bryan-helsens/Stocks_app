# DivTrack

**Portfolio · dividend · FIRE · AI-analyse · Belgische fiscaliteit** — één centrale
applicatie voor portefeuillebeheer, dividendopvolging, investeringsanalyse,
financiële planning en rapportering (desktop + mobiel).

> ⚠️ **Disclaimer:** DivTrack levert **geen** financieel, fiscaal of juridisch advies.
> Alle scores, analyses, AI-uitspraken, FIRE-projecties en fiscale overzichten zijn
> **uitsluitend informatief en educatief**. Voorspellingen zijn geen garanties.

---

## Wat het doet

- 📊 **Portfolio** — multi-asset (aandelen, ETF's, REIT's, obligaties, cash, crypto), FIFO-posities, live waardering
- 🔁 **Broker-import** — generiek framework met **BUX** (echte export-formaat), CSV, Excel, PDF; auto-kolomherkenning + duplicaatdetectie
- 💶 **Dividenden** — yield, yield-on-cost, CAGR, kalender, maandinkomen, projectie
- 🧮 **FIRE** — Lean/Coast/Barista/Fat, FI-datum, scenario's + Monte-Carlo
- 🤖 **AI-analist** — OpenAI / Claude / **Ollama (lokaal)**; domein rekent, LLM interpreteert
- 📈 **Analyse & waardering** — ratio's, score 0–100, DCF/DDM/multiples
- 🧾 **Belgische fiscaliteit** — RV, buitenlandse bronbelasting, **TOB**, jaaroverzicht
- 📄 **Rapporten** — PDF / Excel / CSV / JSON

## Tech stack

| Laag | Technologie |
|------|-------------|
| Frontend | **Flutter** (iOS/Android/Windows/macOS/Linux/Web) |
| Backend | **FastAPI** (async), Clean/Hexagonal Architecture |
| Database | **PostgreSQL 16** (+ optioneel TimescaleDB) |
| Cache/taken | **Redis** + **Celery** (+ Beat) |
| AI | OpenAI · Anthropic Claude · Ollama (lokaal) |
| Deployment | **Docker Compose**, GitHub Actions CI |

## Snelstart

```bash
git clone https://github.com/bryan-helsens/Stocks_app.git
cd Stocks_app
cp .env.example .env          # zet een sterke SECRET_KEY!
make up                       # bouwt + start de hele stack (migraties automatisch)
make seed                     # systeembrokers + demo-assets
```
- API + Swagger: <http://localhost:8000/docs>
- Frontend: `cd frontend && flutter run --dart-define=API_BASE_URL=http://localhost:8000`

## Documentatie (`docs/`)

| # | Document |
|---|----------|
| 01 | [Systeemarchitectuur](docs/01-architecture.md) |
| 02 | [Functionele analyse](docs/02-functional-analysis.md) |
| 03 | [Database-ontwerp](docs/03-database-design.md) · [`db/schema.sql`](db/schema.sql) |
| 04 | [UI wireframes](docs/04-wireframes.md) |
| 05 | [UX flows](docs/05-ux-flows.md) |
| 06 | [Mappenstructuur](docs/06-folder-structure.md) |
| 10 | [API-documentatie](docs/10-api-documentation.md) |
| 11 | [AI-architectuur](docs/11-ai-architecture.md) |
| 15 | [Deployment-handleiding](docs/15-deployment.md) |
| 16 | [Gebruikershandleiding](docs/16-user-manual.md) |

## Projectstructuur

```
backend/    FastAPI (core · domain · application · infrastructure · api · workers) + Alembic + tests
frontend/   Flutter (feature-first: core + auth/dashboard/portfolio/import/dividends/fire/ai/tax)
db/         Canonieke schema.sql + seeds
docker/     Reverse-proxy config
docs/       Deliverables 1–16
```

## Tests

```bash
cd backend && make test     # 50 unit + integratietests (Postgres vereist voor integratie)
cd frontend && flutter test
```

## Licentie & gebruik

Persoonlijk/educatief gebruik. Geen beleggings-, fiscaal of juridisch advies.
