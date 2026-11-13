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


# --------------------------------------------------------------------------- Interactive Brokers
class IBKRUnavailable(RuntimeError):
    pass


def ibkr_fetch(contracts: Dict[str, Dict[str, int]], exchanges: Dict[str, str], host: str, port: int,
               client_id: int, market_data_type: int = 3, timeout: int = 15,
               intraday: bool = True, daily: bool = True, snapshot: bool = True) -> dict:
    """Pull bars and last prices for many futures from TWS / IB Gateway in one connection.

    contracts: {curve: {code: conId}}, exchanges: {curve: exchange}.
    Returns {"intraday": {curve: {code: Series}}, "daily": {...}, "last": {curve: {code: float}}, "errors": [...]}.
    Intraday bars are tz-aware UTC; daily bars are naive session dates (same shape as yahoo_prices).
    """
    import asyncio
    import math

    try:  # Streamlit runs scripts in worker threads that have no event loop
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())
    from ib_async import IB, Contract

    ib = IB()
    try:
        ib.connect(host, port, clientId=client_id, timeout=timeout, readonly=True)
    except Exception as e:  # noqa: BLE001
        raise IBKRUnavailable(f"cannot connect to TWS/IB Gateway at {host}:{port} ({e})") from e

    out = {"intraday": {}, "daily": {}, "last": {}, "errors": []}
    try:
        ib.reqMarketDataType(market_data_type)
        flat = [(cv, code, Contract(conId=cid, exchange=exchanges[cv]))
                for cv, codes in contracts.items() for code, cid in codes.items()]
        qualified = ib.qualifyContracts(*[c for _, _, c in flat])
        ok = {c.conId for c in qualified}
        for cv, code, c in flat:
            if c.conId not in ok:
                out["errors"].append(f"IBKR {cv} {code}: contract {c.conId} not found")
        flat = [(cv, code, c) for cv, code, c in flat if c.conId in ok]

        def bars(c, duration, size):
            b = ib.reqHistoricalData(c, endDateTime="", durationStr=duration, barSizeSetting=size,
                                     whatToShow="TRADES", useRTH=False, formatDate=2, timeout=timeout)
            if not b:
                return None
            return pd.Series([x.close for x in b], index=[pd.Timestamp(x.date) for x in b], dtype=float)

        for cv, code, c in flat:
            if daily:
                try:
                    s = bars(c, "1 Y", "1 day")
                    if s is not None:
                        s.index = pd.DatetimeIndex(s.index).tz_localize(None).normalize()
                        out["daily"].setdefault(cv, {})[code] = s
                except Exception as e:  # noqa: BLE001
                    out["errors"].append(f"IBKR {cv} {code} daily: {e}")
            if intraday:
                try:
                    s = bars(c, "2 D", "5 mins")
                    if s is not None:
                        idx = pd.DatetimeIndex(s.index)
                        s.index = idx.tz_localize("UTC") if idx.tz is None else idx.tz_convert("UTC")
                        out["intraday"].setdefault(cv, {})[code] = s
                except Exception as e:  # noqa: BLE001
                    out["errors"].append(f"IBKR {cv} {code} 5m: {e}")

        if snapshot and flat:
            tickers = [(cv, code, ib.reqMktData(c, "", snapshot=True)) for cv, code, c in flat]
            ib.sleep(min(timeout, 6))
            for cv, code, t in tickers:
                px = t.last if t.last == t.last and t.last else t.marketPrice()
                if px is not None and not math.isnan(px) and px > 0:
                    out["last"].setdefault(cv, {})[code] = float(px)
    finally:
        ib.disconnect()
    return out
