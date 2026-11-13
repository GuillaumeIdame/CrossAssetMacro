"""One-stop shop: mounts the three Investment Process apps and the Cross-Asset Regime Engine
in a single Streamlit navigation.

    streamlit run hub.py

Each app also runs on its own:
    streamlit run apps/g3_central_bank/app.py
    streamlit run apps/macro_fx/app.py
    streamlit run apps/macro_thematic/app.py
    streamlit run streamlit_app.py          # regime engine (legacy entry point)
"""

import importlib
import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from datahub import ui  # noqa: E402

APPS = [
    ("G3 Central Bank", "apps.g3_central_bank.app", "🏛️"),
    ("Macro FX", "apps.macro_fx.app", "💱"),
    ("Macro Thematic", "apps.macro_thematic.app", "🧭"),
]


def _home():
    st.title("Investment Process — one-stop shop")
    st.markdown(
        "Three books, one data spine. Pick a section in the sidebar; every page is one step of the "
        "written process and every number carries its provenance badge.")
    ui.legend()
    cols = st.columns(3)
    blurbs = {
        "G3 Central Bank": "Fundamental assessment → expected distribution → market distribution → pricing → trade → Kelly. "
                           "Fed, ECB, BoE front ends; ZQ / SOFR / Euribor / SONIA strips bootstrapped meeting by meeting.",
        "Macro FX": "Price → driver → regime → confirmation → relative value → expression. Dollar/Carry/Momentum "
                    "decomposition, four differentials, univariate valuation, positioning as state variable, five regime axes.",
        "Macro Thematic": "Regime → theme & scenarios → confirmation → four pillars → crowding → leg choice → size → stress. "
                          "Six-variable regime engine, screener, crowding score, three vol alphas, one-pager.",
    }
    for c, (name, _, icon) in zip(cols, APPS):
        with c:
            st.subheader(f"{icon} {name}")
            st.write(blurbs[name])
    st.divider()
    st.subheader("Data spine")
    st.markdown(
        "- **Yahoo Finance**: equities, FX, futures (incl. individual fed funds contracts), vol indices, ETFs — daily.\n"
        "- **FRED**: UST curve, TIPS, breakevens, ACM term premium, policy rates (EFFR, SOFR, €STR, SONIA, ECB DFR), "
        "OAS, NFCI, Fed balance sheet / TGA / RRP, US releases, BIS REER, OECD monthly rates for EA/UK/JP.\n"
        "- **IBKR**: STIR strips (SOFR 3M, Euribor, SONIA, fed funds) captured through the connector into "
        "`data/ibkr_snapshots/`; refresh with the connector or `python -m datahub.ibkr_refresh` (TWS).\n"
        "- **CFTC COT**: positioning, when the API is reachable or files are dropped in `data/cftc/`.\n"
        "- **Not public**: OTC FX / STIR option surfaces, institutional flow, consensus surveys — typed in (manual) "
        "or left unavailable, never faked.")
    st.markdown("See `docs/DATA_SOURCES.md` for the full availability matrix.")


def _regime_engine_page():
    """Wrap the legacy regime engine dashboard inside the hub."""
    try:
        from streamlit_app import MacroRegimeApp
    except Exception as error:  # pragma: no cover
        st.error(f"Regime engine not importable: {error}")
        return
    app = MacroRegimeApp()
    result = app._result()
    section = st.sidebar.radio("Regime engine section", app.SECTIONS, key="hub_regime_section")
    app._header(result)
    getattr(app, {"Regime": "_regime_tab", "Factors": "_factors_tab", "Signals": "_signals_tab",
                  "Sub-regimes": "_sub_regime_tab", "History": "_history_tab", "Data": "_data_tab"}[section])(result)


def _load_pages(module_name: str):
    try:
        mod = importlib.import_module(module_name)
        return list(mod.PAGES), None
    except Exception as error:
        return [], error


def main():
    ui.page("Investment Process — one-stop shop", "🗂️")
    nav = {"Home": [st.Page(_home, title="Home", icon="🏠", default=True)]}
    for name, module_name, icon in APPS:
        pages, error = _load_pages(module_name)
        if error:
            def _err(e=error, n=name):
                st.error(f"{n} failed to import: {e}")
            nav[name] = [st.Page(_err, title=f"{name} (error)", icon="⚠️", url_path=name.lower().replace(" ", "-"))]
            continue
        entries = []
        for i, (title, fn) in enumerate(pages):
            slug = f"{name}-{title}".lower().replace(" ", "-").replace("/", "-").replace("&", "and")
            slug = "".join(ch for ch in slug if ch.isalnum() or ch == "-")
            entries.append(st.Page(fn, title=title, url_path=slug, icon=icon if i == 0 else None))
        nav[name] = entries
    nav["Regime Engine"] = [st.Page(_regime_engine_page, title="Cross-Asset Regime Engine", icon="📊", url_path="regime-engine")]
    with st.sidebar:
        if st.button("Refresh all data", use_container_width=True):
            st.cache_data.clear()
            st.session_state.pop("result", None)
            st.rerun()
    page = st.navigation(nav, position="sidebar")
    page.run()


if __name__ == "__main__":
    main()
