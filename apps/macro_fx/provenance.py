"""Data & provenance page."""

import pandas as pd
import streamlit as st

from datahub import ui

from . import data


def render():
    ui.step("9", "Data and provenance", "Public data only; professional feeds drop in behind the same loaders.", "live")
    ui.legend()
    m = data.load_all()
    ui.health(m["status"], "Series loaded for this app")
    st.markdown("### What is live, proxy, manual, unavailable")
    st.dataframe(pd.DataFrame([
        dict(input="Spot and crosses", public_source="Yahoo (12y daily), FRED H.10 (since 1999, for seasonality)", status="live", gap="no intraday"),
        dict(input="Rates / OIS proxies", public_source="FRED: EFFR, €STR, SONIA daily; OECD short/long rates monthly for the rest", status="proxy", gap="1Y1Y / 5Y5Y OIS and inflation swaps not public → short-rate and 10y differentials stand in"),
        dict(input="Positioning", public_source="CFTC TFF / legacy (API or files in data/cftc)", status="unavailable from this network until files are dropped", gap="futures only, 3-day lag; misses OTC forwards"),
        dict(input="FX options surface", public_source="none — typed 1M ATM / 25Δ RR / BF; realised vol from spot", status="manual", gap="the hard gap; CME EOD settlements / CVOL could replace it; synthetic generator OFF"),
        dict(input="REER", public_source="BIS via FRED (monthly)", status="live (monthly)", gap="2-month lag"),
        dict(input="Macro surprises", public_source="modelled proxy from FRED/Yahoo growth series", status="proxy", gap="no consensus data"),
        dict(input="Fiscal impulse", public_source="typed from IMF Fiscal Monitor / OECD", status="manual", gap="annual"),
        dict(input="Institutional flow", public_source="not public", status="unavailable", gap="bank flow reports; synthetic generator with the same schema would be flagged"),
        dict(input="Calendar", public_source="data/g3_calendar.csv", status="confirmed / provisional / estimated per row", gap="verify estimated dates"),
    ]), use_container_width=True, hide_index=True)
    st.markdown("### Build plan (from the process document)")
    st.code("fx-macro-monitor/  data/ factors/ macro/ valuation/ positioning/ vol/ seasonality/ regime/ risk/ dashboard/ docs/\n"
            "Weeks 1–2  data layer, cache, synthetic generators; factor module on real spot      ✔ (datahub + page 1)\n"
            "Week 3     COT pipeline end to end; replay Aug-2024                                    ◐ (loader ready, needs CFTC files)\n"
            "Week 4     valuation module; validate on Liberation Day                               ✔ proxies (page 3)\n"
            "Week 5     vol module on CME/CVOL + synthetic surface                                  ◐ manual surface (page 4)\n"
            "Week 6     regime module; seasonality screener                                         ✔ (pages 5–6)\n"
            "Week 7     risk module: amplified shocks, stress library, CED                          ✔ spot-only (page 8)\n"
            "Week 8     dashboard + scorecard contract; docs; tag v1                                this app")
    if m["notes"]:
        st.warning("; ".join(m["notes"]))
