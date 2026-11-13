"""§2.1–2.3 — Delta-one vs the three vol alphas; the leg-choice matrix."""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from datahub import ui

from . import data as D
from . import themes as T

# theme asset -> (price key, implied-vol key or None, label)
THEME_ASSETS = {
    "S&P 500": ("spx", "vix", "VIX"), "UST 10Y (via TLT)": ("tlt", "move", "MOVE (bp, scaled)"), "Brent": ("brent", "ovx", "OVX"),
    "Gold": ("gold", "gvz", "GVZ"), "Nasdaq 100": ("ndx", "vix", "VIX (proxy)"), "EUR/USD": ("eurusd", None, "manual"),
    "USD/JPY": ("usdjpy", None, "manual"), "EM equities": ("eem", None, "manual"), "Copper": ("copper", None, "manual"), "Defence (ITA)": ("ita", None, "manual"),
}


def realised(frame, key, win):
    s = D.series(frame, key)
    return (np.log(s).diff().rolling(win).std() * np.sqrt(252) * 100).dropna()


def premium_state(frame, key, iv_key, manual_iv=None):
    rv20, rv60 = realised(frame, key, 20), realised(frame, key, 60)
    e_rv = (0.6 * rv20 + 0.4 * rv60).dropna()
    if iv_key:
        iv = D.series(frame, iv_key)
        if iv_key == "move":
            iv = iv / 100 * 7.0  # MOVE is bp/yr of yield; ≈ price vol of a 7-duration instrument in %
        q = "live"
    elif manual_iv is not None:
        iv = pd.Series(manual_iv, index=e_rv.index); q = "manual"
    else:
        return dict(quality="unavailable")
    df = pd.concat([iv, e_rv], axis=1, keys=["iv", "erv"]).dropna()
    if df.empty:
        return dict(quality="unavailable")
    vrp = df["iv"] - df["erv"]
    now = float(vrp.iloc[-1]); d20 = float(vrp.iloc[-1] - vrp.iloc[-21]) if len(vrp) > 21 else np.nan
    pct = D.pct_rank(vrp, 756) if len(vrp) > 300 else np.nan
    ivpct = D.pct_rank(df["iv"], 756) if len(df) > 300 else np.nan
    level = "rich" if (np.isfinite(pct) and pct >= 60) else "cheap" if (np.isfinite(pct) and pct <= 35) else "fair"
    direction = "rising" if (np.isfinite(d20) and d20 > 0.5) else "falling" if (np.isfinite(d20) and d20 < -0.5) else "stable"
    return dict(quality=q, iv=float(df["iv"].iloc[-1]), erv=float(df["erv"].iloc[-1]), vrp=now, vrp_d20=d20, vrp_pct=pct, iv_pct=ivpct, level=level, direction=direction, series=vrp)


def leg_choice(level, direction, tailcorr_bid, conviction, headroom):
    """Matrix of §2.3. Order: premium regime (level & direction) → conviction → loss budget."""
    if level == "rich" and direction == "rising" and tailcorr_bid:
        return "Long vol and tail-correlation", "Premium itself in an uptrend: long ATM straddles / OTM strangles on theme assets; index OTM puts vs single-name puts; scale in while premium rises, exit on vol-of-vol rollover."
    if not headroom and conviction in ("high directional", "asymmetric / tail"):
        return "Switch to options — defined max loss", "Δ1 size breaches L_stomach: the defined premium collapses the loss to a known number."
    if level == "rich" and direction in ("stable", "falling"):
        if conviction == "high directional":
            return "Delta-one — don't pay rich vol", "Bank the drift linearly; carry observable in advance; size on the 2w rule."
        return "Sell premium, delta-hedged", "Short straddles/strangles or put skew; ring-fenced, small, always tail-hedged, first to be cut."
    if level == "cheap":
        if conviction == "asymmetric / tail":
            return "Long OTM optionality on the asymmetric side", "Cheap convexity where the scenario tree is lopsided."
        if conviction == "high directional":
            return "Long gamma — calls, puts, straddles", "Cheap with a brewing move: own the move before the crowd and the vol market catch up."
        return "Long gamma (small) / wait", "Cheap vol without direction: small long-gamma or wait for the catalyst."
    if conviction == "high directional" and headroom:
        return "Delta-one", "Fair premium, high conviction, loss-budget headroom: no convexity premium paid unnecessarily."
    return "Wait / small defined-risk", "Fair premium and low conviction: no edge in either space yet."


def render():
    ui.step("§2.1–2.3", "Leg choice & the three vol alphas",
            "Is the premium itself rich or cheap, and — separately — rising or falling, across the theme's basket? Then conviction, then loss budget.")
    frame, _, _ = D.load_universe()
    T.init_state()
    st.session_state.setdefault("manual_vol", {})
    st.markdown("#### Premium state per theme asset — VRP = IV₁ₘ − E[RV], E[RV] = 0.6·RV20 + 0.4·RV60")
    rows, series_plot = [], {}
    for lab, (pk, ivk, ivlab) in THEME_ASSETS.items():
        man = st.session_state["manual_vol"].get(lab)
        ps = premium_state(frame, pk, ivk, man)
        if ps.get("quality") == "unavailable":
            rows.append(dict(asset=lab, iv_source=ivlab, quality="unavailable")); continue
        rows.append(dict(asset=lab, iv_source=ivlab, quality=ps["quality"], IV=ps["iv"], E_RV=ps["erv"], VRP=ps["vrp"], VRP_20D=ps["vrp_d20"], VRP_pct=ps["vrp_pct"], IV_pct=ps["iv_pct"],
                         level=ps["level"], direction=ps["direction"]))
        series_plot[lab] = ps["series"]
    pt = pd.DataFrame(rows)
    st.dataframe(pt.style.format({"IV": "{:.1f}", "E_RV": "{:.1f}", "VRP": "{:+.1f}", "VRP_20D": "{:+.1f}", "VRP_pct": "{:.0f}", "IV_pct": "{:.0f}"}), use_container_width=True, hide_index=True)
    st.markdown(ui.badge("live") + " VIX / MOVE / OVX / GVZ · " + ui.badge("manual") + " type a 1M IV for assets without a public vol index (below) · "
                + ui.badge("proxy") + " MOVE converted to price vol of a ~7-duration bond", unsafe_allow_html=True)
    with st.expander("Manual 1M implied vols (%) for assets without a public index"):
        for lab, (pk, ivk, _) in THEME_ASSETS.items():
            if ivk is None:
                v = st.number_input(lab, value=float(st.session_state["manual_vol"].get(lab) or 0.0), step=0.5, key=f"miv_{lab}")
                st.session_state["manual_vol"][lab] = v if v > 0 else None
    if series_plot:
        fig = go.Figure()
        for lab, s in series_plot.items():
            fig.add_trace(go.Scatter(x=s.index[-504:], y=s.values[-504:], name=lab, line=dict(width=1.4)))
        fig.add_hline(y=0, line=dict(color="#999", width=1))
        fig.update_layout(height=300, margin=dict(l=10, r=10, t=30, b=10), title="VRP, 2y (pts)", legend=dict(orientation="h"))
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("#### Tail-correlation and vol-of-vol signals")
    skew, vvix, vix, vix3m = D.series(frame, "skew"), D.series(frame, "vvix"), D.series(frame, "vix"), D.series(frame, "vix3m")
    secs = [realised(frame, k, 20) for k in ("xli", "xlp", "xly", "xle", "xlf")]
    idx_rv = realised(frame, "spx", 20)
    avg_sec = pd.concat(secs, axis=1).mean(axis=1)
    impl_corr = (idx_rv ** 2 / avg_sec ** 2).dropna()  # realised proxy of correlation (index var / avg single var)
    ratio_manual = st.number_input("Index-put 25Δ IV ÷ basket-of-puts 25Δ IV (manual; > 1 and rising = systemic tail insurance bid)", value=1.0, step=0.05)
    ui.kpi_row([("CBOE SKEW", f"{D.last(frame,'skew'):.0f}", D.sign_fmt(D.diff(skew, 20), 1, " 20D"), "live"),
                ("VVIX", f"{D.last(frame,'vvix'):.0f}", D.sign_fmt(D.diff(vvix, 20), 1, " 20D"), f"pct {D.pct_rank(vvix):.0f}"),
                ("VIX / VIX3M", f"{(vix.iloc[-1] / vix3m.iloc[-1]) if len(vix) and len(vix3m) else float('nan'):.2f}", None, "> 1 = front above back"),
                ("Realised corr proxy (SPX vs sectors)", f"{impl_corr.iloc[-1]:.2f}" if len(impl_corr) else "n/a", D.sign_fmt(D.diff(impl_corr, 20), 2, " 20D"), "proxy"),
                ("Index/basket skew ratio", f"{ratio_manual:.2f}", None, "manual")])
    tail_bid = bool((ratio_manual > 1.1) or (np.isfinite(D.pct_rank(vvix)) and D.pct_rank(vvix) > 80 and D.diff(vvix, 20) > 0))
    st.markdown(f"**Tail-correlation regime:** {'bid — rising premia, fading compounds the bleed' if tail_bid else 'not bid'}")

    st.markdown("#### Leg-choice matrix for a theme")
    names = [t["name"] for t in st.session_state["themes"]]
    sel = st.selectbox("Theme", names, key="leg_theme")
    asset = st.selectbox("Theme asset (premium read)", [r["asset"] for r in rows if r.get("quality") != "unavailable"] or list(THEME_ASSETS))
    pr = pt[pt["asset"] == asset].iloc[0] if (pt["asset"] == asset).any() and "level" in pt.columns else None
    level = pr["level"] if pr is not None and isinstance(pr.get("level"), str) else "fair"
    direction = pr["direction"] if pr is not None and isinstance(pr.get("direction"), str) else "stable"
    c1, c2, c3 = st.columns(3)
    level = c1.selectbox("Premium level", ["rich", "fair", "cheap"], index=["rich", "fair", "cheap"].index(level))
    direction = c2.selectbox("Premium direction", ["rising", "stable", "falling"], index=["rising", "stable", "falling"].index(direction))
    conviction = c3.selectbox("Conviction", ["high directional", "asymmetric / tail", "low or mixed"])
    headroom = st.checkbox("Loss-budget headroom (Δ1 size at conviction fits L_stomach)", value=True)
    leg, why = leg_choice(level, direction, tail_bid, conviction, headroom)
    st.success(f"**Leg: {leg}** — {why}")
    st.dataframe(pd.DataFrame([
        ["Rich and stable/falling", "Low or mixed", "Any", "Sell premium, delta-hedged"], ["Rich and stable/falling", "High directional", "Headroom", "Delta-one — don't pay rich vol"],
        ["Cheap with a brewing move", "High directional", "Any", "Long gamma — calls, puts, straddles"], ["Cheap with a brewing move", "Asymmetric / tail", "Any", "Long OTM optionality on the asymmetric side"],
        ["Rich and rising, tail-corr bid", "Any", "Any", "Long vol and tail-correlation"], ["Any", "High", "Δ1 size breaches L_stomach", "Switch to options — defined max loss"]],
        columns=["Premium state", "Conviction", "Loss budget", "Leg"]), use_container_width=True, hide_index=True)

    st.markdown("#### Event-driven block — implied event move vs scenario mean")
    t = next(x for x in st.session_state["themes"] if x["name"] == sel)
    e1, e2 = st.columns(2)
    be = e1.number_input("Implied event move B_e (ATM straddle premium, same unit as the theme's outcomes)", value=15.0, step=1.0)
    rr = e2.number_input("25Δ risk reversal (IV call − IV put, vol pts)", value=0.0, step=0.1)
    sc = t.get("scenarios", [])
    if sc:
        from datahub import kelly
        mom = kelly.moments([s["prob"] for s in sc], [s["outcome"] for s in sc])
        edge = abs(mom["mean"]) - be
        ui.kpi_row([("|E[Δ]| scenario", f"{abs(mom['mean']):.1f} {t.get('unit','')}"), ("B_e implied", f"{be:.1f}"), ("edge_Δ1 = |E[Δ]| − B_e", f"{edge:+.1f}"),
                    ("Skew: RR vs scenario skew", f"RR {rr:+.1f} / skew {mom['skew']:+.2f}")])
        if edge > 0 and level != "cheap":
            st.info("Implied < expected and vol not cheap → delta-one wins: no convexity premium, drift banked linearly, sized to the worst 2-week move (optional small option hedge).")
        elif edge > 0 and level == "cheap":
            st.info("Implied < expected and vol cheap → own the move with long gamma, switch to delta-one once engaged.")
        else:
            st.info("Implied ≥ expected: the market already pays for the move; only a shape (skew/tails) view or a premium-selling sleeve has edge.")
    with st.expander("Worked reads from the process"):
        st.markdown("""* **Disinflation into FOMC** — 2y vol cheap (VRP 0.5 pts), straddle ±18 bp, internal view 25–30 bp dovish surprise. Implied < expected, no tail-correlation regime → long 2y outright sized to the worst 2-week move, optional small payer-spread hedge.
* **Middle-East war** — Brent IV 38 vs realised 34 looks "rich, sell". But implied correlation of Brent, gold and defence equities 0.35 → 0.55, index/basket skew ratio 1.0 → 1.4, VVIX 85th pct and rising. Premium in an uptrend → Brent strangle, gold calls, SPX OTM puts vs single-name puts; half-Kelly; exit when VVIX rolls over and the ratio falls back through 1.1.
* **Three alphas**: premium harvesting (short the gap, negative skew, ring-fenced), drift capture (long gamma early then delta-one), long vol / tail-correlation (own the regime while premia rise). Not used: variance, correlation or dispersion swaps, autocallables, exotics.""")
