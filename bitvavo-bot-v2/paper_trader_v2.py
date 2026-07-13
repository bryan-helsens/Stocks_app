"""Paper-trader voor rsi_dip_buyer v2 — standalone, geen API-keys nodig.

Gebruikt alleen de publieke Bitvavo-marktdata en houdt een eigen papieren
portefeuille bij in `paper_state_v2.json` (+ logboek `paper_log_v2.txt`).
Er kan dus onmogelijk echt geld bewegen.

Snelstart (op je VPS, in de map met rsi_dip_buyer_v2.py):

    python3 paper_trader_v2.py --once --maker    # eerste run: init + 1 bar
    python3 paper_trader_v2.py --status          # portefeuille bekijken

Daarna elk uur automatisch laten draaien via cron (minuut 1, zodat de
1h-candle van het vorige uur zeker dicht is):

    crontab -e
    # en voeg toe:
    1 * * * * cd /home/debian/Bot-bitvavo && /usr/bin/python3 paper_trader_v2.py --once >> paper_cron.log 2>&1

De strategie-instellingen (fees, interval, markten) worden bij de EERSTE
run in de state vastgelegd en daarna genegeerd — zo blijft de meting
consistent. Opnieuw beginnen: `python3 paper_trader_v2.py --reset`.

⚠️  Educatief. Papieren resultaten bewijzen niets over de toekomst.
"""

from __future__ import annotations

import argparse
import json
import os
import time
import urllib.request
from datetime import datetime, timezone

from rsi_dip_buyer_v2 import (
    Candle, CrashGuard, EntryDecision, EntryGate, ManageAction,
    MarketRegime, PositionManager, RiskModel, StrategyConfig,
)

STATE_FILE = "paper_state_v2.json"
LOG_FILE = "paper_log_v2.txt"
DEFAULT_MARKETS = ["BTC-EUR", "ETH-EUR", "SOL-EUR", "XRP-EUR", "ADA-EUR",
                   "LTC-EUR", "AVAX-EUR", "INJ-EUR", "FET-EUR", "NEAR-EUR"]
MS_PER = {"1h": 3_600_000, "2h": 7_200_000, "4h": 14_400_000}
STOP_SLIPPAGE_PCT = 0.35     # gemeten uit je v1-fills
HISTORY_BARS = 400           # genoeg voor EMA-200 + marge


# --------------------------------------------------------------------------- #
# infra
# --------------------------------------------------------------------------- #
def log(msg: str) -> None:
    line = f"{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}Z  {msg}"
    print(line, flush=True)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def fetch(market: str, interval: str, limit: int = HISTORY_BARS) -> list[Candle]:
    url = (f"https://api.bitvavo.com/v2/{market}/candles"
           f"?interval={interval}&limit={min(limit, 1440)}")
    with urllib.request.urlopen(url, timeout=20) as r:
        rows = json.loads(r.read())
    rows.sort(key=lambda x: x[0])
    return [Candle(r0[0] / 1000, float(r0[1]), float(r0[2]),
                   float(r0[3]), float(r0[4]), float(r0[5])) for r0 in rows]


def load_state() -> dict | None:
    if not os.path.exists(STATE_FILE):
        return None
    with open(STATE_FILE) as f:
        return json.load(f)


def save_state(st: dict) -> None:
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(st, f, indent=1)
    os.replace(tmp, STATE_FILE)


def net_sell(price: float, qty: float, entry: float,
             fee_side_pct: float, slip_pct: float = 0.0) -> float:
    """Netto P&L van een (deel)verkoop incl. fees op BEIDE zijden + slippage."""
    px = price * (1.0 - slip_pct / 100.0)
    gross = (px - entry) * qty
    fees = (entry * qty + px * qty) * fee_side_pct / 100.0
    return gross - fees


# --------------------------------------------------------------------------- #
# één afgesloten bar verwerken (zelfde logica als backtest.run_v2)
# --------------------------------------------------------------------------- #
def process_bar(st: dict, cfg: StrategyConfig, sym: str, window: list[Candle],
                regime: MarketRegime, bar_idx: int,
                gate: EntryGate, riskm: RiskModel, manager: PositionManager) -> None:
    fee_side = st["fee_side_pct"]
    bar = window[-1]
    positions, pending = st["positions"], st["pending"]

    # ---- pending signaal van de vorige bar: vul op de open ---------------- #
    if sym in pending and sym not in positions:
        p = pending.pop(sym)
        dec = EntryDecision(True, p["score"], [], stop_price=p["stop_price"],
                            take_profit=p["take_profit"], atr_value=p["atr_value"])
        plan = riskm.plan(sym, st["equity"], dec, price=bar.open)
        if plan:
            positions[sym] = {
                "entry": plan.entry, "stop": plan.stop, "qty": plan.quantity,
                "orig_qty": plan.quantity, "risk_per_unit": plan.entry - plan.stop,
                "tp_levels": [[p_, f_] for p_, f_ in plan.tp_levels],
                "bars_held": 0, "break_even": False, "realized": 0.0,
                "opened": bar.ts,
            }
            log(f"KOOP  {sym}: {plan.quantity:.6f} @ €{plan.entry:.4f} "
                f"(stop €{plan.stop:.4f}, risico €{plan.risk_amount:.2f}, "
                f"score {p['score']:.0f})")
        else:
            log(f"skip {sym}: signaal verviel bij planning (notional/stop)")
    pending.pop(sym, None)

    # ---- open positie beheren --------------------------------------------- #
    pos = positions.get(sym)
    if pos:
        pos["bars_held"] += 1
        risk_amt = pos["risk_per_unit"] * pos["orig_qty"]

        def close(fill: float, reason: str, slip: float = 0.0) -> None:
            pnl = pos["realized"] + net_sell(fill, pos["qty"], pos["entry"],
                                             fee_side, slip)
            st["equity"] += pnl
            r = pnl / risk_amt if risk_amt > 0 else 0.0
            st["trades"].append({"sym": sym, "entry": pos["entry"], "exit": fill,
                                 "reason": reason, "r": round(r, 3),
                                 "pnl": round(pnl, 4), "opened": pos["opened"],
                                 "closed": bar.ts})
            if pnl < 0:
                st["cooldown"][sym] = bar_idx
            del positions[sym]
            log(f"SLUIT {sym}: {reason} @ €{fill:.4f} → {pnl:+.2f} EUR "
                f"({r:+.2f}R) | equity €{st['equity']:.2f}")

        if bar.open <= pos["stop"]:                       # gap onder de stop
            close(bar.open, "gap_stop")
            return
        if bar.low <= pos["stop"]:                        # intrabar stop
            close(pos["stop"], "stop", STOP_SLIPPAGE_PCT)
            return

        for tp_price, frac in list(pos["tp_levels"]):     # TP's (limit, geen slip)
            if bar.high >= tp_price:
                part_qty = min(pos["orig_qty"] * frac, pos["qty"])
                pnl = net_sell(tp_price, part_qty, pos["entry"], fee_side)
                pos["realized"] += pnl
                pos["qty"] -= part_qty
                pos["tp_levels"].remove([tp_price, frac])
                if not pos["tp_levels"] or pos["qty"] <= 1e-12:
                    total, pos["realized"] = pos["realized"], 0.0
                    st["equity"] += total
                    r = total / risk_amt if risk_amt > 0 else 0.0
                    st["trades"].append({"sym": sym, "entry": pos["entry"],
                                         "exit": tp_price, "reason": "take_profit",
                                         "r": round(r, 3), "pnl": round(total, 4),
                                         "opened": pos["opened"], "closed": bar.ts})
                    del positions[sym]
                    log(f"SLUIT {sym}: take_profit @ €{tp_price:.4f} → "
                        f"{total:+.2f} EUR ({r:+.2f}R) | equity €{st['equity']:.2f}")
                    return
                pos["stop"] = max(pos["stop"], pos["entry"])
                pos["break_even"] = True
                log(f"TP1   {sym}: {frac:.0%} verkocht @ €{tp_price:.4f} "
                    f"({pnl:+.2f} EUR), stop → break-even")

        d = manager.manage(entry_price=pos["entry"], stop_loss=pos["stop"],
                           break_even_armed=pos["break_even"],
                           bars_held=pos["bars_held"], candles=window,
                           regime=regime)
        if d.action is ManageAction.EXIT_NOW:
            close(bar.close, d.reason.split(":")[0], STOP_SLIPPAGE_PCT / 2)
            return
        if d.action is ManageAction.RAISE_STOP and d.new_stop:
            new = max(pos["stop"], d.new_stop)
            if new > pos["stop"]:
                pos["stop"] = new
                if new >= pos["entry"]:
                    pos["break_even"] = True
                log(f"STOP↑ {sym}: → €{new:.4f} ({d.reason})")

    # ---- nieuw signaal? ---------------------------------------------------- #
    if sym not in positions and len(positions) < cfg.max_open_positions:
        last_loss = st["cooldown"].get(sym)
        if last_loss is not None and bar_idx - last_loss < cfg.cooldown_bars_after_stop:
            return
        dec = gate.evaluate(sym, window, regime=regime)
        if dec.allowed:
            pending[sym] = {"score": dec.score, "stop_price": dec.stop_price,
                            "take_profit": dec.take_profit,
                            "atr_value": dec.atr_value}
            log(f"SIGNAAL {sym}: score {dec.score:.0f} — koop op volgende open "
                f"(stop €{dec.stop_price:.4f})")
        elif dec.score >= 65:
            # echte dip in uptrend, maar door een kwaliteits-/kostenfilter geweigerd
            log(f"bijna {sym}: score {dec.score:.0f} geweigerd — "
                + "; ".join(dec.reasons[-2:]))


# --------------------------------------------------------------------------- #
# runs
# --------------------------------------------------------------------------- #
def run_once(st: dict) -> None:
    cfg = StrategyConfig(fee_pct_round_trip=2 * st["fee_side_pct"])
    gate, riskm = EntryGate(cfg), RiskModel(cfg)
    manager, guard = PositionManager(cfg), CrashGuard(cfg)
    interval = st["interval"]
    ms_per = MS_PER[interval]
    sec_per = ms_per / 1000
    now_ms = time.time() * 1000

    series: dict[str, list[Candle]] = {}
    for m in st["markets"]:
        try:
            candles = fetch(m, interval)
        except Exception as e:                    # netwerk-hik: sla deze run over
            log(f"FOUT: fetch {m} mislukt ({e}) — run overgeslagen")
            return
        # alleen afgesloten bars
        series[m] = [c for c in candles if c.ts * 1000 + ms_per <= now_ms]
        time.sleep(0.15)
    btc = series.get("BTC-EUR") or next(iter(series.values()))

    ts_index = {m: {c.ts: i for i, c in enumerate(cs)} for m, cs in series.items()}
    new_ts = [c.ts for c in btc if c.ts > st["last_ts"]]
    if not new_ts:
        return                                    # nog geen nieuwe bar — stil klaar

    warmup = cfg.ema_slow + 5
    for ts in new_ts:
        bar_idx = int(ts // sec_per)
        bi = ts_index["BTC-EUR"].get(ts) if "BTC-EUR" in ts_index else None
        btc_win = (btc[: bi + 1] if bi is not None else btc)
        regime = guard.market_regime(btc_win[-cfg.market_window_bars - 2:])
        for sym, candles in series.items():
            idx = ts_index[sym].get(ts)
            if idx is None or idx + 1 < warmup:
                continue
            process_bar(st, cfg, sym, candles[: idx + 1], regime, bar_idx,
                        gate, riskm, manager)
        st["last_ts"] = ts
    save_state(st)


def show_status(st: dict) -> None:
    trades = st["trades"]
    wins = [t for t in trades if t["pnl"] > 0]
    days = (time.time() - st["created"]) / 86400
    print(f"paper-portefeuille (start €{st['start_equity']:.2f}, "
          f"{days:.1f} dagen, {st['interval']}, fee {st['fee_side_pct']}%/zijde)")
    print(f"  equity   €{st['equity']:.2f}  "
          f"({st['equity'] - st['start_equity']:+.2f})")
    print(f"  trades   {len(trades)}  (winst: {len(wins)}, "
          f"verlies: {len(trades) - len(wins)})")
    if trades:
        rs = [t["r"] for t in trades]
        print(f"  gem R    {sum(rs) / len(rs):+.2f}   slechtste {min(rs):+.2f}R")
    if st["positions"]:
        print("  open posities:")
        for sym, p in st["positions"].items():
            try:
                last = fetch(sym, st["interval"], limit=2)[-1].close
                upnl = net_sell(last, p["qty"], p["entry"], st["fee_side_pct"])
                extra = f"laatste €{last:.4f}, ongerealiseerd {upnl:+.2f} EUR"
            except Exception:
                extra = "koers niet opgehaald"
            print(f"    {sym}: {p['qty']:.6f} @ €{p['entry']:.4f} "
                  f"(stop €{p['stop']:.4f}) — {extra}")
    else:
        print("  open posities: geen (dat is normaal — de gate is streng)")
    for t in trades[-10:]:
        when = datetime.fromtimestamp(t["closed"], timezone.utc).strftime("%d/%m %H:%M")
        print(f"    {when}  {t['sym']:<9} {t['reason']:<12} "
              f"{t['r']:+.2f}R  {t['pnl']:+.2f} EUR")


def init_state(args: argparse.Namespace) -> dict:
    st = {
        "created": time.time(),
        "interval": args.interval,
        "fee_side_pct": 0.15 if args.maker else 0.25,
        "markets": [m.strip() for m in args.markets.split(",") if m.strip()],
        "start_equity": args.equity,
        "equity": args.equity,
        "last_ts": 0.0,
        "positions": {}, "pending": {}, "cooldown": {}, "trades": [],
    }
    # vers beginnen: geen backfill — start bij de op één na laatste dichte bar,
    # zodat de eerste run meteen één bar verwerkt
    try:
        candles = fetch(st["markets"][0], st["interval"], limit=5)
        ms_per = MS_PER[st["interval"]]
        closed = [c for c in candles if c.ts * 1000 + ms_per <= time.time() * 1000]
        if len(closed) >= 2:
            st["last_ts"] = closed[-2].ts
    except Exception:
        pass
    save_state(st)
    log(f"INIT: paper-trader gestart — €{st['equity']:.2f}, {st['interval']}, "
        f"fee {st['fee_side_pct']}%/zijde, {len(st['markets'])} markten")
    return st


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--once", action="store_true",
                      help="verwerk nieuwe candles en stop (voor cron)")
    mode.add_argument("--loop", action="store_true",
                      help="blijf draaien; wordt elke bar wakker")
    mode.add_argument("--status", action="store_true",
                      help="toon portefeuille + laatste trades")
    mode.add_argument("--reset", action="store_true",
                      help="verwijder state en begin opnieuw")
    ap.add_argument("--maker", action="store_true",
                    help="(alleen eerste run) limit-order fees 0.15%%/zijde")
    ap.add_argument("--interval", default="1h", choices=list(MS_PER),
                    help="(alleen eerste run) candle-interval")
    ap.add_argument("--markets", default=",".join(DEFAULT_MARKETS),
                    help="(alleen eerste run) komma-gescheiden markten")
    ap.add_argument("--equity", type=float, default=100.0,
                    help="(alleen eerste run) startbedrag in EUR")
    args = ap.parse_args()

    if args.reset:
        for f in (STATE_FILE,):
            if os.path.exists(f):
                os.remove(f)
        print("state verwijderd — volgende run begint vers")
        return

    st = load_state()
    if st is None:
        st = init_state(args)
    if args.status:
        show_status(st)
        return

    if args.loop:
        ms_per = MS_PER[st["interval"]]
        while True:
            run_once(st)
            st = load_state()                     # herlaad (voor --reset e.d.)
            if st is None:
                return
            # slaap tot 90s ná de volgende bar-close
            now = time.time()
            nxt = (int(now * 1000 // ms_per) + 1) * ms_per / 1000 + 90
            time.sleep(max(60.0, nxt - now))
    else:
        run_once(st)


if __name__ == "__main__":
    main()
