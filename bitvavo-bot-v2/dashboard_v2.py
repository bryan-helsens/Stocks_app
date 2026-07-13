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
        f'<td class="num">{t["r"]:+.2f}R</td>{pnl_cell(t["pnl"])}</tr>'
        for t in trades) or ("<tr><td colspan='7' class='empty'>nog geen "
                             "afgesloten trades</td></tr>")

    log_rows = "".join(f"<div>{html.escape(ln)}</div>"
                       for ln in reversed(log_tail()))

    rs = [t["r"] for t in trades]
    stat = lambda label, value, cls="": (  # noqa: E731
        f'<div class="tile"><div class="lbl">{label}</div>'
        f'<div class="val {cls}">{value}</div></div>')
    total = st["equity"] + unreal_total
    tiles = (
        stat("Equity (incl. open)", f"€{total:.2f}",
             "up" if total > st["start_equity"] else
             ("down" if total < st["start_equity"] else "")) +
        stat("Gerealiseerd", f"{realized:+.2f} EUR",
             "up" if realized > 0 else ("down" if realized < 0 else "")) +
        stat("Trades", f"{len(trades)} <span class='sub'>({len(wins)} winst)"
                       "</span>") +
        stat("Gem. R", f"{sum(rs) / len(rs):+.2f}R" if rs else "—") +
        stat("Looptijd", f"{days:.1f} dagen") +
        stat("Instellingen", f"{st['interval']} · fee {st['fee_side_pct']}%"
                             f"/zijde <span class='sub'>· {len(st['markets'])}"
                             " markten</span>"))

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
{pos_table}</table></div>
<h2>Afgesloten trades</h2>
<div class="card"><table>
<tr><th class="num">Gesloten</th><th>Markt</th><th>Reden</th>
<th class="num">Entry</th><th class="num">Exit</th><th class="num">R</th>
<th class="num">P&amp;L</th></tr>
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
