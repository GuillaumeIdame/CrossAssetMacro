"""Page 4 — Three distributions per print (§1.4) and event vol (§4.2 Event Vol, §2.4 leg choice)."""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from datahub import stir, ui

from . import common as C

DEFAULTS = {
    "Nonfarm payrolls": dict(unit="k", cons=150.0, std=60.0, n=70, lo=50.0, hi=250.0, sf=150.0, prev=150.0, beta=4.0),
    "CPI": dict(unit="% m/m core", cons=0.30, std=0.08, n=70, lo=0.1, hi=0.5, sf=0.30, prev=0.30, beta=6.0),
    "Core PCE": dict(unit="% m/m", cons=0.25, std=0.06, n=50, lo=0.1, hi=0.4, sf=0.25, prev=0.25, beta=3.0),
    "HICP flash": dict(unit="% y/y core", cons=2.3, std=0.1, n=40, lo=2.0, hi=2.6, sf=2.3, prev=2.3, beta=4.0),
    "PMI flash": dict(unit="idx composite", cons=50.0, std=0.8, n=30, lo=48.0, hi=52.0, sf=50.0, prev=50.0, beta=2.0),
    "Labour market": dict(unit="% AWE regular 3m y/y", cons=4.5, std=0.15, n=25, lo=4.1, hi=4.9, sf=4.5, prev=4.5, beta=4.0),
}


def _defaults(event: str) -> dict:
    for k, v in DEFAULTS.items():
        if k.lower() in event.lower():
            return dict(v)
    return dict(unit="", cons=0.0, std=1.0, n=30, lo=-2.0, hi=2.0, sf=0.0, prev=0.0, beta=3.0)


def render():
    ui.step("1.4", "Three distributions per print — consensus, Smart Forecasters, priced",
            "Where is the skew between what the median economist expects, what the track-record-weighted lean says, and what the market will be surprised by?")
    cal = C.cal()
    today = pd.Timestamp.today().normalize()
    rel = cal[(cal["type"] == "release") & (cal["date"] >= today) & (cal["tier"] == 1)].head(25)
    if rel.empty:
        st.warning("No upcoming tier-1 releases in the calendar file."); return
    labels = [f"{r['date'].date()} · {r['region']} · {r['event']}" for _, r in rel.iterrows()]
    pick = st.selectbox("Release", labels, key="dist_event")
    row = rel.iloc[labels.index(pick)]
    store = C.ss_get("distributions", {})
    d = store.get(pick) or _defaults(row["event"])
    st.markdown(ui.badge(row["status"]) + f" {row['event']} — {row['region']} — {int((row['date'] - today).days)} days; " +
                ui.badge("manual") + " survey and lean inputs are typed by the desk (no public Bloomberg/Reuters survey feed).", unsafe_allow_html=True)

    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown("**Consensus** — survey")
        d["unit"] = st.text_input("Unit", d["unit"])
        d["cons"] = st.number_input("Mean", value=float(d["cons"]), format="%.3f")
        d["std"] = st.number_input("Std of surprises (historical)", value=float(d["std"]), min_value=1e-6, format="%.3f")
        d["n"] = st.number_input("N forecasters", value=int(d["n"]), min_value=1)
        d["lo"] = st.number_input("Min forecast", value=float(d["lo"]), format="%.3f")
        d["hi"] = st.number_input("Max forecast", value=float(d["hi"]), format="%.3f")
        d["prev"] = st.number_input("Previous print", value=float(d["prev"]), format="%.3f")
    with c2:
        st.markdown("**Smart Forecasters** — internal lean")
        d["sf"] = st.number_input("Track-record-weighted expected print (incl. nowcasts)", value=float(d["sf"]), format="%.3f")
        d["sf_std_mult"] = st.slider("Internal width vs consensus std", 0.5, 2.0, float(d.get("sf_std_mult", 1.0)), 0.05)
        d["skew_int"] = st.slider("Internal skew (−1 downside tail … +1 upside tail)", -1.0, 1.0, float(d.get("skew_int", 0.0)), 0.1)
    with c3:
        st.markdown("**Priced** — options / futures")
        d["beta"] = st.number_input("Contract beta: bp move in the front contract per 1σ surprise", value=float(d["beta"]), format="%.2f")
        mode = st.radio("Implied event move from", ["straddle breakeven (bp)", "IV with / without event"], horizontal=True,
                        index=0 if d.get("mode", "s") == "s" else 1)
        d["mode"] = "s" if mode.startswith("straddle") else "iv"
        if d["mode"] == "s":
            d["be"] = st.number_input("Event straddle breakeven on the front contract (bp)", value=float(d.get("be", round(d["beta"] * np.sqrt(2 / np.pi), 1))), format="%.1f")
            implied_bp = d["be"]
        else:
            iv_w = st.number_input("IV expiry after event (bp/yr, normal)", value=float(d.get("iv_w", 90.0)))
            t_w = st.number_input("days to that expiry", value=int(d.get("t_w", 10)), min_value=1)
            iv_wo = st.number_input("IV expiry before event (bp/yr)", value=float(d.get("iv_wo", 60.0)))
            t_wo = st.number_input("days to that expiry ", value=int(d.get("t_wo", 5)), min_value=1)
            d.update(iv_w=iv_w, t_w=t_w, iv_wo=iv_wo, t_wo=t_wo)
            implied_bp = stir.implied_event_move(iv_w, t_w, iv_wo, t_wo)
            st.caption(f"implied event move = √(IV²τ with − IV²τ without) = {implied_bp:.1f} bp")
        d["priced_center"] = st.number_input("Print the market is positioned for (default = consensus)", value=float(d.get("priced_center", d["cons"])), format="%.3f")
    store[pick] = d
    st.session_state["distributions"] = store

    # --- outputs --------------------------------------------------------------
    exp_surprise = d["sf"] - d["cons"]
    surprise_z = exp_surprise / d["std"]
    internal_move_bp = abs(surprise_z) * d["beta"]
    width_int_bp = d["std"] * d["sf_std_mult"] / d["std"] * d["beta"] * np.sqrt(2 / np.pi)  # expected |move| under the internal width (normal)
    width_mkt_bp = implied_bp
    st.markdown("---")
    ui.kpi_row([("Expected surprise", f"{exp_surprise:+.3f} {d['unit']}"), ("Expected surprise ÷ std", f"{surprise_z:+.2f} σ"),
                ("Internal expected move (mean)", f"{internal_move_bp:.1f} bp", None, "|surprise/std| × beta"),
                ("Priced event move", f"{implied_bp:.1f} bp"), ("Internal E|move| (width)", f"{width_int_bp:.1f} bp", None, "normal: std × beta × √(2/π)"),
                ("Dispersion (max−min)/std", f"{(d['hi'] - d['lo']) / d['std']:.1f} σ")])

    # scenario grid
    st.subheader("Scenario grid — written before the number")
    grid = [("Large downside", -2.0), ("Moderate downside", -1.0), ("In line", 0.0), ("Moderate upside", 1.0), ("Large upside", 2.0)]
    std_int = d["std"] * d["sf_std_mult"]
    from datahub import kelly
    outcomes = [d["cons"] + k * d["std"] for _, k in grid]
    # internal probabilities: normal around SF with internal std, tilted by skew
    p_int = kelly.discretise_normal(d["sf"], std_int, outcomes)
    tilt = np.array([1 - 0.5 * d["skew_int"], 1 - 0.25 * d["skew_int"], 1.0, 1 + 0.25 * d["skew_int"], 1 + 0.5 * d["skew_int"]])
    p_int = kelly.normalise(p_int * tilt)
    p_mkt = kelly.discretise_normal(d["priced_center"], d["std"], outcomes)
    moves = [(o - d["priced_center"]) / d["std"] * d["beta"] for o in outcomes]
    sg = pd.DataFrame({"scenario": [g[0] for g in grid], "print": np.round(outcomes, 3), "surprise_sigma": [g[1] for g in grid],
                       "p_internal": np.round(p_int, 3), "p_market": np.round(p_mkt, 3), "front_contract_move_bp": np.round(moves, 1)})
    sg["edge (p_int − p_mkt)"] = (sg["p_internal"] - sg["p_market"]).round(3)
    st.dataframe(sg, hide_index=True, width="stretch")
    st.caption("Market probabilities: normal centred on the priced print with the survey std; internal: normal centred on the Smart-Forecaster lean with the internal width, tilted by the skew slider. In-line data into an offside market moves the curve more than a surprise into a balanced one — positioning travels with the print.")

    fig = go.Figure()
    fig.add_trace(go.Bar(x=sg["scenario"], y=sg["p_market"], name="priced (market)", marker_color=C.SLATE))
    fig.add_trace(go.Bar(x=sg["scenario"], y=sg["p_internal"], name="internal (Smart Forecasters)", marker_color=C.BRONZE))
    st.plotly_chart(C.plotly_layout(fig, height=300), width="stretch")

    # leg suggestion
    st.subheader("Leg suggestion — mean vs shape (§2.4)")
    mean_mis = abs(surprise_z) >= 0.5
    ratio = width_int_bp / width_mkt_bp if width_mkt_bp > 0 else np.nan
    shape_mis = (np.isfinite(ratio) and abs(ratio - 1) > 0.2) or abs(d["skew_int"]) >= 0.4
    if mean_mis and not shape_mis:
        verdict = "Mean mispriced, shape roughly agrees → **delta-one** (futures / meeting swap). Bank the gap linearly; don't pay for convexity the view doesn't need."
    elif shape_mis and not mean_mis:
        direction = "buy" if (np.isfinite(ratio) and ratio > 1) else "sell"
        verdict = f"Shape mispriced, mean agrees → **STIR options**: {direction} the straddle/strangle; skew via wings if the tail tilt is the edge."
    elif mean_mis and shape_mis:
        verdict = "Mean and shape both mispriced → **risk reversal / skewed strangle**, sized off the full tree (Distribution tree page)."
    else:
        verdict = "No material edge on mean or shape → stand aside, or carry only the risk-premia sleeve if wings are rich (§2.3)."
    st.markdown(verdict)
    st.markdown(f"Indicators: |expected surprise/std| = {abs(surprise_z):.2f}σ (threshold 0.5); internal width / priced move = {C.fmt(ratio, 2)} (threshold ±20%); "
                f"internal skew {d['skew_int']:+.1f}. Positioning caution: if CFTC/CTA already sit on the side of the mean view, prefer the defined-loss options leg over sizing up delta-one.")
    C.download_state(["distributions"], "Download distribution inputs (JSON)", "g3_distributions.json")
    C.upload_state("Upload distribution inputs (JSON)", key="upload_dist")
