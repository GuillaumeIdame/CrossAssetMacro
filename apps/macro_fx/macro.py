"""§1.2 — Macro: four differentials (growth surprise, 1Y1Y real rate, terms of trade, fiscal impulse)."""

import numpy as np
import pandas as pd
import streamlit as st

from datahub import stats, ui

from . import common, data

TOT_DEFAULT = pd.DataFrame({  # export (+) / import (−) weights per currency, editable — illustrative
    "brent": [-0.2, -0.3, -0.5, -0.1, 0.6, 0.1, -0.1, -0.1, 0.8, 0.3, -0.2, -0.5, -0.5],
    "copper": [0.0, 0.0, 0.0, 0.0, 0.1, 0.3, 0.0, 0.1, 0.0, 0.1, 0.2, 0.0, 0.1],
    "gold": [0.0, 0.0, 0.0, 0.3, 0.1, 0.2, 0.0, 0.0, 0.0, 0.0, 0.3, 0.0, 0.0],
    "natgas": [-0.1, -0.1, -0.2, 0.0, 0.1, 0.2, 0.0, 0.0, 0.2, 0.0, 0.0, 0.0, 0.0],
    "wheat": [0.0, 0.0, 0.0, 0.0, 0.1, 0.2, 0.3, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
}, index=["USD", "EUR", "GBP", "JPY", "CHF", "CAD", "AUD", "NZD", "SEK", "NOK", "MXN", "ZAR", "CNY"])
TOT_DEFAULT.loc["USD"] = [0.1, 0.0, 0.0, 0.1, 0.1]

GROWTH_SERIES = {  # available growth series per bloc: key, higher = stronger
    "USD": ["indpro", "retail", "payems", "umcsent"], "EUR": ["ea_bus_conf", "sx5e"], "GBP": ["ftse"], "JPY": ["nikkei"],
    "CHF": ["^SSMI"], "CAD": ["^GSPTSE"], "AUD": ["^AXJO"], "NZD": ["^NZ50"], "SEK": ["^OMX"], "NOK": [], "MXN": ["^MXX"], "ZAR": ["^J203.JO"], "CNY": ["000001.SS"],
}


def growth_composite(df: pd.DataFrame, ccy: str) -> pd.Series:
    """Proxy for a growth-surprise index: z of 60D change across standardised growth series.
    Not a true surprise index (no consensus available); label it so."""
    parts = []
    for k in GROWTH_SERIES.get(ccy, []):
        if k in df.columns and df[k].notna().sum() > 300:
            s = df[k].astype(float)
            ch = np.log(s).diff(60) if (s.dropna() > 0).all() else s.diff(60)
            parts.append(stats.zscore(ch, 504))
    if not parts:
        return pd.Series(dtype=float)
    return pd.concat(parts, axis=1).mean(axis=1)


def real_1y1y_proxy(df: pd.DataFrame, ccy: str) -> pd.Series:
    """US: 1y1y nominal = 2·DGS2 − DGS1, minus 5y breakeven as the inflation proxy. Others: 10y nominal
    (monthly) minus CPI YoY — a much weaker proxy, flagged."""
    if ccy == "USD" and all(k in df.columns for k in ("ust1", "ust2", "bei5")):
        return (2 * df["ust2"] - df["ust1"] - df["bei5"]).rename("USD")
    lr, inf = data.long_rate(df, ccy), data.inflation_yoy(df, ccy)
    if lr.empty or inf.empty:
        return pd.Series(dtype=float)
    return (lr - inf.reindex(lr.index).ffill()).rename(ccy)


def terms_of_trade(df: pd.DataFrame, ccy: str, weights: pd.DataFrame) -> pd.Series:
    cols = [c for c in weights.columns if c in df.columns]
    if not cols:
        return pd.Series(dtype=float)
    r = np.log(df[cols].astype(float)).diff()
    w = weights.loc[ccy, cols]
    return (r * w).sum(axis=1).cumsum().rename(ccy)


def differential_block(name: str, a: pd.Series, b: pd.Series, fails: str, quality: str, unit: str = ""):
    if a.empty or b.empty:
        st.markdown(f"**{name}** {ui.badge('unavailable')} — missing series for one leg", unsafe_allow_html=True); return None
    d = (a - b.reindex(a.index)).dropna()
    if d.empty:
        st.markdown(f"**{name}** {ui.badge('unavailable')}", unsafe_allow_html=True); return None
    lvl = d.iloc[-1]; mom = d.iloc[-1] - d.iloc[-61] if len(d) > 61 else np.nan
    z = stats.last_z(d.diff(60).dropna(), 504)
    c1, c2, c3, c4 = st.columns([2, 1, 1, 1])
    c1.markdown(f"**{name}** {ui.badge(quality)}<br><span style='color:#55677C;font-size:12px'>Fails when: {fails}</span>", unsafe_allow_html=True)
    c2.metric("Level (A−B)", f"{lvl:+.2f}{unit}")
    c3.metric("60D momentum", "n/a" if np.isnan(mom) else f"{mom:+.2f}{unit}")
    c4.metric("z of 60D Δ (2y)", "n/a" if np.isnan(z) else f"{z:+.2f}")
    return d


def render():
    ui.step("2", "Macro — four differentials", "Which economy is repricing faster, and through which channel? 60D momentum matters more than level.", "proxy")
    m = data.load_all(); df = m["df"]
    c1, c2 = st.columns(2)
    a = c1.selectbox("Currency A (long leg)", data.CCYS, index=0, key="fx_macro_a")
    b = c2.selectbox("Currency B (short leg)", ["USD"] + data.CCYS, index=0, key="fx_macro_b")
    st.caption("Each differential is A − B. Inflation and policy expectations sit inside the real-rate differential; liquidity and risk belong to the regime block.")

    out = {}
    out["growth"] = differential_block("Growth surprise differential", growth_composite(df, a), growth_composite(df, b),
                                       "the reaction function is saturated — at bounds or dominated by the inflation mandate", "proxy")
    st.caption("Proxy: z of 60D change in available growth series (IP, retail, payrolls, sentiment, local equities). A true surprise index needs consensus data (Bloomberg/Citi) — not public.")
    out["real"] = differential_block("1Y1Y real-rate differential", real_1y1y_proxy(df, a), real_1y1y_proxy(df, b),
                                     "credibility-regime switch, where higher yields weaken the currency", "proxy", " pp")
    st.caption("US leg: 2·2y − 1y minus 5y breakeven (daily). Other legs: 10y nominal (monthly OECD) minus CPI YoY (lagging) — weak proxy; swap in OIS/inflation swaps when available.")

    with st.expander("Terms-of-trade weights (export + / import −), editable"):
        w = st.data_editor(common.session_dict("fx_tot_weights", TOT_DEFAULT.to_dict()) and
                           pd.DataFrame(st.session_state["fx_tot_weights"]), key="fx_tot_editor", use_container_width=True)
        st.session_state["fx_tot_weights"] = w.to_dict()
    weights = pd.DataFrame(st.session_state["fx_tot_weights"])
    tot_a, tot_b = terms_of_trade(df, a, weights), terms_of_trade(df, b, weights)
    if not tot_a.empty and not tot_b.empty:
        d = (tot_a - tot_b.reindex(tot_a.index)).dropna()
        r20 = d.iloc[-1] - d.iloc[-21]; r60 = d.iloc[-1] - d.iloc[-61]
        z = stats.last_z(d.diff(60).dropna(), 504)
        c1, c2, c3, c4 = st.columns([2, 1, 1, 1])
        c1.markdown(f"**Terms-of-trade differential** {ui.badge('proxy')}<br><span style='color:#55677C;font-size:12px'>Fails when: fiscal policy sterilises the windfall or hedging flows dominate</span>", unsafe_allow_html=True)
        c2.metric("20D", f"{100 * r20:+.2f}%"); c3.metric("60D", f"{100 * r60:+.2f}%"); c4.metric("z of 60D Δ", f"{z:+.2f}" if np.isfinite(z) else "n/a")
        out["tot"] = d
    fi_a = st.number_input(f"Fiscal impulse {a} (Δ cyclically-adjusted primary balance, % GDP, forecast year)", value=0.0, step=0.1, key="fx_fi_a")
    fi_b = st.number_input(f"Fiscal impulse {b}", value=0.0, step=0.1, key="fx_fi_b")
    st.markdown(f"**Fiscal impulse differential** {ui.badge('manual')}: {fi_a - fi_b:+.1f} pp — sign is regime-dependent: positive under credibility, negative under fiscal dominance (IMF Fiscal Monitor / OECD EO, typed by the desk).", unsafe_allow_html=True)

    series = {k: v for k, v in out.items() if v is not None and not v.empty}
    if series:
        panel = pd.DataFrame({k: stats.zscore(v.diff(60).dropna(), 504) for k, v in series.items()}).iloc[-504:]
        st.plotly_chart(common.line(panel, f"{a} − {b}: z of 60D momentum per differential", hline=0), use_container_width=True)
    st.info("Anything the four differentials cannot explain is, by construction, a regime or flow phenomenon → pages 4 and 6.")
