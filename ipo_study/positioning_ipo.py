"""Robustness of the IPO-level positioning result (PSI at listing vs day-63 return).

Usage: python3 ipo_study/positioning_ipo.py  -> ipo_study/data/positioning_ipo.json
Checks: QQQ-adjusted returns, control for demand (price revision) and size, excluding 2021 listings,
year-block bootstrap of the Spearman correlation, and leave-one-year-out.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
import yfinance as yf
from scipy import stats

DATA = Path(__file__).parent / "data"
RNG = np.random.default_rng(5)
pos = json.load(open(DATA / "positioning.json"))
ts = pd.DataFrame({k: v for k, v in pos["ts"].items() if k != "dates"}, index=pd.to_datetime(pos["ts"]["dates"]))
co = pd.read_csv(DATA / "enriched_cohort.csv").merge(pd.read_csv(DATA / "deal_terms.csv")[["ticker", "revision_pct", "float_pct"]], on="ticker")
qqq = yf.Ticker("QQQ").history(period="max", auto_adjust=True)["Close"]; qqq.index = qqq.index.tz_localize(None)
rows = []
for _, r in co.iterrows():
    d0 = pd.Timestamp(r.ipo_date)
    s = ts.loc[:d0 - pd.Timedelta(days=1)].iloc[-1]  # weekly state, last reading before listing
    c = yf.Ticker(r.ticker).history(period="max", auto_adjust=False)["Close"]; c.index = c.index.tz_localize(None)
    q = qqq.reindex(c.index).ffill()
    x63 = (c.iloc[62] / c.iloc[0] - q.iloc[62] / q.iloc[0]) if len(c) >= 63 else np.nan
    x21 = (c.iloc[20] / c.iloc[0] - q.iloc[20] / q.iloc[0]) if len(c) >= 21 else np.nan
    rows.append(dict(ticker=r.ticker, year=d0.year, PSI=s.PSI, rv21=s.rv21, mom63=s.mom63, beta63=s.beta63, vix_term=s.vix_term, btc_mom63=s.btc_mom63,
                     lev_net=s.lev_net, margin_yoy=s.margin_yoy, pop=r.d1_pop, r21=r.r21, r63=r.r63, x21=x21, x63=x63, rev=r.revision_pct, logcap=np.log(r.cap_b)))
d = pd.DataFrame(rows)
out = {}
def sp(a, b, df=d):
    ok = df[[a, b]].dropna(); rho, p = stats.spearmanr(ok[a], ok[b]); return dict(n=len(ok), rho=float(rho), p=float(p))
out["base"] = {y: sp("PSI", y) for y in ["pop", "r21", "r63", "x21", "x63"]}
out["ex2021"] = {y: sp("PSI", y, d[d.year != 2021]) for y in ["pop", "r63", "x63"]}
out["loyo"] = {str(yr): sp("PSI", "r63", d[d.year != yr])["rho"] for yr in sorted(d.year.unique())}
# year-block bootstrap
yrs = d.year.unique(); bs = []
for _ in range(5000):
    pick = RNG.choice(yrs, len(yrs)); s = pd.concat([d[d.year == y] for y in pick]).dropna(subset=["PSI", "r63"])
    if len(s) > 8 and s.PSI.nunique() > 3: bs.append(stats.spearmanr(s.PSI, s.r63)[0])
out["block_ci_r63"] = [float(np.nanpercentile(bs, 2.5)), float(np.nanpercentile(bs, 97.5))]
# regressions (HC3)
regs = {}
for y in ["pop", "r63", "x63"]:
    for f in [f"{y} ~ PSI", f"{y} ~ PSI + rev + logcap"]:
        m = smf.ols(f, d.dropna(subset=[y, "rev"])).fit(cov_type="HC3")
        regs[f] = dict(n=int(m.nobs), r2=float(m.rsquared), coef={k: float(v) for k, v in m.params.items()}, t={k: float(v) for k, v in m.tvalues.items()}, p={k: float(v) for k, v in m.pvalues.items()})
out["regs"] = regs
# terciles of PSI
d["tercile"] = pd.qcut(d.PSI, 3, labels=["Low PSI", "Mid PSI", "High PSI"])
out["terciles"] = {str(k): dict(n=int(len(g)), psi=float(g.PSI.median()), pop=float(g["pop"].median()), r21=float(g.r21.median()), r63=float(g.r63.median()),
                                x63=float(g.x63.median()), names=list(g.ticker)) for k, g in d.groupby("tercile", observed=True)}
# per-variable correlations with BH across the family
fam = []
for v in ["PSI", "rv21", "mom63", "beta63", "vix_term", "btc_mom63", "lev_net", "margin_yoy"]:
    for y in ["pop", "r63", "x63"]:
        fam.append(dict(var=v, outcome=y, **sp(v, y)))
p = np.array([f["p"] for f in fam]); o = np.argsort(p); n = len(p)
q = np.empty(n); q[o] = np.minimum.accumulate((p[o] * n / np.arange(1, n + 1))[::-1])[::-1]
for f, qq in zip(fam, q): f["q"] = float(min(qq, 1))
out["family"] = fam
out["corr_psi_rev"] = sp("PSI", "rev")
json.dump(out, open(DATA / "positioning_ipo.json", "w"), default=float)
print(json.dumps({k: out[k] for k in ["base", "ex2021", "block_ci_r63", "loyo", "corr_psi_rev"]}, indent=0, default=float))
for k, v in regs.items(): print(k, {kk: (round(v["coef"][kk], 3), round(v["t"][kk], 2)) for kk in v["coef"]}, "R2", round(v["r2"], 2))
print(pd.DataFrame(out["terciles"]).T.drop(columns="names"))
print(pd.DataFrame(fam).round(3).sort_values("p").head(12).to_string(index=False))
