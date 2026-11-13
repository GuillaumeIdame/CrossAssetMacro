"""Page 6 — Risk: shocks, strike map, expiry map, liquidity/positioning, aggregate and cross-book ladder (§3)."""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from datahub import kelly, ui

from . import common as C
from . import engine as E

BOOK_COLS = ["family", "contract", "structure", "qty", "strike", "premium_bp", "note"]
STRUCTS = ["future", "call (rate up)", "put (rate down)", "straddle", "strangle"]


def _book() -> pd.DataFrame:
    b = st.session_state.get("book")
    if b is None:
        b = pd.DataFrame([dict(family="ZQ", contract="", structure="future", qty=0.0, strike=np.nan, premium_bp=np.nan, note="example row — edit me")], columns=BOOK_COLS)
    return b


def _legs(row, r_now):
    q = float(row["qty"]); k = row["strike"] if np.isfinite(row.get("strike", np.nan)) else r_now
    prem = float(row["premium_bp"]) if np.isfinite(row.get("premium_bp", np.nan)) else 0.0
    s = row["structure"]
    if s == "future":          # qty > 0 = long the future = short the rate
        return [dict(type="linear", strike=r_now, qty=-q)]
    if s.startswith("call"):
        return [dict(type="call", strike=k, qty=q, premium_bp=prem)]
    if s.startswith("put"):
        return [dict(type="put", strike=k, qty=q, premium_bp=prem)]
    if s == "straddle":
        return [dict(type="call", strike=k, qty=q, premium_bp=prem / 2), dict(type="put", strike=k, qty=q, premium_bp=prem / 2)]
    if s == "strangle":
        return [dict(type="call", strike=k + 0.25, qty=q, premium_bp=prem / 2), dict(type="put", strike=k - 0.25, qty=q, premium_bp=prem / 2)]
    return []


def render():
    ui.step("3.1", "Risk highlights and shock analysis",
            "What can hurt the book today, and what creates a large P&L if the thesis is right?")
    strips = {f: C.active_strip(f) for f in C.FAMILY_META}
    st.subheader("Book")
    st.markdown(ui.badge("manual") + " positions are typed by the desk. qty: lots (+ long). Options: strike in rate (%), premium in bp paid (+) per structure.", unsafe_allow_html=True)
    all_contracts = sorted({c for s in strips.values() if not s.empty for c in s["contract"]})
    edited = st.data_editor(_book(), num_rows="dynamic", key="book_editor", width="stretch",
                            column_config={"family": st.column_config.SelectboxColumn(options=list(C.FAMILY_META)),
                                           "contract": st.column_config.SelectboxColumn(options=all_contracts),
                                           "structure": st.column_config.SelectboxColumn(options=STRUCTS)})
    st.session_state["book"] = edited
    book = edited.dropna(subset=["family", "contract"]).copy()
    book = book[(book["contract"] != "") & (book["qty"].fillna(0) != 0)]
    C.download_state(["book"], "Download book (JSON)", "g3_book.json")
    C.upload_state("Upload book (JSON)", key="upload_book")
    if book.empty:
        st.info("Add positions to run shocks, the strike map and the expiry map."); 
    # --- shock grid -----------------------------------------------------------
    st.subheader("Shock grid — P&L by shock family ($k, intrinsic re-evaluation)")
    shocks = {"−50 bp": ("par", -50), "−25 bp": ("par", -25), "−10 bp": ("par", -10), "−5 bp": ("par", -5), "+5 bp": ("par", 5), "+10 bp": ("par", 10),
              "+25 bp": ("par", 25), "+50 bp": ("par", 50), "bull steepener (front −25 → back 0)": ("steep", -25), "bear steepener (front 0 → back +25)": ("steep", 25),
              "bull flattener (front 0 → back −25)": ("flat", -25), "bear flattener (front +25 → back 0)": ("flat", 25)}
    rows = []
    for _, pos in book.iterrows():
        s = strips[pos["family"]]
        if s.empty or pos["contract"] not in list(s["contract"]):
            continue
        i = list(s["contract"]).index(pos["contract"]); n = len(s)
        r_now = float(s.loc[i, "implied_rate"])
        usd = C.FAMILY_META[pos["family"]]["usd_per_bp"]
        legs = _legs(pos, r_now)
        base = kelly.structure_pnl(legs, np.array([r_now]))[0]
        out = dict(position=f"{pos['family']} {pos['contract']} {pos['structure']} x{pos['qty']:+.0f}")
        for name, (kind, bp) in shocks.items():
            if kind == "par":
                dr = bp
            elif kind == "steep":
                dr = bp * (1 - i / max(n - 1, 1)) if bp < 0 else bp * (i / max(n - 1, 1))
            else:
                dr = bp * (i / max(n - 1, 1)) if bp < 0 else bp * (1 - i / max(n - 1, 1))
            pnl = kelly.structure_pnl(legs, np.array([r_now + dr / 100]))[0] - base
            out[name] = pnl * usd / 1000
        rows.append(out)
    if rows:
        grid = pd.DataFrame(rows).set_index("position")
        grid.loc["AGGREGATE"] = grid.sum()
        st.dataframe(grid.round(1), width="stretch")
        agg = grid.loc["AGGREGATE"]
        worst = agg.idxmin()
        ui.kpi_row([("Worst shock", worst), ("Loss under worst shock", f"{agg.min():,.0f} $k"), ("Best shock", agg.idxmax()), ("Gain under best shock", f"{agg.max():,.0f} $k")])
        st.caption("Options are re-evaluated at intrinsic value under the shock (no vega / theta); that understates long-option P&L and overstates short-option losses under small shocks — conservative for a long-gamma book.")
    # --- strike map -------------------------------------------------------------
    st.subheader("Strike map — options book by contract × strike")
    opts = book[book["structure"] != "future"]
    if not opts.empty:
        cells = []
        for _, pos in opts.iterrows():
            k = pos["strike"]; q = float(pos["qty"])
            if pos["structure"] == "strangle":
                cells += [(pos["contract"], round(k + 0.25, 3), q, "call"), (pos["contract"], round(k - 0.25, 3), q, "put")]
            elif pos["structure"] == "straddle":
                cells += [(pos["contract"], round(k, 3), q, "call"), (pos["contract"], round(k, 3), q, "put")]
            else:
                cells.append((pos["contract"], round(k, 3), q, "call" if pos["structure"].startswith("call") else "put"))
        sm = pd.DataFrame(cells, columns=["contract", "strike", "net_qty", "type"])
        piv = sm.pivot_table(index="strike", columns="contract", values="net_qty", aggfunc="sum").fillna(0)
        fig = go.Figure(go.Heatmap(z=piv.values, x=piv.columns, y=[f"{k:.3f}" for k in piv.index], colorscale=[[0, C.RED], [0.5, "#F5F7FA"], [1, C.GREEN]],
                                   zmid=0, text=piv.values, texttemplate="%{text:+.0f}"))
        st.plotly_chart(C.plotly_layout(fig, height=300, title="net option lots (+ long gamma, − short gamma)"), width="stretch")
        gamma = float(sm["net_qty"].sum())
        verdict = "well positioned" if abs(gamma) <= 0.3 * sm["net_qty"].abs().sum() else ("too long gamma / volatility" if gamma > 0 else "too short gamma / volatility")
        conc = piv.abs().max().max() / max(piv.abs().values.sum(), 1e-9)
        st.markdown(f"Net option lots {gamma:+.0f}; largest single strike = {conc:.0%} of the option book → **{verdict}{'; too concentrated' if conc > 0.5 else ''}**. "
                    "Re-read against the expected outcome, relevant strikes, potential pin and gamma concentration as the countdown advances.")
    else:
        st.caption("No option positions in the book.")
    # --- expiry map -------------------------------------------------------------
    st.subheader("Expiry map — what each option carries into expiry")
    cal = C.cal()
    if not opts.empty:
        rows = []
        for _, pos in opts.iterrows():
            s = strips[pos["family"]]
            if s.empty or pos["contract"] not in list(s["contract"]):
                continue
            c = s[s["contract"] == pos["contract"]].iloc[0]
            ltd = pd.to_datetime(c["last_trading_date"]) if pd.notna(c.get("last_trading_date")) else pd.to_datetime(c["win_start"])
            ev = E.expiry_events(ltd, C.FAMILY_META[pos["family"]]["region"], cal)
            rows.append(dict(position=f"{pos['family']} {pos['contract']} {pos['structure']}", expiry=ltd.date(), days=(ltd - pd.Timestamp.today().normalize()).days,
                             events_before_expiry=len(ev), meetings=int((ev["type"] == "meeting").sum()), tier1_releases=int(((ev["type"] == "release") & (ev["tier"] == 1)).sum()),
                             carries=E.carries(ev), next_event=(f"{ev.iloc[0]['date'].date()} {ev.iloc[0]['event']}" if len(ev) else "—")))
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
        st.caption("Key question: what events occur between today and expiry, and what happens to the position if they change the market distribution? (Expiry = contract last trading date; option expiries on these contracts are at or before it.)")
    # --- liquidity & positioning -------------------------------------------------
    st.subheader("Liquidity and positioning — the exit test")
    st.markdown("CFTC TFF positioning in SOFR and Treasury futures: " + ui.badge("unavailable") +
                " when cftc.gov is unreachable from this network — drop the FinFutYY files in data/cftc (see datahub.cftc). Flow is used for risk and timing only, never as a signal.", unsafe_allow_html=True)
    checks = ["Just before data: can every structure be cut at a reasonable price?", "Just after data: is there a two-way market in the wings held?",
              "Before the meeting: concentration in similar structures across the desk checked", "During a large rates move / VaR shock: dealer capacity and bid-offer re-quoted"]
    ex = C.ss_get("exit_checks", {})
    for i, c in enumerate(checks):
        ex[str(i)] = st.checkbox(c, value=ex.get(str(i), False), key=f"exit_{i}")
    st.session_state["exit_checks"] = ex
    # --- cross-book ladder --------------------------------------------------------
    st.subheader("Aggregate and cross-book risk — one $5M vol budget")
    c1, c2 = st.columns(2)
    budget = c1.number_input("Combined book annualised vol budget ($M)", value=5.0, min_value=0.5)
    dd = c2.number_input("Current drawdown across the three books ($M, positive number)", value=0.0, min_value=0.0)
    ratio = dd / budget if budget > 0 else 0
    if ratio >= 2:
        state, colour = "≥ 2× book vol — flatten to defined-loss and insurance only", C.RED
    elif ratio >= 1.5:
        state, colour = "≥ 1.5× — de-gross the most crowded / least convex legs across all three books", "#B26A00"
    elif ratio >= 1:
        state, colour = "≥ 1× — review", C.BRONZE
    else:
        state, colour = "inside the ladder", C.GREEN
    st.markdown(f"<div style='border-left:5px solid {colour};padding:6px 12px'><b>Drawdown {dd:.2f} $M = {ratio:.2f}× budget → {state}</b></div>", unsafe_allow_html=True)
    st.markdown("""
| Layer | Check | Frequency |
|---|---|---|
| Pre-event calendar | CB event-outcome grid for CB positions; FX event-amplification table for exposed pairs; Thematic event card for themes tied to the catalyst | every tier-1 release / meeting |
| Factor netting | Rates level/slope, USD, credit and vol summed across the three books before any shock | continuous |
| Combined drawdown ladder | review 1×, de-gross 1.5×, flatten 2× | daily |
| Stress replay | BoJ hike, UK mini-budget, April-2025 tariffs run once against the combined positions | weekly / event-driven |
""")
    st.info("Crowding reads asymmetrically: in this book, internal distribution + market distribution + positioning all pointing the same way is a caution, not a third confirmation.")
