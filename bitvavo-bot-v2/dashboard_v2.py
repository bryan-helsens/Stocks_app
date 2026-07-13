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


try:                                    # cooldown-lengte uit de strategie zelf
    from rsi_dip_buyer_v2 import StrategyConfig as _SC
    COOLDOWN_BARS = _SC().cooldown_bars_after_stop
except Exception:
    COOLDOWN_BARS = 48


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


def pnl_cell(val: float, suffix: str = " EUR") -> str:
    if val > 0:
        return f'<td class="num up">▲ +{val:.2f}{suffix}</td>'
    if val < 0:
        return f'<td class="num down">▼ {val:.2f}{suffix}</td>'
    return f'<td class="num">0.00{suffix}</td>'


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
    pos_rows, unreal_total = [], 0.0
    for sym, p in st["positions"].items():
        px = last_price(sym)
        if px is not None:
            gross = (px - p["entry"]) * p["qty"]
            fees = (p["entry"] + px) * p["qty"] * st["fee_side_pct"] / 100.0
            upnl = gross - fees + p.get("realized", 0.0)
            unreal_total += upnl
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
    total = st["equity"] + unreal_total
    tiles = (
        stat("Equity (incl. open)", f"€{total:.2f}",
             "up" if total > st["start_equity"] else
             ("down" if total < st["start_equity"] else ""),
             f"start €{st['start_equity']:.2f}") +
        stat("Gerealiseerd", f"{realized:+.2f} EUR",
             "up" if realized > 0 else ("down" if realized < 0 else ""),
             f"open {unreal_total:+.2f} EUR" if st["positions"] else "") +
        stat("Max drawdown", f"{mdd:.1%}") +
        stat("Fees betaald", f"€{fees_total:.2f}") +
        stat("Trades", f"{len(trades)}",
             sub=f"{len(wins)} winst · {len(losses)} verlies") +
        stat("Winrate", f"{winrate:.0%}" if winrate is not None else "—",
             sub=(f"break-even bij {be_winrate:.0%}" if be_winrate else "")) +
        stat("Profit factor", "∞" if pf == float("inf") else f"{pf:.2f}",
             sub="doel &gt; 1.3") +
        stat("Gem. win / verlies",
             f"{avg_w:+.2f}R / {avg_l:+.2f}R" if trades else "—",
             sub="verlies hoort ≥ −1.4R te blijven") +
        stat("Gem. R", f"{sum(rs) / len(rs):+.2f}R" if rs else "—") +
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
        mkt_rows.append(
            f'<tr><td>{html.escape(m)}</td>'
            f'<td class="num">{a.get("bijna", 0)}</td>'
            f'<td class="num">{a.get("signalen", 0)}</td>'
            f'<td class="num">{len(mt)}</td>'
            f'<td class="num">{(len(mw) / len(mt)):.0%}</td>'
            f'{pnl_cell(pnl_sum)}'
            f'<td class="num">{(sum(t["r"] for t in mt) / len(mt)):+.2f}R</td>'
            if mt else
            f'<tr><td>{html.escape(m)}</td>'
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

    now = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")
    return f"""<!doctype html>
<html lang="nl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="60">
<title>Paper-bot v2</title>
<style>
:root {{
  --page: #0d0d0d; --surface: #1a1a19; --border: rgba(255,255,255,0.10);
  --ink: #ffffff; --ink-2: #c3c2b7; --muted: #898781;
  --grid: #2c2c2a; --baseline: #383835; --series: #3987e5;
  --up: #0ca30c; --down: #d03b3b;
}}
* {{ box-sizing: border-box; margin: 0; }}
body {{ background: var(--page); color: var(--ink-2);
       font: 14px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif;
       padding: 20px; max-width: 960px; margin: 0 auto; }}
h1 {{ color: var(--ink); font-size: 18px; }}
h2 {{ color: var(--ink); font-size: 14px; margin: 24px 0 8px; }}
.meta {{ color: var(--muted); font-size: 12px; margin-bottom: 16px; }}
.tiles {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
          gap: 8px; margin-bottom: 16px; }}
.tile {{ background: var(--surface); border: 1px solid var(--border);
         border-radius: 8px; padding: 10px 12px; }}
.tile .lbl {{ font-size: 11px; color: var(--muted); }}
.tile .val {{ font-size: 18px; color: var(--ink); margin-top: 2px; }}
.tile .sub {{ font-size: 12px; color: var(--muted); }}
.card {{ background: var(--surface); border: 1px solid var(--border);
         border-radius: 8px; padding: 12px; overflow-x: auto; }}
svg {{ width: 100%; height: auto; display: block; }}
.axis {{ fill: var(--muted); font-size: 11px;
         font-family: system-ui, sans-serif; }}
table {{ width: 100%; border-collapse: collapse; }}
th {{ text-align: left; color: var(--muted); font-size: 11px;
      font-weight: 500; padding: 4px 8px; border-bottom: 1px solid var(--baseline); }}
td {{ padding: 5px 8px; border-bottom: 1px solid var(--grid); }}
tr:last-child td {{ border-bottom: none; }}
.num {{ font-variant-numeric: tabular-nums; text-align: right; }}
th.num {{ text-align: right; }}
.up {{ color: var(--up); }} .down {{ color: var(--down); }}
.empty {{ color: var(--muted); text-align: center; padding: 14px; }}
.log {{ font: 12px/1.7 ui-monospace, monospace; color: var(--ink-2);
        max-height: 320px; overflow-y: auto; }}
.disclaimer {{ color: var(--muted); font-size: 11px; margin-top: 16px; }}
</style></head><body>
<h1>Paper-bot v2 — rsi_dip_buyer</h1>
<div class="meta">nepgeld · alleen-lezen · bijgewerkt {now} · pagina ververst
elke 60&nbsp;s</div>
<div class="tiles">{tiles}</div>
<h2>Equity (gerealiseerd, per gesloten trade)</h2>
<div class="card">{svg_equity(st)}</div>
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
<h2>Logboek (recentste eerst)</h2>
<div class="card log">{log_rows or '<div class="empty">nog leeg</div>'}</div>
<div class="disclaimer">⚠️ Educatief — papieren resultaten voorspellen geen
toekomstige winst. Dit dashboard kan niets kopen of verkopen.</div>
</body></html>"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        if self.path.startswith("/api/state"):
            body = json.dumps(load_state() or {}).encode()
            ctype = "application/json"
        else:
            body = render(load_state()).encode()
            ctype = "text/html; charset=utf-8"
        self.send_response(200)
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
