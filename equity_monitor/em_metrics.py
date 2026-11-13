"""Calculations for the Equity Monitor: returns, betas, volatility, breadth, earnings reactions, signals."""

import calendar
import math
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd

TRADING_DAYS = {"1D": 1, "5D": 5, "1M": 21, "3M": 63, "6M": 126, "1Y": 252}


def f(x):
    """float or None (never NaN)."""
    try:
        if x is None:
            return None
        x = float(x)
        return None if (math.isnan(x) or math.isinf(x)) else x
    except Exception:  # noqa: BLE001
        return None


# --------------------------------------------------------------------------- currency

def to_usd(series: pd.Series, currency: str, fx: pd.DataFrame) -> pd.Series:
    """Convert a price series into USD using EURUSD / GBPUSD (GBp = pence)."""
    cur = (currency or "USD").upper()
    if cur == "USD":
        return series
    if cur in ("GBP", "GBX") or currency == "GBp":
        rate = fx["GBPUSD"].reindex(series.index).ffill()
        return series * rate / (100.0 if currency == "GBp" or cur == "GBX" else 1.0)
    if cur == "EUR":
        rate = fx["EURUSD"].reindex(series.index).ffill()
        return series * rate
    return series


# --------------------------------------------------------------------------- returns

def horizon_return(s: pd.Series, n: int):
    s = s.dropna()
    if len(s) <= n:
        return None
    return f(s.iloc[-1] / s.iloc[-1 - n] - 1)


def ytd_return(s: pd.Series):
    s = s.dropna()
    if s.empty:
        return None
    last_year = s.index[-1].year - 1
    prev = s[s.index.year <= last_year]
    if prev.empty:
        return None
    return f(s.iloc[-1] / prev.iloc[-1] - 1)


def realized_vol(s: pd.Series, n: int):
    r = np.log(s.dropna()).diff().dropna()
    if len(r) < max(10, n // 2):
        return None
    return f(r.iloc[-n:].std(ddof=1) * math.sqrt(252))


def rsi(s: pd.Series, n: int = 14):
    s = s.dropna()
    if len(s) < n + 2:
        return None
    d = s.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    rs = up / dn.replace(0, np.nan)
    return f(100 - 100 / (1 + rs.iloc[-1]))


def zscore(s: pd.Series, n: int = 20):
    s = s.dropna()
    if len(s) < n + 1:
        return None
    w = s.iloc[-n:]
    sd = w.std(ddof=1)
    return f((s.iloc[-1] - w.mean()) / sd) if sd and sd > 0 else None


def market_stats(s: pd.Series):
    s = s.dropna()
    if s.empty:
        return {}
    ma50 = s.rolling(50).mean().iloc[-1] if len(s) >= 50 else np.nan
    ma200 = s.rolling(200).mean().iloc[-1] if len(s) >= 200 else np.nan
    hi52 = s.iloc[-252:].max()
    lo52 = s.iloc[-252:].min()
    return {
        "last": f(s.iloc[-1]), "last_date": str(s.index[-1].date()),
        "prev_close": f(s.iloc[-2]) if len(s) > 1 else None,
        "r_1d": horizon_return(s, 1), "r_5d": horizon_return(s, 5), "r_1m": horizon_return(s, 21),
        "r_3m": horizon_return(s, 63), "r_6m": horizon_return(s, 126), "r_1y": horizon_return(s, 252), "r_ytd": ytd_return(s),
        "vol_1m": realized_vol(s, 21), "vol_3m": realized_vol(s, 63), "vol_1y": realized_vol(s, 252),
        "ma50": f(ma50), "ma200": f(ma200),
        "pct_vs_ma50": f(s.iloc[-1] / ma50 - 1) if ma50 and not np.isnan(ma50) else None,
        "pct_vs_ma200": f(s.iloc[-1] / ma200 - 1) if ma200 and not np.isnan(ma200) else None,
        "pct_vs_52w_high": f(s.iloc[-1] / hi52 - 1), "pct_vs_52w_low": f(s.iloc[-1] / lo52 - 1),
        "high_20d": bool(s.iloc[-1] >= s.iloc[-20:].max()) if len(s) >= 20 else None,
        "rsi_14": rsi(s, 14), "z_20d": zscore(s, 20),
    }


# --------------------------------------------------------------------------- beta

def _ols(y: pd.Series, x: pd.Series):
    df = pd.concat([y, x], axis=1).dropna()
    if len(df) < 20:
        return None
    yv, xv = df.iloc[:, 0].values, df.iloc[:, 1].values
    vx = np.var(xv, ddof=1)
    if vx <= 0:
        return None
    beta = np.cov(yv, xv, ddof=1)[0, 1] / vx
    alpha = yv.mean() - beta * xv.mean()
    resid = yv - alpha - beta * xv
    sst = np.sum((yv - yv.mean()) ** 2)
    r2 = 1 - np.sum(resid ** 2) / sst if sst > 0 else None
    return {"beta": f(beta), "alpha_daily": f(alpha), "r2": f(r2), "resid_std": f(np.std(resid, ddof=2)), "n": int(len(df))}


def beta_block(asset_usd: pd.Series, bench_usd: pd.Series, end=None):
    """1y daily, 3m daily, 1y weekly, downside 1y, R2 and idiosyncratic vol — all in USD returns."""
    a = asset_usd.dropna()
    b = bench_usd.dropna()
    if end is not None:
        a, b = a[a.index <= end], b[b.index <= end]
    ra, rb = np.log(a).diff(), np.log(b).diff()
    out = {}
    d1y = _ols(ra.iloc[-252:], rb.reindex(ra.index).iloc[-252:])
    d3m = _ols(ra.iloc[-63:], rb.reindex(ra.index).iloc[-63:])
    aw = a.resample("W-FRI").last().dropna()
    bw = b.resample("W-FRI").last().dropna()
    w1y = _ols(np.log(aw).diff().iloc[-52:], np.log(bw).diff().reindex(aw.index).iloc[-52:])
    joined = pd.concat([ra, rb.reindex(ra.index)], axis=1).dropna().iloc[-252:]
    down = joined[joined.iloc[:, 1] < 0]
    ddown = _ols(down.iloc[:, 0], down.iloc[:, 1]) if len(down) >= 20 else None
    out["beta_1y"] = d1y["beta"] if d1y else None
    out["beta_3m"] = d3m["beta"] if d3m else None
    out["beta_1y_weekly"] = w1y["beta"] if w1y else None
    out["beta_downside_1y"] = ddown["beta"] if ddown else None
    out["r2_1y"] = d1y["r2"] if d1y else None
    out["idio_vol_1y"] = f(d1y["resid_std"] * math.sqrt(252)) if d1y and d1y["resid_std"] is not None else None
    out["n_1y"] = d1y["n"] if d1y else 0
    return out


def idio_contribution(asset_usd, bench_usd, beta, n):
    ra, rb = horizon_return(asset_usd, n), horizon_return(bench_usd, n)
    if ra is None or rb is None or beta is None:
        return {"total": ra, "beta_part": None, "idio_part": None}
    return {"total": ra, "beta_part": f(beta * rb), "idio_part": f(ra - beta * rb)}


# --------------------------------------------------------------------------- percentile

def percentile_of_last(series: pd.Series, window: int = 252):
    s = series.dropna()
    if len(s) < 30:
        return None
    w = s.iloc[-window:]
    return f((w < w.iloc[-1]).mean() * 100)


# --------------------------------------------------------------------------- breadth

def breadth_block(closes: pd.DataFrame, index_close: pd.Series, exclude=None):
    """Local breadth on the constituents we could download (survivorship: today's members only)."""
    df = closes.dropna(axis=1, how="all")
    if exclude:
        df = df[[c for c in df.columns if c not in exclude]]
    if df.empty:
        return {"n": 0}
    # exchanges have different holidays and Yahoo posts European closes with a lag: keep the rows where
    # at least 80 % of the members printed, forward-fill the rest by at most 3 sessions
    coverage = df.notna().mean(axis=1)
    df = df[coverage >= 0.8]
    if df.empty:
        return {"n": 0}
    as_of = str(df.index[-1].date())
    df = df.ffill(limit=3)
    last = df.iloc[-1]
    ma50 = df.rolling(50, min_periods=45).mean().iloc[-1]
    ma200 = df.rolling(200, min_periods=180).mean().iloc[-1]
    hi20 = df.rolling(20, min_periods=18).max().iloc[-1]
    valid50, valid200 = ma50.notna() & last.notna(), ma200.notna() & last.notna()
    rets = df.pct_change()
    adv = (rets > 0).sum(axis=1) - (rets < 0).sum(axis=1)
    ad_line = adv.iloc[-63:].cumsum()
    ew_1m = (df.iloc[-1] / df.iloc[-22] - 1).mean() if len(df) > 22 else None
    ew_3m = (df.iloc[-1] / df.iloc[-64] - 1).mean() if len(df) > 64 else None
    cw_1m = horizon_return(index_close, 21) if index_close is not None else None
    cw_3m = horizon_return(index_close, 63) if index_close is not None else None
    pct_ma50_series = ((df > df.rolling(50, min_periods=45).mean()).sum(axis=1) / df.notna().sum(axis=1) * 100).iloc[-63:]
    return {
        "n": int(last.notna().sum()), "as_of": as_of,
        "pct_above_ma50": f((last[valid50] > ma50[valid50]).mean() * 100) if valid50.any() else None,
        "pct_above_ma200": f((last[valid200] > ma200[valid200]).mean() * 100) if valid200.any() else None,
        "pct_20d_high": f((last >= hi20).sum() / last.notna().sum() * 100),
        "ad_line_3m": {"dates": [str(d.date()) for d in ad_line.index], "values": [int(v) for v in ad_line.values]},
        "pct_above_ma50_3m": {"dates": [str(d.date()) for d in pct_ma50_series.index], "values": [f(v) for v in pct_ma50_series.values]},
        "ew_1m": f(ew_1m), "ew_3m": f(ew_3m), "cw_1m": cw_1m, "cw_3m": cw_3m,
        "ew_minus_cw_1m": f(ew_1m - cw_1m) if ew_1m is not None and cw_1m is not None else None,
        "ew_minus_cw_3m": f(ew_3m - cw_3m) if ew_3m is not None and cw_3m is not None else None,
    }


# --------------------------------------------------------------------------- earnings reactions

def timing_from_hour(hour):
    if hour is None:
        return None
    if hour >= 15:
        return "AMC"
    if hour <= 10:
        return "BMO"
    return None


def _loc(idx: pd.DatetimeIndex, d: pd.Timestamp, side="right"):
    """Position of the first trading day >= d (side='right' → searchsorted left)."""
    return idx.searchsorted(d, side="left")


def earnings_reactions(px: pd.Series, spx: pd.Series, events, max_events=12, today=None):
    """Per past earnings: 5d pre-drift, day reaction, abnormal reaction (beta 1y prior), PEAD 5/20, surprise."""
    px, spx = px.dropna(), spx.dropna()
    today = pd.Timestamp(today or date.today())
    idx = px.index
    rows = []
    past = [e for e in events if e.get("eps_reported") is not None and pd.Timestamp(e["date"]) < today]
    past.sort(key=lambda e: e["date"], reverse=True)
    for e in past[:max_events]:
        d = pd.Timestamp(e["date"])
        timing = timing_from_hour(e.get("hour_local"))
        pos = _loc(idx, d)
        if pos >= len(idx) or pos < 7:
            continue
        ann_day_is_trading = idx[pos] == d
        # reaction window: AMC -> close(D) to close(D+1); BMO -> close(D-1) to close(D); unknown -> treated as AMC
        if timing == "BMO" and ann_day_is_trading:
            i0, i1 = pos - 1, pos
        else:
            i0, i1 = (pos if ann_day_is_trading else pos - 1), (pos + 1 if ann_day_is_trading else pos)
        if i1 >= len(idx):
            continue
        beta = beta_block(px, spx, end=idx[i0])["beta_1y"]
        p = px.values
        s = spx.reindex(idx).ffill().values
        react = p[i1] / p[i0] - 1
        mkt = s[i1] / s[i0] - 1 if not np.isnan(s[i1]) and not np.isnan(s[i0]) else None
        pre = p[i0] / p[i0 - 5] - 1
        pead5 = p[i1 + 5] / p[i1] - 1 if i1 + 5 < len(p) else None
        pead20 = p[i1 + 20] / p[i1] - 1 if i1 + 20 < len(p) else None
        rows.append({
            "date": e["date"], "timing": timing or "n/a", "eps_estimate": e.get("eps_estimate"), "eps_reported": e.get("eps_reported"),
            "surprise_pct": e.get("surprise_pct"),
            "pre_drift_5d": f(pre), "reaction": f(react), "market_move": f(mkt), "beta_prior_1y": beta,
            "abnormal": f(react - beta * mkt) if beta is not None and mkt is not None else None,
            "pead_5d": f(pead5), "pead_20d": f(pead20),
            "window": f"{idx[i0].date()} → {idx[i1].date()}",
        })
    summary = summarize_reactions(rows)
    return rows, summary


def summarize_reactions(rows):
    if not rows:
        return {"n": 0}
    ab = [r["abnormal"] for r in rows if r["abnormal"] is not None]
    re_ = [r["reaction"] for r in rows if r["reaction"] is not None]
    su = [(r["surprise_pct"], r["abnormal"]) for r in rows if r["surprise_pct"] is not None and r["abnormal"] is not None]
    corr = None
    if len(su) >= 4:
        a = np.array(su, dtype=float)
        if a[:, 0].std() > 0 and a[:, 1].std() > 0:
            corr = f(np.corrcoef(a[:, 0], a[:, 1])[0, 1])
    return {
        "n": len(rows),
        "avg_abs_move": f(np.mean([abs(x) for x in re_])) if re_ else None,
        "avg_abs_abnormal": f(np.mean([abs(x) for x in ab])) if ab else None,
        "avg_abnormal": f(np.mean(ab)) if ab else None,
        "beat_rate": f(np.mean([1 if (r["surprise_pct"] or 0) > 0 else 0 for r in rows if r["surprise_pct"] is not None])) if any(r["surprise_pct"] is not None for r in rows) else None,
        "positive_rate": f(np.mean([1 if x > 0 else 0 for x in re_])) if re_ else None,
        "avg_pead_20d": f(np.mean([r["pead_20d"] for r in rows if r["pead_20d"] is not None])) if any(r["pead_20d"] is not None for r in rows) else None,
        "corr_surprise_abnormal": corr,
    }


# --------------------------------------------------------------------------- calendar helpers

def third_friday(year, month):
    c = calendar.Calendar()
    fridays = [d for d in c.itermonthdates(year, month) if d.weekday() == 4 and d.month == month]
    return fridays[2]


def next_business_day(d: date):
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def next_13f_deadline(today: date):
    """45 days after the latest quarter end, rolled to the next business day (SEC rule 13f-1)."""
    out = []
    for qend in (date(today.year - 1, 12, 31), date(today.year, 3, 31), date(today.year, 6, 30), date(today.year, 9, 30), date(today.year, 12, 31)):
        dl = next_business_day(qend + timedelta(days=45))
        if dl >= today:
            out.append({"quarter_end": qend.isoformat(), "deadline": dl.isoformat()})
    return out[0] if out else None


def option_expiries(today: date, days=45):
    out = []
    y, m = today.year, today.month
    for _ in range(3):
        tf = third_friday(y, m)
        if 0 <= (tf - today).days <= days:
            quad = m in (3, 6, 9, 12)
            out.append({"date": tf.isoformat(), "type": "quadruple witching + rebalancement S&P" if quad else "echeance mensuelle (3e vendredi)", "quad": quad})
        m += 1
        if m > 12:
            m, y = 1, y + 1
    return out


# --------------------------------------------------------------------------- signals

def momentum_signal(row, spx_r3m, cfg):
    """Momentum US: MA stack + 3M excess vs SPX + positive 1M idiosyncratic return."""
    conds = []
    if cfg.get("require_ma_stack", True):
        ok = row.get("last") is not None and row.get("ma50") and row.get("ma200") and row["last"] > row["ma50"] > row["ma200"]
        conds.append(("prix > MM50 > MM200", bool(ok)))
    r3 = row.get("r_3m")
    conds.append((f"perf 3M − SPX 3M > {cfg['excess_3m_min']:+.0%}", r3 is not None and spx_r3m is not None and (r3 - spx_r3m) > cfg["excess_3m_min"]))
    idio = row.get("idio_1m")
    conds.append((f"idio 1M > {cfg['idio_1m_min']:+.0%}", idio is not None and idio > cfg["idio_1m_min"]))
    return {"name": "Momentum US", "active": all(c[1] for c in conds), "conditions": conds, "side": "long"}


def mean_reversion_signal(row, cfg):
    z, r = row.get("z_20d"), row.get("rsi_14")
    if z is None or r is None:
        return {"name": "Mean reversion Europe", "active": False, "state": "n/a", "conditions": []}
    buy = z <= cfg["z_entry"] and r <= cfg["rsi_entry"]
    stretch = z >= cfg["z_stretch"] and r >= cfg["rsi_stretch"]
    state = "achat (survendu)" if buy else ("tension (suracheté)" if stretch else "neutre")
    return {"name": "Mean reversion Europe", "active": bool(buy or stretch), "state": state, "side": "long" if buy else ("alléger" if stretch else None),
            "conditions": [(f"z 20j ≤ {cfg['z_entry']}", bool(z <= cfg['z_entry'])), (f"RSI14 ≤ {cfg['rsi_entry']}", bool(r <= cfg['rsi_entry'])),
                           (f"z 20j ≥ {cfg['z_stretch']}", bool(z >= cfg['z_stretch'])), (f"RSI14 ≥ {cfg['rsi_stretch']}", bool(r >= cfg['rsi_stretch']))]}


# --------------------------------------------------------------------------- correlations

def correlation_matrix(closes_usd: pd.DataFrame, window=60):
    r = np.log(closes_usd).diff().iloc[-window:]
    r = r.dropna(axis=1, thresh=int(window * 0.8))
    if r.shape[1] < 2:
        return {"symbols": list(r.columns), "matrix": [], "pairs_above": []}
    c = r.corr()
    return {"symbols": list(c.columns), "matrix": [[f(v) for v in row] for row in c.values], "n_days": int(len(r))}
