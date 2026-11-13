"""G3 macro calendar: central-bank meetings and tier-1 releases.

Source of truth is ``data/g3_calendar.csv`` (editable). ``status`` says how much to trust a date:
confirmed (published by the central bank), provisional (published but subject to change),
estimated (rule-of-thumb, e.g. NFP = first Friday; verify before trading).
"""

from datetime import date
from typing import Iterable, Optional

import pandas as pd

from . import DATA_DIR

CB_BY_REGION = {"US": "Fed", "EA": "ECB", "UK": "BoE", "JP": "BoJ", "CH": "SNB"}
EFFECTIVE_LAG_DAYS = {"US": 1, "EA": 6, "UK": 1, "JP": 1, "CH": 1}  # decision -> new rate effective


def load(path=None) -> pd.DataFrame:
    path = path or (DATA_DIR / "g3_calendar.csv")
    cal = pd.read_csv(path, parse_dates=["date"])
    cal["note"] = cal["note"].fillna("")
    return cal.sort_values("date").reset_index(drop=True)


def meetings(region: str, start: Optional[pd.Timestamp] = None, end: Optional[pd.Timestamp] = None,
             cal: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    cal = cal if cal is not None else load()
    m = cal[(cal["type"] == "meeting") & (cal["region"] == region)].copy()
    start = start or pd.Timestamp.today().normalize()
    m = m[m["date"] >= start]
    if end is not None:
        m = m[m["date"] <= end]
    m["effective"] = m["date"] + pd.to_timedelta(EFFECTIVE_LAG_DAYS.get(region, 1), unit="D")
    return m.reset_index(drop=True)


def upcoming(days: int = 60, regions: Iterable[str] = ("US", "EA", "UK"), cal: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    cal = cal if cal is not None else load()
    today = pd.Timestamp.today().normalize()
    out = cal[(cal["date"] >= today) & (cal["date"] <= today + pd.Timedelta(days=days)) & (cal["region"].isin(regions))].copy()
    out["days_to"] = (out["date"] - today).dt.days
    return out.reset_index(drop=True)


def counts_before(target: pd.Timestamp, region: str, cal: Optional[pd.DataFrame] = None) -> dict:
    """How much information is still to come before `target`: counts of inflation / growth /
    labour / policy releases for the region (plus US releases, which move every front end)."""
    cal = cal if cal is not None else load()
    today = pd.Timestamp.today().normalize()
    w = cal[(cal["date"] >= today) & (cal["date"] < target) & (cal["region"].isin({region, "US"}))]
    rel = w[w["type"] == "release"]
    return dict(inflation=int((rel["gauge"] == "inflation").sum()), growth=int((rel["gauge"] == "growth").sum()),
                labour=int((rel["gauge"] == "labour").sum()), tier1=int((rel["tier"] == 1).sum()),
                meetings=int((w["type"] == "meeting").sum()), total=int(len(w)))


def countdown_stage(days_to_event: int) -> str:
    if days_to_event > 10:
        return "~2 weeks before: broad assessment, wide distribution"
    if days_to_event > 4:
        return "~1 week before: update with data, surveys, communication"
    if days_to_event >= 0:
        return "2-3 days before: refine print, strikes, pin, Kelly size"
    return "post-event: restart the cycle"
