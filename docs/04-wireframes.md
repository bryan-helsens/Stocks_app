# 04 — UI Wireframes

> Low-fidelity wireframes (ASCII) voor DivTrack, per kernscherm, voor **desktop** (breed) en **mobiel** (smal). Design-taal: Material 3, light/dark, datarijk maar rustig (TradingView/Snowball/Simply Wall St). Deze wireframes sturen de Flutter-`presentation`-laag (deliverable 8).

> ⚠️ Elk scherm met scores/voorspellingen/AI/fiscaliteit toont een **disclaimer-strip**: "Informatief & educatief — geen financieel/fiscaal advies."

---

## 0. Navigatiestructuur

```
Desktop: persistente linker-rail (NavigationRail)        Mobiel: bottom nav + "More"
┌──────────────────────────────────────────┐            ┌───────────────────────┐
│ [≡] DivTrack            🔔  🌓  👤        │           │  DivTrack        🔔 👤 │
├─────┬────────────────────────────────────┤           ├───────────────────────┤
│ 📊  │                                    │           │                       │
│ 💼  │                                    │           │      (content)        │
│ 🔁  │          (content area)            │           │                       │
│ 💶  │                                    │           │                       │
│ 📅  │                                    │           ├───────────────────────┤
│ 🧮  │                                    │           │ 📊  💼  💶  🤖  •••   │
│ 🤖  │                                    │           └───────────────────────┘
│ 👁  │                                    │
│ 🧾  │                                    │   Rail-iconen:
│ ⚙️  │                                    │   📊 Dashboard  💼 Portfolio  🔁 Import
└─────┴────────────────────────────────────┘   💶 Dividend  📅 Kalender  🧮 FIRE
                                                🤖 AI  👁 Watchlist  🧾 Belasting ⚙️ Settings
```

---

## 1. Portfolio Dashboard (M7)

**Desktop**
```
┌──────────────────────────────────────────────────────────────────────────────┐
│ Dashboard            Portefeuille: [Alle ▾]      Periode: [1D 1W 1M 1J MAX]    │
├──────────────────────────────────────────────────────────────────────────────┤
│ ┌── Totale waarde ──┐ ┌── Dag W/V ──┐ ┌── Maand W/V ─┐ ┌── Jaar W/V ─┐         │
│ │  € 142.380,55     │ │ +€812 +0,57%│ │ +€3.1k +2,2% │ │ +€18k +14,5%│         │
│ │  ▁▂▃▅▆▇█ sparkline │ │   ▲ groen   │ │   ▲ groen    │ │   ▲ groen   │         │
│ └───────────────────┘ └─────────────┘ └──────────────┘ └─────────────┘         │
│ ┌─────────────────────────── Waarde-evolutie ───────────────────────────────┐ │
│ │  €                                                              ╭─╮         │ │
│ │       ╭──╮        ╭───╮                       ╭────╮      ╭────╯           │ │
│ │  ─────╯  ╰────────╯   ╰───────────────────────╯    ╰──────╯  (area chart)  │ │
│ │  └────────────────────────────────────────────────────────────────────────┘ │
│ ┌──── Asset allocatie ────┐ ┌──── Sector ────┐ ┌──── Land ────┐ ┌── Risico ──┐ │
│ │     ◓ donut             │ │   ◔ donut       │ │  🗺 bars      │ │  Score 72  │ │
│ │ Aandelen 58% ETF 27%    │ │ Tech 22% ...    │ │ US 61% BE 12%│ │  ████░ Mid │ │
│ │ REIT 8% Cash 7%         │ │                 │ │ ...          │ │            │ │
│ └─────────────────────────┘ └─────────────────┘ └──────────────┘ └────────────┘ │
│ ┌──── FIRE voortgang ─────────────────┐ ┌──── Dividendvoorspelling (12m) ─────┐ │
│ │ Coast ███████████░░░ 78%  FI: 2034  │ │  ▁▃▂▅▃▆▄█▅▇▄█  € 4.820 verwacht     │ │
│ └─────────────────────────────────────┘ └──────────────────────────────────────┘ │
│ ⓘ Informatief & educatief — geen financieel advies.                            │
└──────────────────────────────────────────────────────────────────────────────┘
```

**Mobiel** (verticaal gestapeld)
```
┌───────────────────────┐
│ € 142.380,55          │
│ +€812 (+0,57%) vandaag│
│ ▁▂▃▅▆▇█  [1D 1W 1M 1J]│
├───────────────────────┤
│ [Dag][Week][Maand][Jr]│  ← swipebare KPI-chips
├───────────────────────┤
│   ◓ Asset allocatie   │
│   Aandelen 58% ...    │
├───────────────────────┤
│   FIRE  ███████░ 78%  │
├───────────────────────┤
│  Dividend 12m: €4.820 │
├───────────────────────┤
│ ⓘ educatief, geen advies
└───────────────────────┘
```

---

## 2. Portfolio / Posities (M2)

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ Portefeuille  [+ Transactie] [⬆ Import]      Zoek: [______]  Filter: [Class ▾] │
├──────────────────────────────────────────────────────────────────────────────┤
│ Asset            Aant.   Gem.kost  Koers   Waarde     O.W/V        YoC   Div%  │
│ ───────────────────────────────────────────────────────────────────────────── │
│ 🟦 AAPL  Apple    40     €120,10  €172,3  €6.892   +€2.084 +43% ▲  2,1%  0,5%   │
│ 🟦 MSFT  Microsoft 25    €230,00  €310,5  €7.762   +€2.012 +35% ▲  1,9%  0,8%   │
│ 🟩 VWCE  Vanguard 120    €98,40   €112,8  €13.536  +€1.728 +14% ▲   –    1,4%   │
│ 🟨 O     Realty    90    €52,30   €48,1   €4.329   −€378  −8% ▼   6,3%  5,8%   │
│ ...                                                                            │
│ ───────────────────────────────────────────────────────────────────────────── │
│ ▸ Klik rij → positie-detail (historiek, dividenden, analyse, BHS)              │
└──────────────────────────────────────────────────────────────────────────────┘

Positie-detail (tabs):
┌── AAPL · Apple Inc. ─────────────────────────────────────────────────┐
│ [Overzicht] [Transacties] [Dividenden] [Analyse] [Waardering] [BHS]  │
│ ┌ Overzicht ───────────────────────────────────────────────────────┐ │
│ │ Koersgrafiek (cand/ line, 1D–MAX)                                │ │
│ │ Marktwaarde €6.892 · Invest. €4.804 · O.W/V +€2.084 (+43%)        │ │
│ │ Gerealiseerd €0 · Div ontvangen €72 · YoC 0,6% · Score 81/100    │ │
│ └──────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 3. Broker Import (M4) — wizard

```
Stap 1: Bron          Stap 2: Upload        Stap 3: Mapping       Stap 4: Preview/Commit
┌──────────────┐      ┌──────────────┐      ┌──────────────────┐  ┌────────────────────┐
│ ○ BUX        │      │  ⬆ Sleep      │     │ Kolom → Veld     │  │ 124 rijen          │
│ ○ CSV        │  →   │  bestand of   │  →  │ Datum  → trade   │→ │ ✓ 110 nieuw        │
│ ○ Excel      │      │  [Kies...]    │     │ ISIN   → asset   │  │ ⊘ 12 duplicaat     │
│ ○ PDF        │      │  bux_2025.csv │     │ Bedrag → gross   │  │ ⚠ 2 ongeldig       │
│ ○ Handmatig  │      │               │     │ Type   → (auto)  │  │ [Bewerk] [Commit]  │
└──────────────┘      └──────────────┘      └──────────────────┘  └────────────────────┘

Preview-tabel (stap 4):
┌────────────────────────────────────────────────────────────────────────┐
│ ✓/⊘  Datum       Type      Asset   Aantal  Bedrag    Fee   Tax   Status  │
│ ✓    2025-03-04  BUY       AAPL    10      €1.701    €0    €1,7  NIEUW    │
│ ⊘    2025-03-04  BUY       AAPL    10      €1.701    €0    €1,7  DUP      │
│ ✓    2025-03-15  DIVIDEND  O       –       €43,20    –     €13   NIEUW    │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Dividend Dashboard (M5) & Kalender (M6)

```
Dividend Dashboard
┌──────────────────────────────────────────────────────────────────────────────┐
│ Jaarinkomen €4.620  ·  Gem./maand €385  ·  YoC portef. 3,8%  ·  CAGR 5j 7,1%   │
│ ┌──── Dividend per maand ────────────────┐ ┌──── Per sector ──┐ ┌── Per land ─┐│
│ │ €  ▃ ▅ ▂ █ ▄ ▆ ▃ █ ▅ ▇ ▄ █  (bars)     │ │  ◓ donut          │ │  bars       ││
│ │    J F M A M J J A S O N D              │ │  Financials 31%   │ │  US 54%...  ││
│ └─────────────────────────────────────────┘ └───────────────────┘ └────────────┘│
│ ⓘ Verwachte dividenden zijn schattingen, geen garantie.                        │
└──────────────────────────────────────────────────────────────────────────────┘

Dividend Kalender
┌──────────────────────────────────────────────────────────────────────────────┐
│ Mei 2026   [< >]    Filter: [Portef ▾][Type: ex/record/betaal ▾][✓ verwacht]  │
│ ma   di   wo   do   vr   za   zo                                               │
│              1    2    3    4                                                  │
│  5    6    7•  8    9   10   11     • 7 mei  O   ex-div  $0,26                 │
│ 12  13• 14   15★ 16   17   18      • 13 mei MSFT ex-div $0,75                  │
│ 19  20   21   22★ 23   24   25     ★ 15/22 mei betaaldatums                    │
│ ...                                                                            │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## 5. Aandelenanalyse & Waardering (M8/M9)

```
┌── AAPL · Analyse ────────────────────────────────────────────────────────────┐
│ Score 81/100   [Waardering 70][Groei 88][Gezondheid 92][Dividend 64]          │
│ ┌ Ratio's ─────────────────────────────────────────────────────────────────┐ │
│ │ P/E 28,4  Fwd P/E 24,1  PEG 1,8  ROE 147%  ROIC 56%  D/E 1,9              │ │
│ │ FCF €99B  Payout 15%  Rev gr. 8%  EPS gr. 11%  Div gr. 5%                 │ │
│ └───────────────────────────────────────────────────────────────────────────┘ │
│ ┌ Waardering ──────────────────────────────────────────────────────────────┐ │
│ │ Methode    Fair Value   Koers    Margin of Safety   Verdict               │ │
│ │ DCF        €158         €172      −8,9%              OVERGEWAARDEERD        │ │
│ │ DDM        €120         €172      −43%               OVERGEWAARDEERD       │ │
│ │ Multiples  €165         €172      −4,2%              CORRECT               │ │
│ │ ── Blended €161  →  Verdict: licht OVERGEWAARDEERD ──                      │ │
│ │ [▸ Aannames tonen]                                                         │ │
│ └───────────────────────────────────────────────────────────────────────────┘ │
│ ⓘ Modeluitkomsten, sterk afhankelijk van aannames. Geen advies.               │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## 6. AI Analyst & Koop/Houd/Verkoop (M12/M13)

```
┌── AI Portfolio Analyst ──────────────────────────────────────────────────────┐
│ Provider: [Claude ▾] [OpenAI][Ollama-lokaal]      [⟳ Analyseer portefeuille]  │
│ ┌ Samenvatting ────────────────────────────────────────────────────────────┐ │
│ │ "Je portefeuille leunt sterk op Amerikaanse tech (concentratie ↑).        │ │
│ │  Dividenddekking is gezond; REIT-blok voegt yield maar rentegevoeligheid." │ │
│ └───────────────────────────────────────────────────────────────────────────┘ │
│ Risicoscore 64 · Diversificatie ⚠  Concentratie: AAPL+MSFT = 31%             │
│ ┌ Sterk ─────┐ ┌ Zwak ──────┐ ┌ Kansen ─────┐ ┌ Bedreigingen ─┐             │
│ │ • Cashflow  │ │ • US-bias   │ │ • EU-spreid │ │ • Rente/REIT   │            │
│ │ • Div groei │ │ • Tech 38%  │ │ • Healthcare│ │ • FX USD/EUR   │            │
│ └─────────────┘ └─────────────┘ └─────────────┘ └────────────────┘            │
│ ⓘ AI-output is educatief, kan fouten bevatten, geen advies.                   │
└──────────────────────────────────────────────────────────────────────────────┘

Koop/Houd/Verkoop (per positie)
┌── O · Realty Income ─────────────────────────────────────────────────────────┐
│        ┌─────────────┐                                                        │
│        │    HOLD      │   Confidence 71%   Risico 58/100                      │
│        └─────────────┘   [Strong Buy|Buy|●Hold|Reduce|Sell]                   │
│ Sterk: hoge yield, maandelijks dividend · Zwak: rentegevoelig, lage groei     │
│ Kansen: dalende rente · Bedreigingen: refinanciering, bezetting               │
│ ⓘ Informatief signaal, geen beleggingsadvies.                                 │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## 7. FIRE & Scenario Planner (M10/M11)

```
┌── FIRE ──────────────────────────────────────────────────────────────────────┐
│ Jaarl. uitgaven [€ 30.000]  SWR [4%]  Maandinleg [€ 800]  Rendement [7%]      │
│ ┌ Doelen ──────────────────────────────────────────────────────────────────┐ │
│ │ Lean FIRE   €600.000   ████████░░ 64%   ~2032                             │ │
│ │ Coast FIRE  €310.000   ██████████ 100% ✓ bereikt                          │ │
│ │ Barista     €450.000   █████████░ 79%   ~2030                             │ │
│ │ Fat FIRE    €1.250.000 ███░░░░░░░ 21%   ~2045                             │ │
│ └───────────────────────────────────────────────────────────────────────────┘ │
│ ┌ Projectie portefeuillewaarde ────────────────────────────────────────────┐ │
│ │  €      ░░░░░░░░░░░░░░░░░░░░░░░ P90                                        │ │
│ │         ──────────────────────  P50 (verwacht)        FI-datum: ~2034     │ │
│ │  ▁▂▃▄▅▆▇████████████ P10                                                  │ │
│ └───────────────────────────────────────────────────────────────────────────┘ │
│ Scenario's: [Crash −30%] [Inflatie 4%] [Extra €200/m] [Div −20%] [+ Nieuw]    │
│ ⓘ Projecties zijn schattingen, geen garanties.                                │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## 8. Belgische Fiscaliteit (M17)

```
┌── Belastingoverzicht  Jaar [2025 ▾]   [⬇ Export PDF]──────────────────────────┐
│ Dividendinkomsten (bruto)                                        € 4.620,00   │
│  • Belgische dividenden                                          €   820,00   │
│  • Buitenlandse dividenden                                       € 3.800,00   │
│ Roerende voorheffing (30%)                                       € 1.386,00   │
│ Buitenlandse bronbelasting (ingehouden aan de bron)              €   570,00   │
│ Beurstaks (TOB)                                                  €   142,30   │
│ Transactiekosten                                                 €    98,00   │
│ ─────────────────────────────────────────────────────────────────────────────│
│ Netto dividendinkomen (indicatief)                               € 3.234,00   │
│ ┌ Detail per positie/land ───────────────────────────────────────────────────┐│
│ │ Asset  Land  Bruto    Bronbel.  RV     Netto                               ││
│ │ O      US    €248     €37       €74     €137                               ││
│ │ ...                                                                         ││
│ └─────────────────────────────────────────────────────────────────────────────┘│
│ ⚠ Uitsluitend informatief/educatief. Geen fiscaal advies — verifieer met je   │
│   boekhouder/FOD Financiën.                                                    │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## 9. Watchlist (M15) & Notificaties (M16)

```
┌── Watchlist: "Dividend Aristocrats" [+ lijst] ───────────────────────────────┐
│ Asset   Koers    Koersdoel  Δ doel   Fair value   Div%   Alerts   Notitie     │
│ JNJ     €148,2   €140       +5,9%    €152 (onder) 3,1%   🔔div    "wachten"    │
│ PG      €152,0   €150       +1,3%    €148 (boven) 2,5%   🔔FV     ""           │
│ [+ asset toevoegen]                                                           │
└──────────────────────────────────────────────────────────────────────────────┘

Notificatie-instellingen
┌──────────────────────────────────────────────────────────────────────────────┐
│ Kanalen:  [✓] Push   [✓] Telegram (@user)   [✓] E-mail                         │
│ Triggers: [✓] Dividend ontvangen  [✓] Ex-div nadert  [✓] Koersdoel             │
│           [✓] Risico  [✓] Grote koerswijziging (>[5]%)  [✓] Over/onderwaard.   │
│ Stille uren: [22:00] – [07:00]                                                 │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## 10. Auth & Settings (M1/M19)

```
Login                         2FA                         Settings
┌──────────────────┐         ┌──────────────────┐        ┌──────────────────────┐
│   DivTrack       │         │  Voer 2FA-code    │       │ Profiel  Valuta [EUR] │
│  e-mail [______] │         │   [_][_][_][_][_] │       │ Thema [Systeem ▾]     │
│  wachtw [______] │   →     │   [Bevestig]      │  →    │ Kostbasis [FIFO ▾]    │
│  [ Inloggen ]    │         │                   │       │ AI-provider [Ollama▾] │
│  of  👆 biometrie │         │  📷 (QR bij setup)│       │ Providers/API-keys 🔒 │
│  [Registreren]   │         └──────────────────┘        │ Devices · Back-up     │
└──────────────────┘                                     │ Export/Verwijder data │
                                                         └──────────────────────┘
```

---

## 11. Design tokens (richtlijn voor deliverable 8)

| Token | Light | Dark |
|-------|-------|------|
| `surface` | #FFFFFF | #121417 |
| `surfaceAlt` | #F4F6F8 | #1B1F24 |
| `primary` | #1F6FEB | #4C8DFF |
| `positive` (winst) | #16A34A | #34D399 |
| `negative` (verlies) | #DC2626 | #F87171 |
| `warning` | #D97706 | #FBBF24 |
| `textPrimary` | #0F172A | #E5E7EB |
| `textMuted` | #64748B | #94A3B8 |

Typografie: Inter / Roboto; tabular figures voor bedragen. Spacing-grid 4 px. Hoeken 12 px. Grafiekkleuren consistent per asset class.

---

*Einde deliverable 4 — UI wireframes. Stuur `VERDER` voor deliverable 5: UX flows.*
