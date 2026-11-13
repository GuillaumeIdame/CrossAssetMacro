"""Free data adapters. Each returns plain pandas objects and raises on failure;
the app catches the error and shows the feed as unavailable instead of inventing numbers.

To plug in a paid feed later, add a function with the same return shape
(dict of contract code -> pd.Series of prices) and point the app at it.
"""

from __future__ import annotations

import io
import xml.etree.ElementTree as ET
from typing import Dict, List, Sequence

import pandas as pd
import requests

TIMEOUT = 20
HEADERS = {"User-Agent": "Mozilla/5.0 (STIR Monitor)"}


# --------------------------------------------------------------------------- Yahoo Finance
def _closes(raw: pd.DataFrame, tickers: Sequence[str]) -> Dict[str, pd.Series]:
    if raw is None or raw.empty:
        return {}
    if isinstance(raw.columns, pd.MultiIndex):
        close = raw["Close"]
    else:  # single ticker
        close = raw[["Close"]].rename(columns={"Close": tickers[0]})
    return {t: close[t].dropna() for t in tickers if t in close.columns and not close[t].dropna().empty}


def yahoo_prices(tickers: Sequence[str], period: str, interval: str) -> Dict[str, pd.Series]:
    """Bar closes per ticker. Intraday bars are tz-aware (UTC); daily bars are naive dates."""
    import yfinance as yf

    tickers = list(tickers)
    raw = yf.download(tickers, period=period, interval=interval, progress=False,
                      auto_adjust=False, threads=True, group_by="column")
    out = _closes(raw, tickers)
    for t, s in out.items():
        if interval.endswith(("m", "h")):
            s.index = s.index.tz_localize("UTC") if s.index.tz is None else s.index.tz_convert("UTC")
        else:
            s.index = pd.DatetimeIndex(s.index).tz_localize(None).normalize()
    return out


# --------------------------------------------------------------------------- fixings
def fred_series(series_id: str, start: str) -> pd.Series:
    r = requests.get("https://fred.stlouisfed.org/graph/fredgraph.csv",
                     params={"id": series_id, "cosd": start}, headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    df = pd.read_csv(io.StringIO(r.text))
    s = pd.to_numeric(df.iloc[:, 1], errors="coerce")
    s.index = pd.to_datetime(df.iloc[:, 0])
    return s.dropna()


def boc_series(series_id: str, start: str) -> pd.Series:
    r = requests.get(f"https://www.bankofcanada.ca/valet/observations/{series_id}/json",
                     params={"start_date": start}, headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    obs = r.json()["observations"]
    s = pd.Series({pd.Timestamp(o["d"]): float(o[series_id]["v"]) for o in obs if o.get(series_id, {}).get("v")})
    return s.sort_index()


def rba_series(series_id: str, start: str) -> pd.Series:
    """RBA statistical table F1 (money market rates), CSV with metadata rows on top."""
    r = requests.get("https://www.rba.gov.au/statistics/tables/csv/f1-data.csv", headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    raw = pd.read_csv(io.StringIO(r.content.decode("latin-1")), header=None, dtype=str)
    hdr = raw.index[raw.iloc[:, 0].str.strip().eq("Series ID")][0]
    cols = raw.iloc[hdr].str.strip().tolist()
    data = raw.iloc[hdr + 1:].set_axis(cols, axis=1)
    if series_id not in cols:
        raise KeyError(f"{series_id} not in RBA F1")
    s = pd.to_numeric(data[series_id], errors="coerce")
    s.index = pd.to_datetime(data["Series ID"], format="%d-%b-%Y", errors="coerce")
    s = s[s.index.notna()].dropna()
    return s[s.index >= pd.Timestamp(start)]


FIXING_SOURCES = {"fred": fred_series, "boc": boc_series, "rba": rba_series}


# --------------------------------------------------------------------------- Fed speeches
def fed_speeches(url: str, limit: int = 8) -> List[dict]:
    r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    root = ET.fromstring(r.content)
    items = []
    for it in root.iter("item"):
        items.append({
            "title": (it.findtext("title") or "").strip(),
            "link": (it.findtext("link") or "").strip(),
            "date": pd.to_datetime(it.findtext("pubDate"), errors="coerce"),
        })
    return items[:limit]
