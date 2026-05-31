# 11 — AI Architectuur

> Ontwerp van de AI-engine van DivTrack (M12 AI Portfolio Analyst, M13 Koop/Houd/Verkoop). Kernprincipe: **het domein rekent, de LLM interpreteert.**

> ⚠️ AI-output is **uitsluitend educatief/informatief**, kan fouten bevatten en is **geen** financieel advies. Elke AI-respons draagt verplicht een disclaimer (BR9).

---

## 1. Ontwerpprincipe: domein rekent, LLM interpreteert

De LLM berekent **nooit** financiële kerncijfers. Allocaties, ratio's, scores, risico en waardering worden deterministisch berekend door de domeinlaag (`app/domain/services/*`). De LLM krijgt die **vooraf berekende context** en doet enkel wat taalmodellen goed kunnen: **interpreteren, verbanden leggen en verwoorden** (risico's, concentratie, kansen, SWOT).

Voordelen:
- **Geen numerieke hallucinatie** — cijfers zijn auditeerbaar en reproduceerbaar.
- **Determinisme** — dezelfde portefeuille levert dezelfde context op.
- **Provider-onafhankelijk** — de kwaliteit van de cijfers hangt niet af van het model.

```
┌──────────────────────────────────────────────────────────────────┐
│  Portfolio / Position data (DB)                                    │
└───────────────┬───────────────────────────────────────────────────┘
                │  domain services (pnl, scoring, valuation, risk, dividends)
                ▼
┌──────────────────────────────────────────────────────────────────┐
│  build_*_context()  →  DETERMINISTISCHE CONTEXTBUNDEL (JSON)       │
│  allocaties · HHI-concentratie · ratio's · score 0-100 · risico    │
└───────────────┬───────────────────────────────────────────────────┘
                │  AIAnalysisService
                ▼
┌──────────────────────────────────────────────────────────────────┐
│  LLMProvider.complete(json_mode)  ── OpenAI │ Claude │ Ollama      │
└───────────────┬───────────────────────────────────────────────────┘
                │  validate (Pydantic) → repair-retry → fallback
                ▼
┌──────────────────────────────────────────────────────────────────┐
│  Gevalideerde JSON + disclaimer  →  persist ai_analyses (audit)    │
└──────────────────────────────────────────────────────────────────┘
```

---

## 2. Componenten

| Component | Bestand | Rol |
|-----------|---------|-----|
| `LLMProvider` (port) | `domain/ports/llm.py` | Interface: `complete(messages, json_mode, …)` |
| OpenAI adapter | `infrastructure/ai/openai_provider.py` | Chat Completions, `response_format=json_object` |
| Claude adapter | `infrastructure/ai/claude_provider.py` | Messages API, system+JSON-instructie |
| Ollama adapter | `infrastructure/ai/ollama_provider.py` | Lokaal, `/api/chat`, `format=json` (privacy) |
| Factory | `infrastructure/ai/__init__.py` | Kiest provider o.b.v. user-settings/request |
| Context builders | `application/services/ai_context.py` | Deterministische context (domein) |
| Analysis service | `application/services/ai_analysis.py` | Prompt, validatie, retry, fallback, disclaimer |
| API | `api/v1/routers/ai.py` | `POST /ai/analyze/portfolio`, `/ai/analyze/position` |

---

## 3. Contextbundels (deterministisch)

### Portefeuille (M12)
- Totaalwaarde, invest., gerealiseerde/ongerealiseerde W/V, #posities
- Allocatie per asset class / sector / land (gewichten 0–1)
- Top-5 holdings met gewicht
- **Concentratie**: Herfindahl-Hirschman index (`domain/services/risk.concentration_hhi`)

### Positie (M13)
- Aantal, gem. kost, koers, marktwaarde, ongerealiseerde W/V, portefeuillegewicht
- **Kwaliteitsscore 0–100** + subscores (`domain/services/scoring.score_asset`)
- Ratio's: P/E, Fwd P/E, PEG, ROE, ROIC, D/E, payout, groei (omzet/winst/dividend)

Ontbrekende data wordt expliciet als `null`/`"n/a"` doorgegeven — nooit als 0 (FR8.3).

---

## 4. Betrouwbaarheid: validatie, retry, fallback

De `AIAnalysisService` garandeert dat een request **nooit faalt** door modelgedrag:

1. **JSON-extractie** — verwijdert code-fences (```​json … ```), pakt het eerste `{…}`-object.
2. **Pydantic-validatie** — `PortfolioAnalysis` / `PositionAnalysis` schema's.
3. **Repair-retry** — bij ongeldige JSON wordt het model één keer gevraagd de JSON te corrigeren.
4. **Veilige fallback** — blijft het ongeldig, dan worden veilige defaults teruggegeven (met disclaimer).
5. **Disclaimer** — wordt **altijd** geïnjecteerd, ongeacht modeloutput.

Provider-fouten (timeout/down) → `ExternalServiceError` (HTTP 502) of, waar zinvol, fallback-provider. (Unit tests dekken: geldige JSON, repair-retry, persistente garbage → fallback, code-fence.)

---

## 5. Uitvoerschema's

**Portefeuille**
```json
{ "summary": "…", "risk_score": 0-100, "concentration_note": "…",
  "strengths": ["…"], "weaknesses": ["…"], "opportunities": ["…"], "threats": ["…"],
  "disclaimer": "Informatief en educatief — geen advies." }
```

**Positie (Koop/Houd/Verkoop)**
```json
{ "recommendation": "STRONG_BUY|BUY|HOLD|REDUCE|SELL",
  "confidence": 0-1, "risk_score": 0-100, "summary": "…",
  "strengths": [...], "weaknesses": [...], "opportunities": [...], "threats": [...],
  "disclaimer": "…" }
```

---

## 6. Privacy & providerkeuze

- **Standaard: Ollama (lokaal)** — portefeuilledata verlaat de eigen server niet (FR12.3).
- OpenAI/Claude vereisen een API-sleutel die de gebruiker in Settings opgeeft; sleutels worden **versleuteld** opgeslagen (`user_settings.provider_keys`, app-level AES).
- De gebruiker kiest de provider per request of via voorkeursinstelling.

---

## 7. Auditeerbaarheid

Elke analyse wordt opgeslagen in `ai_analyses` met: provider, model, contextsnapshot, ruwe respons, gevalideerde velden, confidence/risk en disclaimer. Zo is elke uitspraak herleidbaar tot de exacte input.

---

## 8. Prompt-governance

- Systeemprompt legt expliciet op: geen advies, niets herberekenen, enkel interpreteren, altijd JSON, geen stellige garanties.
- Temperatuur laag (0.2) voor consistente, conservatieve output.
- Toekomstige uitbreiding: prompt-versies bijhouden en A/B-evalueren; rate-limiting per gebruiker op AI-endpoints.

---

*Einde deliverable 11 — AI architectuur. De rapportgenerator (deliverable 12), tests (13), Docker (14), deployment (15) en gebruikershandleiding (16) volgen; backendmodules (dividend/FIRE/tax/notify/reports/workers) worden verder afgewerkt in deliverable 7.*
