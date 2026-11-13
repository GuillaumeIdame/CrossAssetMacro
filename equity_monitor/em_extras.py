"""Attribution, futures session windows, volume anomalies, option skew / term structure, alerts, N-PORT composition."""

import math
import time
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone

import numpy as np
import pandas as pd
import requests

from em_common import now_iso, retry
from em_metrics import f, horizon_return


# --------------------------------------------------------------------------- attribution: market beta, sector beta, residual

def two_factor_attribution(asset: pd.Series, market: pd.Series, sector: pd.Series, horizons=((21, "1m"), (63, "3m"))):
    """Daily log-returns over 1y: r = a + b_m * mkt + b_s * sector_orth + e, sector_orth = sector residual on mkt.
    Horizon contributions: b_m * mkt_h, b_s * sector_orth_h (sum of daily), residual = total - both."""
    a, m, s = asset.dropna(), market.dropna(), sector.dropna()
    df = pd.concat([np.log(a).diff(), np.log(m).diff(), np.log(s).diff()], axis=1).dropna().iloc[-252:]
    if len(df) < 120:
        return None
    y, xm, xs = df.iloc[:, 0].values, df.iloc[:, 1].values, df.iloc[:, 2].values
    # orthogonalise the sector factor on the market
    Xm = np.column_stack([np.ones(len(xm)), xm])
    bs_m = np.linalg.lstsq(Xm, xs, rcond=None)[0]
    xs_o = xs - Xm @ bs_m
    X = np.column_stack([np.ones(len(y)), xm, xs_o])
    beta = np.linalg.lstsq(X, y, rcond=None)[0]
    resid = y - X @ beta
    r2 = 1 - (resid @ resid) / ((y - y.mean()) @ (y - y.mean()))
    out = {"beta_market": f(beta[1]), "beta_sector_orth": f(beta[2]), "sector_on_market_beta": f(bs_m[1]), "r2": f(r2), "n": int(len(y)), "horizons": {}}
    xs_o_s = pd.Series(xs_o, index=df.index)
    for n, key in horizons:
        if len(df) <= n:
            continue
        total = horizon_return(a, n)
        mk = beta[1] * (df.iloc[-n:, 1].sum())
        sc = beta[2] * (xs_o_s.iloc[-n:].sum())
        tot_log = math.log(1 + total) if total is not None and total > -1 else None
        out["horizons"][key] = {"total": total, "market": f(math.exp(mk) - 1), "sector": f(math.exp(sc) - 1),
                                "residual": f(math.exp(tot_log - mk - sc) - 1) if tot_log is not None else None,
                                "share_market": f(mk / tot_log) if tot_log else None, "share_sector": f(sc / tot_log) if tot_log else None}
    return out


# --------------------------------------------------------------------------- futures session windows (Asia / Europe / US hours)

def session_windows(hourly_close_utc: pd.Series, asia_end="06:00", europe_end="13:30", us_end="21:00"):
    """From hourly futures closes (index UTC, label = bar start), returns per calendar day:
    asia  = price(asia_end)   / price(us_end, previous day) - 1   (Asian hours, 21:00 -> 06:00 UTC)
    europe= price(europe_end) / price(asia_end) - 1               (European hours, 06:00 -> 13:30 UTC)
    us    = price(us_end)     / price(europe_end) - 1             (US cash hours, 13:30 -> 21:00 UTC)
    Bars are labelled by start time, so the price *at* HH:00 is the close of the bar starting at HH-1:00."""
    s = hourly_close_utc.dropna()
    end_px = s.copy()
    end_px.index = end_px.index + pd.Timedelta(hours=1)  # close of the bar = price at bar end
    days = sorted(set(end_px.index.normalize()))
    rows = []
    for i in range(1, len(days)):
        d, dprev = days[i], days[i - 1]
        def px_at(day, hhmm):
            t = pd.Timestamp(f"{day.date()} {hhmm}", tz="UTC")
            w = end_px[(end_px.index <= t) & (end_px.index > t - pd.Timedelta(hours=3))]
            return float(w.iloc[-1]) if len(w) else None
        p_prev_close = px_at(dprev, us_end)
        p_asia = px_at(d, asia_end)
        p_eu = px_at(d, europe_end)
        p_us = px_at(d, us_end)
        if p_prev_close and p_asia:
            rows.append({"date": d, "asia": p_asia / p_prev_close - 1,
                         "europe": (p_eu / p_asia - 1) if p_eu else None,
                         "us": (p_us / p_eu - 1) if (p_us and p_eu) else None,
                         "cc": (p_us / p_prev_close - 1) if p_us else None})
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows).set_index("date")
    df.index = pd.DatetimeIndex(df.index).tz_localize(None)
    return df


def _corr_beta(y, x):
    j = pd.concat([y, x], axis=1).dropna()
    if len(j) < 30:
        return None
    yv, xv = j.iloc[:, 0].values, j.iloc[:, 1].values
    vx = xv.var(ddof=1)
    b = np.cov(yv, xv, ddof=1)[0, 1] / vx if vx > 0 else None
    r = np.corrcoef(yv, xv)[0, 1]
    t = r * math.sqrt((len(j) - 2) / max(1e-9, 1 - r * r)) if abs(r) < 1 else None
    return {"corr": f(r), "beta": f(b), "t_stat": f(t), "n": int(len(j))}


def futures_relay(windows: dict, asia_rets: dict, us_cash: dict, lookback=250, thr=0.005):
    """windows: {'NQ': DataFrame(asia, europe, us, cc), 'ES': ...}; asia_rets: {'Asie IA': Series}; us_cash: {'NDX': DataFrame(gap, intra, cc)}."""
    out = {"futures": {}, "lookback_days": lookback}
    for fut, w in windows.items():
        d = w.iloc[-lookback:]
        res = {"today": None, "stats": {}, "relay": {}, "conditional": {}}
        last = w.iloc[-1]
        res["today"] = {"date": str(w.index[-1].date()), "asia": f(last["asia"]), "europe": f(last["europe"]) if pd.notna(last["europe"]) else None,
                        "us": f(last["us"]) if pd.notna(last["us"]) else None, "partial": bool(pd.isna(last["us"]))}
        res["avg_abs"] = {k: f(d[k].abs().mean()) for k in ("asia", "europe", "us")}
        res["share_of_variance"] = {k: f(d[k].var() / d[["asia", "europe", "us"]].sum(axis=1).var()) for k in ("asia", "europe", "us")} if d["us"].notna().sum() > 30 else None
        for a_name, a in asia_rets.items():
            res["stats"][a_name] = {"asia_window_on_asia": _corr_beta(d["asia"], a.reindex(d.index)),
                                    "europe_window_on_asia": _corr_beta(d["europe"], a.reindex(d.index)),
                                    "us_window_on_asia": _corr_beta(d["us"], a.reindex(d.index))}
        res["relay"] = {"europe_on_asia_window": _corr_beta(d["europe"], d["asia"]), "us_on_asia_window": _corr_beta(d["us"], d["asia"]),
                        "us_on_europe_window": _corr_beta(d["us"], d["europe"]), "us_on_asia_plus_europe": _corr_beta(d["us"], d["asia"] + d["europe"])}
        j = d[["asia", "europe", "us"]].dropna()
        if len(j) > 30:
            up, dn = j[j["asia"] > thr], j[j["asia"] < -thr]
            res["conditional"] = {"us_if_asia_up": {"n": int(len(up)), "mean": f(up["us"].mean()), "hit": f((up["us"] > 0).mean()), "europe_mean": f(up["europe"].mean())},
                                  "us_if_asia_down": {"n": int(len(dn)), "mean": f(dn["us"].mean()), "hit": f((dn["us"] > 0).mean()), "europe_mean": f(dn["europe"].mean())},
                                  "us_if_asia_and_europe_up": (lambda k: {"n": int(len(k)), "mean": f(k["us"].mean()), "hit": f((k["us"] > 0).mean())})(j[(j["asia"] > thr) & (j["europe"] > 0)]),
                                  "us_if_asia_up_europe_down": (lambda k: {"n": int(len(k)), "mean": f(k["us"].mean()), "hit": f((k["us"] > 0).mean())})(j[(j["asia"] > thr) & (j["europe"] < 0)])}
            rc = j["asia"].rolling(60).corr(j["us"]).dropna()
            res["rolling_corr_us_on_asia_60d"] = {"dates": [str(x.date()) for x in rc.index], "values": [f(v) for v in rc.values]}
            re_ = j["asia"].rolling(60).corr(j["europe"]).dropna()
            res["rolling_corr_europe_on_asia_60d"] = {"dates": [str(x.date()) for x in re_.index], "values": [f(v) for v in re_.values]}
            res["history_60d"] = {"dates": [str(x.date()) for x in j.index[-60:]], "asia": [f(v) for v in j["asia"].values[-60:]], "europe": [f(v) for v in j["europe"].values[-60:]], "us": [f(v) for v in j["us"].values[-60:]]}
        out["futures"][fut] = res
    out["method"] = ("Futures CME (ES, NQ) en barres horaires Yahoo, fenetres UTC fixes : Asie 21:00 -> 06:00, Europe 06:00 -> 13:30, US 13:30 -> 21:00 "
                     "(l'heure d'ete decale d'une heure les bornes cash reelles, approximation assumee). A 06:45 UTC la fenetre Asie du jour est observee : "
                     "c'est le prix deja paye avant Londres. Le relais Europe mesure si la fenetre europeenne prolonge ou efface le mouvement asiatique, "
                     "et la fenetre US ce qui reste pour la seance cash.")
    return out


# --------------------------------------------------------------------------- volume anomalies (flow proxy)

def volume_anomalies(volumes: pd.DataFrame, closes: pd.DataFrame, names: dict, window=20):
    out = {}
    for t in volumes.columns:
        v = volumes[t].dropna()
        v = v[v > 0]
        if len(v) < window + 5 or t not in closes.columns:
            continue
        c = closes[t].reindex(v.index).ffill()
        avg = v.iloc[-window - 1:-1].mean()
        sd = v.iloc[-window - 1:-1].std(ddof=1)
        ret = c.pct_change()
        last10 = pd.DataFrame({"v": v, "r": ret}).dropna().iloc[-10:]
        upv, dnv = last10[last10["r"] > 0]["v"].sum(), last10[last10["r"] < 0]["v"].sum()
        obv = (np.sign(ret.fillna(0)) * v).cumsum()
        dollar = (v * c)
        out[t] = {"name": names.get(t, t), "last_date": str(v.index[-1].date()), "volume": int(v.iloc[-1]), "avg_20d": f(avg),
                  "ratio_vs_20d": f(v.iloc[-1] / avg) if avg else None, "z_20d": f((v.iloc[-1] - avg) / sd) if sd and sd > 0 else None,
                  "dollar_volume_m": f(dollar.iloc[-1] / 1e6), "dollar_volume_avg_20d_m": f(dollar.iloc[-window - 1:-1].mean() / 1e6),
                  "up_down_volume_10d": f(upv / dnv) if dnv > 0 else None, "obv_slope_20d": f((obv.iloc[-1] - obv.iloc[-21]) / (avg * 20)) if len(obv) > 21 and avg else None,
                  "r_1d": f(ret.iloc[-1]), "ratio_5d": f(v.iloc[-5:].mean() / avg) if avg else None}
    return out


# --------------------------------------------------------------------------- option skew and term structure

def _bs_price(spot, strike, t, sigma, call=True):
    from math import erf, exp, log, sqrt
    if t <= 0 or sigma <= 0:
        return max(spot - strike, 0) if call else max(strike - spot, 0)
    d1 = (log(spot / strike) + 0.5 * sigma * sigma * t) / (sigma * sqrt(t))
    d2 = d1 - sigma * sqrt(t)
    N = lambda x: 0.5 * (1 + erf(x / sqrt(2)))
    return spot * N(d1) - strike * N(d2) if call else strike * N(-d2) - spot * N(-d1)


def _iv(spot, strike, t, price, call=True):
    if not price or price <= 0 or t <= 0:
        return None
    intrinsic = max(spot - strike, 0) if call else max(strike - spot, 0)
    if price <= intrinsic + 1e-6:
        return None
    lo, hi = 0.01, 5.0
    if _bs_price(spot, strike, t, hi, call) < price:
        return None
    for _ in range(50):
        mid = 0.5 * (lo + hi)
        if _bs_price(spot, strike, t, mid, call) > price:
            hi = mid
        else:
            lo = mid
    return 0.5 * (lo + hi)


def _delta(spot, strike, t, sigma, call=True):
    from math import erf, log, sqrt
    d1 = (log(spot / strike) + 0.5 * sigma * sigma * t) / (sigma * sqrt(t))
    N = lambda x: 0.5 * (1 + erf(x / sqrt(2)))
    return N(d1) if call else N(d1) - 1


def chain_surface(calls: pd.DataFrame, puts: pd.DataFrame, spot, t_years):
    """Per-strike IV from the last traded (or mid) price; returns ATM IV, 25-delta put/call IVs and skew."""
    def price(row):
        b, a, l = row.get("bid"), row.get("ask"), row.get("lastPrice")
        if b and a and b > 0 and a > 0:
            return float((a + b) / 2), "mid"
        return (float(l), "last") if l and not pd.isna(l) and l > 0 else (None, None)
    pts = []
    for df, is_call in ((calls, True), (puts, False)):
        for _, r in df.iterrows():
            k = float(r["strike"])
            if not (0.6 * spot <= k <= 1.5 * spot):
                continue
            p, basis = price(r)
            iv = _iv(spot, k, t_years, p, is_call)
            if iv and 0.05 < iv < 4:
                pts.append({"k": k, "iv": iv, "call": is_call, "basis": basis, "delta": _delta(spot, k, t_years, iv, is_call)})
    if len(pts) < 4:
        return None
    atm = min(pts, key=lambda p: abs(p["k"] - spot))
    atm_ivs = [p["iv"] for p in pts if abs(p["k"] - atm["k"]) < 1e-9]
    atm_iv = float(np.mean(atm_ivs))
    # stale last prices on illiquid strikes give absurd IVs: keep a band around the ATM level
    pts = [p for p in pts if 0.45 * atm_iv <= p["iv"] <= 2.2 * atm_iv]
    n_filtered = len(pts)
    pc = sorted([p for p in pts if p["call"]], key=lambda p: p["k"])
    pp = sorted([p for p in pts if not p["call"]], key=lambda p: p["k"])

    def interp(points, target_delta):
        cand = sorted([p for p in points if 0.6 * atm_iv <= p["iv"] <= 1.6 * atm_iv], key=lambda p: abs(abs(p["delta"]) - target_delta))
        return cand[0] if cand and abs(abs(cand[0]["delta"]) - target_delta) < 0.08 else None
    p25 = interp(pp, 0.25)
    c25 = interp(pc, 0.25)
    out = {"atm_strike": atm["k"], "atm_iv": f(atm_iv), "n_strikes": n_filtered, "basis": "mid" if pts and all(p["basis"] == "mid" for p in pts) else "last",
           "quality_note": "IV par strike derivee des derniers prix traites ; strikes hors de 0,45-2,2 x IV ATM ecartes (prix perimes)",
           "put25_iv": f(p25["iv"]) if p25 else None, "put25_strike": p25["k"] if p25 else None, "call25_iv": f(c25["iv"]) if c25 else None, "call25_strike": c25["k"] if c25 else None}
    out["skew_25d"] = f(p25["iv"] - c25["iv"]) if p25 and c25 else None
    out["skew_25d_norm"] = f((p25["iv"] - c25["iv"]) / atm_iv) if p25 and c25 and atm_iv else None
    out["put_skew"] = f(p25["iv"] - atm_iv) if p25 else None
    out["call_skew"] = f(c25["iv"] - atm_iv) if c25 else None
    return out


def term_structure(front: dict, back: dict, t_front, t_back):
    """Front = first expiry after earnings, back = a later expiry. Jump variance = T_f * (sigma_f^2 - sigma_b^2)."""
    if not front or not back or not front.get("atm_iv") or not back.get("atm_iv"):
        return None
    sf, sb = front["atm_iv"], back["atm_iv"]
    jump_var = t_front * (sf * sf - sb * sb)
    return {"front_atm_iv": f(sf), "back_atm_iv": f(sb), "ratio_front_back": f(sf / sb), "t_front_days": round(t_front * 365), "t_back_days": round(t_back * 365),
            "implied_event_move_from_term": f(math.sqrt(jump_var)) if jump_var > 0 else None,
            "note": "move evenementiel = racine de T_front x (IV_front^2 - IV_back^2), IV_back prise comme vol diffusive ; n/a si la structure n'est pas inversee"}


# --------------------------------------------------------------------------- alerts

def build_alerts(quotes, risk, events, sectors, baskets, asia, futures, cfg, today):
    th = cfg.get("alerts", {})
    al = []
    add = lambda sev, kind, symbol, text, value=None, src=None: al.append({"severity": sev, "kind": kind, "symbol": symbol, "text": text, "value": value, "source": src})
    # 1. idiosyncratic 1d move > k sigma
    k = th.get("idio_sigma", 2.0)
    for t, q in quotes.get("stocks", {}).items():
        m = q.get("market") or {}
        b = (risk.get("betas", {}).get(t) or {}).get("SPX") or {}
        iv = b.get("idio_vol_1y")
        if m.get("idio_1d") is not None and iv:
            z = m["idio_1d"] / (iv / math.sqrt(252))
            if abs(z) >= k:
                add("high" if abs(z) >= k + 1 else "medium", "idio", t, f"mouvement idiosyncratique 1 j de {m['idio_1d']:+.1%} = {z:+.1f} σ idio (β {q.get('beta_spx_1y') and round(q['beta_spx_1y'], 2)})", z, "quotes.market.idio_1d / risk.betas.idio_vol_1y")
    # 2. MA crossover today / yesterday
    for coll in ("stocks", "indices", "etfs"):
        for t, q in quotes.get(coll, {}).items():
            m = q.get("market") or {}
            for key in ("cross_50_200", "cross_20_50"):
                c = m.get(key) or {}
                if c.get("sessions_since") is not None and c["sessions_since"] <= th.get("cross_max_sessions", 1):
                    add("medium" if key == "cross_50_200" else "low", "cross", t, f"{'golden' if c['last_cross'] == 'golden' else 'death'} cross MM{c['fast']}/{c['slow']} le {c['last_cross_date']}", c["sessions_since"], "quotes.market." + key)
    # 3. basket / benchmark ratio z
    for name, b in (baskets or {}).get("baskets", {}).items():
        z = ((b.get("relative") or {}).get("ratio_z_1y"))
        if z is not None and abs(z) >= th.get("ratio_z", 2.0):
            add("high", "ratio_z", b.get("label", name), f"ratio {b.get('label', name).split(' (')[0]} / {b.get('benchmark')} à {z:+.1f} σ de son année (rel. 1M {(b['relative'].get('1M') or 0):+.1%})", z, "baskets.relative.ratio_z_1y")
    # 4. RRG quadrant change (5 sessions)
    for rk, reg in (sectors or {}).get("regions", {}).items():
        for t, r in reg.get("sectors", {}).items():
            if r.get("quadrant") and r.get("quadrant_prev") and r["quadrant"] != r["quadrant_prev"]:
                sev = "medium" if (r["quadrant"] in ("Leading", "Lagging")) else "low"
                add(sev, "rrg", f"{rk} {r.get('label', t)}", f"quadrant RRG {r['quadrant_prev']} → {r['quadrant']} (RS-ratio {r.get('rs_ratio') and round(r['rs_ratio'], 1)}, RS-mom {r.get('rs_momentum') and round(r['rs_momentum'], 1)})", None, "sectors.quadrant vs quadrant_prev")
    # 5. Asia AI basket beyond +/- 2%
    for k, sr in (asia or {}).get("asia_series", {}).items():
        if sr.get("last") is not None and abs(sr["last"]) >= th.get("asia_move", 0.02):
            add("high" if abs(sr["last"]) >= th.get("asia_move", 0.02) * 1.5 else "medium", "asia", k, f"{k} {sr['last']:+.1%} ({'séance du jour' if sr.get('is_today') else sr.get('last_date')})", sr["last"], "asia.asia_series")
    # 6. futures Asia window today
    for fut, r in (futures or {}).get("futures", {}).items():
        t_ = r.get("today") or {}
        if t_.get("asia") is not None and abs(t_["asia"]) >= th.get("futures_asia_window", 0.01):
            add("medium", "futures", fut, f"{fut} fenêtre Asie (21:00 → 06:00 UTC) {t_['asia']:+.1%}{' · Europe ' + format(t_['europe'], '+.1%') if t_.get('europe') is not None else ''}", t_["asia"], "asia.futures.today")
    # 7. post-earnings move beyond the implied (recent 14 days) ; implied history when stored, else hist avg abs move x1.5 as proxy
    hist_impl = cfg.get("_implied_history", {})
    for e in (events or {}).get("recent_earnings", []):
        t = e["ticker"]
        impl = (hist_impl.get(t) or {}).get(e["date"])
        ref, label = (impl, "move implicite enregistré") if impl else (None, None)
        if ref is None:
            s_ = ((events.get("reactions", {}).get(t) or {}).get("summary") or {})
            if s_.get("avg_abs_move"):
                ref, label = s_["avg_abs_move"] * 1.5, "1,5 × move historique moyen (pas de move implicite enregistré avant l'événement)"
        if ref and e.get("reaction") is not None and abs(e["reaction"]) > ref:
            add("high", "earnings", t, f"réaction {e['reaction']:+.1%} le {e['date']} au-delà de {ref:.1%} ({label})", e["reaction"], "events.recent_earnings")
    # 8. RSI extremes on tracked names
    for t, v in (risk.get("signals", {}).get("technical") or {}).items():
        if v.get("rsi_state"):
            add("low", "rsi", t, f"RSI 14 {v['rsi_14']:.0f} {v['rsi_state']}", v["rsi_14"], "risk.signals.technical")
    order = {"high": 0, "medium": 1, "low": 2}
    al.sort(key=lambda a: (order[a["severity"]], a["kind"]))
    return {"generated_at": now_iso(), "today": today.isoformat(), "thresholds": th, "alerts": al, "counts": {s: sum(1 for a in al if a["severity"] == s) for s in order}}


# --------------------------------------------------------------------------- basket earnings share

def basket_earnings_share(baskets_members: dict, upcoming: dict, quotes_stocks: dict, days=10):
    out = {}
    for name, members in baskets_members.items():
        soon = [t for t in members if (upcoming.get(t) or {}).get("days_to") is not None and 0 <= upcoming[t]["days_to"] <= days]
        drift = [((quotes_stocks.get(t) or {}).get("market") or {}).get("r_5d") for t in soon]
        drift = [x for x in drift if x is not None]
        out[name] = {"n": len(members), "n_reporting": len(soon), "share": f(len(soon) / len(members)) if members else None, "tickers": soon,
                     "avg_pre_drift_5d": f(np.mean(drift)) if drift else None,
                     "next_dates": sorted({upcoming[t]["date"] for t in soon}),
                     "implied_moves": {t: (upcoming[t] or {}).get("implied_move") for t in soon}}
    return out


# --------------------------------------------------------------------------- N-PORT: iShares Russell 2000 ETF holdings

def nport_latest_holdings(sec, series_name, cik="0001100663", logger=None, lookback_months=8):
    """Find the latest public N-PORT-P of the series (full-text search on the series name), parse its holdings."""
    start = (date.today() - timedelta(days=30 * lookback_months)).isoformat()
    r = sec.get("https://efts.sec.gov/LATEST/search-index", params={"q": f'"{series_name}"', "forms": "NPORT-P", "ciks": cik, "startdt": start, "enddt": date.today().isoformat()})
    hits = r.json().get("hits", {}).get("hits", [])
    # every hit is a document of a filing that mentions the series name; the fund's own filing is the one whose
    # primary_doc.xml carries that seriesName (other iShares funds hold IWM and mention it too). Part F attachments
    # are named after the fund (e.g. iSRuss2000.htm), so they are tried first.
    seen, cands = set(), []
    for h in hits:
        acc, doc = h["_id"].split(":")
        if acc in seen:
            continue
        seen.add(acc)
        likely = 0 if (not doc.lower().endswith(".xml") and "russ" in doc.lower() and "2000" in doc) else 1
        cands.append((likely, h["_source"].get("period_ending", ""), h["_source"].get("file_date", ""), acc))
    cands.sort(key=lambda c: (c[0], c[1]), reverse=False)
    cands = sorted(cands, key=lambda c: (c[0], -int(c[1].replace("-", "") or 0)))
    import re as _re
    for likely, period, fdate, acc in cands[:60]:
        folder = acc.replace("-", "")
        url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{folder}/primary_doc.xml"
        try:
            xml = sec.get(url).text
        except Exception as exc:  # noqa: BLE001
            if logger:
                logger.warning("nport %s unreadable: %s", acc, exc)
            continue
        m = _re.search(r"<seriesName>([^<]+)</seriesName>", xml[:8000])
        if not m or m.group(1).strip().lower() != series_name.lower():
            continue
        root = ET.fromstring(xml)
        ns = {"n": root.tag.split("}")[0].strip("{")}
        gi = root.find(".//n:genInfo", ns)
        rep = gi.findtext("n:repPdDate", namespaces=ns)
        holdings = []
        for it in root.findall(".//n:invstOrSec", ns):
            g = lambda p: (it.findtext(p, namespaces=ns) or "").strip()
            if g("n:assetCat") != "EC" or g("n:payoffProfile") != "Long":
                continue
            isin = None
            for ident in it.findall("n:identifiers/*", ns):
                if ident.tag.endswith("isin"):
                    isin = ident.attrib.get("value")
            holdings.append({"name": g("n:name"), "cusip": g("n:cusip").upper(), "isin": isin, "pct": float(g("n:pctVal") or 0), "value_usd": float(g("n:valUSD") or 0), "country": g("n:invCountry")})
        return {"accession": acc, "filing_date": fdate, "period": rep, "series_id": gi.findtext("n:seriesId", namespaces=ns), "url": url, "holdings": holdings, "fetched_at": now_iso()}
    return None
