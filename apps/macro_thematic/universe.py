"""Screener universe built from public data — one record per instrument.

Common frame (§1.7): long = receive / long the bond / long base currency / first leg over second.
`series` is the level traded in the common frame: yields for rates (long = receive, so a positive
valuation residual = cheap = favours long), prices for everything else (positive residual = rich).
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from . import data as D


@dataclass
class Instrument:
    key: str
    label: str
    asset_class: str          # rates | rates_fut | xmkt | fx | commodity | equity
    region: str               # US | EA | UK | JP | G10 | EM
    mode: str                 # level (yields, bp) | price
    series: pd.Series
    drivers: Dict[str, pd.Series] = field(default_factory=dict)
    cftc_key: Optional[str] = None
    vol_key: Optional[str] = None      # implied-vol index when one exists
    tenor: Optional[float] = None      # for outright rates
    legs: Optional[List[float]] = None  # tenors for slopes/flies
    quality: str = "live"
    note: str = ""
    long_means: str = ""


def _s(frame, k):
    return D.series(frame, k)


def build(frame: pd.DataFrame) -> Dict[str, Instrument]:
    u: Dict[str, Instrument] = {}
    y = {t: _s(frame, k) for t, k in [(0.25, "ust3m"), (1, "ust1"), (2, "ust2"), (5, "ust5"), (10, "ust10"), (30, "ust30")]}
    one_one = (2 * y[2] - y[1]).dropna(); one_one.name = "1y1y"
    rate_drivers_all = {"1y1y": one_one, "5y": y[5], "10y": y[10]}

    # --- rates outrights ---
    for t, lab in [(2, "UST 2Y"), (5, "UST 5Y"), (10, "UST 10Y"), (30, "UST 30Y")]:
        drv = {k: v for k, v in rate_drivers_all.items() if k != f"{t}y"}
        if t == 2:
            drv = {"1y1y": one_one, "5y": y[5], "10y": y[10]}
        ybp = (y[t] * 100).dropna(); ybp.name = f"ust{t}_bp"
        u[f"ust{t}"] = Instrument(f"ust{t}", lab + " (bp)", "rates", "US", "level", ybp, drv, cftc_key={2: "TU", 5: "FV", 10: "TY", 30: "US"}[t],
                                  vol_key="move", tenor=t, long_means="receive / long the bond")
    # --- slopes & fly (bp) ---
    for a, b in [(2, 5), (2, 10), (5, 30), (10, 30)]:
        s = ((y[b] - y[a]) * 100).dropna(); s.name = f"{a}s{b}s"
        u[f"s{a}{b}"] = Instrument(f"s{a}{b}", f"{a}s{b}s steepener", "rates", "US", "level", s, dict(rate_drivers_all), vol_key="move", legs=[a, b],
                                   long_means="steepener (receive short leg, pay long leg)")
    fly = ((2 * y[5] - y[2] - y[10]) * 100).dropna(); fly.name = "2s5s10s"
    u["fly2510"] = Instrument("fly2510", "2s5s10s fly (belly cheapens +)", "rates", "US", "level", fly, dict(rate_drivers_all), vol_key="move", legs=[2, 5, 10],
                              long_means="receive the belly vs wings")
    # --- UST futures (price) ---
    for k, lab, ck in [("zt", "TU future", "TU"), ("zf", "FV future", "FV"), ("zn", "TY future", "TY"), ("zb", "US future", "US")]:
        u[k] = Instrument(k, lab, "rates_fut", "US", "price", _s(frame, k), {"1y1y": one_one, "5y": y[5], "10y": y[10]}, cftc_key=ck, vol_key="move", long_means="long the future")
    # --- cross-market 10y spreads (monthly OECD mirrors, lagging) ---
    for k, lab, reg in [("de_10y", "US–DE 10Y (RX–TY proxy)", "EA"), ("uk_10y", "US–UK 10Y (G–TY proxy)", "UK"), ("jp_10y", "US–JP 10Y", "JP")]:
        loc = _s(frame, k)
        if len(loc):
            sp = ((y[10].resample("MS").last() - loc.resample("MS").last()) * 100).dropna(); sp.name = lab
            sp = sp.reindex(frame.index, method="ffill").dropna()
            u[f"x_{k}"] = Instrument(f"x_{k}", lab, "xmkt", reg, "level", sp, {"US 10y": y[10], "1y1y": one_one}, quality="proxy",
                                     note="monthly OECD series on FRED, 1–2 months lag", long_means="long US 10Y vs short foreign 10Y (spread narrows −)")
    # --- FX vs USD (price = USD per base; long = long base currency) ---
    fx_defs = [("eurusd", "EUR/USD", "EA", "EUR", "sx5e", "de_10y", "estr"), ("gbpusd", "GBP/USD", "UK", "GBP", "ftse", "uk_10y", "sonia"),
               ("usdjpy", "JPY/USD (inverted)", "JP", "JPY", "nikkei", "jp_10y", "jp_policy"), ("usdchf", "CHF/USD (inverted)", "G10", "CHF", "sx5e", "de_10y", None),
               ("audusd", "AUD/USD", "G10", "AUD", "eem", None, None), ("nzdusd", "NZD/USD", "G10", "NZD", "eem", None, None),
               ("usdcad", "CAD/USD (inverted)", "G10", "CAD", "xle", None, None), ("usdsek", "SEK/USD (inverted)", "G10", None, "sx5e", "de_10y", None),
               ("usdnok", "NOK/USD (inverted)", "G10", None, "xle", None, None), ("usdmxn", "MXN/USD (inverted)", "EM", "MXN", "eem", None, None)]
    for k, lab, reg, ck, eq, r10, pol in fx_defs:
        s = _s(frame, k)
        if not len(s):
            continue
        if k.startswith("usd"):
            s = (1.0 / s); s.name = lab
        eqd = (_s(frame, eq) / _s(frame, "spx")).dropna() if eq else pd.Series(dtype=float)
        drv = {"equity differential": eqd, "US 2Y (inverse)": -y[2], "US 10Y real (inverse)": -_s(frame, "real10")}
        if r10:
            d10 = (_s(frame, r10).reindex(frame.index, method="ffill") - y[10]).dropna()
            drv["10Y differential (lagging)"] = d10
        ins = Instrument(k, lab, "fx", reg, "price", s, drv, cftc_key=ck, long_means="long base currency vs USD")
        ins.note = f"carry from {pol}" if pol else "no public short rate for carry"
        ins.policy_key = pol  # type: ignore[attr-defined]
        u[k] = ins
    # --- commodities ---
    for k, lab, ck, vk in [("brent", "Brent", "CL", "ovx"), ("wti", "WTI", "CL", "ovx"), ("gold", "Gold", "GC", "gvz"), ("copper", "Copper", "HG", None), ("silver", "Silver", "SI", None), ("natgas", "Henry Hub", "NG", None)]:
        s = _s(frame, k)
        if len(s):
            u[k] = Instrument(k, lab, "commodity", "G10", "price", s, {"DXY (inverse)": -_s(frame, "dxy"), "10Y breakeven": _s(frame, "bei10"), "EM equities": _s(frame, "eem")},
                              cftc_key=ck, vol_key=vk, long_means="long the commodity")
    # --- equity indices ---
    for k, lab, reg, ck in [("spx", "S&P 500", "US", "ES"), ("ndx", "Nasdaq 100", "US", "NQ"), ("rut", "Russell 2000", "US", "RTY"), ("sx5e", "Euro Stoxx 50", "EA", None),
                            ("dax", "DAX", "EA", None), ("ftse", "FTSE 100", "UK", None), ("nikkei", "Nikkei 225", "JP", None), ("eem", "EM equities", "EM", None)]:
        s = _s(frame, k)
        if len(s):
            u[k] = Instrument(k, lab, "equity", reg, "price", s, {"10Y real (inverse)": -_s(frame, "real10"), "HY OAS (inverse)": -_s(frame, "hy_oas"), "10Y breakeven": _s(frame, "bei10")},
                              cftc_key=ck, vol_key="vix" if reg == "US" else None, long_means="long the index")
    return u


def adverse_2w_move(ins: Instrument, lookback: int = 252, q: float = 0.95) -> float:
    """95th-percentile adverse 2-week move over the past year, in the instrument's own units
    (bp for levels, % for prices), for a LONG position in the common frame."""
    s = ins.series.dropna().iloc[-lookback - 10:]
    if len(s) < 60:
        return np.nan
    if ins.mode == "level":
        ch = s.diff(10).dropna()
        if ins.legs is not None:          # steepener / belly receiver loses when the spread falls
            adverse = -ch
        else:                             # receiver (or long US vs foreign) loses when the yield/spread rises
            adverse = ch
        return float(np.quantile(adverse, q))
    ret = (np.log(s).diff(10)).dropna() * 100
    return float(-np.quantile(ret, 1 - q))


def price_proxy(ins: Instrument) -> pd.Series:
    """A positive, price-like series that rises when a LONG in the common frame makes money
    (needed by the log-return based trend models). Yields and US-vs-foreign spreads in bp map to
    100 − s/100 (a bond-like index); slopes/flies to 100 + s/100; prices pass through."""
    s = ins.series.dropna()
    if ins.mode == "price":
        return s
    if ins.legs is not None:
        return 100.0 + s / 100.0
    return 100.0 - s / 100.0
