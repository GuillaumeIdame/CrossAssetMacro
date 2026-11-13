"""§1.1 / §4.1 — Factor decomposition: Δs_i = β_USD F_USD + β_Carry F_Carry + β_Mom F_Mom + ε."""

import numpy as np
import pandas as pd
import streamlit as st

from datahub import stats, ui

from . import common, data


@st.cache_data(ttl=3600, show_spinner=False)
def build_factors(df: pd.DataFrame) -> dict:
    rets = data.returns(df, data.G10).dropna(how="all")
    if rets.empty:
        return dict(factors=pd.DataFrame(), betas={}, eps=pd.DataFrame(), ranks=pd.DataFrame())
    # F_USD: equal-weight G10 basket vs USD (positive = foreign up = USD weaker)
    f_usd = rets.mean(axis=1).rename("F_USD")
    vol = rets.rolling(60, min_periods=20).std()
    # carry rank from short-rate differentials (daily where live, monthly proxy otherwise)
    carry = pd.DataFrame({c: data.carry_diff(df, c) for c in data.G10}).reindex(rets.index).ffill()
    mom = np.log(data.spots(df, data.G10)).diff(252).shift(21).reindex(rets.index)  # 12-1 month
    month_ends = rets.index.to_period("M")
    w_carry = pd.DataFrame(0.0, index=rets.index, columns=rets.columns)
    w_mom = pd.DataFrame(0.0, index=rets.index, columns=rets.columns)

    def leg_weights(scores: pd.Series, v: pd.Series) -> pd.Series:
        s = scores.dropna(); v = v.reindex(s.index)
        w = pd.Series(0.0, index=scores.index)
        if len(s) < 6:
            return w
        order = s.sort_values()
        shorts, longs = order.index[:3], order.index[-3:]
        iv = (1.0 / v.replace(0, np.nan)).fillna(0)
        if iv[longs].sum() > 0:
            w[longs] = iv[longs] / iv[longs].sum()
        if iv[shorts].sum() > 0:
            w[shorts] = -iv[shorts] / iv[shorts].sum()
        return w

    prev = None
    for i, (d, per) in enumerate(zip(rets.index, month_ends)):
        if per != prev:  # rebalance on the first day of the month using yesterday's information; legs frozen intra-month
            j = max(i - 1, 0)
            wc = leg_weights(carry.iloc[j], vol.iloc[j])
            wm = leg_weights(mom.iloc[j], vol.iloc[j])
            prev = per
        w_carry.iloc[i] = wc.values
        w_mom.iloc[i] = wm.values
    f_carry = (w_carry * rets).sum(axis=1).rename("F_Carry")
    f_mom = (w_mom * rets).sum(axis=1).rename("F_Mom")
    factors = pd.concat([f_usd, f_carry, f_mom], axis=1)
    # 120D univariate betas per pair and factor (one regression per factor, never a joint fit)
    betas, eps = {}, {}
    all_rets = data.returns(df).dropna(how="all")
    for c in all_rets.columns:
        y = all_rets[c]
        b = {}
        resid = y.copy()
        for f in factors.columns:
            r = stats.rolling_ols(y, factors[f], 120)
            if r.empty:
                b[f] = pd.Series(np.nan, index=y.index)
            else:
                b[f] = r["beta"].reindex(y.index)
            resid = resid - b[f].fillna(0) * factors[f].reindex(y.index).fillna(0)
        betas[c] = pd.DataFrame(b)
        eps[c] = resid
    eps = pd.DataFrame(eps)
    ranks = pd.DataFrame({"carry_diff_pp": carry.iloc[-1], "mom_12_1": mom.iloc[-1], "w_carry": w_carry.iloc[-1], "w_mom": w_mom.iloc[-1]})
    return dict(factors=factors, betas=betas, eps=eps, ranks=ranks, carry=carry)


def render():
    ui.step("1", "Price → Driver: factor decomposition",
            "Δs = β_USD·F_USD + β_Carry·F_Carry + β_Mom·F_Mom + ε. What is left, ε, is the object the narrative has to explain.", "live")
    m = data.load_all()
    df = m["df"]
    out = build_factors(df)
    if out["factors"].empty:
        st.warning("FX returns unavailable."); return
    fac = out["factors"]
    c1, c2, c3 = st.columns(3)
    for col, f in zip((c1, c2, c3), fac.columns):
        s = fac[f].dropna()
        col.metric(f, f"{100 * s.iloc[-1]:+.2f}% (1D)", f"{100 * s.iloc[-20:].sum():+.2f}% 20D")
    st.markdown("F_USD = equal-weight G10 basket vs USD (positive = USD weaker). F_Carry / F_Mom = top-3 vs bottom-3 G10, "
                "inverse-vol weights, rebalanced monthly with legs frozen intra-month. Carry rank uses the short-rate differential "
                + ui.badge("proxy") + " (daily €STR/SONIA/EFFR, monthly OECD elsewhere); momentum rank is the 12-1 month return.", unsafe_allow_html=True)
    cum = (fac.fillna(0).cumsum() * 100).iloc[-756:]
    cum = cum - cum.iloc[0]
    st.plotly_chart(common.line(cum, "Cumulative factor returns, % (3y)", "%"), use_container_width=True)

    st.markdown("**Betas (120D univariate) and the residual ε — last reading**")
    rows = []
    for c, b in out["betas"].items():
        e = out["eps"][c].dropna()
        e20 = e.rolling(20).sum()
        z = stats.last_z(e20, 504)
        rows.append(dict(pair=data.PAIR_LABEL[c], beta_USD=common.last(b["F_USD"]), beta_Carry=common.last(b["F_Carry"]),
                         beta_Mom=common.last(b["F_Mom"]), eps_20D_pct=100 * common.last(e20), eps_20D_z=z,
                         ret_20D_pct=100 * data.returns(df, [c])[c].iloc[-20:].sum()))
    tab = pd.DataFrame(rows)
    st.dataframe(common.dfmt(tab), use_container_width=True, hide_index=True)
    st.plotly_chart(common.heatmap(tab.set_index("pair")[["beta_USD", "beta_Carry", "beta_Mom"]].T, "Factor loadings", zmax=2, height=260), use_container_width=True)

    ccy = st.selectbox("Narrative object ε for", data.CCYS, format_func=lambda c: data.PAIR_LABEL[c], key="fx_eps_ccy")
    e = out["eps"][ccy].dropna()
    show = pd.DataFrame({"ε cumulative 60D (%)": 100 * e.rolling(60).sum(), "20D z of ε": stats.zscore(e.rolling(20).sum(), 504)}).iloc[-504:]
    st.plotly_chart(common.line(show, f"{data.PAIR_LABEL[ccy]} — residual after Dollar, Carry, Momentum", hline=0), use_container_width=True)

    st.markdown("**Basket membership today**" + (" — carry and momentum legs currently coincide (same top-3 / bottom-3), so F_Carry = F_Mom this month" if (out["ranks"]["w_carry"] - out["ranks"]["w_mom"]).abs().sum() < 1e-9 else ""))
    st.dataframe(common.dfmt(out["ranks"].rename(index=data.PAIR_LABEL)), use_container_width=True)

    with st.expander("Validation episodes (§4.1): Apr-2025 should be F_USD-dominated, Aug-2024 a large negative F_Carry"):
        for label in ("Apr-2025 tariffs", "Aug-2024 carry unwind"):
            a, b = common.window_dates(label)
            w = fac.loc[a:b]
            if w.empty:
                st.write(f"{label}: outside loaded history"); continue
            st.write(f"{label} ({a} → {b}): " + ", ".join(f"{f} {100 * w[f].sum():+.2f}%" for f in fac.columns))
        st.caption("Failure mode: basket membership changes mid-month — legs are frozen within the month here.")
