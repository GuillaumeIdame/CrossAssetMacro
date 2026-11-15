"""Book-building ("subscription") signals and the IPO pop: intraday and close-to-close.

Usage: python3 ipo_study/signals.py  -> ipo_study/data/signals.json (+ prints)

Signals (known at pricing, before trading):
  rev        offer vs midpoint of the FIRST filed range            (price revision, Hanley 1993)
  range_rev  final-range midpoint vs first-range midpoint           (range raised before pricing)
  rev_final  offer vs midpoint of the FINAL range                   (where in the final range it priced)
  above      offer above the first range (1/0)
  upsized    share count increased (1/0, unknown -> 0)
  oversub    reported book coverage multiple (data/oversub.csv, when available)
  float_pct, log proceeds, and the market state at listing (PSI, crowding composite)
Outcomes: opening print vs offer, open->close, close vs high, day-1 close vs offer (pop), day-2 gap and
open->close, close-to-close days 2-10, day 1->5, 1->21, 1->63, day 63 vs QQQ.
Tests: Spearman with Benjamini-Hochberg q; OLS with HC3; decomposition of the pop into the opening print
and the intraday drift; group tables; an entry/exit matrix (subscribe at offer, buy the open, buy the first
close) by signal group; a leave-one-out predictive model of the pop, applied to Anthropic using the
prediction-market-implied offer price.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
import yfinance as yf
from scipy import stats

DATA = Path(__file__).parent / "data"
RNG = np.random.default_rng(13)


def bh(p):
    p = np.asarray(p, float); n = len(p); o = np.argsort(p)
    q = np.empty(n); q[o] = np.minimum.accumulate((p[o] * n / np.arange(1, n + 1))[::-1])[::-1]
    return np.minimum(q, 1)


def main():
    terms = pd.read_csv(DATA / "deal_terms_raw.csv")
    co = pd.read_csv(DATA / "enriched_cohort.csv")
    cr = pd.DataFrame(json.load(open(DATA / "crowding.json"))["cohort"])[["ticker", "CROWD", "PSI", "turn1"]]
    d = co.merge(terms, on="ticker", suffixes=("", "_t")).merge(cr, on="ticker", how="left")
    d = d.merge(pd.read_csv(DATA / "deal_terms.csv")[["ticker", "float_pct"]], on="ticker", how="left")
    init_mid = (d.init_lo + d.init_hi) / 2; fin_mid = (d.fin_lo + d.fin_hi) / 2
    init_mid = init_mid.fillna(fin_mid)
    d["rev"] = d.offer / init_mid - 1
    d["range_rev"] = fin_mid / init_mid - 1
    d["rev_final"] = d.offer / fin_mid - 1
    d["above"] = (d.offer > d.init_hi.fillna(d.fin_hi)).astype(float); d.loc[init_mid.isna(), "above"] = np.nan
    d["range_raised"] = (d.range_rev > 0.001).astype(float); d.loc[init_mid.isna(), "range_raised"] = np.nan
    d["upsized"] = (d.upsized.astype(str) == "True").astype(float)
    d["logproc"] = np.log(d.proceeds_m)
    ov = DATA / "oversub.csv"
    if ov.exists():
        o = pd.read_csv(ov)[["ticker", "oversub"]].rename(columns={"oversub": "oversub_r"})
        d = d.merge(o, on="ticker", how="left"); d["oversub"] = d.oversub_r
    else:
        d["oversub"] = np.nan

    # ---------- daily OHLC outcomes, close-to-close path ----------
    qqq = yf.Ticker("QQQ").history(period="max", auto_adjust=True)["Close"]; qqq.index = qqq.index.tz_localize(None)
    paths, rows = {}, []
    for r in d.itertuples():
        h = yf.Ticker(r.ticker).history(period="max", auto_adjust=False); h.index = h.index.tz_localize(None)
        o_, hi_, c_ = h.Open, h.High, h.Close
        q = qqq.reindex(c_.index).ffill()
        row = dict(ticker=r.ticker, open_pop=o_.iloc[0] / r.offer - 1, oc1=c_.iloc[0] / o_.iloc[0] - 1, close_vs_high=c_.iloc[0] / hi_.iloc[0] - 1,
                   hi_vs_open=hi_.iloc[0] / o_.iloc[0] - 1, gap2=o_.iloc[1] / c_.iloc[0] - 1, oc2=c_.iloc[1] / o_.iloc[1] - 1,
                   c2=c_.iloc[1] / c_.iloc[0] - 1, x63=(c_.iloc[62] / c_.iloc[0] - q.iloc[62] / q.iloc[0]) if len(c_) >= 63 else np.nan,
                   open_to5=c_.iloc[4] / o_.iloc[0] - 1, open_to21=c_.iloc[20] / o_.iloc[0] - 1, open_to63=c_.iloc[62] / o_.iloc[0] - 1 if len(c_) >= 63 else np.nan,
                   offer_to5=c_.iloc[4] / r.offer - 1, offer_to21=c_.iloc[20] / r.offer - 1, offer_to63=c_.iloc[62] / r.offer - 1 if len(c_) >= 63 else np.nan,
                   offer_open=o_.iloc[0] / r.offer - 1)
        rows.append(row)
        paths[r.ticker] = (c_.iloc[:11].values / c_.iloc[0])
    d = d.merge(pd.DataFrame(rows), on="ticker")
    d["pop"] = d.d1_pop
    d["d1_5"] = d.r5; d["d1_21"] = d.r21; d["d1_63"] = d.r63

    # ---------- 1. correlations ----------
    sigs = ["rev", "range_rev", "rev_final", "above", "range_raised", "upsized", "oversub", "float_pct", "logproc", "CROWD", "PSI"]
    outs = ["open_pop", "oc1", "close_vs_high", "pop", "gap2", "oc2", "d1_5", "d1_21", "d1_63", "x63"]
    corr = []
    for s in sigs:
        for y in outs:
            ok = d[[s, y]].dropna()
            if len(ok) < 8 or ok[s].nunique() < 2:
                continue
            rho, p = stats.spearmanr(ok[s], ok[y]); corr.append(dict(signal=s, outcome=y, n=len(ok), rho=float(rho), p=float(p)))
    for c, q in zip(corr, bh([c["p"] for c in corr])):
        c["q"] = float(q)

    # ---------- 2. decomposition: which signals price the opening print vs the intraday drift ----------
    d["lopen"] = np.log1p(d.open_pop); d["loc1"] = np.log1p(d.oc1); d["lpop"] = np.log1p(d["pop"])
    dec = {}
    for y in ["lopen", "loc1", "lpop", "d1_5", "d1_63"]:
        m = smf.ols(f"{y} ~ rev + CROWD + logproc", d.dropna(subset=["rev", "CROWD", y])).fit(cov_type="HC3")
        dec[y] = dict(n=int(m.nobs), r2=float(m.rsquared), coef={k: float(v) for k, v in m.params.items()}, t={k: float(v) for k, v in m.tvalues.items()})
    share_open = float((d.lopen.sum()) / d.lpop.sum())

    # ---------- 3. groups ----------
    d["rev_g"] = pd.cut(d.rev, [-1, 0.0, 0.2, 9], labels=["At or below first-range midpoint", "Up to 20% above", "More than 20% above"]).astype(str)
    d["sig_g"] = np.where((d.above == 1) & (d.range_raised == 1), "Hot: range raised and priced above it",
                          np.where(d.above == 1, "Warm: above first range", np.where(d.above == 0, "Cold: at or below first range", None)))
    def gstats(col, order):
        out = []
        for k in order:
            g = d[d[col] == k]
            if not len(g):
                continue
            out.append(dict(key=k, n=len(g), names=list(g.ticker), **{m: float(g[m].median()) for m in ["open_pop", "oc1", "close_vs_high", "pop", "gap2", "d1_5", "d1_21", "d1_63", "x63"]},
                            below_open=float((g.oc1 < 0).mean()), broke=float((g["pop"] < 0).mean())))
        kw = {}
        for m in ["open_pop", "pop", "oc1", "d1_5", "d1_21", "d1_63"]:
            arr = [d[d[col] == k][m].dropna().values for k in order if (d[col] == k).sum() >= 3]
            kw[m] = float(stats.kruskal(*arr).pvalue) if len(arr) >= 2 else None
        return dict(rows=out, kw=kw)
    groups = {"Price revision": gstats("rev_g", ["At or below first-range midpoint", "Up to 20% above", "More than 20% above"]),
              "Book-building signal": gstats("sig_g", ["Cold: at or below first range", "Warm: above first range", "Hot: range raised and priced above it"])}
    if d.oversub.notna().sum() >= 10:
        d["ov_g"] = pd.cut(d.oversub, [0, 10, 25, 1e9], labels=["Under 10x", "10x to 25x", "25x or more"]).astype(str)
        groups["Reported oversubscription"] = gstats("ov_g", ["Under 10x", "10x to 25x", "25x or more"])

    # ---------- 4. close-to-close paths days 1-10 by signal group ----------
    P = pd.DataFrame({k: pd.Series(v) for k, v in paths.items()})
    cpath = {}
    for k in ["Cold: at or below first range", "Warm: above first range", "Hot: range raised and priced above it"]:
        tk = d[d.sig_g == k].ticker
        m = P[tk]; cpath[k] = dict(n=len(tk), mean=(m.mean(axis=1) - 1).tolist(), median=(m.median(axis=1) - 1).tolist())

    # ---------- 5. entry/exit matrix (subscribe vs open vs first close) ----------
    def tr(x):
        x = pd.Series(x).dropna().values
        if len(x) < 4:
            return None
        bs = RNG.choice(x, (5000, len(x))).mean(axis=1)
        return dict(n=len(x), mean=float(x.mean()), median=float(np.median(x)), lo=float(np.percentile(bs, 2.5)), hi=float(np.percentile(bs, 97.5)),
                    hit=float((x > 0).mean()), sr=float(x.mean() / x.std(ddof=1)) if x.std(ddof=1) > 0 else None, p=float(stats.wilcoxon(x).pvalue))
    entries = {"Subscribe at offer": {"Sell at open": "offer_open", "Sell at day-1 close": "pop", "Sell day 5": "offer_to5", "Sell day 21": "offer_to21", "Sell day 63": "offer_to63"},
               "Buy the open": {"Sell at day-1 close": "oc1", "Sell day 5": "open_to5", "Sell day 21": "open_to21", "Sell day 63": "open_to63"},
               "Buy the day-1 close": {"Sell day 5": "d1_5", "Sell day 21": "d1_21", "Sell day 63": "d1_63"}}
    matrix = {}
    for grp in ["All", "Cold: at or below first range", "Warm: above first range", "Hot: range raised and priced above it"]:
        sub = d if grp == "All" else d[d.sig_g == grp]
        matrix[grp] = {e: {x: tr(sub[c]) for x, c in ex.items()} for e, ex in entries.items()}

    # ---------- 6. predictive model of the pop (leave-one-out) ----------
    mm = d.dropna(subset=["rev", "CROWD", "lpop"]).reset_index(drop=True)
    form = "lpop ~ rev + CROWD + logproc"
    preds = []
    for i in range(len(mm)):
        m = smf.ols(form, mm.drop(i)).fit(); preds.append(float(m.predict(mm.iloc[[i]]).iloc[0]))
    mm["loo"] = preds
    ss_res = ((mm["lpop"] - mm.loo) ** 2).sum(); ss_tot = ((mm["lpop"] - mm["lpop"].mean()) ** 2).sum()
    full = smf.ols(form, mm).fit(cov_type="HC3")
    resid = mm["lpop"] - full.fittedvalues
    # Anthropic: revision from the prediction-market offer, crowding today, proceeds from the amount-raised market
    pm = json.load(open(DATA / "pm.json")); crw = json.load(open(DATA / "crowding.json"))["anthropic"]
    ant = []
    for lab, offer in [("Prediction-market offer (amount raised)", pm["offer_from_raise"]["mean"]), ("Prediction-market offer (valuation)", pm["offer_from_valuation"]["mean"]),
                       ("Top of range ($78)", 78.0), ("Midpoint of range ($74)", 74.0)]:
        x = pd.DataFrame(dict(rev=[offer / 74 - 1], CROWD=[crw["CROWD"]], logproc=[np.log(825 * offer)]))
        mu = float(full.predict(x).iloc[0])
        sims = mu + RNG.choice(resid.values, 20000) + RNG.normal(0, np.sqrt(np.diag(full.cov_params())).mean() * 0, 20000)
        ant.append(dict(label=lab, offer=float(offer), rev=float(offer / 74 - 1), pred=float(np.expm1(mu)), p10=float(np.expm1(np.percentile(sims, 10))),
                        p90=float(np.expm1(np.percentile(sims, 90))), p_pos=float((sims > 0).mean())))
    # crowding at the cohort median instead of today's (sensitivity)
    x = pd.DataFrame(dict(rev=[pm["offer_from_raise"]["mean"] / 74 - 1], CROWD=[float(d.CROWD.median())], logproc=[np.log(825 * pm["offer_from_raise"]["mean"])]))
    ant_med_crowd = float(np.expm1(full.predict(x).iloc[0]))
    model = dict(form=form, n=int(full.nobs), r2=float(full.rsquared), r2_loo=float(1 - ss_res / ss_tot), coef={k: float(v) for k, v in full.params.items()},
                 t={k: float(v) for k, v in full.tvalues.items()}, anthropic=ant, anthropic_median_crowding=ant_med_crowd,
                 extrapolation=dict(logproc_ant=float(np.log(825 * pm["offer_from_raise"]["mean"])), logproc_max=float(mm.logproc.max()),
                                    crowd_ant=float(crw["CROWD"]), crowd_min=float(mm.CROWD.min())))

    # ---------- 7. hourly: first-hour high by signal (14 IPOs) ----------
    intra = json.load(open(DATA / "intraday.json"))["hourly"]
    used = intra["names"]
    hourly = dict(n=len(used), names=used, hot=list(d[(d.ticker.isin(used)) & (d.sig_g == "Hot: range raised and priced above it")].ticker))

    out = dict(cohort=json.loads(d[["ticker", "name", "ipo_date", "offer", "rev", "range_rev", "rev_final", "above", "range_raised", "upsized", "oversub", "float_pct", "logproc", "CROWD", "PSI",
                                    "open_pop", "oc1", "close_vs_high", "pop", "gap2", "oc2", "d1_5", "d1_21", "d1_63", "x63", "sig_g", "rev_g"]].to_json(orient="records")),
               corr=corr, decomposition=dec, share_open=share_open, groups=groups, cpath=cpath, matrix=matrix, model=model, hourly=hourly,
               n_oversub=int(d.oversub.notna().sum()))
    json.dump(out, open(DATA / "signals.json", "w"), default=float)

    pd.set_option("display.width", 230, "display.max_columns", 30)
    c = pd.DataFrame(corr); print(c.sort_values("p").head(24).round(3).to_string(index=False))
    print("\nshare of log pop from opening print:", round(share_open, 3))
    for k, v in dec.items(): print(k, {kk: (round(v['coef'][kk], 3), round(v['t'][kk], 1)) for kk in v['coef']}, "R2", round(v['r2'], 2))
    for k, g in groups.items():
        print("\n==", k, {m: (round(p, 3) if p is not None else None) for m, p in g["kw"].items()})
        print(pd.DataFrame(g["rows"]).drop(columns="names").round(3).to_string(index=False))
    print("\nMATRIX")
    for grp, e in matrix.items():
        print(grp, {en: {ex: (round(v['mean'] * 100, 1), round(v['hit'] * 100), round(v['sr'], 2) if v and v['sr'] is not None else None) if v else None for ex, v in xs.items()} for en, xs in e.items()})
    print("\nMODEL", {k: (round(model['coef'][k], 3), round(model['t'][k], 1)) for k in model['coef']}, "R2", round(model['r2'], 2), "LOO R2", round(model['r2_loo'], 2))
    print("ANT", json.dumps(ant, indent=0)[:900], "median-crowding pred", round(ant_med_crowd, 3), model["extrapolation"])
    print("n oversub", out["n_oversub"], "| cpath", {k: (v['n'], [round(x * 100, 1) for x in v['mean'][:6]]) for k, v in cpath.items()})


if __name__ == "__main__":
    main()
