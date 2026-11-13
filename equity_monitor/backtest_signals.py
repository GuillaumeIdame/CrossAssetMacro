"""Backtest of the two monitor signals on the prices already downloaded (prices.json).

- Momentum US (long only, weekly rebalance, equal weight among names where the signal is on,
  cash otherwise), universe = Mag7+AMD + the 13F basket, benchmark SPX.
- Mean reversion Europe (long only): buy an index when z-score 20d <= z_entry, exit when z >= z_exit;
  equal weight across the indices in position, cash otherwise; benchmark = equal-weight of the indices.

In-sample = first `in_sample_share` of the history, out-of-sample = the rest (thresholds are the
config values, nothing is optimised here: the split only shows whether the rule holds out of sample).
Costs: fee + slippage per side, in bps, applied to turnover. Everything in USD (Europe converted).

Selection bias (explicit): the 13F basket is known today, after the fact. Backtesting it over the
past five years overstates what one could have earned, because these names were picked because they
went up. The momentum result is therefore reported both with and without the 13F names.
"""

import json
import math
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from em_common import HERE, load_config, now_iso, output_dir, read_json, write_json
from em_metrics import to_usd


def series_from_prices(prices, ticker):
    s = prices["symbols"].get(ticker)
    if not s or not s.get("dates"):
        return None
    return pd.Series(s["close"], index=pd.DatetimeIndex(s["dates"]), name=ticker)


def perf_stats(ret: pd.Series, periods=52):
    ret = ret.dropna()
    if len(ret) < 10:
        return {"n": int(len(ret))}
    eq = (1 + ret).cumprod()
    years = len(ret) / periods
    cagr = eq.iloc[-1] ** (1 / years) - 1 if years > 0 else None
    vol = ret.std(ddof=1) * math.sqrt(periods)
    dd = (eq / eq.cummax() - 1).min()
    return {"n": int(len(ret)), "total_return": float(eq.iloc[-1] - 1), "cagr": float(cagr), "vol": float(vol),
            "sharpe": float(cagr / vol) if vol else None, "max_drawdown": float(dd),
            "hit_rate": float((ret > 0).mean()), "start": str(ret.index[0].date()), "end": str(ret.index[-1].date())}


def momentum_weights(px_w: pd.DataFrame, px_d: pd.DataFrame, spx_d: pd.Series, cfg):
    """Signal evaluated at each weekly date on daily data up to that date (no look-ahead)."""
    ma50 = px_d.rolling(50).mean()
    ma200 = px_d.rolling(200).mean()
    r3m = px_d / px_d.shift(63) - 1
    spx3m = spx_d / spx_d.shift(63) - 1
    # 1M idiosyncratic return with a rolling 1y beta (daily log returns)
    la, lb = np.log(px_d).diff(), np.log(spx_d).diff()
    cov = la.rolling(252).cov(lb)
    var = lb.rolling(252).var()
    beta = cov.div(var, axis=0)
    r1m = px_d / px_d.shift(21) - 1
    spx1m = spx_d / spx_d.shift(21) - 1
    idio = r1m - beta.mul(spx1m, axis=0)
    cond = (px_d > ma50) & (ma50 > ma200) if cfg.get("require_ma_stack", True) else pd.DataFrame(True, index=px_d.index, columns=px_d.columns)
    cond &= (r3m.sub(spx3m, axis=0) > cfg["excess_3m_min"])
    cond &= (idio > cfg["idio_1m_min"])
    sig = cond.reindex(px_w.index, method="ffill").fillna(False)
    n = sig.sum(axis=1)
    w = sig.div(n.replace(0, np.nan), axis=0).fillna(0.0)
    return w


def mean_reversion_weights(px_w: pd.DataFrame, px_d: pd.DataFrame, cfg):
    m = px_d.rolling(20).mean()
    s = px_d.rolling(20).std(ddof=1)
    z = (px_d - m) / s
    zw = z.reindex(px_w.index, method="ffill")
    pos = pd.DataFrame(False, index=zw.index, columns=zw.columns)
    state = {c: False for c in zw.columns}
    for d in zw.index:
        for c in zw.columns:
            v = zw.at[d, c]
            if pd.isna(v):
                continue
            if not state[c] and v <= cfg["z_entry"]:
                state[c] = True
            elif state[c] and v >= cfg["z_exit"]:
                state[c] = False
            pos.at[d, c] = state[c]
    n = pos.sum(axis=1)
    return pos.div(n.replace(0, np.nan), axis=0).fillna(0.0)


def run_strategy(weights: pd.DataFrame, px_w: pd.DataFrame, cost_bps_side: float):
    rets = px_w.pct_change().fillna(0.0)
    w_prev = weights.shift(1).fillna(0.0)               # weights decided at t-1 earn the return from t-1 to t
    gross = (w_prev * rets).sum(axis=1)
    turnover = (weights - w_prev).abs().sum(axis=1)   # one-way turnover
    cost = turnover * cost_bps_side / 10000.0
    net = gross - cost
    return gross, net, turnover


def split(ret: pd.Series, share: float):
    k = int(len(ret) * share)
    return ret.iloc[:k], ret.iloc[k:]


def main():
    cfg = load_config()
    out = output_dir(cfg)
    prices = read_json(out / "prices.json")
    universe = read_json(out / "universe.json")
    if not prices or not universe:
        print("prices.json / universe.json missing: run update_monitor.py first", file=sys.stderr)
        return 1
    bt = cfg["backtest"]
    cost_side = bt["fee_bps_per_side"] + bt["slippage_bps_per_side"]
    fx = pd.DataFrame({k: series_from_prices(prices, t) for k, t in universe["fx_keys"].items()}).ffill()
    spx = series_from_prices(prices, universe["index_keys"]["SPX"])
    result = {"generated_at": now_iso(), "source": "prices.json (" + prices["generated_at"] + ")",
              "costs": {"fee_bps_per_side": bt["fee_bps_per_side"], "slippage_bps_per_side": bt["slippage_bps_per_side"], "applied_to": "turnover one-way, each rebalance"},
              "rebalance": bt["rebalance"], "in_sample_share": bt["in_sample_share"], "thresholds": cfg["signals"], "strategies": {}}

    # ---------------- momentum US
    mag = cfg["stock_groups"]["Mag7+AMD"]
    sa = universe["groups"].get("13F Situational Awareness", [])
    for label, names in (("momentum_us_mag7_amd", mag), ("momentum_us_with_13f_basket", list(dict.fromkeys(mag + sa)))):
        cols = {t: series_from_prices(prices, t) for t in names}
        cols = {t: s for t, s in cols.items() if s is not None and len(s) > 300}
        px_d = pd.DataFrame(cols).dropna(how="all")
        if px_d.shape[1] < 2:
            continue
        spx_d = spx.reindex(px_d.index).ffill()
        px_w = px_d.resample(bt["rebalance"]).last().dropna(how="all")
        w = momentum_weights(px_w, px_d, spx_d, cfg["signals"]["momentum_us"])
        gross, net, to = run_strategy(w, px_w, cost_side)
        bench = spx_d.resample(bt["rebalance"]).last().pct_change().reindex(net.index).fillna(0.0)
        first_valid = w.index[(w.sum(axis=1) > 0).argmax()] if (w.sum(axis=1) > 0).any() else net.index[0]
        start = max(first_valid, px_w.index[min(260 // 5, len(px_w) - 1)])
        net, gross, bench, to = net[net.index >= start], gross[gross.index >= start], bench[bench.index >= start], to[to.index >= start]
        ins, oos = split(net, bt["in_sample_share"])
        bins, boos = split(bench, bt["in_sample_share"])
        eq = (1 + net).cumprod()
        beq = (1 + bench).cumprod()
        result["strategies"][label] = {
            "universe": list(px_d.columns), "n_names": int(px_d.shape[1]),
            "selection_bias": None if label.endswith("mag7_amd") else "Le panier 13F est connu aujourd'hui, pas sur la periode : resultat surestime (biais de selection).",
            "benchmark": "SPX",
            "gross": perf_stats(gross), "net": perf_stats(net), "benchmark_stats": perf_stats(bench),
            "in_sample": {"strategy": perf_stats(ins), "benchmark": perf_stats(bins)},
            "out_of_sample": {"strategy": perf_stats(oos), "benchmark": perf_stats(boos)},
            "avg_turnover_one_way": float(to.mean()), "avg_cost_per_week_bps": float((to * cost_side).mean()),
            "avg_names_held": float((w[w.index >= start] > 0).sum(axis=1).mean()),
            "time_invested": float(((w[w.index >= start].sum(axis=1)) > 0).mean()),
            "equity": {"dates": [str(d.date()) for d in eq.index], "strategy": [float(v) for v in eq.values], "benchmark": [float(v) for v in beq.values]},
        }

    # ---------------- mean reversion Europe
    eu = {k: universe["index_keys"][k] for k in ("SX5E", "DAX", "CAC", "FTSE")}
    cols = {}
    for k, t in eu.items():
        s = series_from_prices(prices, t)
        if s is not None:
            cur = cfg["indices"][k]["currency"]
            cols[k] = to_usd(s, cur, fx)
    px_d = pd.DataFrame(cols).dropna(how="all").ffill()
    px_w = px_d.resample(bt["rebalance"]).last().dropna(how="all")
    w = mean_reversion_weights(px_w, px_d, cfg["signals"]["mean_reversion_eu"])
    gross, net, to = run_strategy(w, px_w, cost_side)
    bench = px_w.pct_change().mean(axis=1).fillna(0.0)
    start = px_w.index[min(6, len(px_w) - 1)]
    net, gross, bench, to = net[net.index >= start], gross[gross.index >= start], bench[bench.index >= start], to[to.index >= start]
    ins, oos = split(net, bt["in_sample_share"])
    bins, boos = split(bench, bt["in_sample_share"])
    eq = (1 + net).cumprod()
    beq = (1 + bench).cumprod()
    result["strategies"]["mean_reversion_eu"] = {
        "universe": list(px_d.columns), "n_names": int(px_d.shape[1]), "benchmark": "EW SX5E/DAX/CAC/FTSE en USD (buy & hold)",
        "gross": perf_stats(gross), "net": perf_stats(net), "benchmark_stats": perf_stats(bench),
        "in_sample": {"strategy": perf_stats(ins), "benchmark": perf_stats(bins)},
        "out_of_sample": {"strategy": perf_stats(oos), "benchmark": perf_stats(boos)},
        "avg_turnover_one_way": float(to.mean()), "avg_cost_per_week_bps": float((to * cost_side).mean()),
        "time_invested": float(((w[w.index >= start].sum(axis=1)) > 0).mean()),
        "n_entries": int(((w > 0) & (w.shift(1).fillna(0) == 0)).sum().sum()),
        "equity": {"dates": [str(d.date()) for d in eq.index], "strategy": [float(v) for v in eq.values], "benchmark": [float(v) for v in beq.values]},
    }
    result["caveats"] = [
        "Rendements hebdomadaires sur clotures ajustees Yahoo ; execution supposee au cours de cloture du vendredi (pas d'intraday).",
        "Long only, pas de levier, cash non remunere.",
        "Seuils = ceux de monitor_config.json, non optimises ; le decoupage in/out-of-sample mesure la stabilite, pas une optimisation.",
        "Cinq ans d'historique : peu d'episodes de mean reversion en Europe, resultat statistiquement fragile.",
    ]
    write_json(out / "backtest.json", result)
    for k, v in result["strategies"].items():
        print(k, "net CAGR", round(v["net"].get("cagr", 0) * 100, 1), "% | bench", round(v["benchmark_stats"].get("cagr", 0) * 100, 1), "% | OOS net", round((v["out_of_sample"]["strategy"].get("cagr") or 0) * 100, 1), "%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
