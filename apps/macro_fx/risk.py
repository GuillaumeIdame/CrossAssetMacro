"""§3.1–3.6 — Risk: sizing checks, limits, factor exposure $/1σ, shock grid, stress replay, CED, theta budget."""

import numpy as np
import pandas as pd
import streamlit as st

from datahub import stats, ui

from . import common, data, factors, positioning

VOL_BUDGET = 5_000_000
SHOCK_FACTORS = {"SPX": ("spx", "price"), "DXY": ("dxy", "price"), "US 2Y": ("ust2", "level"), "2s10s": ("curve", "level"),
                 "VIX": ("vix", "level"), "MOVE": ("move", "level"), "Brent": ("brent", "price"), "Gold": ("gold", "price")}
SHOCK_GRID = {"US 2Y": [0.10, 0.25, 0.35, 0.50, -0.10, -0.25, -0.35, -0.50], "SPX": [-0.05, -0.10, -0.20], "Brent": [0.15, -0.15], "DXY": [0.02, -0.02]}
EPISODES = ["COVID Mar-2020", "Fed hiking 2022", "UK mini-budget Sep-2022", "Aug-2024 carry unwind", "Apr-2025 tariffs", "BoJ Jul-2024 hike"]


def book_positions() -> pd.DataFrame:
    cards = st.session_state.get("fx_trade_cards", [])
    if not cards:
        return pd.DataFrame(columns=["ccy", "pair", "direction", "notional_usd"])
    b = pd.DataFrame(cards)[["ccy", "pair", "direction", "notional_usd"]].copy()
    b["signed"] = np.where(b["direction"] == "long", 1, -1) * b["notional_usd"].astype(float)
    return b.groupby(["ccy", "pair"], as_index=False)["signed"].sum()


def factor_changes(df: pd.DataFrame) -> pd.DataFrame:
    out = {}
    for name, (k, mode) in SHOCK_FACTORS.items():
        if k == "curve":
            if "ust2" in df.columns and "ust10" in df.columns:
                out[name] = (df["ust10"] - df["ust2"]).diff()
        elif k in df.columns:
            s = df[k].astype(float)
            out[name] = np.log(s).diff() if mode == "price" else s.diff()
    return pd.DataFrame(out)


def render():
    ui.step("8", "Risk — sizing, limits, factor exposure, shocks, stress, drawdown", "The Dollar-factor beta is the headline number: the exposure most likely to build unintentionally across 'idiosyncratic' trades.", "proxy")
    m = data.load_all(); df = m["df"]
    book = book_positions()
    if book.empty:
        st.info("No trade cards yet (page 7). Showing the per-pair exposure matrix so the risk map is readable before the first trade.")
    rets = data.returns(df)
    fac = factors.build_factors(df)["factors"]
    fc = factor_changes(df)

    # --- book P&L series (daily $) ---
    if not book.empty:
        pnl = sum(row["signed"] * rets[row["ccy"]].fillna(0) for _, row in book.iterrows())
        pnl = pnl.dropna()
        c1, c2, c3, c4 = st.columns(4)
        gross = book["signed"].abs().sum(); net = book["signed"].sum()
        vol = pnl.iloc[-60:].std() * np.sqrt(252)
        c1.metric("Gross, $", f"{gross:,.0f}"); c2.metric("Net USD-short (Σ foreign longs), $", f"{net:,.0f}"); c3.metric("Realised book vol (60D, ann.), $", f"{vol:,.0f}")
        c4.metric("vs $5M budget", f"{100 * vol / VOL_BUDGET:.0f}%")
    else:
        pnl = pd.Series(dtype=float)

    st.markdown("### Factor exposure — $ per 1σ daily move (60D univariate)")
    rows = []
    targets = {r["pair"]: r["signed"] * rets[r["ccy"]] for _, r in book.iterrows()} if not book.empty else {data.PAIR_LABEL[c]: 1_000_000 * rets[c] for c in data.G10}
    label = "book" if not book.empty else "$1M long each pair"
    for name in fc.columns:
        for pname, y in targets.items():
            b = stats.beta_dollar_per_sigma(y.dropna(), fc[name].dropna(), 60)
            rows.append(dict(position=pname, factor=name, dollar_per_sigma=b["dollar_per_sigma"], beta=b["beta"], r2=b["r2"]))
    ex = pd.DataFrame(rows)
    if not ex.empty:
        piv = ex.pivot(index="position", columns="factor", values="dollar_per_sigma")
        piv.loc["BOOK TOTAL"] = piv.sum()
        st.dataframe(common.dfmt(piv, 0), use_container_width=True)
        st.caption(f"Rows: {label}. Macro factors each alone, 60D. Rates enter as level (2Y) + slope (2s10s); never 2y + 10y + 2s10s together.")
    # Dollar / Carry / Mom structure betas
    if not fac.empty:
        srows = []
        for pname, y in targets.items():
            r = {}
            for f in fac.columns:
                b = stats.beta_dollar_per_sigma(y.dropna(), fac[f].dropna(), 60)
                r[f] = b["dollar_per_sigma"]
            srows.append(dict(position=pname, **r))
        sb = pd.DataFrame(srows).set_index("position"); sb.loc["BOOK TOTAL"] = sb.sum()
        st.markdown("**FX structure factors — Dollar / Carry / Momentum ($/1σ)**")
        st.dataframe(common.dfmt(sb, 0), use_container_width=True)
        if not book.empty:
            st.metric("Headline: book Dollar-factor exposure, $/1σ", f"{sb.loc['BOOK TOTAL', 'F_USD']:,.0f}")

    st.markdown("### Limits (illustrative levels)")
    pos = positioning.positioning_table().set_index("ccy")
    if not book.empty:
        pair_share = (book.set_index("pair")["signed"].abs() / max(book["signed"].abs().sum(), 1))
        crowded_share = sum(abs(r["signed"]) for _, r in book.iterrows() if r["ccy"] in pos.index and bool(pos.loc[r["ccy"], "crowded"])) / max(book["signed"].abs().sum(), 1)
        lim = pd.DataFrame([
            dict(limit="Single pair net ≤ 30% of book vol budget (proxy: share of gross)", level=f"{100 * pair_share.max():.0f}%", ok=pair_share.max() <= 0.30),
            dict(limit="Net USD factor delta ≤ 50% (proxy: |net| / gross)", level=f"{100 * abs(book['signed'].sum()) / max(book['signed'].abs().sum(), 1):.0f}%", ok=abs(book["signed"].sum()) / max(book["signed"].abs().sum(), 1) <= 0.5),
            dict(limit="Crowded-position share ≤ 25% of gross", level=f"{100 * crowded_share:.0f}%", ok=crowded_share <= 0.25),
            dict(limit="Net short vega: hard cap; zero into flagged meetings in funding currencies", level="manual (theta table)", ok=True),
            dict(limit="Combined crash budget ≤ 1.5 × monthly vol budget", level="see stress replay", ok=True),
            dict(limit="Liquidity ≤ 3 days' prudent volume per leg", level="manual", ok=True),
        ])
        st.dataframe(lim, use_container_width=True, hide_index=True)

    st.markdown("### Shock grid (propagated shock → factor → FX → position → portfolio)")
    amplify = st.checkbox("Positioning-amplified variant (crowded pairs' betas × 1.5)", value=False, key="fx_amp")
    if not book.empty and not fc.empty:
        grows = []
        for fname, shocks in SHOCK_GRID.items():
            if fname not in fc.columns:
                continue
            for s in shocks:
                total = 0.0
                for _, r in book.iterrows():
                    b = stats.beta_dollar_per_sigma(rets[r["ccy"]].dropna(), fc[fname].dropna(), 60)
                    beta = b["beta"] if np.isfinite(b["beta"]) else 0.0
                    if amplify and r["ccy"] in pos.index and bool(pos.loc[r["ccy"], "crowded"]):
                        beta *= 1.5
                    total += r["signed"] * beta * s
                unit = "bp" if fname == "US 2Y" else "%"
                grows.append(dict(factor=fname, shock=f"{s * (100 if unit == 'bp' else 100):+.0f}{unit}", pnl_usd=total))
        g = pd.DataFrame(grows)
        st.dataframe(common.dfmt(g, 0), use_container_width=True, hide_index=True)
    else:
        st.caption("Add trade cards to populate the grid.")
    st.caption("Quadrant-conditional variants (the quadrant selects the co-movement matrix) and full option repricing under surface shifts require the options book — enter it in the theta table; betas here are unconditional 60D.")

    st.markdown("### Stress library — historical replay on today's exposures")
    srows = []
    for ep in EPISODES:
        a, b = common.window_dates(ep)
        w = rets.loc[a:b]
        if w.empty:
            srows.append(dict(episode=ep, window=f"{a}→{b}", status="outside loaded history")); continue
        moves = w.sum()
        if not book.empty:
            p = sum(r["signed"] * moves.get(r["ccy"], 0.0) for _, r in book.iterrows())
            srows.append(dict(episode=ep, window=f"{a}→{b}", status="ok", book_pnl_usd=p, worst_pair=moves.idxmin(), worst_move_pct=100 * moves.min()))
        else:
            srows.append(dict(episode=ep, window=f"{a}→{b}", status="ok", book_pnl_usd=np.nan, worst_pair=moves.idxmin(), worst_move_pct=100 * moves.min()))
    st.dataframe(common.dfmt(pd.DataFrame(srows)), use_container_width=True, hide_index=True)
    st.caption("Every scenario should also keep the surface shift (ATM, RR, fly), cross-asset moves and duration; the public replay carries spot only. Narrative scenarios (de-dollarisation, Hormuz, fiscal-dominance switch…) are transmission maps typed in the theme tracker.")

    st.markdown("### Drawdown control — CED and the ladder")
    if len(pnl) > 60:
        cum = pnl.cumsum()
        dd = []
        for i in range(21, len(cum)):
            path = cum.iloc[i - 21:i]
            dd.append((path.cummax() - path).max())
        dd = pd.Series(dd)
        q = dd.quantile(0.9)
        ced = dd[dd >= q].mean()
        c1, c2, c3 = st.columns(3)
        c1.metric("CED (E[DD | DD ≥ q0.9], 1M paths), $", f"{ced:,.0f}")
        c2.metric("Current drawdown from peak, $", f"{(cum.cummax() - cum).iloc[-1]:,.0f}")
        c3.metric("Worst 1M drawdown in history, $", f"{dd.max():,.0f}")
    ladder = pd.DataFrame([dict(trigger="−$5M", action="review and gross-cut option"), dict(trigger="−$7.5M", action="mandatory de-gross of risk-premia sleeves"),
                           dict(trigger="−$10M", action="flatten ex-insurance"), dict(trigger="daily ±$1M / ±$2.5M / ±$5M", action="same-day attribution / factor review / risk-committee note")])
    st.dataframe(ladder, use_container_width=True, hide_index=True)

    st.markdown("### Theta budget (§3.5) — long-option lines")
    theta_default = pd.DataFrame({"line": ["example: EUR 1M 25Δ call"], "premium_usd": [0.0], "theta_usd_day": [0.0], "gamma_usd_per_1pct": [0.0], "is_insurance_wing": [False]})
    th = st.data_editor(pd.DataFrame(st.session_state.get("fx_theta", theta_default.to_dict(orient="list"))), num_rows="dynamic", key="fx_theta_editor", use_container_width=True)
    st.session_state["fx_theta"] = th.to_dict(orient="list")
    nav = st.number_input("NAV, $ (for bp/day)", value=100_000_000.0, step=10_000_000.0, key="fx_nav_usd")
    theta = th["theta_usd_day"].astype(float).abs().sum()
    bp = 1e4 * theta / nav if nav else np.nan
    eff = (th["gamma_usd_per_1pct"].astype(float).sum() / theta) if theta else np.nan
    c1, c2, c3 = st.columns(3)
    c1.metric("|θ_book|, bp NAV/day", f"{bp:.1f}"); c2.metric("Γ/|θ| efficiency", "n/a" if not np.isfinite(eff) else f"{eff:.2f}")
    c3.metric("Status", "operating 5–10" if bp <= 10 else ("SOFT BREACH (>10)" if bp <= 12 else "HARD BREACH (>12)"))
    st.caption("Soft breach: no adds; lengthen tenor or move from ATM to wings. Hard breach: trim least efficient lines first, never the crash wings bought as insurance. Long-vol lines are exempt from vol targeting.")

    st.markdown("### Cross-book layer (§3.6)")
    st.markdown("- **Pre-event calendar**: the Central Bank app's tier-1 calendar is the house calendar; the event-amplification table (page 4) runs for any exposed pair.\n"
                "- **Factor netting**: rates level/slope, USD, credit and vol exposure summed across the three books before any shock.\n"
                "- **Combined drawdown ladder** on the aggregate $5M book; **stress replay** once per episode across the combined positions.\n"
                "- Crowding overlap read across Macro FX and Macro Thematic; excluded for Central Bank, where a crowded consensus is a caution, not a confirmation.")
