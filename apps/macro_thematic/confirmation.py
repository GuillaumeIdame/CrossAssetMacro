"""T3 — Cross-asset confirmation map and divergence alerts (§1.5)."""

import numpy as np
import pandas as pd
import streamlit as st

from datahub import ui

from . import data as D

# narrative -> list of (label, getter name, required sign)  getter returns a % or bp move over the horizon
NARRATIVES = {
    "Demand growth": [("Equities ↑", "spx", +1), ("Copper ↑", "copper", +1), ("HY tighter", "hy_tight", +1), ("Cyclicals lead", "cyc_def", +1)],
    "Supply inflation": [("Oil ↑", "brent", +1), ("Breakevens ↑", "bei10", +1), ("Curve steepens", "s2s10", +1), ("Equities soft", "spx", -1)],
    "Liquidity expansion": [("USD ↓", "dxy", -1), ("EM ↑", "eem", +1), ("Credit tightens", "hy_tight", +1), ("High beta leads", "high_beta", +1)],
    "Policy repricing": [("2y moves", "ust2_abs", +1), ("Curve reshapes", "s2s10_abs", +1), ("USD consistent", "usd_vs_2y", +1), ("Gold consistent", "gold_vs_2y", +1)],
    "Credit stress": [("HY widens", "hy_tight", -1), ("Vol term inverts", "vix_term", +1), ("Equity–credit gap", "eq_credit_gap", +1)],
}
FALSE_POSITIVES = {
    "Demand growth": "Liquidity rally: equities alone, narrow breadth",
    "Supply inflation": "Demand inflation mislabelled",
    "Liquidity expansion": "Positioning squeeze without credit",
    "Policy repricing": "2y moves on flow, FX does not ratify",
    "Credit stress": "Idiosyncratic issuer noise",
}
ASSET_CLASS = {"spx": "equity", "copper": "commodity", "hy_tight": "credit", "cyc_def": "equity", "brent": "commodity", "bei10": "rates",
               "s2s10": "rates", "dxy": "fx", "eem": "equity", "high_beta": "equity", "ust2_abs": "rates", "s2s10_abs": "rates",
               "usd_vs_2y": "fx", "gold_vs_2y": "commodity", "vix_term": "vol", "eq_credit_gap": "credit"}


def moves(frame: pd.DataFrame, horizon: int) -> dict:
    h = horizon
    m = {}
    m["spx"] = D.pct_change(D.series(frame, "spx"), h) * 100
    m["copper"] = D.pct_change(D.series(frame, "copper"), h) * 100
    m["brent"] = D.pct_change(D.series(frame, "brent"), h) * 100
    m["eem"] = D.pct_change(D.series(frame, "eem"), h) * 100
    m["dxy"] = D.pct_change(D.series(frame, "dxy"), h) * 100
    m["gold"] = D.pct_change(D.series(frame, "gold"), h) * 100
    m["cyc_def"] = D.pct_change(D.ratio(frame, "xli", "xlp"), h) * 100
    m["high_beta"] = D.pct_change(D.ratio(frame, "iwm", "spy"), h) * 100
    hy = D.series(frame, "hy_oas")
    m["hy_tight"] = -D.diff(hy, h) if len(hy) else D.pct_change(D.ratio(frame, "hyg", "lqd"), h) * 100
    m["bei10"] = D.diff(D.series(frame, "bei10"), h) * 100
    s2s10 = (D.series(frame, "ust10") - D.series(frame, "ust2")).dropna()
    m["s2s10"] = D.diff(s2s10, h) * 100
    m["ust2"] = D.diff(D.series(frame, "ust2"), h) * 100
    m["ust2_abs"] = abs(m["ust2"]) - 15  # material if > 15 bp
    m["s2s10_abs"] = abs(m["s2s10"]) - 10
    m["usd_vs_2y"] = np.sign(m["ust2"]) * m["dxy"] if np.isfinite(m["ust2"]) else np.nan  # USD up with 2y up = consistent
    m["gold_vs_2y"] = -np.sign(m["ust2"]) * m["gold"] if np.isfinite(m["ust2"]) else np.nan
    vt = (D.series(frame, "vix") / D.series(frame, "vix3m")).dropna()
    m["vix_term"] = (float(vt.iloc[-1]) - 1.0) * 100 if len(vt) else np.nan  # >0 inverted
    m["eq_credit_gap"] = (m["spx"] + (D.diff(hy, h) if len(hy) else 0) / 10) if np.isfinite(m["spx"]) else np.nan  # equities up while HY wider
    m["real10"] = D.diff(D.series(frame, "real10"), h) * 100
    m["vix"] = D.diff(D.series(frame, "vix"), h)
    return m


def confirmation_table(frame: pd.DataFrame, horizon: int = 20) -> pd.DataFrame:
    m = moves(frame, horizon)
    rows = []
    for narrative, reqs in NARRATIVES.items():
        checks, classes = [], set()
        for label, key, sign in reqs:
            v = m.get(key, np.nan)
            ok = bool(np.isfinite(v) and np.sign(v) == sign and abs(v) > 1e-9)
            checks.append((label, v, ok))
            if ok:
                classes.add(ASSET_CLASS.get(key, "other"))
        n_ok = sum(c[2] for c in checks)
        rows.append(dict(narrative=narrative, confirmed=f"{n_ok}/{len(checks)}", n_ok=n_ok, n=len(checks),
                         breadth_classes=len(classes), detail=" · ".join(f"{l} {'✓' if ok else '✗'} ({v:+.1f})" if np.isfinite(v) else f"{l} n/a" for l, v, ok in checks),
                         false_positive=FALSE_POSITIVES[narrative]))
    return pd.DataFrame(rows)


def divergences(frame: pd.DataFrame, horizon: int = 20) -> pd.DataFrame:
    m = moves(frame, horizon)
    hy_wider = -m["hy_tight"]
    policy_dovish = m["ust2"] < -10
    nf = D.diff(D.series(frame, "nfci"), 4)
    rows = [
        ("Equity ↑ / credit ↓", m["spx"] > 1 and hy_wider > 10, f"SPX {m['spx']:+.1f}%, HY OAS {hy_wider:+.0f} bp"),
        ("USD ↑ / EM ↑", m["dxy"] > 1 and m["eem"] > 1, f"DXY {m['dxy']:+.1f}%, EEM {m['eem']:+.1f}%"),
        ("Oil ↑ / copper ↓", m["brent"] > 3 and m["copper"] < -2, f"Brent {m['brent']:+.1f}%, copper {m['copper']:+.1f}%"),
        ("Dovish pricing / tighter conditions", policy_dovish and np.isfinite(nf) and nf > 0.05, f"2Y {m['ust2']:+.0f} bp, NFCI 4w Δ {nf:+.2f}" if np.isfinite(nf) else "NFCI n/a"),
        ("Gold ↑ / real yields ↑", m["gold"] > 2 and m["real10"] > 10, f"Gold {m['gold']:+.1f}%, 10Y real {m['real10']:+.0f} bp"),
    ]
    return pd.DataFrame([dict(divergence=a, active=bool(b) if not (isinstance(b, float) and np.isnan(b)) else False, evidence=c) for a, b, c in rows])


@st.cache_resource(ttl=3600, show_spinner=False)
def engine_divergences():
    """Root regime engine (separate tool) — optional, cached, never fatal."""
    try:
        import sys
        if str(D.ROOT) not in sys.path:
            sys.path.insert(0, str(D.ROOT))
        from regime_engine import RegimeEngine  # noqa
        res = RegimeEngine().run()
        return [dict(severity=d.severity, title=d.title, detail=d.detail) for d in res.divergences], res.regime.headline() if hasattr(res.regime, "headline") else str(res.regime.cell)
    except Exception as error:
        return None, f"{type(error).__name__}: {str(error)[:120]}"


def render():
    ui.step("T3", "Cross-asset confirmation & divergence (§1.5)",
            "Is the narrative ratified across independent asset classes, and which contradictions need a written resolution?")
    frame, _, _ = D.load_universe()
    horizon = st.radio("Horizon", [20, 60], horizontal=True, format_func=lambda d: f"{d}D")
    tab = confirmation_table(frame, horizon)
    st.markdown("#### Narrative confirmations " + ui.badge("live"), unsafe_allow_html=True)
    st.dataframe(tab[["narrative", "confirmed", "breadth_classes", "detail", "false_positive"]].rename(columns={
        "narrative": "Narrative", "confirmed": "Confirmed", "breadth_classes": "Asset classes (B)", "detail": "Evidence", "false_positive": "Typical false positive"}),
        use_container_width=True, hide_index=True)

    st.markdown("#### Divergence alerts — investigate, don't fade")
    dv = divergences(frame, horizon)
    notes = st.session_state.setdefault("divergence_notes", {})
    for _, r in dv.iterrows():
        c1, c2, c3 = st.columns([2, 3, 4])
        c1.markdown(("🔴 **" if r["active"] else "⚪ ") + r["divergence"] + ("**" if r["active"] else ""))
        c2.caption(r["evidence"])
        notes[r["divergence"]] = c3.text_input("One-line written resolution", value=notes.get(r["divergence"], ""), key=f"dvn_{r['divergence']}", label_visibility="collapsed",
                                               placeholder="one-line resolution (required when active)")
    st.session_state["divergence_notes"] = notes
    unresolved = [r["divergence"] for _, r in dv.iterrows() if r["active"] and not notes.get(r["divergence"])]
    if unresolved:
        st.warning("Unresolved active divergences: " + ", ".join(unresolved))

    with st.expander("Cross-Asset Regime Engine (root tool) — its divergence log", expanded=False):
        if st.button("Run the root regime engine (slow, cached 1h)"):
            st.session_state["run_root_engine"] = True
        if st.session_state.get("run_root_engine"):
            items, headline = engine_divergences()
            if items is None:
                st.info(f"Root engine unavailable: {headline}")
            else:
                st.markdown(f"**Root engine regime:** {headline}")
                st.dataframe(pd.DataFrame(items), use_container_width=True, hide_index=True)
