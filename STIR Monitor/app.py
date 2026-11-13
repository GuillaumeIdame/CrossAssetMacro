"""STIR / short-rates monitor.

    cd "STIR Monitor"
    pip install -r requirements.txt
    streamlit run app.py

Market data
  * IBKR (TWS / IB Gateway running locally with the API enabled): 3M SOFR, Euribor, SONIA, CORRA,
    SARON, ASX 90-day bills and 30D Fed Funds futures, by contract id (config.yaml).
  * Yahoo Finance (yfinance): fallback for SOFR and Fed Funds futures, plus UST yield indices.
  * FRED / Bank of Canada Valet / RBA: overnight fixings. Fed speeches RSS.
A curve with no data from either source is shown as unavailable, or as a MOCK-tagged row if
"Show mock rows" is switched on.
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
YCFG, CURVES, ZQ_CFG = CFG["yahoo"], CFG["curves"], CFG["fed_funds"]
CODES = CFG["contracts"] + CFG["extra_contracts"]
FOMC = [pd.Timestamp(d).date() for d in CFG["fomc_meetings"]]
BOC = [pd.Timestamp(d).date() for d in CFG["boc_meetings"]]
ZQ_KEY = "Fed Funds"

st.set_page_config(page_title="STIR Monitor", page_icon="📈", layout="wide")
st.markdown(ui.CSS, unsafe_allow_html=True)


def html(s):
    st.markdown(s, unsafe_allow_html=True)


def pills(options, default, key):
    v = st.segmented_control(key, options, default=default, key=key, label_visibility="collapsed")
    return v or default


# =========================================================================== sidebar: connection
with st.sidebar:
    html(ui.title("Data source"))
    providers = ["auto", "ibkr", "yahoo"]
    provider = st.selectbox("Provider", providers, index=providers.index(CFG.get("provider", "auto")),
                            help="auto = IBKR first, Yahoo fallback for SOFR and Fed Funds.")
    ib_cfg = dict(CFG["ibkr"])
    if provider != "yahoo":
        with st.expander("IBKR connection", expanded=False):
            ib_cfg["host"] = st.text_input("Host", ib_cfg["host"])
            ib_cfg["port"] = int(st.number_input("Port", value=int(ib_cfg["port"]), step=1,
                                                 help="TWS 7496 live / 7497 paper · Gateway 4001 / 4002"))
            ib_cfg["client_id"] = int(st.number_input("Client ID", value=int(ib_cfg["client_id"]), step=1))
            mdt = {"Live (1)": 1, "Delayed (3)": 3, "Delayed frozen (4)": 4}
            ib_cfg["market_data_type"] = mdt[st.selectbox("Market data", list(mdt),
                                                          index=list(mdt.values()).index(ib_cfg["market_data_type"]))]
    if st.button("↻ Refresh data", width="stretch"):
        st.cache_data.clear()
    html(ui.title("Display"))
    since = st.date_input("'Since' reference date", value=date(2026, 10, 28),
                          help="Used by the 'Since' pill (e.g. last FOMC decision).")
    show_mock = st.toggle("Show mock rows", value=False, help="Fill curves that returned no data with MOCK rows.")


# =========================================================================== data (cached)
def _ib_contracts(with_zq: bool):
    c = {cv: {k: v for k, v in spec["conids"].items() if k in CODES} for cv, spec in CURVES.items()}
    ex = {cv: spec["exchange"] for cv, spec in CURVES.items()}
    if with_zq:
        c[ZQ_KEY], ex[ZQ_KEY] = ZQ_CFG["conids"], ZQ_CFG["exchange"]
    return c, ex


def _ib(kind: str, cfg: dict):
    flags = {"daily": dict(daily=True, intraday=False, snapshot=False),
             "intraday": dict(daily=False, intraday=True, snapshot=False),
             "last": dict(daily=False, intraday=False, snapshot=True)}[kind]
    contracts, exchanges = _ib_contracts(with_zq=kind != "intraday")
    offset = {"daily": 0, "intraday": 1, "last": 2}[kind]  # distinct client ids, no clash between calls
    try:
        return sources.ibkr_fetch(contracts, exchanges, cfg["host"], cfg["port"], cfg["client_id"] + offset,
                                  cfg["market_data_type"], cfg["timeout"], **flags)
    except sources.IBKRUnavailable as e:
        return {"unavailable": str(e)}
    except Exception as e:  # noqa: BLE001
        return {"unavailable": f"IBKR {kind}: {e}"}


@st.cache_data(ttl=3600, show_spinner=False)
def ib_daily(cfg):
    return _ib("daily", cfg)


@st.cache_data(ttl=300, show_spinner=False)
def ib_intraday(cfg):
    return _ib("intraday", cfg)


@st.cache_data(ttl=60, show_spinner=False)
def ib_last(cfg):
    return _ib("last", cfg)


def _yahoo_map(codes, root, exch):
    return {calc.contract_ticker(c, root, exch, YCFG["ticker_template"]): c for c in codes}


@st.cache_data(ttl=60, show_spinner=False)
def yahoo_sofr():
    tick = _yahoo_map(CODES, CURVES["SOFR"]["yahoo_root"], CURVES["SOFR"]["yahoo_exchange"])
    out, errs = {}, []
    for kind, period, interval in (("intraday", YCFG["intraday_period"], YCFG["intraday_interval"]),
                                   ("daily", YCFG["daily_period"], "1d")):
        try:
            out[kind] = {tick[t]: s for t, s in sources.yahoo_prices(list(tick), period, interval).items()}
        except Exception as e:  # noqa: BLE001
            out[kind] = {}
            errs.append(f"Yahoo SOFR {kind}: {e}")
    return out, errs


@st.cache_data(ttl=600, show_spinner=False)
def yahoo_zq():
    tick = _yahoo_map(list(ZQ_CFG["conids"]), ZQ_CFG["yahoo_root"], ZQ_CFG["yahoo_exchange"])
    try:
        return {tick[t]: s for t, s in sources.yahoo_prices(list(tick), YCFG["daily_period"], "1d").items()}, None
    except Exception as e:  # noqa: BLE001
        return {}, f"Yahoo Fed Funds: {e}"


@st.cache_data(ttl=3600, show_spinner=False)
def load_fixings():
    start = (date.today() - timedelta(days=400)).isoformat()
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
    out, errs = {"intraday": {}, "daily": {}}, []
    for kind, period, interval in (("intraday", YCFG["intraday_period"], YCFG["intraday_interval"]),
                                   ("daily", YCFG["daily_period"], "1d")):
        try:
            out[kind] = {tick[t]: s for t, s in sources.yahoo_prices(list(tick), period, interval).items()}
        except Exception as e:  # noqa: BLE001
            errs.append(f"Yahoo bonds {kind}: {e}")
    return out, errs


@st.cache_data(ttl=1800, show_spinner=False)
def load_speeches():
    try:
        return sources.fed_speeches(CFG["fed_speeches_rss"]), None
    except Exception as e:  # noqa: BLE001
        return [], f"Fed speeches RSS: {e}"


def with_last(intraday: dict, last: dict) -> dict:
    """Append the latest snapshot price as a final intraday point (if newer)."""
    out = dict(intraday)
    now = pd.Timestamp.now(tz="UTC")
    for code, px in last.items():
        s = out.get(code)
        out[code] = pd.concat([s, pd.Series([px], index=[now])]) if s is not None and len(s) else pd.Series([px], index=[now])
    return out


def assemble():
    """STRIPS[curve] = {intraday, daily, source}; ZQ[(y, m)] = daily Series."""
    errors, strips, zq, zq_src = [], {cv: {"intraday": {}, "daily": {}, "source": None} for cv in CURVES}, {}, None
    if provider in ("auto", "ibkr"):
        cfg = {**ib_cfg, "timeout": CFG["ibkr"]["timeout"]}
        d, i, l = ib_daily(cfg), ib_intraday(cfg), ib_last(cfg)
        if "unavailable" in d:
            errors.append(d["unavailable"])
        else:
            for part in (d, i, l):
                errors += part.get("errors", [])
            for cv in CURVES:
                daily = d["daily"].get(cv, {})
                intra = with_last(i.get("intraday", {}).get(cv, {}), l.get("last", {}).get(cv, {}))
                if daily or intra:
                    strips[cv] = {"intraday": intra, "daily": daily, "source": "IBKR"}
            for code, s in d["daily"].get(ZQ_KEY, {}).items():
                y, m = 2000 + int(code[1:]), calc.MONTH_CODES[code[0]]
                zq[(y, m)] = s
            zq_src = "IBKR" if zq else None
    if provider in ("auto", "yahoo"):
        if strips["SOFR"]["source"] is None:
            ys, errs = yahoo_sofr()
            errors += errs
            if ys["daily"] or ys["intraday"]:
                strips["SOFR"] = {**ys, "source": "Yahoo"}
        if not zq:
            got, err = yahoo_zq()
            if err:
                errors.append(err)
            for code, s in got.items():
                zq[(2000 + int(code[1:]), calc.MONTH_CODES[code[0]])] = s
            zq_src = "Yahoo" if zq else None
    return strips, zq, zq_src, errors


with st.spinner("Loading market data…"):
    STRIPS, ZQ, ZQ_SRC, ERRORS = assemble()
    FIX, fix_errs = load_fixings()
    BONDS, bond_errs = load_bonds()
    SPEECHES, sp_err = load_speeches()
ERRORS += fix_errs + bond_errs + ([sp_err] if sp_err else [])


def is_live(cv):
    return STRIPS[cv]["source"] is not None


with st.sidebar:
    html(ui.title("Data status"))
    lines = [f"{cv}: {STRIPS[cv]['source'] or '—'} ({len(STRIPS[cv]['daily'])} contracts)" for cv in CURVES]
    lines.append(f"Fed Funds: {ZQ_SRC or '—'} ({len(ZQ)} months)")
    lines.append(f"Fixings: {len(FIX)}/{len(CFG['fixings'])}")
    st.caption("  \n".join(lines))
    for e in ERRORS[:25]:
        st.warning(e, icon="⚠️")
    if len(ERRORS) > 25:
        st.caption(f"…and {len(ERRORS) - 25} more")


def tag_for(curves):
    live = [is_live(c) for c in curves]
    if all(live):
        return "live"
    if any(live):
        return "mixed" if show_mock else "live"
    return "mock" if show_mock else ""


# =========================================================================== header + fixings
bars = [s.index[-1] for cv in CURVES for s in STRIPS[cv]["intraday"].values() if len(s)]
stamp = max(bars).tz_convert("Europe/London").strftime("%d %b %y · %H:%M London") if bars else "no intraday data"
src = sorted({STRIPS[cv]["source"] for cv in CURVES if STRIPS[cv]["source"]})
html(f'<div style="display:flex;justify-content:space-between;flex-wrap:wrap;gap:6px;margin-bottom:10px">'
     f'<div style="font-size:15px;font-weight:600;letter-spacing:.14em"><span style="color:#22d3ee">■</span> STIR / SHORT-RATES MONITOR</div>'
     f'<div style="font-size:11px;color:#8a93a4">{" + ".join(src) or "NO FUTURES FEED"} · LAST BAR {stamp.upper()}</div></div>')

with st.container(border=True):
    html(ui.title("Overnight fixings", "% · Δ bp", "live" if FIX else ""))
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


def curve_row(cv, values_live, values_mock):
    """(name, values, is_mock) or None when the curve has no data and mock is off."""
    if is_live(cv):
        return (cv, values_live(), False)
    if show_mock:
        return (cv, values_mock(), True)
    return None


# =========================================================================== heatmap
HEAT_TF = ["15m", "30m", "1h", "Day", "Week", "Since", "Since EU Open"]
cols = CFG["contracts"]
with st.container(border=True):
    c1, c2 = st.columns([1, 1.4])
    with c1:
        html(ui.title("Net change", "Outrights · bp", tag_for(CFG["heatmap_curves"])))
    with c2:
        tf = pills(HEAT_TF, "Day", "heat_tf")
    rows = []
    for cv in CFG["heatmap_curves"]:
        S = STRIPS[cv]
        r = curve_row(cv, lambda S=S: list(calc.strip_changes(cols, S["intraday"], S["daily"], tf, since).values()),
                      lambda cv=cv: list(mock.strip(cv, cols, tf).values()) if cv in mock.PROFILES else [None] * len(cols))
        if r:
            rows.append(r)
    if rows:
        html(ui.heat_table(cols, rows))
    else:
        st.info("No outright data. Check the IBKR connection in the sidebar.")
    html('<div class="note">Rate change in bp vs reference (−Δprice×100). White border = largest |move| in row. '
         f'Day = vs prior settle · Week = vs last Friday · Since = vs close on {since:%d %b %y}. '
         '— = contract expired / not listed.</div>')

# =========================================================================== dec spreads + sentiment
left, right = st.columns([6, 6])
with left, st.container(border=True):
    html(ui.title("Dec spreads", "Δ bp", tag_for(CFG["dec_spread_curves"])))
    pairs = CFG["dec_pairs"]
    rows = []
    for cv in CFG["dec_spread_curves"]:
        S = STRIPS[cv]
        r = curve_row(cv, lambda S=S: calc.dec_spread_changes(pairs, S["intraday"], S["daily"], "Day")
                      + calc.dec_spread_changes(pairs, S["intraday"], S["daily"], "Week"),
                      lambda cv=cv: mock.dec_spreads(cv, "Day") + mock.dec_spreads(cv, "Week") if cv in mock.PROFILES else [None] * 6)
        if r:
            rows.append(r)
    if rows:
        html(ui.heat_table([p[2] for p in pairs] * 2, rows, groups=[("DAY", 3), ("THIS WEEK", 3)]))
    else:
        st.info("No data.")
    html('<div class="note">Spread = price(front Z) − price(back Z). THIS WEEK = vs last Friday settle.</div>')

with right, st.container(border=True):
    k = CFG["sentiment_contract"]
    html(ui.title(f"{k} · vs Fri settle", "", tag_for(CFG["sentiment_curves"])))
    stf = pills(["Day", "Week", "1W", "1M", "3M", "6M"], "Day", "sent_tf")
    vals = {}
    for cv in CFG["sentiment_curves"]:
        S = STRIPS[cv]
        if is_live(cv):
            vals[cv] = calc.strip_changes([k], S["intraday"], S["daily"], stf)[k]
        elif show_mock and cv in mock.SENTIMENT_BASE:
            vals[f"{cv} (mock)"] = mock.sentiment(cv, stf)
    items = sorted([(n, v) for n, v in vals.items() if v is not None], key=lambda x: x[1])
    if not items:
        st.info(f"No {k} data available.")
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
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})

# =========================================================================== net change curve
with st.container(border=True):
    title_slot = st.empty()
    strip_modes = [cv for cv in CURVES if is_live(cv)]
    mode = pills(["Bonds"] + strip_modes, strip_modes[0] if strip_modes else "Bonds", "curve_mode")
    ctf = pills(["15m", "30m", "1h", "Day", "Since"], "Day", "curve_tf")
    title_slot.markdown(ui.title("Net change curve", f"{mode} · bp vs reference", "live"), unsafe_allow_html=True)
    if mode == "Bonds":
        pts = []
        for b in CFG["bonds"]:
            lb = b["label"]
            last = calc.last_price(BONDS["intraday"].get(lb), BONDS["daily"].get(lb))
            ref = calc.reference_price(ctf, BONDS["intraday"].get(lb), BONDS["daily"].get(lb), since)
            v = calc.yield_change_bp(last, ref)
            if v is not None:
                pts.append((lb, v))
        dec = 1
    else:
        S = STRIPS[mode]
        ch = calc.strip_changes(cols, S["intraday"], S["daily"], ctf, since)
        pts = [(c, ch[c]) for c in cols if ch[c] is not None]
        dec = 2
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
                                 text=["" if i in (imax, imin) else ui.fmt(y, dec) for i, y in enumerate(ys)],
                                 cliponaxis=False, textposition="top center",
                                 textfont=dict(family="IBM Plex Mono", size=11, color="#c4cad5"), hoverinfo="x+y"))
        for i, col, nm in ((imax, "#22c55e", "max"), (imin, "#22d3ee", "min")):
            fig.add_trace(go.Scatter(x=[xs[i]], y=[ys[i]], mode="markers+text", text=[f"{nm} {ui.fmt(ys[i], dec)}"],
                                     textposition="bottom center" if nm == "min" else "top center",
                                     textfont=dict(family="IBM Plex Mono", size=12, color=col),
                                     marker=dict(size=14, color=col, line=dict(color="#12161f", width=2)),
                                     hoverinfo="skip", cliponaxis=False))
        fig.update_layout(height=340, showlegend=False, margin=dict(l=0, r=30, t=30, b=10),
                          paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                          font=dict(family="IBM Plex Mono", color="#8a93a4", size=11),
                          yaxis=dict(gridcolor="#262e3c", zerolinecolor="#5d6576", ticksuffix=" bp"),
                          xaxis=dict(gridcolor="rgba(0,0,0,0)", range=[-0.4, len(xs) - 0.6]))
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})

# =========================================================================== priced moves
FED_HIST = calc.priced_history(FOMC, ZQ, days=10, start_rate_series=FIX.get("EFFR"))


def boc_history(days=10):
    """Approximate BoC path per session from the 3M CORRA strip (see calc.strip_meeting_path)."""
    daily = STRIPS["CORRA"]["daily"]
    corra = FIX.get("CORRA")
    frame = pd.DataFrame(daily).dropna(how="all")
    if frame.empty or corra is None or corra.empty:
        return []
    paths = []
    for s in list(frame.index[-(days + 2):])[::-1]:
        row = frame.loc[s].dropna()
        cur = calc._asof(corra, s)
        if cur is None:
            continue
        rates = {c: 100 - float(v) for c, v in row.items()}
        paths.append((pd.Timestamp(s).date(), calc.strip_meeting_path(BOC, rates, cur, pd.Timestamp(s).date())))
    out = []
    for i in range(len(paths) - 1):
        d, rows = paths[i]
        prev = {r.meeting: r.cumulative for r in paths[i + 1][1]}
        out.append((d, rows, [round(r.cumulative - prev[r.meeting], 1) if r.meeting in prev else None for r in rows]))
    return out


def stepper(key, max_days):
    return int(st.number_input("N DAYS AGO", min_value=0, max_value=max(0, max_days), value=min(1, max_days),
                               step=1, key=key))


pl, pr = st.columns(2)
with pl, st.container(border=True):
    html(ui.title("Priced moves", f"SOFR / Fed · ZQ{' · ' + ZQ_SRC if ZQ_SRC else ''}", "live" if FED_HIST else ""))
    if not FED_HIST or not FED_HIST[0][1]:
        st.info("Fed Funds futures unavailable. See Data status.")
    else:
        n = stepper("fed_days", len(FED_HIST) - 1)
        d, rows, delta = FED_HIST[n]
        st.caption(f"As of settle {d:%a %d %b %y} · start rate {rows[0].implied - rows[0].cumulative / 100:.3f}%")
        html(ui.priced_table(rows, delta))
        html('<div class="note">Meeting-by-meeting from monthly ZQ averages (FedWatch method). Cumulative = running sum '
             'of moves · Implied = start + cumulative · Δ1D on cumulative.</div>')

BOC_HIST = boc_history() if is_live("CORRA") else []
with pr, st.container(border=True):
    live_boc = bool(BOC_HIST and BOC_HIST[0][1])
    html(ui.title("Priced moves", "CORRA / BoC · CRA strip", "live" if live_boc else "mock" if show_mock else ""))
    if live_boc:
        n = stepper("boc_days", len(BOC_HIST) - 1)
        d, rows, delta = BOC_HIST[n]
        st.caption(f"As of settle {d:%a %d %b %y} · start rate (CORRA) {rows[0].implied - rows[0].cumulative / 100:.3f}%")
        html(ui.priced_table(rows, delta))
        html('<div class="note">Approximate: piecewise-constant path fitted to quarterly 3M CORRA futures '
             '(no monthly CORRA contract exists), lightly smoothed.</div>')
    elif show_mock:
        n = stepper("boc_days", 5)
        today_m, prev_m = mock.boc_moves(n), mock.boc_moves(n + 1)
        rows, deltas, cum, pcum = [], [], 0.0, 0.0
        for m, mv, pm in zip(BOC, today_m, prev_m):
            cum, pcum = cum + mv, pcum + pm
            rows.append(calc.MeetingRow(m, mv, round(cum, 1), round(mock.BOC_START + cum / 100, 3)))
            deltas.append(round(cum - pcum, 1))
        st.caption(f"MOCK · {n} day(s) ago · start rate {mock.BOC_START:.2f}%")
        html(ui.priced_table(rows, deltas))
    else:
        st.info("Needs CORRA futures from IBKR and the CORRA fixing. See Data status.")

# =========================================================================== speakers
html('<div style="height:6px"></div>' + ui.title("Central bank speakers"))
if FED_HIST and len(FED_HIST[0][1]) >= 2:
    r0 = FED_HIST[0][1]
    priced = {"dec": f"~{r0[0].move:.0f}bp", "jan": f"~{r0[1].cumulative:.0f}bp"}
else:
    priced = {"dec": "n/a", "jan": "n/a"}
for col, s in zip(st.columns(len(SPEAKERS)), SPEAKERS):
    with col, st.container(border=True):
        html(ui.speaker_card(s, priced))
        st.caption("Manual entry · edit speakers.json · RATES READ pricing is filled live from Fed Funds futures.")

with st.container(border=True):
    html(ui.title("Latest Fed speeches", "federalreserve.gov RSS", "live" if SPEECHES else ""))
    if not SPEECHES:
        st.info("Fed speeches feed unavailable.")
    for sp in SPEECHES:
        dt = sp["date"].strftime("%d %b %y") if pd.notna(sp["date"]) else ""
        html(f'<div style="font-size:12px;margin:3px 0"><span style="color:#8a93a4">{dt}</span> &nbsp; '
             f'<a href="{sp["link"]}" target="_blank" style="color:#d7dce5">{sp["title"]}</a></div>')
