-- ============================================================================
-- DivTrack — Reference PostgreSQL schema (DDL)
-- ----------------------------------------------------------------------------
-- This file is the canonical, human-readable reference of the data model.
-- In production the schema is applied via Alembic migrations (see deliverable 9
-- / backend/alembic). Money is NUMERIC(20,8); timestamps are TIMESTAMPTZ (UTC).
--
-- DISCLAIMER: Tax/score/AI columns are informational/educational only.
-- ============================================================================

-- ---------------------------------------------------------------------------
-- Extensions
-- ---------------------------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS "pgcrypto";   -- gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS "citext";      -- case-insensitive email
-- CREATE EXTENSION IF NOT EXISTS "timescaledb";  -- optional, for time-series

-- ---------------------------------------------------------------------------
-- Enum types
-- ---------------------------------------------------------------------------
CREATE TYPE asset_class         AS ENUM ('STOCK','ETF','REIT','BOND','CASH','CRYPTO');
CREATE TYPE transaction_type    AS ENUM ('BUY','SELL','DIVIDEND','FEE','TAX','DEPOSIT','WITHDRAWAL','STOCK_SPLIT','REVERSE_SPLIT');
CREATE TYPE transaction_source  AS ENUM ('MANUAL','IMPORT_CSV','IMPORT_EXCEL','IMPORT_PDF','IMPORT_BUX','API');
CREATE TYPE import_status       AS ENUM ('PENDING','PARSING','PREVIEWED','COMMITTED','FAILED');
CREATE TYPE import_row_status   AS ENUM ('NEW','DUPLICATE','INVALID','COMMITTED');
CREATE TYPE recommendation      AS ENUM ('STRONG_BUY','BUY','HOLD','REDUCE','SELL');
CREATE TYPE valuation_verdict   AS ENUM ('UNDERVALUED','FAIR','OVERVALUED');
CREATE TYPE valuation_method    AS ENUM ('DCF','DDM','MULTIPLES','BLENDED');
CREATE TYPE alert_type          AS ENUM ('PRICE_TARGET','FAIR_VALUE','DIVIDEND_RECEIVED','EX_DIVIDEND','RISK','PRICE_MOVE','OVERVALUED','UNDERVALUED');
CREATE TYPE alert_channel       AS ENUM ('PUSH','TELEGRAM','EMAIL');
CREATE TYPE notification_status AS ENUM ('PENDING','SENT','FAILED','READ');
CREATE TYPE fire_type           AS ENUM ('LEAN','COAST','BARISTA','FAT');
CREATE TYPE ai_provider         AS ENUM ('OPENAI','CLAUDE','OLLAMA');
CREATE TYPE report_type         AS ENUM ('PORTFOLIO','DIVIDEND','ANNUAL','TAX','FIRE','RISK','ALLOCATION','AI');
CREATE TYPE report_format       AS ENUM ('PDF','CSV','EXCEL','JSON');
CREATE TYPE report_status       AS ENUM ('QUEUED','GENERATING','READY','FAILED');
CREATE TYPE dividend_kind       AS ENUM ('CONFIRMED','PROJECTED');
CREATE TYPE cost_basis_method   AS ENUM ('FIFO','LIFO','AVERAGE');

-- ---------------------------------------------------------------------------
-- Shared trigger: maintain updated_at
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION set_updated_at() RETURNS trigger AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ===========================================================================
-- IDENTITY & SECURITY
-- ===========================================================================
CREATE TABLE users (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    email          citext NOT NULL UNIQUE,
    password_hash  text   NOT NULL,
    full_name      text,
    base_currency  char(3) NOT NULL DEFAULT 'EUR',
    locale         text    NOT NULL DEFAULT 'nl-BE',
    is_active      boolean NOT NULL DEFAULT true,
    is_admin       boolean NOT NULL DEFAULT false,
    totp_secret    text,                       -- encrypted at app level
    totp_enabled   boolean NOT NULL DEFAULT false,
    created_at     timestamptz NOT NULL DEFAULT now(),
    updated_at     timestamptz NOT NULL DEFAULT now()
);
CREATE TRIGGER trg_users_updated BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE devices (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    device_name         text,
    platform            text,
    push_token          text,
    refresh_token_hash  text,
    biometric_enabled   boolean NOT NULL DEFAULT false,
    last_seen_at        timestamptz,
    revoked_at          timestamptz,
    created_at          timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_devices_user ON devices(user_id);

CREATE TABLE user_settings (
    user_id             uuid PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    theme               text NOT NULL DEFAULT 'system',
    cost_basis_method   cost_basis_method NOT NULL DEFAULT 'FIFO',
    dividend_tax_rate   numeric(6,4) NOT NULL DEFAULT 0.30,   -- BE roerende voorheffing
    fire_annual_expenses numeric(20,8),
    fire_swr            numeric(6,4) NOT NULL DEFAULT 0.04,
    ai_provider         ai_provider NOT NULL DEFAULT 'OLLAMA',
    notify_quiet_hours  jsonb NOT NULL DEFAULT '{}'::jsonb,
    provider_keys       jsonb NOT NULL DEFAULT '{}'::jsonb,   -- encrypted at app level
    updated_at          timestamptz NOT NULL DEFAULT now()
);
CREATE TRIGGER trg_user_settings_updated BEFORE UPDATE ON user_settings
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE audit_log (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      uuid REFERENCES users(id) ON DELETE SET NULL,
    action       text NOT NULL,
    entity_type  text,
    entity_id    uuid,
    before       jsonb,
    after        jsonb,
    ip           inet,
    device_id    uuid,
    created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_audit_user_time ON audit_log(user_id, created_at DESC);

-- ===========================================================================
-- REFERENCE DATA (assets & market)
-- ===========================================================================
CREATE TABLE assets (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    ticker       text NOT NULL,
    isin         text UNIQUE,
    name         text NOT NULL,
    asset_class  asset_class NOT NULL,
    sector       text,
    industry     text,
    country      char(2),
    currency     char(3) NOT NULL DEFAULT 'USD',
    exchange     text,
    logo_url     text,
    is_active    boolean NOT NULL DEFAULT true,
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX ux_assets_ticker_exchange ON assets(ticker, COALESCE(exchange,''));
CREATE TRIGGER trg_assets_updated BEFORE UPDATE ON assets
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE price_history (
    asset_id  uuid NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    ts        timestamptz NOT NULL,
    open      numeric(20,8),
    high      numeric(20,8),
    low       numeric(20,8),
    close     numeric(20,8) NOT NULL,
    volume    bigint,
    PRIMARY KEY (asset_id, ts)
);
CREATE INDEX ix_price_asset_ts ON price_history(asset_id, ts DESC);
-- SELECT create_hypertable('price_history','ts', if_not_exists => TRUE);  -- TimescaleDB

CREATE TABLE fx_rates (
    base   char(3) NOT NULL,
    quote  char(3) NOT NULL,
    date   date    NOT NULL,
    rate   numeric(20,8) NOT NULL,
    PRIMARY KEY (base, quote, date)
);

CREATE TABLE fundamentals (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id        uuid NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    as_of           date NOT NULL,
    pe              numeric(20,8),
    forward_pe      numeric(20,8),
    peg             numeric(20,8),
    roe             numeric(20,8),
    roic            numeric(20,8),
    debt_equity     numeric(20,8),
    fcf             numeric(20,8),
    payout_ratio    numeric(20,8),
    revenue_growth  numeric(20,8),
    earnings_growth numeric(20,8),
    dividend_growth numeric(20,8),
    eps             numeric(20,8),
    book_value      numeric(20,8),
    raw             jsonb,
    source          text,
    created_at      timestamptz NOT NULL DEFAULT now(),
    UNIQUE (asset_id, as_of, source)
);
CREATE INDEX ix_fundamentals_asof ON fundamentals(asset_id, as_of DESC);

CREATE TABLE dividend_schedule (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id          uuid NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    ex_date           date,
    record_date       date,
    pay_date          date,
    amount_per_share  numeric(20,8) NOT NULL,
    currency          char(3) NOT NULL,
    frequency         text,
    kind              dividend_kind NOT NULL DEFAULT 'CONFIRMED',
    source            text,
    created_at        timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_div_sched_exdate ON dividend_schedule(ex_date);
CREATE INDEX ix_div_sched_paydate ON dividend_schedule(pay_date);

-- ===========================================================================
-- PORTFOLIO & TRANSACTIONS
-- ===========================================================================
CREATE TABLE brokers (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id          uuid REFERENCES users(id) ON DELETE CASCADE,  -- null = system broker
    name             text NOT NULL,
    slug             text NOT NULL UNIQUE,
    country          char(2),
    default_currency char(3),
    parser_key       text,
    created_at       timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE portfolios (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id        uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name           text NOT NULL,
    description    text,
    base_currency  char(3) NOT NULL DEFAULT 'EUR',
    is_default     boolean NOT NULL DEFAULT false,
    created_at     timestamptz NOT NULL DEFAULT now(),
    updated_at     timestamptz NOT NULL DEFAULT now(),
    deleted_at     timestamptz
);
CREATE INDEX ix_portfolios_user ON portfolios(user_id) WHERE deleted_at IS NULL;
CREATE TRIGGER trg_portfolios_updated BEFORE UPDATE ON portfolios
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE import_batches (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id          uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    broker_id        uuid REFERENCES brokers(id) ON DELETE SET NULL,
    portfolio_id     uuid REFERENCES portfolios(id) ON DELETE SET NULL,
    filename         text,
    file_path        text,
    file_type        text,
    status           import_status NOT NULL DEFAULT 'PENDING',
    detected_columns jsonb,
    column_mapping   jsonb,
    row_count        integer NOT NULL DEFAULT 0,
    dup_count        integer NOT NULL DEFAULT 0,
    error            text,
    created_at       timestamptz NOT NULL DEFAULT now(),
    committed_at     timestamptz
);
CREATE INDEX ix_import_batches_user ON import_batches(user_id, created_at DESC);
CREATE INDEX gin_import_mapping ON import_batches USING gin (column_mapping);

CREATE TABLE transactions (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id          uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    portfolio_id     uuid NOT NULL REFERENCES portfolios(id) ON DELETE RESTRICT,
    asset_id         uuid REFERENCES assets(id) ON DELETE RESTRICT,
    broker_id        uuid REFERENCES brokers(id) ON DELETE SET NULL,
    type             transaction_type NOT NULL,
    trade_date       timestamptz NOT NULL,
    settle_date      date,
    quantity         numeric(20,8),
    price            numeric(20,8),
    gross_amount     numeric(20,8) NOT NULL DEFAULT 0,
    fee              numeric(20,8) NOT NULL DEFAULT 0,
    tax              numeric(20,8) NOT NULL DEFAULT 0,
    net_amount       numeric(20,8) NOT NULL DEFAULT 0,
    currency         char(3) NOT NULL DEFAULT 'EUR',
    fx_rate          numeric(20,8) NOT NULL DEFAULT 1,
    split_ratio      numeric(20,8),
    source           transaction_source NOT NULL DEFAULT 'MANUAL',
    external_id      text,
    dedup_hash       text NOT NULL,
    import_batch_id  uuid REFERENCES import_batches(id) ON DELETE SET NULL,
    note             text,
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now(),
    deleted_at       timestamptz,
    CONSTRAINT ux_tx_dedup UNIQUE (user_id, dedup_hash),
    CONSTRAINT ck_tx_trade_requires_asset CHECK (
        type NOT IN ('BUY','SELL','DIVIDEND','STOCK_SPLIT','REVERSE_SPLIT')
        OR asset_id IS NOT NULL
    ),
    CONSTRAINT ck_tx_trade_requires_qty CHECK (
        type NOT IN ('BUY','SELL') OR (quantity IS NOT NULL AND price IS NOT NULL)
    ),
    CONSTRAINT ck_tx_split_ratio CHECK (
        type NOT IN ('STOCK_SPLIT','REVERSE_SPLIT') OR split_ratio IS NOT NULL
    )
);
CREATE INDEX ix_tx_user_date       ON transactions(user_id, trade_date DESC);
CREATE INDEX ix_tx_portfolio_asset ON transactions(portfolio_id, asset_id);
CREATE TRIGGER trg_tx_updated BEFORE UPDATE ON transactions
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE import_rows (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    batch_id        uuid NOT NULL REFERENCES import_batches(id) ON DELETE CASCADE,
    raw             jsonb NOT NULL,
    normalized      jsonb,
    suggested_type  transaction_type,
    status          import_row_status NOT NULL DEFAULT 'NEW',
    dedup_hash      text,
    transaction_id  uuid REFERENCES transactions(id) ON DELETE SET NULL,
    error           text
);
CREATE INDEX ix_import_rows_batch ON import_rows(batch_id);

CREATE TABLE positions (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    portfolio_id    uuid NOT NULL REFERENCES portfolios(id) ON DELETE RESTRICT,
    asset_id        uuid NOT NULL REFERENCES assets(id) ON DELETE RESTRICT,
    quantity        numeric(20,8) NOT NULL DEFAULT 0,
    avg_cost        numeric(20,8) NOT NULL DEFAULT 0,
    total_invested  numeric(20,8) NOT NULL DEFAULT 0,
    realized_pnl    numeric(20,8) NOT NULL DEFAULT 0,
    currency        char(3) NOT NULL DEFAULT 'EUR',
    opened_at       timestamptz,
    updated_at      timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ux_position_pa UNIQUE (portfolio_id, asset_id)
);
CREATE INDEX ix_positions_user ON positions(user_id);
CREATE TRIGGER trg_positions_updated BEFORE UPDATE ON positions
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE portfolio_snapshots (
    portfolio_id    uuid NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
    date            date NOT NULL,
    total_value     numeric(20,8) NOT NULL DEFAULT 0,
    total_cost      numeric(20,8) NOT NULL DEFAULT 0,
    cash            numeric(20,8) NOT NULL DEFAULT 0,
    unrealized_pnl  numeric(20,8) NOT NULL DEFAULT 0,
    day_change      numeric(20,8) NOT NULL DEFAULT 0,
    currency        char(3) NOT NULL DEFAULT 'EUR',
    PRIMARY KEY (portfolio_id, date)
);
-- SELECT create_hypertable('portfolio_snapshots','date', if_not_exists => TRUE);

-- ===========================================================================
-- DIVIDENDS (received)
-- ===========================================================================
CREATE TABLE dividends (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id           uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    portfolio_id      uuid NOT NULL REFERENCES portfolios(id) ON DELETE RESTRICT,
    asset_id          uuid NOT NULL REFERENCES assets(id) ON DELETE RESTRICT,
    transaction_id    uuid REFERENCES transactions(id) ON DELETE SET NULL,
    ex_date           date,
    pay_date          date,
    amount_per_share  numeric(20,8),
    shares            numeric(20,8),
    gross_amount      numeric(20,8) NOT NULL DEFAULT 0,
    withholding_tax   numeric(20,8) NOT NULL DEFAULT 0,   -- foreign source tax
    belgian_rv        numeric(20,8) NOT NULL DEFAULT 0,   -- roerende voorheffing
    net_amount        numeric(20,8) NOT NULL DEFAULT 0,
    currency          char(3) NOT NULL DEFAULT 'EUR',
    source_country    char(2),
    created_at        timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_dividends_user_pay ON dividends(user_id, pay_date);
CREATE INDEX ix_dividends_asset ON dividends(asset_id);

-- ===========================================================================
-- ANALYSIS, VALUATION & AI
-- ===========================================================================
CREATE TABLE asset_scores (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id         uuid NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    as_of            date NOT NULL,
    total_score      numeric(6,2),
    valuation_score  numeric(6,2),
    growth_score     numeric(6,2),
    health_score     numeric(6,2),
    dividend_score   numeric(6,2),
    breakdown        jsonb,
    created_at       timestamptz NOT NULL DEFAULT now(),
    UNIQUE (asset_id, as_of)
);

CREATE TABLE valuations (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id          uuid NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    method            valuation_method NOT NULL,
    fair_value        numeric(20,8),
    current_price     numeric(20,8),
    margin_of_safety  numeric(8,4),
    verdict           valuation_verdict,
    assumptions       jsonb,
    as_of             date NOT NULL,
    created_at        timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_valuations_asset ON valuations(asset_id, as_of DESC);

CREATE TABLE ai_analyses (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id           uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    scope             text NOT NULL,                 -- 'portfolio' | 'position'
    portfolio_id      uuid REFERENCES portfolios(id) ON DELETE CASCADE,
    asset_id          uuid REFERENCES assets(id) ON DELETE SET NULL,
    provider          ai_provider NOT NULL,
    model             text,
    recommendation    recommendation,
    confidence        numeric(6,4),
    risk_score        numeric(6,2),
    strengths         jsonb,
    weaknesses        jsonb,
    opportunities     jsonb,
    threats           jsonb,
    summary           text,
    context_snapshot  jsonb,
    raw_response      jsonb,
    disclaimer        text NOT NULL,
    created_at        timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_ai_user_time ON ai_analyses(user_id, created_at DESC);
CREATE INDEX gin_ai_context ON ai_analyses USING gin (context_snapshot);

-- ===========================================================================
-- FIRE & SCENARIOS
-- ===========================================================================
CREATE TABLE fire_plans (
    id                       uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id                  uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name                     text NOT NULL,
    annual_expenses          numeric(20,8) NOT NULL,
    swr                      numeric(6,4) NOT NULL DEFAULT 0.04,
    expected_return          numeric(6,4) NOT NULL DEFAULT 0.07,
    expected_dividend_growth numeric(6,4) NOT NULL DEFAULT 0.05,
    monthly_contribution     numeric(20,8) NOT NULL DEFAULT 0,
    inflation                numeric(6,4) NOT NULL DEFAULT 0.02,
    targets                  jsonb,   -- {lean, coast, barista, fat}
    fi_date                  date,
    projection               jsonb,
    created_at               timestamptz NOT NULL DEFAULT now(),
    updated_at               timestamptz NOT NULL DEFAULT now()
);
CREATE TRIGGER trg_fire_updated BEFORE UPDATE ON fire_plans
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE scenarios (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    fire_plan_id  uuid REFERENCES fire_plans(id) ON DELETE CASCADE,
    name          text NOT NULL,
    params        jsonb NOT NULL,
    result        jsonb,
    created_at    timestamptz NOT NULL DEFAULT now()
);

-- ===========================================================================
-- WATCHLIST, ALERTS, NOTIFICATIONS
-- ===========================================================================
CREATE TABLE watchlists (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name        text NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_watchlists_user ON watchlists(user_id);

CREATE TABLE watchlist_items (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    watchlist_id      uuid NOT NULL REFERENCES watchlists(id) ON DELETE CASCADE,
    asset_id          uuid NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    target_price      numeric(20,8),
    fair_value_alert  boolean NOT NULL DEFAULT false,
    dividend_alert    boolean NOT NULL DEFAULT false,
    note              text,
    created_at        timestamptz NOT NULL DEFAULT now(),
    UNIQUE (watchlist_id, asset_id)
);

CREATE TABLE alerts (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id           uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    asset_id          uuid REFERENCES assets(id) ON DELETE CASCADE,
    portfolio_id      uuid REFERENCES portfolios(id) ON DELETE CASCADE,
    type              alert_type NOT NULL,
    threshold         jsonb,
    channels          alert_channel[] NOT NULL DEFAULT '{}',
    is_active         boolean NOT NULL DEFAULT true,
    last_triggered_at timestamptz,
    created_at        timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_alerts_active ON alerts(user_id) WHERE is_active;

CREATE TABLE notifications (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    alert_id    uuid REFERENCES alerts(id) ON DELETE SET NULL,
    type        alert_type NOT NULL,
    channel     alert_channel NOT NULL,
    title       text NOT NULL,
    body        text,
    payload     jsonb,
    status      notification_status NOT NULL DEFAULT 'PENDING',
    sent_at     timestamptz,
    read_at     timestamptz,
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_notif_user_status ON notifications(user_id, status);

-- ===========================================================================
-- TAX (BE) & REPORTS
-- ===========================================================================
CREATE TABLE tax_summaries (
    id                       uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id                  uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    year                     integer NOT NULL,
    foreign_dividends_gross  numeric(20,8) NOT NULL DEFAULT 0,
    belgian_dividends_gross  numeric(20,8) NOT NULL DEFAULT 0,
    withholding_tax_foreign  numeric(20,8) NOT NULL DEFAULT 0,
    belgian_rv               numeric(20,8) NOT NULL DEFAULT 0,
    tob_total                numeric(20,8) NOT NULL DEFAULT 0,
    fees_total               numeric(20,8) NOT NULL DEFAULT 0,
    net_dividend_income      numeric(20,8) NOT NULL DEFAULT 0,
    breakdown                jsonb,
    generated_at             timestamptz NOT NULL DEFAULT now(),
    UNIQUE (user_id, year)
);

CREATE TABLE reports (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    type          report_type NOT NULL,
    format        report_format NOT NULL,
    status        report_status NOT NULL DEFAULT 'QUEUED',
    params        jsonb,
    file_path     text,
    file_size     bigint,
    expires_at    timestamptz,
    created_at    timestamptz NOT NULL DEFAULT now(),
    completed_at  timestamptz,
    error         text
);
CREATE INDEX ix_reports_user ON reports(user_id, created_at DESC);

-- ===========================================================================
-- AUDIT trigger (records before/after on financial core tables)
-- ===========================================================================
CREATE OR REPLACE FUNCTION audit_trigger() RETURNS trigger AS $$
DECLARE
    v_user uuid;
BEGIN
    v_user := COALESCE(NEW.user_id, OLD.user_id);
    INSERT INTO audit_log(user_id, action, entity_type, entity_id, before, after)
    VALUES (
        v_user,
        TG_OP,
        TG_TABLE_NAME,
        COALESCE(NEW.id, OLD.id),
        CASE WHEN TG_OP IN ('UPDATE','DELETE') THEN to_jsonb(OLD) ELSE NULL END,
        CASE WHEN TG_OP IN ('INSERT','UPDATE') THEN to_jsonb(NEW) ELSE NULL END
    );
    RETURN COALESCE(NEW, OLD);
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_audit_transactions AFTER INSERT OR UPDATE OR DELETE ON transactions
    FOR EACH ROW EXECUTE FUNCTION audit_trigger();
CREATE TRIGGER trg_audit_positions AFTER INSERT OR UPDATE OR DELETE ON positions
    FOR EACH ROW EXECUTE FUNCTION audit_trigger();
CREATE TRIGGER trg_audit_portfolios AFTER INSERT OR UPDATE OR DELETE ON portfolios
    FOR EACH ROW EXECUTE FUNCTION audit_trigger();

-- ============================================================================
-- End of reference schema.
-- ============================================================================
