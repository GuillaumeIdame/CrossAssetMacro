"""Do crowded trades give a signal on the IPO itself? Within-bucket tests.

Usage: python3 ipo_study/crowding.py   -> ipo_study/data/crowding.json (+ prints)

Crowding signals, measured on the last close before listing (all backward-looking):
  beta63    SPHB/SPLV 63d relative return (crowded high beta)
  mtum63    MTUM/SPY 63d relative return (crowded momentum)
  btc63     Bitcoin 63d return (crowded speculative risk)
  ipo63     Renaissance IPO ETF / SPY 63d (crowding into recent new issues)
  sector63  the IPO's sector ETF / SPY 63d (crowding into its theme)
  CROWD     composite: mean z-score of the five
IPO-level crowding (observed after listing, so used for later horizons only):
  turn1     day-1 volume / shares offered;  turn5  days 1-5 volume / shares offered
Outcomes: pop (day-1 close vs offer), r21/r63/r126 (from day-1 close), x63 (vs QQQ), d5_63 (day 5 to 63)
Tests: Spearman with Benjamini-Hochberg q; within each bucketing (market cap, sector, quarter, 10Y trend,
VIX, float, demand, PSI) the crowded-vs-not split per bucket, OLS r63 ~ CROWD + bucket fixed effects (HC3),
and a stratified permutation test that shuffles CROWD only within buckets.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
import yfinance as yf
from scipy import stats

DATA = Path(__file__).parent / "data"
RNG = np.random.default_rng(17)
SECTOR_ETF = {"Software, AI & semis": "IGV", "Consumer internet": "FDN", "Fintech & financials": "ARKF", "Healthcare": "XLV",
              "Consumer & leisure": "XLY", "Industrials, energy & space": "XLI"}


def bh(p):
    p = np.asarray(p, float); n = len(p); o = np.argsort(p)
    q = np.empty(n); q[o] = np.minimum.accumulate((p[o] * n / np.arange(1, n + 1))[::-1])[::-1]
    return np.minimum(q, 1)


def main():
    co = pd.read_csv(DATA / "enriched_cohort.csv").merge(pd.read_csv(DATA / "deal_terms.csv")[["ticker", "demand", "float_pct", "revision_pct", "proceeds_m", "offer"]],
                                                         on="ticker", suffixes=("", "_t"))
    pos = json.load(open(DATA / "positioning.json"))
    ts = pd.DataFrame({k: v for k, v in pos["ts"].items() if k != "dates"}, index=pd.to_datetime(pos["ts"]["dates"]))
    tick = ["SPHB", "SPLV", "MTUM", "SPY", "BTC-USD", "IPO", "QQQ"] + list(SECTOR_ETF.values())
    px = yf.download(tick, start="2019-06-01", progress=False, auto_adjust=True)["Close"]
    cal = px["SPY"].dropna().index; px = px.reindex(cal).ffill()
    rel = lambda a, b: (px[a] / px[b]) / (px[a] / px[b]).shift(63) - 1
    sig = pd.DataFrame({"beta63": rel("SPHB", "SPLV"), "mtum63": rel("MTUM", "SPY"), "btc63": px["BTC-USD"] / px["BTC-USD"].shift(63) - 1, "ipo63": rel("IPO", "SPY")})
    secrel = {s: rel(e, "SPY") for s, e in SECTOR_ETF.items()}

    rows = []
    for _, r in co.iterrows():
        d0 = pd.Timestamp(r.ipo_date); s = cal[cal < d0][-1]
        h = yf.Ticker(r.ticker).history(period="max", auto_adjust=False); h.index = h.index.tz_localize(None)
        c, v = h["Close"], h["Volume"]
        q = px["QQQ"].reindex(c.index).ffill()
        shares_off = r.proceeds_m * 1e6 / r.offer
        row = dict(ticker=r.ticker, name=r["name"], ipo_date=r.ipo_date, sector=r.sector, bucket=r.bucket, quarter=r.quarter, yld=r.yld, vix_reg=r.vix_reg,
                   demand=r.demand, float_pct=r.float_pct, **{k: float(sig[k].loc[s]) for k in sig}, sector63=float(secrel[r.sector].loc[s]),
                   PSI=float(ts.PSI.loc[:s].iloc[-1]), turn1=float(v.iloc[0] / shares_off), turn5=float(v.iloc[:5].sum() / shares_off),
                   pop=r.d1_pop, r21=r.r21, r63=r.r63, r126=r.r126, r5=r.r5,
                   x63=float(c.iloc[62] / c.iloc[0] - q.iloc[62] / q.iloc[0]) if len(c) >= 63 else np.nan)
        row["d5_63"] = (1 + r.r63) / (1 + r.r5) - 1 if pd.notna(r.r63) else np.nan
        rows.append(row)
    d = pd.DataFrame(rows)
    comp = ["beta63", "mtum63", "btc63", "ipo63", "sector63"]
    Z = (d[comp] - d[comp].mean()) / d[comp].std()
    d["CROWD"] = Z.mean(axis=1)
    d["crowded"] = np.where(d.CROWD >= d.CROWD.median(), "Crowded", "Not crowded")
    d["float_b"] = pd.cut(d.float_pct, [0, .08, .15, 1], labels=["Float <8%", "Float 8-15%", "Float >15%"]).astype(str)
    d["demand_b"] = np.where(d.demand == "Above range", "Above range", "At or below range"); d.loc[d.demand.isna(), "demand_b"] = None
    d["psi_t"] = pd.qcut(d.PSI, 3, labels=["Low PSI", "Mid PSI", "High PSI"]).astype(str)
    d["cap_b"] = np.where(d.bucket.isin(["Large 30-100B", "Mega >=100B"]), "Large & mega ($30B+)", d.bucket)

    # ---------- 1. correlations ----------
    sigs = comp + ["CROWD", "PSI", "turn1", "turn5"]
    outs = ["pop", "r21", "r63", "r126", "x63", "d5_63"]
    corr = []
    for s_ in sigs:
        for y in outs:
            if s_ in ("turn1", "turn5") and y == "pop":
                continue  # turnover is observed on/after day 1
            if s_ == "turn5" and y in ("r21",):
                pass
            ok = d[[s_, y]].dropna(); rho, p = stats.spearmanr(ok[s_], ok[y]); corr.append(dict(signal=s_, outcome=y, n=len(ok), rho=float(rho), p=float(p)))
    for c_, qq in zip(corr, bh([c["p"] for c in corr])):
        c_["q"] = float(qq)

    # ---------- 2. bucketing ----------
    dims = {"Market cap": "cap_b", "Sector": "sector", "Listing quarter": "quarter", "10Y trend": "yld", "VIX at listing": "vix_reg",
            "Float": "float_b", "Pricing vs range": "demand_b", "PSI tercile": "psi_t"}
    buck = {}
    for lab, col in dims.items():
        g = d.dropna(subset=[col, "r63"])
        g = g[g[col] != "nan"]
        rows_b = []
        for k, gg in g.groupby(col):
            cr, nc = gg[gg.crowded == "Crowded"], gg[gg.crowded == "Not crowded"]
            rho = stats.spearmanr(gg.CROWD, gg.r63)[0] if len(gg) >= 5 else np.nan
            rows_b.append(dict(key=str(k), n=len(gg), n_cr=len(cr), n_nc=len(nc), pop_cr=cr["pop"].median() if len(cr) else np.nan, pop_nc=nc["pop"].median() if len(nc) else np.nan,
                               r63_cr=cr.r63.median() if len(cr) else np.nan, r63_nc=nc.r63.median() if len(nc) else np.nan, rho=float(rho) if not np.isnan(rho) else None,
                               same_sign=bool(len(cr) and len(nc) and cr.r63.median() < nc.r63.median())))
        # fixed-effects regressions
        fe = {}
        for y in ["pop", "r63", "x63"]:
            m = smf.ols(f"{y} ~ CROWD + C({col})", g.dropna(subset=[y])).fit(cov_type="HC3")
            fe[y] = dict(coef=float(m.params["CROWD"]), t=float(m.tvalues["CROWD"]), p=float(m.pvalues["CROWD"]), n=int(m.nobs))
        # stratified permutation on r63
        obs = stats.spearmanr(g.CROWD, g.r63)[0]; perm = []
        for _ in range(5000):
            sh = g.groupby(col)["CROWD"].transform(lambda x: x.sample(frac=1, random_state=int(RNG.integers(1e9))).values)
            perm.append(stats.spearmanr(sh, g.r63)[0])
        perm = np.array(perm)
        buck[lab] = dict(rows=rows_b, fe=fe, perm_p=float((np.abs(perm) >= abs(obs)).mean()), rho_all=float(obs),
                         share_negative=float(np.mean([r["same_sign"] for r in rows_b if r["n_cr"] and r["n_nc"]])),
                         n_split=int(sum(1 for r in rows_b if r["n_cr"] and r["n_nc"])))
    # ---------- 3. horse race: crowding vs PSI vs demand ----------
    race = {}
    for y in ["pop", "r63", "x63"]:
        for f in [f"{y} ~ CROWD", f"{y} ~ CROWD + PSI", f"{y} ~ CROWD + revision_pct", f"{y} ~ CROWD + PSI + revision_pct + np.log(float_pct)", f"{y} ~ turn1 + CROWD"]:
            dd = d.merge(co[["ticker", "revision_pct"]], on="ticker", how="left") if "revision_pct" in f else d
            if "turn1" in f and y == "pop":
                continue
            m = smf.ols(f, dd.dropna(subset=[y])).fit(cov_type="HC3")
            race[f] = dict(n=int(m.nobs), r2=float(m.rsquared), coef={k: float(v) for k, v in m.params.items()}, t={k: float(v) for k, v in m.tvalues.items()})
    # ---------- 4. crowded x demand x turnover tables ----------
    d["turn_hi"] = np.where(d.turn1 >= d.turn1.median(), "High day-1 turnover", "Low day-1 turnover")
    two = {}
    for a, b in [("crowded", "demand_b"), ("crowded", "turn_hi"), ("turn_hi", "demand_b")]:
        t = d.dropna(subset=[a, b]).groupby([a, b]).agg(n=("r63", "size"), pop=("pop", "median"), r63=("r63", "median"), x63=("x63", "median"))
        two[f"{a}|{b}"] = [dict(a=i[0], b=i[1], **{k: float(v) for k, v in r.items()}) for i, r in t.iterrows()]
    # strategy: short day 5 -> 63 when crowded (and crowded+above range)
    strat = {}
    for lab, m in [("All", d.ticker.notna()), ("Crowded", d.crowded == "Crowded"), ("Not crowded", d.crowded == "Not crowded"),
                   ("Crowded and above range", (d.crowded == "Crowded") & (d.demand_b == "Above range")), ("High day-1 turnover", d.turn_hi == "High day-1 turnover")]:
        x = -d.loc[m, "d5_63"].dropna().values
        bs = RNG.choice(x, (10000, len(x))).mean(axis=1)
        strat[lab] = dict(n=len(x), mean=float(x.mean()), lo=float(np.percentile(bs, 2.5)), hi=float(np.percentile(bs, 97.5)), hit=float((x > 0).mean()),
                          p=float(stats.wilcoxon(x).pvalue), sr=float(x.mean() / x.std(ddof=1)))
    # Anthropic now
    s_now = cal[cal <= "2026-11-13"][-1]
    ant = {k: float(sig[k].loc[s_now]) for k in sig}; ant["sector63"] = float(secrel["Software, AI & semis"].loc[s_now])
    zant = {k: (ant[k] - d[k].mean()) / d[k].std() for k in comp}; ant["CROWD"] = float(np.mean(list(zant.values())))
    ant["CROWD_pct_vs_cohort"] = float((d.CROWD < ant["CROWD"]).mean())
    sx = d[d.ticker == "SPCX"].iloc[0]
    out = dict(cohort=json.loads(d.drop(columns=[]).to_json(orient="records")), corr=corr, buckets=buck, race=race, two=two, strat=strat, anthropic=ant,
               spacex=dict(CROWD=float(sx.CROWD), pct=float((d.CROWD < sx.CROWD).mean()), turn1=float(sx.turn1)), median_crowd=float(d.CROWD.median()))
    json.dump(out, open(DATA / "crowding.json", "w"), default=float)

    pd.set_option("display.width", 220, "display.max_columns", 30)
    cdf = pd.DataFrame(corr); print(cdf.sort_values("p").head(20).round(3).to_string(index=False))
    for lab, b in buck.items():
        print(f"\n== {lab}: rho_all {b['rho_all']:+.2f}, stratified perm p {b['perm_p']:.3f}, crowded worse in {b['share_negative']*100:.0f}% of {b['n_split']} buckets;",
              " | ".join(f"{y}: {v['coef']:+.3f} (t {v['t']:+.1f})" for y, v in b["fe"].items()))
        print(pd.DataFrame(b["rows"]).round(3).to_string(index=False))
    print("\nRACE"); [print(k, {kk: (round(v['coef'][kk], 3), round(v['t'][kk], 1)) for kk in v['coef']}, round(v['r2'], 2)) for k, v in race.items()]
    print("\nTWO-WAY"); [print(k, v) for k, v in two.items()]
    print("\nSTRAT", json.dumps(strat, indent=0)[:900]); print("ANT", ant); print("SPCX", out["spacex"])


if __name__ == "__main__":
    main()
