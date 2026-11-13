"""Scenario tree → EV → Kelly, and simple payoff structures in rate space (bp)."""

from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd


def normalise(probs: List[float]) -> np.ndarray:
    p = np.asarray(probs, dtype=float)
    p = np.clip(p, 0, None)
    return p / p.sum() if p.sum() > 0 else np.full(len(p), 1.0 / len(p))


def moments(probs, outcomes) -> Dict[str, float]:
    p = normalise(probs); x = np.asarray(outcomes, dtype=float)
    mu = float((p * x).sum())
    var = float((p * (x - mu) ** 2).sum())
    ent = float(-(p[p > 0] * np.log(p[p > 0])).sum())
    skew = float((p * (x - mu) ** 3).sum() / var ** 1.5) if var > 0 else 0.0
    return dict(mean=mu, var=var, std=float(np.sqrt(var)), entropy=ent, skew=skew)


def kelly_fraction(probs, returns, f_max: Optional[float] = None, grid: int = 2001) -> Dict[str, float]:
    """f* = argmax Σ p_j ln(1 + f r_j). `returns` are P&L per unit of capital committed (−1 = total loss).
    Returns f*, half-Kelly, expected log-growth at f* and the EV."""
    p = normalise(probs); r = np.asarray(returns, dtype=float)
    ev = float((p * r).sum())
    if ev <= 0 or (r >= 0).all():
        return dict(f_star=0.0 if ev <= 0 else np.inf, half=0.0, growth=0.0, ev=ev)
    worst = r.min()
    cap = f_max if f_max is not None else 0.999 / abs(worst)
    fs = np.linspace(0, cap, grid)
    with np.errstate(divide="ignore", invalid="ignore"):
        g = np.array([(p * np.log1p(f * r)).sum() if (1 + f * r > 0).all() else -np.inf for f in fs])
    i = int(np.nanargmax(g))
    return dict(f_star=float(fs[i]), half=float(fs[i] / 2), growth=float(g[i]), ev=ev)


# --- payoffs in rate space: positive quantity = long the rate (short the future) -------------
def leg_payoff(leg: dict, rate_after: np.ndarray) -> np.ndarray:
    """leg = {type: linear|call|put, strike, qty, premium_bp}; rates in %, premium in bp.
    'call' pays max(rate − K, 0) in bp (a put on the futures price); 'put' pays max(K − rate, 0)."""
    k = leg.get("strike", 0.0); q = leg.get("qty", 1.0); prem = leg.get("premium_bp", 0.0)
    if leg["type"] == "linear":
        return q * ((rate_after - k) * 100.0)
    if leg["type"] == "call":
        return q * (np.maximum(rate_after - k, 0) * 100.0 - prem)
    if leg["type"] == "put":
        return q * (np.maximum(k - rate_after, 0) * 100.0 - prem)
    raise ValueError(leg["type"])


def structure_pnl(legs: List[dict], rate_after: np.ndarray) -> np.ndarray:
    return sum(leg_payoff(l, rate_after) for l in legs)


def evaluate_structure(name: str, legs: List[dict], probs, rate_after, market_price_bp: float = 0.0) -> Dict[str, float]:
    """Per structure: expected P&L (bp), max loss/gain, EV vs market, Kelly on the loss-normalised
    return (fraction of the loss budget to commit)."""
    p = normalise(probs); r = np.asarray(rate_after, dtype=float)
    pnl = structure_pnl(legs, r) - market_price_bp
    mx_loss = float(pnl.min()); mx_gain = float(pnl.max())
    ev = float((p * pnl).sum())
    if mx_loss < 0:
        k = kelly_fraction(p, pnl / abs(mx_loss))
    else:
        k = dict(f_star=np.inf, half=np.inf, growth=np.nan, ev=ev)
    prob_profit = float(p[pnl > 0].sum())
    return dict(structure=name, ev_bp=ev, max_loss_bp=mx_loss, max_gain_bp=mx_gain, p_profit=prob_profit,
                kelly=k["f_star"], half_kelly=k["half"], pnl=pnl)


def scenario_table(scenarios: List[dict]) -> pd.DataFrame:
    """scenarios: list of {name, prob, outcome} → normalised table with cumulative probability."""
    df = pd.DataFrame(scenarios)
    df["prob"] = normalise(df["prob"].tolist())
    df["cum_prob"] = df["prob"].cumsum()
    return df


def straddle_breakeven_bp(premium_bp: float) -> float:
    return premium_bp


def normal_pdf_grid(mean: float, std: float, lo: float, hi: float, n: int = 201) -> Tuple[np.ndarray, np.ndarray]:
    x = np.linspace(lo, hi, n)
    pdf = np.exp(-0.5 * ((x - mean) / std) ** 2) / (std * np.sqrt(2 * np.pi))
    return x, pdf / pdf.sum()


def discretise_normal(mean: float, std: float, grid_bp: List[float]) -> np.ndarray:
    """Probability mass of a normal at each grid point (bins at midpoints)."""
    g = np.asarray(grid_bp, dtype=float)
    edges = np.concatenate([[-np.inf], (g[1:] + g[:-1]) / 2, [np.inf]])
    from math import erf, sqrt
    cdf = lambda v: 0.5 * (1 + erf((v - mean) / (std * sqrt(2)))) if np.isfinite(v) else (1.0 if v > 0 else 0.0)
    return np.array([cdf(edges[i + 1]) - cdf(edges[i]) for i in range(len(g))])
