# 16 — Gebruikershandleiding

> Praktische gids voor DivTrack: van eerste login tot BUX-import, dividenden, FIRE, AI-analyse en je Belgisch fiscaal overzicht.

> ⚠️ **Belangrijk:** DivTrack geeft **geen** financieel, fiscaal of juridisch advies. Alle scores, analyses, AI-uitspraken, FIRE-projecties en fiscale overzichten zijn **uitsluitend informatief en educatief**. Voorspellingen zijn geen garanties. Verifieer fiscale zaken met je boekhouder of de FOD Financiën.

---

## 1. Aan de slag

### 1.1 Account aanmaken & inloggen
1. Open de app (desktop, mobiel of web).
2. Klik **Registreren**, vul naam, e-mail en een wachtwoord (min. 8 tekens) in.
3. Je wordt automatisch ingelogd en komt op het **Dashboard**.

### 1.2 Tweestapsverificatie (2FA) — aanbevolen
1. Ga naar **Instellingen → 2FA inschakelen**.
2. Scan de QR-code met een authenticator-app (Google Authenticator, Authy, …).
3. Voer de 6-cijferige code in om te bevestigen. Voortaan vraagt DivTrack bij elke login een code.

### 1.3 Biometrische login (mobiel)
Op een vertrouwd toestel kun je inloggen met vingerafdruk/gezichtsherkenning. De app bewaart je sessie veilig in de toestel-keystore.

---

## 2. Je portefeuille opzetten

DivTrack berekent alles uit je **transacties** — je voert nooit posities rechtstreeks in. Posities (aantal, gemiddelde kostprijs, winst/verlies) worden automatisch afgeleid via **FIFO**.

### 2.1 Een portefeuille maken
Tab **Portfolio → +** → geef een naam (bv. "BUX") en basisvaluta (EUR).

### 2.2 Transacties toevoegen — twee manieren
- **Importeren** (snelst, zie §3)
- **Handmatig**: kies type (Koop, Verkoop, Dividend, Storting, …), vul asset, aantal, prijs, kosten en datum in.

---

## 3. BUX importeren (en andere brokers)

1. Exporteer je transactieoverzicht uit BUX als **CSV**.
2. In DivTrack: tab **Import**.
3. Kies bron **BUX** (of CSV/Excel/PDF) en klik **Kies bestand**.
4. DivTrack herkent automatisch kolommen, types (koop/verkoop/dividend/kosten/taks), wisselkoersen en **duplicaten**.
5. Bekijk de **preview**:
   - 🟢 **Nieuw** — wordt geïmporteerd
   - 🟠 **Duplicaat** — wordt overgeslagen (al aanwezig)
   - 🔴 **Ongeldig** — vraagt aandacht (bv. een corporate action) — controleer handmatig
6. Klik **Commit** om de nieuwe transacties te boeken. Je posities en dashboard worden meteen bijgewerkt.

> 💡 BUX gebruikt dubbele boekhouding (een cash- en een asset-regel per trade). DivTrack houdt automatisch enkel de juiste regel, zodat niets dubbel geteld wordt. Vreemde valuta (bv. USD-aandelen) worden via de wisselkoers naar EUR omgerekend.

> 💡 Opnieuw hetzelfde bestand importeren is veilig: bestaande transacties worden als duplicaat herkend.

---

## 4. Het dashboard lezen

- **Totale waarde** en **onrealiseerde W/V** (winst/verlies dat je nog niet hebt gerealiseerd).
- **Geïnvesteerd** (je kostbasis) en **gerealiseerd** (winst/verlies uit verkopen, FIFO).
- **Asset-allocatie** donut: spreiding over aandelen/ETF's/REIT's/cash/crypto.
- Groen = winst, rood = verlies (kleuren passen zich aan licht/donker thema aan).

Trek omlaag (mobiel) of klik vernieuwen om live koersen op te halen.

---

## 5. Dividenden opvolgen

Tab **Dividend** toont:
- **Totaal ontvangen** en **gemiddeld per maand**.
- **Dividend per jaar** (staafgrafiek) en **CAGR** (groeivoet).
- **12-maands projectie** — een *schatting* op basis van je historiek (geen garantie).

---

## 6. FIRE plannen

Tab **FIRE**: vul je jaarlijkse uitgaven, huidige waarde, maandelijkse inleg, veilige opnamevoet (SWR, standaard 4%) en verwacht rendement in. Klik **Bereken**:
- **Lean / Coast / Barista / Fat FIRE** doelbedragen.
- Een geschatte **FI-datum** (financiële onafhankelijkheid).

Alles zijn projecties met de getoonde aannames — **geen garanties**.

---

## 7. AI-analyse (Koop/Houd/Verkoop)

Tab **AI**:
1. Kies een provider:
   - **Ollama (lokaal)** — je gegevens blijven op je eigen server (privacy).
   - **OpenAI** of **Claude** — vereist een API-sleutel in Instellingen.
2. Klik **Analyseer**. Je krijgt een samenvatting, een risicoscore en een **SWOT** (sterktes/zwaktes/kansen/bedreigingen).

De AI **rekent geen cijfers zelf** — die komen uit DivTrack's eigen berekeningen; de AI **interpreteert** ze. De output is informatief en kan fouten bevatten. **Geen advies.**

---

## 8. Belgisch fiscaal overzicht

Tab **Belasting** → kies een jaar. Je ziet een **indicatief** overzicht:
- Binnenlandse en buitenlandse dividenden (bruto)
- Buitenlandse bronbelasting
- Roerende voorheffing (30%)
- Beurstaks (**TOB**) en transactiekosten
- Netto dividendinkomen

> ⚠️ Dit is **geen** fiscaal advies en geen aangifte. Het vereenvoudigt je administratie. Controleer alles met je boekhouder of de FOD Financiën.

---

## 9. Rapporten exporteren

Genereer rapporten (portfolio, dividend, belasting, FIRE) in **PDF, Excel, CSV of JSON** via de rapportfunctie. Elk rapport bevat de educatieve disclaimer.

---

## 10. Instellingen & privacy

- **Thema:** licht / donker / systeem (knop rechtsboven).
- **Basisvaluta & taal:** EUR / nl-BE standaard.
- **AI-provider & API-sleutels:** sleutels worden versleuteld bewaard.
- **Je data is van jou:** je kunt exporteren en je account/gegevens laten verwijderen.

---

## 11. Veelgestelde vragen

**Mijn koersen zijn leeg / "n.b."?**
De marktdata-provider was even onbereikbaar, of het effect kon niet herkend worden. Vernieuw later; de app blijft werken met je laatst bekende gegevens.

**Een importrij staat op "ongeldig" (rood).**
Meestal een corporate action of overdracht die handmatige controle vraagt. Reguliere koop/verkoop/dividend/kosten worden automatisch herkend.

**Klopt mijn winst/verlies?**
Gerealiseerde winst volgt **FIFO** (eerst gekochte aandelen eerst verkocht). Onrealiseerde W/V gebruikt de laatst bekende koers.

**Geeft DivTrack beleggingsadvies?**
Nee. Alle output is informatief en educatief. Beslissingen neem je zelf, eventueel met een erkend adviseur.

---

## 12. Beveiligingstips

- Zet **2FA** aan.
- Gebruik een sterk, uniek wachtwoord.
- Deel je API-sleutels niet.
- Log uit op gedeelde toestellen (knop rechtsboven).

---

*Einde deliverable 16 — Gebruikershandleiding. Hiermee zijn alle 16 deliverables opgeleverd.*
