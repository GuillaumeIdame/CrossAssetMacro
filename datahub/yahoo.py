"""Yahoo Finance loader: daily closes (and OHLC) with cache, retry and rejection log."""

import time
from typing import Dict, Iterable, List, Optional

import pandas as pd

from .cache import DiskCache

_cache = DiskCache()
rejected: Dict[str, str] = {}


def _download(tickers: List[str], period: str, retries: int = 3):
    import yfinance as yf

    last_error = None
    for attempt in range(retries):
        try:
            raw = yf.download(tickers, period=period, interval="1d", auto_adjust=True,
                              progress=False, threads=True, group_by="column")
            if raw is not None and len(raw):
                return raw
        except Exception as error:  # rate limits, transient network
            last_error = error
        time.sleep(1.5 * (attempt + 1))
    if last_error:
        raise last_error
    return pd.DataFrame()


def closes(tickers: Iterable[str], years: int = 12, min_obs: int = 30,
           use_cache: bool = True) -> pd.DataFrame:
    """Return a DataFrame of daily closes, one column per ticker (tickers that fail are dropped
    and recorded in ``yahoo.rejected``)."""
    tickers = list(dict.fromkeys(t for t in tickers if t))
    if not tickers:
        return pd.DataFrame()
    key = "yahoo_" + "_".join(sorted(tickers))[:180] + f"_{years}y"
    if use_cache and _cache.fresh(key):
        cached = _cache.read(key)
        if cached is not None and not cached.empty:
            return cached
    raw = _download(tickers, f"{years}y")
    if raw.empty:
        for t in tickers:
            rejected[t] = "no data returned"
        return pd.DataFrame()
    if isinstance(raw.columns, pd.MultiIndex):
        close = raw["Close"]
    else:
        close = raw[["Close"]].rename(columns={"Close": tickers[0]})
    out = {}
    for t in tickers:
        if t not in close.columns:
            rejected[t] = "ticker not returned"
            continue
        s = close[t].dropna()
        if len(s) < min_obs:
            rejected[t] = f"only {len(s)} observations"
            continue
        out[t] = s
    if not out:
        return pd.DataFrame()
    frame = pd.DataFrame(out)
    frame.index = pd.DatetimeIndex(frame.index).tz_localize(None)
    frame = frame.sort_index()
    _cache.write(key, frame)
    return frame


def ohlc(ticker: str, years: int = 5, use_cache: bool = True) -> pd.DataFrame:
    """Open/High/Low/Close for one ticker (needed for Yang-Zhang volatility)."""
    key = f"yahoo_ohlc_{ticker}_{years}y"
    if use_cache and _cache.fresh(key):
        cached = _cache.read(key)
        if cached is not None and not cached.empty:
            return cached
    import yfinance as yf

    hist = yf.Ticker(ticker).history(period=f"{years}y", auto_adjust=True)
    if hist is None or hist.empty:
        rejected[ticker] = "no OHLC returned"
        return pd.DataFrame()
    frame = hist[["Open", "High", "Low", "Close"]].copy()
    frame.index = pd.DatetimeIndex(frame.index).tz_localize(None)
    _cache.write(key, frame)
    return frame


def futures_strip(root: str, suffix: str, months: Iterable[str], years: int = 1,
                  period: str = "1y") -> pd.DataFrame:
    """Download a set of individual futures contracts, e.g. ZQZ26.CBT, ZQH27.CBT ...

    `months` are contract codes such as 'Z26', 'H27'. Contracts with no history are skipped.
    """
    tickers = [f"{root}{m}.{suffix}" for m in months]
    frame = closes(tickers, years=years, min_obs=1)
    return frame


def latest(frame: pd.DataFrame) -> pd.Series:
    """Last non-NaN value per column."""
    return frame.apply(lambda s: s.dropna().iloc[-1] if s.notna().any() else float("nan"))
