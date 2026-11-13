"""Page 2 — Macro read: 3×2 gauges, regime cell, curve segment, credibility switch (§1.3)."""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from datahub import ui

from . import common as C

# --- transforms --------------------------------------------------------------
def ann3m(s): return ((s / s.shift(3)) ** 4 - 1) * 100
def yoy(s): return (s / s.shift(12) - 1) * 100
def level(s): return s
def chg3m(s): return s - s.shift(3)
def payroll3m(s): return s.diff().rolling(3).mean()
def ma4k(s): return s.rolling(4).mean() / 1000.0
def perm_yoy(s): return (s / s.shift(12) - 1) * 100
def thousands(s): return s / 1000.0

# region, gauge, horizon, label, key, transform, reference ('mean' or number), invert, unit
COMPONENTS = [
    ("US", "inflation", "spot", "Core CPI 3m annualised", "core_cpi", ann3m, 2.0, False, "%"),
    ("US", "inflation", "spot", "Core PCE 3m annualised", "core_pce", ann3m, 2.0, False, "%"),
    ("US", "inflation", "spot", "Core CPI y/y", "core_cpi", yoy, 2.0, False, "%"),
    ("US", "inflation", "forward", "5y5y forward inflation", "fwd5y5y", level, "mean", False, "%"),
    ("US", "inflation", "forward", "5Y breakeven", "bei5", level, "mean", False, "%"),
    ("US", "inflation", "forward", "UMich 1Y inflation expectations", "mich_infl", level, 3.0, False, "%"),
    ("US", "growth", "spot", "Industrial production 3m ann.", "indpro", ann3m, 1.0, False, "%"),
    ("US", "growth", "spot", "Retail sales ex autos 3m ann.", "retail_core", ann3m, 3.0, False, "%"),
    ("US", "growth", "spot", "Atlanta Fed GDPNow", "gdpnow", level, 2.0, False, "%"),
    ("US", "growth", "forward", "Building permits y/y", "permit", perm_yoy, 0.0, False, "%"),
    ("US", "growth", "forward", "UMich sentiment", "umcsent", level, "mean", False, "idx"),
    ("US", "growth", "forward", "2s10s curve", "__2s10s", level, "mean", False, "%"),
    ("US", "growth", "forward", "NFCI (tighter = cool)", "nfci", level, 0.0, True, "idx"),
    ("US", "labour", "spot", "Unemployment rate", "unrate", level, 4.2, True, "%"),
    ("US", "labour", "spot", "Unemployment 3m change", "unrate", chg3m, 0.0, True, "pp"),
    ("US", "labour", "spot", "Payrolls 3m average", "payems", payroll3m, 100.0, False, "k"),
    ("US", "labour", "spot", "Avg hourly earnings y/y", "ahe", yoy, 3.5, False, "%"),
    ("US", "labour", "forward", "Initial claims 4w avg", "claims", ma4k, 230.0, True, "k"),
    ("US", "labour", "forward", "Continuing claims", "cont_claims", thousands, "mean", True, "k"),
    ("US", "labour", "forward", "JOLTS openings", "jolts", level, "mean", False, "k"),
    ("US", "labour", "forward", "JOLTS quits rate", "quits", level, 2.3, False, "%"),
    ("EA", "inflation", "spot", "HICP 3m annualised", "ea_hicp", ann3m, 2.0, False, "%"),
    ("EA", "inflation", "spot", "HICP y/y", "ea_hicp", yoy, 2.0, False, "%"),
    ("EA", "growth", "forward", "EA business confidence", "ea_bus_conf", level, "mean", False, "idx"),
    ("EA", "labour", "spot", "EA unemployment", "ea_unemp", level, "mean", True, "%"),
    ("UK", "labour", "spot", "UK unemployment", "uk_unemp", level, 4.3, True, "%"),
]
GAUGE_W = {"inflation": 0.4, "growth": 0.3, "labour": 0.3}
CELLS = {
    (1, 1): ("Overheating", "spot hot, forward hot", "Front and belly bear-flatten in a credible regime; the policy-path trade dominates."),
    (1, -1): ("Late cycle", "spot hot, forward cool", "Peak rates, hump in 2s5s10s; in a supply shock the expression migrates to 5s30s / 10s30s."),
    (-1, 1): ("Early reacceleration", "spot cool, forward hot", "Belly leads; 2s5s bear-steepener (front pinned, belly cheapens to price forward hikes)."),
    (-1, -1): ("Slowdown", "spot cool, forward cool", "Bull-steepener as cuts get priced, then bull-flatten; front rallies first."),
}
REACTION = {
    "Fed": "Dual mandate. Data that enters: core PCE and supercore, payrolls / unemployment, SEP dots. Threshold language: 'inflation sustainably toward 2%', labour 'solid'. Committee: map hawks / doves / centrists here.",
    "ECB": "Three legs — inflation outlook, underlying inflation dynamics, strength of transmission. Data: HICP core, negotiated wages, PMI prices, bank lending survey. Meeting-by-meeting, no pre-commitment.",
    "BoE": "Services CPI, AWE private regular pay persistence, DMP survey expectations, labour slack. Guidance: 'gradual and careful'. Vote split is the signal.",
}


def _component_frame(res) -> pd.DataFrame:
    rows = []
    for region, gauge, horizon, label, key, tf, ref, inv, unit in COMPONENTS:
        if key == "__2s10s":
            s = (C.series(res, "ust10") - C.series(res, "ust2")).dropna()
        else:
            s = C.series(res, key)
        if s.empty:
            rows.append(dict(region=region, gauge=gauge, horizon=horizon, component=label, value=np.nan, ref=np.nan,
                             scale=np.nan, z=np.nan, last=None, quality="unavailable", unit=unit, stale=True))
            continue
        t = tf(s).dropna()
        if t.empty:
            continue
        hist = t.iloc[-120:] if len(t) > 120 else t  # ~10y monthly or 120 obs
        reference = float(hist.mean()) if ref == "mean" else float(ref)
        scale = float(hist.std()) if hist.std() and np.isfinite(hist.std()) else np.nan
        z = (float(t.iloc[-1]) - reference) / scale if scale and scale > 0 else np.nan
        if inv and np.isfinite(z):
            z = -z
        z = float(np.clip(z, -3, 3)) if np.isfinite(z) else np.nan
        last_date = t.index[-1]
        stale = (pd.Timestamp.today() - last_date).days > 400
        q = C.quality_of(key) if key != "__2s10s" else "live"
        rows.append(dict(region=region, gauge=gauge, horizon=horizon, component=label, value=float(t.iloc[-1]), ref=reference,
                         scale=scale, z=z, last=last_date.date(), quality=("stale" if stale else q), unit=unit, stale=stale))
    return pd.DataFrame(rows)


def _gauges(comp: pd.DataFrame, region: str) -> dict:
    out = {}
    for gauge in ("inflation", "growth", "labour"):
        for horizon in ("spot", "forward"):
            sub = comp[(comp.region == region) & (comp.gauge == gauge) & (comp.horizon == horizon) & comp.z.notna() & ~comp.stale]
            out[(gauge, horizon)] = int(np.clip(round(sub["z"].mean()), -2, 2)) if len(sub) else None
    return out


def _composite(g: dict, horizon: str):
    vals = [(g[(k, horizon)], w) for k, w in GAUGE_W.items() if g.get((k, horizon)) is not None]
    if not vals:
        return np.nan
    return sum(v * w for v, w in vals) / sum(w for _, w in vals)


def _heat(g: dict, title: str):
    z = [[g.get((k, "spot")), g.get((k, "forward"))] for k in ("inflation", "growth", "labour")]
    text = [[("n/a" if v is None else f"{v:+d}") for v in row] for row in z]
    zz = [[0 if v is None else v for v in row] for row in z]
    fig = go.Figure(go.Heatmap(z=zz, x=["Spot — what is happening", "Forward — what is coming"], y=["Inflation", "Growth", "Labour"],
                               zmin=-2, zmax=2, colorscale=[[0, "#2F6DB5"], [0.5, "#F5F7FA"], [1, "#B71C1C"]], text=text,
                               texttemplate="%{text}", showscale=False))
    fig.update_yaxes(autorange="reversed")
    return C.plotly_layout(fig, height=230, title=title)


def render():
    ui.step("1.3", "Macro read — gauges, regime cell, curve segment",
            "Three variables, each read spot and forward, scored −2…+2 and signed so that hot always means hawkish.")
    res = C.market()
    comp = _component_frame(res)
    st.markdown("z<sub>i</sub> = (value<sub>i</sub> − reference<sub>i</sub>) / scale<sub>i</sub> · gauge = clamp(round(mean z), −2, +2). "
                "Reference = target or neutral where one exists, else the 10-year mean; scale = 10-year std of the component; "
                "inverted components (unemployment, claims, NFCI) are negated.", unsafe_allow_html=True)

    region = st.radio("Region", ["US", "EA", "UK"], horizontal=True, key="macro_region")
    auto = _gauges(comp, region)
    overrides = C.ss_get("gauge_overrides", {})

    c1, c2 = st.columns([1.1, 1])
    with c1:
        st.plotly_chart(_heat(auto, f"{C.REGION_LABEL[region]} gauges — computed"), width="stretch")
        st.markdown(ui.badge("live") + " computed from the components below; " + ui.badge("manual") + " when overridden", unsafe_allow_html=True)
    with c2:
        st.markdown("**Desk override** (slider = manual gauge; tick *use* to apply)")
        final = {}
        for gauge in ("inflation", "growth", "labour"):
            cols = st.columns(2)
            for col, horizon in zip(cols, ("spot", "forward")):
                k = f"{region}:{gauge}:{horizon}"
                base = auto.get((gauge, horizon))
                with col:
                    use = st.checkbox(f"use {gauge} {horizon}", value=overrides.get(k, {}).get("use", base is None), key=f"use_{k}")
                    val = st.slider(f"{gauge} {horizon}", -2, 2, int(overrides.get(k, {}).get("val", base if base is not None else 0)), key=f"sl_{k}")
                overrides[k] = {"use": use, "val": val}
                final[(gauge, horizon)] = val if use else base
        st.session_state["gauge_overrides"] = overrides

    spot_c, fwd_c = _composite(final, "spot"), _composite(final, "forward")
    sign = lambda v: 1 if (np.isfinite(v) and v > 0) else -1
    lit = np.isfinite(spot_c) and np.isfinite(fwd_c) and abs(spot_c) >= 0.25 and abs(fwd_c) >= 0.25
    if lit:
        cell = CELLS[(sign(spot_c), sign(fwd_c))]
    else:
        near = CELLS[(sign(spot_c), sign(fwd_c))]
        cell = ("No cell clearly lit", "a composite sits inside ±0.25", f"Nearest cell: {near[0]} ({near[1]}). Wait for data, or set the gauges by hand; do not route a curve segment off a neutral read.")
    st.markdown("---")
    k1, k2, k3 = st.columns([1, 1, 2])
    k1.metric("Spot composite", C.fmt(spot_c, 2), help="0.4 inflation + 0.3 growth + 0.3 labour")
    k2.metric("Forward composite", C.fmt(fwd_c, 2))
    k3.markdown(f"<div style='border:1px solid {C.BRONZE};border-radius:8px;padding:10px 14px;background:rgba(169,129,79,0.08)'>"
                f"<b style='color:{C.NAVY};font-size:16px'>Regime cell: {cell[0]}</b> <span style='color:{C.SLATE}'>— {cell[1]}</span><br>"
                f"<span style='font-size:13px'>{cell[2]}</span></div>", unsafe_allow_html=True)
    if not (np.isfinite(spot_c) and np.isfinite(fwd_c)):
        st.warning("At least one composite is undefined for this region (missing public series) — use the manual sliders.")

    st.subheader("Components")
    show = comp[comp.region == region].copy()
    if show.empty:
        st.info("No public components configured for this region; gauges are manual.")
    else:
        show["z"] = show["z"].round(2); show["value"] = show["value"].round(2); show["ref"] = show["ref"].round(2); show["scale"] = show["scale"].round(2)
        st.dataframe(show[["gauge", "horizon", "component", "value", "unit", "ref", "scale", "z", "last", "quality"]], hide_index=True,
                     width="stretch", height=min(700, 38 + 35 * len(show)))
        st.caption("quality: live = official print via FRED; proxy = monthly OECD/Eurostat mirror (lagging); stale = last print older than ~13 months, excluded from the gauge.")
    if region == "UK":
        st.info("UK CPI and wage series are not on the public FRED mirror in a usable form — set the UK inflation gauges by hand (services CPI, AWE).")
    if region == "EA":
        st.info("EA forward inflation (inflation swaps, SPF) and spot growth (PMI) are not public daily series — set them by hand; HICP comes from Eurostat via FRED.")

    # --- component chart ----------------------------------------------------
    with st.expander("Component history"):
        opts = [r for r in COMPONENTS if r[0] == region]
        pick = st.selectbox("Component", [r[3] for r in opts])
        row = next(r for r in opts if r[3] == pick)
        s = (C.series(res, "ust10") - C.series(res, "ust2")).dropna() if row[4] == "__2s10s" else C.series(res, row[4])
        if not s.empty:
            t = row[5](s).dropna().iloc[-180:]
            fig = go.Figure(go.Scatter(x=t.index, y=t.values, line=dict(color=C.NAVY)))
            ref = row[6] if row[6] != "mean" else float(t.mean())
            fig.add_hline(y=ref, line=dict(color=C.BRONZE, dash="dash"), annotation_text="reference")
            st.plotly_chart(C.plotly_layout(fig, height=300, title=pick), width="stretch")
        else:
            st.write("unavailable")

    # --- segment routing ----------------------------------------------------
    st.subheader("Curve segment routing")
    st.markdown("""
| Segment | What it chiefly reads | Lit by |
|---|---|---|
| Cash–2y | Pure expected policy path (~2y) | Overheating / Slowdown — the path trade |
| 2s5s | Forward cycle continuation — more or fewer hikes/cuts coming | Early reacceleration (bear-steepener) |
| 2s10s | Whole path plus some term premium (canonical gauge) | All cells, confirmation |
| 2s5s10s fly | Curvature and timing — where peak rates sit | Late cycle (hump) |
| 5s30s · 10s30s | Terminal rate and r* blended with term premium · almost pure term premium and supply | Late cycle under a supply shock; fiscal dominance |
""")

    # --- credibility switch -------------------------------------------------
    st.subheader("Credibility switch — sign before size")
    tp, ust10, ust2 = C.series(res, "tp10"), C.series(res, "ust10"), C.series(res, "ust2")
    if not tp.empty and not ust10.empty and not ust2.empty:
        df = pd.concat([tp, ust10, ust2], axis=1, keys=["tp", "y10", "y2"]).dropna()
        n = min(63, len(df) - 1)
        d = df.iloc[-1] - df.iloc[-1 - n]
        exp_part = d["y10"] - d["tp"]
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Δ10y, 3m", f"{d['y10'] * 100:+.0f} bp")
        c2.metric("of which term premium (ACM)", f"{d['tp'] * 100:+.0f} bp")
        c3.metric("of which expected rates", f"{exp_part * 100:+.0f} bp")
        c4.metric("Δ2y, 3m", f"{d['y2'] * 100:+.0f} bp")
        if d["tp"] > 0.10 and d["tp"] > abs(exp_part) and d["y10"] > d["y2"]:
            verdict = "Term-premium-led bear steepening: long-end moves are not a reaction-function read. Treat hot prints as potential bear steepeners (fiscal-dominance tell) and pair front-end views with a curve leg."
        elif d["y2"] > d["y10"]:
            verdict = "Front-led flattening: the move is a policy-path repricing under credible targeting. Hot prints bear-flatten; the front-end view stands alone."
        else:
            verdict = "Mixed: expected-rate and term-premium components comparable. Decompose before reading the long end as macro."
        st.markdown(ui.badge("live") + f" ACM term premium (FRED THREEFYTP10), last {df.index[-1].date()} — **{verdict}**", unsafe_allow_html=True)
        fig = go.Figure()
        w = df.iloc[-504:]
        fig.add_trace(go.Scatter(x=w.index, y=w["y10"] - w["tp"], name="10y expected-rate component", line=dict(color=C.NAVY)))
        fig.add_trace(go.Scatter(x=w.index, y=w["tp"], name="10y term premium (ACM)", line=dict(color=C.BRONZE)))
        fig.add_trace(go.Scatter(x=w.index, y=w["y2"], name="2y", line=dict(color=C.SLATE, dash="dot")))
        st.plotly_chart(C.plotly_layout(fig, height=320), width="stretch")
    else:
        st.info("ACM term premium or Treasury yields unavailable — credibility read is manual.")

    # --- reaction functions -------------------------------------------------
    st.subheader("Reaction functions on file")
    rf = C.ss_get("reaction_functions", dict(REACTION))
    cols = st.columns(3)
    for col, cb in zip(cols, ("Fed", "ECB", "BoE")):
        with col:
            rf[cb] = st.text_area(cb, rf.get(cb, REACTION[cb]), height=170, key=f"rf_{cb}")
    st.session_state["reaction_functions"] = rf
    st.markdown(ui.badge("manual") + " reaction functions are desk text: which data enters, with what weight, at what threshold, plus the committee map.", unsafe_allow_html=True)
