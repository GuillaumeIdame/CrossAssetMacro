"""Sector rotation: relative strength, simplified Relative Rotation Graph, literature-based entry score."""

import math

import numpy as np
import pandas as pd

from em_metrics import f, horizon_return, market_stats, realized_vol, ytd_return


def rs_series(sector: pd.Series, bench: pd.Series):
    df = pd.concat([sector.dropna(), bench.dropna()], axis=1).dropna()
    if len(df) < 60:
        return None
    return df.iloc[:, 0] / df.iloc[:, 1]


def rrg_point(ratio: pd.Series, win_ratio=50, win_mom=10):
    """Simplified JdK: RS-Ratio = 100 x ratio / SMA(ratio, 50) ; RS-Momentum = 100 x RS-Ratio / RS-Ratio[-10]."""
    rsr = 100 * ratio / ratio.rolling(win_ratio).mean()
    rsm = 100 * rsr / rsr.shift(win_mom)
    return rsr, rsm


def quadrant(rsr, rsm):
    if rsr is None or rsm is None:
        return None
    if rsr >= 100 and rsm >= 100:
        return "Leading"
    if rsr >= 100 and rsm < 100:
        return "Weakening"
    if rsr < 100 and rsm < 100:
        return "Lagging"
    return "Improving"


def sector_table(closes: pd.DataFrame, region_cfg: dict, sig_cfg: dict):
    bench_t = region_cfg["benchmark"]
    bench = closes[bench_t].dropna() if bench_t in closes.columns else None
    rows = {}
    for t, label in region_cfg["members"].items():
        if t not in closes.columns or bench is None:
            rows[t] = {"ticker": t, "label": label, "missing": True}
            continue
        px = closes[t].dropna()
        m = market_stats(px)
        ratio = rs_series(px, bench)
        if ratio is None:
            rows[t] = {"ticker": t, "label": label, "missing": True}
            continue
        rsr, rsm = rrg_point(ratio, sig_cfg["rs_ratio_window"], sig_cfg["rs_momentum_window"])
        # weekly trail of the last 8 weeks for the RRG chart
        trail_idx = ratio.index[-1::-5][:8][::-1]
        trail = [{"date": str(d.date()), "rsr": f(rsr.loc[d]), "rsm": f(rsm.loc[d])} for d in trail_idx]
        ma_r50 = ratio.rolling(50).mean().iloc[-1]
        ma_r200 = ratio.rolling(200).mean().iloc[-1] if len(ratio) >= 200 else np.nan
        n = len(px)
        mom_12_1 = f(px.iloc[-22] / px.iloc[-253] - 1) if n > 253 else None
        mom_12_7 = f(px.iloc[-127] / px.iloc[-253] - 1) if n > 253 else None
        r12 = f(px.iloc[-1] / px.iloc[-253] - 1) if n > 253 else None
        ma_f = px.rolling(sig_cfg["faber_ma_days"]).mean().iloc[-1] if n >= sig_cfg["faber_ma_days"] else np.nan
        rows[t] = {
            "ticker": t, "label": label, "missing": False, "last": m["last"], "last_date": m["last_date"],
            "abs": {k: m[k] for k in ("r_1d", "r_5d", "r_1m", "r_3m", "r_6m", "r_1y", "r_ytd")},
            "rel": {k: (f(m[k] - horizon_return(bench, nn)) if m[k] is not None else None) for k, nn in (("r_1d", 1), ("r_5d", 5), ("r_1m", 21), ("r_3m", 63), ("r_6m", 126), ("r_1y", 252))},
            "rel_ytd": f(m["r_ytd"] - ytd_return(bench)) if m["r_ytd"] is not None and ytd_return(bench) is not None else None,
            "vol_3m": m["vol_3m"], "rsi_14": m["rsi_14"], "rsi_state": m.get("rsi_state"), "cross_50_200": m.get("cross_50_200"), "cross_20_50": m.get("cross_20_50"), "mom_6_1": m.get("mom_6_1"),
            "rs_vs_ma50": f(ratio.iloc[-1] / ma_r50 - 1) if ma_r50 else None,
            "rs_vs_ma200": f(ratio.iloc[-1] / ma_r200 - 1) if ma_r200 and not np.isnan(ma_r200) else None,
            "rs_ratio": f(rsr.iloc[-1]), "rs_momentum": f(rsm.iloc[-1]), "quadrant": quadrant(f(rsr.iloc[-1]), f(rsm.iloc[-1])),
            "quadrant_prev": quadrant(f(rsr.iloc[-6]), f(rsm.iloc[-6])) if len(rsr) > 6 else None, "trail": trail,
            "mom_12_1": mom_12_1, "mom_12_7": mom_12_7, "r_12m": r12,
            "above_ma_faber": bool(px.iloc[-1] > ma_f) if ma_f and not np.isnan(ma_f) else None, "pct_vs_ma_faber": f(px.iloc[-1] / ma_f - 1) if ma_f and not np.isnan(ma_f) else None,
            "pct_vs_52w_high": m["pct_vs_52w_high"], "above_ma50": bool(px.iloc[-1] > m["ma50"]) if m["ma50"] else None, "above_ma200": bool(px.iloc[-1] > m["ma200"]) if m["ma200"] else None,
            "rs_history": {"dates": [str(d.date()) for d in ratio.index[-252:]], "values": [f(v / ratio.iloc[-252] * 100) if len(ratio) >= 252 else f(v / ratio.iloc[0] * 100) for v in ratio.values[-252:]]},
        }
    # ranks and entry score
    valid = [r for r in rows.values() if not r.get("missing") and r.get("mom_12_1") is not None]
    for key, rank_key in (("mom_12_1", "rank_12_1"), ("mom_12_7", "rank_12_7")):
        order = sorted(valid, key=lambda r: -(r[key] if r[key] is not None else -9))
        for i, r in enumerate(order):
            r[rank_key] = i + 1
    order_1m = sorted(valid, key=lambda r: -(r["abs"]["r_1m"] if r["abs"]["r_1m"] is not None else -9))
    for i, r in enumerate(order_1m):
        r["rank_1m"] = i + 1
    for r in valid:
        r["score"] = entry_score(r, sig_cfg)
    return rows, len(valid)


def entry_score(r, cfg):
    conds = [
        ("MG1999", f"momentum 12-1 dans le top {cfg['top_n']} (rang {r.get('rank_12_1')})", r.get("rank_12_1") is not None and r["rank_12_1"] <= cfg["top_n"]),
        ("Faber2007", f"prix > MM{cfg['faber_ma_days']} ({'n/a' if r.get('pct_vs_ma_faber') is None else f'{r['pct_vs_ma_faber']:+.1%}'})", bool(r.get("above_ma_faber"))),
        ("Antonacci2014", f"momentum absolu 12M > 0 ({'n/a' if r.get('r_12m') is None else f'{r['r_12m']:+.1%}'})", r.get("r_12m") is not None and r["r_12m"] > 0),
        ("GH2004", f"à moins de {cfg['high_52w_proximity']:.0%} du plus haut 52 sem. ({'n/a' if r.get('pct_vs_52w_high') is None else f'{r['pct_vs_52w_high']:+.1%}'})", r.get("pct_vs_52w_high") is not None and r["pct_vs_52w_high"] >= -cfg["high_52w_proximity"]),
        ("RRG", f"quadrant {r.get('quadrant')} (RS-ratio {r.get('rs_ratio') and round(r['rs_ratio'], 1)}, RS-mom {r.get('rs_momentum') and round(r['rs_momentum'], 1)})", r.get("quadrant") in ("Leading", "Improving") and (r.get("rs_momentum") or 0) >= 100),
        ("Jegadeesh1990", f"pas dans le top {cfg['reversal_avoid_top']} du dernier mois (rang 1M {r.get('rank_1m')})", r.get("rank_1m") is not None and r["rank_1m"] > cfg["reversal_avoid_top"]),
    ]
    score = sum(1 for c in conds if c[2])
    in_top = r.get("rank_12_1") is not None and r["rank_12_1"] <= cfg["top_n"]
    held_like = in_top or r.get("quadrant") == "Leading"          # what a rotation book would currently hold
    broken = r.get("above_ma_faber") is False or (r.get("quadrant") == "Weakening" and (r.get("rs_momentum") or 100) < 100)
    entry = in_top and score >= cfg["entry_min_score"] and not broken   # momentum rank anchors, the score confirms, no entry into a broken trend
    exit_flag = held_like and broken
    avoid = (not held_like) and ((r.get("rank_12_1") or 0) >= cfg["exit_rank"] or r.get("above_ma_faber") is False)
    watch = (not entry) and (not exit_flag) and (not avoid) and score >= cfg["entry_min_score"]
    state = "entrée" if entry else ("sortie" if exit_flag else ("éviter" if avoid else ("surveiller" if watch else "neutre")))
    return {"score": score, "max": len(conds), "entry": bool(entry), "exit": bool(exit_flag), "avoid": bool(avoid), "watch": bool(watch), "state": state,
            "pullback": bool(in_top and (r["abs"].get("r_1m") or 0) < 0),
            "conditions": [{"ref": c[0], "label": c[1], "ok": bool(c[2])} for c in conds]}


def region_summary(rows: dict, closes: pd.DataFrame, region_cfg: dict):
    valid = {t: r for t, r in rows.items() if not r.get("missing")}
    out = {"n": len(valid)}
    if not valid:
        return out
    out["pct_above_ma50"] = f(np.mean([1 if r["above_ma50"] else 0 for r in valid.values() if r["above_ma50"] is not None]) * 100)
    out["pct_above_ma200"] = f(np.mean([1 if r["above_ma200"] else 0 for r in valid.values() if r["above_ma200"] is not None]) * 100)
    out["pct_leading"] = f(np.mean([1 if r["quadrant"] == "Leading" else 0 for r in valid.values()]) * 100)
    out["quadrants"] = {q: [t for t, r in valid.items() if r["quadrant"] == q] for q in ("Leading", "Weakening", "Lagging", "Improving")}
    cyc = [t for t in region_cfg["cyclical"] if t in valid]
    dfn = [t for t in region_cfg["defensive"] if t in valid]
    for h in ("r_1m", "r_3m", "r_1d", "r_5d"):
        c = np.mean([valid[t]["abs"][h] for t in cyc if valid[t]["abs"][h] is not None]) if cyc else None
        d = np.mean([valid[t]["abs"][h] for t in dfn if valid[t]["abs"][h] is not None]) if dfn else None
        out[f"cyc_minus_def_{h[2:]}"] = f(c - d) if c is not None and d is not None else None
    # dispersion: cross-sectional std of 1M returns (rotation intensity)
    r1 = [r["abs"]["r_1m"] for r in valid.values() if r["abs"]["r_1m"] is not None]
    out["dispersion_1m"] = f(np.std(r1)) if len(r1) > 2 else None
    out["leaders_1m"] = [t for t, _ in sorted(valid.items(), key=lambda kv: -(kv[1]["abs"]["r_1m"] or -9))[:3]]
    out["laggards_1m"] = [t for t, _ in sorted(valid.items(), key=lambda kv: (kv[1]["abs"]["r_1m"] if kv[1]["abs"]["r_1m"] is not None else 9))[:3]]
    out["entries"] = [t for t, r in valid.items() if r.get("score", {}).get("entry")]
    out["exits"] = [t for t, r in valid.items() if r.get("score", {}).get("exit")]
    out["watch"] = [t for t, r in valid.items() if r.get("score", {}).get("watch")]
    # pair ratios, 1 year base 100
    pairs = []
    for a, b, label in region_cfg.get("pairs", []):
        if a in closes.columns and b in closes.columns:
            ratio = rs_series(closes[a], closes[b])
            if ratio is not None:
                last = ratio.iloc[-252:]
                pairs.append({"a": a, "b": b, "label": label, "dates": [str(d.date()) for d in last.index], "values": [f(v / last.iloc[0] * 100) for v in last.values],
                              "r_1m": f(last.iloc[-1] / last.iloc[-22] - 1) if len(last) > 22 else None, "r_3m": f(last.iloc[-1] / last.iloc[-64] - 1) if len(last) > 64 else None})
    out["pairs"] = pairs
    ew = region_cfg.get("equal_weight")
    if ew and ew in closes.columns and region_cfg["benchmark"] in closes.columns:
        e, b = closes[ew].dropna(), closes[region_cfg["benchmark"]].dropna()
        out["ew_minus_cw"] = {"1m": f(horizon_return(e, 21) - horizon_return(b, 21)), "3m": f(horizon_return(e, 63) - horizon_return(b, 63)), "ticker": ew}
    return out
