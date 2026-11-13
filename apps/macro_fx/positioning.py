"""§1.4 / §4.1 — Flows & positioning: CFTC pipeline, event amplification, options block (manual surface + public vol)."""

from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

from datahub import DATA_DIR, calendar, cftc, stats, ui

from . import common, data

CFTC_KEY = {"EUR": "EUR", "GBP": "GBP", "JPY": "JPY", "CHF": "CHF", "CAD": "CAD", "AUD": "AUD", "NZD": "NZD", "MXN": "MXN"}
REGION = {"EUR": "EA", "GBP": "UK", "JPY": "JP", "CHF": "CH", "USD": "US"}
SURFACE_DEFAULT = {c: {"atm_1m": np.nan, "rr25_1m": np.nan, "bf25_1m": np.nan, "atm_prev": np.nan, "rr25_prev": np.nan} for c in data.CCYS}


@st.cache_data(ttl=3600, show_spinner=False)
def cftc_block():
    res = cftc.load()
    met = cftc.metrics(res["data"]) if not res["data"].empty else pd.DataFrame()
    return res["status"], res["source"], met


def positioning_table() -> pd.DataFrame:
    """Positioning per currency: CFTC if available, else manual override from session."""
    status, source, met = cftc_block()
    manual = common.session_dict("fx_pos_manual", {c: np.nan for c in data.CCYS})
    rows = []
    for c in data.CCYS:
        k = CFTC_KEY.get(c)
        r = met[met["key"] == k] if (k and not met.empty) else pd.DataFrame()
        if not r.empty:
            r = r.iloc[0]
            rows.append(dict(ccy=c, z=r["z"], net_oi=r["net_oi"], crowded=bool(r["crowded"]), built_by=r["built_by"], date=r["date"], source="CFTC", quality="live"))
        elif np.isfinite(manual.get(c, np.nan)):
            rows.append(dict(ccy=c, z=manual[c], net_oi=np.nan, crowded=abs(manual[c]) >= 1.5, built_by="", date=None, source="manual", quality="manual"))
        else:
            rows.append(dict(ccy=c, z=np.nan, net_oi=np.nan, crowded=False, built_by="", date=None, source="none", quality="unavailable"))
    return pd.DataFrame(rows)


def realised_vol_table(df: pd.DataFrame) -> pd.DataFrame:
    rets = data.returns(df)
    rows = []
    for c in rets.columns:
        r = rets[c].dropna()
        rv20 = stats.realised_vol(r, 20).iloc[-1] * 100; rv60 = stats.realised_vol(r, 60).iloc[-1] * 100
        erv = 0.6 * rv20 + 0.4 * rv60
        # spot / realised-vol correlation 20D: proxy for spot / ATM-vol correlation
        rv = stats.realised_vol(r, 20)
        corr = r.iloc[-20:].corr(rv.diff().iloc[-20:])
        rows.append(dict(ccy=c, rv20=rv20, rv60=rv60, e_rv=erv, spot_vol_corr_20d=corr))
    return pd.DataFrame(rows)


def surface_editor():
    surf = common.session_dict("fx_surface", SURFACE_DEFAULT)
    tab = pd.DataFrame(surf).T.reindex(data.CCYS)
    tab.index.name = "ccy"
    edited = st.data_editor(tab, key="fx_surface_editor", use_container_width=True,
                            column_config={"atm_1m": "1M ATM vol %", "rr25_1m": "25Δ RR (call−put) %", "bf25_1m": "25Δ BF %",
                                           "atm_prev": "ATM 5D ago %", "rr25_prev": "RR 5D ago %"})
    st.session_state["fx_surface"] = edited.to_dict(orient="index")
    return edited


def options_table(df: pd.DataFrame) -> pd.DataFrame:
    rv = realised_vol_table(df).set_index("ccy")
    surf = pd.DataFrame(common.session_dict("fx_surface", SURFACE_DEFAULT)).T.reindex(data.CCYS).astype(float)
    out = rv.join(surf)
    out["vrp"] = out["atm_1m"] - out["e_rv"]
    out["vrp_5d_change"] = out["atm_1m"] - out["atm_prev"]
    out["rr_5d_change"] = out["rr25_1m"] - out["rr25_prev"]
    return out


def event_amplification(pos: pd.DataFrame) -> pd.DataFrame:
    """Next 4 weeks of meetings in each currency's bloc × positioning sign → amplified if |z|≥1.5 against the surprise direction."""
    today = pd.Timestamp.today().normalize()
    rows = []
    for c, region in REGION.items():
        mts = calendar.meetings(region, start=today, end=today + pd.Timedelta(days=28))
        for _, mt in mts.iterrows():
            z = np.nan
            if c == "USD":
                z = np.nan  # USD positioning is the mirror of the basket; shown through pairs
            elif c in pos["ccy"].values:
                z = pos.set_index("ccy").loc[c, "z"]
            if np.isfinite(z) and abs(z) >= 1.5:
                side = "long" if z > 0 else "short"
                surprise = "hawkish" if z < 0 else "dovish"
                verdict = f"AMPLIFIED-{surprise}: crowd is {side} {c}; a {surprise} surprise forces it out"
            elif np.isfinite(z):
                verdict = "normal"
            else:
                verdict = "positioning unavailable"
            rows.append(dict(date=mt["date"].date(), currency=c, event=mt["event"], status=mt["status"], positioning_z=z, verdict=verdict))
    return pd.DataFrame(rows)


def render():
    ui.step("4", "Flows and positioning — the state variable",
            "The expected reaction to any catalyst is written conditional on positioning (BIS Bulletin 124).", "live")
    m = data.load_all(); df = m["df"]
    status, source, met = cftc_block()
    st.markdown(f"**CFTC COT pipeline** — status: `{status}` (source: {source})")
    if met.empty:
        st.warning("CFTC data is not reachable from this network. Download the TFF history (FinFutYY.txt / zip) from "
                   "cftc.gov → Historical Compressed and drop it in `data/cftc/`, or upload it here.")
        up = st.file_uploader("Upload CFTC file (FinFutYY.txt, deacotYY.zip, csv)", type=["txt", "csv", "zip"], key="fx_cftc_up")
        if up is not None:
            dest = Path(DATA_DIR) / "cftc" / up.name
            dest.write_bytes(up.getvalue())
            cftc_block.clear(); st.success(f"saved to {dest}; recomputing…"); st.rerun()
        with st.expander("Manual positioning override (z-scores, 156w) — used by the lifecycle, carry and risk pages until CFTC is available"):
            man = pd.DataFrame({"z": pd.Series(common.session_dict("fx_pos_manual", {c: np.nan for c in data.CCYS}))}).reindex(data.CCYS)
            ed = st.data_editor(man, key="fx_pos_manual_editor")
            st.session_state["fx_pos_manual"] = ed["z"].to_dict()
    else:
        st.dataframe(common.dfmt(met), use_container_width=True, hide_index=True)
        st.caption("z on 156 weeks of leveraged-fund (TFF) net; crowding = |z| ≥ 1.5 ∧ |Net/OI| ≥ p80; 'built-by' from the gross decomposition. 3-day lag: Friday release for Tuesday positions.")
    pos = positioning_table()
    st.markdown("**Positioning state used by the other pages**")
    st.dataframe(common.dfmt(pos), use_container_width=True, hide_index=True)

    st.markdown("### Event-risk overlay — next 4 weeks")
    amp = event_amplification(pos)
    if amp.empty:
        st.info("No central-bank meeting in the next 4 weeks for the tracked blocs.")
    else:
        st.dataframe(common.dfmt(amp), use_container_width=True, hide_index=True)
    st.caption("Amplified → asymmetry widens; any position aligned with the crowd takes a mandatory size cut or a convex overlay. Meeting dates from data/g3_calendar.csv (status column says confirmed / provisional / estimated).")

    st.markdown("### Options measures (1M)")
    st.markdown("No public OTC FX surface exists. Type the desk's 1M ATM / 25Δ RR / 25Δ BF (and the values 5 days ago for direction); "
                "realised vol, E[RV] = 0.6·RV20 + 0.4·RV60 and the spot/vol correlation proxy are computed from public data. "
                + ui.badge("manual") + " surface · " + ui.badge("live") + " realised · " + ui.badge("proxy") + " spot/RV correlation (stands in for spot/ATM-vol).", unsafe_allow_html=True)
    surface_editor()
    common.json_io("fx_surface", "surface inputs")
    ot = options_table(df)
    st.dataframe(common.dfmt(ot.reset_index()), use_container_width=True, hide_index=True)
    st.caption("Reading: RR level = insurance premium state; RR change diverging from spot = leading unwind tell; a flip of the spot/vol correlation sign (e.g. USD/JPY to 'vol up when JPY up') marks a carry-unwind regime. "
               "Synthetic surface generator: OFF (on synthetic data the RR-divergence signal is disabled, not faked).")
    st.markdown("**CTA / institutional flow (Tier-2)** — the CTA liquidation map lives in the Thematic app's CTA page (shared spec §4.2); bank flow reports are not public.")
