# rsi_dip_buyer v2 — integratie in je Bot-bitvavo

> ⚠️ Educatief. Draai dit eerst **paper**, minimaal 2–4 weken, vóór echt geld.
> Geen enkele strategie garandeert winst; het doel is de verdeling kantelen.

## Wat er in zit (en waarom)

| Probleem in v1 (gemeten) | Fix in v2 |
|---|---|
| Winrate 40.5% maar break-even eiste 64% | `rr_target=1.6` → break-even zakt naar **38.5%**, ónder je huidige winrate |
| SL (−3.40%) groter dan TP (+2.06%) | ATR-stops + TP = 1.6× risico, altijd positieve R/R |
| Vallende messen gekocht (dips die door-dipten) | EntryGate: uptrend-filter + RSI moet al **draaien** |
| Alts (FET/NEAR/XLM…) droegen 100% van het verlies | ATR%-band sluit wilde symbolen automatisch uit + optionele allow/denylist |
| Volle stop-loss telkens geraakt | **CrashGuard**: dump-detectie verkoopt ~0.9R i.p.v. 1R+, BTC-regime sluit alle alt-longs |
| Dood kapitaal in zijwaartse trades | Time-stop na 96 bars zonder progressie |
| Fees = 43% van het verlies | Edge-check: geen trade als TP ≤ 2× round-trip-fee; minder trades door de gate |

## Bestanden

```
rsi_dip_buyer_v2.py        # de strategie-module (dependency-vrij, pure Python)
test_rsi_dip_buyer_v2.py   # 27 tests — allemaal groen (pytest)
```

Kopieer beide naar je bot, bv.:
```bash
scp rsi_dip_buyer_v2.py test_rsi_dip_buyer_v2.py debian@vps:~/Bot-bitvavo/strategies/
ssh debian@vps "cd ~/Bot-bitvavo/strategies && python3 -m pytest test_rsi_dip_buyer_v2.py -q"
```

## Aansluiten op je bestaande bot-loop

De module kent Bitvavo niet — jij voedt candles, hij geeft beslissingen.
Jouw positie-velden (`entry_price`, `stop_loss`, `break_even_armed`,
`take_profit_levels`, `trailing_stop_price`) sluiten 1-op-1 aan.

```python
from rsi_dip_buyer_v2 import (
    Candle, StrategyConfig, EntryGate, RiskModel, PositionManager,
    CrashGuard, DailyCircuitBreaker, ManageAction, MarketRegime,
)

cfg     = StrategyConfig()            # zie "Config-knoppen" hieronder
gate    = EntryGate(cfg)
risk    = RiskModel(cfg)
manager = PositionManager(cfg)
guard   = CrashGuard(cfg)
breaker = DailyCircuitBreaker(cfg)

def to_candles(ohlcv):                # Bitvavo: [ts, open, high, low, close, vol]
    return [Candle(float(r[0]), float(r[1]), float(r[2]),
                   float(r[3]), float(r[4]), float(r[5])) for r in ohlcv]

def on_bar_close(symbol, ohlcv, btc_ohlcv, equity, open_positions):
    candles = to_candles(ohlcv)
    regime  = guard.market_regime(to_candles(btc_ohlcv))   # BTC = markt-proxy

    # ---- 1. open posities beheren (crash-interceptor + BE + trailing) ----
    for pos in open_positions.get(symbol, []):
        d = manager.manage(
            entry_price=float(pos.entry_price),
            stop_loss=float(pos.stop_loss),
            break_even_armed=pos.break_even_armed,
            bars_held=pos.bars_held,               # tel bars sinds opened_at
            candles=candles,
            regime=regime,
        )
        if d.action is ManageAction.EXIT_NOW:
            market_sell(pos); log(d.reason)
        elif d.action is ManageAction.RAISE_STOP:
            replace_stop_order(pos, d.new_stop); pos.stop_loss = d.new_stop
            if d.new_stop >= float(pos.entry_price):
                pos.break_even_armed = True

    # ---- 2. nieuwe entry? alleen via de gate + circuit-breaker ----
    if not breaker.allow_trading(equity):
        return
    if len(all_open_positions()) >= cfg.max_open_positions:
        return
    decision = gate.evaluate(symbol, candles, regime=regime)
    log(f"{symbol}: score={decision.score:.0f} :: " + " | ".join(decision.reasons))
    if decision.allowed:
        plan = risk.plan(symbol, equity, decision, price=candles[-1].close)
        if plan:
            place_buy(plan.symbol, plan.quantity)
            place_stop(plan.symbol, plan.stop)
            place_take_profit(plan.symbol, plan.take_profit)   # 1.6R
```

Roep verder één keer per dag (bv. 00:00 UTC) `breaker.new_day(equity)` aan.

## Config-knoppen (defaults zijn afgestemd op je gemeten data)

| Knop | Default | Effect |
|---|---|---|
| `rr_target` | 1.6 | TP-afstand als veelvoud van risico. Hoger = minder maar grotere winsten |
| `stop_atr_mult` | 2.0 | Stop-afstand in ATR. Vast % was v1's fout: alts werden weggeschud |
| `risk_per_trade_pct` | 0.75 | % equity per trade op het spel (fixed fractional) |
| `min_quality_score` | 65 | Gate-drempel. Hoger = selectiever = minder trades |
| `min_atr_pct`/`max_atr_pct` | 0.15 / 4.0 | Volatiliteitsband — knijp `max` naar bv. 2.5 om alts nog harder te weren |
| `allowlist` | () | bv. `("BTC","ETH","SOL")` → alleen majors |
| `crash_bar_drop_atr` | 1.8 | Dump-bar-drempel; ligt bewust ónder de stop (2.0) → exit ~0.9R |
| `market_crash_pct` | 2.5 | BTC −2.5% in 12 bars → BEAR: alt-longs eruit, geen entries |
| `time_stop_bars` | 96 | Bars zonder progressie → exit (96×15m = 24u) |
| `max_daily_loss_pct` | 2.0 | Dag-circuit-breaker |

## De wiskunde in één regel

```
v1:  winrate 40.5% nodig 64.0%  → expectancy −€0.12/trade  → gegarandeerd bloeden
v2:  winrate 40.5% nodig 38.5%  → expectancy > 0 bij GELIJKE winrate
     + gate verhoogt winrate    + interceptor maakt verliezers < 1R
```

## Wat je moet verifiëren tijdens paper-run

1. **Trade-frequentie daalt fors** (de gate weigert de meeste v1-setups) — dat is de bedoeling.
2. Log per geweigerde entry de `decision.reasons` — zo zie je wát de gate tegenhoudt.
3. Na 30+ gesloten trades: check `profit factor > 1` en `gem. verlies ≤ 1R`.
4. Interceptor-exits horen kleiner dan −1R te zijn; zo niet, verlaag `crash_bar_drop_atr`.

---

## Nieuw in deze versie (v2.1)

### 1. Cooldown na stop-loss (`CooldownTracker`)
v1 kocht FET **6×**, INJ **5×**, SOL **4×** opnieuw terwijl de coin bleef
vallen. Na elke SL/crash-exit is het symbool nu `cooldown_bars_after_stop`
(default 48 bars = 12u op 15m) geblokkeerd:

```python
cooldown = CooldownTracker(cfg)
# bij een verlies-exit:
cooldown.record_loss_exit(symbol, bar_index)
# vóór de gate:
if cooldown.blocked(symbol, bar_index): return
```

### 2. Partial take-profit (sluit aan op jouw take_profit_levels)
Default: **50% eraf bij +1R** (stop → break-even), rest naar **2.2R**, zodat
het gewogen gemiddelde exact `rr_target` (1.6R) blijft. `RiskModel.plan`
geeft nu `plan.tp_levels = [(prijs, size_fraction), ...]` terug — map die
1-op-1 op jouw `take_profit_levels`. Uitzetten: `partial_tp_enabled=False`.

### 3. Backtest-engine (`backtest.py`) — draai dit op je VPS
Vergelijkt v1 (jouw gemeten parameters: stop −2.55%, TP +2.45%, geen filters)
met v2 op échte Bitvavo-candles, inclusief 0.25% fee/zijde, 0.35%
stop-slippage (gemeten uit je v1-fills!), gap-fills en entry op de
next-bar-open (geen look-ahead):

```bash
# op de VPS:
python3 backtest.py --days 60                 # beide, 10 markten, 15m
python3 backtest.py --days 90 --only v2       # alleen v2
python3 backtest.py --synthetic               # offline smoke-test
```

Beoordeel v2 pas als "goed" bij: PF > 1.3, gem. verlies ≤ 1R, maxDD < 8%,
en dat over ≥ 60 dagen die zowel groene als rode weken bevatten.

## Nieuw in v2.2 — de kosten-gate (fix na jouw échte backtest)

Jouw 60-dagen backtest op de VPS bewees dat v2.1 **slechter** was dan v1
(PF 0.21, worst −3.25R). De oorzaak zat niet in de strategie maar in de
kosten, uitgedrukt in R:

- Op 15m is de ATR vaak maar ~0.2%. Stop = 2×ATR = **0.4%**.
- Vaste kosten per trade: 0.50% fees (round-trip) + 0.35% stop-slippage
  = **0.85%** — meer dan twee keer de stopafstand.
- Gevolg: een TP-hit leverde netto maar **+0.35R** op, een SL-hit kostte
  netto **−3.1R**. Met zulke payoffs is winst wiskundig onmogelijk,
  hoe goed de entries ook zijn.

De fix (`EntryGate`): een trade wordt geweigerd als de vaste kosten meer
dan `max_cost_per_risk` (default **0.30R**) van het risico opeten:

```python
fee_pct_round_trip: float = 0.50   # 0.25% taker per zijde (Bitvavo)
stop_slippage_pct: float = 0.35    # gemeten uit jouw v1-fills
max_cost_per_risk: float = 0.30    # (fees+slip)/stop% ≤ 0.30, anders skip
```

Praktische consequentie: de gate eist een stopafstand van minstens
~2.8% (dus ATR ≥ ~1.4%). **Op 15m komt dat zelden voor — dat timeframe
is bij deze kosten structureel te duur.** Draai de backtest daarom op 1h:

```bash
python3 backtest.py --interval 1h --days 120
python3 backtest.py --interval 1h --days 90 --only v2
```

Het rapport toont nu ook `avgW`/`avgL` apart, zodat je meteen ziet of de
verliezen netjes rond −1R blijven (dat is waar v2.1 op faalde).

### Twee knoppen om méér (betaalbare) trades te vinden

De 120-dagen 1h-run gaf maar 4 trades: bij 0.85% vaste kosten zijn er
gewoon weinig setups die de moeite waard zijn. Twee eerlijke manieren om
dat te verruimen — allebei verlagen ze de kosten, niet de lat:

1. **`--maker`** — rekent met limit-order (maker) fees: 0.15%/zijde
   i.p.v. 0.25% taker. Round-trip zakt van 0.50% naar 0.30%, waardoor de
   gate stops vanaf ~2.2% accepteert i.p.v. ~2.8%. Alleen eerlijk als je
   live bot óók met limit orders instapt.
2. **`--interval 2h` of `4h`** — grotere ATR → bredere stops → kosten
   worden een kleiner deel van het risico. Neem dan meer dagen
   (`--days 240`) zodat je genoeg bars houdt.

```bash
python3 backtest.py --interval 1h --days 120 --maker
python3 backtest.py --interval 4h --days 240
```

## Zo draai je v2 met nepgeld (`paper_trader_v2.py`)

Standalone paper-trader: gebruikt alleen publieke Bitvavo-marktdata
(geen API-keys, echt geld kan onmogelijk bewegen) en houdt zijn eigen
portefeuille bij in `paper_state_v2.json` + logboek `paper_log_v2.txt`.
Je hoeft je bestaande bot dus niet aan te passen.

```bash
cd ~/Bot-bitvavo

# 1) eerste run: legt de instellingen vast (1h, maker-fees, €100)
python3 paper_trader_v2.py --once --maker

# 2) elk uur automatisch draaien via cron:
crontab -e
# voeg deze regel toe (minuut 1: de 1h-candle van het vorige uur is dan dicht):
# 1 * * * * cd /home/debian/Bot-bitvavo && /usr/bin/python3 paper_trader_v2.py --once >> paper_cron.log 2>&1

# 3) kijken hoe het gaat:
python3 paper_trader_v2.py --status
tail -20 paper_log_v2.txt
```

Wat je in het log gaat zien:
- `SIGNAAL`/`KOOP`/`SLUIT`/`TP1`/`STOP↑` — de trades zelf, met R-multiple
- `bijna …: score XX geweigerd` — echte dips die door een kwaliteits- of
  kostenfilter zijn afgewezen (leerzaam: dáár zie je wat de gate tegenhoudt)
- **wekenlang stilte is normaal** — verwacht grofweg één trade per maand;
  de gate weigert alles wat na kosten geen positieve verwachting heeft

Rode vlaggen om te melden: een verlies dieper dan ±−1.4R (dan is de echte
slippage groter dan de 0.35% die we gemeten hebben), of ineens dagelijkse
trades (dan klopt er iets niet).

Instellingen worden bij de EERSTE run vastgelegd en daarna genegeerd,
zodat de meting consistent blijft. Opnieuw beginnen: `--reset`.
Geen cron maar één proces: `python3 paper_trader_v2.py --loop` (bv. in
`screen`/`tmux`), die wordt vanzelf elke bar wakker.

## Pushmeldingen op je telefoon (ntfy.sh)

Met ~1 trade per maand wil je een pushmelding, geen dashboard-gestaar.
Gratis en zonder account via [ntfy.sh](https://ntfy.sh):

```bash
# 1) verzin een geheim topic (het topic ís het wachtwoord — maak het lang):
python3 paper_trader_v2.py --set-ntfy bryan-bot-x7k2m9q4

# 2) installeer de ntfy-app (Android/iOS) en abonneer op datzelfde topic
# 3) klaar — je krijgt een push bij elke papieren KOOP/SLUIT/TP1
#    uitzetten: python3 paper_trader_v2.py --set-ntfy ""
```

## Gezondheidsbewaking

Het dashboard toont bovenaan de laatst verwerkte bar en waarschuwt met
een rode banner zodra de trader ≥ 2 bars achterloopt (service gecrasht,
API onbereikbaar, …). Stilte betekent dus echt "geen trades", niet
"kapot".

## v3 — momentum/breakout (`momentum_breakout_v3.py`)

Na de v1/v2-data was de conclusie: dips kopen heeft op deze markten geen
eetbare edge na kosten. v3 draait het om — **koop sterkte, rijd de trend,
trail de stop**:

- entry: close boven de hoogste high van 55 bars, in een uptrend
  (EMA50>EMA200), niet meer dan 1.5×ATR boven het breakout-niveau
  (geen pumps chasen), volume- en momentum-bonus, BTC-regime niet BEAR
- dezelfde KOSTEN-GATE als v2 (≤ 0.30R) — maar breakouts gebeuren juist
  als de ATR groot is, dus de gate en de strategie werken hier sámen
- exits: 50% winst op +2R (stop → break-even), rest op een
  chandelier-trail (hoogste close − 3×ATR); crash-interceptor,
  BEAR-exit, time-stop na 48 bars zonder progressie
- 18 tests in `test_momentum_breakout_v3.py`

Falsifiëren op de VPS (v3 draait nu standaard mee in de vergelijking):

```bash
python3 backtest.py --interval 1h --days 120 --maker
python3 backtest.py --interval 4h --days 240
python3 backtest.py --interval 1h --days 120 --only v3   # alleen v3
```

Beoordeel v3 op: PF > 1.3, avgW/avgL-verhouding ruim boven 1.5 (de winst
zit in de staart), avgL rond −0.7R, maxDD < 10%, ≥ 30 trades. Pas als
dat op écht data staat, bouwen we hem in de paper-trader.
