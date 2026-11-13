"""STIR strips and meeting-dated policy-path bootstrap for the Fed, ECB and BoE.

Strip sources (first that works):
  1. Yahoo individual contracts for 30-day fed funds (ZQ<code><yy>.CBT) — refreshed daily.
  2. The most recent IBKR snapshot CSV in data/ibkr_snapshots (ZQ, SR3, Euribor, SONIA).
  3. A strip typed in the app (same schema).

Bootstrap: unknown policy steps j_k at each meeting; the policy rate r(t) = spot + Σ_{eff_k ≤ t} j_k.
Each contract's implied average rate (100 − P) must equal the window average of r(t). Linear in
j, solved by ridge-regularised least squares (3M contracts give fewer equations than meetings,
so the regulariser spreads the residual move across the meetings inside a contract window;
monthly fed funds contracts over-determine the system and are fitted in the least-squares sense).
"""

import glob
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from . import DATA_DIR, calendar, yahoo

MONTH_CODES = {1: "F", 2: "G", 3: "H", 4: "J", 5: "K", 6: "M", 7: "N", 8: "Q", 9: "U", 10: "V", 11: "X", 12: "Z"}
FAMILIES = {
    "ZQ": dict(region="US", ccy="USD", name="30-day fed funds", window="month", rate="EFFR", yahoo=("ZQ", "CBT")),
    "SR3": dict(region="US", ccy="USD", name="3M SOFR", window="imm3m", rate="SOFR", yahoo=None),
    "ER": dict(region="EA", ccy="EUR", name="3M Euribor", window="imm3m", rate="€STR + basis", yahoo=None),
    "SON": dict(region="UK", ccy="GBP", name="3M SONIA", window="imm3m", rate="SONIA", yahoo=None),
}


def third_wednesday(year: int, month: int) -> pd.Timestamp:
    first = pd.Timestamp(year=year, month=month, day=1)
    offset = (2 - first.weekday()) % 7  # Wednesday = 2
    return first + pd.Timedelta(days=offset + 14)


def contract_window(family: str, contract_month: str) -> Tuple[pd.Timestamp, pd.Timestamp]:
    y, m = int(contract_month[:4]), int(contract_month[5:7])
    if FAMILIES[family]["window"] == "month":
        start = pd.Timestamp(year=y, month=m, day=1)
        end = start + pd.offsets.MonthEnd(0)
        return start, end
    start = third_wednesday(y, m)
    ny, nm = (y + (m + 3 - 1) // 12, (m + 3 - 1) % 12 + 1)
    end = third_wednesday(ny, nm) - pd.Timedelta(days=1)
    return start, end


def latest_snapshot_path() -> Optional[str]:
    files = sorted(glob.glob(str(DATA_DIR / "ibkr_snapshots" / "stir_strips_*.csv")))
    return files[-1] if files else None


def load_snapshot(path: Optional[str] = None) -> pd.DataFrame:
    path = path or latest_snapshot_path()
    if not path:
        return pd.DataFrame()
    df = pd.read_csv(path, parse_dates=["last_trading_date", "close_date"])
    df["contract_month"] = df["contract_month"].astype(str)
    return df


def yahoo_zq_strip(n_months: int = 14) -> pd.DataFrame:
    """Refresh the fed funds strip from Yahoo's individual ZQ contracts (daily history)."""
    today = pd.Timestamp.today().normalize()
    months = []
    for i in range(n_months):
        d = (today + pd.DateOffset(months=i))
        months.append((d.year, d.month))
    codes = [f"{MONTH_CODES[m]}{str(y)[-2:]}" for y, m in months]
    frame = yahoo.futures_strip("ZQ", "CBT", codes, years=1)
    rows = []
    for (y, m), code in zip(months, codes):
        t = f"ZQ{code}.CBT"
        if t in frame.columns and frame[t].notna().any():
            s = frame[t].dropna()
            rows.append(dict(contract=f"ZQ{code}", exchange="CBOT", family="ZQ", ccy="USD", contract_month=f"{y}-{m:02d}",
                             last_trading_date=pd.Timestamp(year=y, month=m, day=1) + pd.offsets.MonthEnd(0),
                             close=float(s.iloc[-1]), close_date=s.index[-1], source="Yahoo", status="live",
                             chg_1d=float(s.iloc[-1] - s.iloc[-2]) if len(s) > 1 else np.nan,
                             chg_1w=float(s.iloc[-1] - s.iloc[-6]) if len(s) > 5 else np.nan))
    return pd.DataFrame(rows)


def strip(family: str, prefer_yahoo: bool = True) -> pd.DataFrame:
    """Best available strip for a family, with window dates and implied rate."""
    df = pd.DataFrame()
    if family == "ZQ" and prefer_yahoo:
        try:
            df = yahoo_zq_strip()
        except Exception:
            df = pd.DataFrame()
    if df.empty:
        snap = load_snapshot()
        df = snap[snap["family"] == family].copy() if not snap.empty else pd.DataFrame()
    if df.empty:
        return df
    df = df.sort_values("contract_month").reset_index(drop=True)
    win = [contract_window(family, cm) for cm in df["contract_month"]]
    df["win_start"] = [w[0] for w in win]
    df["win_end"] = [w[1] for w in win]
    df["implied_rate"] = 100.0 - df["close"]
    return df


def bootstrap(family: str, strip_df: pd.DataFrame, spot_rate: float, basis_bp: float = 0.0,
              ridge: float = 1e-3, horizon_days: int = 800) -> pd.DataFrame:
    """Solve meeting-by-meeting steps so the policy-rate path reprices the strip.

    spot_rate: today's overnight rate in the contract's own terms (EFFR for ZQ, SOFR for SR3,
    SONIA for SON, €STR for ER). basis_bp: constant added to the overnight path to reach the
    contract's reference rate (e.g. 3M Euribor over €STR). Returns a per-meeting table.
    """
    if strip_df.empty:
        return pd.DataFrame()
    region = FAMILIES[family]["region"]
    today = pd.Timestamp.today().normalize()
    end = min(strip_df["win_end"].max(), today + pd.Timedelta(days=horizon_days))
    mts = calendar.meetings(region, start=today, end=end)
    if mts.empty:
        return pd.DataFrame()
    eff = mts["effective"].values
    contracts = strip_df[strip_df["win_end"] >= today].copy()
    A = np.zeros((len(contracts), len(mts)))
    b = np.zeros(len(contracts))
    for i, (_, c) in enumerate(contracts.iterrows()):
        days = pd.date_range(max(c["win_start"], today), c["win_end"], freq="D")
        n = len(days)
        if n == 0:
            continue
        for k, e in enumerate(eff):
            A[i, k] = (days >= e).sum() / n
        # the part of the window already elapsed is assumed to have realised at the spot rate
        full = pd.date_range(c["win_start"], c["win_end"], freq="D")
        frac_future = n / len(full)
        b[i] = (c["implied_rate"] - basis_bp / 100.0 - spot_rate) / max(frac_future, 1e-9)
    # ridge least squares: minimise ||A j - b||² + ridge ||j||²  (j in percentage points)
    AtA = A.T @ A + ridge * np.eye(A.shape[1])
    j = np.linalg.solve(AtA, A.T @ b)
    fitted = A @ j
    out = mts[["date", "event", "status", "effective"]].copy()
    out["step_bp"] = j * 100.0
    out["cum_bp"] = out["step_bp"].cumsum()
    out["rate_after"] = spot_rate + out["cum_bp"] / 100.0
    out["p_move_25"] = (out["step_bp"] / 25.0).clip(-2, 2)
    out.attrs["fit_error_bp"] = float(np.sqrt(np.mean((fitted - b) ** 2)) * 100.0) if len(b) else np.nan
    out.attrs["n_contracts"] = int(len(contracts))
    out.attrs["spot"] = spot_rate
    out.attrs["basis_bp"] = basis_bp
    return out


def path_from_steps(steps: pd.DataFrame, spot_rate: float, start: pd.Timestamp, end: pd.Timestamp) -> pd.Series:
    days = pd.date_range(start, end, freq="D")
    r = pd.Series(spot_rate, index=days)
    for _, m in steps.iterrows():
        r[days >= m["effective"]] += m["step_bp"] / 100.0
    return r


def reprice_strip(family: str, strip_df: pd.DataFrame, steps: pd.DataFrame, spot_rate: float, basis_bp: float = 0.0) -> pd.DataFrame:
    """Given a meeting-step path (market or internal), what should each contract trade at?"""
    if strip_df.empty or steps.empty:
        return strip_df
    today = pd.Timestamp.today().normalize()
    path = path_from_steps(steps, spot_rate, min(strip_df["win_start"].min(), today), strip_df["win_end"].max())
    out = strip_df.copy()
    fair = []
    for _, c in out.iterrows():
        w = path[(path.index >= c["win_start"]) & (path.index <= c["win_end"])]
        fair.append(100.0 - (w.mean() + basis_bp / 100.0))
    out["fair_price"] = fair
    out["ev_ticks_bp"] = (out["fair_price"] - out["close"]) * 100.0
    return out


def implied_event_move(iv_with: float, t_with_days: float, iv_without: float, t_without_days: float) -> float:
    """√(IV²_with τ_with − IV²_without τ_without), IVs annualised in the same units (bp or %)."""
    a = iv_with ** 2 * t_with_days / 365.0 - iv_without ** 2 * t_without_days / 365.0
    return float(np.sqrt(max(a, 0.0)))
