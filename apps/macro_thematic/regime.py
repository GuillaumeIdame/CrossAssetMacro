"""T1/T2 — Regime engine, transition state machine, credibility overlay (§1.3)."""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from datahub import ui

from . import data as D

QUADRANTS = {
    ("up", "up"): ("Reflation", "Short duration, long cyclicals, steepener bias."),
    ("up", "down"): ("Goldilocks", "Long risk, carry-friendly, short vol."),
    ("down", "up"): ("Stagflation", "Long real assets, short duration and risk, long vol."),
    ("down", "down"): ("Deflation / slowdown", "Long duration, long quality."),
}
# which direction of each state variable confirms each quadrant (sign of z expected)
CONFIRMS = {
    "Reflation": dict(Growth=+1, Inflation=+1, Policy=+1, Liquidity=0, Credit=+1, Volatility=-1),
    "Goldilocks": dict(Growth=+1, Inflation=-1, Policy=-1, Liquidity=+1, Credit=+1, Volatility=-1),
    "Stagflation": dict(Growth=-1, Inflation=+1, Policy=+1, Liquidity=-1, Credit=-1, Volatility=+1),
    "Deflation / slowdown": dict(Growth=-1, Inflation=-1, Policy=-1, Liquidity=0, Credit=-1, Volatility=+1),
}
WEIGHTS = dict(Growth=1.0, Inflation=1.0, Policy=0.8, Liquidity=0.6, Credit=0.8, Volatility=0.6)


def _annualised_3m(idx: pd.Series) -> pd.Series:
    """3m annualised momentum of a monthly index vs 12m trend (pp)."""
    m = idx.dropna()
    m3 = (m / m.shift(3)) ** 4 - 1
    m12 = m / m.shift(12) - 1
    return (m3 - m12) * 100


def state_variables(frame: pd.DataFrame):
    """Return (table, history) where history is a DataFrame of daily z-scores per variable."""
    rows, hist = [], {}

    # Growth — ISM not on FRED: INDPRO 3m momentum + GDPNow + UMich, labelled proxy
    ip = D.prints("indpro"); gd = D.prints("gdpnow"); um = D.prints("umcsent")
    idx = frame.index
    g_parts = []
    if len(ip) > 36:
        g_parts.append(D.z3y((((ip / ip.shift(3)) ** 4 - 1) * 100).reindex(idx, method="ffill")))
    if len(gd) > 36:
        g_parts.append(D.z3y(gd.reindex(idx, method="ffill")))
    if len(um) > 36:
        g_parts.append(D.z3y(um.reindex(idx, method="ffill")))
    g = pd.concat(g_parts, axis=1).mean(axis=1) if g_parts else pd.Series(dtype=float)
    conf_g = D.ratio(frame, "xli", "xlp")
    rows.append(_row("Growth", g, "INDPRO 3m ann. + GDPNow + UMich (ISM proxy)", "proxy",
                     D.pct_change(conf_g, 60) * 100, "Cyclicals/defensives 60D %", +1))
    hist["Growth"] = g

    # Inflation — core CPI 3m annualised vs 12m
    cc = D.prints("core_cpi")
    infl = D.z3y(_annualised_3m(cc).reindex(frame.index, method="ffill")) if len(cc) > 36 else pd.Series(dtype=float)
    rows.append(_row("Inflation", infl, "Core CPI 3m ann. − 12m (pp)", "live", D.diff(D.series(frame, "fwd5y5y"), 20) * 100, "5y5y fwd BE 20D Δ bp", +1))
    hist["Inflation"] = infl

    # Policy — 1y-forward priced path minus spot (from the ZQ strip) with DGS2 − EFFR as the history proxy
    pol_hist = (D.series(frame, "ust1") - D.series(frame, "effr")).dropna()
    pol = D.z3y(pol_hist)
    pp = D.load_policy_path()
    pol_note = "1Y UST − EFFR (history); strip 12m cum. priced: "
    if pp and "cum_12m_bp" in pp and np.isfinite(pp["cum_12m_bp"]):
        pol_note += f"{pp['cum_12m_bp']:+.0f} bp ({pp['source']})"
    else:
        pol_note += "n/a"
    rows.append(_row("Policy", pol, pol_note, "live" if pp and "cum_12m_bp" in pp else "proxy", D.diff(D.series(frame, "ust2"), 20) * 100, "2Y 20D Δ bp", +1))
    hist["Policy"] = pol

    # Liquidity — Fed net liquidity 4w change
    w, t, r = D.series(frame, "walcl"), D.series(frame, "tga"), D.series(frame, "rrp")
    if len(w) and len(t) and len(r):
        nl = (w - t - r.reindex(w.index, method="ffill").fillna(0) * 1000).dropna()  # RRP in $bn → $mn
        nl4 = nl.diff(20).dropna()
        liq = D.z3y(nl4)
        liq_val = float(nl4.iloc[-1]) / 1000 if len(nl4) else np.nan
    else:
        liq, liq_val = pd.Series(dtype=float), np.nan
    rows.append(_row("Liquidity", liq, f"WALCL − TGA − RRP, 4w Δ = {liq_val:+.0f} $bn" if np.isfinite(liq_val) else "net liquidity n/a", "live",
                     -D.diff(D.series(frame, "nfci"), 5), "NFCI weekly Δ (sign flipped)", +1))
    hist["Liquidity"] = liq

    # Credit & risk — HY OAS percentile + 20D Δ (z sign flipped: tight spreads = healthy = +)
    hy = D.series(frame, "hy_oas")
    cred = -D.z3y(hy) if len(hy) > 300 else pd.Series(dtype=float)
    rows.append(_row("Credit & Risk", cred, f"HY OAS {D.last(frame,'hy_oas')*100:.0f} bp, pct {D.pct_rank(hy):.0f}, 20D Δ {D.diff(hy,20)*100:+.0f} bp" if len(hy) else "HY OAS n/a",
                     "live", D.pct_change(D.ratio(frame, "hyg", "lqd"), 20) * 100, "HYG/LQD 20D %", +1))
    hist["Credit"] = cred

    # Volatility — VIX & MOVE percentile + term slope
    vix, move, v3 = D.series(frame, "vix"), D.series(frame, "move"), D.series(frame, "vix3m")
    v_parts = [D.z3y(vix)] + ([D.z3y(move)] if len(move) > 300 else [])
    vol = pd.concat(v_parts, axis=1).mean(axis=1)
    slope = (vix / v3).dropna()
    rv = (np.log(D.series(frame, "spx")).diff().rolling(20).std() * np.sqrt(252) * 100).dropna()
    iv_rv = float(vix.iloc[-1] - rv.iloc[-1]) if len(rv) and len(vix) else np.nan
    rows.append(_row("Volatility", vol, f"VIX pct {D.pct_rank(vix):.0f}, MOVE pct {D.pct_rank(move) if len(move) else float('nan'):.0f}, VIX/VIX3M {slope.iloc[-1] if len(slope) else float('nan'):.2f}",
                     "live", iv_rv, "VIX − realised 20D (pts)", +1))
    hist["Volatility"] = vol

    table = pd.DataFrame(rows)
    history = pd.DataFrame(hist).dropna(how="all")
    return table, history


def _row(name, z_series, primary_desc, quality, conf_val, conf_desc, sign):
    z = z_series.dropna()
    z_now = float(z.iloc[-1]) if len(z) else np.nan
    z_20 = float(z.iloc[-21]) if len(z) > 21 else np.nan
    return dict(variable=name, z=z_now, m=(z_now - z_20) if np.isfinite(z_20) else np.nan, primary=primary_desc,
                quality=quality, confirmation=conf_val, confirmation_desc=conf_desc)


def classify(table: pd.DataFrame, history: pd.DataFrame):
    g = table.set_index("variable")
    gz, iz = g.loc["Growth", "z"], g.loc["Inflation", "z"]
    quad, playbook = QUADRANTS[("up" if gz >= 0 else "down", "up" if iz >= 0 else "down")]
    # regime confidence
    num = den = 0.0
    for var, w in WEIGHTS.items():
        key = "Credit & Risk" if var == "Credit" else var
        if key not in g.index or not np.isfinite(g.loc[key, "z"]):
            continue
        want = CONFIRMS[quad][var]
        den += w
        if want == 0 or np.sign(g.loc[key, "z"]) == want:
            num += w
    rc = num / den if den else np.nan
    # history of quadrant labels
    lab = pd.Series(index=history.index, dtype=object)
    if {"Growth", "Inflation"} <= set(history.columns):
        hh = history[["Growth", "Inflation"]].dropna()
        lab = pd.Series([QUADRANTS[("up" if a >= 0 else "down", "up" if b >= 0 else "down")][0] for a, b in hh.values], index=hh.index)
    # transition machine
    days_in = 0
    if len(lab):
        cur = lab.iloc[-1]
        for v in lab.values[::-1]:
            if v == cur:
                days_in += 1
            else:
                break
    against = 0
    for var in ("Growth", "Inflation", "Policy", "Credit", "Volatility"):
        key = "Credit & Risk" if var == "Credit" else var
        if key in g.index and np.isfinite(g.loc[key, "m"]):
            want = CONFIRMS[quad][var]
            if want != 0 and abs(g.loc[key, "m"]) > 0.5 and np.sign(g.loc[key, "m"]) == -want:
                against += 1
    if days_in >= 20 and rc >= 0.6:
        state = "Stable"; behaviour = "Full thematic risk; carry and mean reversion allowed"
    elif days_in < 20 and rc >= 0.5:
        state = "Confirmed transition" if days_in > 1 else "Confirmed transition"
        behaviour = "Rotate expressions; prefer convexity while RC < 0.7"
    elif against >= 2:
        state = "Early transition"; behaviour = "No new old-regime positions; open the competing-narrative file"
    elif days_in >= 20:
        state = "Stable (low RC)"; behaviour = "Quadrant held but confirmation weak: cap thematic gross at 60%, marginal expression in options"
    else:
        state = "New regime (RC < 0.5)"; behaviour = "Held < 20d; back to Stable rules once RC ≥ 0.6 for 20d"
    return dict(quadrant=quad, playbook=playbook, rc=rc, days_in=days_in, against=against, state=state, behaviour=behaviour, labels=lab)


def credibility(frame: pd.DataFrame) -> dict:
    """Rolling 2y beta of 5y5y breakevens to CPI surprises proxy (monthly CPI change vs its 12m mean),
    plus the ACM term-premium trend. Positive, rising beta + rising TP + long yields up = fiscal-dominance tell."""
    cpi = D.prints("cpi").pct_change() * 100
    cpi.index = cpi.index.to_period("M").to_timestamp()
    surprise = (cpi - cpi.rolling(12).mean()).dropna()
    be = D.series(frame, "fwd5y5y").resample("MS").last().diff()
    df = pd.concat([be, surprise], axis=1, keys=["dbe", "surp"]).dropna()
    beta = np.nan
    if len(df) > 30:
        w = df.iloc[-24:]
        beta = float(np.cov(w["dbe"], w["surp"])[0, 1] / w["surp"].var()) if w["surp"].var() > 0 else np.nan
    tp = D.series(frame, "tp10")
    tp_tr = D.diff(tp, 60) * 100 if len(tp) else np.nan
    y30 = D.diff(D.series(frame, "ust30"), 60) * 100
    dxy = D.pct_change(D.series(frame, "dxy"), 60) * 100
    fiscal = bool(np.isfinite(tp_tr) and tp_tr > 15 and np.isfinite(y30) and y30 > 0 and np.isfinite(dxy) and dxy < 0)
    return dict(beta=beta, tp_trend_bp=tp_tr, y30_60d_bp=y30, dxy_60d=dxy, switch="fiscal-dominance tell" if fiscal else "credible targeting")


def render():
    ui.step("T1 · T2", "Regime engine & transition state (§1.3)",
            "Which quadrant are we in, how confident is the read, and is the regime stable or in transition?")
    frame, observed, status = D.load_universe()
    table, history = state_variables(frame)
    cls = classify(table, history)

    ui.kpi_row([("Quadrant", cls["quadrant"], None, cls["playbook"]),
                ("Regime confidence RC", f"{cls['rc']:.2f}" if np.isfinite(cls["rc"]) else "n/a", None, "Σ w·1[confirms] / Σ w"),
                ("Days in quadrant", str(cls["days_in"]), None, None),
                ("Transition state", cls["state"], None, cls["behaviour"]),
                ("Variables moving against", str(cls["against"]), None, "|m| > 0.5 against the quadrant")])
    st.markdown(f"**Playbook:** {cls['playbook']}  \n**Desk behaviour:** {cls['behaviour']}")

    st.markdown("#### Six state variables — z on 3y (winsorised ±3), m = z − z(−20d)")
    show = table.copy()
    show["quality"] = show["quality"].map(lambda q: q)
    show = show.rename(columns={"variable": "State variable", "z": "z", "m": "m (20d)", "primary": "Primary indicator",
                                "confirmation": "Confirmation value", "confirmation_desc": "Market confirmation"})
    st.dataframe(show.style.format({"z": "{:+.2f}", "m (20d)": "{:+.2f}", "Confirmation value": "{:+.2f}"}), use_container_width=True, hide_index=True)
    st.markdown(" ".join(f"{r['variable']}: {ui.badge(r['quality'])}" for _, r in table.iterrows()), unsafe_allow_html=True)
    ui.note("Growth uses INDPRO momentum + GDPNow + UMich because ISM is not on FRED (proxy). Policy history is 1Y − EFFR; the live 12m priced path comes from the fed-funds strip (Central Bank app).")

    # strip chart of z history
    if not history.empty:
        fig = go.Figure()
        colours = [D.NAVY, D.BRONZE, "#5B7DB1", "#8FA0B2", "#B26A00", "#55677C"]
        for (name, s), c in zip(history.items(), colours):
            fig.add_trace(go.Scatter(x=s.index[-504:], y=s.values[-504:], name=name, line=dict(color=c, width=1.6)))
        fig.add_hline(y=0, line=dict(color="#999", width=1))
        fig.update_layout(height=320, margin=dict(l=10, r=10, t=30, b=10), title="State variables, 2y (z)", legend=dict(orientation="h"))
        st.plotly_chart(fig, use_container_width=True)
        # ribbon
        lab = cls["labels"]
        if len(lab):
            lab = lab.iloc[-504:]
            cmap = {"Reflation": "#B26A00", "Goldilocks": "#2E7D32", "Stagflation": "#B71C1C", "Deflation / slowdown": "#1F3550"}
            fig2 = go.Figure()
            for q, c in cmap.items():
                m = (lab == q).astype(int)
                fig2.add_trace(go.Bar(x=lab.index, y=m, name=q, marker_color=c, width=1.0 * 86400000))
            fig2.update_layout(barmode="stack", height=120, margin=dict(l=10, r=10, t=30, b=10), title="2y regime ribbon", yaxis=dict(visible=False), legend=dict(orientation="h"))
            st.plotly_chart(fig2, use_container_width=True)

    st.markdown("#### Transition state machine")
    st.dataframe(pd.DataFrame([
        ["Stable", "Quadrant unchanged 20d+, RC ≥ 0.6", "Full thematic risk; carry and mean reversion allowed"],
        ["Early transition", "|m| > 0.5 on ≥ 2 variables against quadrant", "No new old-regime positions; open the competing-narrative file"],
        ["Confirmed transition", "Sign flip + ≥ 2 confirmations + RC(new) ≥ 0.5", "Rotate expressions; prefer convexity while RC < 0.7"],
        ["New regime", "Held 20d, RC ≥ 0.6", "Back to Stable rules"]], columns=["State", "Entry condition", "Desk behaviour"]),
        use_container_width=True, hide_index=True)

    st.markdown("#### Credibility overlay")
    cr = credibility(frame)
    ui.kpi_row([("β(5y5y BE → CPI surprise), 2y", D.sign_fmt(cr["beta"], 2), None, "Monthly, proxy surprise = CPI m/m − 12m mean"),
                ("ACM 10Y term premium 60D", D.sign_fmt(cr["tp_trend_bp"], 0, " bp"), None, None),
                ("30Y 60D", D.sign_fmt(cr["y30_60d_bp"], 0, " bp"), None, None),
                ("DXY 60D", D.sign_fmt(cr["dxy_60d"], 1, " %"), None, None),
                ("Switch", cr["switch"], None, "Currency down + long end up + TP up = fiscal dominance")])
    st.markdown(ui.badge("proxy") + " A hot CPI is a bear flattener under credible targeting and a bear steepener under fiscal dominance. Decompose the long end (ACM) before reading it as macro.", unsafe_allow_html=True)

    st.markdown("#### G10 gauges & curve routing (summary)")
    st.dataframe(pd.DataFrame([
        ["Overheating — spot hot, forward hot", "Front and belly bear-flatten; policy-path trade", "Cash–2y, 2s5s"],
        ["Late cycle — spot hot, forward cool", "Peak rates, hump in 2s5s10s; supply shock → 5s30s/10s30s", "2s5s10s fly, 5s30s"],
        ["Early reacceleration — spot cool, forward hot", "Belly leads; 2s5s bear-steepener", "2s5s"],
        ["Slowdown — spot cool, forward cool", "Bull-steepener then bull-flatten; front rallies first", "Cash–2y, 2s10s"]],
        columns=["Cell", "Curve reaction", "Segment"]), use_container_width=True, hide_index=True)
    ui.note("Full 3×2 gauge grid, reaction functions and meeting-dated pricing live in the G3 Central Bank app (apps/g3_central_bank). Path trade ∝ (reaction-function path − priced path) × positioning offside; term-premium trade in 5s30s/10s30s is independent of the path.")
