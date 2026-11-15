"""Liquidity transfer and mechanism tests: how does a new stock interact with the rest of the market?

Usage: python3 ipo_study/transfer.py  -> ipo_study/data/transfer.json (+ prints)

H-A  Peer substitution: investors sell listed peers to buy the new issue. Test: sector ETF minus SPY around each
     of the 43 listings (T-10..T-1, T0..T+5, T+6..T+20) against random dates (sector-specific null), all IPOs and large ones.
H-B  Attention / volume transfer: dollar volume migrates toward the new issue. Test: abnormal volume (log of volume
     over its prior-60-session mean) for SPY, QQQ, the sector ETF and the IPO ETF in the listing week, vs random weeks.
H-C  Liquidity-driven co-selling: when liquidity is pulled, assets fall together. Test: change in the 10-session
     correlation of daily returns (SPY-BTC, SPY-GLD, BTC-GLD) from the 10 sessions before T-10 to T-10..T-1, large listings vs placebo.
H-D  The IPO joins the crowded book: daily IPO returns (days 2-63) regressed on QQQ, the high-beta spread (SPHB-SPLV)
     and Bitcoin. Average betas and their link with positioning at listing.
H-E  Crowding mean-reverts: does a stretched high-beta spread at listing predict its own reversal over the next 63
     sessions (all days, Newey-West), and how much of the PSI-fade link runs through that factor reversal (mediation)?
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
import yfinance as yf
from scipy import stats

DATA = Path(__file__).parent / "data"
RNG = np.random.default_rng(29)
SECTOR_ETF = {"Software, AI & semis": "IGV", "Consumer internet": "FDN", "Fintech & financials": "ARKF", "Healthcare": "XLV",
              "Consumer & leisure": "XLY", "Industrials, energy & space": "XLI"}


def main():
    co = pd.read_csv(DATA / "enriched_cohort.csv").merge(pd.read_csv(DATA / "deal_terms.csv")[["ticker", "proceeds_m"]], on="ticker")
    pos = json.load(open(DATA / "positioning.json"))
    ts = pd.DataFrame({k: v for k, v in pos["ts"].items() if k != "dates"}, index=pd.to_datetime(pos["ts"]["dates"]))
    tick = ["SPY", "QQQ", "SPHB", "SPLV", "BTC-USD", "GLD", "IPO"] + list(SECTOR_ETF.values())
    raw = yf.download(tick, start="2019-06-01", progress=False, auto_adjust=True)
    px, vol = raw["Close"], raw["Volume"]
    cal = px["SPY"].dropna().index; px = px.reindex(cal).ffill(); vol = vol.reindex(cal)
    lr = np.log(px); dr = lr.diff()
    lo = cal.get_loc(cal[cal >= "2020-06-01"][0]); hi = len(cal) - 70
    idx_all = np.arange(lo, hi)
    t0s = {r.ticker: cal.get_indexer([pd.Timestamp(r.ipo_date)], method="bfill")[0] for r in co.itertuples()}
    large = set(co[co.proceeds_m >= 1000].ticker)

    def perm(vals, null, B=5000):
        vals = np.asarray(vals, float); vals = vals[~np.isnan(vals)]; null = np.asarray(null, float); null = null[~np.isnan(null)]
        d = RNG.choice(null, (B, len(vals))).mean(axis=1)
        return float((np.abs(d - null.mean()) >= abs(vals.mean() - null.mean())).mean()), float(null.mean())

    out = {}
    # ---------------- H-A peer substitution ----------------
    W = {"pre": (-11, -1), "list": (-1, 5), "late": (5, 20)}
    rel = {s: lr[e] - lr["SPY"] for s, e in SECTOR_ETF.items()}
    ha = {}
    for grp, names in [("All IPOs", set(co.ticker)), ("Large IPOs ($1bn+)", large)]:
        res = {}
        for w, (a, b) in W.items():
            vals, nulls = [], []
            for r in co[co.ticker.isin(names)].itertuples():
                t = t0s[r.ticker]; s_ = rel[r.sector]
                vals.append(float(s_.iloc[t + b] - s_.iloc[t + a]))
            # null: random date, random sector drawn in the same proportions
            secs = co[co.ticker.isin(names)].sector.values
            for _ in range(4000):
                t = RNG.choice(idx_all); s_ = rel[RNG.choice(secs)]
                nulls.append(float(s_.iloc[t + b] - s_.iloc[t + a]))
            p, mu = perm(vals, nulls)
            res[w] = dict(mean=float(np.nanmean(vals)), median=float(np.nanmedian(vals)), hit=float(np.mean(np.array(vals) > 0)), null=mu, p=p, n=len(vals))
        ha[grp] = res
    out["peer"] = ha
    # Anthropic-relevant peers: software and AI complex around SpaceX / large AI listings
    # ---------------- H-B volume / attention ----------------
    av = np.log(vol / vol.rolling(60).mean().shift(1))
    hb = {}
    for k, col in [("S&P 500 (SPY)", "SPY"), ("Nasdaq (QQQ)", "QQQ"), ("Recent IPOs (IPO ETF)", "IPO"), ("Bitcoin", "BTC-USD")]:
        res = {}
        for w, (a, b) in [("pre", (-10, -1)), ("list", (0, 4))]:
            vals = [float(av[col].iloc[t0s[t] + a:t0s[t] + b + 1].mean()) for t in large]
            nulls = [float(av[col].iloc[t + a:t + b + 1].mean()) for t in idx_all[::2]]
            p, mu = perm(vals, nulls); res[w] = dict(mean=float(np.nanmean(vals)), null=mu, p=p, n=len(vals))
        hb[k] = res
    sec_av = []
    for r in co[co.ticker.isin(large)].itertuples():
        sec_av.append(float(av[SECTOR_ETF[r.sector]].iloc[t0s[r.ticker]:t0s[r.ticker] + 5].mean()))
    nulls = [float(av[e].iloc[t:t + 5].mean()) for t in idx_all[::3] for e in SECTOR_ETF.values()]
    p, mu = perm(sec_av, nulls); hb["Own sector ETF"] = {"list": dict(mean=float(np.nanmean(sec_av)), null=mu, p=p, n=len(sec_av))}
    out["volume"] = hb
    # ---------------- H-C correlation shift ----------------
    pairs = [("SPY", "BTC-USD"), ("SPY", "GLD"), ("BTC-USD", "GLD"), ("SPY", "IPO")]
    def cshift(t, x, y):
        a = dr[x].iloc[t - 21:t - 11].corr(dr[y].iloc[t - 21:t - 11]); b = dr[x].iloc[t - 11:t - 1].corr(dr[y].iloc[t - 11:t - 1])
        return b - a, b
    hc = {}
    for x, y in pairs:
        ev = [cshift(t0s[t], x, y) for t in large]
        nul = [cshift(t, x, y) for t in idx_all[::2]]
        p1, m1 = perm([e[0] for e in ev], [n[0] for n in nul]); p2, m2 = perm([e[1] for e in ev], [n[1] for n in nul])
        sx = cshift(t0s["SPCX"], x, y)
        hc[f"{x}|{y}"] = dict(shift=float(np.nanmean([e[0] for e in ev])), null_shift=m1, p_shift=p1, level=float(np.nanmean([e[1] for e in ev])), null_level=m2, p_level=p2,
                              spacex_shift=float(sx[0]), spacex_level=float(sx[1]))
    # Anthropic: corr in the 10 sessions to 13 Nov vs the 10 before
    tN = cal.get_indexer([pd.Timestamp("2026-11-13")], method="ffill")[0] + 1
    for x, y in pairs:
        hc[f"{x}|{y}"]["anthropic_shift"], hc[f"{x}|{y}"]["anthropic_level"] = [float(v) for v in cshift(tN, x, y)]
    out["corr"] = hc
    # ---------------- H-D IPO factor betas ----------------
    fac = pd.DataFrame({"QQQ": dr["QQQ"], "BETA": dr["SPHB"] - dr["SPLV"], "BTC": dr["BTC-USD"]})
    rows = []
    for r in co.itertuples():
        h = yf.Ticker(r.ticker).history(period="max", auto_adjust=True)["Close"]; h.index = h.index.tz_localize(None)
        ri = np.log(h).diff().iloc[1:63]
        X = fac.reindex(ri.index).dropna(); y_ = ri.reindex(X.index)
        if len(X) < 40:
            continue
        m = sm.OLS(y_.values, sm.add_constant(X.values)).fit()
        # factor-implied and residual cumulative return over days 2-63
        fitted = X.values @ m.params[1:]
        rows.append(dict(ticker=r.ticker, b_qqq=m.params[1], b_beta=m.params[2], b_btc=m.params[3], t_beta=m.tvalues[2], r2=m.rsquared,
                         fac_ret=float(fitted.sum()), resid_ret=float((y_.values - fitted).sum()), tot=float(y_.sum()),
                         PSI=float(ts.PSI.loc[:pd.Timestamp(r.ipo_date) - pd.Timedelta(days=1)].iloc[-1])))
    B = pd.DataFrame(rows)
    def cs(col):
        x = B[col]; bs = RNG.choice(x.values, (5000, len(x))).mean(axis=1)
        return dict(mean=float(x.mean()), median=float(x.median()), lo=float(np.percentile(bs, 2.5)), hi=float(np.percentile(bs, 97.5)),
                    t=float(stats.ttest_1samp(x, 0).statistic), p=float(stats.ttest_1samp(x, 0).pvalue))
    hd = {c: cs(c) for c in ["b_qqq", "b_beta", "b_btc", "r2"]}
    hd["share_beta_sig"] = float((B.t_beta.abs() > 2).mean())
    for c in ["b_qqq", "b_beta", "b_btc", "fac_ret", "resid_ret", "tot"]:
        rho, p = stats.spearmanr(B.PSI, B[c]); hd[f"psi_vs_{c}"] = dict(rho=float(rho), p=float(p))
    out["betas"] = hd; out["beta_rows"] = json.loads(B.round(5).to_json(orient="records"))
    # ---------------- H-E crowding reversal ----------------
    spread = lr["SPHB"] - lr["SPLV"]; b63 = spread - spread.shift(63)
    ys, xs = [], []
    for t in idx_all:
        if np.isnan(b63.iloc[t]):
            continue
        ys.append(float(spread.iloc[t + 63] - spread.iloc[t])); xs.append(float(b63.iloc[t]))
    m = sm.OLS(np.array(ys), sm.add_constant(np.array(xs))).fit(cov_type="HAC", cov_kwds={"maxlags": 63})
    he = dict(slope=float(m.params[1]), t=float(m.tvalues[1]), p=float(m.pvalues[1]), r2=float(m.rsquared), n=int(m.nobs))
    # after listings: factor return next 63 sessions by PSI tercile
    co["PSI"] = [float(ts.PSI.loc[:pd.Timestamp(d) - pd.Timedelta(days=1)].iloc[-1]) for d in co.ipo_date]
    co["fac63"] = [float(spread.iloc[min(t0s[t] + 62, len(cal) - 1)] - spread.iloc[t0s[t]]) if t0s[t] + 62 < len(cal) else np.nan for t in co.ticker]
    co["terc"] = pd.qcut(co.PSI, 3, labels=["Low PSI", "Mid PSI", "High PSI"])
    he["fac63_by_tercile"] = {str(k): dict(n=int(len(g)), median=float(g.fac63.median()), mean=float(g.fac63.mean())) for k, g in co.groupby("terc", observed=True)}
    rho, p = stats.spearmanr(co.PSI, co.fac63, nan_policy="omit"); he["psi_vs_fac63"] = dict(rho=float(rho), p=float(p))
    # mediation: does PSI still predict the IPO's day-63 return after removing its factor-implied part?
    B2 = B.merge(co[["ticker", "r63"]], on="ticker")
    he["mediation"] = {c: dict(zip(["rho", "p"], [float(v) for v in stats.spearmanr(B2.PSI, B2[c])])) for c in ["tot", "fac_ret", "resid_ret"]}
    out["reversal"] = he

    json.dump(out, open(DATA / "transfer.json", "w"), default=float)
    print("H-A peer substitution"); [print(" ", g, {w: (round(v['mean'] * 100, 2), round(v['null'] * 100, 2), round(v['p'], 3)) for w, v in r.items()}) for g, r in ha.items()]
    print("H-B volume"); [print(" ", k, {w: (round(v['mean'], 3), round(v['null'], 3), round(v['p'], 3)) for w, v in r.items()}) for k, r in hb.items()]
    print("H-C corr"); [print(" ", k, {kk: round(vv, 3) for kk, vv in v.items()}) for k, v in hc.items()]
    print("H-D betas"); print(json.dumps(hd, indent=0, default=float)[:1500])
    print("H-E reversal", json.dumps(he, default=float)[:1200])


if __name__ == "__main__":
    main()
