"""Page 7 — Data and provenance."""

import pandas as pd
import streamlit as st

from datahub import stir, ui
from datahub import ROOT

from . import common as C


def render():
    ui.step("4.4", "Data and provenance", "Which numbers are observed, which are proxies, which are typed by the desk.")
    ui.legend()
    res = C.market()
    ui.health(res.status, "Series used by this app")
    st.subheader("STIR strips")
    rows = []
    for fam in C.FAMILY_META:
        s = C.active_strip(fam)
        if s.empty:
            rows.append(dict(family=fam, contracts=0, source="none", closes_as_of=None, note="no strip"))
        else:
            rows.append(dict(family=fam, contracts=len(s), source=str(s["source"].iloc[0]),
                             closes_as_of=pd.to_datetime(s["close_date"]).max().date() if "close_date" in s else None,
                             note="Yahoo individual contracts refresh daily" if fam == "ZQ" else "IBKR connector snapshot (delayed), refresh per data/ibkr_snapshots/README.md"))
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    snap = stir.latest_snapshot_path()
    st.caption(f"Latest snapshot file: {snap.split('/')[-1] if snap else 'none'}")
    st.subheader("Calendar")
    cal = C.cal()
    fut = cal[cal["date"] >= pd.Timestamp.today().normalize()]
    st.dataframe(fut.groupby(["type", "status"]).size().rename("count").reset_index(), hide_index=True, width="stretch")
    st.caption("confirmed = published by the central bank; provisional = published, subject to change; estimated = rule of thumb (NFP first Friday, CPI mid-month) — verify before trading. Edit data/g3_calendar.csv.")
    st.subheader("What is live, proxy, manual, unavailable")
    st.markdown("""
| Block | Status | Detail |
|---|---|---|
| Fed funds strip (ZQ) | live | Yahoo individual contracts, daily closes |
| SOFR / Euribor / SONIA strips | live (snapshot) | IBKR connector, delayed; date shown above |
| Meeting-dated path | derived | ridge least-squares bootstrap on the strip; fit error reported |
| Overnight spot rates | live | FRED EFFR, SOFR, €STR, SONIA (1–2 day lag) |
| Euribor − €STR basis | manual | slider |
| US macro gauges | live | FRED official prints; references = target or 10y mean |
| EA / UK gauges | proxy / manual | OECD-Eurostat monthly mirrors, lagging; UK CPI not available → manual |
| Consensus / Smart Forecaster | manual | no public survey feed; type Bloomberg/Reuters numbers |
| STIR option IVs, premiums | manual | no public STIR vol surface; IBKR FOP quotes can be read through the connector |
| CFTC positioning | unavailable here | cftc.gov blocked from this network; drop files in data/cftc |
| Term premium | live | ACM via FRED (THREEFYTP10) |
""")
    readme = ROOT / "data" / "ibkr_snapshots" / "README.md"
    if readme.exists():
        with st.expander("IBKR refresh path"):
            st.markdown(readme.read_text())
