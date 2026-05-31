# 06 — Mappenstructuur (Monorepo)

> De volledige projectboom van DivTrack. Eén monorepo met `backend/` (FastAPI, clean/hexagonal), `frontend/` (Flutter, feature-first), `db/` (referentie-DDL + seeds), `docker/`, `.github/` (CI/CD), `scripts/` en `docs/`. Deze structuur is reeds gescaffold in de repo.

---

## 1. Top-level

```
Stocks_app/
├── README.md
├── docs/                  # deliverables 1–6, API-docs, AI-arch, handleidingen
│   ├── 01-architecture.md
│   ├── 02-functional-analysis.md
│   ├── 03-database-design.md
│   ├── 04-wireframes.md
│   ├── 05-ux-flows.md
│   ├── 06-folder-structure.md
│   └── samples/           # voorbeeld-importbestanden (BUX e.d.)
├── backend/               # Python FastAPI service (deliverables 7,9,10–14)
├── frontend/              # Flutter app (deliverable 8)
├── db/                    # schema.sql (referentie) + seeds
│   ├── schema.sql
│   └── seeds/
├── docker/                # Dockerfiles + compose-fragmenten (deliverable 14)
├── scripts/               # dev/ops helper-scripts
├── .github/workflows/     # CI/CD pipelines (deliverable 14)
├── docker-compose.yml     # orchestratie (deliverable 14)
├── .env.example           # configuratietemplate
└── Makefile               # dev-commando's
```

---

## 2. Backend (`backend/`) — Clean / Hexagonal Architecture

De afhankelijkheden wijzen **naar binnen**: `api → application → domain`, en `infrastructure` implementeert de **ports** (interfaces) die in `domain`/`application` gedefinieerd zijn. De domeinlaag is zuiver Python (geen FastAPI/SQLAlchemy-imports).

```
backend/
├── pyproject.toml              # deps, tooling (ruff, mypy, pytest)
├── alembic.ini
├── Dockerfile
├── app/
│   ├── main.py                 # FastAPI-app factory, router-mount, middleware
│   ├── core/                   # cross-cutting (geen domeinlogica)
│   │   ├── config.py           # Pydantic Settings (12-factor)
│   │   ├── security.py         # JWT, hashing, TOTP, dependencies
│   │   ├── logging.py          # structlog setup
│   │   ├── errors.py           # exceptions + handlers (error-envelope)
│   │   ├── ratelimit.py        # Redis rate limiting
│   │   └── deps.py             # FastAPI dependency providers (DI)
│   │
│   ├── domain/                 # ZUIVERE domeinlaag
│   │   ├── entities/           # Portfolio, Position, Transaction, Asset, ...
│   │   ├── value_objects/      # Money, Currency, Quantity, Percentage
│   │   ├── services/           # domeinberekeningen (geen I/O):
│   │   │   ├── pnl.py          #   FIFO realized/unrealized P/L
│   │   │   ├── dividends.py    #   yield, YoC, CAGR, veiligheid
│   │   │   ├── valuation.py    #   DCF, DDM, multiples, margin of safety
│   │   │   ├── scoring.py      #   asset-score 0–100, health-score
│   │   │   ├── fire.py         #   Lean/Coast/Barista/Fat, FI-datum
│   │   │   ├── scenarios.py    #   simulaties, Monte-Carlo
│   │   │   ├── risk.py         #   volatiliteit, concentratie, correlatie
│   │   │   └── tax_be.py       #   RV, bronbelasting, TOB (informatief)
│   │   └── ports/              # interfaces (Protocols):
│   │       ├── market_data.py  #   MarketDataProvider, FundamentalsProvider
│   │       ├── broker_parser.py#   BrokerStatementParser
│   │       ├── llm.py          #   LLMProvider
│   │       ├── notifier.py     #   Notifier
│   │       ├── storage.py      #   FileStorage
│   │       └── repositories.py #   *Repository protocols
│   │
│   ├── application/            # use-cases / orchestratie
│   │   ├── dto/                # interne data transfer objects
│   │   └── services/           # AuthService, PortfolioService, ImportService,
│   │                           # DividendService, AnalysisService, FireService,
│   │                           # AIAnalysisService, TaxService, ReportService,
│   │                           # AlertService, NotificationService, ...
│   │
│   ├── infrastructure/         # adapters (implementeren ports)
│   │   ├── db/
│   │   │   ├── base.py         # async engine, session, declarative base
│   │   │   ├── models/         # SQLAlchemy ORM-modellen (mirror schema.sql)
│   │   │   └── repositories/   # SQLAlchemy repo-implementaties
│   │   ├── cache/redis.py      # async Redis-client + cache helpers
│   │   ├── market_data/        # yfinance/FMP/AlphaVantage adapters + factory
│   │   ├── brokers/            # bux.py, csv_generic.py, excel.py, pdf.py + registry
│   │   ├── ai/                 # openai.py, claude.py, ollama.py + factory
│   │   ├── notifications/      # email.py, telegram.py, push.py
│   │   ├── storage/            # local.py, s3_minio.py
│   │   └── reports/            # pdf (WeasyPrint), excel, csv, json generators
│   │
│   ├── schemas/                # Pydantic request/response-modellen (API-contract)
│   │
│   ├── api/
│   │   ├── deps.py             # auth/user dependencies voor routers
│   │   └── v1/
│   │       ├── api.py          # APIRouter-aggregatie
│   │       └── routers/        # auth, users, portfolios, positions, transactions,
│   │                           # imports, dividends, calendar, analysis, valuation,
│   │                           # fire, scenarios, ai, watchlists, alerts,
│   │                           # notifications, tax, reports, market
│   │
│   └── workers/                # Celery
│       ├── celery_app.py       # app + beat-schedule
│       └── tasks/              # import_tasks, market_tasks, dividend_tasks,
│                               # ai_tasks, report_tasks, notification_tasks
│
├── alembic/
│   ├── env.py
│   └── versions/               # versioned migraties (deliverable 9)
└── tests/
    ├── conftest.py
    ├── unit/                   # domeinservices (pnl, valuation, fire, tax…)
    ├── integration/            # repos + API met test-DB
    └── e2e/                    # volledige flows (import → dashboard)
```

**Waarom deze lagen?**
- **Testbaarheid:** domeinservices testen zonder DB/HTTP (pure functies).
- **Verwisselbaarheid:** een nieuwe broker = nieuw bestand in `infrastructure/brokers/` + registratie; geen kernwijziging (open/closed).
- **Determinisme AI:** financiële cijfers komen uit `domain/services`, niet uit de LLM-adapter.

---

## 3. Frontend (`frontend/`) — Flutter, feature-first

Elke feature spiegelt de backend-lagen (`data / domain / presentation`). Gedeelde zaken in `core/`.

```
frontend/
├── pubspec.yaml               # deps: riverpod, go_router, dio, fl_chart,
│                              # syncfusion_charts, freezed, local_auth, secure_storage
├── analysis_options.yaml
├── lib/
│   ├── main.dart              # bootstrap, ProviderScope, thema, router
│   ├── core/
│   │   ├── network/           # dio-client, interceptors (auth-refresh, retry)
│   │   ├── theme/             # design tokens, light/dark, typografie
│   │   ├── router/            # go_router routes + auth-guards
│   │   ├── storage/           # flutter_secure_storage wrapper
│   │   ├── widgets/           # herbruikbaar (charts, cards, disclaimer-strip…)
│   │   └── utils/             # money/locale-formatting, validators
│   └── features/
│       ├── auth/              # login, registratie, 2FA, biometrie
│       ├── dashboard/         # KPI's, allocatie/FIRE/dividend-widgets
│       ├── portfolio/         # posities-lijst + detail
│       ├── transactions/      # CRUD + audit
│       ├── import/            # import-wizard (4 stappen)
│       ├── dividends/         # dividend-dashboard
│       ├── calendar/          # dividendkalender
│       ├── analysis/          # ratio's + score
│       ├── valuation/         # DCF/DDM/multiples UI
│       ├── fire/              # FIRE-doelen + projectie
│       ├── scenarios/         # scenario-vergelijking
│       ├── ai/                # AI-analyst + Koop/Houd/Verkoop
│       ├── watchlist/         # watchlists + items
│       ├── alerts/            # alert-beheer
│       ├── tax/               # Belgisch fiscaal overzicht
│       ├── reports/           # rapporten/downloads
│       └── settings/          # profiel, valuta, thema, providers, devices
│       (elke feature: data/{models,datasources,repositories} +
│        domain/{entities,repositories,usecases} +
│        presentation/{pages,widgets,providers})
└── test/                      # widget- en unit-tests
```

---

## 4. Infrastructuur & ops

```
db/
├── schema.sql                 # referentie-DDL (bron van waarheid voor model)
└── seeds/                     # systeembrokers (BUX), FX-basis, demo-assets

docker/
├── backend.Dockerfile
├── nginx/ of traefik/         # reverse-proxy config
└── ...

.github/workflows/
├── ci.yml                     # lint → typecheck → test (backend+frontend)
└── deploy.yml                 # build images → push → deploy

scripts/
├── dev_up.sh / dev_down.sh
├── seed_db.py
├── backup_db.sh
└── wait_for_db.sh

docker-compose.yml             # api, worker, beat, postgres, redis, minio, (ollama)
.env.example                   # alle env-vars met veilige defaults
Makefile                       # make up / test / migrate / lint / seed
```

---

## 5. Naamgevings- & conventieafspraken

| Aspect | Conventie |
|--------|-----------|
| Python modules/bestanden | `snake_case` |
| Python klassen | `PascalCase` (entiteiten, services, adapters) |
| Dart bestanden | `snake_case.dart`; klassen `PascalCase` |
| API-routes | `/api/v1/<resource>` (kebab waar nodig), plural nouns |
| ORM-tabellen | exact zoals `db/schema.sql` |
| Ports (interfaces) | suffix `Provider`/`Repository`/`Parser`/`Notifier` |
| Tests | `test_<unit>.py` / `<widget>_test.dart` |
| Env-vars | `UPPER_SNAKE_CASE`, prefix per domein (`DB_`, `REDIS_`, `JWT_`, `AI_`) |

---

## 6. Afhankelijkheidsregels (afgedwongen via review/lint)

```
api  ───────► application ───────► domain ◄─────── infrastructure
 │                                   ▲                    │
 └─ mag schemas + application        │  domein importeert  │ implementeert ports,
    aanroepen                        │  NIETS van buiten   │ mag domein importeren
                                     └─────────────────────┘
```
- `domain/` importeert **nooit** uit `infrastructure/`, `api/` of frameworks.
- `infrastructure/` implementeert `domain/ports/*` en mag domein-entities gebruiken.
- `api/` praat enkel met `application/` (+ `schemas/`), niet rechtstreeks met repos.

---

*Einde deliverable 6 — Mappenstructuur (gescaffold in de repo). Stuur `VERDER` voor deliverable 7: Backend code — ik start met `core/` (config, security, errors) + `domain/` (value objects, entities, kernservices: P/L, dividenden, waardering, FIRE, fiscaliteit).*
