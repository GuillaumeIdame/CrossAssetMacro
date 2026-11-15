"""Statistical layer for the IPO study: confidence intervals, tests, day-by-day paths and
trade-level Sharpe ratios. Raw and QQQ-adjusted (IPO return minus QQQ return, same dates).

Usage:  python3 ipo_study/ipo_stats.py      -> ipo_study/data/stats.json
Inputs: data/enriched_cohort.csv, data/intraday_daily.csv, optional data/deal_terms.json

Methods
- Bootstrap: 10,000 resamples of IPOs (percentile 95% CI) for means and medians.
- One-sample tests: Student t (mean = 0) and Wilcoxon signed-rank (median = 0).
- Group differences: Kruskal-Wallis across buckets; Spearman rank correlation with p-value.
- Sharpe: per-trade mean/std; "annualised-equivalent" = per-trade SR x sqrt(252/holding days)
  (assumes the trade could be repeated back to back, which overstates it); "realistic" = per-trade
  SR x sqrt(trades available per year in this cohort) with cash in between.
Samples are small (n<=43) and IPO returns are fat-tailed and cross-sectionally correlated (deals
cluster in hot windows), so p-values are optimistic. Nothing here is investment advice.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf
from scipy import stats

HERE = Path(__file__).parent
DATA = HERE / "data"
RNG = np.random.default_rng(7)
B = 10_000


def boot(x, f=np.mean):
    x = np.asarray(pd.Series(x).dropna(), float)
    if len(x) < 3:
        return [np.nan, np.nan]
    idx = RNG.integers(0, len(x), (B, len(x)))
    v = f(x[idx], axis=1)
    return [float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))]


def p_boot_pos(x):
    x = np.asarray(pd.Series(x).dropna(), float)
    idx = RNG.integers(0, len(x), (B, len(x)))
    return float((x[idx].mean(axis=1) > 0).mean())


def describe(x, hold_days, per_year):
    x = pd.Series(x).dropna().astype(float)
    n = len(x)
    if n < 3:
        return dict(n=n)
    m, sd = x.mean(), x.std(ddof=1)
    t = stats.ttest_1samp(x, 0.0)
    try:
        w = stats.wilcoxon(x).pvalue
    except ValueError:
        w = np.nan
    sr = m / sd if sd > 0 else np.nan
    return dict(n=n, mean=m, median=x.median(), std=sd, hit=(x > 0).mean(), ci_mean=boot(x), ci_median=boot(x, np.median),
                t=float(t.statistic), p_t=float(t.pvalue), p_wilcoxon=float(w), p_boot_pos=p_boot_pos(x),
                sr_trade=sr, sr_ann_equiv=sr * np.sqrt(252 / hold_days), sr_realistic=sr * np.sqrt(per_year),
                worst=x.min(), best=x.max())


def bh(p):
    """Benjamini-Hochberg adjusted q-values."""
    p = np.asarray(p, float); n = len(p); o = np.argsort(p)
    q = np.empty(n); q[o] = np.minimum.accumulate((p[o] * n / np.arange(1, n + 1))[::-1])[::-1]
    return [float(min(1, x)) for x in q]


def confidence(d):
    if d.get("n", 0) < 5:
        return "Too few"
    lo, hi = d["ci_mean"]
    if (lo > 0 or hi < 0) and d["p_wilcoxon"] < 0.05:
        return "High"
    if min(d["p_t"], d["p_wilcoxon"]) < 0.10:
        return "Medium"
    return "Low"


def main():
    e = pd.read_csv(DATA / "enriched_cohort.csv")
    i = pd.read_csv(DATA / "intraday_daily.csv")[["ticker", "open_pop", "oc1", "close_vs_high", "gap2", "oc2"]]
    df = e.merge(i, on="ticker")
    t = pd.read_csv(DATA / "deal_terms.csv")
    df = df.merge(t[["ticker", "float_pct", "demand", "revision_pct", "oversub"]], on="ticker", how="left")
    df["r5_63"] = (1 + df.r63) / (1 + df.r5) - 1  # day 5 -> day 63, no overlap with the day 1 -> 5 squeeze
    years = (pd.Timestamp(df.ipo_date.max()) - pd.Timestamp(df.ipo_date.min())).days / 365.25
    per_year = len(df) / years

    # ---------- price paths (raw + vs QQQ) ----------
    qqq = yf.Ticker("QQQ").history(period="max", auto_adjust=True)["Close"]
    qqq.index = qqq.index.tz_localize(None)
    paths, xpaths, opens = {}, {}, {}
    for _, r in df.iterrows():
        h = yf.Ticker(r.ticker).history(period="max", auto_adjust=False)
        h.index = h.index.tz_localize(None)
        c = h["Close"].iloc[:253]
        q = qqq.reindex(c.index).ffill()
        paths[r.ticker] = c.values / c.values[0]
        xpaths[r.ticker] = (c.values / c.values[0]) - (q.values / q.values[0]) + 1  # simple excess index
        opens[r.ticker] = (h["Open"].iloc[0], q.iloc[0])
    P = pd.DataFrame({k: pd.Series(v) for k, v in paths.items()})
    X = pd.DataFrame({k: pd.Series(v) for k, v in xpaths.items()})

    def ret(Pm, a, b):  # return between trading day a and b (1-indexed), per IPO
        return Pm.iloc[b - 1] / Pm.iloc[a - 1] - 1

    # ---------- strategies ----------
    S = {}
    S["Allocation flip: offer to day-1 close (long)"] = (df.set_index("ticker").d1_pop, 1)
    S["Buy the open, sell day-1 close (long)"] = (df.set_index("ticker").oc1, 1)
    S["Squeeze: day-1 close to day 5 (long)"] = (ret(P, 1, 5), 4)
    S["Fade: short day 5 to day 21"] = (-ret(P, 5, 21), 16)
    S["Fade: short day 5 to day 63"] = (-ret(P, 5, 63), 58)
    # short from the open: price(D63)/open - 1
    o = pd.Series({k: v[0] for k, v in opens.items()})
    close63 = pd.Series({k: (P[k].iloc[62] if P[k].notna().sum() >= 63 else np.nan) for k in P.columns})
    d1close_abs = df.set_index("ticker").offer * (1 + df.set_index("ticker").d1_pop)
    S["Short the open to day 63"] = (-(close63 * d1close_abs / o - 1), 63)
    S["Lock-up window: short day 118 to day 130"] = (-ret(P, 118, 130), 12)
    S["Buy day-1 close, hold 1 year (long)"] = (ret(P, 1, 252), 251)
    # QQQ-adjusted versions of the multi-day trades
    SX = {"Squeeze vs QQQ: day 1 to 5": (ret(X, 1, 5), 4), "Fade vs QQQ: short day 5 to 21": (-ret(X, 5, 21), 16),
          "Fade vs QQQ: short day 5 to 63": (-ret(X, 5, 63), 58), "Lock-up vs QQQ: short day 118 to 130": (-ret(X, 118, 130), 12)}
    strat = []
    for name, (x, hd) in list(S.items()) + list(SX.items()):
        d = describe(x, hd, per_year)
        d.update(name=name, hold_days=hd, adjusted="vs QQQ" in name, confidence=confidence(d))
        strat.append(d)

    # subsets relevant to ANT: large/mega caps; software/AI; rising 10Y
    sub = {}
    masks = {"Large and mega caps ($30B+)": df.cap_b >= 30, "Software, AI & semis": df.sector == "Software, AI & semis",
             "Listed with 10Y rising": df.yld == "10Y rising", "Day-1 pop 15-40% (SpaceX-like)": df.d1_pop.between(0.15, 0.40),
             "Priced above initial range": df.demand == "Above range", "Float under 8% (ANT ~4.5%)": df.float_pct < 0.08}
    for lab, m in masks.items():
        tk = df[m].ticker
        rows = []
        for name, (x, hd) in [("Squeeze: day 1 to 5", (ret(P, 1, 5), 4)), ("Fade: short day 5 to 21", (-ret(P, 5, 21), 16)),
                              ("Fade: short day 5 to 63", (-ret(P, 5, 63), 58))]:
            d = describe(x.reindex(tk), hd, per_year)
            d.update(name=name, confidence=confidence(d))
            rows.append(d)
        sub[lab] = dict(n=int(m.sum()), names=list(tk), rows=rows)

    # ---------- day-by-day close-to-close with CI ----------
    daily = []
    for k in range(2, 11):
        x = (P.iloc[k - 1] / P.iloc[k - 2] - 1)
        xx = (X.iloc[k - 1] / X.iloc[k - 2] - 1)
        daily.append(dict(day=k, mean=x.mean(), ci=boot(x), median=x.median(), hit=(x > 0).mean(), p_t=float(stats.ttest_1samp(x.dropna(), 0).pvalue),
                          xmean=xx.mean(), xci=boot(xx)))
    band = []
    for k in range(1, 253):
        x = P.iloc[k - 1].dropna() - 1
        if len(x) < 8:
            break
        lo, hi = boot(x, np.median) if k > 1 else (0, 0)
        xl, xh = boot(X.iloc[k - 1].dropna() - 1, np.median) if k > 1 else (0, 0)
        band.append(dict(d=k, med=float(x.median()), lo=lo, hi=hi, xmed=float((X.iloc[k - 1].dropna() - 1).median()), xlo=xl, xhi=xh, n=int(len(x))))

    # ---------- buckets with CI + Kruskal-Wallis ----------
    def grp(col, order=None):
        g = df.dropna(subset=[col]).groupby(col)
        keys = order or list(g.groups)
        out = []
        for k in keys:
            if k not in g.groups:
                continue
            s = g.get_group(k)
            out.append(dict(key=str(k), n=len(s), pop=s.d1_pop.median(), pop_ci=boot(s.d1_pop, np.median),
                            r21=s.r21.median(), r21_ci=boot(s.r21, np.median), r63=s.r63.median(), r63_ci=boot(s.r63, np.median),
                            r126=s.r126.median(), r126_ci=boot(s.r126, np.median), names=list(s.ticker)))
        kw = {}
        for m in ["d1_pop", "r21", "r63", "r126"]:
            arrs = [g.get_group(k)[m].dropna().values for k in keys if k in g.groups and g.get_group(k)[m].notna().sum() >= 3]
            kw[m] = float(stats.kruskal(*arrs).pvalue) if len(arrs) >= 2 else None
        return dict(rows=out, kruskal=kw)
    groups = {"Market cap": grp("bucket", ["Small <10B", "Mid 10-30B", "Large 30-100B", "Mega >=100B"]),
              "Sector": grp("sector"), "Listing quarter": grp("quarter", ["Q1", "Q2", "Q3", "Q4"]),
              "10Y trend": grp("yld", ["10Y falling", "10Y flat", "10Y rising"]), "VIX": grp("vix_reg", ["VIX <16", "VIX 16-22", "VIX >22"])}
    if "float_pct" in df:
        df["float_b"] = pd.cut(df.float_pct, [0, 0.08, 0.15, 1], labels=["Float <8%", "Float 8-15%", "Float >15%"]).astype(str).replace("nan", np.nan)
        df["demand_b"] = np.where(df.demand == "Above range", "Priced above initial range", np.where(df.demand.notna(), "At or below initial range", None))
        groups["Float %"] = grp("float_b", ["Float <8%", "Float 8-15%", "Float >15%"])
        groups["Pricing vs range"] = grp("demand_b", ["At or below initial range", "Priced above initial range"])

    # ---------- correlations ----------
    corr = []
    pairs = [("d1_pop", "r21", "Day-1 pop vs day-21 return"), ("d1_pop", "r63", "Day-1 pop vs day-63 return"),
             ("open_pop", "oc1", "Opening pop vs open-to-close"), ("cap_b", "d1_pop", "Market cap vs day-1 pop"),
             ("y10_3m_chg", "r63", "10Y 3-month change vs day-63 return"), ("vix", "d1_pop", "VIX vs day-1 pop"),
             ("r5", "r5_63", "Day 1-5 squeeze vs day 5-63 return (non-overlapping)")]
    if "float_pct" in df:
        pairs += [("float_pct", "d1_pop", "Float % vs day-1 pop"), ("float_pct", "r63", "Float % vs day-63 return"),
                  ("revision_pct", "d1_pop", "Price revision vs day-1 pop"), ("revision_pct", "r63", "Price revision vs day-63 return"),
                  ("oversub", "d1_pop", "Oversubscription vs day-1 pop")]
    for a, b, lab in pairs:
        s = df[[a, b]].dropna()
        if len(s) >= 6:
            rho, p = stats.spearmanr(s[a], s[b])
            corr.append(dict(label=lab, n=len(s), rho=float(rho), p=float(p)))

    # Benjamini-Hochberg across every Kruskal-Wallis test run above
    flat = [(g, m, p) for g, v in groups.items() for m, p in v["kruskal"].items() if p is not None]
    q = bh([p for *_, p in flat])
    for (g, m, _), qq in zip(flat, q):
        groups[g].setdefault("kruskal_q", {})[m] = qq
    cq = bh([c["p"] for c in corr])
    for c, qq in zip(corr, cq):
        c["q"] = qq
    out = dict(per_year=per_year, years=years, strategies=strat, subsets=sub, daily=daily, band=band, groups=groups, corr=corr,
               cohort_terms=json.loads(df[[c for c in ["ticker", "name", "float_pct", "demand", "revision_pct", "oversub", "cap_b"] if c in df]].to_json(orient="records")))
    json.dump(out, open(DATA / "stats.json", "w"), default=float)

    pd.set_option("display.width", 250, "display.max_columns", 30)
    st = pd.DataFrame(strat)[["name", "n", "mean", "median", "hit", "ci_mean", "p_t", "p_wilcoxon", "sr_trade", "sr_ann_equiv", "sr_realistic", "confidence"]]
    print(st.round(3).to_string(index=False))
    print("\ntrades/year", round(per_year, 2))
    for k, v in sub.items():
        print("\n", k, v["n"]); print(pd.DataFrame(v["rows"])[["name", "n", "mean", "hit", "ci_mean", "p_wilcoxon", "sr_trade", "confidence"]].round(3).to_string(index=False))
    print("\nDAILY"); print(pd.DataFrame(daily).round(4).to_string(index=False))
    for k, g in groups.items():
        print("\n", k, {m: (round(p, 3) if p is not None else None) for m, p in g["kruskal"].items()})
        print(pd.DataFrame(g["rows"]).drop(columns=["names"]).round(3).to_string(index=False))
    print("\nCORR"); print(pd.DataFrame(corr).round(3).to_string(index=False))


if __name__ == "__main__":
    main()
