"""High-level loader: give it catalogue keys, get back one aligned business-day frame."""

from typing import Dict, Iterable, List, Optional

import pandas as pd

from . import fred, yahoo
from .catalogue import CATALOGUE


class LoadResult:
    def __init__(self, frame: pd.DataFrame, observed: pd.DataFrame, status: pd.DataFrame):
        self.frame = frame          # aligned, forward-filled (limit) business-day frame, keyed by catalogue key
        self.observed = observed    # True where a genuine print exists
        self.status = status        # provenance table

    def last_observed(self, key: str) -> Optional[pd.Timestamp]:
        if key not in self.observed.columns:
            return None
        s = self.observed[key]
        return s[s].index[-1] if s.any() else None


def load(keys: Iterable[str], years: int = 12, fill_limit: int = 7, start: Optional[str] = None,
         use_cache: bool = True) -> LoadResult:
    keys = [k for k in dict.fromkeys(keys) if k in CATALOGUE]
    ymap = {k: CATALOGUE[k]["ticker"] for k in keys if CATALOGUE[k]["source"] == "yahoo"}
    fmap = {k: CATALOGUE[k]["ticker"] for k in keys if CATALOGUE[k]["source"] == "fred"}
    start = start or (pd.Timestamp.today().normalize() - pd.DateOffset(years=years)).strftime("%Y-%m-%d")

    frames = []
    if ymap:
        y = yahoo.closes(list(ymap.values()), years=years, use_cache=use_cache)
        inv = {v: k for k, v in ymap.items()}
        y = y.rename(columns=inv)
        frames.append(y)
    if fmap:
        f = fred.series(list(fmap.values()), start=start, use_cache=use_cache)
        inv = {v: k for k, v in fmap.items()}
        f = f.rename(columns=inv)
        frames.append(f)
    frames = [x for x in frames if not x.empty]
    if not frames:
        raw = pd.DataFrame()
    else:
        raw = pd.concat(frames, axis=1).sort_index()
    raw = raw.loc[:, ~raw.columns.duplicated()] if not raw.empty else raw

    if raw.empty:
        return LoadResult(raw, raw, _status(keys, raw, raw))
    cal = pd.bdate_range(raw.index.min(), max(raw.index.max(), pd.Timestamp.today().normalize()))
    re = raw.reindex(cal)
    observed = re.notna()
    # monthly/weekly series are carried forward until the next print (that is the point-in-time truth)
    limit_by_key = {}
    for k in re.columns:
        freq = CATALOGUE.get(k, {}).get("freq", "d")
        limit_by_key[k] = {"d": fill_limit, "w": 12, "m": 45, "q": 130}.get(freq, fill_limit)
    filled = pd.DataFrame({k: re[k].ffill(limit=limit_by_key[k]) for k in re.columns}, index=cal)
    filled.index.name = "date"
    return LoadResult(filled, observed, _status(keys, raw, observed))


def _status(keys: List[str], raw: pd.DataFrame, observed: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for k in keys:
        meta = CATALOGUE[k]
        ok = (not raw.empty) and k in raw.columns and raw[k].notna().any()
        if ok:
            s = raw[k].dropna()
            rows.append(dict(key=k, name=meta["name"], source=meta["source"], ticker=meta["ticker"], quality=meta["quality"],
                             freq=meta["freq"], status="loaded", first=s.index[0].date(), last=s.index[-1].date(),
                             obs=int(len(s)), value=float(s.iloc[-1]), note=meta.get("note", "")))
        else:
            note = (yahoo.rejected.get(meta["ticker"]) or fred.rejected.get(meta["ticker"]) or "not returned")
            rows.append(dict(key=k, name=meta["name"], source=meta["source"], ticker=meta["ticker"], quality=meta["quality"],
                             freq=meta["freq"], status="unavailable", first=None, last=None, obs=0, value=float("nan"), note=note))
    return pd.DataFrame(rows)
