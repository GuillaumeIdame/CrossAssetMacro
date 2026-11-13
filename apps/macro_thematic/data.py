"""Universe, cached loads and small helpers for the Macro Thematic app."""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from datahub import calendar, cftc, loader, stats, stir  # noqa: E402

NAVY, BRONZE, SLATE, GREEN, RED = "#1F3550", "#A9814F", "#55677C", "#2E7D32", "#B71C1C"

UNIVERSE = [
    # equities
    "spx", "ndx", "rut", "sx5e", "dax", "ftse", "nikkei", "eem", "spy", "qqq", "iwm", "xli", "xlp", "xly", "xle", "xlf", "ita", "kre",
    # credit / bonds
    "hyg", "lqd", "jnk", "emb", "tlt", "ief", "shy", "tip", "hy_oas", "ig_oas", "eu_hy_oas",
    # commodities / crypto
    "wti", "brent", "gold", "copper", "silver", "natgas", "btc",
    # futures
    "zt", "zf", "zn", "zb", "es",
    # vol
    "vix", "vix3m", "vix9d", "vvix", "move", "ovx", "gvz", "skew",
    # rates
    "ust3m", "ust1", "ust2", "ust5", "ust10", "ust30", "real5", "real10", "bei5", "bei10", "fwd5y5y", "tp10",
    "effr", "sofr", "ecb_dfr", "estr", "sonia", "jp_policy", "uk_policy_m", "ea_3m", "uk_3m", "jp_3m",
    "de_10y", "uk_10y", "jp_10y",
    # conditions / liquidity
    "nfci", "anfci", "walcl", "tga", "rrp",
    # macro
    "cpi", "core_cpi", "core_pce", "unrate", "payems", "claims", "indpro", "retail", "gdpnow", "umcsent", "mich_infl",
    # fx
    "eurusd", "gbpusd", "usdjpy", "usdchf", "usdcad", "audusd", "nzdusd", "usdsek", "usdnok", "usdmxn", "dxy", "usd_broad",
]


@st.cache_data(ttl=3600, show_spinner="Loading the Macro Thematic universe (Yahoo + FRED)...")
def load_universe():
    res = loader.load(UNIVERSE, years=12)
    return res.frame, res.observed, res.status


@st.cache_data(ttl=3600, show_spinner=False)
def load_cftc():
    out = cftc.load()
    m = cftc.metrics(out["data"]) if not out["data"].empty else pd.DataFrame()
    return m, out["status"], out["source"]


@st.cache_data(ttl=3600, show_spinner=False)
def load_policy_path():
    """Market-priced Fed path from the fed-funds strip (12m cumulative, bp)."""
    try:
        s = stir.strip("ZQ")
        frame, _, _ = load_universe()
        spot = float(frame["effr"].dropna().iloc[-1])
        bs = stir.bootstrap("ZQ", s, spot)
        if bs.empty:
            return None
        today = pd.Timestamp.today().normalize()
        within = bs[bs["date"] <= today + pd.Timedelta(days=365)]
        return dict(spot=spot, cum_12m_bp=float(within["cum_bp"].iloc[-1]) if len(within) else float("nan"),
                    steps=bs, source=s["source"].iloc[0] if len(s) else "n/a", n=len(s))
    except Exception as error:  # strip unavailable
        return dict(error=str(error))


@st.cache_data(ttl=3600, show_spinner=False)
def load_calendar():
    return calendar.load()


@st.cache_data(ttl=3600, show_spinner=False)
def load_volumes(tickers=("SPY", "QQQ", "IWM", "HYG", "LQD", "TLT", "IEF", "EEM", "GLD", "USO", "XLE", "FXE", "FXY", "UUP")):
    """Volume z (liquidity proxy) for a handful of ETFs; separate pull because closes() drops volume."""
    try:
        import yfinance as yf
        raw = yf.download(list(tickers), period="2y", interval="1d", progress=False, threads=True, group_by="column")
        vol = raw["Volume"] if isinstance(raw.columns, pd.MultiIndex) else raw[["Volume"]]
        vol.index = pd.DatetimeIndex(vol.index).tz_localize(None)
        return vol.dropna(how="all")
    except Exception:
        return pd.DataFrame()


def series(frame: pd.DataFrame, key: str) -> pd.Series:
    if key in frame.columns:
        return frame[key].dropna()
    return pd.Series(dtype=float, name=key)


def prints(key: str) -> pd.Series:
    """Genuine prints only (no forward-fill) — use for monthly/weekly macro series before resampling."""
    frame, observed, _ = load_universe()
    if key not in frame.columns or key not in observed.columns:
        return pd.Series(dtype=float, name=key)
    return frame[key].where(observed[key]).dropna()


def last(frame, key, default=np.nan):
    s = series(frame, key)
    return float(s.iloc[-1]) if len(s) else default


def ratio(frame, a, b):
    sa, sb = series(frame, a), series(frame, b)
    r = (sa / sb).dropna()
    r.name = f"{a}/{b}"
    return r


def pct_change(s: pd.Series, days: int) -> float:
    s = s.dropna()
    if len(s) <= days:
        return np.nan
    return float(s.iloc[-1] / s.iloc[-1 - days] - 1)


def diff(s: pd.Series, days: int) -> float:
    s = s.dropna()
    if len(s) <= days:
        return np.nan
    return float(s.iloc[-1] - s.iloc[-1 - days])


def z3y(s: pd.Series) -> pd.Series:
    """z on 3y, winsorised ±3 (the process convention)."""
    return stats.zscore(s.dropna(), window=756, clip=3.0)


def pct_rank(s: pd.Series, window: int = 1260) -> float:
    return stats.last_percentile(s, window)


# --- session-state persistence (JSON) -------------------------------------------------------
def state_json() -> str:
    keys = ["themes", "book", "divergence_notes", "quality", "manual_vol"]
    payload = {k: st.session_state.get(k) for k in keys if k in st.session_state}
    return json.dumps(payload, indent=2, default=str)


def load_state_json(text: str) -> None:
    payload = json.loads(text)
    for k, v in payload.items():
        st.session_state[k] = v


def sign_fmt(x, nd=1, suffix=""):
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return "n/a"
    return f"{x:+.{nd}f}{suffix}"


def shade(lo: float, hi: float, neg="#B71C1C", pos="#2E7D32", mid="#FFFFFF"):
    """matplotlib-free cell shading for Styler.map: linear blend from neg (lo) through mid to pos (hi)."""
    def _hex(c):
        return tuple(int(c[i:i + 2], 16) for i in (1, 3, 5))
    def _blend(a, b, t):
        return "#%02x%02x%02x" % tuple(int(x + (y - x) * t) for x, y in zip(_hex(a), _hex(b)))
    def f(v):
        try:
            if v is None or not np.isfinite(float(v)):
                return ""
            v = float(v)
            if hi == lo:
                return ""
            if v >= (lo + hi) / 2:
                t = min(1.0, (v - (lo + hi) / 2) / ((hi - lo) / 2))
                return f"background-color: {_blend(mid, pos, t * 0.55)}"
            t = min(1.0, ((lo + hi) / 2 - v) / ((hi - lo) / 2))
            return f"background-color: {_blend(mid, neg, t * 0.55)}"
        except Exception:
            return ""
    return f
