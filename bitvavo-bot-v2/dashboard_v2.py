"""Web-dashboard voor de paper-trader — leest paper_state_v2.json, read-only.

Start op de VPS (in de map met paper_state_v2.json):

    python3 dashboard_v2.py                  # http://<vps-ip>:8787
    python3 dashboard_v2.py --port 9000
    python3 dashboard_v2.py --host 127.0.0.1 # alleen lokaal (SSH-tunnel)

Het toont alleen papieren data en kan niets wijzigen of handelen.
De pagina ververst zichzelf elke 60 seconden.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

STATE_FILE = "paper_state_v2.json"
LOG_FILE = "paper_log_v2.txt"

_price_cache: dict[str, tuple[float, float]] = {}   # sym -> (ts, prijs)


def last_price(market: str) -> float | None:
    now = time.time()
    hit = _price_cache.get(market)
    if hit and now - hit[0] < 60:
        return hit[1]
    try:
        url = f"https://api.bitvavo.com/v2/ticker/price?market={market}"
        with urllib.request.urlopen(url, timeout=5) as r:
            px = float(json.loads(r.read())["price"])
        _price_cache[market] = (now, px)
        return px
    except Exception:
        return hit[1] if hit else None


def load_state() -> dict | None:
    if not os.path.exists(STATE_FILE):
        return None
    with open(STATE_FILE) as f:
        return json.load(f)


def log_tail(n: int = 30) -> list[str]:
    if not os.path.exists(LOG_FILE):
        return []
    with open(LOG_FILE) as f:
        return [ln.rstrip() for ln in f.readlines()[-n:]]


def gate_activity() -> dict[str, dict[str, int]]:
    """Telt per markt de gate-gebeurtenissen uit het volledige logboek."""
    acts: dict[str, dict[str, int]] = {}
    if not os.path.exists(LOG_FILE):
        return acts
    with open(LOG_FILE) as f:
        for ln in f:
            parts = ln.split()
            if len(parts) < 4:
                continue
            kind, sym = parts[2].rstrip(":"), parts[3].rstrip(":")
            key = {"SIGNAAL": "signalen", "KOOP": "koop",
                   "bijna": "bijna", "SLUIT": "sluit"}.get(kind)
            if key and "-" in sym:
                acts.setdefault(sym, {"bijna": 0, "signalen": 0,
                                      "koop": 0, "sluit": 0})[key] += 1
    return acts


def max_drawdown(pts: list[tuple[float, float]]) -> float:
    peak, mdd = pts[0][1], 0.0
    for _, v in pts:
        peak = max(peak, v)
        if peak > 0:
            mdd = max(mdd, (peak - v) / peak)
    return mdd


def cooldown_left_h(st: dict, sym: str) -> float:
    """Resterende cooldown-uren voor een markt, 0 als vrij."""
    last = st.get("cooldown", {}).get(sym)
    if last is None:
        return 0.0
    sec_per = {"1h": 3600, "2h": 7200, "4h": 14400}.get(st["interval"], 3600)
    bars_gone = time.time() / sec_per - last
    left = (COOLDOWN_BARS - bars_gone) * sec_per / 3600
    return max(0.0, left)


try:                                    # strategie-module voor de coin-pagina
    from rsi_dip_buyer_v2 import (Candle, CrashGuard, EntryGate, MarketRegime,
                                  StrategyConfig, atr, ema, rsi)
    COOLDOWN_BARS = StrategyConfig().cooldown_bars_after_stop
    HAVE_STRATEGY = True
except Exception:
    COOLDOWN_BARS = 48
    HAVE_STRATEGY = False

_candle_cache: dict[tuple[str, str], tuple[float, list]] = {}
MS_PER = {"1h": 3_600_000, "2h": 7_200_000, "4h": 14_400_000}


def fetch_candles(market: str, interval: str, limit: int = 400) -> list:
    """Afgesloten candles via de publieke API, 4 min gecachet."""
    key, now = (market, interval), time.time()
    hit = _candle_cache.get(key)
    if hit and now - hit[0] < 240:
        return hit[1]
    url = (f"https://api.bitvavo.com/v2/{market}/candles"
           f"?interval={interval}&limit={limit}")
    with urllib.request.urlopen(url, timeout=10) as r:
        rows = json.loads(r.read())
    rows.sort(key=lambda x: x[0])
    ms = MS_PER.get(interval, 3_600_000)
    candles = [Candle(r0[0] / 1000, float(r0[1]), float(r0[2]),
                      float(r0[3]), float(r0[4]), float(r0[5]))
               for r0 in rows if r0[0] + ms <= now * 1000]
    _candle_cache[key] = (now, candles)
    return candles


STYLE = """
:root {
  --page: #0d0d0d; --surface: #1a1a19; --border: rgba(255,255,255,0.10);
  --ink: #ffffff; --ink-2: #c3c2b7; --muted: #898781;
  --grid: #2c2c2a; --baseline: #383835; --series: #3987e5;
  --up: #0ca30c; --down: #d03b3b;
}
* { box-sizing: border-box; margin: 0; }
body { background: var(--page); color: var(--ink-2);
       font: 14px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif;
       padding: 20px; max-width: 960px; margin: 0 auto; }
h1 { color: var(--ink); font-size: 18px; }
h2 { color: var(--ink); font-size: 14px; margin: 24px 0 8px; }
a { color: var(--series); text-decoration: none; }
a:hover { text-decoration: underline; }
.meta { color: var(--muted); font-size: 12px; margin-bottom: 16px; }
.tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
          gap: 8px; margin-bottom: 16px; }
.tile { background: var(--surface); border: 1px solid var(--border);
         border-radius: 8px; padding: 10px 12px; }
.tile .lbl { font-size: 11px; color: var(--muted); }
.tile .val { font-size: 18px; color: var(--ink); margin-top: 2px; }
.tile .sub { font-size: 12px; color: var(--muted); }
.card { background: var(--surface); border: 1px solid var(--border);
         border-radius: 8px; padding: 12px; overflow-x: auto; }
svg { width: 100%; height: auto; display: block; }
.axis { fill: var(--muted); font-size: 11px;
         font-family: system-ui, sans-serif; }
table { width: 100%; border-collapse: collapse; }
th { text-align: left; color: var(--muted); font-size: 11px;
      font-weight: 500; padding: 4px 8px; border-bottom: 1px solid var(--baseline); }
td { padding: 5px 8px; border-bottom: 1px solid var(--grid); }
tr:last-child td { border-bottom: none; }
.num { font-variant-numeric: tabular-nums; text-align: right; }
th.num { text-align: right; }
.up { color: var(--up); } .down { color: var(--down); }
.note { color: var(--muted); font-size: 12px; }
.empty { color: var(--muted); text-align: center; padding: 14px; }
.log { font: 12px/1.7 ui-monospace, monospace; color: var(--ink-2);
        max-height: 320px; overflow-y: auto; }
.disclaimer { color: var(--muted); font-size: 11px; margin-top: 16px; }
.verdict { font: 13px/1.7 ui-monospace, monospace; }
.verdict .ok { color: var(--up); } .verdict .no { color: var(--down); }
"""


def fmt_ts(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%d/%m %H:%M")


def equity_points(st: dict) -> list[tuple[float, float]]:
    """Stappenreeks: start-equity + cumulatieve P&L per gesloten trade."""
    pts = [(st["created"], st["start_equity"])]
    eq = st["start_equity"]
    for t in sorted(st["trades"], key=lambda x: x["closed"]):
        eq += t["pnl"]
        pts.append((t["closed"], eq))
    pts.append((time.time(), eq))
    return pts


def svg_equity(st: dict) -> str:
    pts = equity_points(st)
    w, h, pad_l, pad_r, pad_t, pad_b = 860, 240, 56, 16, 14, 26
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    x0, x1 = min(xs), max(xs)
    lo, hi = min(ys + [st["start_equity"]]), max(ys + [st["start_equity"]])
    span = max(hi - lo, 0.5)
    lo, hi = lo - span * 0.15, hi + span * 0.15

    def X(t: float) -> float:
        return pad_l + (w - pad_l - pad_r) * ((t - x0) / max(x1 - x0, 1))

    def Y(v: float) -> float:
        return pad_t + (h - pad_t - pad_b) * (1 - (v - lo) / (hi - lo))

    # stappenpad (equity verandert alleen op een trade-close)
    d = f"M {X(pts[0][0]):.1f} {Y(pts[0][1]):.1f}"
    for i in range(1, len(pts)):
        d += f" H {X(pts[i][0]):.1f} V {Y(pts[i][1]):.1f}"

    grid, labels = [], []
    for frac in (0.0, 0.5, 1.0):
        v = lo + (hi - lo) * frac
        y = Y(v)
        grid.append(f'<line x1="{pad_l}" y1="{y:.1f}" x2="{w - pad_r}" '
                    f'y2="{y:.1f}" stroke="var(--grid)" stroke-width="1"/>')
        labels.append(f'<text x="{pad_l - 8}" y="{y + 4:.1f}" text-anchor="end" '
                      f'class="axis">€{v:.2f}</text>')
    y_start = Y(st["start_equity"])
    startline = (f'<line x1="{pad_l}" y1="{y_start:.1f}" x2="{w - pad_r}" '
                 f'y2="{y_start:.1f}" stroke="var(--baseline)" '
                 'stroke-width="1" stroke-dasharray="4 4"/>')
    for frac in (0.0, 0.5, 1.0):
        t = x0 + (x1 - x0) * frac
        anchor = "start" if frac == 0 else ("end" if frac == 1 else "middle")
        labels.append(f'<text x="{X(t):.1f}" y="{h - 8}" text-anchor="{anchor}" '
                      f'class="axis">{fmt_ts(t)}</text>')

    dots = "".join(
        f'<circle cx="{X(t["closed"]):.1f}" '
        f'cy="{Y(v):.1f}" r="4" fill="var(--series)" stroke="var(--surface)" '
        f'stroke-width="2"><title>{html.escape(t["sym"])} {t["reason"]} '
        f'{t["r"]:+.2f}R → €{v:.2f}</title></circle>'
        for t, v in zip(sorted(st["trades"], key=lambda x: x["closed"]),
                        [p[1] for p in pts[1:-1]])
    )
    return (f'<svg viewBox="0 0 {w} {h}" role="img" '
            'aria-label="Equity-verloop van de paper-portefeuille">'
            + "".join(grid) + startline
            + f'<path d="{d}" fill="none" stroke="var(--series)" '
              'stroke-width="2" stroke-linejoin="round"/>'
            + dots + "".join(labels) + "</svg>")


def svg_snapshots(st: dict) -> str:
    """Lijn van de bar-close snapshots (equity incl. open posities)."""
    snaps = st.get("snapshots", [])
    if len(snaps) < 2:
        return ('<div class="empty">nog geen snapshots — vullen zich vanzelf '
                'zodra de trader nieuwe bars verwerkt</div>')
    snaps = snaps[:: max(1, len(snaps) // 700)]
    w, h, pad_l, pad_r, pad_t, pad_b = 860, 240, 56, 16, 14, 26
    xs, ys = [s[0] for s in snaps], [s[1] for s in snaps]
    x0, x1 = xs[0], xs[-1]
    lo, hi = min(ys + [st["start_equity"]]), max(ys + [st["start_equity"]])
    span = max(hi - lo, 0.5)
    lo, hi = lo - span * 0.15, hi + span * 0.15

    def X(t: float) -> float:
        return pad_l + (w - pad_l - pad_r) * ((t - x0) / max(x1 - x0, 1))

    def Y(v: float) -> float:
        return pad_t + (h - pad_t - pad_b) * (1 - (v - lo) / (hi - lo))

    d = "M " + " L ".join(f"{X(t):.1f} {Y(v):.1f}" for t, v in snaps)
    grid, labels = [], []
    for frac in (0.0, 0.5, 1.0):
        v = lo + (hi - lo) * frac
        y = Y(v)
        grid.append(f'<line x1="{pad_l}" y1="{y:.1f}" x2="{w - pad_r}" '
                    f'y2="{y:.1f}" stroke="var(--grid)" stroke-width="1"/>')
        labels.append(f'<text x="{pad_l - 8}" y="{y + 4:.1f}" text-anchor="end" '
                      f'class="axis">€{v:.2f}</text>')
        t = x0 + (x1 - x0) * frac
        anchor = "start" if frac == 0 else ("end" if frac == 1 else "middle")
        labels.append(f'<text x="{X(t):.1f}" y="{h - 8}" text-anchor="{anchor}" '
                      f'class="axis">{fmt_ts(t)}</text>')
    y_start = Y(st["start_equity"])
    startline = (f'<line x1="{pad_l}" y1="{y_start:.1f}" x2="{w - pad_r}" '
                 f'y2="{y_start:.1f}" stroke="var(--baseline)" '
                 'stroke-width="1" stroke-dasharray="4 4"/>')
    return (f'<svg viewBox="0 0 {w} {h}" role="img" '
            'aria-label="Equity inclusief open posities, per verwerkte bar">'
            + "".join(grid) + startline
            + f'<path d="{d}" fill="none" stroke="var(--series)" '
              'stroke-width="2" stroke-linejoin="round"/>'
            + "".join(labels) + "</svg>")


def svg_symbol_bars(trades: list[dict]) -> str:
    """Horizontale staafjes: netto P&L per symbool (groen winst, rood verlies)."""
    per: dict[str, float] = {}
    for t in trades:
        per[t["sym"]] = per.get(t["sym"], 0.0) + t["pnl"]
    if not per:
        return '<div class="empty">nog geen afgesloten trades</div>'
    items = sorted(per.items(), key=lambda kv: -kv[1])
    v_lo = min(0.0, min(per.values()))
    v_hi = max(0.0, max(per.values()))
    # extra linkerruimte als er negatieve staven zijn: symbool + waarde-label
    w, row_h, gap, pad_r, pad_t = 860, 22, 8, 76, 6
    pad_l = 160 if v_lo < 0 else 96
    h = pad_t * 2 + len(items) * (row_h + gap) - gap
    span = max(v_hi - v_lo, 0.01)

    def X(v: float) -> float:
        return pad_l + (w - pad_l - pad_r) * ((v - v_lo) / span)

    x_zero = X(0.0)
    parts = [f'<line x1="{x_zero:.1f}" y1="{pad_t}" x2="{x_zero:.1f}" '
             f'y2="{h - pad_t}" stroke="var(--baseline)" stroke-width="1"/>']
    for i, (sym, v) in enumerate(items):
        y = pad_t + i * (row_h + gap)
        x = min(x_zero, X(v))
        bw = abs(X(v) - x_zero)
        color = ("var(--up)" if v > 0
                 else ("var(--down)" if v < 0 else "var(--baseline)"))
        lbl_x = X(v) + (6 if v >= 0 else -6)
        anchor = "start" if v >= 0 else "end"
        parts.append(
            f'<rect x="{x:.1f}" y="{y}" width="{max(bw, 1):.1f}" '
            f'height="{row_h}" rx="4" fill="{color}">'
            f'<title>{html.escape(sym)}: {v:+.2f} EUR</title></rect>'
            f'<text x="8" y="{y + row_h - 6}" text-anchor="start" '
            f'class="axis" fill="var(--ink-2)">{html.escape(sym)}</text>'
            f'<text x="{lbl_x:.1f}" y="{y + row_h - 6}" text-anchor="{anchor}" '
            f'class="axis">{v:+.2f}</text>')
    return (f'<svg viewBox="0 0 {w} {h}" role="img" '
            'aria-label="Netto P&L per symbool">' + "".join(parts) + "</svg>")


def pnl_cell(val: float, suffix: str = " EUR") -> str:
    if val > 0:
        return f'<td class="num up">▲ +{val:.2f}{suffix}</td>'
    if val < 0:
        return f'<td class="num down">▼ {val:.2f}{suffix}</td>'
    return f'<td class="num">0.00{suffix}</td>'


def svg_price(st: dict, sym: str, candles: list) -> str:
    """Koerslijn met entry/exit-markers en (open) stop-niveau."""
    candles = candles[-300:]
    if len(candles) < 2:
        return '<div class="empty">te weinig koersdata</div>'
    w, h, pad_l, pad_r, pad_t, pad_b = 860, 280, 64, 16, 14, 26
    x0, x1 = candles[0].ts, candles[-1].ts
    pos = st["positions"].get(sym)
    lows = [c.low for c in candles] + ([pos["stop"]] if pos else [])
    highs = [c.high for c in candles]
    lo, hi = min(lows), max(highs)
    span = max(hi - lo, 1e-9)
    lo, hi = lo - span * 0.08, hi + span * 0.08

    def X(t: float) -> float:
        return pad_l + (w - pad_l - pad_r) * ((t - x0) / max(x1 - x0, 1))

    def Y(v: float) -> float:
        return pad_t + (h - pad_t - pad_b) * (1 - (v - lo) / (hi - lo))

    d = "M " + " L ".join(f"{X(c.ts):.1f} {Y(c.close):.1f}" for c in candles)
    grid, labels = [], []
    for frac in (0.0, 0.5, 1.0):
        v = lo + (hi - lo) * frac
        grid.append(f'<line x1="{pad_l}" y1="{Y(v):.1f}" x2="{w - pad_r}" '
                    f'y2="{Y(v):.1f}" stroke="var(--grid)" stroke-width="1"/>')
        labels.append(f'<text x="{pad_l - 8}" y="{Y(v) + 4:.1f}" '
                      f'text-anchor="end" class="axis">€{v:.4g}</text>')
        t = x0 + (x1 - x0) * frac
        anchor = "start" if frac == 0 else ("end" if frac == 1 else "middle")
        labels.append(f'<text x="{X(t):.1f}" y="{h - 8}" text-anchor="{anchor}" '
                      f'class="axis">{fmt_ts(t)}</text>')

    marks = []
    for t in st["trades"]:
        if t["sym"] != sym:
            continue
        if x0 <= t["opened"] <= x1:
            marks.append(f'<circle cx="{X(t["opened"]):.1f}" '
                         f'cy="{Y(t["entry"]):.1f}" r="4" fill="none" '
                         'stroke="var(--ink-2)" stroke-width="2">'
                         f'<title>entry @ €{t["entry"]:.4f}</title></circle>')
        if x0 <= t["closed"] <= x1:
            col = "var(--up)" if t["pnl"] > 0 else "var(--down)"
            marks.append(f'<circle cx="{X(t["closed"]):.1f}" '
                         f'cy="{Y(t["exit"]):.1f}" r="5" fill="{col}" '
                         'stroke="var(--surface)" stroke-width="2">'
                         f'<title>{t["reason"]} {t["r"]:+.2f}R @ '
                         f'€{t["exit"]:.4f}</title></circle>')
    if pos:
        ys = Y(pos["stop"])
        marks.append(f'<line x1="{pad_l}" y1="{ys:.1f}" x2="{w - pad_r}" '
                     f'y2="{ys:.1f}" stroke="var(--down)" stroke-width="1" '
                     'stroke-dasharray="5 4"/>'
                     f'<text x="{w - pad_r}" y="{ys - 5:.1f}" text-anchor="end" '
                     f'class="axis" fill="var(--down)">stop €{pos["stop"]:.4f}'
                     '</text>')
        marks.append(f'<circle cx="{X(max(x0, pos["opened"])):.1f}" '
                     f'cy="{Y(pos["entry"]):.1f}" r="5" fill="var(--series)" '
                     'stroke="var(--surface)" stroke-width="2">'
                     f'<title>open positie @ €{pos["entry"]:.4f}</title></circle>')
    legend = ('<div class="meta" style="margin-top:8px">○ entry · '
              '<span class="up">●</span>/<span class="down">●</span> exit '
              '(winst/verlies) · <span style="color:var(--series)">●</span> '
              'open positie · rode stippellijn = actuele stop</div>')
    return (f'<svg viewBox="0 0 {w} {h}" role="img" '
            f'aria-label="Koersverloop {html.escape(sym)} met trades">'
            + "".join(grid)
            + f'<path d="{d}" fill="none" stroke="var(--series)" '
              'stroke-width="2" stroke-linejoin="round"/>'
            + "".join(marks) + "".join(labels) + "</svg>") + legend


def render_coin(st: dict, sym: str) -> str:
    """Detailpagina voor één markt."""
    back = '<div class="meta"><a href="/">← terug naar overzicht</a></div>'
    if not HAVE_STRATEGY:
        return (f"<!doctype html><style>{STYLE}</style><body>{back}"
                "<h1>rsi_dip_buyer_v2.py niet gevonden</h1>"
                "<p>Zet dashboard_v2.py in dezelfde map als de strategie."
                "</p></body>")
    try:
        candles = fetch_candles(sym, st["interval"])
        btc = (candles if sym == "BTC-EUR"
               else fetch_candles("BTC-EUR", st["interval"]))
    except Exception as e:
        return (f"<!doctype html><style>{STYLE}</style><body>{back}"
                f"<h1>{html.escape(sym)}</h1><div class='card empty'>"
                f"koersdata ophalen mislukt: {html.escape(str(e))}</div></body>")

    cfg = StrategyConfig(fee_pct_round_trip=2 * st["fee_side_pct"])
    regime = CrashGuard(cfg).market_regime(btc[-cfg.market_window_bars - 2:])
    dec = EntryGate(cfg).evaluate(sym, candles, regime=regime)

    closes = [c.close for c in candles]
    price = closes[-1]
    rs = rsi(closes, cfg.rsi_period)
    ats = atr(candles, cfg.atr_period)
    e50 = ema(closes, cfg.ema_fast)
    e200 = ema(closes, cfg.ema_slow)
    atr_pct = 100.0 * ats[-1] / price if ats else 0.0
    uptrend = bool(e200) and price > e200[-1] and e50[-1] > e200[-1]
    min_stop_pct = ((2 * st["fee_side_pct"] + 0.35) / cfg.max_cost_per_risk
                    if getattr(cfg, "max_cost_per_risk", 0) else 0.0)

    sym_trades = [t for t in st["trades"] if t["sym"] == sym]
    sym_wins = [t for t in sym_trades if t["pnl"] > 0]
    pnl_sum = sum(t["pnl"] for t in sym_trades)
    cd = cooldown_left_h(st, sym)
    pos = st["positions"].get(sym)

    stat = lambda label, value, cls="", sub="": (  # noqa: E731
        f'<div class="tile"><div class="lbl">{label}</div>'
        f'<div class="val {cls}">{value}</div>'
        + (f'<div class="sub">{sub}</div>' if sub else "") + "</div>")
    tiles = (
        stat("Laatste koers", f"€{price:.4g}",
             sub=f"slot {fmt_ts(candles[-1].ts)}") +
        stat("RSI (14)", f"{rs[-1]:.0f}" if rs else "—",
             sub=f"dip-drempel &lt; {cfg.rsi_dip_level:.0f}") +
        stat("ATR", f"{atr_pct:.2f}%",
             "" if atr_pct * cfg.stop_atr_mult >= min_stop_pct else "down",
             sub=f"stop wordt {atr_pct * cfg.stop_atr_mult:.2f}% · gate eist "
                 f"≥ {min_stop_pct:.2f}%") +
        stat("Trend", "↑ up" if uptrend else "↓ down",
             "up" if uptrend else "down",
             sub="close vs EMA200 én EMA50&gt;EMA200") +
        stat("BTC-regime", regime.value,
             "down" if str(regime.value).lower() == "bear" else "") +
        stat("Cooldown", f"{cd:.0f}u" if cd > 0 else "vrij",
             "down" if cd > 0 else "") +
        stat("P&amp;L dit symbool", f"{pnl_sum:+.2f} EUR",
             "up" if pnl_sum > 0 else ("down" if pnl_sum < 0 else ""),
             sub=(f"{len(sym_trades)} trades · "
                  f"{len(sym_wins)}/{len(sym_trades)} winst"
                  if sym_trades else "nog geen trades")) +
        stat("Positie", "open" if pos else "geen",
             "up" if pos else "",
             sub=(f"entry €{pos['entry']:.4g} · stop €{pos['stop']:.4g}"
                  if pos else "")))

    verdict_head = ('<span class="ok">✔ KOOP-signaal — wacht op fill bij '
                    'volgende bar-open</span>' if dec.allowed else
                    '<span class="no">✘ geen koop op dit moment</span>')
    verdict_lines = "".join(f"<div>· {html.escape(r)}</div>"
                            for r in dec.reasons) or "<div>· geen dip actief</div>"

    trade_rows = "".join(
        f'<tr><td class="num">{fmt_ts(t["closed"])}</td>'
        f'<td>{html.escape(t["reason"])}</td>'
        f'<td class="num">€{t["entry"]:.4f}</td>'
        f'<td class="num">€{t["exit"]:.4f}</td>'
        f'<td class="num">{"€" + format(t["fees"], ".2f") if "fees" in t else "—"}</td>'
        f'<td class="num">{t["r"]:+.2f}R</td>{pnl_cell(t["pnl"])}</tr>'
        for t in sorted(sym_trades, key=lambda x: -x["closed"])) or (
        "<tr><td colspan='7' class='empty'>nog geen trades op dit symbool"
        "</td></tr>")

    base = sym.split("-")[0]
    log_rows = "".join(
        f"<div>{html.escape(ln)}</div>"
        for ln in reversed([ln for ln in log_tail(400) if base in ln][-40:]))

    now = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")
    return f"""<!doctype html>
<html lang="nl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="120">
<title>{html.escape(sym)} — paper-bot</title>
<style>{STYLE}</style></head><body>
{back}
<h1>{html.escape(sym)}</h1>
<div class="meta">nepgeld · alleen-lezen · bijgewerkt {now}</div>
<div class="tiles">{tiles}</div>
<h2>Wat vindt de gate er nú van?</h2>
<div class="card verdict">{verdict_head}
<div style="margin-top:8px">score {dec.score:.0f} / drempel
{cfg.min_quality_score:.0f}</div>{verdict_lines}</div>
<h2>Koers ({st["interval"]}, laatste {min(len(candles), 300)} bars) met trades</h2>
<div class="card">{svg_price(st, sym, candles)}</div>
<h2>Trades op {html.escape(sym)}</h2>
<div class="card"><table>
<tr><th class="num">Gesloten</th><th>Reden</th><th class="num">Entry</th>
<th class="num">Exit</th><th class="num">Fees</th><th class="num">R</th>
<th class="num">P&amp;L</th></tr>
{trade_rows}</table></div>
<h2>Logboek voor {html.escape(base)}</h2>
<div class="card log">{log_rows or '<div class="empty">nog niets gelogd</div>'}</div>
<div class="disclaimer">⚠️ Educatief — geen beleggingsadvies. Dit dashboard
kan niets kopen of verkopen.</div>
</body></html>"""


def render(st: dict | None) -> str:
    if st is None:
        return ("<!doctype html><meta charset='utf-8'>"
                "<meta http-equiv='refresh' content='30'>"
                "<body style='font-family:system-ui;background:#0d0d0d;"
                "color:#c3c2b7;padding:3rem'>"
                "<h2>Nog geen paper_state_v2.json</h2>"
                "<p>Draai eerst: <code>python3 paper_trader_v2.py --once "
                "--maker</code></p></body>")

    trades = sorted(st["trades"], key=lambda x: x["closed"], reverse=True)
    wins = [t for t in trades if t["pnl"] > 0]
    days = (time.time() - st["created"]) / 86400
    realized = st["equity"] - st["start_equity"]

    # open posities + live koers
    pos_rows, unreal_total, underwater = [], 0.0, 0
    for sym, p in st["positions"].items():
        px = last_price(sym)
        if px is not None:
            gross = (px - p["entry"]) * p["qty"]
            fees = (p["entry"] + px) * p["qty"] * st["fee_side_pct"] / 100.0
            upnl = gross - fees + p.get("realized", 0.0)
            unreal_total += upnl
            if upnl < 0:
                underwater += 1
            r = upnl / (p["risk_per_unit"] * p["orig_qty"])
            live = f'<td class="num">€{px:.4f}</td>{pnl_cell(upnl)}<td class="num">{r:+.2f}R</td>'
        else:
            live = '<td class="num">—</td><td class="num">—</td><td class="num">—</td>'
        pos_rows.append(
            f'<tr><td>{html.escape(sym)}</td>'
            f'<td class="num">{p["qty"]:.6f}</td>'
            f'<td class="num">€{p["entry"]:.4f}</td>'
            f'<td class="num">€{p["stop"]:.4f}</td>'
            f'<td class="num">{fmt_ts(p["opened"])}</td>{live}</tr>')
    pos_table = ("<tr><td colspan='8' class='empty'>geen open posities "
                 "(normaal — de gate is streng)</td></tr>"
                 if not pos_rows else "".join(pos_rows))

    trade_rows = "".join(
        f'<tr><td class="num">{fmt_ts(t["closed"])}</td>'
        f'<td>{html.escape(t["sym"])}</td>'
        f'<td>{html.escape(t["reason"])}</td>'
        f'<td class="num">€{t["entry"]:.4f}</td>'
        f'<td class="num">€{t["exit"]:.4f}</td>'
        f'<td class="num">{"€" + format(t["fees"], ".2f") if "fees" in t else "—"}</td>'
        f'<td class="num">{t["r"]:+.2f}R</td>{pnl_cell(t["pnl"])}</tr>'
        for t in trades) or ("<tr><td colspan='8' class='empty'>nog geen "
                             "afgesloten trades</td></tr>")

    log_rows = "".join(f"<div>{html.escape(ln)}</div>"
                       for ln in reversed(log_tail()))

    rs = [t["r"] for t in trades]
    losses = [t for t in trades if t["pnl"] <= 0]
    win_sum = sum(t["pnl"] for t in wins)
    loss_sum = abs(sum(t["pnl"] for t in losses))
    pf = win_sum / loss_sum if loss_sum > 0 else (float("inf") if wins else 0.0)
    avg_w = (sum(t["r"] for t in wins) / len(wins)) if wins else 0.0
    avg_l = (sum(t["r"] for t in losses) / len(losses)) if losses else 0.0
    payoff = avg_w / abs(avg_l) if avg_l < 0 else 0.0
    be_winrate = 1.0 / (1.0 + payoff) if payoff > 0 else None
    winrate = len(wins) / len(trades) if trades else None
    fees_total = sum(t.get("fees", 0.0) for t in trades)
    mdd = max_drawdown(equity_points(st))

    stat = lambda label, value, cls="", sub="": (  # noqa: E731
        f'<div class="tile"><div class="lbl">{label}</div>'
        f'<div class="val {cls}">{value}</div>'
        + (f'<div class="sub">{sub}</div>' if sub else "") + "</div>")
    # prijsbewegingen (zoals de v1-analyse: gem. TP% vs gem. SL%)
    win_pct = ([(t["exit"] - t["entry"]) / t["entry"] * 100 for t in wins]
               if wins else [])
    loss_pct = ([(t["exit"] - t["entry"]) / t["entry"] * 100 for t in losses]
                if losses else [])
    avg_tp_pct = sum(win_pct) / len(win_pct) if win_pct else 0.0
    avg_sl_pct = sum(loss_pct) / len(loss_pct) if loss_pct else 0.0
    expectancy = realized / len(trades) if trades else None

    total = st["equity"] + unreal_total
    tiles = (
        stat("Equity (incl. open)", f"€{total:.2f}",
             "up" if total > st["start_equity"] else
             ("down" if total < st["start_equity"] else ""),
             f"{(total / st['start_equity'] - 1):+.2%} sinds start") +
        stat("Gerealiseerd", f"{realized:+.2f} EUR",
             "up" if realized > 0 else ("down" if realized < 0 else ""),
             (f"open {unreal_total:+.2f} EUR · " if st["positions"] else "")
             + f"waarvan €{fees_total:.2f} fees") +
        stat("Max drawdown", f"{mdd:.1%}") +
        stat("Expectancy",
             f"{expectancy:+.2f} EUR" if expectancy is not None else "—",
             ("up" if expectancy and expectancy > 0 else
              ("down" if expectancy and expectancy < 0 else "")),
             f"per trade · gem. {sum(rs) / len(rs):+.2f}R" if rs else "") +
        stat("Trades", f"{len(trades)}",
             sub=f"{len(wins)} winst · {len(losses)} verlies") +
        stat("Winrate", f"{winrate:.0%}" if winrate is not None else "—",
             sub=(f"nodig voor break-even: {be_winrate:.0%}"
                  if be_winrate else "")) +
        stat("Profit factor", "∞" if pf == float("inf") else f"{pf:.2f}",
             sub="doel &gt; 1.3 · &lt; 1 = verliesgevend") +
        stat("Payoff-ratio", f"{payoff:.2f}" if payoff > 0 else "—",
             sub=(f"TP {avg_tp_pct:+.2f}% vs SL {avg_sl_pct:+.2f}%"
                  if trades else "")) +
        stat("Gem. win / verlies",
             f"{avg_w:+.2f}R / {avg_l:+.2f}R" if trades else "—",
             sub="verlies hoort ≥ −1.4R te blijven") +
        stat("Looptijd", f"{days:.1f} dagen",
             sub=f"~{len(trades) / (days / 30):.1f} trades/maand"
                 if trades and days >= 3 else "") +
        stat("Instellingen", f"{st['interval']} · {st['fee_side_pct']}%/zijde",
             sub=f"{len(st['markets'])} markten · max risico 0.75%/trade"))

    # per markt: gate-activiteit + resultaat + cooldown
    acts = gate_activity()
    mkt_rows = []
    for m in st["markets"]:
        mt = [t for t in trades if t["sym"] == m]
        mw = [t for t in mt if t["pnl"] > 0]
        a = acts.get(m, {})
        cd = cooldown_left_h(st, m)
        pnl_sum = sum(t["pnl"] for t in mt)
        link = f'<a href="/coin/{html.escape(m)}">{html.escape(m)}</a>'
        mkt_rows.append(
            f'<tr><td>{link}</td>'
            f'<td class="num">{a.get("bijna", 0)}</td>'
            f'<td class="num">{a.get("signalen", 0)}</td>'
            f'<td class="num">{len(mt)}</td>'
            f'<td class="num">{(len(mw) / len(mt)):.0%}</td>'
            f'{pnl_cell(pnl_sum)}'
            f'<td class="num">{(sum(t["r"] for t in mt) / len(mt)):+.2f}R</td>'
            if mt else
            f'<tr><td>{link}</td>'
            f'<td class="num">{a.get("bijna", 0)}</td>'
            f'<td class="num">{a.get("signalen", 0)}</td>'
            f'<td class="num">0</td><td class="num">—</td>'
            f'<td class="num">—</td><td class="num">—</td>')
        mkt_rows[-1] += (f'<td class="num">{cd:.0f}u</td></tr>' if cd > 0
                         else '<td class="num">—</td></tr>')
    mkt_table = "".join(mkt_rows)

    # exits per reden
    reasons: dict[str, list[dict]] = {}
    for t in trades:
        reasons.setdefault(t["reason"], []).append(t)
    reason_rows = "".join(
        f'<tr><td>{html.escape(rn)}</td>'
        f'<td class="num">{len(ts_)}</td>'
        f'{pnl_cell(sum(t["pnl"] for t in ts_))}'
        f'<td class="num">{sum(t["r"] for t in ts_) / len(ts_):+.2f}R</td></tr>'
        for rn, ts_ in sorted(reasons.items(),
                              key=lambda kv: -len(kv[1]))) or (
        "<tr><td colspan='4' class='empty'>nog geen exits</td></tr>")

    pending_note = ""
    if st.get("pending"):
        syms = ", ".join(f"{html.escape(s)} (stop €{p['stop_price']:.4f})"
                         for s, p in st["pending"].items())
        pending_note = (f'<div class="meta" style="margin-top:8px">⏳ wacht op '
                        f'fill bij volgende bar-open: {syms}</div>')

    # kerncijfers-tabel (metric / waarde / toelichting), zoals de v1-analyse
    n_tp = sum(1 for t in trades if t["reason"] == "take_profit")
    n_sl = sum(1 for t in trades if t["reason"] in ("stop", "gap_stop"))
    n_other = len(trades) - n_tp - n_sl
    gross_pl = realized + fees_total
    fee_share = (f"{fees_total / (fees_total + loss_sum):.0%} van het totale "
                 "verlies" if (fees_total + loss_sum) > 0 else "—")
    cds = [(m, cooldown_left_h(st, m)) for m in st["markets"]]
    cds = [(m, hh) for m, hh in cds if hh > 0]
    check_sum = sum(t["pnl"] for t in st["trades"])
    valid = abs(check_sum - realized) < 0.01

    def krow(metric: str, value: str, note: str) -> str:
        return (f"<tr><td>{metric}</td><td class='num'>{value}</td>"
                f"<td class='note'>{note}</td></tr>")

    kern_rows = (
        krow("Trades (TP / SL / overig)", f"{len(trades)} ({n_tp} / {n_sl} / "
             f"{n_other})", "overig = crash-interceptor, time-stop, trailing") +
        krow("Gem. take-profit", f"{avg_tp_pct:+.2f}%",
             f"≈ {win_sum / len(wins):+.2f} EUR netto per winnende trade"
             if wins else "nog geen winnaars") +
        krow("Gem. stop-loss", f"{avg_sl_pct:+.2f}%",
             f"≈ {-loss_sum / len(losses):+.2f} EUR netto per verliezende trade"
             if losses else "nog geen verliezers") +
        krow("Bruto P/L (vóór fees)", f"{gross_pl:+.2f} EUR",
             "positief + netto negatief = de kosten zijn het probleem; "
             "beide negatief = de strategie zelf") +
        krow("Fees (gesloten trades)", f"−€{fees_total:.2f}", fee_share) +
        krow("Open posities",
             f"{len(st['positions'])}"
             + (f" ({underwater} onder water)" if st["positions"] else ""),
             f"ongerealiseerd {unreal_total:+.2f} EUR"
             if st["positions"] else "de gate wacht op een betaalbare setup") +
        krow("Max drawdown", f"−{mdd:.2%}",
             "op de gerealiseerde equity-curve") +
        krow("Cooldowns actief",
             ", ".join(f"{m} ({hh:.0f}u)" for m, hh in cds) if cds else "geen",
             f"na een verlies-exit is een markt {COOLDOWN_BARS} bars "
             "geblokkeerd") +
        krow("Cost-gate", "≤ 0.30R kosten per trade",
             "weigert setups waar fees+slippage &gt; 30% van het risico opeten "
             "— dé les uit de v1-analyse") +
        krow("Validatie", "✓ klopt" if valid else "✗ AFWIJKING",
             f"som van alle trade-P/L = {check_sum:+.4f} = gerealiseerd "
             f"{realized:+.4f}" + ("" if valid else " — meld dit!")))

    # Belgische belastingen (educatief) — gerealiseerd resultaat per jaar
    by_year: dict[int, float] = {}
    for t in st["trades"]:
        y = datetime.fromtimestamp(t["closed"], timezone.utc).year
        by_year[y] = by_year.get(y, 0.0) + t["pnl"]
    tax_rows = "".join(
        f"<tr><td class='num'>{y}</td>{pnl_cell(v)}"
        f"<td class='num'>{'€' + format(v * 0.33, '.2f') if v > 0 else '—'}</td>"
        f"<td class='note'>"
        + ("hypothetisch: winst × 33% (+ gemeentebelasting)" if v > 0 else
           "verlies — als 'diverse inkomsten' 5 jaar verrekenbaar met "
           "winsten uit dezelfde categorie")
        + "</td></tr>"
        for y, v in sorted(by_year.items())) or (
        "<tr><td colspan='4' class='empty'>nog geen gesloten trades</td></tr>")

    # gezondheid: draait de trader nog? (laatst verwerkte bar vs verwachte)
    sec_per = {"1h": 3600, "2h": 7200, "4h": 14400}.get(st["interval"], 3600)
    newest_closed = (int(time.time()) // sec_per - 1) * sec_per
    lag_bars = ((newest_closed - st["last_ts"]) / sec_per
                if st["last_ts"] else 0.0)
    health = ""
    if st["last_ts"] and lag_bars >= 2:
        health = (f'<div class="card" style="border-color:var(--down);'
                  f'margin-bottom:16px"><b style="color:var(--down)">'
                  f'⚠ trader loopt {lag_bars:.0f} bars achter</b> — laatste '
                  f'verwerkte bar {fmt_ts(st["last_ts"])}. Check op de VPS: '
                  '<code>systemctl status paperbot-v2</code> en '
                  '<code>journalctl -u paperbot-v2 -n 30</code></div>')

    now = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")
    return f"""<!doctype html>
<html lang="nl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="60">
<title>Paper-bot v2</title>
<style>{STYLE}</style></head><body>
<h1>Paper-bot v2 — rsi_dip_buyer</h1>
<div class="meta">nepgeld · alleen-lezen · bijgewerkt {now} · laatste bar
{fmt_ts(st["last_ts"]) if st["last_ts"] else "—"} · meldingen
{"aan" if st.get("ntfy_topic") else "uit"} · ververst elke 60&nbsp;s</div>
{health}
<div class="tiles">{tiles}</div>
<h2>Equity (gerealiseerd, per gesloten trade)</h2>
<div class="card">{svg_equity(st)}</div>
<h2>Equity-verloop (per bar, incl. open posities)</h2>
<div class="card">{svg_snapshots(st)}
<div class="meta" style="margin-top:8px">Elk punt is de bar-close: cash +
open posities tegen marktwaarde. Dit is de curve die dips van open trades
laat zien die de gerealiseerde curve verbergt.</div></div>
<h2>Netto P&amp;L per symbool</h2>
<div class="card">{svg_symbol_bars(trades)}</div>
<h2>Open posities</h2>
<div class="card"><table>
<tr><th>Markt</th><th class="num">Aantal</th><th class="num">Entry</th>
<th class="num">Stop</th><th class="num">Geopend</th><th class="num">Koers</th>
<th class="num">Ongerealiseerd</th><th class="num">R</th></tr>
{pos_table}</table>{pending_note}</div>
<h2>Per markt — gate-activiteit &amp; resultaat</h2>
<div class="card"><table>
<tr><th>Markt</th><th class="num">bijna*</th><th class="num">Signalen</th>
<th class="num">Trades</th><th class="num">Winrate</th>
<th class="num">P&amp;L</th><th class="num">Gem. R</th>
<th class="num">Cooldown</th></tr>
{mkt_table}</table>
<div class="meta" style="margin-top:8px">* "bijna" = echte dip in uptrend die
door een kwaliteits- of kostenfilter is geweigerd — zie het logboek voor de
reden per geval.</div></div>
<h2>Exits per reden</h2>
<div class="card"><table>
<tr><th>Reden</th><th class="num">Aantal</th><th class="num">P&amp;L</th>
<th class="num">Gem. R</th></tr>
{reason_rows}</table></div>
<h2>Afgesloten trades</h2>
<div class="card"><table>
<tr><th class="num">Gesloten</th><th>Markt</th><th>Reden</th>
<th class="num">Entry</th><th class="num">Exit</th><th class="num">Fees</th>
<th class="num">R</th><th class="num">P&amp;L</th></tr>
{trade_rows}</table></div>
<h2>Alle kerncijfers</h2>
<div class="card"><table>
<tr><th>Metric</th><th class="num">Waarde</th><th>Toelichting</th></tr>
{kern_rows}</table></div>
<h2>Belgische belastingen (educatief)</h2>
<div class="card"><table>
<tr><th class="num">Jaar</th><th class="num">Gerealiseerd resultaat</th>
<th class="num">Hypothetisch 33%</th><th>Toelichting</th></tr>
{tax_rows}</table>
<div class="meta" style="margin-top:10px">
<b>Dit is nepgeld</b> — er valt dus niets aan te geven. Zou dit echt geld
zijn, dan kent België grofweg drie regimes voor crypto-meerwaarden:
<b>goede huisvader</b> (normaal beheer van privévermogen → vrijgesteld),
<b>speculatief</b> (diverse inkomsten → 33% + gemeentebelasting, aangifte
vak XV) en <b>beroepsmatig</b> (progressieve tarieven). Een bot die
frequent en geautomatiseerd handelt wijst doorgaans richting het
speculatieve regime — daarom rekent de kolom hierboven met 33%.
Koerswinst op crypto kent geen roerende voorheffing en geen beurstaks
(TOB); rente uit staking/lending zou wél roerend inkomen zijn (30%).<br><br>
⚠️ Educatief en indicatief — <b>geen belastingadvies</b>. De kwalificatie
hangt af van jouw volledige situatie; raadpleeg een accountant of
belastingadviseur (of vraag een ruling) vóór je met echt geld handelt.
</div></div>
<h2>Logboek (recentste eerst)</h2>
<div class="card log">{log_rows or '<div class="empty">nog leeg</div>'}</div>
<div class="disclaimer">Bron: paper_state_v2.json + paper_log_v2.txt ·
validatie som(P/L) = gerealiseerd: {"✓" if valid else "✗"}<br>
⚠️ Educatief — papieren resultaten voorspellen geen toekomstige winst.
Dit dashboard kan niets kopen of verkopen.</div>
</body></html>"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        status = 200
        if self.path.startswith("/api/state"):
            body = json.dumps(load_state() or {}).encode()
            ctype = "application/json"
        elif self.path.startswith("/coin/"):
            st = load_state()
            sym = urllib.parse.unquote(self.path[len("/coin/"):]).split("?")[0]
            if st and sym in st["markets"]:
                body = render_coin(st, sym).encode()
            else:
                status = 404
                body = (f"<!doctype html><style>{STYLE}</style><body>"
                        '<div class="meta"><a href="/">← terug</a></div>'
                        f"<h1>Onbekende markt</h1></body>").encode()
            ctype = "text/html; charset=utf-8"
        else:
            body = render(load_state()).encode()
            ctype = "text/html; charset=utf-8"
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a) -> None:                 # geen access-log spam
        pass


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8787)
    args = ap.parse_args()
    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"dashboard: http://{args.host}:{args.port}  (Ctrl-C om te stoppen)")
    srv.serve_forever()


if __name__ == "__main__":
    main()
