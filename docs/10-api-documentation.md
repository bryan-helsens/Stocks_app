# 10 — API Documentatie

> REST-API van DivTrack (FastAPI). Basis-URL: `http://<host>:8000`, prefix `/api/v1`.
> Interactieve, altijd-actuele documentatie: **`/docs`** (Swagger UI) en **`/redoc`**. Het OpenAPI-schema staat op `/api/v1/openapi.json`.

> ⚠️ Analyse-, AI-, FIRE- en fiscale endpoints leveren **uitsluitend educatieve/informatieve** output. Geen financieel, fiscaal of juridisch advies.

---

## 1. Conventies

- **Formaat:** JSON in en uit (behalve uploads = `multipart/form-data`, rapport-download = bestand).
- **Geld:** als string verzonden/ontvangen (Decimal-precisie, bv. `"1234.56000000"`).
- **Tijd:** ISO-8601 UTC (`2025-03-04T10:00:00Z`).
- **Auth:** `Authorization: Bearer <access_token>` op alle endpoints behalve registratie/login/refresh.
- **Foutformaat (uniform):**
  ```json
  { "error": { "code": "not_found", "message": "Portfolio not found.", "details": {} } }
  ```
- **Statuscodes:** `200` ok · `201` aangemaakt · `401` niet geauthenticeerd · `403` geen toegang · `404` niet gevonden · `409` conflict (duplicaat) · `422` validatiefout · `429` rate-limited · `502` externe provider.

---

## 2. Authenticatie & accounts (`/auth`)

| Methode | Pad | Auth | Beschrijving |
|--------|-----|------|--------------|
| POST | `/auth/register` | — | Account aanmaken |
| POST | `/auth/login` | — | Inloggen (kan 2FA-challenge teruggeven) |
| POST | `/auth/2fa/verify` | — | 2FA-code verifiëren → tokens |
| POST | `/auth/refresh` | — | Access-token vernieuwen via refresh-token |
| GET | `/auth/me` | ✓ | Huidige gebruiker |
| POST | `/auth/2fa/setup` | ✓ | TOTP-secret + otpauth-URI (QR) |
| POST | `/auth/2fa/confirm` | ✓ | 2FA activeren met code |
| POST | `/auth/devices` | ✓ | Device koppelen (biometrie) |

**Voorbeeld — registreren**
```http
POST /api/v1/auth/register
{ "email": "jij@example.com", "password": "supersecret1", "full_name": "Jij" }
→ 201 { "id": "…", "email": "jij@example.com", "totp_enabled": false, … }
```

**Voorbeeld — inloggen (zonder 2FA)**
```http
POST /api/v1/auth/login
{ "email": "jij@example.com", "password": "supersecret1" }
→ 200 {
  "requires_2fa": false,
  "user_id": "…",
  "tokens": { "access_token": "…", "refresh_token": "…", "token_type": "bearer" }
}
```
Bij actieve 2FA: `requires_2fa: true`, `tokens: null` → vervolg met `/auth/2fa/verify`.

---

## 3. Portefeuilles & posities (`/portfolios`)

| Methode | Pad | Beschrijving |
|--------|-----|--------------|
| POST | `/portfolios` | Portefeuille aanmaken |
| GET | `/portfolios` | Lijst van portefeuilles |
| GET | `/portfolios/{id}/summary` | Waardering + holdings (live koersen) |

**Summary-respons (verkort)**
```json
{
  "portfolio_id": "…", "name": "BUX", "base_currency": "EUR",
  "total_value": "14238.05", "total_invested": "12000.00",
  "total_unrealized": "2238.05", "realized_pnl": "650.00",
  "holdings": [
    { "asset": { "ticker": "AAPL", "name": "Apple", "asset_class": "STOCK", "currency": "USD" },
      "quantity": "6.00000000", "avg_cost": "120.00", "total_invested": "720.00",
      "realized_pnl": "200.00", "price": "172.30", "market_value": "1033.80",
      "unrealized_pnl": "313.80", "unrealized_pct": "0.4358" }
  ]
}
```

---

## 4. Transacties (`/transactions`)

| Methode | Pad | Beschrijving |
|--------|-----|--------------|
| POST | `/transactions` | Transactie toevoegen (positie wordt FIFO-herberekend) |
| DELETE | `/transactions/{id}` | Soft-delete + positie herberekend |

**Body** (types: `BUY, SELL, DIVIDEND, FEE, TAX, DEPOSIT, WITHDRAWAL, STOCK_SPLIT, REVERSE_SPLIT`)
```json
{
  "portfolio_id": "…", "type": "BUY", "trade_date": "2025-01-02T10:00:00Z",
  "currency": "EUR", "asset_id": "…", "quantity": "10", "price": "100",
  "fee": "0.5", "tax": "0", "fx_rate": "1"
}
```
Duplicaat (zelfde dedup-hash) → `409 conflict`. Zet `"allow_duplicate": true` om te forceren.

---

## 5. Broker-import (`/imports`)

| Methode | Pad | Beschrijving |
|--------|-----|--------------|
| GET | `/imports/parsers` | Beschikbare parsers (`bux`, `csv_generic`, `excel`, `pdf`) |
| POST | `/imports` | Upload (`multipart`): `portfolio_id`, `file`, optioneel `parser_key` → preview |
| POST | `/imports/{batch_id}/commit` | Drafts → transacties (idempotent) |

**Preview-respons**
```json
{
  "batch_id": "…", "status": "PREVIEWED", "row_count": 465,
  "new_count": 388, "dup_count": 0, "invalid_count": 8,
  "column_mapping": { "_parser": "bux" },
  "rows": [ { "type": "BUY", "trade_date": "2022-02-02T17:14:20", "ticker": null,
              "isin": "US0378331005", "quantity": "0.161834", "price": "174.0",
              "gross_amount": "28.16", "currency": "USD", "status": "NEW" }, … ]
}
```

---

## 6. Dividenden (`/dividends`)

| Methode | Pad | Beschrijving |
|--------|-----|--------------|
| GET | `/dividends/dashboard` | Totaal, per maand/jaar/sector/land, YoC, CAGR, 12m-projectie |

---

## 7. FIRE & scenario's (`/fire`)

| Methode | Pad | Beschrijving |
|--------|-----|--------------|
| POST | `/fire/plan` | Lean/Coast/Barista/Fat doelen + FI-datum |
| POST | `/fire/scenario` | What-if simulatie (crash/inflatie/extra inleg/dividendwijziging) |
| POST | `/fire/monte-carlo` | P10/P50/P90 bandbreedte |

**`/fire/plan` body → respons (verkort)**
```json
{ "annual_expenses": "30000", "swr": "0.04", "current_value": "50000",
  "monthly_contribution": "800", "expected_return": "0.07" }
→ { "targets": { "full_number": "750000", "lean": "525000", "coast": "…",
                 "barista": "375000", "fat": "1500000" },
    "fi_date": "2034-06-01", "years_to_fi": "8.4",
    "projection": [ {"year":0,"value":"50000"}, … ],
    "disclaimer": "Informatief en educatief — …" }
```

---

## 8. AI-analyse (`/ai`)

| Methode | Pad | Beschrijving |
|--------|-----|--------------|
| POST | `/ai/analyze/portfolio` | Portefeuille-analyse (samenvatting + SWOT + risico) |
| POST | `/ai/analyze/position` | Koop/Houd/Verkoop-signaal + confidence + SWOT |

**Body:** `{ "portfolio_id": "…", "provider": "OLLAMA" }` (`OLLAMA`=lokaal, of `OPENAI`/`CLAUDE`).
Output bevat altijd een `disclaimer`. Provider down/timeout → `502`.

---

## 9. Belgische fiscaliteit (`/tax/be`)

| Methode | Pad | Beschrijving |
|--------|-----|--------------|
| GET | `/tax/be/report?year=2025` | RV (30%), buitenlandse bronbelasting, TOB, kosten, netto dividendinkomen |

Output bevat per-dividend detail + verplichte disclaimer (informatief, geen fiscaal advies).

---

## 10. Rapporten (`/reports`)

| Methode | Pad | Beschrijving |
|--------|-----|--------------|
| GET | `/reports/generate?type=…&format=…` | Genereert & downloadt een rapport |

- `type`: `PORTFOLIO, DIVIDEND, ANNUAL, TAX, FIRE, RISK, ALLOCATION, AI`
- `format`: `PDF, CSV, EXCEL, JSON`
- Optioneel: `portfolio_id`, `year`. Response = bestand (`Content-Disposition: attachment`).

---

## 11. Systeem

| Methode | Pad | Beschrijving |
|--------|-----|--------------|
| GET | `/api/v1/health` | Liveness (geen DB) |
| GET | `/api/v1/ready` | Readiness (verifieert DB) |
| GET | `/` | Root + disclaimer |

---

## 12. Rate limiting & beveiliging

- Auth-endpoints strenger gelimiteerd (`AUTH_RATE_LIMIT_PER_MINUTE`), overige via `RATE_LIMIT_PER_MINUTE`.
- Access-tokens ~15 min, refresh-tokens roterend ~7 dagen.
- Elke financiële schrijfactie wordt in `audit_log` vastgelegd.
- Gevoelige velden (2FA-secret, provider-API-keys) encrypted at-rest.

---

*Einde deliverable 10 — API-documentatie. Volledige, uitvoerbare referentie: `/docs` (Swagger). Volgende: deliverable 15 (deployment) en 16 (gebruikershandleiding).*
