"""STIR / short-rates monitor on free data.

    cd "STIR Monitor"
    pip install -r requirements.txt
    streamlit run app.py

Live (free): CME 3M SOFR futures and 30D Fed Funds futures (Yahoo Finance, ~10-min delayed),
UST yield indices (Yahoo), overnight fixings (FRED, Bank of Canada Valet, RBA), Fed speeches RSS.
No free feed exists for Euribor / SONIA / CORRA / SARON / Aussie Bills futures: those rows and
the BoC table appear only with "Show mock rows" on, and are tagged MOCK.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yaml

from stir import calc, mock, sources, ui

HERE = Path(__file__).parent
CFG = yaml.safe_load((HERE / "config.yaml").read_text())
SPEAKERS = json.loads((HERE / "speakers.json").read_text())
ui.COLORS.update(CFG["colors"])
YCFG, SCFG, ZCFG = CFG["yahoo"], CFG["sofr_futures"], CFG["fed_funds_futures"]
MEETINGS = [pd.Timestamp(d).date() for d in CFG["fomc_meetings"]]

st.set_page_config(page_title="STIR Monitor", page_icon="📈", layout="wide")
st.markdown(ui.CSS, unsafe_allow_html=True)


# =========================================================================== data (cached)
def _ticker(code, c):
    return calc.contract_ticker(code, c["root"], c["exchange"], YCFG["ticker_template"])


@st.cache_data(ttl=60, show_spinner=False)
def load_sofr():
    codes = SCFG["contracts"] + SCFG["extra_contracts"]
    tick = {_ticker(c, SCFG): c for c in codes}
    out = {"intraday": {}, "daily": {}, "errors": []}
    for kind, period, interval in (("intraday", YCFG["intraday_period"], YCFG["intraday_interval"]),
                                   ("daily", YCFG["daily_period"], "1d")):
        try:
            got = sources.yahoo_prices(list(tick), period, interval)
            out[kind] = {tick[t]: s for t, s in got.items()}
        except Exception as e:  # noqa: BLE001 - surface any feed failure in the status panel
            out["errors"].append(f"SOFR {kind}: {e}")
    missing = [c for c in codes if c not in out["daily"]]
    if missing:
        out["errors"].append(f"SOFR daily missing: {', '.join(missing)}")
    return out


@st.cache_data(ttl=300, show_spinner=False)
def load_zq():
    today = date.today()
    months = calc.months_between(date(today.year, today.month, 1), max(MEETINGS) + timedelta(days=40))
    tick = {_ticker(calc.fed_funds_code(y, m), ZCFG): (y, m) for y, m in months}
    try:
        got = sources.yahoo_prices(list(tick), YCFG["daily_period"], "1d")
        return {tick[t]: s for t, s in got.items()}, None
    except Exception as e:  # noqa: BLE001
        return {}, f"Fed Funds futures: {e}"


@st.cache_data(ttl=3600, show_spinner=False)
def load_fixings():
    start = (date.today() - timedelta(days=60)).isoformat()
    out, errs = {}, []
    for f in CFG["fixings"]:
        try:
            out[f["label"]] = sources.FIXING_SOURCES[f["source"]](f["id"], start)
        except Exception as e:  # noqa: BLE001
            errs.append(f"{f['label']} ({f['source']}:{f['id']}): {e}")
    return out, errs


@st.cache_data(ttl=60, show_spinner=False)
def load_bonds():
    tick = {b["ticker"]: b["label"] for b in CFG["bonds"]}
    out = {"intraday": {}, "daily": {}, "errors": []}
    for kind, period, interval in (("intraday", YCFG["intraday_period"], YCFG["intraday_interval"]),
                                   ("daily", YCFG["daily_period"], "1d")):
        try:
            out[kind] = {tick[t]: s for t, s in sources.yahoo_prices(list(tick), period, interval).items()}
        except Exception as e:  # noqa: BLE001
            out["errors"].append(f"Bonds {kind}: {e}")
    return out


@st.cache_data(ttl=1800, show_spinner=False)
def load_speeches():
    try:
        return sources.fed_speeches(CFG["fed_speeches_rss"]), None
    except Exception as e:  # noqa: BLE001
        return [], f"Fed speeches RSS: {e}"


# =========================================================================== sidebar
with st.sidebar:
    st.markdown(ui.title("Controls"), unsafe_allow_html=True)
    if st.button("↻ Refresh data", use_container_width=True):
        st.cache_data.clear()
    since = st.date_input("'Since' reference date", value=date(2026, 10, 28),
                          help="Used by the 'Since' pill (e.g. last FOMC decision).")
    show_mock = st.toggle("Show mock rows", value=False,
                          help="Curves with no free futures feed (Euribor, SONIA, CORRA, SARON, Aussie Bills) and BoC pricing.")

with st.spinner("Loading free feeds…"):
    SOFR = load_sofr()
    ZQ, zq_err = load_zq()
    FIX, fix_errs = load_fixings()
    BONDS = load_bonds()
    SPEECHES, sp_err = load_speeches()

errors = SOFR["errors"] + BONDS["errors"] + fix_errs + [e for e in (zq_err, sp_err) if e]
with st.sidebar:
    st.markdown(ui.title("Data status"), unsafe_allow_html=True)
    st.caption(f"SOFR contracts: {len(SOFR['daily'])} daily / {len(SOFR['intraday'])} intraday · "
               f"ZQ months: {len(ZQ)} · fixings: {len(FIX)}/{len(CFG['fixings'])}")
    for e in errors:
        st.warning(e, icon="⚠️")
    if not errors:
        st.success("All free feeds loaded", icon="✅")


def pills(options, default, key):
    v = st.segmented_control(key, options, default=default, key=key, label_visibility="collapsed")
    return v or default


def html(s):
    st.markdown(s, unsafe_allow_html=True)


# =========================================================================== header + fixings
last_bar = max((s.index[-1] for s in SOFR["intraday"].values()), default=None)
stamp = last_bar.tz_convert("Europe/London").strftime("%d %b %y · %H:%M London") if last_bar is not None else "no intraday data"
html(f'<div style="display:flex;justify-content:space-between;flex-wrap:wrap;gap:6px;margin-bottom:10px">'
     f'<div style="font-size:15px;font-weight:600;letter-spacing:.14em"><span style="color:#22d3ee">■</span> STIR / SHORT-RATES MONITOR</div>'
     f'<div style="font-size:11px;color:#8a93a4">LAST SOFR BAR {stamp.upper()}</div></div>')

with st.container(border=True):
    html(ui.title("Overnight fixings", "% · Δ bp", "live"))
    cells = ""
    for f in CFG["fixings"]:
        s = FIX.get(f["label"])
        if s is None or s.empty:
            cells += f'<div><div class="l">{f["label"]}</div><div class="v">—</div><div class="c dzero">unavailable</div></div>'
            continue
        d1 = (s.iloc[-1] - s.iloc[-2]) * 100 if len(s) > 1 else None
        w = calc._asof(s, s.index[-1] - pd.Timedelta(days=7))
        d7 = (s.iloc[-1] - w) * 100 if w is not None else None
        cells += (f'<div><div class="l">{f["label"]} · {s.index[-1]:%d %b}</div><div class="v">{s.iloc[-1]:.3f}</div>'
                  f'<div class="c"><span class="{ui.dclass(d1)}">1D {ui.fmt(d1, 1)}</span> · '
                  f'<span class="{ui.dclass(d7)}">1W {ui.fmt(d7, 1)}</span></div></div>')
    html(f'<div class="fix">{cells}</div>')

# =========================================================================== heatmap
HEAT_TF = ["15m", "30m", "1h", "Day", "Week", "Since", "Since EU Open"]
with st.container(border=True):
    c1, c2 = st.columns([1, 1.4])
    with c1:
        html(ui.title("Net change", "Outrights · bp", "mixed" if show_mock else "live"))
    with c2:
        tf = pills(HEAT_TF, "Day", "heat_tf")
    cols = SCFG["contracts"]
    sofr = calc.strip_changes(cols, SOFR["intraday"], SOFR["daily"], tf, since)
    rows = [("SOFR", [sofr[c] for c in cols], False)]
    if show_mock:
        rows += [(cv, list(mock.strip(cv, cols, tf).values()), True) for cv in ["Euribor", "SONIA", "CORRA", "SARON"]]
    html(ui.heat_table(cols, rows))
    html('<div class="note">Rate change in bp vs reference (−Δprice×100). White border = largest |move| in row. '
         f'Day = vs prior settle · Week = vs last Friday · Since = vs close on {since:%d %b %y}.</div>')

# =========================================================================== dec spreads + sentiment
left, right = st.columns([6, 6])
with left, st.container(border=True):
    html(ui.title("Dec spreads", "Δ bp", "mixed" if show_mock else "live"))
    pairs = SCFG["dec_pairs"]
    labels = [p[2] for p in pairs]
    rows = [("SOFR", calc.dec_spread_changes(pairs, SOFR["intraday"], SOFR["daily"], "Day")
             + calc.dec_spread_changes(pairs, SOFR["intraday"], SOFR["daily"], "Week"), False)]
    if show_mock:
        rows += [(cv, mock.dec_spreads(cv, "Day") + mock.dec_spreads(cv, "Week"), True) for cv in ["Euribor", "SONIA", "CORRA"]]
    html(ui.heat_table(labels * 2, rows, groups=[("DAY", 3), ("THIS WEEK", 3)]))
    html('<div class="note">Spread = price(front Z) − price(back Z). THIS WEEK = vs last Friday settle.</div>')

with right, st.container(border=True):
    k = SCFG["sentiment_contract"]
    html(ui.title(f"{k} · vs Fri settle", "", "mixed" if show_mock else "live"))
    stf = pills(["Day", "Week", "1W", "1M", "3M", "6M"], "Day", "sent_tf")
    vals = {"SOFR": calc.strip_changes([k], SOFR["intraday"], SOFR["daily"], stf)[k]}
    if show_mock:
        vals.update({f"{cv} (mock)": mock.sentiment(cv, stf) for cv in mock.SENTIMENT_BASE})
    items = sorted([(n, v) for n, v in vals.items() if v is not None], key=lambda x: x[1])
    if not items:
        st.info("No Z27 data available.")
    else:
        lim = max(2, max(abs(v) for _, v in items) * 1.25)
        fig = go.Figure(go.Bar(
            y=[n for n, _ in items], x=[v for _, v in items], orientation="h",
            marker_color=[CFG["colors"].get(n.replace(" (mock)", ""), "#888") for n, _ in items],
            text=[ui.fmt(v) for _, v in items], textposition="outside", cliponaxis=False,
            textfont=dict(family="IBM Plex Mono", size=12)))
        fig.update_layout(height=60 + 34 * len(items), margin=dict(l=0, r=40, t=6, b=24),
                          paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                          font=dict(family="IBM Plex Mono", color="#c4cad5", size=11),
                          xaxis=dict(range=[-lim, lim], zeroline=True, zerolinecolor="#5d6576", gridcolor="#262e3c",
                                     ticksuffix=" bp"), yaxis=dict(gridcolor="rgba(0,0,0,0)"), bargap=.35)
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

# =========================================================================== net change curve
with st.container(border=True):
    title_slot = st.empty()
    c2, c3 = st.columns([1, 2])
    with c2:
        mode = pills(["Bonds", "SOFR strip"], "SOFR strip", "curve_mode")
    with c3:
        ctf = pills(["15m", "30m", "1h", "Day", "Since"], "Day", "curve_tf")
    title_slot.markdown(ui.title("Net change curve", f"{mode} · bp vs reference", "live"), unsafe_allow_html=True)
    if mode == "SOFR strip":
        labels = SCFG["contracts"]
        ch = calc.strip_changes(labels, SOFR["intraday"], SOFR["daily"], ctf, since)
        pts = [(c, ch[c]) for c in labels if ch[c] is not None]
        dec = 2
    else:
        pts = []
        for b in CFG["bonds"]:
            lb = b["label"]
            last = calc.last_price(BONDS["intraday"].get(lb), BONDS["daily"].get(lb))
            ref = calc.reference_price(ctf, BONDS["intraday"].get(lb), BONDS["daily"].get(lb), since)
            v = calc.yield_change_bp(last, ref)
            if v is not None:
                pts.append((lb, v))
        dec = 1
    if not pts:
        st.info("No data for this view.")
    else:
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        imax, imin = ys.index(max(ys)), ys.index(min(ys))
        html('<div class="chips">' + "".join(
            f'<span class="chip" style="{"border-color:#22c55e" if i == imax else "border-color:#22d3ee" if i == imin else ""}">'
            f'<b>{x}</b><span class="{ui.dclass(y)}">{ui.fmt(y, dec)}</span></span>' for i, (x, y) in enumerate(pts)) + "</div>")
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines+markers+text", line=dict(shape="spline", color="#22d3ee", width=2),
                                 fill="tozeroy", fillcolor="rgba(34,211,238,.08)",
                                 marker=dict(size=7, color="#1b212d", line=dict(color="#22d3ee", width=1.5)),
                                 text=['' if i in (imax, imin) else ui.fmt(y, dec) for i, y in enumerate(ys)], cliponaxis=False, textposition="top center",
                                 textfont=dict(family="IBM Plex Mono", size=11, color="#c4cad5"), hoverinfo="x+y"))
        for i, col, nm in ((imax, "#22c55e", "max"), (imin, "#22d3ee", "min")):
            fig.add_trace(go.Scatter(x=[xs[i]], y=[ys[i]], mode="markers+text", text=[f"{nm} {ui.fmt(ys[i], dec)}"],
                                     textposition="bottom center" if nm == "min" else "top center",
                                     textfont=dict(family="IBM Plex Mono", size=12, color=col),
                                     marker=dict(size=14, color=col, line=dict(color="#12161f", width=2)), hoverinfo="skip", cliponaxis=False))
        fig.update_layout(height=340, showlegend=False, margin=dict(l=0, r=30, t=30, b=10),
                          paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                          font=dict(family="IBM Plex Mono", color="#8a93a4", size=11),
                          yaxis=dict(gridcolor="#262e3c", zerolinecolor="#5d6576", ticksuffix=" bp"),
                          xaxis=dict(gridcolor="rgba(0,0,0,0)", range=[-0.4, len(xs) - 0.6]))
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

# =========================================================================== priced moves
effr = FIX.get("EFFR")
FED_HIST = calc.priced_history(MEETINGS, ZQ, days=10, start_rate_series=effr)


def stepper(key, max_days):
    return int(st.number_input("N DAYS AGO", min_value=0, max_value=max(0, max_days), value=min(1, max_days),
                               step=1, key=key))


pl, pr = st.columns(2)
with pl, st.container(border=True):
    html(ui.title("Priced moves", "SOFR / Fed · ZQ", "live"))
    if not FED_HIST or not FED_HIST[0][1]:
        st.info("Fed Funds futures unavailable — see Data status.")
    else:
        n = stepper("fed_days", len(FED_HIST) - 1)
        d, rows, delta = FED_HIST[n]
        st.caption(f"As of settle {d:%a %d %b %y} · start rate {rows[0].implied - rows[0].cumulative / 100:.3f}%")
        html(ui.priced_table(rows, delta))
        html('<div class="note">Cumulative = running sum of moves · Implied = start + cumulative · Δ1D on cumulative.</div>')

with pr, st.container(border=True):
    html(ui.title("Priced moves", "CORRA / BoC", "mock"))
    if not show_mock:
        st.info("No free CORRA futures feed (Montréal Exchange data is licensed). Turn on “Show mock rows” to see the layout.")
    else:
        n = stepper("boc_days", 5)
        today = mock.boc_moves(n)
        prev = mock.boc_moves(n + 1)
        rows = [calc.MeetingRow(m, mv, 0, 0) for m, mv in zip(mock.BOC_MEETINGS, today)]
        cum, pcum, deltas = 0, 0, []
        for r, pm in zip(rows, prev):
            cum += r.move
            pcum += pm
            r.cumulative, r.implied = round(cum, 1), round(mock.BOC_START + cum / 100, 3)
            deltas.append(round(cum - pcum, 1))
        st.caption(f"MOCK · {n} business day(s) ago · start rate {mock.BOC_START:.2f}%")
        html(ui.priced_table(rows, deltas))

# =========================================================================== speakers
html('<div style="height:6px"></div>' + ui.title("Central bank speakers"))
if FED_HIST and len(FED_HIST[0][1]) >= 2:
    r0 = FED_HIST[0][1]
    priced = {"dec": f"~{r0[0].move:.0f}bp", "jan": f"~{r0[1].cumulative:.0f}bp"}
else:
    priced = {"dec": "n/a", "jan": "n/a"}
cols = st.columns(len(SPEAKERS))
for col, s in zip(cols, SPEAKERS):
    with col, st.container(border=True):
        html(ui.speaker_card(s, priced))
        st.caption("Manual entry · edit speakers.json · RATES READ pricing is filled live from Fed Funds futures.")

with st.container(border=True):
    html(ui.title("Latest Fed speeches", "federalreserve.gov RSS", "live"))
    if not SPEECHES:
        st.info("Fed speeches feed unavailable.")
    for sp in SPEECHES:
        dt = sp["date"].strftime("%d %b %y") if pd.notna(sp["date"]) else ""
        html(f'<div style="font-size:12px;margin:3px 0"><span style="color:#8a93a4">{dt}</span> &nbsp; '
             f'<a href="{sp["link"]}" target="_blank" style="color:#d7dce5">{sp["title"]}</a></div>')
