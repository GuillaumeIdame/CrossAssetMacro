"""Investment Process — Macro Thematic · Streamlit one-stop shop.

    streamlit run apps/macro_thematic/app.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from datahub import ui  # noqa: E402

from apps.macro_thematic import confirmation, crowding, legs, onepager, regime, risk, screener, themes  # noqa: E402
from apps.macro_thematic import data as D  # noqa: E402


def data_page():
    ui.step("Data", "Data & provenance", "What is observed, what is approximated, what is typed in — and the public-data build plan.")
    frame, observed, status = D.load_universe()
    ui.legend()
    ui.health(status, "Universe (Yahoo + FRED)")
    _, cftc_status, cftc_source = D.load_cftc()
    pp = D.load_policy_path()
    st.markdown("#### Blocks")
    st.dataframe(pd.DataFrame([
        ["Regime engine", "live / proxy", "ISM replaced by INDPRO+GDPNow+UMich; policy history 1Y−EFFR, live path from the fed-funds strip"],
        ["Confirmation map", "live", "20/60D moves from Yahoo & FRED"],
        ["Theme records & scenarios", "manual", "session state, JSON export; examples pre-filled"],
        ["Screener — valuation", "live", "univariate OLS 20/60/90D + 3-PC curve residual"],
        ["Screener — carry", "live / proxy / n/a", "cash-curve carry+roll live; futures & FX proxy; commodities n/a without the 2nd contract"],
        ["Screener — seasonality", "live (score 0)", "two gates computed; 12y history covers 2 of 4 sub-periods so gate 2 cannot pass yet"],
        ["Screener — positioning", "estimated / live", f"CTA ensemble model; CFTC: {cftc_status}"],
        ["Crowding", "mixed", "CFTC or CTA pct; ETF volume z for flow/liquidity; concentration unavailable"],
        ["Vol premium", "live / manual", "VIX, MOVE, OVX, GVZ; manual IV elsewhere; index/basket skew ratio manual"],
        ["Risk", "live on manual book", "60D betas, episode replay over loaded history, CED, reverse stress"],
        ["Fed-funds strip", pp.get("source", "n/a") if pp else "n/a", f"{pp.get('n', 0) if pp else 0} contracts; 12m cumulative priced {pp.get('cum_12m_bp', float('nan')):+.0f} bp" if pp and 'cum_12m_bp' in pp else "unavailable"],
    ], columns=["Block", "Quality", "Note"]), use_container_width=True, hide_index=True)
    st.markdown("#### Public-data build plan (§4.5)")
    st.dataframe(pd.DataFrame([
        ["1 Data spine", "Loaders + parquet cache (FRED, yfinance, CFTC, IBKR snapshot)", "Idempotent refresh; CFTC history matches published reports on 10 dates", "done (CFTC needs files/API)"],
        ["2 Regime engine", "Six state variables, RC, transition machine, credibility overlay", "Reproduces 2013 taper, 2020, 2022 inflation, 2022 UK", "built; validation pending"],
        ["3 Pillars", "Carry, Valuation (univariate + PCA), Seasonality registry", "Carry reconciles by hand on 5 tenors; PCA flags 2015 and 2022", "built; seasonality needs 2000+ history"],
        ["4 Positioning & crowding", "CFTC metrics, replication, options layer, composite", "R² ≥ 0.6 vs SG Trend; crowding peaks precede known unwinds", "partial (no SG Trend / CFTC here)"],
        ["5 Risk & integration", "Factor model, CED, stress engine, theme tracker, one-pager", "Full daily cycle in under 5 minutes", "built"]],
        columns=["Phase", "Deliverable", "Acceptance test", "Status"]), use_container_width=True, hide_index=True)
    st.caption("Perimeter: public data and open-source tooling only. On joining a desk only Phase 1 changes — loaders swap to Bloomberg behind the same interfaces.")


PAGES = [
    ("1 · Regime engine & transition (T1/T2)", regime.render),
    ("2 · Theme tracker & scenarios (T13)", themes.render),
    ("3 · Confirmation & divergence (T3)", confirmation.render),
    ("4 · Four pillars & Trade Screener (T4–T8)", screener.render),
    ("5 · Crowding, quality, unwind tree (T9/T10)", crowding.render),
    ("6 · Leg choice & vol alphas (§2)", legs.render),
    ("7 · Sizing, exposure, stress, theta (§3)", risk.render),
    ("8 · Daily one-pager (T14)", onepager.render),
    ("9 · Data & provenance", data_page),
]


def main():
    ui.page("Macro Thematic", "🧭")
    with st.sidebar:
        st.markdown("## Macro Thematic")
        st.caption("Regime → Theme & scenarios → Confirmation → Four pillars → Crowding → Leg → Size → Stress")
        choice = st.radio("Process step", [p[0] for p in PAGES], label_visibility="collapsed")
        if st.button("Refresh data"):
            st.cache_data.clear(); st.rerun()
    st.markdown(f"### Investment Process — Macro Thematic")
    dict(PAGES)[choice]()


if __name__ == "__main__":
    main()
