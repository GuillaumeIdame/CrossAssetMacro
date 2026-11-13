"""Investment Process — G3 Central Bank: front-end rates process for the Fed, ECB and BoE.

    streamlit run apps/g3_central_bank/app.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st  # noqa: E402

from datahub import ui  # noqa: E402

from apps.g3_central_bank import pages_data, pages_distributions, pages_macro, pages_market, pages_overview, pages_risk, pages_valuation  # noqa: E402

PAGES = [
    ("Countdown & process", pages_overview.render),
    ("Macro read", pages_macro.render),
    ("Market-implied state", pages_market.render),
    ("Three distributions", pages_distributions.render),
    ("Distribution tree & valuation", pages_valuation.render),
    ("Risk", pages_risk.render),
    ("Data & provenance", pages_data.render),
]


def main():
    ui.page("G3 Central Bank", "🏦")
    st.sidebar.title("G3 Central Bank")
    st.sidebar.caption("Fundamental → Expected distribution → Market distribution → Pricing → Trade → Kelly")
    titles = [t for t, _ in PAGES]
    choice = st.sidebar.radio("Process step", titles, key="cb_nav")
    if st.sidebar.button("Refresh data"):
        st.cache_data.clear()
        st.rerun()
    st.sidebar.markdown("---")
    st.sidebar.caption("Internal research tooling, not investment advice. All calibrations illustrative until connected to live desk data.")
    st.title("Investment Process — G3 Central Bank")
    dict(PAGES)[choice]()


if __name__ == "__main__":
    main()
