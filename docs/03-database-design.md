# 03 — Database Ontwerp (PostgreSQL)

> Volledig relationeel schema voor DivTrack. PostgreSQL 16, optioneel TimescaleDB voor tijdreeksen. Geld als `NUMERIC(20,8)`, tijdstippen als `TIMESTAMPTZ` (UTC). Identifiers als `UUID` (gen_random_uuid). Soft-delete waar zinvol; onveranderlijke audit log.

> ⚠️ Fiscale/score/AI-velden zijn informatief/educatief — zie disclaimers in 01/02.

---

## 1. Ontwerpprincipes

1. **Single source of truth = transacties.** Posities (`positions`) zijn een afgeleide/gematerialiseerde projectie van `transactions`, herberekend bij elke commit.
2. **Geld = `NUMERIC(20,8)`**, valuta apart als ISO-4217 `CHAR(3)`. Nooit floats.
3. **Tijd = `TIMESTAMPTZ` in UTC**; datums zonder tijd als `DATE` (bv. ex-dividend).
4. **UUID-PK's** (`uuid DEFAULT gen_random_uuid()`) voor veilige, niet-raadbare id's.
5. **Multi-tenancy op rij-niveau:** vrijwel elke tabel heeft `user_id` met FK + index; API dwingt ownership af.
6. **Referentiële integriteit** met expliciete `ON DELETE` regels; financiële historie wordt nooit hard verwijderd (soft-delete + audit).
7. **JSONB** voor flexibele, evoluerende payloads (importmapping, AI-output, ratio-snapshots) met GIN-index waar nodig.
8. **Enums** als PostgreSQL `ENUM`-types voor vaste verzamelingen (transactietype, asset class, advies…).

---

## 2. Entity-Relationship Diagram (logisch)

```
                         ┌───────────┐
                         │   users   │
                         └─────┬─────┘
        ┌──────────────┬───────┼───────────┬───────────────┬──────────────┐
        │              │       │           │               │              │
 ┌──────▼─────┐ ┌──────▼────┐ ┌▼──────────┐ ┌▼────────────┐ ┌▼──────────┐ ┌▼───────────┐
 │  devices   │ │ user_     │ │ portfolios│ │ watchlists  │ │ alerts    │ │ audit_log  │
 │            │ │ settings  │ │           │ │             │ │           │ │            │
 └────────────┘ └───────────┘ └────┬──────┘ └──────┬──────┘ └───────────┘ └────────────┘
                                   │               │
                  ┌────────────────┼───────┐  ┌────▼──────────┐
                  │                │       │  │ watchlist_    │
            ┌─────▼──────┐  ┌──────▼─────┐ │  │ items         │──→ assets
            │ positions  │  │transactions│ │  └───────────────┘
            └─────┬──────┘  └──────┬─────┘ │
                  │                │       │
                  │         ┌──────▼──────┐│
                  │         │ import_     ││
                  │         │ batches     ││
                  │         └──────┬──────┘│
                  │         ┌──────▼──────┐│
                  │         │ import_     ││
                  │         │ rows        ││
                  │         └─────────────┘│
                  │                        │
          ┌───────▼────────────────────────▼──────────────────────────┐
          │                         assets                              │
          │  (ticker, ISIN, naam, asset_class, sector, land, valuta)    │
          └───┬───────────────┬──────────────┬───────────────┬─────────┘
              │               │              │               │
      ┌───────▼─────┐ ┌───────▼──────┐ ┌─────▼───────┐ ┌─────▼────────┐
      │ price_      │ │ dividends    │ │ fundamentals│ │ valuations   │
      │ history     │ │ (events)     │ │ (snapshots) │ │ (DCF/DDM…)   │
      └─────────────┘ └──────────────┘ └─────────────┘ └──────────────┘

  Onafhankelijke / koppel-tabellen:
   brokers · dividend_schedule · fx_rates · ai_analyses · reports ·
   tax_summaries · notifications · fire_plans · scenarios · portfolio_snapshots
```

---

## 3. Enumeraties

| Enum-type | Waarden |
|-----------|---------|
| `asset_class` | `STOCK, ETF, REIT, BOND, CASH, CRYPTO` |
| `transaction_type` | `BUY, SELL, DIVIDEND, FEE, TAX, DEPOSIT, WITHDRAWAL, STOCK_SPLIT, REVERSE_SPLIT` |
| `transaction_source` | `MANUAL, IMPORT_CSV, IMPORT_EXCEL, IMPORT_PDF, IMPORT_BUX, API` |
| `import_status` | `PENDING, PARSING, PREVIEWED, COMMITTED, FAILED` |
| `import_row_status` | `NEW, DUPLICATE, INVALID, COMMITTED` |
| `recommendation` | `STRONG_BUY, BUY, HOLD, REDUCE, SELL` |
| `valuation_verdict` | `UNDERVALUED, FAIR, OVERVALUED` |
| `valuation_method` | `DCF, DDM, MULTIPLES, BLENDED` |
| `alert_type` | `PRICE_TARGET, FAIR_VALUE, DIVIDEND_RECEIVED, EX_DIVIDEND, RISK, PRICE_MOVE, OVERVALUED, UNDERVALUED` |
| `alert_channel` | `PUSH, TELEGRAM, EMAIL` |
| `notification_status` | `PENDING, SENT, FAILED, READ` |
| `fire_type` | `LEAN, COAST, BARISTA, FAT` |
| `ai_provider` | `OPENAI, CLAUDE, OLLAMA` |
| `report_type` | `PORTFOLIO, DIVIDEND, ANNUAL, TAX, FIRE, RISK, ALLOCATION, AI` |
| `report_format` | `PDF, CSV, EXCEL, JSON` |
| `report_status` | `QUEUED, GENERATING, READY, FAILED` |
| `dividend_kind` | `CONFIRMED, PROJECTED` |
| `cost_basis_method` | `FIFO, LIFO, AVERAGE` |

---

## 4. Tabellen (overzicht + sleutels)

### 4.1 Identiteit & beveiliging

**users**
| kolom | type | opmerking |
|-------|------|-----------|
| id | uuid PK | |
| email | citext UNIQUE NOT NULL | hoofdletterongevoelig |
| password_hash | text NOT NULL | bcrypt |
| full_name | text | |
| base_currency | char(3) NOT NULL DEFAULT 'EUR' | |
| locale | text NOT NULL DEFAULT 'nl-BE' | |
| is_active | bool NOT NULL DEFAULT true | |
| is_admin | bool NOT NULL DEFAULT false | |
| totp_secret | text | versleuteld; null = 2FA uit |
| totp_enabled | bool NOT NULL DEFAULT false | |
| created_at / updated_at | timestamptz | |

**devices** — geregistreerde toestellen voor biometrie/refresh.
`id, user_id→users, device_name, platform, push_token, refresh_token_hash, biometric_enabled, last_seen_at, revoked_at, created_at`

**user_settings** — voorkeuren (1:1 met users).
`user_id PK→users, theme(text), cost_basis_method(enum), dividend_tax_rate(numeric), fire_annual_expenses(numeric), fire_swr(numeric DEFAULT 0.04), ai_provider(enum), notify_quiet_hours(jsonb), provider_keys(jsonb, versleuteld)`

**audit_log** — onveranderlijk.
`id, user_id, action(text), entity_type(text), entity_id(uuid), before(jsonb), after(jsonb), ip(inet), device_id, created_at`. Append-only (geen UPDATE/DELETE; afgedwongen via trigger/permissies).

### 4.2 Referentiedata (assets & markt)

**assets** — uniek effect (gedeeld over gebruikers).
`id, ticker, isin UNIQUE, name, asset_class(enum), sector, industry, country(char2), currency(char3), exchange, logo_url, is_active, created_at, updated_at`. Unieke index op `(ticker, exchange)`.

**price_history** — EOD/intraday koersen (TimescaleDB-hypertable op `ts`).
`asset_id→assets, ts(timestamptz), open, high, low, close NUMERIC, volume BIGINT`. PK `(asset_id, ts)`.

**fx_rates** — wisselkoersen per dag.
`base(char3), quote(char3), date(date), rate NUMERIC`. PK `(base, quote, date)`.

**fundamentals** — periodieke snapshot van ratio's per asset.
`id, asset_id→assets, as_of(date), pe, forward_pe, peg, roe, roic, debt_equity, fcf, payout_ratio, revenue_growth, earnings_growth, dividend_growth, eps, book_value, raw(jsonb), source(text), created_at`. Unieke `(asset_id, as_of, source)`.

**dividend_schedule** — bekende/aangekondigde dividenden per asset.
`id, asset_id→assets, ex_date(date), record_date(date), pay_date(date), amount_per_share NUMERIC, currency(char3), frequency(text), kind(dividend_kind), source(text), created_at`. Index op `ex_date`, `pay_date`.

### 4.3 Portefeuille & transacties

**brokers**
`id, user_id→users (nullable voor systeembrokers), name, slug UNIQUE, country, default_currency, parser_key(text), created_at`.

**portfolios**
`id, user_id→users, name, description, base_currency(char3), is_default(bool), created_at, updated_at, deleted_at(nullable)`.

**transactions** — kern, single source of truth.
| kolom | type |
|-------|------|
| id | uuid PK |
| user_id | uuid→users |
| portfolio_id | uuid→portfolios |
| asset_id | uuid→assets (nullable: deposit/withdrawal/fee) |
| broker_id | uuid→brokers (nullable) |
| type | transaction_type |
| trade_date | timestamptz |
| settle_date | date (nullable) |
| quantity | NUMERIC(20,8) (nullable) |
| price | NUMERIC(20,8) (nullable) |
| gross_amount | NUMERIC(20,8) |
| fee | NUMERIC(20,8) DEFAULT 0 |
| tax | NUMERIC(20,8) DEFAULT 0 |
| net_amount | NUMERIC(20,8) |
| currency | char(3) |
| fx_rate | NUMERIC(20,8) DEFAULT 1 (→ base_currency) |
| split_ratio | NUMERIC (nullable, voor splits) |
| source | transaction_source |
| external_id | text (broker-referentie) |
| dedup_hash | text (uniek per user) |
| import_batch_id | uuid→import_batches (nullable) |
| note | text |
| created_at / updated_at | timestamptz |
| deleted_at | timestamptz (soft-delete via correctie) |

Constraints: `UNIQUE(user_id, dedup_hash)`; `CHECK` op type-specifieke verplichte velden (bv. BUY/SELL vereisen asset+quantity+price).

**positions** — afgeleide projectie (1 rij per portfolio+asset).
`id, user_id, portfolio_id→portfolios, asset_id→assets, quantity NUMERIC, avg_cost NUMERIC, total_invested NUMERIC, realized_pnl NUMERIC, currency, opened_at, updated_at`. Unieke `(portfolio_id, asset_id)`. Marktwaarde/onrealiseerde W/V worden runtime berekend uit laatste prijs (niet gepersisteerd, of in `portfolio_snapshots`).

**portfolio_snapshots** — dagelijkse waardering (TimescaleDB-hypertable).
`portfolio_id→portfolios, date(date), total_value NUMERIC, total_cost NUMERIC, cash NUMERIC, unrealized_pnl NUMERIC, day_change NUMERIC, currency`. PK `(portfolio_id, date)`.

### 4.4 Import

**import_batches**
`id, user_id, broker_id→brokers, filename, file_path, file_type, status(import_status), detected_columns(jsonb), column_mapping(jsonb), row_count, dup_count, error(text), created_at, committed_at`.

**import_rows** — genormaliseerde drafts vóór commit.
`id, batch_id→import_batches, raw(jsonb), normalized(jsonb), suggested_type(transaction_type), status(import_row_status), dedup_hash, transaction_id(→transactions, na commit), error(text)`.

### 4.5 Dividenden (ontvangen)

**dividends** — werkelijk geboekte dividend-events (gekoppeld aan transactie van type DIVIDEND).
`id, user_id, portfolio_id→portfolios, asset_id→assets, transaction_id→transactions, ex_date(date), pay_date(date), amount_per_share NUMERIC, shares NUMERIC, gross_amount NUMERIC, withholding_tax NUMERIC, belgian_rv NUMERIC, net_amount NUMERIC, currency, source_country(char2), created_at`.

### 4.6 Analyse, waardering & AI

**asset_scores** — kwaliteitsscore 0–100 per asset (M8).
`id, asset_id→assets, as_of(date), total_score, valuation_score, growth_score, health_score, dividend_score, breakdown(jsonb), created_at`.

**valuations** — fair value (M9).
`id, asset_id→assets, method(valuation_method), fair_value NUMERIC, current_price NUMERIC, margin_of_safety NUMERIC, verdict(valuation_verdict), assumptions(jsonb), as_of(date), created_at`.

**ai_analyses** — AI-output (M12/M13), audit-bestendig.
`id, user_id, scope(text: 'portfolio'|'position'), portfolio_id(nullable), asset_id(nullable), provider(ai_provider), model(text), recommendation(recommendation, nullable), confidence NUMERIC, risk_score NUMERIC, strengths(jsonb), weaknesses(jsonb), opportunities(jsonb), threats(jsonb), summary(text), context_snapshot(jsonb), raw_response(jsonb), disclaimer(text), created_at`.

### 4.7 FIRE & scenario's

**fire_plans**
`id, user_id, name, annual_expenses NUMERIC, swr NUMERIC, expected_return NUMERIC, expected_dividend_growth NUMERIC, monthly_contribution NUMERIC, inflation NUMERIC, targets(jsonb: lean/coast/barista/fat), fi_date(date, nullable), projection(jsonb), created_at, updated_at`.

**scenarios**
`id, user_id, fire_plan_id→fire_plans (nullable), name, params(jsonb), result(jsonb), created_at`.

### 4.8 Watchlist, alerts, notificaties

**watchlists**
`id, user_id→users, name, created_at`.

**watchlist_items**
`id, watchlist_id→watchlists, asset_id→assets, target_price NUMERIC, fair_value_alert bool, dividend_alert bool, note text, created_at`. Unieke `(watchlist_id, asset_id)`.

**alerts** — gebruikersregels.
`id, user_id, asset_id(nullable), portfolio_id(nullable), type(alert_type), threshold(jsonb), channels(alert_channel[]), is_active bool, last_triggered_at, created_at`.

**notifications** — verzonden/te verzenden berichten.
`id, user_id, alert_id(nullable), type(alert_type), channel(alert_channel), title, body, payload(jsonb), status(notification_status), sent_at, read_at, created_at`.

### 4.9 Fiscaliteit & rapporten

**tax_summaries** — Belgische fiscale aggregatie per jaar (M17, informatief).
`id, user_id, year(int), foreign_dividends_gross NUMERIC, belgian_dividends_gross NUMERIC, withholding_tax_foreign NUMERIC, belgian_rv NUMERIC, tob_total NUMERIC, fees_total NUMERIC, net_dividend_income NUMERIC, breakdown(jsonb), generated_at`. Unieke `(user_id, year)`.

**reports** — gegenereerde exports/rapporten.
`id, user_id, type(report_type), format(report_format), status(report_status), params(jsonb), file_path(text), file_size BIGINT, expires_at, created_at, completed_at, error(text)`.

---

## 5. Indexen (selectie)

```
CREATE INDEX ix_tx_user_date        ON transactions(user_id, trade_date DESC);
CREATE INDEX ix_tx_portfolio_asset  ON transactions(portfolio_id, asset_id);
CREATE UNIQUE INDEX ux_tx_dedup     ON transactions(user_id, dedup_hash);
CREATE INDEX ix_positions_user      ON positions(user_id);
CREATE UNIQUE INDEX ux_position_pa  ON positions(portfolio_id, asset_id);
CREATE INDEX ix_price_asset_ts      ON price_history(asset_id, ts DESC);
CREATE INDEX ix_div_sched_exdate    ON dividend_schedule(ex_date);
CREATE INDEX ix_dividends_user_pay  ON dividends(user_id, pay_date);
CREATE INDEX ix_alerts_active       ON alerts(user_id) WHERE is_active;
CREATE INDEX ix_notif_user_status   ON notifications(user_id, status);
CREATE INDEX ix_fundamentals_asof   ON fundamentals(asset_id, as_of DESC);
CREATE INDEX gin_ai_context         ON ai_analyses USING gin (context_snapshot);
CREATE INDEX gin_import_mapping     ON import_batches USING gin (column_mapping);
```

---

## 6. Integriteit & triggers

- **`updated_at`-trigger** op alle muteerbare tabellen (`set_updated_at()`).
- **Audit-trigger** op `transactions`, `positions`, `portfolios`, `user_settings`: schrijft before/after naar `audit_log`.
- **Append-only `audit_log`**: revoke UPDATE/DELETE voor app-rol; alleen INSERT.
- **CHECK-constraints** op `transactions` per type (zie 4.3).
- **FK `ON DELETE`**: `RESTRICT` op financiële kern (transactions/positions), `CASCADE` op afhankelijke metadata (watchlist_items, import_rows).

---

## 7. Migratiestrategie

- **Alembic** beheert versioned migraties (`alembic/versions/*`).
- Extensies: `CREATE EXTENSION IF NOT EXISTS "pgcrypto"` (gen_random_uuid), `citext`, en optioneel `timescaledb`.
- Seed-migratie: systeembrokers (BUX), basis FX, demo-assets.
- Hypertables (`price_history`, `portfolio_snapshots`) worden enkel als TimescaleDB beschikbaar is omgezet; anders gewone tabellen met partitionering op datum.

De volledige DDL staat in `db/schema.sql` (referentie) en wordt in productie via Alembic toegepast (deliverable 9).

---

*Einde deliverable 3 (ontwerp). De bijhorende referentie-DDL staat in `db/schema.sql`. Stuur `VERDER` voor deliverable 4: UI wireframes.*
