"""CFTC Commitments of Traders (Traders in Financial Futures + legacy) positioning.

Order of attempts:
  1. CFTC Socrata API (publicreporting.cftc.gov) — blocked in some networks.
  2. Local files in data/cftc/: annual "FinFutYY.txt" / "deacotYY" zips or CSVs downloaded from
     https://www.cftc.gov/MarketReports/CommitmentsofTraders/HistoricalCompressed/index.htm
  3. Nothing → empty frame with a clear status; apps show the positioning block as *unavailable*
     and never fake it.

Metrics follow the FX / Thematic processes: net leveraged-fund (TFF) or non-commercial (legacy)
position, z on 156 weeks, net/OI, crowding = |z| ≥ 1.5 and |net/OI| ≥ 80th percentile, weekly Δ z,
"built-by" tag (new longs / long liquidation / new shorts / short covering).
"""

import glob
import io
import zipfile
from typing import Dict, Optional

import numpy as np
import pandas as pd
import requests

from . import DATA_DIR
from .cache import DiskCache

_cache = DiskCache(ttl_hours=24)
SOCRATA_TFF = "https://publicreporting.cftc.gov/resource/gpe5-46if.json"
SOCRATA_LEGACY = "https://publicreporting.cftc.gov/resource/6dca-aqww.json"

# CFTC market names (TFF, futures only) -> our keys
TFF_MARKETS: Dict[str, str] = {
    "EURO FX - CHICAGO MERCANTILE EXCHANGE": "EUR", "JAPANESE YEN - CHICAGO MERCANTILE EXCHANGE": "JPY",
    "BRITISH POUND - CHICAGO MERCANTILE EXCHANGE": "GBP", "CANADIAN DOLLAR - CHICAGO MERCANTILE EXCHANGE": "CAD",
    "SWISS FRANC - CHICAGO MERCANTILE EXCHANGE": "CHF", "AUSTRALIAN DOLLAR - CHICAGO MERCANTILE EXCHANGE": "AUD",
    "NZ DOLLAR - CHICAGO MERCANTILE EXCHANGE": "NZD", "MEXICAN PESO - CHICAGO MERCANTILE EXCHANGE": "MXN",
    "USD INDEX - ICE FUTURES U.S.": "DXY", "UST 2Y NOTE - CHICAGO BOARD OF TRADE": "TU",
    "UST 5Y NOTE - CHICAGO BOARD OF TRADE": "FV", "UST 10Y NOTE - CHICAGO BOARD OF TRADE": "TY",
    "UST BOND - CHICAGO BOARD OF TRADE": "US", "ULTRA UST BOND - CHICAGO BOARD OF TRADE": "WN",
    "SOFR-3M - CHICAGO MERCANTILE EXCHANGE": "SR3", "FED FUNDS - CHICAGO BOARD OF TRADE": "ZQ",
    "E-MINI S&P 500 - CHICAGO MERCANTILE EXCHANGE": "ES", "NASDAQ MINI - CHICAGO MERCANTILE EXCHANGE": "NQ",
    "RUSSELL E-MINI - CHICAGO MERCANTILE EXCHANGE": "RTY", "VIX FUTURES - CBOE FUTURES EXCHANGE": "VX",
}
LEGACY_MARKETS: Dict[str, str] = {
    "GOLD - COMMODITY EXCHANGE INC.": "GC", "SILVER - COMMODITY EXCHANGE INC.": "SI", "COPPER-GRADE #1 - COMMODITY EXCHANGE INC.": "HG",
    "WTI-PHYSICAL - NEW YORK MERCANTILE EXCHANGE": "CL", "CRUDE OIL, LIGHT SWEET-WTI - ICE FUTURES EUROPE": "CL_ICE",
    "NATURAL GAS - NEW YORK MERCANTILE EXCHANGE": "NG",
}


def _socrata(url: str, names: Dict[str, str], since: str) -> pd.DataFrame:
    where = " OR ".join(f"market_and_exchange_names='{n}'" for n in names)
    params = {"$where": f"({where}) AND report_date_as_yyyy_mm_dd >= '{since}'", "$limit": 50000}
    r = requests.get(url, params=params, timeout=30)
    r.raise_for_status()
    df = pd.DataFrame(r.json())
    return df


def _from_local() -> pd.DataFrame:
    """Read every CSV / TXT / ZIP under data/cftc and concatenate (TFF 'FinFut' and legacy 'deacot')."""
    frames = []
    for path in glob.glob(str(DATA_DIR / "cftc" / "*")):
        try:
            if path.lower().endswith(".zip"):
                with zipfile.ZipFile(path) as z:
                    for n in z.namelist():
                        if n.lower().endswith((".txt", ".csv")):
                            frames.append(pd.read_csv(io.BytesIO(z.read(n)), low_memory=False))
            elif path.lower().endswith((".txt", ".csv")):
                frames.append(pd.read_csv(path, low_memory=False))
        except Exception:
            continue
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def _normalise(df: pd.DataFrame) -> pd.DataFrame:
    """Return long frame: date, key, net, oi, long, short, category."""
    if df.empty:
        return df
    cols = {c.lower().strip(): c for c in df.columns}
    name_col = next((cols[c] for c in cols if "market_and_exchange" in c), None)
    date_col = next((cols[c] for c in cols if "report_date_as_yyyy" in c or c == "as_of_date_in_form_yyyy-mm-dd"), None)
    oi_col = next((cols[c] for c in cols if c.startswith("open_interest_all") or c == "open_interest_all"), None)
    if not (name_col and date_col and oi_col):
        return pd.DataFrame()
    out = []
    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
    for src_name, key in {**TFF_MARKETS, **LEGACY_MARKETS}.items():
        sub = df[df[name_col].astype(str).str.upper().str.strip() == src_name]
        if sub.empty:
            continue
        lev_l = next((cols[c] for c in cols if c in ("lev_money_positions_long_all", "lev_money_positions_long")), None)
        lev_s = next((cols[c] for c in cols if c in ("lev_money_positions_short_all", "lev_money_positions_short")), None)
        nc_l = next((cols[c] for c in cols if c in ("noncomm_positions_long_all", "noncommercial_positions_long_all", "noncomm_positions_long")), None)
        nc_s = next((cols[c] for c in cols if c in ("noncomm_positions_short_all", "noncommercial_positions_short_all", "noncomm_positions_short")), None)
        if lev_l and lev_s and sub[lev_l].notna().any():
            L, S, cat = pd.to_numeric(sub[lev_l], errors="coerce"), pd.to_numeric(sub[lev_s], errors="coerce"), "leveraged_funds"
        elif nc_l and nc_s:
            L, S, cat = pd.to_numeric(sub[nc_l], errors="coerce"), pd.to_numeric(sub[nc_s], errors="coerce"), "non_commercial"
        else:
            continue
        out.append(pd.DataFrame({"date": sub[date_col].values, "key": key, "long": L.values, "short": S.values,
                                 "net": (L - S).values, "oi": pd.to_numeric(sub[oi_col], errors="coerce").values, "category": cat}))
    if not out:
        return pd.DataFrame()
    long = pd.concat(out, ignore_index=True).dropna(subset=["date"]).sort_values(["key", "date"])
    return long.drop_duplicates(["key", "date"], keep="last")


def load(since: str = "2010-01-01", use_cache: bool = True) -> Dict[str, object]:
    """Return {'data': long frame, 'source': str, 'status': str}."""
    if use_cache and _cache.fresh("cftc_long"):
        cached = _cache.read("cftc_long")
        if cached is not None and not cached.empty:
            return dict(data=cached, source=cached.attrs.get("source", "cache"), status="loaded (cache)")
    try:
        tff = _socrata(SOCRATA_TFF, TFF_MARKETS, since)
        leg = _socrata(SOCRATA_LEGACY, LEGACY_MARKETS, since)
        long = _normalise(pd.concat([tff, leg], ignore_index=True))
        if not long.empty:
            long.attrs["source"] = "CFTC Socrata API"
            _cache.write("cftc_long", long)
            return dict(data=long, source="CFTC Socrata API", status="loaded")
    except Exception as error:
        api_error = f"{type(error).__name__}"
    else:
        api_error = "empty"
    local = _normalise(_from_local())
    if not local.empty:
        local.attrs["source"] = "local files in data/cftc"
        _cache.write("cftc_long", local)
        return dict(data=local, source="local files in data/cftc", status=f"loaded from local files (API: {api_error})")
    return dict(data=pd.DataFrame(), source="none",
                status=f"unavailable — CFTC API unreachable ({api_error}); drop FinFutYY / deacotYY files in data/cftc")


def metrics(long: pd.DataFrame, z_weeks: int = 156) -> pd.DataFrame:
    """One row per key: net, net/OI, z(156w), weekly Δ, Δz, pct rank, crowding flag, built-by tag."""
    if long.empty:
        return pd.DataFrame()
    rows = []
    for key, g in long.groupby("key"):
        g = g.sort_values("date").set_index("date")
        net = g["net"].astype(float); oi = g["oi"].astype(float).replace(0, np.nan)
        ratio = net / oi
        mu, sd = net.rolling(z_weeks, min_periods=52).mean(), net.rolling(z_weeks, min_periods=52).std()
        z = ((net - mu) / sd).iloc[-1] if sd.notna().any() else np.nan
        d_net = net.diff()
        dz = (d_net.iloc[-1] / d_net.rolling(52).std().iloc[-1]) if len(d_net) > 52 else np.nan
        r_pct = 100 * (ratio.iloc[-z_weeks:].abs() < abs(ratio.iloc[-1])).mean() if len(ratio) > 10 else np.nan
        crowd = bool(abs(z) >= 1.5 and r_pct >= 80) if np.isfinite(z) and np.isfinite(r_pct) else False
        dl, ds = g["long"].diff().iloc[-1], g["short"].diff().iloc[-1]
        if np.isfinite(dl) and np.isfinite(ds):
            built = ("new longs" if dl > 0 and dl >= -ds else "short covering" if ds < 0 else "new shorts" if ds > 0 and ds >= -dl else "long liquidation")
        else:
            built = ""
        rows.append(dict(key=key, date=g.index[-1].date(), category=g["category"].iloc[-1], net=net.iloc[-1], oi=oi.iloc[-1],
                         net_oi=ratio.iloc[-1], z=z, weekly_change=d_net.iloc[-1], dz=dz, ratio_pct=r_pct, crowded=crowd, built_by=built))
    return pd.DataFrame(rows)
