"""Shared state, cached loaders and small helpers for the G3 Central Bank app."""

import io
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from datahub import calendar, loader, stir, ui  # noqa: E402
from datahub.catalogue import CATALOGUE  # noqa: E402

NAVY, BRONZE, SLATE, GREEN, RED = "#1F3550", "#A9814F", "#55677C", "#2E7D32", "#B71C1C"

SERIES = [
    # rates / policy
    "effr", "sofr", "estr", "sonia", "ecb_dfr", "fft_upper", "fft_lower", "iorb",
    "ust1", "ust2", "ust5", "ust10", "ust30", "bei5", "bei10", "fwd5y5y", "real10", "tp10", "acm1", "acm2",
    "tbill3m", "zq_front", "sr3_front", "vix", "move", "nfci", "hy_oas", "ig_oas",
    # US macro
    "cpi", "core_cpi", "pce", "core_pce", "mich_infl", "unrate", "payems", "claims", "cont_claims", "jolts", "quits",
    "ahe", "hours", "partic", "indpro", "retail_core", "gdpnow", "permit", "houst", "umcsent", "manemp",
    # EA / UK (lagging monthly mirrors)
    "ea_hicp", "ea_unemp", "ea_bus_conf", "ea_3m", "de_10y", "uk_unemp", "uk_3m", "uk_10y", "uk_policy_m",
]

FAMILY_META = {
    "ZQ": dict(label="Fed funds (ZQ)", region="US", spot="effr", spot_label="EFFR", usd_per_bp=41.67, ccy="$"),
    "SR3": dict(label="3M SOFR (SR3)", region="US", spot="sofr", spot_label="SOFR", usd_per_bp=25.0, ccy="$"),
    "ER": dict(label="3M Euribor (ER)", region="EA", spot="estr", spot_label="€STR", usd_per_bp=25.0, ccy="€"),
    "SON": dict(label="3M SONIA (SON)", region="UK", spot="sonia", spot_label="SONIA", usd_per_bp=25.0, ccy="£"),
}
REGION_LABEL = {"US": "Fed", "EA": "ECB", "UK": "BoE", "JP": "BoJ", "CH": "SNB"}


@st.cache_data(ttl=3600, show_spinner="Loading FRED and Yahoo series...")
def market():
    return loader.load(SERIES, years=15)


@st.cache_data(ttl=3600, show_spinner="Loading STIR strips...")
def strip(family: str) -> pd.DataFrame:
    try:
        return stir.strip(family)
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=3600)
def cal() -> pd.DataFrame:
    return calendar.load()


def active_strip(family: str) -> pd.DataFrame:
    """Manual strip edits (session state) take precedence over the loaded strip."""
    edited = st.session_state.get(f"strip_manual_{family}")
    if edited is not None and not edited.empty:
        df = edited.copy()
        win = [stir.contract_window(family, cm) for cm in df["contract_month"]]
        df["win_start"] = [w[0] for w in win]
        df["win_end"] = [w[1] for w in win]
        df["implied_rate"] = 100.0 - df["close"]
        df["source"] = "manual"
        return df.sort_values("contract_month").reset_index(drop=True)
    return strip(family)


def spot_rate(family: str, res=None) -> float:
    res = res or market()
    key = FAMILY_META[family]["spot"]
    if key in res.frame.columns and res.frame[key].notna().any():
        return float(res.frame[key].dropna().iloc[-1])
    return float("nan")


def basis_bp(family: str) -> float:
    return float(st.session_state.get("euribor_basis_bp", 12.0)) if family == "ER" else 0.0


def bootstrap(family: str):
    s = active_strip(family)
    sp = spot_rate(family)
    if s.empty or not np.isfinite(sp):
        return pd.DataFrame(), s, sp
    try:
        bs = stir.bootstrap(family, s, sp, basis_bp=basis_bp(family))
    except Exception as error:  # never crash a page on a bootstrap problem
        st.warning(f"Bootstrap failed for {family}: {error}")
        bs = pd.DataFrame()
    return bs, s, sp


def last(res, key: str):
    """(value, date) of the last genuine print, or (nan, None)."""
    if key not in res.frame.columns or not res.frame[key].notna().any():
        return float("nan"), None
    obs = res.observed[key]
    dates = obs[obs].index
    if len(dates) == 0:
        return float("nan"), None
    d = dates[-1]
    return float(res.frame.loc[d, key]), d


@st.cache_data(ttl=3600, show_spinner=False)
def _fred_direct(ticker: str) -> pd.Series:
    """Fallback for series the business-day alignment drops (weekend-dated prints such as ICSA/CCSA)."""
    from datahub import fred
    try:
        return fred.one(ticker, start="2010-01-01")
    except Exception:
        return pd.Series(dtype=float)


def series(res, key: str) -> pd.Series:
    out = pd.Series(dtype=float)
    if key in res.frame.columns:
        obs = res.observed[key]
        out = res.frame.loc[obs[obs].index, key].dropna()
    if out.empty and CATALOGUE.get(key, {}).get("source") == "fred":
        out = _fred_direct(CATALOGUE[key]["ticker"])
    return out


def quality_of(key: str) -> str:
    return CATALOGUE.get(key, {}).get("quality", "live")


def badge_md(quality: str) -> str:
    return ui.badge(quality)


def fmt(x, nd=2, suffix=""):
    return ui.fmt(x, nd, suffix)


def ss_get(key, default):
    if key not in st.session_state:
        st.session_state[key] = default
    return st.session_state[key]


def download_state(keys, label="Download manual inputs (JSON)", name="g3_inputs.json"):
    payload = {}
    for k in keys:
        v = st.session_state.get(k)
        if isinstance(v, pd.DataFrame):
            payload[k] = {"__df__": v.to_json(orient="split", date_format="iso")}
        elif v is not None:
            try:
                json.dumps(v)
                payload[k] = v
            except TypeError:
                payload[k] = str(v)
    st.download_button(label, json.dumps(payload, indent=2), file_name=name, mime="application/json")


def upload_state(label="Upload manual inputs (JSON)", key="upload_json"):
    up = st.file_uploader(label, type=["json"], key=key)
    if up is not None:
        try:
            payload = json.load(up)
            for k, v in payload.items():
                if isinstance(v, dict) and "__df__" in v:
                    st.session_state[k] = pd.read_json(io.StringIO(v["__df__"]), orient="split")
                else:
                    st.session_state[k] = v
            st.success(f"Loaded {len(payload)} inputs.")
        except Exception as error:
            st.error(f"Could not read file: {error}")


def plotly_layout(fig, height=360, title=None):
    fig.update_layout(height=height, margin=dict(l=10, r=10, t=40 if title else 10, b=10), title=title,
                      template="plotly_white", legend=dict(orientation="h", y=1.08, x=0),
                      font=dict(family="Segoe UI, Helvetica, Arial", size=12))
    return fig
