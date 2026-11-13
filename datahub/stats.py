"""Statistics used across the three processes: z-scores, percentiles, vol estimators,
univariate rolling OLS, PCA residuals, tanh scaling, winsorising."""

from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd


def winsorize(s: pd.Series, k: float = 5.0) -> pd.Series:
    sd = s.std()
    if not np.isfinite(sd) or sd == 0:
        return s
    m = s.mean()
    return s.clip(lower=m - k * sd, upper=m + k * sd)


def zscore(s: pd.Series, window: int = 504, min_periods: Optional[int] = None, clip: float = 3.0) -> pd.Series:
    """Rolling z-score (default 2y of business days), clipped at ±clip."""
    mp = min_periods or max(20, window // 4)
    mu = s.rolling(window, min_periods=mp).mean()
    sd = s.rolling(window, min_periods=mp).std()
    z = (s - mu) / sd.replace(0, np.nan)
    return z.clip(-clip, clip)


def last_z(s: pd.Series, window: int = 504) -> float:
    z = zscore(s.dropna(), window)
    return float(z.dropna().iloc[-1]) if z.notna().any() else float("nan")


def percentile(s: pd.Series, window: int = 1260) -> pd.Series:
    """Rolling percentile rank of the last value within the window (0-100)."""
    def rank(x):
        return 100.0 * (x[:-1] < x[-1]).mean() if len(x) > 1 else np.nan
    return s.rolling(window, min_periods=max(20, window // 5)).apply(rank, raw=True)


def last_percentile(s: pd.Series, window: int = 1260) -> float:
    s = s.dropna()
    if len(s) < 20:
        return float("nan")
    w = s.iloc[-window:]
    return float(100.0 * (w.iloc[:-1] < w.iloc[-1]).mean())


def log_returns(prices: pd.DataFrame) -> pd.DataFrame:
    return np.log(prices).diff()


def ewma_vol(returns: pd.Series, lam: float = 0.94, floor_days: int = 60, annualise: int = 252) -> pd.Series:
    """EWMA volatility (RiskMetrics λ) with a 60-day simple floor, annualised."""
    var = returns.pow(2).ewm(alpha=1 - lam, min_periods=20).mean()
    simple = returns.rolling(floor_days, min_periods=20).var()
    out = np.sqrt(np.maximum(var, simple.fillna(var))) * np.sqrt(annualise)
    return out


def realised_vol(returns: pd.Series, window: int = 20, annualise: int = 252) -> pd.Series:
    return returns.rolling(window).std() * np.sqrt(annualise)


def yang_zhang(ohlc: pd.DataFrame, window: int = 60, annualise: int = 252) -> pd.Series:
    """Yang-Zhang volatility estimator from Open/High/Low/Close."""
    o, h, l, c = [np.log(ohlc[x]) for x in ("Open", "High", "Low", "Close")]
    co = c - o
    oc_prev = o - c.shift(1)
    rs = (h - c) * (h - o) + (l - c) * (l - o)
    k = 0.34 / (1.34 + (window + 1) / (window - 1))
    v_open = oc_prev.rolling(window).var()
    v_close = co.rolling(window).var()
    v_rs = rs.rolling(window).mean()
    return np.sqrt(np.maximum(v_open + k * v_close + (1 - k) * v_rs, 0)) * np.sqrt(annualise)


def rolling_ols(y: pd.Series, x: pd.Series, window: int = 60) -> pd.DataFrame:
    """Rolling univariate OLS of y on x. Returns alpha, beta, r2, resid (last point), resid_z."""
    df = pd.concat([y, x], axis=1, keys=["y", "x"]).dropna()
    if len(df) < window:
        return pd.DataFrame(columns=["alpha", "beta", "r2", "resid"])
    xm = df["x"].rolling(window).mean()
    ym = df["y"].rolling(window).mean()
    cov = (df["x"] * df["y"]).rolling(window).mean() - xm * ym
    varx = df["x"].rolling(window).var(ddof=0)
    vary = df["y"].rolling(window).var(ddof=0)
    beta = cov / varx.replace(0, np.nan)
    alpha = ym - beta * xm
    r2 = (cov ** 2) / (varx * vary).replace(0, np.nan)
    resid = df["y"] - (alpha + beta * df["x"])
    out = pd.DataFrame({"alpha": alpha, "beta": beta, "r2": r2, "resid": resid})
    out["resid_z"] = resid / resid.rolling(window).std().replace(0, np.nan)
    return out


def univariate_residuals(y: pd.Series, drivers: Dict[str, pd.Series], window: int = 60,
                         r2_floor: float = 0.05, r2_ceiling: float = 0.999) -> pd.DataFrame:
    """One rolling univariate regression per driver (never a joint fit). Returns the last row per
    driver: beta, R², residual z. Near-perfect or near-zero fits return NaN z (not a spurious extreme)."""
    rows = []
    for name, x in drivers.items():
        res = rolling_ols(y, x, window)
        if res.empty or res["resid_z"].dropna().empty:
            rows.append(dict(driver=name, beta=np.nan, r2=np.nan, resid_z=np.nan, note="insufficient data"))
            continue
        last = res.dropna().iloc[-1]
        z = last["resid_z"]
        note = ""
        if last["r2"] < r2_floor:
            z, note = np.nan, "R² too low — unmodelled"
        elif last["r2"] > r2_ceiling:
            z, note = np.nan, "degenerate fit"
        rows.append(dict(driver=name, beta=last["beta"], r2=last["r2"], resid_z=z, note=note))
    out = pd.DataFrame(rows)
    return out


def composite_residual(table: pd.DataFrame) -> Tuple[float, bool]:
    """Median residual z across drivers and a driver-disagreement flag (sign split with |z|≥1)."""
    z = table["resid_z"].dropna()
    if z.empty:
        return float("nan"), False
    disagree = bool((z[z.abs() >= 1] > 0).any() and (z[z.abs() >= 1] < 0).any())
    return float(z.median()), disagree


def pca_residual(levels: pd.DataFrame, n_components: int = 3, window: int = 504) -> pd.DataFrame:
    """Fit PCA on changes of a set of series over the trailing window; return the residual of the
    latest level vs the n_components reconstruction, in z units, per column."""
    df = levels.dropna().iloc[-window:]
    if len(df) < 60 or df.shape[1] <= n_components:
        return pd.DataFrame(columns=["pc_resid", "pc_resid_z"])
    x = df - df.mean()
    u, s, vt = np.linalg.svd(x.values, full_matrices=False)
    comps = vt[:n_components]
    recon = (x.values @ comps.T) @ comps
    resid = x.values - recon
    resid = pd.DataFrame(resid, index=df.index, columns=df.columns)
    z = resid.iloc[-1] / resid.std().replace(0, np.nan)
    explained = (s ** 2) / (s ** 2).sum()
    out = pd.DataFrame({"pc_resid": resid.iloc[-1], "pc_resid_z": z})
    out.attrs["explained"] = explained[:n_components].tolist()
    return out


def tanh_score(z: float, scale: float = 2.0) -> float:
    """Map a z-score to −100…+100 with 100·tanh(z/scale)."""
    if z is None or not np.isfinite(z):
        return float("nan")
    return float(100.0 * np.tanh(z / scale))


def horizon_change(s: pd.Series, days: int, mode: str = "price") -> float:
    s = s.dropna()
    if len(s) <= days:
        return float("nan")
    a, b = s.iloc[-1 - days], s.iloc[-1]
    return float(np.log(b / a)) if mode == "price" else float(b - a)


def momentum_sign(s: pd.Series) -> float:
    """TSMOM cross-check: ⅓[sign(r1M)+sign(r3M)+sign(r12M)]."""
    vals = [horizon_change(s, d) for d in (21, 63, 252)]
    vals = [np.sign(v) for v in vals if np.isfinite(v)]
    return float(np.mean(vals)) if vals else float("nan")


def ewmac_barbell(prices: pd.Series, vol: Optional[pd.Series] = None,
                  speeds=(8, 32, 64), weights=(0.42, 0.16, 0.42), cap: float = 2.0) -> pd.Series:
    """CTA signal (a): Σ w_k · clip(x_k/cap, −1, 1), x_k = [EWMA(n_k) − EWMA(4n_k)] / σ·P."""
    p = prices.dropna()
    if vol is None:
        vol = ewma_vol(np.log(p).diff(), annualise=1)  # daily vol
    sig = pd.Series(0.0, index=p.index)
    for n, w in zip(speeds, weights):
        fast = p.ewm(span=n).mean()
        slow = p.ewm(span=4 * n).mean()
        x = (fast - slow) / (p * vol.reindex(p.index) * np.sqrt(n)).replace(0, np.nan)
        sig = sig + w * (x / cap).clip(-1, 1)
    return sig


def breakout(prices: pd.Series, window: int = 100) -> pd.Series:
    p = prices.dropna()
    hi = p.rolling(window).max()
    lo = p.rolling(window).min()
    return ((2 * p - hi - lo) / (hi - lo).replace(0, np.nan)).clip(-1, 1)


def cta_ensemble(prices: pd.Series) -> Dict[str, float]:
    """s = ⅓(s_a + s_b + s_c): EWMAC barbell, TSMOM and breakout; plus agree/split flag."""
    p = prices.dropna()
    if len(p) < 300:
        return dict(ewmac=np.nan, tsmom=np.nan, breakout=np.nan, ensemble=np.nan, split=False, mature=False)
    a = ewmac_barbell(p)
    b = momentum_sign(p)
    c = breakout(p)
    a_last = float(a.iloc[-1]); c_last = float(c.dropna().iloc[-1]) if c.notna().any() else np.nan
    ens = float(np.nanmean([a_last, b, c_last]))
    split = bool(np.sign(a_last) != np.sign(b)) if np.isfinite(b) and b != 0 else False
    mature = bool((a.abs().iloc[-20:] >= 0.75).all())
    return dict(ewmac=a_last, tsmom=b, breakout=c_last, ensemble=ens, split=split, mature=mature)


def beta_dollar_per_sigma(y: pd.Series, x: pd.Series, window: int = 60, notional: float = 1.0) -> Dict[str, float]:
    """Univariate 60D beta of y on x, expressed per 1σ daily move of x, times a notional."""
    res = rolling_ols(y, x, window)
    if res.empty or res.dropna().empty:
        return dict(beta=np.nan, sigma_x=np.nan, dollar_per_sigma=np.nan, r2=np.nan)
    last = res.dropna().iloc[-1]
    sx = x.dropna().iloc[-window:].std()
    return dict(beta=float(last["beta"]), sigma_x=float(sx), dollar_per_sigma=float(last["beta"] * sx * notional), r2=float(last["r2"]))
