"""Page 3 — Market-implied state: futures grid, meeting-dated path, broader pricing (§4.1 c3, §4.2)."""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from datahub import stir, ui

from . import common as C


def _strip_table(s: pd.DataFrame):
    show = s.copy()
    cols = ["contract", "contract_month", "close", "implied_rate", "win_start", "win_end", "source"]
    for extra in ("chg_1d", "chg_1w"):
        if extra in show.columns:
            cols.insert(4, extra)
    show = show[cols]
    show["win_start"] = pd.to_datetime(show["win_start"]).dt.date
    show["win_end"] = pd.to_datetime(show["win_end"]).dt.date
    for c in ("chg_1d", "chg_1w"):
        if c in show.columns:
            show[c] = (show[c] * 100).round(1).rename(c + "_bp")
            show = show.rename(columns={c: c + "_bp"})
    show["implied_rate"] = show["implied_rate"].round(3)
    st.dataframe(show, hide_index=True, width="stretch", height=min(520, 38 + 35 * len(show)))


def _path_chart(family, s, bs, spot):
    fig = go.Figure()
    if not bs.empty:
        today = pd.Timestamp.today().normalize()
        path = stir.path_from_steps(bs, spot, today, bs["effective"].max() + pd.Timedelta(days=60))
        fig.add_trace(go.Scatter(x=path.index, y=path.values, name=f"market-implied {C.FAMILY_META[family]['spot_label']} path",
                                 line=dict(color=C.NAVY, shape="hv")))
        fig.add_trace(go.Scatter(x=bs["date"], y=bs["rate_after"], mode="markers+text", text=[f"{v:+.0f}" for v in bs["step_bp"]],
                                 textposition="top center", name="meeting (step bp)", marker=dict(color=C.BRONZE, size=9)))
    mid = (s["win_start"] + (s["win_end"] - s["win_start"]) / 2)
    fig.add_trace(go.Scatter(x=mid, y=s["implied_rate"] - C.basis_bp(family) / 100, mode="markers", name="contract implied (net of basis)",
                             marker=dict(symbol="diamond", color=C.SLATE, size=8)))
    fig.add_hline(y=spot, line=dict(color=C.SLATE, dash="dot"), annotation_text=f"spot {spot:.2f}")
    return C.plotly_layout(fig, height=360)


def _family_block(family: str):
    meta = C.FAMILY_META[family]
    bs, s, spot = C.bootstrap(family)
    if s.empty:
        st.warning(f"No strip available for {meta['label']} — paste one below or refresh the IBKR snapshot.")
        return
    src = str(s["source"].iloc[0])
    q = "manual" if src == "manual" else "live"
    close_date = pd.to_datetime(s["close_date"]).max().date() if "close_date" in s.columns else "n/a"
    st.markdown(f"**{meta['label']}** {ui.badge(q)} &nbsp;<span style='color:{C.SLATE};font-size:12px'>source: {src}, closes as of {close_date} · "
                f"spot {meta['spot_label']} = {spot:.3f}% {ui.badge(C.quality_of(meta['spot']))}</span>", unsafe_allow_html=True)
    c1, c2 = st.columns([1.15, 1])
    with c1:
        _strip_table(s)
    with c2:
        if bs.empty:
            st.info("No meetings inside the strip horizon in the calendar file.")
        else:
            show = bs[["date", "event", "status", "step_bp", "cum_bp", "rate_after", "p_move_25"]].copy()
            show["date"] = pd.to_datetime(show["date"]).dt.date
            show = show.round({"step_bp": 1, "cum_bp": 1, "rate_after": 3, "p_move_25": 2})
            st.dataframe(show, hide_index=True, width="stretch", height=min(520, 38 + 35 * len(show)))
            st.caption(f"Fit error {bs.attrs.get('fit_error_bp', float('nan')):.2f} bp over {bs.attrs.get('n_contracts')} contracts · "
                       f"p(25bp) = step/25 (sign = direction). Meeting dates: {ui.badge('estimated')} where the calendar says so.", unsafe_allow_html=True)
    st.plotly_chart(_path_chart(family, s, bs, spot), width="stretch")
    with st.expander(f"Edit / paste a strip for {family} (manual)"):
        base = s[["contract", "contract_month", "close"]].copy()
        edited = st.data_editor(base, num_rows="dynamic", key=f"editor_{family}", width="stretch")
        c_a, c_b = st.columns(2)
        if c_a.button(f"Use edited strip for {family}", key=f"use_{family}"):
            ed = edited.dropna(subset=["contract_month", "close"]).copy()
            ed["contract_month"] = ed["contract_month"].astype(str).str[:7]
            ed["close"] = ed["close"].astype(float)
            ed["exchange"] = ""; ed["family"] = family; ed["ccy"] = ""; ed["close_date"] = pd.Timestamp.today().normalize()
            ed["last_trading_date"] = pd.NaT; ed["status"] = "manual"
            st.session_state[f"strip_manual_{family}"] = ed
            st.rerun()
        if c_b.button(f"Revert to loaded strip for {family}", key=f"rev_{family}"):
            st.session_state.pop(f"strip_manual_{family}", None)
            st.rerun()


def render():
    ui.step("4.2", "Market-implied state — G3 futures grid and meeting path",
            "What is the market implying, meeting by meeting, and is it ahead of or behind the bank?")
    res = C.market()
    st.session_state["euribor_basis_bp"] = st.slider("3M Euribor − €STR basis (bp) used to translate the Euribor strip into an overnight path",
                                                     0.0, 30.0, float(st.session_state.get("euribor_basis_bp", 12.0)), 0.5)
    st.markdown(ui.badge("manual") + " basis is a desk input (no public daily Euribor fixing on FRED).", unsafe_allow_html=True)

    # --- broad state strip ----------------------------------------------------
    st.subheader("Market-implied state")
    y1, _ = C.last(res, "ust1"); y2, d2 = C.last(res, "ust2"); y10, _ = C.last(res, "ust10"); y5, _ = C.last(res, "ust5"); y30, _ = C.last(res, "ust30")
    b10, _ = C.last(res, "bei10"); tp, _ = C.last(res, "tp10"); effr, _ = C.last(res, "effr")
    fwd1y1y = ((1 + y2 / 100) ** 2 / (1 + y1 / 100) - 1) * 100 if np.isfinite(y1) and np.isfinite(y2) else np.nan
    terminal = {}
    for fam in ("ZQ", "SR3", "ER", "SON"):
        s = C.active_strip(fam)
        if not s.empty:
            terminal[fam] = float(s["implied_rate"].max() - C.basis_bp(fam) / 100)
    ui.kpi_row([("EFFR", C.fmt(effr, 2, "%")), ("US 2y", C.fmt(y2, 2, "%")), ("1y1y (from 1y/2y)", C.fmt(fwd1y1y, 2, "%"), None, "proxy: ((1+y2)²/(1+y1))−1"),
                ("2s10s", C.fmt((y10 - y2) * 100 if np.isfinite(y10) and np.isfinite(y2) else np.nan, 0, " bp")),
                ("5s30s", C.fmt((y30 - y5) * 100 if np.isfinite(y30) and np.isfinite(y5) else np.nan, 0, " bp")),
                ("10y breakeven", C.fmt(b10, 2, "%")), ("ACM 10y term premium", C.fmt(tp, 2, "%"))])
    tcols = st.columns(4)
    for col, fam in zip(tcols, ("ZQ", "SR3", "ER", "SON")):
        col.metric(f"Strip peak / terminal proxy — {fam}", C.fmt(terminal.get(fam), 2, "%"), help="max implied rate on the loaded strip, net of basis")
    st.markdown(ui.badge("live") + f" FRED yields as of {d2.date() if d2 is not None else 'n/a'}; " + ui.badge("proxy") +
                " 1y1y from the par 1y/2y points; terminal = strip maximum.", unsafe_allow_html=True)

    # --- families ------------------------------------------------------------
    st.subheader("Futures grid and meeting-dated pricing")
    tabs = st.tabs([C.FAMILY_META[f]["label"] for f in ("ZQ", "SR3", "ER", "SON")])
    for tab, fam in zip(tabs, ("ZQ", "SR3", "ER", "SON")):
        with tab:
            _family_block(fam)

    # --- Fed: ZQ vs SR3 consistency ------------------------------------------
    st.subheader("Reaction-function check: market ahead of the bank, bank ahead of the market, or consistent?")
    bs_zq, _, _ = C.bootstrap("ZQ")
    if not bs_zq.empty:
        nxt = bs_zq.iloc[0]
        cum4 = bs_zq["step_bp"].iloc[:4].sum()
        g = st.session_state.get("gauge_overrides", {})
        st.markdown(f"Fed: next meeting prices **{nxt['step_bp']:+.0f} bp**, next four meetings **{cum4:+.0f} bp** cumulative. "
                    "Compare with the regime cell on the Macro read page: Overheating/Early-reacceleration cells call for a path above the priced one "
                    "(bank behind the market → pay the front end only if positioning is not already there); Slowdown calls for a path below it.")
    snap = stir.latest_snapshot_path()
    st.caption(f"IBKR snapshot in use for SR3 / Euribor / SONIA: {snap.split('/')[-1] if snap else 'none'} — refresh via the connector, "
               "`python -m datahub.ibkr_refresh` (TWS/Gateway), or the manual editor above. Fed funds (ZQ) refresh daily from Yahoo individual contracts.")
