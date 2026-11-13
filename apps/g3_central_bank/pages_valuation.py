"""Page 5 — Distribution tree, valuation engine, Kelly, leg choice (§1.5, §2.4, §4.3)."""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from datahub import calendar, kelly, ui

from . import common as C
from . import engine as E

OUTCOMES = [-50, -25, 0, 25, 50]


def _default_probs(step_bp: float, width_bp: float) -> list:
    return [float(x) for x in E.normal_probs(step_bp, width_bp, OUTCOMES)]


def render():
    ui.step("1.5", "Distribution tree → fair value → size",
            "Macro scenarios → probability distribution → meeting outcomes → futures prices; E[F] = Σ pⱼ Fⱼ, EV = E[payoff] − market, f* = argmax Σ pⱼ ln(1 + f rⱼ).")
    fam = st.radio("Contract family", list(C.FAMILY_META), format_func=lambda f: C.FAMILY_META[f]["label"], horizontal=True, key="val_family")
    bs, s, spot = C.bootstrap(fam)
    if bs.empty or s.empty:
        st.warning("Strip or meeting calendar missing for this family."); return
    region = C.FAMILY_META[fam]["region"]
    basis = C.basis_bp(fam)
    mts = calendar.meetings(region, start=pd.Timestamp.today().normalize(), end=s["win_end"].max(), cal=C.cal())
    A, contracts = E.window_fractions(fam, s, mts)
    market_steps = bs["step_bp"].values.tolist()

    n_m = st.slider("Meetings in the tree (later meetings keep the market-priced step)", 1, min(4, len(mts)), min(2, len(mts)))
    width_mkt = st.slider("Market-implied width per meeting (bp, std of the step) — manual until an options surface is wired", 5.0, 40.0,
                          float(st.session_state.get("width_mkt", 15.0)), 1.0)
    st.session_state["width_mkt"] = width_mkt
    st.markdown(ui.badge("live") + " market steps from the bootstrap; " + ui.badge("manual") + " internal probabilities and widths.", unsafe_allow_html=True)

    probs_store = C.ss_get("tree_probs", {})
    per_meeting_int, per_meeting_mkt = [], []
    cols = st.columns(n_m)
    for m in range(n_m):
        mk = mts.iloc[m]; step = market_steps[m]
        key = f"{fam}:{mk['date'].date()}"
        default = probs_store.get(key) or _default_probs(step, width_mkt)
        with cols[m]:
            st.markdown(f"**{m + 1}. {mk['date'].date()} — {mk['event']}** {ui.badge(mk['status'])}<br><span style='color:{C.SLATE};font-size:12px'>market step {step:+.1f} bp</span>",
                        unsafe_allow_html=True)
            edit = pd.DataFrame({"outcome_bp": OUTCOMES, "p_internal": np.round(default, 3)})
            edited = st.data_editor(edit, hide_index=True, key=f"tree_{key}", width="stretch",
                                    column_config={"p_internal": st.column_config.NumberColumn(min_value=0.0, max_value=1.0, step=0.01)})
            p = kelly.normalise(edited["p_internal"].fillna(0).tolist())
            probs_store[key] = [float(x) for x in p]
            if st.button("reset to market", key=f"reset_{key}"):
                probs_store.pop(key, None); st.rerun()
            mom = kelly.moments(p, OUTCOMES)
            st.caption(f"internal mean {mom['mean']:+.1f} bp · std {mom['std']:.1f} · skew {mom['skew']:+.2f}")
        per_meeting_int.append((OUTCOMES, p))
        per_meeting_mkt.append((OUTCOMES, _default_probs(step, width_mkt)))
    st.session_state["tree_probs"] = probs_store

    tree_int = E.build_tree(per_meeting_int)
    tree_mkt = E.build_tree(per_meeting_mkt)
    tail = market_steps[n_m:]

    def fair_for(tree):
        fp = np.zeros((len(tree), len(contracts)))
        for i, r in tree.iterrows():
            steps = [r[f"m{m + 1}"] for m in range(n_m)] + tail
            fp[i] = E.fair_prices(contracts, A, spot, basis, steps)
        return fp

    fp_int, fp_mkt = fair_for(tree_int), fair_for(tree_mkt)
    p_int, p_mkt = tree_int["prob"].values, tree_mkt["prob"].values
    ef_int = p_int @ fp_int; ef_mkt = p_mkt @ fp_mkt

    st.subheader("Per contract — expected price, market, EV")
    tbl = contracts[["contract", "contract_month", "close"]].copy()
    tbl["E[F] internal"] = ef_int.round(4); tbl["E[F] market tree"] = ef_mkt.round(4)
    tbl["EV vs market (bp)"] = ((ef_int - contracts["close"].values) * 100).round(1)
    tbl["std internal (bp)"] = (np.sqrt(p_int @ (fp_int - ef_int) ** 2) * 100).round(1)
    tbl["std market (bp)"] = (np.sqrt(p_mkt @ (fp_mkt - ef_mkt) ** 2) * 100).round(1)
    st.dataframe(tbl, hide_index=True, width="stretch", height=min(500, 38 + 35 * len(tbl)))
    st.caption("Positive EV = internal distribution expects the contract to trade higher (lower rate) than the market. Market-tree E[F] should match the close (bootstrap consistency check).")

    # meeting-level rates
    st.subheader("Rate after each meeting — internal vs market")
    rows = []
    for m in range(n_m):
        r_int = spot + (tree_int[[f"m{k + 1}" for k in range(m + 1)]].sum(axis=1) * p_int).sum() / 100
        r_mkt = spot + np.sum(market_steps[: m + 1]) / 100
        rows.append(dict(meeting=str(mts.iloc[m]["date"].date()), internal=round(r_int, 3), market=round(r_mkt, 3), gap_bp=round((r_int - r_mkt) * 100, 1)))
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

    # --- structures -----------------------------------------------------------
    st.subheader("Structures on one EV scale")
    ci = st.selectbox("Contract for the structures", list(contracts["contract"]), index=min(1, len(contracts) - 1))
    idx = list(contracts["contract"]).index(ci)
    rate_int = 100 - fp_int[:, idx]; rate_mkt = 100 - fp_mkt[:, idx]
    r_now = 100 - float(contracts.loc[idx, "close"])
    sd_mkt_bp = float(np.sqrt(p_mkt @ (rate_mkt - (p_mkt @ rate_mkt)) ** 2) * 100)
    sd_int_bp = float(np.sqrt(p_int @ (rate_int - (p_int @ rate_int)) ** 2) * 100)
    mean_gap_bp = float((p_int @ rate_int - r_now) * 100)
    k_atm = round(r_now * 4) / 4
    straddle_fair = float(p_mkt @ np.abs(rate_mkt - k_atm)) * 100  # expectation under the market tree
    c1, c2, c3 = st.columns(3)
    wing = c2.number_input("Strangle / RR wing distance (bp)", value=25.0, min_value=5.0)
    strikes = dict(atm=k_atm, up=k_atm + wing / 100, dn=k_atm - wing / 100)
    strangle_fair = float(p_mkt @ (np.maximum(rate_mkt - strikes["up"], 0) + np.maximum(strikes["dn"] - rate_mkt, 0))) * 100
    prem_str = c1.number_input("ATM straddle premium (bp, market)", value=float(round(straddle_fair, 1)), min_value=0.0,
                               help="defaults to the expected payoff under the market-implied tree (fair, no vol premium)")
    prem_strangle = c3.number_input("Strangle premium (bp, market)", value=float(round(strangle_fair, 1)), min_value=0.0,
                                    help="defaults to the expected payoff under the market-implied tree")
    st.caption(f"Market-tree fair values: straddle {straddle_fair:.1f} bp, strangle {strangle_fair:.1f} bp; market std of the contract rate {sd_mkt_bp:.1f} bp, internal {sd_int_bp:.1f} bp, mean gap {mean_gap_bp:+.1f} bp. "
               "Type the dealer quote to replace the fair value — the difference is the premium you pay for the shape.")
    fly_ok = idx + 2 < len(contracts)

    structs = {
        "Long future (receive)": [dict(type="linear", strike=r_now, qty=-1)],
        "Short future (pay)": [dict(type="linear", strike=r_now, qty=+1)],
        "Long ATM straddle": [dict(type="call", strike=strikes["atm"], qty=1, premium_bp=prem_str / 2), dict(type="put", strike=strikes["atm"], qty=1, premium_bp=prem_str / 2)],
        "Short ATM straddle": [dict(type="call", strike=strikes["atm"], qty=-1, premium_bp=prem_str / 2), dict(type="put", strike=strikes["atm"], qty=-1, premium_bp=prem_str / 2)],
        f"Long strangle ±{wing:.0f}": [dict(type="call", strike=strikes["up"], qty=1, premium_bp=prem_strangle / 2), dict(type="put", strike=strikes["dn"], qty=1, premium_bp=prem_strangle / 2)],
        f"Short strangle ±{wing:.0f}": [dict(type="call", strike=strikes["up"], qty=-1, premium_bp=prem_strangle / 2), dict(type="put", strike=strikes["dn"], qty=-1, premium_bp=prem_strangle / 2)],
        "Risk reversal: long rate-up wing / short rate-down wing": [dict(type="call", strike=strikes["up"], qty=1, premium_bp=prem_strangle / 2), dict(type="put", strike=strikes["dn"], qty=-1, premium_bp=prem_strangle / 2)],
        "Risk reversal: long rate-down wing / short rate-up wing": [dict(type="put", strike=strikes["dn"], qty=1, premium_bp=prem_strangle / 2), dict(type="call", strike=strikes["up"], qty=-1, premium_bp=prem_strangle / 2)],
    }
    results = []
    for name, legs in structs.items():
        r = kelly.evaluate_structure(name, legs, p_int, rate_int)
        results.append(r)
    # meeting swap on the first meeting in the tree
    m0_int = tree_int["m1"].values; m0_mkt = market_steps[0]
    for name, sign in (("Meeting swap: pay (long step)", 1), ("Meeting swap: receive (short step)", -1)):
        pnl = sign * (m0_int - m0_mkt)
        results.append(dict(structure=name, **E.kelly_on_pnl(p_int, pnl)))
    if fly_ok:
        r1, r2, r3 = (100 - fp_int[:, idx], 100 - fp_int[:, idx + 1], 100 - fp_int[:, idx + 2])
        now = [100 - contracts.loc[idx + k, "close"] for k in range(3)]
        fly_now = now[0] - 2 * now[1] + now[2]
        fly_scn = r1 - 2 * r2 + r3
        for name, sign in ((f"Long fly {contracts.loc[idx, 'contract']}/{contracts.loc[idx + 1, 'contract']}/{contracts.loc[idx + 2, 'contract']} (long price fly)", -1),
                           ("Short fly (short price fly)", 1)):
            pnl = sign * (fly_scn - fly_now) * 100
            results.append(dict(structure=name, **E.kelly_on_pnl(p_int, pnl)))
    res_df = pd.DataFrame([{k: v for k, v in r.items() if k != "pnl"} for r in results])
    res_df = res_df.replace([np.inf], np.nan)
    res_df = res_df.round({"ev_bp": 1, "max_loss_bp": 1, "max_gain_bp": 1, "p_profit": 2, "kelly": 2, "half_kelly": 2})
    res_df = res_df.sort_values("ev_bp", ascending=False)
    st.dataframe(res_df, hide_index=True, width="stretch", height=min(560, 38 + 35 * len(res_df)))
    st.caption("P&L in bp of the contract rate per unit; Kelly = fraction of the loss budget to commit (loss-normalised returns); half-Kelly is the desk size before Part-III limits; blank Kelly = no losing scenario in the tree (premium too cheap to be real). Option premiums are manual (no public STIR vol surface).")

    best = res_df.iloc[0]["structure"]
    best_r = next(r for r in results if r["structure"] == best)
    fig = go.Figure()
    order = np.argsort(rate_int)
    fig.add_trace(go.Bar(x=[f"{(x - r_now) * 100:+.0f}" for x in rate_int[order]], y=best_r["pnl"][order], marker_color=[C.GREEN if v >= 0 else C.RED for v in best_r["pnl"][order]], name="P&L bp"))
    fig.add_trace(go.Scatter(x=[f"{(x - r_now) * 100:+.0f}" for x in rate_int[order]], y=p_int[order] * 100, yaxis="y2", name="internal prob %", line=dict(color=C.BRONZE)))
    fig.update_layout(yaxis2=dict(overlaying="y", side="right", title="prob %"), xaxis_title="contract rate change vs today (bp)")
    st.plotly_chart(C.plotly_layout(fig, height=320, title=f"P&L by scenario — {best}"), width="stretch")

    # --- leg choice -----------------------------------------------------------
    st.subheader("Choosing the leg (§2.4)")
    c1, c2, c3 = st.columns(3)
    loss_budget = c1.number_input("Loss budget per trade ($k)", value=750.0, min_value=10.0)
    usd_bp = c2.number_input(f"{C.FAMILY_META[fam]['ccy']} per bp per lot", value=float(C.FAMILY_META[fam]["usd_per_bp"]))
    tol = c3.number_input("Desk tolerance for a delta-one loss at the event ($k)", value=500.0, min_value=10.0)
    mean_flag = abs(mean_gap_bp) >= max(5.0, 0.33 * sd_mkt_bp)
    width_ratio = sd_int_bp / sd_mkt_bp if sd_mkt_bp > 0 else np.nan
    shape_flag = np.isfinite(width_ratio) and abs(width_ratio - 1) >= 0.2
    d1 = next(r for r in results if r["structure"].startswith("Long future" if mean_gap_bp < 0 else "Short future"))
    lots = (d1["half_kelly"] * loss_budget * 1000 / (abs(d1["max_loss_bp"]) * usd_bp)) if d1["max_loss_bp"] < 0 and np.isfinite(d1["half_kelly"]) else 0.0
    d1_worst = lots * abs(d1["max_loss_bp"]) * usd_bp / 1000
    rows = [("Mean mispriced (|E_int − market| ≥ max(5bp, ⅓ market std))", mean_flag, f"gap {mean_gap_bp:+.1f} bp, market std {sd_mkt_bp:.1f} bp"),
            ("Width/skew mispriced (internal std / market std off by ≥ 20%)", shape_flag, f"ratio {C.fmt(width_ratio, 2)}"),
            ("Half-Kelly delta-one loss at the event exceeds tolerance", d1_worst > tol, f"{lots:.0f} lots → worst {d1_worst:,.0f} $k vs tolerance {tol:,.0f} $k")]
    st.table(pd.DataFrame([dict(test=t, result=("yes" if f else "no"), detail=dd) for t, f, dd in rows]))
    if mean_flag and not shape_flag and d1_worst <= tol:
        verdict = "Delta-one — meeting swap or futures. The market has the right shape, the wrong centre."
    elif shape_flag and not mean_flag:
        verdict = "STIR options — straddle / strangle / wings. The market has the right centre, the wrong shape."
    elif mean_flag and shape_flag:
        verdict = "Risk reversal or skewed strangle, sized off the full tree — compounding edge."
    elif d1_worst > tol:
        verdict = "Same view, can't hold the linear size → switch to options: the defined premium collapses the loss to a known number."
    else:
        verdict = "No material mispricing in mean or shape → no trade from this tree; revisit after the next release."
    st.markdown(f"**Verdict:** {verdict}")
    st.markdown("Consensus-trade caution: if positioning already sits heavily on the same side as the mean view, prefer the defined-loss options leg over sizing up delta-one.")
    C.download_state(["tree_probs", "width_mkt"], "Download tree inputs (JSON)", "g3_tree.json")
    C.upload_state("Upload tree inputs (JSON)", key="upload_tree")
