# 01 — Volledige Systeemarchitectuur

> **Project:** Portfolio & Dividend Management Platform (codenaam **"DivTrack"**)
> **Doel:** Eén centrale applicatie voor portefeuillebeheer, dividendopvolging, investeringsanalyse, financiële planning (FIRE), AI-analyse en Belgische fiscale rapportering.
> **Status:** Architectuurontwerp — productieklaar referentiemodel.

> ⚠️ **Disclaimer (geldt voor het volledige systeem):** De applicatie levert **geen** financieel, fiscaal of juridisch advies. Alle analyses, scores, waarderingen en voorspellingen zijn **uitsluitend educatief en informatief**. Voorspellingen worden nooit als garantie weergegeven. Deze disclaimer wordt in de UI, in elk gegenereerd rapport en in elke AI-respons opgenomen.

---

## 1. Architectuuroverzicht

DivTrack is opgebouwd als een **modulaire, service-georiënteerde monorepo** met een duidelijke scheiding tussen presentatie, applicatielogica, domeinlogica en infrastructuur. De architectuur volgt principes van **Clean Architecture / Hexagonal Architecture** (ports & adapters) aan backendzijde, zodat externe afhankelijkheden (marktdata-providers, brokers, AI-providers) achter interfaces zitten en uitwisselbaar zijn.

```
┌──────────────────────────────────────────────────────────────────────────┐
│                              CLIENTS (Presentation)                        │
│                                                                            │
│   ┌────────────────────┐     ┌────────────────────┐    ┌───────────────┐  │
│   │ Flutter App         │    │ Flutter Desktop     │    │ (toekomst)    │  │
│   │ iOS / Android       │    │ Windows/macOS/Linux │    │ Web (Flutter) │  │
│   │ - Biometrische login│    │ - Multi-window      │    │               │  │
│   └─────────┬──────────┘     └─────────┬──────────┘    └───────┬───────┘  │
└─────────────┼──────────────────────────┼──────────────────────┼──────────┘
              │            HTTPS / REST + WebSocket (JWT)         │
              └──────────────────────────┬──────────────────────┘
                                         │
┌────────────────────────────────────────▼──────────────────────────────────┐
│                         API GATEWAY / EDGE (Nginx / Traefik)               │
│   TLS-terminatie · rate limiting · gzip · security headers · routing       │
└────────────────────────────────────────┬──────────────────────────────────┘
                                         │
┌────────────────────────────────────────▼──────────────────────────────────┐
│                       BACKEND — FastAPI (ASGI, Uvicorn/Gunicorn)           │
│                                                                            │
│  ┌──────────────────────────── API LAYER (routers) ──────────────────────┐ │
│  │ auth · users · portfolios · positions · transactions · dividends ·    │ │
│  │ imports · analysis · valuation · fire · scenarios · ai · reports ·    │ │
│  │ tax(BE) · watchlists · alerts · notifications · market-data           │ │
│  └───────────────────────────────────────────────────────────────────────┘ │
│  ┌──────────────────────── APPLICATION / SERVICE LAYER ──────────────────┐ │
│  │ Use-cases, orchestratie, transactionele grenzen, DTO-mapping          │ │
│  └───────────────────────────────────────────────────────────────────────┘ │
│  ┌──────────────────────────── DOMAIN LAYER ─────────────────────────────┐ │
│  │ Entities · Value Objects · domeinregels (yield, YoC, CAGR, DCF, DDM,  │ │
│  │ FIRE, health score, risico) · zuiver, framework-onafhankelijk         │ │
│  └───────────────────────────────────────────────────────────────────────┘ │
│  ┌──────────────────── INFRASTRUCTURE / ADAPTERS ────────────────────────┐ │
│  │ SQLAlchemy repos · Redis cache · broker-import adapters ·             │ │
│  │ market-data adapters · AI-provider adapters · PDF-generator ·         │ │
│  │ notificatie-adapters (email/Telegram/push) · object storage          │ │
│  └───────────────────────────────────────────────────────────────────────┘ │
└──────┬───────────────┬───────────────┬───────────────┬────────────────────┘
       │               │               │               │
┌──────▼─────┐  ┌──────▼─────┐  ┌──────▼──────┐  ┌─────▼───────────────────┐
│ PostgreSQL │  │   Redis    │  │  Celery     │  │ Object Storage (S3/MinIO)│
│ (primair)  │  │ cache +    │  │  workers +  │  │  rapporten, uploads,     │
│ TimescaleDB│  │ broker +   │  │  beat       │  │  importbestanden         │
│ (optioneel)│  │ ratelimit  │  │ (scheduler) │  │                          │
└────────────┘  └────────────┘  └──────┬──────┘  └──────────────────────────┘
                                       │
        ┌──────────────────────────────┼───────────────────────────────┐
        │            EXTERNE INTEGRATIES (achter adapters)              │
        │  Marktdata: yfinance / Financial Modeling Prep / Alpha        │
        │  Vantage / EOD Historical Data (pluggable)                    │
        │  AI: OpenAI · Anthropic Claude · Ollama (lokaal)              │
        │  Notificaties: SMTP · Telegram Bot API · FCM/APNs             │
        └───────────────────────────────────────────────────────────────┘
```

---

## 2. Architecturale principes

1. **Clean / Hexagonal Architecture** — domeinlogica is zuiver Python zonder framework-afhankelijkheden. Alles wat extern is (DB, HTTP, providers) zit achter een **port** (interface) met **adapters** als implementatie. Dit maakt brokers, marktdataproviders en AI-providers uitwisselbaar en testbaar met mocks.
2. **Provider-agnostisch** — Marktdata, AI en notificaties worden aangesproken via abstracte interfaces. Configuratie bepaalt welke concrete provider actief is (Strategy + Factory pattern).
3. **Generiek importframework** — Broker-imports werken via een pipeline (`parse → normalize → classify → deduplicate → persist`) waarbij elke broker enkel een eigen *parser/mapper* levert. Nieuwe brokers toevoegen vergt geen wijziging aan de kern.
4. **CQRS-light** — Lees-zware analytics (dashboards) worden via gematerialiseerde views / Redis-cache geserveerd; schrijfacties lopen via expliciete commands met audit trail.
5. **Event-driven achtergrondverwerking** — Zware taken (import-parsing, koers-refresh, AI-analyse, PDF-generatie, notificaties) lopen asynchroon via Celery, nooit in de request/response-cyclus.
6. **Security by design** — JWT (kort levende access + refresh), 2FA (TOTP), biometrie op device, encryptie at-rest voor gevoelige velden, volledige audit logging, secrets via env/secret manager.
7. **Educatief, niet adviserend** — Elke output die als "advies" kan worden geïnterpreteerd (Buy/Hold/Sell, FIRE, fiscaal) draagt een verplichte disclaimer en is geformuleerd als informatie, niet als aanbeveling.

---

## 3. Componenten in detail

### 3.1 Frontend — Flutter (mobiel + desktop)

**Keuze: Flutter** (boven React+Electron) omwille van: één codebase voor iOS, Android, Windows, macOS, Linux én later web; native biometrische login (`local_auth`); uitstekende grafiekbibliotheken (`fl_chart`, `syncfusion_flutter_charts`); en lichtere desktopbundels dan Electron.

| Laag | Technologie | Verantwoordelijkheid |
|------|-------------|----------------------|
| State management | **Riverpod** | Reactieve, testbare state; dependency injection |
| Navigatie | **go_router** | Declaratieve routing, deep links, auth-guards |
| Netwerk | **dio** + interceptors | REST-calls, auto token-refresh, retry/backoff |
| Realtime | **web_socket_channel** | Live koers- en portefeuille-updates |
| Lokale opslag | **flutter_secure_storage** | Tokens, biometrie-flag, device-id |
| Grafieken | **fl_chart** + **syncfusion_flutter_charts** | Interactieve allocatie-/dividend-/rendementsgrafieken |
| Theming | Material 3 + custom design tokens | Light/Dark mode, responsive (mobiel/tablet/desktop) |
| i18n | **flutter_localizations** | NL (primair) + EN |
| Codegen | **freezed** + **json_serializable** | Immutable models, DTO (de)serialisatie |

Architectuurpatroon frontend: **feature-first** met per feature `data / domain / presentation` lagen (mirrort de backend).

### 3.2 Backend — Python FastAPI

| Onderdeel | Technologie |
|-----------|-------------|
| Web framework | **FastAPI** (async, OpenAPI-native) |
| ASGI server | **Uvicorn** workers achter **Gunicorn** |
| ORM | **SQLAlchemy 2.0** (async) + **Alembic** (migraties) |
| Validatie/serialisatie | **Pydantic v2** |
| Auth | **python-jose** (JWT), **passlib[bcrypt]**, **pyotp** (TOTP/2FA) |
| Achtergrondtaken | **Celery** + **Redis** broker + **Celery Beat** (scheduler) |
| Caching | **redis-py** (async) |
| HTTP-client | **httpx** (async) voor externe providers |
| PDF | **WeasyPrint** (HTML/CSS → PDF) of **ReportLab** |
| Excel/CSV | **openpyxl**, **pandas** |
| Testing | **pytest**, **pytest-asyncio**, **httpx AsyncClient**, **factory_boy** |
| Observability | **structlog** (JSON logs), **Prometheus** metrics, **Sentry** (errors) |

### 3.3 Datalaag — PostgreSQL (+ optioneel TimescaleDB)

- **PostgreSQL 16** als primaire transactionele store (ACID, sterke constraints, JSONB voor flexibele velden zoals AI-output en importmappings).
- **TimescaleDB-extensie (optioneel)** voor tijdreeksen (historische koersen, portefeuillewaarde per dag) — hypertables met automatische partitionering en continuous aggregates voor snelle dashboard-queries.
- Money wordt opgeslagen als `NUMERIC(20,8)` (nooit float) en in code als `Decimal`.

### 3.4 Caching & taken — Redis + Celery

- **Redis** dient drie doelen: (1) cache van marktdata en dashboard-aggregaties met TTL, (2) Celery-broker & result-backend, (3) rate-limiting buckets en idempotency-keys.
- **Celery workers** verwerken: importbestanden, koers-refresh (periodiek), dividend-detectie, AI-analyses, PDF-rapporten, notificaties.
- **Celery Beat** plant terugkerende jobs: dagelijkse koersupdate, ex-dividend-kalender-sync, end-of-day portefeuillewaardering, dividend-betaaldetectie.

### 3.5 AI-laag — pluggable LLM-providers

```
                ┌─────────────────────────────────────────┐
                │            AIAnalysisService              │
                │  (bouwt context, kiest provider, parsed   │
                │   gestructureerde JSON-output, disclaimer)│
                └───────────────┬───────────────────────────┘
                                │  LLMProvider (port/interface)
        ┌───────────────────────┼───────────────────────────┐
   ┌────▼─────┐           ┌──────▼──────┐             ┌──────▼──────┐
   │ OpenAI   │           │ Anthropic   │             │ Ollama      │
   │ adapter  │           │ Claude      │             │ (lokaal)    │
   └──────────┘           │ adapter     │             └─────────────┘
                          └─────────────┘
```

- De AI krijgt een **deterministische, vooraf berekende contextbundel** (portefeuille-snapshot, ratio's, allocaties, dividendkwaliteit, risicometrieken). De LLM **rekent niet zelf** financiële kerncijfers — die komen uit de domeinlaag. De LLM **interpreteert en verwoordt** (risico's, concentratie, kansen) en geeft gestructureerde JSON terug (score, sterktes/zwaktes/kansen/bedreigingen, confidence).
- Output wordt gevalideerd tegen een Pydantic-schema; ongeldige output → retry/fallback.
- Privacymodus: gebruiker kan **Ollama (lokaal)** kiezen zodat geen portefeuilledata de server verlaat.

### 3.6 Externe integraties (achter adapters)

| Domein | Port (interface) | Voorbeeld-adapters |
|--------|------------------|--------------------|
| Marktdata | `MarketDataProvider` | yfinance, Financial Modeling Prep, Alpha Vantage, EOD Historical Data |
| Fundamentals | `FundamentalsProvider` | FMP, Alpha Vantage |
| Broker-import | `BrokerStatementParser` | BUX, generieke CSV, Excel, PDF |
| AI | `LLMProvider` | OpenAI, Claude, Ollama |
| Notificaties | `Notifier` | SMTP, Telegram, FCM/APNs push |
| Object storage | `FileStorage` | MinIO (self-host), S3, lokaal filesystem |

---

## 4. Belangrijkste dataflows

### 4.1 Broker-import (BUX/CSV/Excel/PDF)

```
Client upload bestand
  → POST /imports (multipart)            [API valideert type/grootte, slaat ruw bestand op]
  → Celery taak: import_pipeline
        1. PARSE     : broker-specifieke parser → ruwe records
        2. NORMALIZE : naar canoniek TransactionDraft (currency, datum, ISIN/ticker)
        3. CLASSIFY  : type bepalen (buy/sell/dividend/fee/tax/split/...)
        4. ENRICH    : ticker↔ISIN resolutie, FX-koers op transactiedatum
        5. DEDUPE    : hash (broker, externe-id, datum, ticker, bedrag) → duplicaten weg
        6. STAGE     : opslaan als ImportBatch met previewbare drafts
  → Client haalt preview op, bevestigt/wijzigt mapping
  → POST /imports/{id}/commit            [drafts → echte Transactions, posities herberekend]
```

### 4.2 Koers- & waarde-refresh (periodiek)

```
Celery Beat (elk X min tijdens beursuren)
  → market_data.refresh_quotes(alle unieke tickers)
  → cache in Redis (TTL) + persist EOD-snapshot in price_history
  → herbereken position.market_value, unrealized_pnl
  → push update via WebSocket naar verbonden clients
```

### 4.3 AI Koop/Houd/Verkoop-rapport

```
POST /ai/analyze/position/{id}
  → service bouwt deterministische contextbundel (ratio's, waardering, dividend, risico)
  → LLMProvider.generate(structured) → JSON {recommendation, confidence, risk, S/W/O/T}
  → validatie (Pydantic) + disclaimer toegevoegd
  → persist als AIAnalysis (audit) + return
```

### 4.4 Belgisch fiscaal rapport

```
GET /tax/be/report?year=2025
  → aggregatie: buitenlandse/Belgische dividenden, RV (30%), buitenlandse bronbelasting,
    TOB per transactietype, transactiekosten
  → output: gestructureerd overzicht + PDF-export (informatief, met disclaimer)
```

---

## 5. Deployment-architectuur

```
                         ┌────────────────────────────┐
                         │   Reverse proxy (Traefik)   │
                         │  TLS (Let's Encrypt) · WAF  │
                         └──────────────┬──────────────┘
        ┌───────────────┬───────────────┼───────────────┬──────────────┐
   ┌────▼────┐    ┌─────▼─────┐   ┌──────▼──────┐  ┌──────▼─────┐  ┌─────▼────┐
   │ api     │    │ api       │   │ worker      │  │ beat       │  │ flower   │
   │ (uvicorn│ ×N │ (uvicorn) │   │ (celery)×N  │  │ (scheduler)│  │ (monitor)│
   └────┬────┘    └─────┬─────┘   └──────┬──────┘  └────────────┘  └──────────┘
        └───────────────┴────────────────┴──────────┬───────────────────────┘
                        ┌───────────────┬────────────┼──────────────┐
                   ┌────▼────┐    ┌──────▼─────┐  ┌───▼────┐   ┌─────▼─────┐
                   │postgres │    │   redis    │  │ minio  │   │ ollama    │
                   │(volume) │    │  (volume)  │  │(volume)│   │(optioneel)│
                   └─────────┘    └────────────┘  └────────┘   └───────────┘
```

- **Docker Compose** voor lokale ontwikkeling en single-VPS productie.
- Elke component is een aparte container; horizontaal schaalbaar (`api`, `worker`).
- **CI/CD** (GitHub Actions): lint → typecheck → tests → build images → push registry → deploy.
- Volumes voor Postgres, Redis-persistentie, MinIO en uploads. Dagelijkse `pg_dump`-back-ups naar object storage.

---

## 6. Cross-cutting concerns

| Concern | Aanpak |
|---------|--------|
| **AuthN/AuthZ** | JWT access (15 min) + refresh (7 dagen, roterend), 2FA (TOTP), biometrie op device, rollen (user/admin), per-resource ownership checks |
| **Encryptie** | TLS in transit; gevoelige kolommen (broker-credentials, 2FA-secret) encrypted at-rest (AES-GCM via app-level envelope encryption); volledige DB-encryptie op volumeniveau aanbevolen |
| **Audit logging** | Onveranderlijke `audit_log`-tabel: wie, wat, wanneer, waarvandaan (IP/device); elke schrijfactie op financiële data |
| **Rate limiting** | Per-IP en per-user buckets in Redis (auth-endpoints strenger) |
| **Idempotency** | Idempotency-key header op import/commit en betaling-achtige acties |
| **Observability** | Gestructureerde JSON-logs (structlog), Prometheus-metrics, health/ready endpoints, Sentry voor exceptions |
| **Foutafhandeling** | Uniforme error-envelope (`code`, `message`, `details`), nooit stacktraces naar client |
| **Configuratie** | 12-factor: alles via env-vars / Pydantic `Settings`; secrets nooit in code/repo |
| **i18n & locale** | NL primair; geldbedragen met currency + locale-formatting; tijdzones UTC in DB, lokaal in UI |
| **Money & precisie** | `Decimal`/`NUMERIC(20,8)` overal; bankers-rounding bij presentatie |

---

## 7. Technische beslissingen & afwegingen

| Beslissing | Gekozen | Alternatief | Reden |
|------------|---------|-------------|-------|
| Frontend | Flutter | React+Electron | Eén codebase mobiel+desktop, native biometrie, lichtere bundels |
| Backend async | FastAPI async + SQLAlchemy 2.0 async | Django | Performance bij I/O-zware externe calls, native OpenAPI |
| Achtergrond | Celery + Redis | RQ / Arq | Mature scheduling (Beat), retries, monitoring (Flower) |
| Tijdreeksen | TimescaleDB-extensie (optioneel) | Plain Postgres | Snellere dashboard-aggregaties; blijft "gewoon Postgres" |
| AI-financiën | Domein rekent, LLM interpreteert | LLM rekent alles | Determinisme, auditbaarheid, geen hallucinatie op cijfers |
| Geld | Decimal/NUMERIC | float | Vermijdt afrondingsfouten in financiële data |

---

## 8. Niet-functionele vereisten (NFR's)

- **Performance:** dashboard < 500 ms (gecachte aggregaties); koers-refresh asynchroon.
- **Schaalbaarheid:** stateless API-laag, horizontaal schaalbaar; achtergrondwerk ontkoppeld.
- **Beschikbaarheid:** health-/readiness-probes; graceful shutdown; retries met backoff naar externe providers.
- **Betrouwbaarheid:** idempotente imports, transactionele commits, dagelijkse back-ups.
- **Onderhoudbaarheid:** Clean Architecture, hoge testdekking domeinlaag, typed (mypy/Pydantic).
- **Privacy:** lokale AI-optie (Ollama); dataminimalisatie; gebruiker bezit en kan exporteren/verwijderen.
- **Compliance-houding:** uitsluitend educatieve output, expliciete disclaimers, geen advies.

---

## 9. Roadmap-fasering (implementatievolgorde)

1. **Fundament:** auth (JWT/2FA), users, portfolios, posities, transacties, audit. 
2. **Import:** generiek framework + BUX/CSV/Excel/PDF-parsers, dedup.
3. **Marktdata & dashboard:** koers-refresh, aggregaties, allocatiegrafieken.
4. **Dividenden:** dividend-tracking, kalender, YoC/CAGR, dividend-dashboard.
5. **Analyse & waardering:** ratio's, score 0–100, DCF/DDM, fair value.
6. **FIRE & scenario's:** Lean/Coast/Barista/Fat, simulaties.
7. **AI-analyst & Buy/Hold/Sell:** context-engine + LLM-adapters.
8. **Fiscaliteit (BE):** RV, bronbelasting, TOB, rapporten.
9. **Rapporten & export:** PDF/CSV/Excel/JSON.
10. **Notificaties & watchlists:** push/Telegram/email, alerts.
11. **Hardening & deployment:** security, observability, CI/CD, back-ups.

---

*Einde deliverable 1 — Systeemarchitectuur. Stuur `VERDER` voor deliverable 2: Functionele analyse.*
