# 05 — UX Flows

> Gebruikersreizen (user journeys) voor DivTrack: stap-voor-stap flows met beslissingspunten, edge cases en foutafhandeling. Deze flows koppelen de wireframes (04) aan de API/services (07) en de frontend-navigatie (08). Notatie: `→` stap, `◆` beslissing, `⚠` edge case/fout, `✅` succeseinde.

> ⚠️ Flows met scores/AI/FIRE/fiscaliteit tonen steeds de educatieve disclaimer.

---

## Flow 1 — Onboarding & Authenticatie (M1)

```
Start app
  → Splash (token-check in secure storage)
  ◆ Geldig refresh-token?
     ├─ Ja  → ◆ Biometrie ingeschakeld op device?
     │          ├─ Ja → 👆 biometrische prompt → ✅ Dashboard
     │          └─ Nee → stille token-refresh → ✅ Dashboard
     └─ Nee → Login-scherm
                 ◆ Account?
                    ├─ Nee → Registratie (email, wachtwoord×2)
                    │         → e-mail validatie regels (sterk wachtwoord)
                    │         → POST /auth/register → ✅ → auto-login
                    └─ Ja  → email + wachtwoord → POST /auth/login
                              ◆ 2FA actief?
                                 ├─ Ja → 2FA-code scherm → POST /auth/2fa/verify
                                 │        ⚠ foutieve code → teller +1, melding
                                 │        ⚠ 5× fout → tijdelijke lockout (Redis)
                                 └─ Nee → ✅ tokens ontvangen
                              → ◆ "Biometrie inschakelen?" (eerste keer)
                                   ├─ Ja → koppel device, sla refresh veilig op
                                   └─ Nee → verder
                              → ✅ Dashboard
```
**Edge cases**
- ⚠ Offline bij start → toon laatst gecachte dashboard-snapshot (read-only badge).
- ⚠ Refresh-token verlopen/ingetrokken → terug naar login, vriendelijke melding.
- ⚠ Wachtwoord vergeten → e-mail reset-flow (token, korte TTL).

---

## Flow 2 — Eerste BUX-import (M4) — kritieke happy path

```
Dashboard (leeg) → "Importeer je eerste transacties"
  → Import-wizard Stap 1: kies bron = BUX
  → Stap 2: upload bux_export.csv  (POST /imports  multipart)
       ⚠ verkeerd bestandstype/groter dan limiet → inline fout, opnieuw
  → Server: status PARSING (Celery) — UI toont spinner + "Bestand verwerken…"
  → Stap 3: Kolommapping
       • Auto-detectie toont voorgestelde mapping (Datum→trade_date, ISIN→asset, …)
       ◆ Mapping correct?
          ├─ Ja → "Volgende"
          └─ Nee → gebruiker corrigeert dropdowns → opnieuw normaliseren (preview)
  → Stap 4: Preview
       • Lijst: ✓ nieuw / ⊘ duplicaat / ⚠ ongeldig (per rij reden)
       ◆ Ongeldige rijen?
          ├─ Ja → gebruiker bewerkt of slaat over
          └─ Nee → verder
       → "Commit 110 transacties" (POST /imports/{id}/commit, idempotent)
  → Server: transacties aangemaakt → posities herberekend → koersen opgehaald
  → ✅ "110 transacties geïmporteerd. 12 duplicaten overgeslagen."
  → Redirect → Portfolio met gevulde posities
```
**Edge cases**
- ⚠ Onbekende ISIN/ticker → asset-resolutie faalt → rij gemarkeerd "asset onbekend", gebruiker kan handmatig koppelen of overslaan.
- ⚠ Vreemde valuta zonder FX op datum → systeem haalt historische FX; faalt dat → rij "FX ontbreekt", overslaan/handmatig.
- ⚠ Dubbele commit (netwerk-retry) → idempotency-key voorkomt dubbele transacties.
- ⚠ Parser-fout (corrupt bestand) → batch status FAILED met leesbare reden, ruw bestand bewaard voor support.

---

## Flow 3 — Handmatige transactie toevoegen (M3)

```
Portfolio → [+ Transactie]
  → Formulier: type [BUY ▾]
       ◆ type bepaalt zichtbare velden:
          BUY/SELL    → asset, aantal, prijs, valuta, fee, taks, datum, broker
          DIVIDEND    → asset, bedrag/aandeel of totaal, bronbelasting, datum
          DEPOSIT/WD  → bedrag, valuta, datum
          SPLIT       → asset, ratio, datum
  → asset-zoekveld (typeahead → /market/search)
       ⚠ asset niet gevonden → "Asset aanmaken" mini-dialoog (ticker/ISIN/class)
  → live berekening van net_amount (gross − fee − tax)
  → Opslaan (POST /transactions)
       → server berekent dedup_hash; ⚠ duplicaat → waarschuwing "lijkt al te bestaan"
       → positie herberekend (FIFO), realized P/L bij SELL
  → ✅ terug naar lijst, nieuwe rij gemarkeerd
```
**Edge cases**
- ⚠ SELL meer dan in bezit → validatiefout (negatieve positie geblokkeerd).
- ⚠ Datum in toekomst → geweigerd.
- ⚠ Correctie nodig → bewerken maakt audit-entry (before/after), geen stille mutatie.

---

## Flow 4 — Dividenden opvolgen (M5/M6)

```
Dividend Dashboard
  → toont jaarinkomen, per-maand-bars, YoC, CAGR (uit dividends + schedule)
  → "Verwachte dividenden" toggle
       ◆ aan → projecteert komende 12m uit historiek (gelabeld "schatting")
  → tik op maand-bar → detaillijst (welke assets, bedragen, betaaldatums)
Dividend Kalender
  → maandweergave; filters (portef./type/verwacht)
  → tik op datum → events (ex-div/record/betaal) + verwacht bedrag
  ◆ ex-div nadert (≤ N dagen) én alert aan → notificatie ingepland (Flow 8)
```
**Edge cases**
- ⚠ Geen dividendhistoriek → "Onvoldoende data voor projectie" i.p.v. €0.
- ⚠ Dividendverlaging gedetecteerd (lager dan vorig) → markeer in historiek (informatief).

---

## Flow 5 — Aandelenanalyse, score & waardering (M8/M9)

```
Positie-detail → tab [Analyse]
  → service haalt fundamentals (cache→provider) → berekent score 0–100
       ⚠ ontbrekende ratio's → subscore met "n.b." en lagere weging, niet 0
  → tab [Waardering]
       → DCF + DDM + Multiples berekend met default-aannames
       ◆ gebruiker past aannames aan (groei, discount rate, terminal)
            → herberekening live → verdict (onder/correct/over)
  → "Aannames tonen" → transparante uitleg per model
  → disclaimer steeds zichtbaar
```
**Edge cases**
- ⚠ Asset = ETF/Cash → ratio-analyse beperkt/niet van toepassing → toon passende boodschap.
- ⚠ Negatieve FCF/earnings → DCF/DDM niet betrouwbaar → model gemarkeerd "onbetrouwbaar".

---

## Flow 6 — AI-analyse & Koop/Houd/Verkoop (M12/M13)

```
AI Analyst → kies provider [Claude/OpenAI/Ollama]
  ◆ provider vereist API-key (OpenAI/Claude) en niet ingesteld?
     └─ ⚠ prompt "stel API-key in" → Settings → terug
  → [Analyseer portefeuille]
  → server bouwt deterministische context (allocaties, ratio's, dividend, risico)
       (LLM rekent géén kerncijfers — die komen uit domeinlaag)
  → LLM-call (async) → UI "AI denkt na…" (streaming indien mogelijk)
       ⚠ provider down/timeout → retry → fallback-provider → anders nette fout
       ⚠ ongeldige JSON van model → 1× herprompten met schema → anders fout
  → gevalideerde output → samenvatting + SWOT + risico/concentratie
  → opslaan als ai_analyses (audit) + disclaimer
Per positie → [BHS] → zelfde pijplijn, scope=position
  → label Strong Buy…Sell + confidence + risico + SWOT
```
**Privacy**
- ◆ Ollama gekozen → context blijft lokaal/op eigen server, niets naar externe API.

---

## Flow 7 — FIRE plannen & scenario's (M10/M11)

```
FIRE → vul/wijzig: jaarl. uitgaven, SWR, maandinleg, verwacht rendement/inflatie
  → POST /fire/plan → server berekent Lean/Coast/Barista/Fat doelen + FI-datum
  → projectiegrafiek (P10/P50/P90)
  → Scenario toevoegen:
       kies type [Crash −X% | Inflatie | Extra inleg | Div −X% | Vervroegd pensioen]
       → POST /scenarios → result naast basis getoond (vergelijk)
  ◆ meerdere scenario's → overlay in grafiek + tabel met verschillen
  → disclaimer: projecties, geen garanties
```
**Edge cases**
- ⚠ Onrealistische input (SWR 0%, negatieve uitgaven) → validatie + uitleg.
- ⚠ FI al bereikt → toon "Gefeliciteerd-staat" i.p.v. datum in verleden.

---

## Flow 8 — Alerts & notificaties (M15/M16)

```
Instellen
  Watchlist-item of positie → "Alert toevoegen"
     → type [Koersdoel | Fair value | Ex-div | Risico | Koerswijziging | Over/onder]
     → drempel + kanalen [Push/Telegram/Email]
     → POST /alerts
Triggeren (systeem, Celery Beat)
  → periodieke evaluatie van actieve alerts t.o.v. verse marktdata
     ◆ voorwaarde voldaan én buiten stille uren?
        ├─ Ja → notificatie aangemaakt → verzonden via kanaal/kanalen
        │        ⚠ kanaal faalt (bv. Telegram) → retry/backoff → status FAILED
        │        → last_triggered_at gezet (debounce, geen spam)
        └─ Nee/stille uren → uitstellen tot venster open
  → in-app notificatiecentrum toont historiek (gelezen/ongelezen)
```

---

## Flow 9 — Belgisch fiscaal rapport exporteren (M17/M18)

```
Belastingoverzicht → kies jaar
  → GET /tax/be/report?year=2025 → aggregatie (RV, bronbelasting, TOB, kosten, div)
  → scherm toont totalen + detail per positie/land
  → [Export PDF] → POST /reports (type=TAX, format=PDF)
       → status QUEUED → GENERATING (Celery) → READY
       → download via beveiligde, tijdelijke link
  → prominente disclaimer: informatief/educatief, geen fiscaal advies
```
**Edge cases**
- ⚠ Geen transacties in jaar → leeg-maar-geldig rapport met nul-totalen.
- ⚠ Ontbrekende bronland-info → markeer "land onbekend", neem op in detail.

---

## Flow 10 — Rapporten & export algemeen (M18)

```
Elke module → [Export ▾] [PDF | CSV | Excel | JSON]
  → POST /reports {type, format, params}
  → async generatie → notificatie "rapport klaar"
  → Downloads-overzicht (verloopt na expires_at)
```

---

## Transversale UX-principes

| Principe | Toepassing |
|----------|------------|
| **Optimistic UI** | Lokale acties (transactie toevoegen) tonen direct, rollback bij serverfout. |
| **Lege staten** | Elk leeg scherm heeft een duidelijke call-to-action (importeer/voeg toe). |
| **Foutcommunicatie** | Nooit stacktraces; korte, menselijke boodschap + herstelactie. |
| **Laadstaten** | Skeletons voor lijsten/grafieken; spinners enkel voor korte acties. |
| **Bevestiging destructief** | Verwijderen/portfolio wissen vraagt expliciete bevestiging. |
| **Toegankelijkheid** | Voldoende contrast, schaalbare tekst, semantische labels, toetsenbordnavigatie (desktop). |
| **Disclaimer-consistentie** | Educatieve strip op alle analyse/AI/FIRE/fiscale schermen en in elk rapport. |
| **Offline-tolerantie** | Read-only cache wanneer geen netwerk; schrijfacties in wachtrij of geblokkeerd met uitleg. |

---

*Einde deliverable 5 — UX flows. Stuur `VERDER` voor deliverable 6: Mappenstructuur.*
