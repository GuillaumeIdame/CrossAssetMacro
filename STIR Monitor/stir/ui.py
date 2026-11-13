"""HTML/CSS pieces that give Streamlit the STIR-monitor look (dark cards, mono numbers, heat cells)."""

from __future__ import annotations

import html
import math
from typing import Dict, List, Optional, Sequence

from .calc import argmax_abs

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600;700&display=swap');
:root{--card:#1b212d;--border:#2a3242;--muted:#8a93a4;--faint:#5d6576;--accent:#22d3ee;--pos:34,197,94;--neg:239,68,68}
.stApp{background:#12161f}
html,body,.stApp,.stApp *:not(.material-icons):not([data-testid="stIconMaterial"]){font-family:'IBM Plex Mono',ui-monospace,monospace}
.block-container{padding-top:3.2rem;max-width:1500px}
div[data-testid="stVerticalBlockBorderWrapper"]{background:var(--card);border:1px solid var(--border)!important;border-radius:12px!important;padding:16px}
.ctitle{display:flex;align-items:center;gap:8px;font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:.14em;color:#d7dce5;margin:0 0 8px}
.ctitle::before{content:"";width:3px;height:14px;border-radius:2px;background:var(--accent)}
.ctitle .sub{color:var(--muted);font-weight:500;letter-spacing:.08em}
.mock{font-size:9.5px;color:#fbbf24;border:1px solid rgba(251,191,36,.45);border-radius:3px;padding:0 4px;margin-left:6px;letter-spacing:.06em}
.live{font-size:9.5px;color:#22c55e;border:1px solid rgba(34,197,94,.45);border-radius:3px;padding:0 4px;margin-left:6px}
.note{font-size:10.5px;color:var(--faint);margin-top:6px}
.hscroll{overflow-x:auto;-webkit-overflow-scrolling:touch}
table.heat{border-collapse:separate;border-spacing:3px;width:100%;font-size:12px}
table.heat th{color:var(--muted);font-weight:500;font-size:10.5px;letter-spacing:.08em;text-transform:uppercase;padding:4px 6px;text-align:center;white-space:nowrap;border:none}
table.heat th.grp{color:#d7dce5;border-bottom:1px solid var(--border)}
table.heat td{padding:6px;text-align:center;white-space:nowrap;border-radius:4px;border:1px solid transparent;color:#eef2f7;font-variant-numeric:tabular-nums}
table.heat td.lab{text-align:left;font-weight:600;color:#d7dce5}
table.heat td.lab i{display:inline-block;width:8px;height:8px;border-radius:2px;margin-right:7px}
table.heat td.zero{background:#363d4b;color:#aab2c0}
table.heat td.na{color:var(--faint)}
table.heat td.max{border-color:#fff;box-shadow:0 0 0 1px rgba(255,255,255,.25)}
table.heat td.num{text-align:right;color:#d7dce5}
table.heat tr{border:none}
.dpos{color:rgb(var(--pos))!important}.dneg{color:rgb(var(--neg))!important}.dzero{color:var(--muted)!important}
.chips{display:flex;flex-wrap:wrap;gap:6px;margin:4px 0 6px}
.chip{font-size:11px;border:1px solid var(--border);border-radius:6px;padding:3px 8px;background:#161b25;white-space:nowrap}
.chip b{font-weight:500;color:var(--muted);margin-right:6px}
.fix{display:flex;flex-wrap:wrap;gap:8px}
.fix>div{background:#161b25;border:1px solid var(--border);border-radius:8px;padding:6px 10px;min-width:118px}
.fix .l{font-size:10px;color:var(--muted);letter-spacing:.08em;text-transform:uppercase}
.fix .v{font-size:15px;font-weight:600;color:#eef2f7}
.fix .c{font-size:10.5px}
.spk-head{display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin-bottom:8px}
.badge{background:#2b3446;color:#cfe3ff;border:1px solid #3c4860;font-size:10.5px;font-weight:600;padding:2px 7px;border-radius:4px}
.spk-name{font-weight:600;font-size:14px;color:#eef2f7}.spk-role{color:var(--muted);font-size:11px}
.tag{font-size:10.5px;padding:2px 7px;border-radius:4px}
.spk-date{margin-left:auto;font-size:11px;color:var(--muted)}
.voting{font-size:11px;color:var(--muted);margin-bottom:6px}
.voting .dot{display:inline-block;width:7px;height:7px;border-radius:50%;margin-right:6px}
.warn{font-size:11px;color:#fbbf24;background:rgba(251,191,36,.08);border:1px solid rgba(251,191,36,.3);border-radius:6px;padding:5px 8px;margin:6px 0}
.spk-title{font-size:10.5px;color:var(--muted);text-transform:uppercase;letter-spacing:.08em;margin:8px 0 4px}
.spk-headline{font-weight:600;font-size:13px;color:#f1f4f8;margin:0 0 6px}
.spk ul{margin:0 0 10px;padding-left:16px;font-size:12px;color:#c4cad5}
.spk li b{font-weight:500;font-size:10.5px;color:var(--accent);text-transform:uppercase}
.rr{border:1px solid rgba(34,211,238,.35);background:rgba(34,211,238,.06);border-radius:8px;padding:8px 12px;font-size:12px}
.rr h4{margin:0 0 4px;font-size:10.5px;letter-spacing:.14em;color:var(--accent);padding:0}
</style>
"""

COLORS: Dict[str, str] = {}


def title(text: str, sub: str = "", tag: str = "") -> str:
    tag_html = {"live": '<span class="live">LIVE</span>', "mock": '<span class="mock">MOCK</span>',
                "mixed": '<span class="live">LIVE</span><span class="mock">+ MOCK</span>'}.get(tag, "")
    sub_html = f'<span class="sub">· {html.escape(sub)}</span>' if sub else ""
    return f'<div class="ctitle">{html.escape(text)} {sub_html}{tag_html}</div>'


def fmt(v: Optional[float], d: int = 2) -> str:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "—"
    return f"{v:+.{d}f}".replace("-", "−") if v != 0 else f"{0:.{d}f}"


def heat_td(v: Optional[float], scale: float, is_max: bool, d: int = 2) -> str:
    if v is None:
        return '<td class="na">—</td>'
    if abs(v) < 0.005:
        return f'<td class="zero{" max" if is_max else ""}">{fmt(0, d)}</td>'
    t = min(1.0, abs(v) / (scale or 1))
    a = 0.14 + 0.66 * math.sqrt(t)
    rgb = "34,197,94" if v > 0 else "239,68,68"
    return f'<td class="{"max" if is_max else ""}" style="background:rgba({rgb},{a:.2f})">{fmt(v, d)}</td>'


def label_td(name: str, mock: bool = False) -> str:
    tag = '<span class="mock">MOCK</span>' if mock else ""
    return f'<td class="lab"><i style="background:{COLORS.get(name, "#888")}"></i>{html.escape(name)}{tag}</td>'


def heat_table(columns: Sequence[str], rows: List[tuple], groups: Optional[List[tuple]] = None, d: int = 2) -> str:
    """rows: [(name, values, is_mock)]. White border on each row's max |value|."""
    allv = [abs(v) for _, vals, _ in rows for v in vals if v is not None]
    scale = max(allv) if allv else 1
    head = ""
    if groups:
        head += "<tr><th></th>" + "".join(f'<th class="grp" colspan="{n}">{html.escape(g)}</th>' for g, n in groups) + "</tr>"
    head += "<tr><th></th>" + "".join(f"<th>{html.escape(c)}</th>" for c in columns) + "</tr>"
    body = ""
    for name, vals, mock in rows:
        mi = argmax_abs(vals)
        body += "<tr>" + label_td(name, mock) + "".join(heat_td(v, scale, i == mi, d) for i, v in enumerate(vals)) + "</tr>"
    return f'<div class="hscroll"><table class="heat"><thead>{head}</thead><tbody>{body}</tbody></table></div>'


def dclass(v: Optional[float]) -> str:
    if v is None or abs(v) < 0.05:
        return "dzero"
    return "dpos" if v > 0 else "dneg"


def priced_table(rows, deltas) -> str:
    moves = [r.move for r in rows]
    scale = max([abs(m) for m in moves] or [1])
    mi = argmax_abs(moves)
    body = "".join(
        f'<tr><td class="lab" style="font-weight:500">{r.meeting:%d %b %y}</td>{heat_td(r.move, scale, i == mi, 1)}'
        f'<td class="num">{fmt(r.cumulative, 1)}</td><td class="num">{r.implied:.3f}</td>'
        f'<td class="num {dclass(dl)}">{fmt(dl, 1)}</td></tr>'
        for i, (r, dl) in enumerate(zip(rows, deltas)))
    head = ('<tr><th style="text-align:left">Meeting</th><th>Move (bp)</th><th style="text-align:right">Cum (bp)</th>'
            '<th style="text-align:right">Implied (%)</th><th style="text-align:right">Δ 1D (bp)</th></tr>')
    return f'<div class="hscroll"><table class="heat"><thead>{head}</thead><tbody>{body}</tbody></table></div>'


def speaker_card(s: dict, priced: dict) -> str:
    import re
    avg4 = sum(s["last4"]) / len(s["last4"])
    score = (sum(s["last4"]) + s["hawkish"]) / (len(s["last4"]) + 1)
    dev = s["hawkish"] - avg4
    h = s["hawkish"]
    col = "rgb(239,68,68)" if h >= 6 else "rgb(34,197,94)" if h <= 4 else "#8a93a4"
    lab = "Hawkish" if h >= 6 else "Dovish" if h <= 4 else "Neutral"
    warn = (f'<div class="warn">⚠ Today {h}/10 is {fmt(dev, 1)} vs the last-4 average of {avg4:.1f} — '
            f'{"notably more hawkish" if dev > 0 else "notably more dovish"} than usual.</div>') if abs(dev) >= 1.5 else ""
    bullets = "".join("<li>" + re.sub(r"^([A-Za-z ]+):", r"<b>\1</b> ·", html.escape(b)) + "</li>" for b in s["bullets"])
    rr = html.escape(s["rates_read"].format(**priced))
    return f"""<div class="spk">
<div class="spk-head"><span class="badge">{html.escape(s['bank'])}</span><span class="spk-name">{html.escape(s['name'])}</span>
<span class="spk-role">{html.escape(s['role'])}</span><span>{score:.1f} <small style="color:#8a93a4">({len(s['last4']) + 1})</small></span>
<span class="tag" style="color:{col};border:1px solid {col}">{lab} {h}/10</span><span class="spk-date">{s['date']}</span></div>
<div class="voting"><span class="dot" style="background:{'rgb(34,197,94)' if s.get('votes_next') else '#5d6576'}"></span>{html.escape(s['voting'])}</div>
{warn}<div class="spk-title">{html.escape(s['title'])}</div><p class="spk-headline">{html.escape(s['headline'])}</p>
<ul>{bullets}</ul><div class="rr"><h4>RATES READ</h4>{rr}</div></div>"""
