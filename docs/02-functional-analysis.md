# 02 — Functionele Analyse

> Functionele specificatie van DivTrack: actoren, modules, functionele requirements (FR), user stories, acceptatiecriteria en business rules. Vormt de brug tussen de architectuur (01) en het databaseontwerp (03).

> ⚠️ Alle functies leveren **uitsluitend educatieve/informatieve** output. Geen financieel, fiscaal of juridisch advies. Voorspellingen zijn nooit garanties.

---

## 1. Actoren

| Actor | Beschrijving |
|-------|--------------|
| **Investeerder (User)** | Primaire gebruiker: beheert portefeuilles, importeert, analyseert, plant FIRE, genereert rapporten. |
| **Admin** | Beheer van gebruikers, providers, systeeminstellingen, feature flags. |
| **Systeem (Scheduler)** | Geautomatiseerde processen: koers-refresh, dividenddetectie, kalender-sync, notificaties. |
| **Externe providers** | Marktdata-, fundamentals-, AI- en notificatie-diensten (geen mens). |

---

## 2. Moduleoverzicht (functionele decompositie)

| # | Module | Kernverantwoordelijkheid |
|---|--------|--------------------------|
| M1 | **Auth & Security** | Registratie, login, JWT, 2FA, biometrie, devices, audit |
| M2 | **Portfolio Management** | Portefeuilles, posities, multi-asset, waardering |
| M3 | **Transactiemanagement** | Buy/Sell/Dividend/Fee/Tax/Deposit/Withdrawal/Split, audit trail |
| M4 | **Broker Import** | BUX/CSV/Excel/PDF/handmatig, auto-classificatie, dedup |
| M5 | **Dividend Management** | Dividend-tracking, YoC, CAGR, veiligheid, voorspelling |
| M6 | **Dividend Kalender** | Ex-div/record/betaaldatums, verwachte dividenden, filters |
| M7 | **Dashboard & Analytics** | Waarde, P/L (dag/week/maand/jaar), allocaties, risico, FIRE |
| M8 | **Aandelenanalyse** | Ratio's (P/E, PEG, ROE, ROIC, D/E, FCF…), score 0–100 |
| M9 | **Waardering** | Fair value, DCF, DDM, multiples, margin of safety |
| M10 | **FIRE Module** | Lean/Coast/Barista/Fat FIRE, FI-datum, projecties |
| M11 | **Scenario Planner** | Simulaties: extra inleg, dividendwijziging, crash, inflatie |
| M12 | **AI Portfolio Analyst** | Risico-/concentratie-/waarderingsanalyse, kansen |
| M13 | **Koop/Houd/Verkoop** | Geautomatiseerd rapport met confidence & SWOT |
| M14 | **Portfolio Health Score** | Score 0–100 + verbetervoorstellen |
| M15 | **Watchlist** | Onbeperkte lijsten, koersdoelen, notities, alerts |
| M16 | **Notificaties** | Push/Telegram/email triggers |
| M17 | **Belgische Fiscaliteit** | RV, bronbelasting, TOB, fiscale overzichten |
| M18 | **Rapporten & Export** | PDF/CSV/Excel/JSON van alle modules |
| M19 | **Instellingen & Profiel** | Voorkeuren, valuta, thema, providers, privacy |

---

## 3. Functionele requirements per module

### M1 — Auth & Security
- **FR1.1** Gebruiker registreert met e-mail + sterk wachtwoord (bcrypt-hash).
- **FR1.2** Login levert JWT access (15 min) + refresh (roterend, 7 dagen).
- **FR1.3** 2FA via TOTP: activeren met QR + verificatie; vereist bij login indien actief.
- **FR1.4** Biometrische login op device (Face/Touch/Windows Hello) ontgrendelt opgeslagen refresh-token.
- **FR1.5** Device-management: lijst van actieve devices, intrekken mogelijk.
- **FR1.6** Audit log registreert auth-events en alle financiële schrijfacties.
- **FR1.7** Rate limiting op auth-endpoints; lockout na herhaalde mislukte pogingen.

### M2 — Portfolio Management
- **FR2.1** Meerdere portefeuilles per gebruiker (bv. "BUX", "Pensioen", "Crypto").
- **FR2.2** Ondersteunde asset classes: Aandeel, ETF, REIT, Obligatie, Cash, Crypto (optioneel).
- **FR2.3** Per positie afgeleid: aantal, gem. aankoopprijs, totale investering, huidige koers, marktwaarde, onrealiseerde W/V, gerealiseerde W/V, dividendrendement, Yield on Cost, dividendhistoriek, historische prestatie.
- **FR2.4** Positiewaarden worden **berekend uit transacties** (single source of truth), niet handmatig ingevoerd.
- **FR2.5** Multi-currency: posities in vreemde valuta omgerekend naar basisvaluta (EUR) met FX op transactie- en waarderingsdatum.

### M3 — Transactiemanagement
- **FR3.1** Transactietypes: `BUY, SELL, DIVIDEND, FEE, TAX, DEPOSIT, WITHDRAWAL, STOCK_SPLIT, REVERSE_SPLIT`.
- **FR3.2** Elke transactie: datum, asset (indien van toepassing), aantal, prijs, valuta, FX-koers, fees, taks, broker, bron (import/handmatig), notitie.
- **FR3.3** Splits passen historische aantallen/prijzen consistent aan (ratio).
- **FR3.4** Volledige, onveranderlijke **audit trail**: create/update/delete worden gelogd (wijzigingen via correctie-entries, geen stille mutatie).
- **FR3.5** Realized P/L berekend volgens **FIFO** (configureerbaar; FIFO default).

### M4 — Broker Import (generiek framework)
- **FR4.1** Upload van BUX, CSV, Excel (xlsx), PDF; plus handmatige invoer.
- **FR4.2** **Automatische kolomherkenning** (header-mapping met synoniemen + heuristiek).
- **FR4.3** Automatische herkenning van: aankopen, verkopen, dividenden, belastingen, fees, wisselkoersen.
- **FR4.4** **Duplicaatdetectie** via stabiele hash (broker + externe-id + datum + ticker + bedrag + type).
- **FR4.5** **Preview & bevestiging:** gebruiker ziet genormaliseerde drafts, kan mapping corrigeren vóór commit.
- **FR4.6** **Pluggable**: nieuwe broker = nieuwe parser-klasse, zonder kernwijziging.
- **FR4.7** Import-batches bewaard met status (`pending`, `previewed`, `committed`, `failed`) en herhaalbaar.

### M5 — Dividend Management
- **FR5.1** Per positie: dividend/aandeel, jaarlijks dividend, ex-dividend datum, betaaldatum, dividendgroei, historiek, veiligheidsindicatie.
- **FR5.2** Berekeningen: Yield, Yield on Cost, Dividend CAGR (1/3/5 jaar), totaal ontvangen dividenden, **toekomstige (verwachte) dividenden**.
- **FR5.3** Dividendveiligheid: heuristische score op basis van payout ratio, FCF-dekking, groeistabiliteit, schuld.
- **FR5.4** Verwachte dividenden ⇒ duidelijk gelabeld als *schatting*, geen garantie.

### M6 — Dividend Kalender
- **FR6.1** Kalenderweergave met ex-dividend, record- en betaaldatums.
- **FR6.2** Verwachte (geprojecteerde) dividenden op basis van historiek.
- **FR6.3** Filters: per portefeuille, per asset, per maand, per type (bevestigd/verwacht).

### M7 — Dashboard & Analytics
- **FR7.1** Totale portefeuillewaarde + cash.
- **FR7.2** P/L over dag / week / maand / jaar (en sinds inceptie, TWR & geldgewogen).
- **FR7.3** Allocaties: asset class, sector, land, valuta, dividend-bron.
- **FR7.4** Risicoscore (volatiliteit, concentratie, correlatie).
- **FR7.5** FIRE-voortgangsindicator.
- **FR7.6** Dividendvoorspelling (komende 12 maanden).
- **FR7.7** Interactieve grafieken; data uit gecachte aggregaties (< 500 ms).

### M8 — Aandelenanalyse
- **FR8.1** Per positie/asset: P/E, Forward P/E, PEG, ROE, ROIC, Debt/Equity, FCF, Payout Ratio, Revenue Growth, Earnings Growth, Dividend Growth.
- **FR8.2** **Kwaliteitsscore 0–100** met gewogen subscores (waardering, groei, gezondheid, dividend).
- **FR8.3** Ontbrekende data wordt expliciet als "n.b." getoond, niet als 0.

### M9 — Waardering
- **FR9.1** Fair value via: DCF (FCF-projectie + terminal value), DDM (Gordon growth), Multiple Comparison (peer P/E).
- **FR9.2** Margin of Safety = (fair value − koers) / fair value.
- **FR9.3** Classificatie: **Ondergewaardeerd / Correct gewaardeerd / Overgewaardeerd** met aannames transparant getoond.

### M10 — FIRE Module
- **FR10.1** Berekent Lean / Coast / Barista / Fat FIRE-doelbedragen (instelbare jaarlijkse uitgaven & SWR).
- **FR10.2** Financiële-onafhankelijkheidsdatum o.b.v. huidige waarde, inleg, verwacht rendement & dividend.
- **FR10.3** Projecties: verwachte portefeuillewaarde, dividendinkomen, jaarlijkse passieve inkomsten.
- **FR10.4** Scenarioanalyses koppelbaar (M11).

### M11 — Scenario Planner
- **FR11.1** Simuleer: extra periodieke investeringen, hogere dividenden, dividendverlagingen, marktcrash (%-drop), inflatie, vervroegd pensioen.
- **FR11.2** Vergelijk meerdere scenario's naast elkaar (grafiek + tabel).
- **FR11.3** Monte-Carlo-optie voor bandbreedte (P10/P50/P90) — als illustratie, niet als garantie.

### M12 — AI Portfolio Analyst
- **FR12.1** Analyseert volledige portefeuille met deterministische context (allocaties, ratio's, dividendkwaliteit, risico, macro-indicatoren).
- **FR12.2** Identificeert: concentratierisico, over-/onderwaardering, dividendkansen, waarschuwingen, kansen.
- **FR12.3** Keuze van provider (OpenAI/Claude/Ollama); Ollama = lokaal/privacy.
- **FR12.4** Output gestructureerd + gevalideerd; verplichte disclaimer.

### M13 — Koop/Houd/Verkoop-rapport
- **FR13.1** Per positie/asset automatisch rapport.
- **FR13.2** Analyseert waardering, fundamenten, dividendkwaliteit, dividendgroei, financiële gezondheid, schulden, sectorpositie, technische trend, risico.
- **FR13.3** Label: `STRONG_BUY / BUY / HOLD / REDUCE / SELL` met **Confidence Score** en **Risicoscore**.
- **FR13.4** Toont sterke/zwakke punten, kansen, bedreigingen (SWOT).
- **FR13.5** Geformuleerd als informatie ("signalen wijzen op…"), nooit als instructie.

### M14 — Portfolio Health Score
- **FR14.1** Score 0–100 o.b.v.: diversificatie, dividendkwaliteit, sectorverdeling, landverdeling, risico, concentratie, cashpositie.
- **FR14.2** Concrete **verbetervoorstellen** (educatief).

### M15 — Watchlist
- **FR15.1** Onbeperkt aantal watchlists.
- **FR15.2** Per item: koersdoel, notities, dividendalert, fair-value-alert.
- **FR15.3** Watchlist-items tonen live koers en afgeleide signalen.

### M16 — Notificaties
- **FR16.1** Kanalen: push, Telegram, email (per kanaal in-/uitschakelbaar).
- **FR16.2** Triggers: dividend ontvangen, ex-dividend datum nadert, koersdoel bereikt, risicowaarschuwing, grote koerswijziging (%-drempel), over-/onderwaardering.
- **FR16.3** Per gebruiker configureerbare drempels en stille uren.

### M17 — Belgische Fiscaliteit
- **FR17.1** Rapporten voor: buitenlandse dividenden, Belgische dividenden, roerende voorheffing (30%), buitenlandse bronbelasting, dividendinkomsten, beurstaks (TOB), transactiekosten.
- **FR17.2** Fiscaal jaaroverzicht dat relevante gegevens groepeert en historie bewaart.
- **FR17.3** Export naar PDF.
- **FR17.4** **Expliciet informatief/educatief**, geen fiscaal advies; gebruiker verifieert met eigen adviseur.

### M18 — Rapporten & Export
- **FR18.1** PDF-rapporten: portfolio, dividend, jaaroverzicht, belasting, FIRE, risico, asset-allocatie, AI-analyse.
- **FR18.2** Export-formaten: PDF, CSV, Excel, JSON.
- **FR18.3** Rapporten asynchroon gegenereerd; download via beveiligde, tijdelijke link.

### M19 — Instellingen & Profiel
- **FR19.1** Basisvaluta, locale, thema (light/dark/systeem).
- **FR19.2** Providerkeuze (marktdata, AI), API-sleutels (versleuteld opgeslagen).
- **FR19.3** Privacy: data-export en account-/data-verwijdering.

---

## 4. Representatieve user stories (met acceptatiecriteria)

> Formaat: *Als <actor> wil ik <doel> zodat <waarde>.* + **AC** = acceptatiecriteria.

**US-IMPORT-01** — *Als investeerder wil ik mijn BUX-bestand importeren zodat mijn transacties automatisch verschijnen.*
- **AC1** Na upload zie ik binnen enkele seconden een previewlijst met genormaliseerde transacties.
- **AC2** Aankopen, verkopen, dividenden, fees en taksen zijn correct geclassificeerd (≥ correcte mapping op voorbeeldbestand).
- **AC3** Reeds geïmporteerde transacties worden als duplicaat gemarkeerd en niet dubbel toegevoegd.
- **AC4** Ik kan de kolommapping corrigeren en pas daarna committen.

**US-DASH-01** — *Als investeerder wil ik mijn dagelijkse winst/verlies zien zodat ik mijn portefeuille snel kan inschatten.*
- **AC1** Dashboard toont totale waarde + Δ dag/week/maand/jaar in EUR en %.
- **AC2** Allocatiegrafieken (asset/sector/land) zijn interactief en kloppen met de posities.
- **AC3** Laadtijd < 500 ms bij gecachte data.

**US-DIV-01** — *Als dividendinvesteerder wil ik mijn verwachte dividendinkomen per maand zien zodat ik mijn passieve inkomen kan plannen.*
- **AC1** Dividend-dashboard toont maandelijks/jaarlijks verwacht inkomen.
- **AC2** Verwachte dividenden zijn gelabeld als schatting met disclaimer.
- **AC3** Kalender toont ex-div/record/betaaldatums met filters.

**US-FIRE-01** — *Als gebruiker wil ik mijn FIRE-voortgang zien zodat ik weet hoe ver ik van financiële onafhankelijkheid sta.*
- **AC1** Lean/Coast/Barista/Fat doelbedragen worden berekend uit mijn instellingen.
- **AC2** Een geschatte FI-datum wordt getoond met de gehanteerde aannames.
- **AC3** Een disclaimer maakt duidelijk dat het projecties zijn, geen garanties.

**US-AI-01** — *Als gebruiker wil ik een AI-analyse van mijn portefeuille zodat ik risico's en kansen begrijp.*
- **AC1** Ik kan kiezen tussen OpenAI, Claude of lokaal (Ollama).
- **AC2** Het rapport benoemt concentratierisico, over-/onderwaardering en kansen.
- **AC3** Output bevat confidence- en risicoscore + disclaimer; geen gegarandeerde uitspraken.

**US-BHS-01** — *Als gebruiker wil ik een Koop/Houd/Verkoop-signaal per aandeel zodat ik geïnformeerde keuzes maak.*
- **AC1** Label ∈ {Strong Buy, Buy, Hold, Reduce, Sell} met confidence & risico.
- **AC2** SWOT (sterk/zwak/kans/bedreiging) wordt getoond.
- **AC3** Bewoording is informatief, niet adviserend.

**US-TAX-01** — *Als Belgische belegger wil ik een fiscaal jaaroverzicht zodat mijn aangifte-administratie eenvoudiger wordt.*
- **AC1** Buitenlandse/Belgische dividenden, RV, bronbelasting, TOB en kosten worden gegroepeerd per jaar.
- **AC2** Ik kan het overzicht als PDF exporteren.
- **AC3** Een disclaimer benadrukt dat dit informatief is en geen fiscaal advies.

**US-SEC-01** — *Als gebruiker wil ik 2FA en biometrische login zodat mijn financiële data beschermd is.*
- **AC1** Ik kan TOTP-2FA activeren via QR.
- **AC2** Bij actieve 2FA is een geldige code vereist bij login.
- **AC3** Op een vertrouwd device kan ik via biometrie ontgrendelen.

---

## 5. Business rules (domeinregels)

| ID | Regel |
|----|-------|
| **BR1** | Posities worden uitsluitend afgeleid uit transacties; nooit direct muteerbaar. |
| **BR2** | Realized P/L volgt **FIFO** (default), consistent toegepast over splits. |
| **BR3** | Geld is altijd `Decimal`/`NUMERIC(20,8)`; FX-conversie naar basisvaluta op relevante datum. |
| **BR4** | Yield on Cost = jaarlijks dividend / totale kostbasis van de positie. |
| **BR5** | Dividend CAGR = (laatste / eerste)^(1/n) − 1 over de gekozen periode. |
| **BR6** | Stock split (ratio r): aantal × r, gem. prijs ÷ r; reverse split omgekeerd. |
| **BR7** | Een transactie is duplicaat als haar dedup-hash al bestaat binnen dezelfde gebruiker. |
| **BR8** | TOB (beurstaks) en RV (roerende voorheffing) worden berekend per regels in M17 en zijn informatief. |
| **BR9** | Elke "advies"-achtige output (BHS, AI, FIRE, fiscaal) draagt verplicht een disclaimer. |
| **BR10** | Verwachte dividenden/projecties worden nooit als gerealiseerd of gegarandeerd geboekt. |
| **BR11** | Een gebruiker ziet enkel eigen data (strikte ownership-check op elke resource). |
| **BR12** | Importcommit is idempotent (dezelfde batch tweemaal committen voegt niets dubbel toe). |

---

## 6. Functionele afhankelijkheden tussen modules

```
M1 (Auth) ──→ alle modules (toegang)
M3 (Transacties) ──→ M2 (Posities) ──→ M5,M7,M8,M9,M10,M14,M17
M4 (Import) ──→ M3 (Transacties)
Marktdata ──→ M2 (waardering), M5 (dividend), M8/M9 (analyse)
M8/M9 (analyse/waardering) ──→ M12/M13 (AI/BHS)
M2+M5 ──→ M10 (FIRE) ──→ M11 (scenario)
M3+M5 ──→ M17 (fiscaliteit)
alle modules ──→ M18 (rapporten/export)
events uit M2/M5/M9 ──→ M16 (notificaties), M15 (watchlist-alerts)
```

---

## 7. Out of scope (bewust niet)

- Daadwerkelijke order-uitvoering/trading via brokers (alleen import & tracking).
- Echte fiscale aangifte-indiening (alleen informatieve overzichten).
- Gegarandeerde voorspellingen of beleggingsadvies.

---

*Einde deliverable 2 — Functionele analyse. Stuur `VERDER` voor deliverable 3: Database ontwerp.*
