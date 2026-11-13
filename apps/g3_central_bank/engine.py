"""Valuation helpers built on datahub.stir: window fractions, linear repricing, scenario trees."""

import itertools
from typing import List, Sequence, Tuple

import numpy as np
import pandas as pd

from datahub import calendar, kelly


def window_fractions(family: str, strip_df: pd.DataFrame, meetings: pd.DataFrame) -> Tuple[np.ndarray, pd.DataFrame]:
    """A[i,k] = share of contract i's remaining window after meeting k becomes effective; also the
    share of the window still in the future (elapsed part assumed realised at spot)."""
    today = pd.Timestamp.today().normalize()
    contracts = strip_df[strip_df["win_end"] >= today].copy().reset_index(drop=True)
    eff = pd.to_datetime(meetings["effective"]).values if not meetings.empty else np.array([], dtype="datetime64[ns]")
    A = np.zeros((len(contracts), len(eff)))
    frac_future = np.ones(len(contracts))
    for i, c in contracts.iterrows():
        days = pd.date_range(max(c["win_start"], today), c["win_end"], freq="D")
        full = pd.date_range(c["win_start"], c["win_end"], freq="D")
        n = len(days)
        frac_future[i] = n / max(len(full), 1)
        for k, e in enumerate(eff):
            A[i, k] = (days >= e).sum() / max(n, 1)
    contracts["frac_future"] = frac_future
    return A, contracts


def fair_prices(contracts: pd.DataFrame, A: np.ndarray, spot: float, basis_bp: float, steps_bp: Sequence[float]) -> np.ndarray:
    """Contract fair price under a step path (bp per meeting). The window average rate is
    spot + basis + frac_future·(A·j); elapsed days already sit at spot."""
    j = np.asarray(steps_bp, dtype=float) / 100.0
    avg = spot + basis_bp / 100.0 + contracts["frac_future"].values * (A @ j)
    return 100.0 - avg


def rate_after_meeting(spot: float, steps_bp: Sequence[float], m_index: int) -> float:
    return spot + float(np.sum(np.asarray(steps_bp[: m_index + 1], dtype=float))) / 100.0


def build_tree(per_meeting: List[Tuple[Sequence[float], Sequence[float]]]) -> pd.DataFrame:
    """per_meeting: list of (outcomes_bp, probs) for meetings 1..N. Returns the joint tree
    (independent branches), one row per path with columns m1..mN, prob, cum_bp."""
    if not per_meeting:
        return pd.DataFrame()
    outs = [list(o) for o, _ in per_meeting]
    probs = [kelly.normalise(list(p)) for _, p in per_meeting]
    rows = []
    for combo in itertools.product(*[range(len(o)) for o in outs]):
        p = 1.0
        steps = []
        for m, idx in enumerate(combo):
            p *= probs[m][idx]
            steps.append(outs[m][idx])
        rows.append(dict(**{f"m{m + 1}": s for m, s in enumerate(steps)}, prob=p, cum_bp=float(np.sum(steps))))
    df = pd.DataFrame(rows)
    df = df[df["prob"] > 0].reset_index(drop=True)
    return df


def normal_probs(center_bp: float, std_bp: float, outcomes_bp: Sequence[float]) -> np.ndarray:
    return kelly.discretise_normal(center_bp, max(std_bp, 1e-6), list(outcomes_bp))


def expiry_events(contract_last_trade: pd.Timestamp, region: str, cal: pd.DataFrame) -> pd.DataFrame:
    today = pd.Timestamp.today().normalize()
    w = cal[(cal["date"] >= today) & (cal["date"] <= contract_last_trade) & (cal["region"].isin({region, "US"}))]
    return w.sort_values("date")


def carries(events: pd.DataFrame) -> str:
    tags = []
    if (events["type"] == "meeting").any():
        tags.append("central-bank risk")
    if ((events["type"] == "release") & (events["tier"] == 1)).any():
        tags.append("data risk")
    if not tags:
        tags.append("market-perception / vol risk only")
    return ", ".join(tags)


def kelly_on_pnl(probs: Sequence[float], pnl_bp: np.ndarray) -> dict:
    p = kelly.normalise(list(probs))
    pnl = np.asarray(pnl_bp, dtype=float)
    ev = float((p * pnl).sum())
    mx_loss, mx_gain = float(pnl.min()), float(pnl.max())
    if mx_loss < 0:
        k = kelly.kelly_fraction(p, pnl / abs(mx_loss))
        f, h = k["f_star"], k["half"]
    else:
        f, h = np.inf, np.inf
    return dict(ev_bp=ev, max_loss_bp=mx_loss, max_gain_bp=mx_gain, p_profit=float(p[pnl > 0].sum()), kelly=f, half_kelly=h, pnl=pnl)
