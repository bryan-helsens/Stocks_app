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
