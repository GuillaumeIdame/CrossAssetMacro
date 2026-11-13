"""Thematic baskets, relative-performance matrix and the Asia -> US session lead analysis."""

import math
from datetime import date, datetime, timezone

import numpy as np
import pandas as pd

from em_metrics import beta_block, f, horizon_return, market_stats, percentile_of_last, realized_vol, ytd_return


# --------------------------------------------------------------------------- baskets

def ew_index(closes: pd.DataFrame, members, min_members=2, base=100.0):
    """Daily-rebalanced equal-weight index of the members with data each day (base 100 at the first valid day)."""
    cols = [m for m in members if m in closes.columns]
    if len(cols) < 1:
        return None, []
    rets = closes[cols].pct_change()
    count = closes[cols].notna().sum(axis=1)
    ew = rets.mean(axis=1, skipna=True)
    ew = ew[count >= min(min_members, len(cols))]
    ew = ew.dropna()
    if ew.empty:
        return None, cols
    idx = base * (1 + ew).cumprod()
    return idx, cols


def basket_block(name, bcfg, members, closes, usd, bench_series: dict, spx, ndx, sox, prices_payload):
    idx, cols = ew_index(closes, members)
    if idx is None:
        return {"name": name, "label": bcfg.get("label", name), "members": members, "missing": True}
    m = market_stats(idx)
    bench_key = bcfg.get("benchmark", "NDX")
    bench = bench_series.get(bench_key)
    betas = {"SPX": beta_block(idx, spx), "NDX": beta_block(idx, ndx)}
    if sox is not None:
        betas["SOX"] = beta_block(idx, sox)
    rel = {}
    if bench is not None:
        for h, n in (("1M", 21), ("3M", 63), ("6M", 126), ("1Y", 252)):
            a, b = horizon_return(idx, n), horizon_return(bench, n)
            rel[h] = f(a - b) if a is not None and b is not None else None
        a, b = ytd_return(idx), ytd_return(bench)
        rel["YTD"] = f(a - b) if a is not None and b is not None else None
        ratio = (idx / bench.reindex(idx.index).ffill()).dropna()
        rel["ratio_vs_ma50"] = f(ratio.iloc[-1] / ratio.rolling(50).mean().iloc[-1] - 1) if len(ratio) > 50 else None
        rel["ratio_z_1y"] = f((np.log(ratio.iloc[-1]) - np.log(ratio.iloc[-252:]).mean()) / np.log(ratio.iloc[-252:]).std()) if len(ratio) > 60 else None
        rel["ratio_pct_1y"] = percentile_of_last(ratio)
    # member table
    mem = []
    for t in members:
        if t not in closes.columns:
            mem.append({"ticker": t, "missing": True})
            continue
        ms = market_stats(closes[t])
        mem.append({"ticker": t, "last": ms["last"], "last_date": ms["last_date"], "stale": prices_payload["symbols"].get(t, {}).get("stale"),
                    "r_1d": ms["r_1d"], "r_5d": ms["r_5d"], "r_1m": ms["r_1m"], "r_3m": ms["r_3m"], "r_ytd": ms["r_ytd"], "vol_3m": ms["vol_3m"],
                    "rsi_14": ms["rsi_14"], "above_ma50": bool(ms["last"] > ms["ma50"]) if ms.get("ma50") else None, "above_ma200": bool(ms["last"] > ms["ma200"]) if ms.get("ma200") else None,
                    "contrib_1m": f(ms["r_1m"] / len(cols)) if ms["r_1m"] is not None else None, "contrib_1d": f(ms["r_1d"] / len(cols)) if ms["r_1d"] is not None else None})
    valid = [x for x in mem if not x.get("missing")]
    breadth = {"n": len(valid), "pct_above_ma50": f(np.mean([1 if x["above_ma50"] else 0 for x in valid if x["above_ma50"] is not None]) * 100) if valid else None,
               "pct_above_ma200": f(np.mean([1 if x["above_ma200"] else 0 for x in valid if x["above_ma200"] is not None]) * 100) if valid else None,
               "pct_up_1m": f(np.mean([1 if (x["r_1m"] or 0) > 0 else 0 for x in valid]) * 100) if valid else None,
               "dispersion_1m": f(np.std([x["r_1m"] for x in valid if x["r_1m"] is not None])) if len(valid) > 2 else None}
    r = np.log(closes[cols]).diff().iloc[-60:]
    c = r.corr()
    pairs = [c.iloc[i, j] for i in range(len(c)) for j in range(len(c)) if j > i and not np.isnan(c.iloc[i, j])]
    history = idx.iloc[-756:]
    return {
        "name": name, "label": bcfg.get("label", name), "theme": bcfg.get("theme"), "benchmark": bench_key, "members": members, "n_with_data": len(cols),
        "market": m, "betas": betas, "relative": rel, "breadth": breadth, "avg_pair_corr_60d": f(np.mean(pairs)) if pairs else None,
        "members_table": mem, "history": {"dates": [str(d.date()) for d in history.index], "values": [f(v) for v in history.values]},
        "note": "Indice equipondere rebalance chaque jour (moyenne des rendements des membres disponibles), base 100 au premier jour commun ; "
                "les membres entres en bourse recemment (CRWV, GLXY, SNDK) ne contribuent qu'a partir de leur cotation.",
    }


# --------------------------------------------------------------------------- relative matrix

def relative_matrix(series: dict, benchmarks: list, horizons: dict):
    """series: {name: pd.Series in USD}. Excess return of each row over each benchmark, per horizon, plus a 1y z-score of the log ratio."""
    names = list(series.keys())
    out = {"rows": names, "benchmarks": benchmarks, "horizons": list(horizons.keys()), "excess": {}, "ratio_z_1y": {}, "ratio_vs_ma50": {}}
    for h, n in horizons.items():
        out["excess"][h] = {}
        for a in names:
            out["excess"][h][a] = {}
            ra = horizon_return(series[a], n) if n else ytd_return(series[a])
            for b in benchmarks:
                if b not in series or a == b:
                    out["excess"][h][a][b] = None
                    continue
                rb = horizon_return(series[b], n) if n else ytd_return(series[b])
                out["excess"][h][a][b] = f(ra - rb) if ra is not None and rb is not None else None
    for a in names:
        out["ratio_z_1y"][a], out["ratio_vs_ma50"][a] = {}, {}
        for b in benchmarks:
            if b not in series or a == b:
                out["ratio_z_1y"][a][b] = None
                out["ratio_vs_ma50"][a][b] = None
                continue
            ratio = (series[a] / series[b].reindex(series[a].index).ffill()).dropna()
            lr = np.log(ratio.iloc[-252:])
            out["ratio_z_1y"][a][b] = f((lr.iloc[-1] - lr.mean()) / lr.std()) if len(lr) > 60 and lr.std() > 0 else None
            out["ratio_vs_ma50"][a][b] = f(ratio.iloc[-1] / ratio.rolling(50).mean().iloc[-1] - 1) if len(ratio) > 50 else None
    return out


def pair_history(series: dict, pairs: list, n=252):
    out = []
    for a, b in pairs:
        if a not in series or b not in series:
            continue
        ratio = (series[a] / series[b].reindex(series[a].index).ffill()).dropna().iloc[-n:]
        if len(ratio) < 30:
            continue
        roll20 = (ratio / ratio.shift(20) - 1)
        out.append({"a": a, "b": b, "dates": [str(d.date()) for d in ratio.index], "values": [f(v / ratio.iloc[0] * 100) for v in ratio.values],
                    "roll_20d": [f(v) for v in roll20.values], "r_1m": f(ratio.iloc[-1] / ratio.iloc[-22] - 1) if len(ratio) > 22 else None,
                    "r_3m": f(ratio.iloc[-1] / ratio.iloc[-64] - 1) if len(ratio) > 64 else None, "vs_ma50": f(ratio.iloc[-1] / ratio.rolling(50).mean().iloc[-1] - 1) if len(ratio) > 50 else None})
    return out


# --------------------------------------------------------------------------- Asia -> US

def _ols(y, x):
    df = pd.concat([y, x], axis=1).dropna()
    if len(df) < 30:
        return None
    yv, xv = df.iloc[:, 0].values, df.iloc[:, 1].values
    X = np.column_stack([np.ones(len(xv)), xv])
    beta, res, _, _ = np.linalg.lstsq(X, yv, rcond=None)
    resid = yv - X @ beta
    dof = len(yv) - 2
    s2 = (resid @ resid) / dof
    cov = s2 * np.linalg.inv(X.T @ X)
    t = beta[1] / math.sqrt(cov[1, 1]) if cov[1, 1] > 0 else None
    return {"beta": f(beta[1]), "t_stat": f(t), "n": int(len(yv)), "corr": f(np.corrcoef(yv, xv)[0, 1])}


def _ols2(y, x1, x2):
    df = pd.concat([y, x1, x2], axis=1).dropna()
    if len(df) < 30:
        return None
    yv = df.iloc[:, 0].values
    X = np.column_stack([np.ones(len(df)), df.iloc[:, 1].values, df.iloc[:, 2].values])
    beta, _, _, _ = np.linalg.lstsq(X, yv, rcond=None)
    resid = yv - X @ beta
    s2 = (resid @ resid) / (len(yv) - 3)
    cov = s2 * np.linalg.inv(X.T @ X)
    return {"beta_asia": f(beta[1]), "t_asia": f(beta[1] / math.sqrt(cov[1, 1])) if cov[1, 1] > 0 else None,
            "beta_gap": f(beta[2]), "t_gap": f(beta[2] / math.sqrt(cov[2, 2])) if cov[2, 2] > 0 else None, "n": int(len(yv))}


def asia_lead(opens: pd.DataFrame, closes: pd.DataFrame, asia_cfg: dict, us_targets: dict, us_baskets: dict, lookback=250, thr=0.005, cost_bps=2):
    """Does the Asian session (closed before New York opens) lead the US session?

    asia_t   : Asian close-to-close return on calendar day t (session ends ~06:30 UTC)
    gap_t    : US open_t / close_{t-1} - 1  (information absorbed at the open, Asia included)
    intra_t  : US close_t / open_t - 1      (what remains to be earned after the open)
    us_cc_t  : US close-to-close
    Tests: corr/beta of gap and intraday on asia_t; asia_t on us_cc_{t-1} (US leads Asia); partial beta of asia on intraday
    controlling for the gap; sign hit rates; conditional intraday means; open-to-close rule long when asia_t > thr."""
    out = {"lookback_days": lookback, "threshold": thr, "asia_series": {}, "results": {}, "today": {}}
    today = pd.Timestamp(date.today())
    # Asia signal series (close-to-close)
    asia_rets = {}
    for key, ic in asia_cfg["indices"].items():
        t = ic["ticker"]
        if t in closes.columns:
            asia_rets[key] = closes[t].dropna().pct_change().dropna()
    for bname, bc in asia_cfg["baskets"].items():
        cols = [t for t in bc["members"] if t in closes.columns]
        if cols:
            r = closes[cols].pct_change().mean(axis=1, skipna=True).dropna()
            asia_rets[bname] = r
    for k, r in asia_rets.items():
        last = r.index[-1]
        out["asia_series"][k] = {"last_date": str(last.date()), "last": f(r.iloc[-1]), "r_5d_sum": f(r.iloc[-5:].sum()),
                                 "is_today": bool(last == today), "n": int(len(r))}
    # US target returns
    us = {}
    for key, t in us_targets.items():
        if t in closes.columns and t in opens.columns:
            c, o = closes[t], opens[t]
            df = pd.DataFrame({"gap": o / c.shift(1) - 1, "intra": c / o - 1, "cc": c / c.shift(1) - 1}).dropna()
            us[key] = df
    for bname, members in us_baskets.items():
        cols = [m for m in members if m in closes.columns and m in opens.columns]
        if len(cols) < 2:
            continue
        gap = (opens[cols] / closes[cols].shift(1) - 1).mean(axis=1, skipna=True)
        intra = (closes[cols] / opens[cols] - 1).mean(axis=1, skipna=True)
        cc = closes[cols].pct_change().mean(axis=1, skipna=True)
        us["basket:" + bname] = pd.DataFrame({"gap": gap, "intra": intra, "cc": cc}).dropna()
    for a_name, a in asia_rets.items():
        out["results"][a_name] = {}
        for u_name, df in us.items():
            d = df.iloc[-lookback:]
            a_al = a.reindex(d.index)  # same calendar day: Asia closed before the US open
            a_prev_us = d["cc"].shift(1)  # yesterday's US close-to-close, known before Asia opens
            r = {
                "n": int(pd.concat([a_al, d["intra"]], axis=1).dropna().shape[0]),
                "gap_on_asia": _ols(d["gap"], a_al), "intra_on_asia": _ols(d["intra"], a_al), "cc_on_asia": _ols(d["cc"], a_al),
                "asia_on_prev_us": _ols(a.reindex(d.index), a_prev_us),
                "intra_on_asia_and_gap": _ols2(d["intra"], a_al, d["gap"]),
            }
            j = pd.concat([a_al.rename("a"), d["intra"].rename("i"), d["gap"].rename("g")], axis=1).dropna()
            if len(j) >= 30:
                r["hit_rate_intra"] = f((np.sign(j["a"]) == np.sign(j["i"])).mean())
                r["hit_rate_gap"] = f((np.sign(j["a"]) == np.sign(j["g"])).mean())
                up, dn = j[j["a"] > thr], j[j["a"] < -thr]
                r["cond_intra_up"] = {"n": int(len(up)), "mean": f(up["i"].mean()), "hit": f((up["i"] > 0).mean())} if len(up) else None
                r["cond_intra_down"] = {"n": int(len(dn)), "mean": f(dn["i"].mean()), "hit": f((dn["i"] > 0).mean())} if len(dn) else None
                r["cond_gap_up"] = {"n": int(len(up)), "mean": f(up["g"].mean())} if len(up) else None
                r["cond_gap_down"] = {"n": int(len(dn)), "mean": f(dn["g"].mean())} if len(dn) else None
                # rule: long open->close when asia > thr, else flat ; costs on each round trip
                sig = (j["a"] > thr).astype(float)
                strat = sig * j["i"] - sig * (2 * cost_bps / 10000.0)
                eq = (1 + strat).cumprod()
                always = (1 + j["i"]).cumprod()
                years = len(j) / 252
                r["rule"] = {"days_in": int(sig.sum()), "total": f(eq.iloc[-1] - 1), "cagr": f(eq.iloc[-1] ** (1 / years) - 1) if years > 0 else None,
                             "sharpe": f(strat.mean() / strat.std() * math.sqrt(252)) if strat.std() > 0 else None,
                             "always_long_intraday_total": f(always.iloc[-1] - 1), "max_dd": f((eq / eq.cummax() - 1).min()),
                             "equity": {"dates": [str(x.date()) for x in eq.index[-250:]], "rule": [f(v) for v in eq.values[-250:]], "always": [f(v) for v in always.values[-250:]]}}
                # rolling 60d correlation of intraday on asia
                rc = j["a"].rolling(60).corr(j["i"]).dropna()
                r["rolling_corr_intra_60d"] = {"dates": [str(x.date()) for x in rc.index], "values": [f(v) for v in rc.values]}
                rg = j["a"].rolling(60).corr(j["g"]).dropna()
                r["rolling_corr_gap_60d"] = {"dates": [str(x.date()) for x in rg.index], "values": [f(v) for v in rg.values]}
            out["results"][a_name][u_name] = r
    out["us_targets"] = list(us.keys())
    out["method"] = ("Rendements quotidiens ; asia_t = cloture a cloture de la seance asiatique du jour t (finie vers 06:30 UTC) ; gap_t = ouverture US / cloture US de la veille ; "
                     "intraday_t = cloture US / ouverture US. Si l'Asie 'mene', la correlation avec le gap est forte (information integree a l'ouverture) ; "
                     "si elle 'predit' au-dela de l'ouverture, le beta partiel de l'intraday sur asia_t (gap en controle) est significatif (|t| > 2). "
                     "La correlation de asia_t avec le US cloture-cloture de la veille mesure l'inverse : les US menent l'Asie.")
    return out
