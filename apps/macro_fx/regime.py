"""§1.6 / §4.1 — Regime engine: five axes (−100…+100, level and direction) and the USD × real-yield quadrant."""

import numpy as np
import pandas as pd
import streamlit as st

from datahub import stats, ui

from . import common, data, factors

Z_WIN = 504


def _z(s: pd.Series) -> pd.Series:
    return stats.zscore(s.dropna(), Z_WIN)


def _chg(s: pd.Series, n: int, log=True) -> pd.Series:
    s = s.dropna()
    return (np.log(s).diff(n) if log and (s > 0).all() else s.diff(n))


@st.cache_data(ttl=3600, show_spinner=False)
def axes(df: pd.DataFrame) -> dict:
    rets = data.returns(df, data.G10)
    fac = factors.build_factors(df)["factors"]
    comp = {}
    # USD axis (positive = strong USD)
    usd = {}
    if "usd_broad" in df.columns: usd["broad USD 60D momentum"] = _z(_chg(df["usd_broad"], 60))
    usd["F_USD 20D (sign flipped)"] = _z(-fac["F_USD"].rolling(20).sum()) if not fac.empty else None
    usd["breadth: share of G10 down vs USD (20D)"] = _z((rets.rolling(20).sum() < 0).mean(axis=1))
    if "ust2" in df.columns:
        fr = pd.concat([data.short_rate(df, c) for c in data.G10], axis=1).mean(axis=1)
        usd["rate support: 2y US − avg foreign short, 60D Δ"] = _z(_chg(df["ust2"] - fr.reindex(df.index).ffill(), 60, log=False))
    if "spx" in df.columns: usd["risk-off: −SPX 20D"] = _z(-_chg(df["spx"], 20))
    comp["USD"] = usd
    risk = {}
    for k, lab in [("audjpy", "AUD/JPY 20D"), ("cadjpy", "CAD/JPY 20D"), ("eem", "EM equities 20D"), ("spx", "SPX 20D"), ("copper", "copper 20D")]:
        if k in df.columns: risk[lab] = _z(_chg(df[k], 20))
    if "hyg" in df.columns and "lqd" in df.columns: risk["HYG/LQD 20D"] = _z(_chg(df["hyg"] / df["lqd"], 20))
    if "vix" in df.columns: risk["inverse VIX (level)"] = _z(-df["vix"])
    comp["Global Risk"] = risk
    liq = {}
    if "real10" in df.columns: liq["−real-yield impulse (10y TIPS 20D Δ)"] = _z(-_chg(df["real10"], 20, log=False))
    if "vix" in df.columns: liq["−VIX"] = _z(-df["vix"])
    if "move" in df.columns: liq["−MOVE"] = _z(-df["move"])
    if "hy_oas" in df.columns: liq["−HY OAS"] = _z(-df["hy_oas"])
    if "emb" in df.columns: liq["EM USD sovereign 20D"] = _z(_chg(df["emb"], 20))
    comp["Liquidity"] = liq
    carry = {}
    if not fac.empty:
        cum = fac["F_Carry"].fillna(0).cumsum()
        carry["carry-basket drawdown (60D)"] = _z(cum - cum.rolling(60).max())
        carry["carry-basket 20D return"] = _z(fac["F_Carry"].rolling(20).sum())
    cd = pd.concat([data.carry_diff(df, c) for c in data.G10], axis=1)
    vol = rets.rolling(60).std() * np.sqrt(252) * 100
    if not cd.empty:
        top = cd.reindex(df.index).ffill().apply(lambda r: r.nlargest(3).mean(), axis=1)
        carry["carry/vol of top-3 (level)"] = _z(top / vol.mean(axis=1).reindex(top.index))
    carry["−realised FX vol (G10 avg 20D)"] = _z(-(rets.rolling(20).std() * np.sqrt(252)).mean(axis=1))
    comp["Carry Health"] = carry
    ry = {}
    if all(k in df.columns for k in ("ust1", "ust2", "bei5")):
        r11 = 2 * df["ust2"] - df["ust1"] - df["bei5"]
        ry["US 1y1y real (level)"] = _z(r11); ry["US 1y1y real 20D Δ"] = _z(r11.diff(20))
    if "real10" in df.columns: ry["US 10y real (level)"] = _z(df["real10"])
    comp["Real Yield"] = ry
    scores, raw = {}, {}
    for name, parts in comp.items():
        parts = {k: v for k, v in parts.items() if v is not None and not v.dropna().empty}
        if not parts:
            scores[name] = pd.Series(dtype=float); raw[name] = pd.DataFrame(); continue
        z = pd.concat(parts, axis=1).reindex(df.index).ffill(limit=7)
        zm = z.mean(axis=1)
        scores[name] = 100 * np.tanh(zm / 2)
        raw[name] = z
    S = pd.DataFrame(scores)
    return dict(scores=S, raw=raw)


def quadrant_series(S: pd.DataFrame) -> pd.DataFrame:
    if "USD" not in S or "Real Yield" not in S:
        return pd.DataFrame()
    c = S[["USD", "Real Yield"]].rolling(10).mean().dropna()
    def label(u, r):
        if u >= 0 and r >= 0: return "USD↑ · real↑ — rates shock"
        if u >= 0 and r < 0: return "USD↑ · real↓ — risk-off / liquidity"
        if u < 0 and r >= 0: return "USD↓ · real↑ — confidence / de-dollarisation"
        return "USD↓ · real↓ — dovish easing / reflation"
    c["quadrant"] = [label(u, r) for u, r in zip(c["USD"], c["Real Yield"])]
    # persistence: the quadrant counts once it has held ≥ 5 days
    run = (c["quadrant"] != c["quadrant"].shift()).cumsum()
    c["days_in"] = c.groupby(run).cumcount() + 1
    confirmed = c["quadrant"].where(c["days_in"] >= 5).ffill()
    c["confirmed"] = confirmed
    c["migrating"] = (c["quadrant"] != c["confirmed"]) & (c["days_in"] < 5)
    return c


PLAYBOOK = {
    "USD↑ · real↑ — rates shock": "Policy repricing; short low-yielders, EM pressure; carry mixed, funding-currency squeeze risk.",
    "USD↑ · real↓ — risk-off / liquidity": "Flight to USD; long USD and JPY vs high beta; carry unwinding; cut gross.",
    "USD↓ · real↑ — confidence / de-dollarisation": "The anomalous quadrant (April 2025). Broad short-USD, gold and non-USD blocs; watch term premium, not policy rates.",
    "USD↓ · real↓ — dovish easing / reflation": "Risk-on; EM and commodity FX lead; carry healthy; classic weak-dollar playbook.",
}


def render():
    ui.step("6", "Regime — five axes and one quadrant", "Each axis −100…+100 = 100·tanh(z̄/2), reported as level AND direction (20D change). Quadrant migration is the highest-value regime signal.", "proxy")
    m = data.load_all(); df = m["df"]
    out = axes(df); S = out["scores"]
    if S.empty:
        st.warning("Regime components unavailable."); return
    last = S.dropna(how="all").iloc[-1]; prev = S.dropna(how="all").iloc[-21] if len(S.dropna(how="all")) > 21 else last
    common.gauge_row({k: last[k] for k in S.columns}, {k: last[k] - prev[k] for k in S.columns})
    st.caption("Direction and level together: 'fragile and deteriorating' and 'fragile but stabilising' are different trades. Components are z-scored on 2y; tanh hides extremes, so the raw z is shown below.")
    st.plotly_chart(common.line(S.iloc[-756:], "Axes, 3y", hline=0), use_container_width=True)
    with st.expander("Raw component z-scores (last reading)"):
        for name, z in out["raw"].items():
            if z.empty: st.write(f"{name}: unavailable"); continue
            st.markdown(f"**{name}**")
            st.dataframe(common.dfmt(z.dropna(how='all').iloc[-1].rename('z').to_frame().T), use_container_width=True)
    decides = {"USD": "Express vs USD or as crosses; net USD delta with or against regime", "Global Risk": "Cyclical vs defensive tilt",
               "Liquidity": "Gross ceiling; carry size; whether dislocations revert (easing) or extend (stress). Cross-currency basis not public → not included",
               "Carry Health": "Carry and short-vol sleeve sizing; price of insurance (RR from the manual surface if typed)", "Real Yield": "Feeds the quadrant; rates-driven vs risk-driven USD"}
    st.dataframe(pd.DataFrame({"axis": list(decides), "decides": list(decides.values())}), use_container_width=True, hide_index=True)

    st.markdown("### Quadrant — USD × real yield (10D centroid, ≥ 5-day persistence)")
    q = quadrant_series(S)
    if q.empty:
        st.info("Need both USD and Real Yield axes."); return
    cur = q.iloc[-1]
    c1, c2 = st.columns([1, 2])
    c1.metric("Confirmed quadrant", cur["confirmed"] if isinstance(cur["confirmed"], str) else "n/a")
    c1.metric("Days in current cell", int(cur["days_in"]))
    if cur["migrating"]:
        c1.warning(f"Migration in progress → {cur['quadrant']}")
    c2.info(PLAYBOOK.get(cur["confirmed"], ""))
    import plotly.graph_objects as go
    path = q.iloc[-120:]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=path["USD"], y=path["Real Yield"], mode="lines+markers", line=dict(color=common.SLATE, width=1),
                             marker=dict(size=5, color=np.linspace(0, 1, len(path)), colorscale=[[0, "#D9DEE5"], [1, common.BRONZE]]), name="10D centroid, last 120 days"))
    fig.add_trace(go.Scatter(x=[path["USD"].iloc[-1]], y=[path["Real Yield"].iloc[-1]], mode="markers", marker=dict(size=14, color=common.NAVY), name="today"))
    fig.add_hline(y=0, line=dict(color="#999", width=1)); fig.add_vline(x=0, line=dict(color="#999", width=1))
    for x, y, t in [(50, 50, "rates shock"), (50, -50, "risk-off / liquidity"), (-50, 50, "confidence / de-dollarisation"), (-50, -50, "dovish easing / reflation")]:
        fig.add_annotation(x=x, y=y, text=t, showarrow=False, font=dict(color=common.SLATE, size=11))
    fig.update_layout(xaxis_title="USD axis", yaxis_title="Real-yield axis", xaxis_range=[-100, 100], yaxis_range=[-100, 100], **{**common.LAYOUT, "height": 460})
    st.plotly_chart(fig, use_container_width=True)
    with st.expander("Validation episodes (§4.1): Mar-2020 risk-off, 2022 rates shock, Apr-2025 confidence"):
        for lab, (a, b) in [("Mar-2020", ("2020-03-01", "2020-03-31")), ("2022 rates shock", ("2022-06-01", "2022-10-31")), ("Apr-2025", ("2025-04-01", "2025-04-30"))]:
            w = q.loc[a:b]
            st.write(f"{lab}: " + (w["quadrant"].value_counts().index[0] if len(w) else "outside history"))
