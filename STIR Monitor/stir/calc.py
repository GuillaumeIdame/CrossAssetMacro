"""Pure calculations: price series in, bp numbers out. No I/O here, so it is all unit-testable.

Conventions
-----------
* STIR futures are quoted as price = 100 - rate. A rate change in bp is -(price change) x 100,
  so a hawkish move (rates up, prices down) shows as a positive number.
* A calendar spread (e.g. Z6Z7) is price(front) - price(back); its change is shown in bp.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, time, timedelta
from typing import Dict, Iterable, List, Optional, Sequence

import pandas as pd

MONTH_CODES = {"F": 1, "G": 2, "H": 3, "J": 4, "K": 5, "M": 6, "N": 7, "Q": 8, "U": 9, "V": 10, "X": 11, "Z": 12}
CODE_FOR_MONTH = {v: k for k, v in MONTH_CODES.items()}

INTRADAY_TIMEFRAMES = {"15m": timedelta(minutes=15), "30m": timedelta(minutes=30), "1h": timedelta(hours=1)}
LOOKBACKS = {"1W": pd.DateOffset(weeks=1), "1M": pd.DateOffset(months=1), "3M": pd.DateOffset(months=3), "6M": pd.DateOffset(months=6)}


# --------------------------------------------------------------------------- contracts
def contract_ticker(code: str, root: str, exchange: str, template: str) -> str:
    """'Z26' -> 'SR3Z26.CME' (using the template from config.yaml)."""
    return template.format(root=root, month=code[0], yy=code[1:], exchange=exchange)


def fed_funds_code(year: int, month: int) -> str:
    return f"{CODE_FOR_MONTH[month]}{year % 100:02d}"


# --------------------------------------------------------------------------- changes
def rate_change_bp(last: Optional[float], ref: Optional[float]) -> Optional[float]:
    if last is None or ref is None or pd.isna(last) or pd.isna(ref):
        return None
    return round(-(last - ref) * 100, 2)


def spread_change_bp(last_front, last_back, ref_front, ref_back) -> Optional[float]:
    vals = [last_front, last_back, ref_front, ref_back]
    if any(v is None or pd.isna(v) for v in vals):
        return None
    return round(((last_front - last_back) - (ref_front - ref_back)) * 100, 2)


def _asof(series: pd.Series, when) -> Optional[float]:
    """Last value at or before `when`."""
    s = series.dropna()
    s = s[s.index <= when]
    return None if s.empty else float(s.iloc[-1])


def last_price(intraday: Optional[pd.Series], daily: Optional[pd.Series]) -> Optional[float]:
    for s in (intraday, daily):
        if s is not None and not s.dropna().empty:
            return float(s.dropna().iloc[-1])
    return None


def reference_price(
    timeframe: str,
    intraday: Optional[pd.Series],
    daily: Optional[pd.Series],
    since: Optional[date] = None,
    eu_open: time = time(7, 0),
    eu_tz: str = "Europe/London",
) -> Optional[float]:
    """Reference price for one timeframe pill.

    intraday: tz-aware bar closes. daily: closes indexed by session date (naive).
    """
    intra = intraday.dropna() if intraday is not None else pd.Series(dtype=float)
    dly = daily.dropna() if daily is not None else pd.Series(dtype=float)

    if timeframe in INTRADAY_TIMEFRAMES:
        if intra.empty:
            return None
        return _asof(intra, intra.index[-1] - INTRADAY_TIMEFRAMES[timeframe])

    if timeframe == "Since EU Open":
        if intra.empty:
            return None
        local = intra.tz_convert(eu_tz) if intra.index.tz is not None else intra
        today = local.index[-1].date()
        session = local[(local.index.date == today) & (local.index.time >= eu_open)]
        return None if session.empty else float(session.iloc[0])

    if dly.empty:
        return None
    last_day = (intra.index[-1].tz_convert(None).normalize() if not intra.empty and intra.index.tz is not None
                else pd.Timestamp(dly.index[-1]).normalize())
    prior = dly[dly.index.normalize() < last_day]

    if timeframe == "Day":
        return None if prior.empty else float(prior.iloc[-1])
    if timeframe == "Week":  # vs previous Friday's settle (last close before this week's Monday)
        monday = last_day - pd.Timedelta(days=last_day.weekday())
        s = dly[dly.index.normalize() < monday]
        return None if s.empty else float(s.iloc[-1])
    if timeframe == "Since":
        return None if since is None else _asof(dly, pd.Timestamp(since))
    if timeframe in LOOKBACKS:
        return _asof(dly, last_day - LOOKBACKS[timeframe])
    raise ValueError(f"unknown timeframe {timeframe}")


def strip_changes(
    contracts: Sequence[str],
    intraday: Dict[str, pd.Series],
    daily: Dict[str, pd.Series],
    timeframe: str,
    since: Optional[date] = None,
) -> Dict[str, Optional[float]]:
    out = {}
    for c in contracts:
        last = last_price(intraday.get(c), daily.get(c))
        ref = reference_price(timeframe, intraday.get(c), daily.get(c), since)
        out[c] = rate_change_bp(last, ref)
    return out


def dec_spread_changes(pairs, intraday, daily, timeframe, since=None) -> List[Optional[float]]:
    res = []
    for front, back, _label in pairs:
        lf, lb = last_price(intraday.get(front), daily.get(front)), last_price(intraday.get(back), daily.get(back))
        rf = reference_price(timeframe, intraday.get(front), daily.get(front), since)
        rb = reference_price(timeframe, intraday.get(back), daily.get(back), since)
        res.append(spread_change_bp(lf, lb, rf, rb))
    return res


def yield_change_bp(last: Optional[float], ref: Optional[float]) -> Optional[float]:
    """Yield indices are quoted in %, so no sign flip."""
    if last is None or ref is None:
        return None
    return round((last - ref) * 100, 1)


# --------------------------------------------------------------------------- meeting pricing
@dataclass
class MeetingRow:
    meeting: date
    move: float        # bp
    cumulative: float  # bp
    implied: float     # %


def months_between(start: date, end: date) -> List[tuple]:
    out, y, m = [], start.year, start.month
    while (y, m) <= (end.year, end.month):
        out.append((y, m))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def fomc_path(meetings: Sequence[date], monthly_rate: Dict[tuple, float], start_rate: Optional[float] = None) -> List[MeetingRow]:
    """CME-FedWatch-style meeting-by-meeting path from 30D Fed Funds futures.

    monthly_rate[(y, m)] = 100 - ZQ price = expected average EFFR for that month.
    For a meeting on day d of an N-day month (new rate effective d+1):
        pre  = previous meeting's post-rate (first meeting: the prior month's average if that month has
               no meeting, else start_rate)
        post = next month's average if next month has no meeting, else (avg*N - pre*d) / (N - d)
    Move = post - pre, Cumulative = post - pre(first), Implied = start + cumulative.
    The chain stops at the first meeting whose month is missing from the futures.
    """
    meeting_months = {(m.year, m.month) for m in meetings}
    rows: List[MeetingRow] = []
    pre = None
    for i, mt in enumerate(sorted(meetings)):
        ym = (mt.year, mt.month)
        if ym not in monthly_rate:
            break
        if i == 0:
            prev = (mt.year - 1, 12) if mt.month == 1 else (mt.year, mt.month - 1)
            if prev in monthly_rate and prev not in meeting_months:
                pre = monthly_rate[prev]
            elif start_rate is not None:
                pre = start_rate
            else:
                break
            base = pre
        n = calendar.monthrange(*ym)[1]
        nxt = (mt.year + 1, 1) if mt.month == 12 else (mt.year, mt.month + 1)
        if nxt in monthly_rate and nxt not in meeting_months:
            post = monthly_rate[nxt]
        elif n - mt.day > 0:
            post = (monthly_rate[ym] * n - pre * mt.day) / (n - mt.day)
        else:
            break
        move = (post - pre) * 100
        cum = (post - base) * 100
        rows.append(MeetingRow(mt, round(move, 1), round(cum, 1), round(base + cum / 100, 3)))
        pre = post
    return rows


def priced_history(meetings, zq_daily: Dict[tuple, pd.Series], days: int, start_rate_series: Optional[pd.Series] = None):
    """Meeting paths as of each of the last `days`+1 sessions (index 0 = latest).

    Returns a list of (session_date, rows, delta_1d) where delta_1d[i] is the change in
    cumulative bp vs the previous session (None where not comparable).
    """
    frame = pd.DataFrame(zq_daily).dropna(how="all")
    if frame.empty:
        return []
    sessions = list(frame.index[-(days + 2):])[::-1]
    paths = []
    for s in sessions:
        row = frame.loc[s].dropna()
        monthly = {k: 100 - float(v) for k, v in row.items()}
        start = _asof(start_rate_series, s) if start_rate_series is not None else None
        paths.append((pd.Timestamp(s).date(), fomc_path(meetings, monthly, start)))
    out = []
    for i in range(len(paths) - 1):
        d, rows = paths[i]
        prev = {r.meeting: r.cumulative for r in paths[i + 1][1]}
        delta = [round(r.cumulative - prev[r.meeting], 1) if r.meeting in prev else None for r in rows]
        out.append((d, rows, delta))
    return out


def argmax_abs(values: Iterable[Optional[float]]) -> int:
    best, idx = -1.0, -1
    for i, v in enumerate(values):
        if v is not None and abs(v) > best:
            best, idx = abs(v), i
    return idx if best > 0 else -1


# --------------------------------------------------------------------------- 3M strip -> meeting path
def third_wednesday(year: int, month: int) -> date:
    d = date(year, month, 15)
    return d + timedelta(days=(2 - d.weekday()) % 7)


def imm_period(code: str) -> tuple:
    """Reference quarter of a 3M RFR future: 3rd Wed of the contract month to 3rd Wed three months later."""
    m, y = MONTH_CODES[code[0]], 2000 + int(code[1:])
    em, ey = (m + 3, y) if m <= 9 else (m - 9, y + 1)
    return third_wednesday(y, m), third_wednesday(ey, em)


def strip_meeting_path(meetings: Sequence[date], strip_rates: Dict[str, float], current_rate: float,
                       asof: date, smooth: float = 0.2) -> List[MeetingRow]:
    """Approximate meeting-by-meeting path from quarterly 3M futures (used for CORRA / BoC).

    The overnight rate is piecewise constant, changing the day after each meeting. Each contract's
    implied rate (100 - price) is treated as the simple average of that path over its reference
    quarter (days before `asof` are taken at `current_rate`). Post-meeting rates are solved by least
    squares with a small penalty on changes in consecutive moves, because quarterly contracts do not
    pin every meeting. Meetings after the last contract's reference period are dropped.
    """
    import numpy as np

    periods = {c: imm_period(c) for c in strip_rates}
    periods = {c: p for c, p in periods.items() if p[1] > asof}
    if not periods:
        return []
    horizon = max(p[1] for p in periods.values())
    mts = [m for m in sorted(meetings) if asof <= m < horizon]
    n = len(mts)
    if n == 0:
        return []
    rows, rhs = [], []
    for c, (start, end) in periods.items():
        total = (end - start).days
        coef = np.zeros(n)
        const = 0.0
        d = start
        while d < end:
            k = sum(1 for m in mts if m < d)  # number of meetings already effective on day d
            if d < asof or k == 0:
                const += current_rate
            else:
                coef[k - 1] += 1
            d += timedelta(days=1)
        rows.append(coef / total)
        rhs.append(strip_rates[c] - const / total)
    A, b = np.array(rows), np.array(rhs)
    # penalty on second differences of the path, i.e. on changes between consecutive moves
    # (path point -1 is current_rate, a known constant moved to the right-hand side)
    P, q = [], []
    for i in range(1, n):
        e = np.zeros(n)
        e[i], e[i - 1] = 1.0, -2.0
        if i >= 2:
            e[i - 2] = 1.0
        P.append(e * smooth)
        q.append(0.0 if i >= 2 else -current_rate * smooth)
    if P:
        A, b = np.vstack([A, np.array(P)]), np.concatenate([b, np.array(q)])
    sol, *_ = np.linalg.lstsq(A, b, rcond=None)
    out, prev = [], current_rate
    for m, r in zip(mts, sol):
        r = float(r)
        out.append(MeetingRow(m, round((r - prev) * 100, 1), round((r - current_rate) * 100, 1), round(r, 3)))
        prev = r
    return out
