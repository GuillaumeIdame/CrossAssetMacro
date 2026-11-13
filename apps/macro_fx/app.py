"""Investment Process — Macro FX. Streamlit app.

    streamlit run apps/macro_fx/app.py

Pages follow the process chain Price → Driver → Regime → Confirmation → Relative Value → Expression.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st  # noqa: E402

from datahub import ui  # noqa: E402

from apps.macro_fx import factors, macro, positioning, provenance, regime, risk, seasonality, strategies, valuation  # noqa: E402

PAGES = [
    ("1 · Factor decomposition", factors.render),
    ("2 · Macro differentials", macro.render),
    ("3 · Valuation & REER", valuation.render),
    ("4 · Flows & positioning", positioning.render),
    ("5 · Seasonality", seasonality.render),
    ("6 · Regime & quadrant", regime.render),
    ("7 · Sub-strategies & trade card", strategies.render),
    ("8 · Risk", risk.render),
    ("9 · Data & provenance", provenance.render),
]


def main():
    ui.page("Macro FX", "💱")
    st.sidebar.title("Macro FX")
    st.sidebar.caption("Price → Driver → Regime → Confirmation → Relative Value → Expression")
    choice = st.sidebar.radio("Process step", [p[0] for p in PAGES], key="fx_nav")
    if st.sidebar.button("Refresh data", key="fx_refresh"):
        st.cache_data.clear(); st.rerun()
    st.sidebar.markdown("---")
    st.sidebar.caption("Companion books: G3 Central Bank · Macro Thematic. $5M vol budget shared across the three.")
    st.title("Investment Process — Macro FX")
    dict(PAGES)[choice]()


if __name__ == "__main__":
    main()
