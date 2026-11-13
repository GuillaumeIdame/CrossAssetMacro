"""§2.1–2.5 — Sub-strategies: narrative lifecycle, carry basket, short vol, leg choice, trade card + Kelly."""

import numpy as np
import pandas as pd
import streamlit as st

from datahub import kelly, stats, ui

from . import common, data, factors, positioning, regime, valuation

CONVICTION_WEIGHTS = {"narrative state": 25, "macro alignment": 15, "valuation residual": 15, "positioning": 15,
                      "catalyst quality": 10, "regime consistency": 10, "liquidity": 5, "vol cost": 5}
PLAYBOOK = {
    "Emerging": "Small initial risk; buy convexity while vol lags the story.",
    "Dominant": "Full-size delta-one; trail invalidation with the driver, not the price.",
    "Accelerating": "Hold; harvest partial profits into vol richness; no adds at stretch.",
    "Exhausting": "Reduce; switch to defined-risk options; write the reversal scenario.",
    "Competing": "Smallest book; pay for optionality on resolution.",
}


def lifecycle_table(df: pd.DataFrame) -> pd.DataFrame:
    fac = factors.build_factors(df)
    val = valuation.valuation_table(df, 60).set_index("ccy")
    pos = positioning.positioning_table().set_index("ccy")
    opt = positioning.options_table(df)
    rets = data.returns(df)
    g10 = rets[data.G10]
    quad = regime.quadrant_series(regime.axes(df)["scores"])
    unstable = bool(quad.iloc[-1]["migrating"]) if not quad.empty else False
    rows = []
    for c in data.CCYS:
        r = rets[c].dropna()
        m5, m20, m60 = r.iloc[-5:].sum(), r.iloc[-20:].sum(), r.iloc[-60:].sum()
        consistent = len({np.sign(m5), np.sign(m20), np.sign(m60)}) == 1
        steepening = consistent and abs(m5) / 5 > abs(m20) / 20
        breadth = float((np.sign(g10.iloc[-20:].sum()) == np.sign(m20)).mean())
        eps20 = fac["eps"][c].rolling(20).sum() if c in fac["eps"] else pd.Series(dtype=float)
        eps_z = stats.last_z(eps20.dropna(), 504) if not eps20.empty else np.nan
        comp = val.loc[c, "composite_z"] if c in val.index else np.nan
        dis = bool(val.loc[c, "disagreement"]) if c in val.index else False
        pz = pos.loc[c, "z"] if c in pos.index else np.nan
        crowded = bool(pos.loc[c, "crowded"]) if c in pos.index else False
        rr_chg = opt.loc[c, "rr_5d_change"] if c in opt.index else np.nan
        against_val = np.isfinite(eps_z) and np.isfinite(comp) and abs(eps_z) >= 1 and np.sign(eps_z) != np.sign(comp)
        if unstable or (dis and not consistent):
            state = "Competing"
        elif crowded or (np.isfinite(pz) and abs(pz) >= 1.5 and not steepening) or (np.isfinite(rr_chg) and abs(rr_chg) > 0.5 and abs(m5) < abs(m20) / 4):
            state = "Exhausting"
        elif steepening and ((np.isfinite(rr_chg) and rr_chg * np.sign(m20) > 0) or (np.isfinite(pz) and pz * np.sign(m20) > 0.5)):
            state = "Accelerating"  # needs RR paying up or new longs driving positioning — not momentum alone
        elif consistent and breadth >= 0.6 and (not np.isfinite(pz) or abs(pz) < 1.5):
            state = "Dominant"
        elif against_val or dis:
            state = "Emerging"
        else:
            state = "Competing"
        rows.append(dict(ccy=c, pair=data.PAIR_LABEL[c], state=state, mom_5d=100 * m5, mom_20d=100 * m20, mom_60d=100 * m60, consistent=consistent,
                         breadth=breadth, eps_z=eps_z, val_z=comp, disagreement=dis, pos_z=pz, crowded=crowded, rr_5d=rr_chg, playbook=PLAYBOOK[state]))
    return pd.DataFrame(rows)


def carry_basket(df: pd.DataFrame, gate: str) -> pd.DataFrame:
    pos = positioning.positioning_table().set_index("ccy")
    opt = positioning.options_table(df)
    rows = []
    for c in data.G10:
        cd = common.last(data.carry_diff(df, c))
        sig = opt.loc[c, "atm_1m"] if c in opt.index and np.isfinite(opt.loc[c, "atm_1m"]) else opt.loc[c, "rv60"]
        pz = pos.loc[c, "z"] if c in pos.index else np.nan
        rr = opt.loc[c, "rr25_1m"] if c in opt.index else np.nan
        h_crowd = min(0.5, max(0.0, (abs(pz) - 1.5)) * 0.5) if np.isfinite(pz) else 0.0
        # skew haircut when crash insurance is expensive against the position: long carry ccy hurt by RR paying for its downside
        h_skew = 0.0
        if np.isfinite(rr) and np.isfinite(cd):
            pain = -rr if cd > 0 else rr
            h_skew = min(0.5, max(0.0, pain) * 0.25)
        rows.append(dict(ccy=c, carry_pp=cd, sigma=sig, carry_over_vol=cd / sig if sig and np.isfinite(sig) and sig > 0 else np.nan,
                         pos_z=pz, h_crowd=h_crowd, h_skew=h_skew, sigma_source="IV typed" if (c in opt.index and np.isfinite(opt.loc[c, "atm_1m"])) else "RV60 proxy"))
    t = pd.DataFrame(rows).dropna(subset=["carry_over_vol"])
    if t.empty:
        return t
    rank = t["carry_over_vol"].rank() - (len(t) + 1) / 2
    raw = rank * (1 - t["h_crowd"]) * (1 - t["h_skew"])
    gross = {"Healthy": 1.0, "Fragile": 0.5, "Unwinding": 0.0, "Low-vol rotation": 1.0}[gate]
    t["weight"] = raw / raw.abs().sum() * gross if raw.abs().sum() > 0 else 0.0
    return t.sort_values("weight", ascending=False)


def leg_choice(row: pd.Series, opt_row: pd.Series) -> str:
    vrp = opt_row.get("vrp", np.nan); vrp_d = opt_row.get("vrp_5d_change", np.nan); rr = opt_row.get("rr25_1m", np.nan)
    st_ = row["state"]
    if row["crowded"] or st_ == "Exhausting":
        return "Switch delta-one to defined-risk options (risk reversal, strangle) — amplified event gaps; linear can't be sized to survive it."
    if st_ == "Emerging" and (not np.isfinite(vrp) or vrp <= 0):
        return "Long gamma / cheap optionality — own the move before the crowd and the vol market catch up."
    if st_ == "Dominant" and (not np.isfinite(vrp) or vrp <= 1.0):
        return "Delta-one — bank the drift; no convexity premium paid unnecessarily."
    if np.isfinite(vrp) and vrp > 1.0 and (not np.isfinite(vrp_d) or vrp_d <= 0):
        return "Delta-one — don't pay rich vol for a view already held with conviction (VRP rich and stable/falling)."
    return "Mixed read — size small; prefer the defined-loss leg until the lifecycle resolves."


def render():
    ui.step("7", "Sub-strategies — narrative lifecycle, carry basket, short vol, leg choice", "Diagnosed, not felt: each state has a proxy signature and a playbook.", "proxy")
    m = data.load_all(); df = m["df"]
    lt = lifecycle_table(df)
    st.markdown("### 2.1 Narrative lifecycle" + " " + ui.badge("proxy"), unsafe_allow_html=True)
    st.dataframe(common.dfmt(lt.drop(columns=["ccy"])), use_container_width=True, hide_index=True)
    st.caption("Signature: ε moving against valuation + disagreement → Emerging; breadth ≥ 0.6, 5/20/60D consistent, |pos z| < 1.5 → Dominant; momentum steepening, RR paying up → Accelerating; crowded / RR extreme while spot stalls → Exhausting; quadrant migrating or persistent disagreement → Competing. Positioning and RR enter only when available (CFTC / typed surface).")

    st.markdown("### 2.2 Long carry basket")
    gate = st.selectbox("Carry-Health gate", ["Healthy", "Fragile", "Unwinding", "Low-vol rotation"], key="fx_carry_gate",
                        help="Healthy → full budget; fragile → half; unwinding → zero; low-vol rotation → full with tighter drawdown trigger. Read the Carry Health axis on page 6.")
    cb = carry_basket(df, gate)
    if cb.empty:
        st.info("Carry basket needs short-rate differentials.")
    else:
        st.dataframe(common.dfmt(cb), use_container_width=True, hide_index=True)
        st.plotly_chart(common.bars(cb.set_index("ccy")["weight"], "Basket weights (Σ|w| = gross budget)"), use_container_width=True)
    st.caption("w ∝ rank(c/σ)·(1−h_crowd)·(1−h_skew). c = short-rate differential (forward-implied carry net of basis when a feed exists), σ = 1M IV if typed else 60D realised. Select on carry/vol, never raw carry. Funding-side risk (JPY/CHF positioning and their meetings) is first-class — see page 4.")

    st.markdown("### 2.3 Short FX volatility sleeve")
    opt = positioning.options_table(df)
    sv = opt[["atm_1m", "rv20", "rv60", "e_rv", "vrp", "vrp_5d_change", "rr25_1m", "bf25_1m"]].copy()
    sv["verdict"] = ["sell (wide, stable/widening)" if np.isfinite(v) and v > 1.5 and (not np.isfinite(d) or d >= -0.3) else
                     "no — wide but collapsing" if np.isfinite(v) and v > 1.5 else "no premium" if np.isfinite(v) else "needs IV"
                     for v, d in zip(sv["vrp"], sv["vrp_5d_change"])]
    st.dataframe(common.dfmt(sv.reset_index()), use_container_width=True, hide_index=True)
    st.caption("VRP = IV_1M − E[RV], E[RV] = 0.6·RV20 + 0.4·RV60. Core: delta-hedged 1M ATM straddles/strangles on the 3–5 widest-VRP pairs; mandatory tail buy-back 20–30% of premium into 10Δ wings; no net short vega in > 3 pairs sharing a funding currency. One crash, two expressions: carry and short vol share a single crash budget (§2.4).")

    st.markdown("### 2.5 Delta-one vs options — the FX leg")
    ccy = st.selectbox("Pair", data.CCYS, format_func=lambda c: data.PAIR_LABEL[c], key="fx_leg_ccy")
    row = lt.set_index("ccy").loc[ccy]
    st.success(f"{data.PAIR_LABEL[ccy]} — state **{row['state']}** → {leg_choice(row, opt.loc[ccy])}")
    st.caption("Question: can a linear position survive the catalyst, or does positioning turn it into a gap? Tells: lifecycle stage; VRP level and direction; crowding flag / event-amplification (page 4); spot/vol correlation sign flip; CTA distance-to-trigger (Thematic app).")

    st.markdown("### Trade card — mandatory fields → scenario set → ½-Kelly × conviction")
    cards = common.session_list("fx_trade_cards")
    with st.form("fx_trade_card"):
        c1, c2, c3 = st.columns(3)
        pair = c1.selectbox("Pair", data.CCYS, format_func=lambda c: data.PAIR_LABEL[c])
        direction = c2.selectbox("Direction (on the foreign currency)", ["long", "short"])
        instrument = c3.selectbox("Instrument", ["spot/forward", "futures", "vanilla call", "vanilla put", "risk reversal", "strangle"])
        thesis = st.text_area("Thesis — narrative, transmission map, factor loaded (Dollar or residual)")
        catalyst = st.text_input("Catalyst and horizon")
        c4, c5, c6 = st.columns(3)
        entry = c4.number_input("Entry", value=float(common.last(data.spot(df, pair))), format="%.5f")
        target = c5.number_input("Target", value=0.0, format="%.5f")
        stop = c6.number_input("Stop (thesis invalidation, REER-checked)", value=0.0, format="%.5f")
        invalidation = st.text_input("Invalidation, written so a colleague could enforce it")
        key_risk = st.text_input("Key risk: worst scenario, correlation to the book, does the crowd share it?")
        st.markdown("**Checklist (0 = fails, 1 = passes)** — weights 25/15/15/15/10/10/5/5")
        cols = st.columns(len(CONVICTION_WEIGHTS))
        checks = {k: c.slider(k, 0.0, 1.0, 0.5, 0.1) for c, k in zip(cols, CONVICTION_WEIGHTS)}
        st.markdown("**Scenario set (3–5), P&L in % of notional**")
        sc = st.data_editor(pd.DataFrame({"scenario": ["base", "bull", "bear", "tail"], "prob": [0.45, 0.25, 0.2, 0.1], "pnl_pct": [2.0, 5.0, -2.0, -6.0]}),
                            num_rows="dynamic", key="fx_scn")
        c7, c8 = st.columns(2)
        stomach = c7.number_input("Stomachable loss, $", value=1_000_000.0, step=100_000.0)
        bankroll = c8.number_input("Bankroll the Kelly fraction applies to, $ (capital at risk, not NAV)", value=5_000_000.0, step=500_000.0)
        submitted = st.form_submit_button("Evaluate and save card")
    if submitted:
        p = sc["prob"].astype(float).tolist(); r = (sc["pnl_pct"].astype(float) / 100).tolist()
        k = kelly.kelly_fraction(p, r)
        conviction = sum(CONVICTION_WEIGHTS[n] * v for n, v in checks.items()) / 100
        size_frac = 0.5 * k["f_star"] * conviction if np.isfinite(k["f_star"]) else 0.0
        worst = min(r)
        notional_cap = stomach / abs(worst) if worst < 0 else np.inf
        failing = sum(1 for v in checks.values() if v < 0.5)
        card = dict(pair=data.PAIR_LABEL[pair], ccy=pair, direction=direction, instrument=instrument, thesis=thesis, catalyst=catalyst,
                    entry=entry, target=target, stop=stop, invalidation=invalidation, key_risk=key_risk, conviction=conviction,
                    kelly=k["f_star"], half_kelly=k["half"], ev_pct=100 * k["ev"], size_fraction=size_frac,
                    notional_usd=float(min(size_frac * bankroll, notional_cap)) if np.isfinite(size_frac) else 0.0,
                    stomach_cap_usd=notional_cap, flagged=failing >= 2, created=str(pd.Timestamp.now())[:16])
        cards.append(card)
        st.success(f"EV {100 * k['ev']:+.2f}% of notional · Kelly leverage f* {k['f_star']:.2f}× bankroll · ½-Kelly × conviction ({conviction:.2f}) = {size_frac:.2f}× → "
                   f"notional ${min(size_frac * bankroll, notional_cap):,.0f} (stomach cap ${notional_cap:,.0f})" + (" · FLAGGED: ≥ 2 checklist blocks failing → reduced Kelly fraction and mandatory post-mortem" if failing >= 2 else ""))
    if cards:
        st.dataframe(common.dfmt(pd.DataFrame(cards)), use_container_width=True, hide_index=True)
        if st.button("Clear cards", key="fx_clear_cards"):
            st.session_state["fx_trade_cards"] = []; st.rerun()
    common.json_io("fx_trade_cards", "trade cards")
    st.caption("Notional = ½f*·conviction × bankroll, capped by stomachable loss ÷ worst-scenario loss (the cap binds when tighter than Kelly). Scenario P&L is in % of notional, so f* is a leverage on the bankroll. Half-Kelly is the geometric-growth-consistent haircut for estimation error in p.")
