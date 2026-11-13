"""§1.3 — Valuation: univariate short-horizon regressions, composite residual, disagreement flag, REER anchor."""

import numpy as np
import pandas as pd
import streamlit as st

from datahub import stats, ui

from . import common, data


def drivers_for(df: pd.DataFrame, ccy: str) -> dict:
    """Driver differentials (foreign − US), as levels: short rate, 10y, equity (log ratio), inflation YoY."""
    d = {}
    fs, us = data.short_rate(df, ccy), data.short_rate(df, "USD")
    if not fs.empty and not us.empty:
        d[f"short-rate diff ({data.quality_of(ccy, 'short')})"] = fs - us
    fl, ul = data.long_rate(df, ccy), data.long_rate(df, "USD")
    if not fl.empty and not ul.empty:
        d[f"10y diff ({data.quality_of(ccy, 'long')})"] = fl - ul
    fe, ue = data.equity(df, ccy), data.equity(df, "USD")
    if not fe.empty and not ue.empty:
        d["equity diff (live)"] = np.log(fe) - np.log(ue)
    fi, ui_ = data.inflation_yoy(df, ccy), data.inflation_yoy(df, "USD")
    if not fi.empty and not ui_.empty:
        d[f"inflation diff ({data.quality_of(ccy, 'inflation')})"] = fi - ui_
    if "bei5" in df.columns and ccy == "EUR" and "ea_hicp" in df.columns:
        pass
    return d


@st.cache_data(ttl=3600, show_spinner=False)
def valuation_table(df: pd.DataFrame, window: int) -> pd.DataFrame:
    rows = []
    for c in data.CCYS:
        y = np.log(data.spot(df, c)).dropna()
        drv = drivers_for(df, c)
        if y.empty or not drv:
            rows.append(dict(ccy=c, pair=data.PAIR_LABEL[c], composite_z=np.nan, disagreement=False, n_drivers=0)); continue
        tab = stats.univariate_residuals(y, drv, window=window)
        comp, dis = stats.composite_residual(tab)
        row = dict(ccy=c, pair=data.PAIR_LABEL[c], composite_z=comp, disagreement=dis, n_drivers=int(tab["resid_z"].notna().sum()))
        for _, r in tab.iterrows():
            row[r["driver"].split(" (")[0]] = r["resid_z"]
            row[r["driver"].split(" (")[0] + " R²"] = r["r2"]
        rows.append(row)
    return pd.DataFrame(rows)


def reer_stretch(df: pd.DataFrame, ccy: str):
    s = data.reer(df, ccy).dropna()
    if s.empty:
        return np.nan, None
    m = s.resample("MS").last().dropna()
    w = m.iloc[-120:]
    z = (w.iloc[-1] - w.mean()) / w.std() if w.std() > 0 else np.nan
    return float(z), m


def render():
    ui.step("3", "Valuation — univariate short horizon, REER anchor",
            "Δs = α_k + β_k Δx_k + u_k, one regression per driver. |z| ≥ 2 flags dislocation; value is an anchor, not a signal.", "proxy")
    m = data.load_all(); df = m["df"]
    window = st.radio("Window (business days)", [20, 60, 120], index=1, horizontal=True, key="fx_val_win")
    tab = valuation_table(df, window)
    zcols = [c for c in tab.columns if c not in ("ccy", "pair", "composite_z", "disagreement", "n_drivers") and not c.endswith("R²")]
    st.markdown("Regressions are on **levels** (log spot on the driver differential) over the rolling window; residual z = distance from "
                "the fitted relationship in units of the window's residual σ. Fits with R² < 0.05 or > 0.999 return NaN (unmodelled regime / degenerate), never a dead fair value. "
                + ui.badge("live") + " equity diff; " + ui.badge("proxy") + " rate and inflation diffs where the foreign leg is a monthly OECD mirror.", unsafe_allow_html=True)
    show = tab[["pair", "composite_z", "disagreement", "n_drivers"] + zcols].copy()
    st.dataframe(common.dfmt(show), use_container_width=True, hide_index=True)
    hm = tab.set_index("pair")[zcols].astype(float)
    st.plotly_chart(common.heatmap(hm, f"Residual z by pair × driver ({window}D)", zmax=3, height=420), use_container_width=True)
    dis = tab[tab["disagreement"]]["pair"].tolist()
    if dis:
        st.warning("Driver-disagreement flag ON for: " + ", ".join(dis) + " — the market has rotated to a driver the models do not carry. Response: narrative work, not mean reversion.")

    st.markdown("**Fade or follow** — tiebreakers: breadth (pair-specific or bloc-wide?), options confirmation (is skew paying for continuation?), regime stability (page 6). Fade only when the residual is local, skew unmoved and axes stable.")
    bloc = tab["composite_z"].dropna()
    if len(bloc):
        same = (np.sign(bloc) == np.sign(bloc.median())).mean()
        st.caption(f"Breadth check: {100 * same:.0f}% of pairs share the sign of the median composite residual ({bloc.median():+.2f}).")

    st.markdown("### REER stretch (BIS, monthly) — two uses only")
    rows = []
    for c in ["USD"] + data.CCYS:
        z, mser = reer_stretch(df, c)
        rows.append(dict(currency=c, reer_z_10y=z, haircut="conviction haircut" if np.isfinite(z) and abs(z) >= 2 else "", last=(mser.index[-1].date() if mser is not None else None)))
    rt = pd.DataFrame(rows)
    st.dataframe(common.dfmt(rt), use_container_width=True, hide_index=True)
    st.caption("Use 1: conviction haircut for positions pushing beyond ±2z (modest uplift for fades). Use 2: stop placement away from REER-consistent zones. It never triggers a trade. " + "Source: BIS REER on FRED (RB*BIS), 10y mean z.")
    with st.expander("Built-engine note"):
        st.write("The Valuation Monitor's fx.py regresses log spot on equity, 1y inflation and rate differentials at 1y1y/5y/10y; RATE_TENORS is the one-line switch to the 1Y1Y/5Y5Y specification. Here the public proxies are the short-rate and 10y differentials; drop in OIS 1Y1Y and 5Y5Y behind `drivers_for` when a feed exists.")
