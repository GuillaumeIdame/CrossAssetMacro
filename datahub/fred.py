"""FRED loader using the public fredgraph CSV endpoint (no API key).

If a FRED_API_KEY is present in the environment and the `fredapi` package is installed, the
official API is used instead (same output), which is faster for long histories.
"""

import io
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Iterable, Optional

import pandas as pd
import requests

from .cache import DiskCache

BASE_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"
_cache = DiskCache()
rejected: Dict[str, str] = {}


def _fetch_csv(series_id: str, start: str, timeout: int = 30) -> pd.Series:
    r = requests.get(BASE_URL, params={"id": series_id, "cosd": start}, timeout=timeout)
    r.raise_for_status()
    frame = pd.read_csv(io.StringIO(r.text))
    if frame.shape[1] < 2:
        raise ValueError("unexpected CSV shape")
    s = pd.Series(pd.to_numeric(frame.iloc[:, 1], errors="coerce").values,
                  index=pd.to_datetime(frame.iloc[:, 0]), name=series_id)
    return s.dropna().sort_index()


def _fetch_api(series_id: str, start: str) -> pd.Series:
    from fredapi import Fred  # optional

    fred = Fred(api_key=os.environ["FRED_API_KEY"])
    s = fred.get_series(series_id, observation_start=start)
    s.name = series_id
    return s.dropna().sort_index()


def series(ids: Iterable[str], start: str = "2005-01-01", use_cache: bool = True,
           workers: int = 6) -> pd.DataFrame:
    """Download several FRED series into one DataFrame (outer-joined on date)."""
    ids = list(dict.fromkeys(i for i in ids if i))
    if not ids:
        return pd.DataFrame()
    key = "fred_" + "_".join(sorted(ids))[:180] + f"_{start}"
    if use_cache and _cache.fresh(key):
        cached = _cache.read(key)
        if cached is not None and not cached.empty:
            return cached
    use_api = bool(os.environ.get("FRED_API_KEY"))

    def one(i):
        try:
            return i, (_fetch_api(i, start) if use_api else _fetch_csv(i, start)), None
        except Exception as error:
            return i, None, f"{type(error).__name__}: {str(error)[:80]}"

    cols = {}
    with ThreadPoolExecutor(workers) as ex:
        for i, s, err in ex.map(one, ids):
            if s is None or s.empty:
                rejected[i] = err or "empty"
            else:
                cols[i] = s
    if not cols:
        return pd.DataFrame()
    frame = pd.DataFrame(cols).sort_index()
    frame.index.name = "date"
    _cache.write(key, frame)
    return frame


def one(series_id: str, start: str = "2005-01-01") -> pd.Series:
    frame = series([series_id], start=start)
    if series_id in frame.columns:
        return frame[series_id].dropna()
    return pd.Series(dtype=float, name=series_id)
