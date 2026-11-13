"""Macro FX universe and the single cached data pull.

Sign convention used everywhere in this app: a pair is expressed as **USD per 1 unit of the
foreign currency**, so a positive log return means the foreign currency strengthened against the
USD. Yahoo quotes EUR/GBP/AUD/NZD that way already (``EURUSD=X``) and the others the other way
round (``JPY=X`` = USD/JPY), so the latter are inverted here once, and nowhere else.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from datahub import fred, loader, yahoo  # noqa: E402
from datahub.catalogue import CATALOGUE  # noqa: E402

G10 = ["EUR", "GBP", "JPY", "CHF", "CAD", "AUD", "NZD", "SEK", "NOK"]
EM = ["MXN", "ZAR", "CNY"]
CCYS = G10 + EM

# ccy -> (catalogue key, invert?)  invert = Yahoo quotes foreign units per USD
PAIRS = {"EUR": ("eurusd", False), "GBP": ("gbpusd", False), "JPY": ("usdjpy", True), "CHF": ("usdchf", True),
         "CAD": ("usdcad", True), "AUD": ("audusd", False), "NZD": ("nzdusd", False), "SEK": ("usdsek", True),
         "NOK": ("usdnok", True), "MXN": ("usdmxn", True), "ZAR": ("usdzar", True), "CNY": ("usdcny", True)}
PAIR_LABEL = {"EUR": "EUR/USD", "GBP": "GBP/USD", "JPY": "USD/JPY", "CHF": "USD/CHF", "CAD": "USD/CAD", "AUD": "AUD/USD",
              "NZD": "NZD/USD", "SEK": "USD/SEK", "NOK": "USD/NOK", "MXN": "USD/MXN", "ZAR": "USD/ZAR", "CNY": "USD/CNY"}

# FRED long-history daily FX (H.10) for the seasonality screener (back to 1971/1999), foreign per USD unless noted
FRED_FX = {"EUR": ("DEXUSEU", False), "GBP": ("DEXUSUK", False), "AUD": ("DEXUSAL", False), "NZD": ("DEXUSNZ", False),
           "JPY": ("DEXJPUS", True), "CHF": ("DEXSZUS", True), "CAD": ("DEXCAUS", True), "SEK": ("DEXSDUS", True),
           "NOK": ("DEXNOUS", True), "MXN": ("DEXMXUS", True), "ZAR": ("DEXSFUS", True), "CNY": ("DEXCHUS", True)}

# short rates (policy / overnight / 3M) — daily where FRED has them, else monthly OECD mirrors (proxy)
SHORT_RATE = {"USD": ("effr", "live", "d"), "EUR": ("estr", "live", "d"), "GBP": ("sonia", "live", "d"),
              "JPY": ("IRSTCI01JPM156N", "proxy", "m"), "CHF": ("IR3TIB01CHM156N", "proxy", "m"),
              "CAD": ("IRSTCI01CAM156N", "proxy", "m"), "AUD": ("IRSTCI01AUM156N", "proxy", "m"),
              "NZD": ("IR3TIB01NZM156N", "proxy", "m"), "SEK": ("IR3TIB01SEM156N", "proxy", "m"),
              "NOK": ("IRSTCI01NOM156N", "proxy", "m"), "MXN": ("IRSTCI01MXM156N", "proxy", "m"),
              "ZAR": ("IRSTCI01ZAM156N", "proxy", "m"), "CNY": ("IR3TIB01CNM156N", "proxy", "m")}
LONG_RATE = {"USD": ("ust10", "live"), "EUR": ("de_10y", "proxy"), "GBP": ("uk_10y", "proxy"), "JPY": ("jp_10y", "proxy"),
             "CHF": ("IRLTLT01CHM156N", "proxy"), "CAD": ("IRLTLT01CAM156N", "proxy"), "AUD": ("IRLTLT01AUM156N", "proxy"),
             "NZD": ("IRLTLT01NZM156N", "proxy"), "SEK": ("IRLTLT01SEM156N", "proxy"), "NOK": ("IRLTLT01NOM156N", "proxy"),
             "MXN": ("IRLTLT01MXM156N", "proxy"), "ZAR": ("IRLTLT01ZAM156N", "proxy"), "CNY": (None, "unavailable")}
EQUITY = {"USD": ("spx", "live"), "EUR": ("sx5e", "live"), "GBP": ("ftse", "live"), "JPY": ("nikkei", "live"),
          "CHF": ("^SSMI", "live"), "CAD": ("^GSPTSE", "live"), "AUD": ("^AXJO", "live"), "NZD": ("^NZ50", "live"),
          "SEK": ("^OMX", "live"), "NOK": (None, "unavailable"), "MXN": ("^MXX", "live"), "ZAR": ("^J203.JO", "live"),
          "CNY": ("000001.SS", "live")}
# inflation YoY (OECD mirrors lag badly; flagged proxy + stale date shown)
INFLATION = {"USD": ("cpi", "live"), "EUR": ("ea_hicp", "live"), "GBP": ("CPALTT01GBM659N", "proxy"), "JPY": ("CPALTT01JPM659N", "proxy"),
             "CHF": ("CPALTT01CHM659N", "proxy"), "CAD": ("CPALTT01CAM659N", "proxy"), "AUD": (None, "unavailable"),
             "NZD": (None, "unavailable"), "SEK": ("CPALTT01SEM659N", "proxy"), "NOK": ("CPALTT01NOM659N", "proxy"),
             "MXN": ("CPALTT01MXM659N", "proxy"), "ZAR": ("CPALTT01ZAM659N", "proxy"), "CNY": ("CPALTT01CNM659N", "proxy")}
REER = {"USD": "reer_us", "EUR": "reer_ea", "GBP": "reer_uk", "JPY": "reer_jp", "CHF": "reer_ch", "AUD": "reer_au", "CAD": "reer_ca",
        "NZD": "RBNZBIS", "SEK": "RBSEBIS", "NOK": "RBNOBIS", "MXN": "RBMXBIS", "ZAR": "RBZABIS", "CNY": "RBCNBIS"}

CATALOGUE_KEYS = ([PAIRS[c][0] for c in CCYS] + ["eurjpy", "audjpy", "cadjpy", "dxy", "usd_broad", "usd_afe",
                  "spx", "sx5e", "ftse", "nikkei", "dax", "eem", "hyg", "lqd", "emb", "tlt", "ief",
                  "brent", "wti", "copper", "gold", "natgas", "wheat", "vix", "move", "vix3m",
                  "ust1", "ust2", "ust5", "ust10", "ust30", "real5", "real10", "bei5", "bei10", "effr", "sofr", "estr", "sonia", "ecb_dfr",
                  "hy_oas", "ig_oas", "nfci", "cpi", "core_cpi", "ea_hicp", "indpro", "retail", "payems", "unrate", "claims", "umcsent",
                  "de_10y", "uk_10y", "jp_10y", "jp_policy", "uk_policy_m", "ea_3m", "uk_3m", "jp_3m", "ea_bus_conf",
                  "reer_us", "reer_ea", "reer_uk", "reer_jp", "reer_ch", "reer_au", "reer_ca"])
EXTRA_YAHOO = ["^SSMI", "^GSPTSE", "^AXJO", "^NZ50", "^OMX", "^MXX", "^J203.JO", "000001.SS"]
EXTRA_FRED_M = sorted({v[0] for v in SHORT_RATE.values() if v[0] and v[0] not in CATALOGUE} |
                      {v[0] for v in LONG_RATE.values() if v[0] and v[0] not in CATALOGUE} |
                      {v[0] for v in INFLATION.values() if v[0] and v[0] not in CATALOGUE} |
                      {v for v in REER.values() if v not in CATALOGUE})


@st.cache_data(ttl=3600, show_spinner="Loading FX universe (Yahoo + FRED)…")
def load_all() -> dict:
    """One pull for the whole app. Returns dict with 'df' (aligned business-day frame), 'status',
    'fx_long' (FRED daily FX since 1999, USD per foreign) and 'rejected'."""
    res = loader.load(CATALOGUE_KEYS, years=12)
    df = res.frame.copy()
    status = res.status.copy()
    notes = []
    # extra Yahoo local indices
    try:
        ex = yahoo.closes(EXTRA_YAHOO, years=12)
        for t in EXTRA_YAHOO:
            if t in ex.columns:
                df[t] = ex[t].reindex(df.index).ffill(limit=7)
                s = ex[t].dropna()
                status.loc[len(status)] = dict(key=t, name=t, source="yahoo", ticker=t, quality="live", freq="d", status="loaded",
                                               first=s.index[0].date(), last=s.index[-1].date(), obs=len(s), value=float(s.iloc[-1]), note="local equity index")
            else:
                status.loc[len(status)] = dict(key=t, name=t, source="yahoo", ticker=t, quality="live", freq="d", status="unavailable",
                                               first=None, last=None, obs=0, value=np.nan, note=yahoo.rejected.get(t, "not returned"))
    except Exception as e:  # pragma: no cover
        notes.append(f"extra Yahoo failed: {e}")
    # extra FRED monthly (foreign short/long rates, inflation, REER)
    try:
        exf = fred.series(EXTRA_FRED_M, start="2005-01-01")
        for i in EXTRA_FRED_M:
            if i in exf.columns:
                df[i] = exf[i].reindex(df.index).ffill(limit=45)
                s = exf[i].dropna()
                status.loc[len(status)] = dict(key=i, name=i, source="fred", ticker=i, quality="proxy", freq="m", status="loaded",
                                               first=s.index[0].date(), last=s.index[-1].date(), obs=len(s), value=float(s.iloc[-1]), note="monthly OECD/BIS mirror")
            else:
                status.loc[len(status)] = dict(key=i, name=i, source="fred", ticker=i, quality="proxy", freq="m", status="unavailable",
                                               first=None, last=None, obs=0, value=np.nan, note=fred.rejected.get(i, "not returned"))
    except Exception as e:  # pragma: no cover
        notes.append(f"extra FRED failed: {e}")
    # long FX history for seasonality
    fx_long = pd.DataFrame()
    try:
        raw = fred.series([v[0] for v in FRED_FX.values()], start="1999-01-01")
        cols = {}
        for c, (sid, inv) in FRED_FX.items():
            if sid in raw.columns:
                s = raw[sid].replace(0, np.nan).dropna()
                cols[c] = (1.0 / s) if inv else s
        fx_long = pd.DataFrame(cols).sort_index()
    except Exception as e:  # pragma: no cover
        notes.append(f"FRED FX history failed: {e}")
    return dict(df=df, status=status, fx_long=fx_long, notes=notes, rejected={**yahoo.rejected, **fred.rejected})


# --- derived views -----------------------------------------------------------------------------
def spot(df: pd.DataFrame, ccy: str) -> pd.Series:
    """USD per 1 unit of ccy."""
    key, inv = PAIRS[ccy]
    if key not in df.columns:
        return pd.Series(dtype=float, name=ccy)
    s = df[key].astype(float)
    return (1.0 / s if inv else s).rename(ccy)


def spots(df: pd.DataFrame, ccys=None) -> pd.DataFrame:
    ccys = ccys or CCYS
    return pd.DataFrame({c: spot(df, c) for c in ccys if PAIRS[c][0] in df.columns})


def returns(df: pd.DataFrame, ccys=None) -> pd.DataFrame:
    """Daily log returns, positive = foreign currency up vs USD."""
    return np.log(spots(df, ccys)).diff()


def short_rate(df: pd.DataFrame, ccy: str) -> pd.Series:
    key = SHORT_RATE[ccy][0]
    return df[key].astype(float) if key in df.columns else pd.Series(dtype=float)


def long_rate(df: pd.DataFrame, ccy: str) -> pd.Series:
    key = LONG_RATE[ccy][0]
    return df[key].astype(float) if key and key in df.columns else pd.Series(dtype=float)


def equity(df: pd.DataFrame, ccy: str) -> pd.Series:
    key = EQUITY[ccy][0]
    return df[key].astype(float) if key and key in df.columns else pd.Series(dtype=float)


def inflation_yoy(df: pd.DataFrame, ccy: str) -> pd.Series:
    key = INFLATION[ccy][0]
    if not key or key not in df.columns:
        return pd.Series(dtype=float)
    s = df[key].astype(float)
    if key in ("cpi", "ea_hicp"):  # index level → YoY on monthly prints
        m = s.dropna().resample("MS").last()
        yoy = 100 * (m / m.shift(12) - 1)
        return yoy.reindex(df.index).ffill(limit=45)
    return s


def reer(df: pd.DataFrame, ccy: str) -> pd.Series:
    key = REER[ccy]
    return df[key].astype(float) if key in df.columns else pd.Series(dtype=float)


def carry_diff(df: pd.DataFrame, ccy: str) -> pd.Series:
    """Short-rate differential foreign − USD (percentage points). Proxy for forward-implied carry."""
    f, u = short_rate(df, ccy), short_rate(df, "USD")
    if f.empty or u.empty:
        return pd.Series(dtype=float)
    return (f - u).rename(ccy)


def quality_of(ccy: str, block: str) -> str:
    return {"short": SHORT_RATE, "long": LONG_RATE, "equity": EQUITY, "inflation": INFLATION}[block][ccy][1]


def window_safe(s: pd.Series, n: int) -> pd.Series:
    s = s.dropna()
    return s.iloc[-n:] if len(s) > n else s
