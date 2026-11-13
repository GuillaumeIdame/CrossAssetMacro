"""T9/T10 — Crowding score, quality ladder, unwind tree (§1.8)."""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from datahub import stats, ui

from . import data as D
from . import themes as T
from . import universe as U

CROWD_W = dict(positioning=0.30, flow=0.25, volskew=0.20, concentration=0.15, liquidity=0.10)
VOLUME_PROXY = {"spx": "SPY", "ndx": "QQQ", "rut": "IWM", "ust10": "IEF", "ust30": "TLT", "zn": "IEF", "zb": "TLT", "ust2": "SHY", "ust5": "IEF",
                "gold": "GLD", "brent": "USO", "wti": "USO", "eem": "EEM", "eurusd": "FXE", "usdjpy": "FXY", "dxy": "UUP", "xle": "XLE"}

SHOCKS = {
    "Rates +35 bp (bear flattener)": dict(ust2=35, ust10=25, ust30=20, spx=-4, dxy=1.5, gold=-3, brent=0, vix=5, hy_oas=30),
    "Equity −10% risk-off": dict(ust2=-30, ust10=-25, ust30=-15, spx=-10, dxy=2, gold=2, brent=-8, vix=15, hy_oas=120),
    "Oil +15% supply shock": dict(ust2=10, ust10=15, ust30=20, spx=-3, dxy=0.5, gold=2, brent=15, vix=4, hy_oas=25),
    "USD −5% confidence shock": dict(ust2=0, ust10=20, ust30=30, spx=-5, dxy=-5, gold=6, brent=3, vix=6, hy_oas=40),
    "Carry unwind (Aug-2024 type)": dict(ust2=-40, ust10=-25, ust30=-10, spx=-7, dxy=-2, gold=-1, brent=-6, vix=20, hy_oas=60),
}


@st.cache_data(ttl=3600, show_spinner=False)
def crowding_table():
    frame, _, _ = D.load_universe()
    cftc_m, cftc_status, _ = D.load_cftc()
    vols = D.load_volumes()
    univ = U.build(frame)
    rows = []
    for k, ins in univ.items():
        s = ins.series.dropna()
        if len(s) < 300:
            continue
        cta = stats.cta_ensemble(U.price_proxy(ins))
        cta_pct = min(100.0, abs(cta["ensemble"]) * 100) if np.isfinite(cta["ensemble"]) else np.nan
        parts, q = {}, {}
        # positioning extremity
        cf = np.nan
        if cftc_m is not None and not cftc_m.empty and ins.cftc_key in set(cftc_m["key"]):
            cf = float(cftc_m[cftc_m["key"] == ins.cftc_key]["ratio_pct"].iloc[0])
        parts["positioning"] = np.nanmax([cf, cta_pct]) if (np.isfinite(cf) or np.isfinite(cta_pct)) else np.nan
        q["positioning"] = "live" if np.isfinite(cf) else "estimated"
        # marginal flow — ETF flow not public here; volume z of the ETF proxy as the stand-in
        vt = VOLUME_PROXY.get(k)
        if vt and not vols.empty and vt in vols.columns:
            v = vols[vt].dropna()
            vz = float((v.iloc[-20:].mean() - v.iloc[-252:].mean()) / v.iloc[-252:].std()) if len(v) > 60 else np.nan
            parts["flow"] = float(np.clip(50 + 25 * vz, 0, 100)) if np.isfinite(vz) else np.nan; q["flow"] = "proxy"
            parts["liquidity"] = float(np.clip(50 - 25 * vz, 0, 100)) if np.isfinite(vz) else np.nan; q["liquidity"] = "proxy"
        else:
            parts["flow"] = np.nan; q["flow"] = "unavailable"; parts["liquidity"] = np.nan; q["liquidity"] = "unavailable"
        # vol & skew
        if ins.vol_key and len(D.series(frame, ins.vol_key)) > 300:
            ivp = D.pct_rank(D.series(frame, ins.vol_key), 756)
            sk = D.pct_rank(D.series(frame, "skew"), 756) if k in ("spx", "ndx", "rut") and len(D.series(frame, "skew")) else np.nan
            parts["volskew"] = float(np.nanmean([ivp, sk])); q["volskew"] = "live"
        else:
            rv = (np.log(s).diff().rolling(20).std()).dropna() if ins.mode == "price" else s.diff().rolling(20).std().dropna()
            parts["volskew"] = D.pct_rank(rv, 756) if len(rv) > 300 else np.nan; q["volskew"] = "proxy"
        parts["concentration"] = np.nan; q["concentration"] = "unavailable"
        vals = {kk: v for kk, v in parts.items() if np.isfinite(v)}
        if vals:
            w = sum(CROWD_W[kk] for kk in vals)
            C = sum(CROWD_W[kk] * v for kk, v in vals.items()) / w
        else:
            C = np.nan
        band = ("clean" if C < 40 else "monitored" if C < 65 else "crowded — no adds" if C < 80 else "fragile — convex only, unwind tree armed") if np.isfinite(C) else "n/a"
        direction = "long" if (np.isfinite(cta["ensemble"]) and cta["ensemble"] > 0) else "short"
        rows.append(dict(key=k, label=ins.label, asset_class=ins.asset_class, C=C, band=band, crowd_direction=direction, **{f"{kk}": parts[kk] for kk in CROWD_W},
                         **{f"q_{kk}": q[kk] for kk in CROWD_W}, mature=cta["mature"], split=cta["split"]))
    return pd.DataFrame(rows).sort_values("C", ascending=False), cftc_status


def render():
    ui.step("T9 · T10", "Crowding score, quality ladder, unwind tree (§1.8)",
            "Where does the book lose together, and which trades are too crowded to add to?")
    df, cftc_status = crowding_table()
    if df.empty:
        st.warning("No instruments scored."); return
    st.markdown("**C = 0.30·positioning + 0.25·marginal flow + 0.20·vol & skew + 0.15·concentration + 0.10·liquidity** (weights renormalised over available components). "
                "C < 40 clean · 40–65 monitored · 65–80 crowded, no adds · > 80 fragile, convex-only.")
    st.markdown(ui.badge("live") + " CFTC percentile when available (status: " + cftc_status[:70] + ") · " + ui.badge("estimated") + " CTA-model percentile · "
                + ui.badge("proxy") + " ETF volume z stands in for flow and liquidity · " + ui.badge("unavailable") + " top-4/top-8 concentration without CFTC", unsafe_allow_html=True)
    show = df[["label", "asset_class", "C", "band", "crowd_direction", "positioning", "flow", "volskew", "concentration", "liquidity", "mature", "split"]]
    st.dataframe(show.style.format({"C": "{:.0f}", "positioning": "{:.0f}", "flow": "{:.0f}", "volskew": "{:.0f}", "concentration": "{:.0f}", "liquidity": "{:.0f}"})
                 .background_gradient(subset=["C"], cmap="YlOrRd", vmin=20, vmax=90), use_container_width=True, hide_index=True, height=480)
    fragile = df[df["C"] >= 65]
    if len(fragile):
        st.error("Fragile / crowded list: " + ", ".join(f"{r['label']} ({r['C']:.0f}, {r['crowd_direction']})" for _, r in fragile.iterrows()))
    st.caption("Crowding is directional and a sizing input; it never initiates a fade without a catalyst. Extreme positioning becomes dangerous when it meets deteriorating marginal flow, rising vol and weakening liquidity. Flow has no edge, fragility does.")

    st.markdown("#### Quality ladder — ten criteria scored 0–2, enter at ≥ 14/20")
    T.init_state()
    names = [t["name"] for t in st.session_state["themes"]]
    sel = st.selectbox("Theme", names, key="q_theme")
    qstore = st.session_state["quality"].setdefault(sel, {c: 1 for c in T.QUALITY_CRITERIA})
    cols = st.columns(5)
    for i, c in enumerate(T.QUALITY_CRITERIA):
        qstore[c] = cols[i % 5].slider(c, 0, 2, int(qstore.get(c, 1)), key=f"q_{sel}_{c}")
    total = sum(qstore.values())
    w1, w2, w3 = st.columns(3)
    why = [w1.checkbox("Catalyst in horizon", key=f"wn1_{sel}"), w2.checkbox("Momentum turning", key=f"wn2_{sel}"), w3.checkbox("Positioning washout", key=f"wn3_{sel}")]
    layers = st.multiselect("Layers aligned (3 of 4 rule)", ["Fundamentals", "Price/Trend", "Positioning/Crowding", "Options/Liquidity"], key=f"lay_{sel}")
    ok = total >= 14 and sum(why) >= 2 and len(layers) >= 3
    ui.kpi_row([("Quality", f"{total}/20"), ("Why-now", f"{sum(why)}/3"), ("Layers aligned", f"{len(layers)}/4"), ("Entry test", "PASS" if ok else "FAIL")])
    st.caption("Enter: Quality ≥ 14/20 ∧ Why-Now ≥ 2 of {catalyst in horizon, momentum turning, positioning washout} ∧ 3 of 4 layers aligned. A post-shock opportunity is fundamentals intact with the other three temporarily dislocated.")

    st.markdown("#### Unwind tree — which positions lose together")
    frame, _, _ = D.load_universe()
    book = st.session_state.get("book", [])
    shock_name = st.selectbox("Stored shock", list(SHOCKS.keys()))
    corr_one = st.toggle("Correlation-to-one (tail) version", value=False)
    sh = SHOCKS[shock_name]
    st.markdown("Shock → vol shock → VaR expansion → deleveraging → forced flow → consensus trades hit → correlation convergence → market de-anchors")
    # propagate shock to each instrument through 60D betas to the shocked factors
    univ = U.build(frame)
    fac = {"ust10": D.series(frame, "ust10").diff() * 100, "spx": np.log(D.series(frame, "spx")).diff() * 100, "dxy": np.log(D.series(frame, "dxy")).diff() * 100,
           "brent": np.log(D.series(frame, "brent")).diff() * 100, "vix": D.series(frame, "vix").diff(), "hy_oas": D.series(frame, "hy_oas").diff()}
    rows = []
    for k, ins in univ.items():
        s = ins.series.dropna()
        if len(s) < 300:
            continue
        dy = (s.diff() if ins.mode == "level" else np.log(s).diff() * 100)
        est = 0.0; parts = []
        for f, fs in fac.items():
            if f not in sh or not np.isfinite(sh[f]):
                continue
            b = stats.beta_dollar_per_sigma(dy, fs, 60)["beta"]
            if not np.isfinite(b):
                continue
            if corr_one:
                b = np.sign(b) * max(abs(b), dy.iloc[-60:].std() / max(fs.iloc[-60:].std(), 1e-9) * 0.8)
            est += b * sh[f] / len([x for x in fac if x in sh])
            parts.append(f"{f}:{b * sh[f]:+.1f}")
        rows.append(dict(label=ins.label, asset_class=ins.asset_class, est_move=est, unit="bp" if ins.mode == "level" else "%", drivers=" ".join(parts[:4]),
                         C=float(df[df["key"] == k]["C"].iloc[0]) if (df["key"] == k).any() else np.nan))
    ut = pd.DataFrame(rows)
    # long positions in the common frame lose when yields rise (level) or prices fall
    ut["long_pnl_sign"] = np.where(ut["unit"] == "bp", -np.sign(ut["est_move"]), np.sign(ut["est_move"]))
    losers = ut[ut["long_pnl_sign"] < 0].sort_values("est_move", key=abs, ascending=False)
    st.dataframe(ut.sort_values(["long_pnl_sign", "est_move"]).style.format({"est_move": "{:+.1f}", "C": "{:.0f}"}), use_container_width=True, hide_index=True, height=360)
    hot = losers[losers["C"] > 65]
    st.markdown(f"**Lose together as longs:** {len(losers)} instruments · **crowded among them (C > 65):** {', '.join(hot['label'].tolist()) or 'none'}")
    if book:
        st.markdown("Book positions hit by this shock (see Sizing & stress page for $ figures): " + ", ".join(b.get("instrument", "") for b in book))
