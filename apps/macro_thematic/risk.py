"""§3.1–3.6 — Sizing, exposure, stress, control, theta budget."""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from datahub import stats, ui

from . import data as D
from . import universe as U

BOOK_VOL = 5_000_000.0
FACTORS = {"SPX": ("spx", "price"), "DXY": ("dxy", "price"), "10Y": ("ust10", "level"), "2s10s": ("s2s10", "slope"), "VIX": ("vix", "level"),
           "MOVE": ("move", "level"), "Brent": ("brent", "price"), "Gold": ("gold", "price")}
EPISODES = {
    "Lehman (Sep–Nov 2008)": ("2008-09-12", "2008-11-20"), "2011 US downgrade (Jul–Aug 2011)": ("2011-07-22", "2011-08-10"),
    "Bund tantrum (Apr–Jun 2015)": ("2015-04-17", "2015-06-10"), "2015–16 growth scare (Dec 2015–Feb 2016)": ("2015-12-01", "2016-02-11"),
    "2018 Q4": ("2018-10-01", "2018-12-24"), "Aug-2019": ("2019-07-31", "2019-08-15"), "COVID (Feb–Mar 2020)": ("2020-02-19", "2020-03-23"),
    "Jan-2022 rates shock": ("2022-01-03", "2022-01-28"), "Jun-2022 hike repricing": ("2022-06-01", "2022-06-16"), "Fed hiking 2022 (full year)": ("2022-01-03", "2022-10-21"),
    "UK mini-budget / LDI (Sep–Oct 2022)": ("2022-09-22", "2022-10-12"), "Nov-2022 FCI loosening": ("2022-11-09", "2022-12-01"),
    "Aug-2024 carry unwind": ("2024-07-31", "2024-08-05"), "Apr-2025 tariffs": ("2025-04-02", "2025-04-08"), "1987 crash": ("1987-10-14", "1987-10-20"),
}
PARAMETRIC = {"Equity −10%": dict(SPX=-10), "Equity −20%": dict(SPX=-20), "Rates +35 bp": {"10Y": 35}, "Rates −35 bp": {"10Y": -35}, "Oil +15%": dict(Brent=15),
              "Oil −15%": dict(Brent=-15), "USD +5%": dict(DXY=5), "Vol +10 pts": dict(VIX=10, MOVE=30), "Combined stagflation": {"SPX": -8, "10Y": 30, "Brent": 15, "Gold": 5, "VIX": 8}}
EXAMPLE_BOOK = [
    dict(instrument="s530", label="5s30s steepener", direction="long", size=67_000, size_unit="DV01 $/bp", L_stomach=1_200_000, theme="Stagflation / supply shock", kind="delta-one", premium=0, theta_day=0, gamma=0),
    dict(instrument="brent", label="Brent call spread", direction="long", size=0, size_unit="premium $", L_stomach=400_000, theme="Stagflation / supply shock", kind="long-vol", premium=400_000, theta_day=5_000, gamma=1.2),
    dict(instrument="ust2", label="Long 2Y (receive)", direction="long", size=40_000, size_unit="DV01 $/bp", L_stomach=800_000, theme="Disinflation / soft landing", kind="delta-one", premium=0, theta_day=0, gamma=0),
    dict(instrument="audusd", label="AUD puts", direction="short", size=0, size_unit="premium $", L_stomach=250_000, theme="Trade policy / tariffs", kind="long-vol", premium=250_000, theta_day=3_000, gamma=0.8),
]


def factor_frame(frame):
    out = {}
    for name, (k, mode) in FACTORS.items():
        if mode == "slope":
            s = ((D.series(frame, "ust10") - D.series(frame, "ust2")) * 100).dropna().diff()
        elif mode == "level":
            s = D.series(frame, k).diff() * (100 if k.startswith("ust") else 1)
        else:
            s = np.log(D.series(frame, k)).diff() * 100
        out[name] = s
    return pd.DataFrame(out).dropna(how="all")


def instrument_daily(ins: U.Instrument) -> pd.Series:
    s = ins.series.dropna()
    return s.diff() if ins.mode == "level" else np.log(s).diff() * 100


def position_pnl_per_unit(pos, ins):
    """$ P&L per 1 unit move of the instrument series (bp for level, % for price) for the position as entered."""
    sign = 1 if pos["direction"] == "long" else -1
    if ins.mode == "level":
        if ins.legs is None:
            return -sign * pos["size"]            # receiver gains when yield falls: DV01 $ per bp
        return sign * pos["size"]                 # steepener gains when slope widens
    return sign * pos["size"] / 100.0             # notional $ per 1 %


def render():
    ui.step("§3.1–3.6", "Sizing, exposure, stress, control, theta",
            "Can every line be held through a normal two-week wobble, and does the book survive the tail with its convexity intact?")
    frame, _, _ = D.load_universe()
    univ = U.build(frame)
    if "book" not in st.session_state:
        st.session_state["book"] = [dict(b) for b in EXAMPLE_BOOK]
    st.markdown("#### Book " + ui.badge("manual") + " (example lines pre-filled)", unsafe_allow_html=True)
    opts = list(univ.keys())
    book = pd.DataFrame(st.session_state["book"])
    book = st.data_editor(book, num_rows="dynamic", use_container_width=True, key="book_editor",
                          column_config={"instrument": st.column_config.SelectboxColumn("instrument", options=opts), "direction": st.column_config.SelectboxColumn("direction", options=["long", "short"]),
                                         "size_unit": st.column_config.SelectboxColumn("size_unit", options=["DV01 $/bp", "notional $", "premium $"]),
                                         "kind": st.column_config.SelectboxColumn("kind", options=["delta-one", "long-vol", "short-premium"])})
    book = book.dropna(subset=["instrument"])
    st.session_state["book"] = book.to_dict("records")

    # ---------------- sizing
    st.markdown("#### Sizing — size_$ = L_stomach / |Δ_2w,adv|, book √(ΣL² + 2Σρ^tail L_i L_j) ≤ $5M")
    rows = []
    daily = {}
    for _, p in book.iterrows():
        ins = univ.get(p["instrument"])
        if ins is None:
            continue
        adv = U.adverse_2w_move(ins)
        per_unit = position_pnl_per_unit(p, ins)
        cur_loss = abs(per_unit) * adv if np.isfinite(adv) else np.nan
        max_size = p["L_stomach"] / adv if (np.isfinite(adv) and adv > 0) else np.nan
        if p["kind"] == "long-vol":
            cur_loss = float(p.get("premium", 0) or 0)  # premium-at-risk
            max_size = np.nan
        rows.append(dict(label=p["label"], instrument=ins.label, kind=p["kind"], adv_2w=adv, unit="bp" if ins.mode == "level" else "%", size=p["size"], size_unit=p["size_unit"],
                         loss_2w=cur_loss, L_stomach=p["L_stomach"], ok=bool(np.isfinite(cur_loss) and cur_loss <= p["L_stomach"]), max_size_for_L=max_size, theme=p["theme"]))
        d = instrument_daily(ins) * per_unit
        if p["kind"] == "long-vol":
            d = d * 0  # premium-at-risk lines: path P&L not modelled linearly
        daily[p["label"]] = d
    sz = pd.DataFrame(rows)
    if not sz.empty:
        st.dataframe(sz.style.format({"adv_2w": "{:.1f}", "size": "{:,.0f}", "loss_2w": "{:,.0f}", "L_stomach": "{:,.0f}", "max_size_for_L": "{:,.0f}"}), use_container_width=True, hide_index=True)
        L = sz["loss_2w"].fillna(0).values
        pnl = pd.DataFrame(daily).dropna(how="all").fillna(0)
        if pnl.shape[1] >= 2 and len(pnl) > 120:
            port = pnl.sum(axis=1)
            tail_days = port[port <= port.quantile(0.1)].index
            rho_tail = pnl.loc[tail_days].corr().fillna(0).values
            rho_calm = pnl.iloc[-60:].corr().fillna(0).values
        else:
            rho_tail = rho_calm = np.eye(len(L))
        Lv = np.array([sz["loss_2w"].fillna(0).iloc[i] for i in range(len(L))])
        book_tail = float(np.sqrt(max(Lv @ rho_tail[:len(Lv), :len(Lv)] @ Lv, 0)))
        book_calm = float(np.sqrt(max(Lv @ rho_calm[:len(Lv), :len(Lv)] @ Lv, 0)))
        w = np.abs(Lv); neff = (w.sum() ** 2 / (w ** 2).sum()) if (w ** 2).sum() > 0 else 0
        theme_share = sz.groupby("theme")["loss_2w"].sum() / max(book_tail, 1)
        ui.kpi_row([("Book L (tail ρ)", f"${book_tail/1e6:.2f}M", None, "binding: the worse of tail and placid"), ("Book L (placid ρ)", f"${book_calm/1e6:.2f}M"),
                    ("Budget", "$5.0M", None, "annualised vol book; 2w/1y rule"), ("N_eff", f"{neff:.1f}", None, "≥ 3 required"),
                    ("Max theme share", f"{theme_share.max():.0%}" if len(theme_share) else "n/a", None, "≤ 30% of book vol")])
        if book_tail > BOOK_VOL:
            st.error("Book loss under tail correlation exceeds the $5M envelope: cut size, not the trade.")
        if len(theme_share) and theme_share.max() > 0.30:
            st.warning("Theme concentration above 30%: review from 30%, cut the most crowded / least convex leg at 35–40%.")
        if neff < 3:
            st.warning("N_eff < 3: diversification is credited only at tail correlation.")
    st.dataframe(pd.DataFrame([["High conviction, theme-aligned", "|composite| > 1.5, pillars agree, clear leg", "$1.0–1.5M"], ["Medium", "|composite| 0.8–1.5, some conflict", "$0.5–1.0M"],
                               ["Tactical / event", "Short horizon, single-pillar lead, defined loss preferred", "< $0.5M"]], columns=["Setup", "Screener × Monitor", "L_stomach"]),
                 use_container_width=True, hide_index=True)
    st.caption("Order of constraints: stomach → concentration → crowding haircut → liquidity → drawdown state. Long-vol sleeve sized by premium-at-risk (30–50% of the theme's vol slot), exempt from vol targeting. RC < 0.5 caps thematic gross at 60%.")

    # ---------------- exposure layer
    st.markdown("#### Exposure layer — $ per 1σ day, univariate 60D, β⁻ − β⁺ convexity")
    ff = factor_frame(frame)
    if daily:
        port = pd.DataFrame(daily).dropna(how="all").fillna(0).sum(axis=1)
        erows = []
        for f in ff.columns:
            x = ff[f].dropna()
            b = stats.beta_dollar_per_sigma(port, x, 60)
            df = pd.concat([port, x], axis=1, keys=["p", "x"]).dropna().iloc[-250:]
            up, dn = df[df["x"] > 0], df[df["x"] < 0]
            bu = np.polyfit(up["x"], up["p"], 1)[0] if len(up) > 20 else np.nan
            bd = np.polyfit(dn["x"], dn["p"], 1)[0] if len(dn) > 20 else np.nan
            erows.append(dict(factor=f, beta=b["beta"], sigma_1d=b["sigma_x"], dollar_per_sigma=b["dollar_per_sigma"], r2=b["r2"], convexity=(bd - bu) if np.isfinite(bu) and np.isfinite(bd) else np.nan))
        ex = pd.DataFrame(erows)
        st.dataframe(ex.style.format({"beta": "{:,.0f}", "sigma_1d": "{:.2f}", "dollar_per_sigma": "{:,.0f}", "r2": "{:.2f}", "convexity": "{:,.0f}"}), use_container_width=True, hide_index=True)
        healthy = []
        g = ex.set_index("factor")
        if "SPX" in g.index and np.isfinite(g.loc["SPX", "dollar_per_sigma"]):
            healthy.append(("SPX β ≤ 0", g.loc["SPX", "dollar_per_sigma"] <= 0))
        for f in ("VIX", "MOVE"):
            if f in g.index and np.isfinite(g.loc[f, "dollar_per_sigma"]):
                healthy.append((f"{f} β ≥ 0", g.loc[f, "dollar_per_sigma"] >= 0))
        tot = ex["dollar_per_sigma"].abs().sum()
        if tot > 0:
            share = ex["dollar_per_sigma"].abs().max() / tot
            healthy.append(("No single factor > 30% of risk", share <= 0.30))
        st.markdown("Healthy signature: " + " · ".join(f"{'✅' if ok else '❌'} {n}" for n, ok in healthy))
        st.caption("Never 2y + 10y + 2s10s together; 2y is a derived read; orthogonalise anything with VIF > 5. Style-replicable R² ≤ ~0.5 or the book is a beta/style book wearing a thematic label.")
    else:
        ex = pd.DataFrame()

    # ---------------- stress
    st.markdown("#### Stress layer — historical factor moves applied to *today's* exposures")
    corr_one = st.toggle("Correlation-to-one version (tail)", value=False, key="stress_c1")
    srows = []
    if not ex.empty:
        g = ex.set_index("factor")
        for name, (a, b) in EPISODES.items():
            if pd.Timestamp(a) < ff.index.min():
                srows.append(dict(scenario=name, kind="historical", pnl=np.nan, note="outside loaded history")); continue
            w = ff.loc[a:b]
            if w.empty:
                srows.append(dict(scenario=name, kind="historical", pnl=np.nan, note="no data")); continue
            moves = w.sum()
            pnl = 0.0
            for f, mv in moves.items():
                if f in g.index and np.isfinite(g.loc[f, "beta"]):
                    beta = g.loc[f, "beta"]
                    if corr_one:
                        beta = np.sign(beta) * max(abs(beta), abs(g.loc[f, "dollar_per_sigma"]) / max(g.loc[f, "sigma_1d"], 1e-9))
                    pnl += beta * mv / len(moves)   # average across factor lenses (univariate, not additive)
            srows.append(dict(scenario=name, kind="historical", pnl=pnl, note=", ".join(f"{f} {v:+.0f}" for f, v in moves.items() if f in ("SPX", "10Y", "VIX"))))
        for name, sh in PARAMETRIC.items():
            pnl = 0.0; n = 0
            for f, mv in sh.items():
                if f in g.index and np.isfinite(g.loc[f, "beta"]):
                    pnl += g.loc[f, "beta"] * mv; n += 1
            srows.append(dict(scenario=name, kind="parametric", pnl=pnl / max(n, 1), note=str(sh)))
        stt = pd.DataFrame(srows)
        st.dataframe(stt.style.format({"pnl": "{:,.0f}"}).map(D.shade(-1e6, 1e6), subset=["pnl"]), use_container_width=True, hide_index=True, height=440)
        worst = stt.dropna(subset=["pnl"]).sort_values("pnl").head(3)
        st.markdown("**Top-3 fragilities:** " + "; ".join(f"{r['scenario']} ({r['pnl']:,.0f})" for _, r in worst.iterrows()))
        # reverse stress: Mahalanobis-nearest factor vector to the loss limit
        L = st.number_input("Reverse stress: loss limit ($)", value=2_500_000, step=250_000)
        try:
            cov = ff.iloc[-250:].cov().loc[g.index, g.index].values
            beta = g["beta"].fillna(0).values
            lam = -L / (beta @ cov @ beta) if (beta @ cov @ beta) > 0 else 0
            x_star = lam * cov @ beta
            dist = float(np.sqrt(x_star @ np.linalg.pinv(cov) @ x_star))
            st.markdown(f"Nearest factor vector hitting −${L:,.0f} (Mahalanobis distance {dist:.1f}σ): " + ", ".join(f"{f} {v:+.1f}" for f, v in zip(g.index, x_star)))
        except Exception:
            st.caption("Reverse stress needs a full factor covariance.")
        # CED
        if daily:
            port = pd.DataFrame(daily).dropna(how="all").fillna(0).sum(axis=1).iloc[-756:]
            cum = port.cumsum()
            dd = (cum - cum.cummax()).rolling(21).min()
            tail = dd[dd <= dd.quantile(0.1)]
            ui.kpi_row([("CED (E[DD | DD ≥ q0.9], 1M paths)", f"${-tail.mean():,.0f}" if len(tail) else "n/a"), ("Worst 1M drawdown (3y)", f"${-dd.min():,.0f}" if len(dd.dropna()) else "n/a"),
                        ("Daily vol of book", f"${port.std():,.0f}"), ("Annualised", f"${port.std()*np.sqrt(252)/1e6:.2f}M vs $5M")])
    st.markdown("#### Seven ways the book loses — limits and actions")
    st.dataframe(pd.DataFrame([
        [1, "Quiet-tape bleed", "Daily theta % NAV; 20D decay", "Operating 5–10 bp/day; soft 10, hard 12", "Trim long gamma, lengthen tenor, pause adds"],
        [2, "Hidden directional beta", "$/1σ to each macro factor", "Equity, USD, duration caps", "Add offsetting hedge leg"],
        [3, "Style-factor proxy", "Style-replicable R²", "R² ≤ ~0.5; single-style β capped", "Re-examine edge; diversify expression"],
        [4, "Theme concentration", "Tail-corr risk share per theme", "≤ 30% of book vol ($1.5M)", "Cut most crowded / least convex leg"],
        [5, "Crowding & forced flow", "CTA stretch; forced flow vs ADV", "Stretch 70 no adds, 80 reduce; flow ≤ ~1 day ADV", "Reduce; switch to defined-loss options"],
        [6, "Path / un-holdability", "Worst 2w move × size vs L_stomach", "Per-line and book L not exceeded", "Cut size, not the trade"],
        [7, "Convexity / surface", "Vega by tenor, gamma, vanna/volga", "Sub-limits; max grid loss", "Rebalance Greeks; buy back wings"]],
        columns=["#", "Failure mode", "Primary metric", "Limit (illustrative)", "Action"]), use_container_width=True, hide_index=True)
    st.markdown("**Drawdown ladder (combined $5M book):** review at ~1× book vol · de-gross the most crowded / least convex legs across all three books at ~1.5× · flatten to defined-loss and insurance only at ~2×. Daily bands ±$1M / ±$2.5M / ±$5M → same-day attribution, factor review, risk-committee note.")

    # ---------------- theta
    st.markdown("#### Theta budget — a price to spend, not a number to minimise")
    nav = st.number_input("NAV ($)", value=100_000_000, step=10_000_000)
    lv = book[book["kind"] == "long-vol"] if "kind" in book.columns else pd.DataFrame()
    theta = float(lv["theta_day"].fillna(0).sum()) if len(lv) else 0.0
    gamma = float(lv["gamma"].fillna(0).sum()) if len(lv) else 0.0
    bp_day = theta / nav * 1e4
    status = "operating band" if 5 <= bp_day <= 10 else "below band — book has stopped owning the repricing" if bp_day < 5 else "SOFT BREACH (≥10 bp)" if bp_day < 12 else "HARD BREACH (≥12 bp)"
    ui.kpi_row([("|θ_book| per day", f"${theta:,.0f}"), ("bp of NAV / day", f"{bp_day:.1f}", None, status), ("20D decay", f"${theta*20:,.0f}"),
                ("Efficiency Γ/|θ|", f"{gamma / theta * 1000:.2f}" if theta > 0 else "n/a"), ("Premium in long-vol lines", f"${lv['premium'].fillna(0).sum():,.0f}" if len(lv) else "$0")])
    st.markdown(f"**Status: {status}.** Soft breach → no adds, lengthen tenor or move from ATM to wings. Hard breach → trim least efficient long gamma first; never by selling the crash wings bought as insurance. Short-premium legs never offset the budget.")
