"""Monte Carlo EV of a GBP 65k application to the Anthropic UK retail offer via an IBKR ISA.
Offer ~ Polymarket; fill ~ UK-offer scale-back with winner's curse; close ~ blend of signal model and Polymarket close
(Gaussian copula with the offer); exits from cohort day-1->5/21 returns. Output data/ev_trade.json."""
import json
import numpy as np, pandas as pd, statsmodels.formula.api as smf
from scipy import stats

rng = np.random.default_rng(42); N = 200_000
GBP, FX = 65_000, 1.3212; USD = GBP * FX
S = json.load(open("data/signals.json")); P = json.load(open("data/pm.json"))
co = pd.DataFrame(S["cohort"]); d = co.dropna(subset=["rev", "CROWD", "pop", "logproc"]).copy(); d["lpop"] = np.log1p(d["pop"])
mc = smf.ols("lpop ~ rev + CROWD + logproc", d).fit(); res = mc.resid.values; CR = S["model"]["extrapolation"]["crowd_ant"]

# --- offer: average of the two Polymarket-implied offer distributions, via quantile interpolation
qs = [0.10, 0.25, 0.50, 0.75, 0.90]
def qfun(dd):
    v = [dd["p10"], dd["p25"], dd["median"], dd["p75"], dd["p90"]]; return v
qv = np.mean([qfun(P["offer_from_raise"]), qfun(P["offer_from_valuation"])], axis=0)
# extend tails linearly
xq = np.r_[0.0, qs, 1.0]; yq = np.r_[qv[0] - 1.25 * (qv[1] - qv[0]) * 2, qv, qv[-1] + 1.25 * (qv[-1] - qv[-2]) * 2]
z = rng.multivariate_normal([0, 0], [[1, 0.7], [0.7, 1]], N)          # copula offer <-> PM close
u_off, u_close = stats.norm.cdf(z[:, 0]), stats.norm.cdf(z[:, 1])
offer = np.interp(u_off, xq, yq)
rev = offer / 74 - 1

# --- close, source A: signal model at Anthropic's crowding and size
lc = mc.params["Intercept"] + mc.params["rev"] * rev + mc.params["CROWD"] * CR + mc.params["logproc"] * np.log(825 * offer)
closeA = offer * np.exp(lc + rng.choice(res, N))
# --- close, source B: Polymarket day-1 closing cap (basic 13.087bn shares), coupled to the offer
edges = [(0.5, 0.6), (0.6, 0.9), (0.9, 1.2), (1.2, 1.25), (1.25, 1.5), (1.5, 1.75), (1.75, 2.0), (2.0, 2.25), (2.25, 2.5), (2.5, 2.75), (2.75, 3.0), (3.0, 3.5)]
pr = np.array(P["closing_cap"]["p"]); pr /= pr.sum(); cdf = np.r_[0, np.cumsum(pr)]
k = np.clip(np.searchsorted(cdf, u_close, side="right") - 1, 0, len(edges) - 1)
lo = np.array([e[0] for e in edges])[k]; hi = np.array([e[1] for e in edges])[k]
w = (u_close - cdf[k]) / pr[k]; capB = lo + w * (hi - lo); closeB = capB * 1000 / 13.087
src = rng.random(N) < 0.5; close = np.where(src, closeA, closeB)

# --- fill rate (share of the application allocated), winner's curse: cold deals fill more
f = np.where(rev <= 0, rng.uniform(0.5, 1.0, N), np.where(rev <= 0.054, rng.uniform(0.25, 0.6, N), rng.uniform(0.08, 0.35, N)))
shares = np.floor(f * USD / offer); shares = np.minimum(shares, 1000)  # SpaceX-style per-investor cap (not binding here)
cost = shares * offer

# --- exits: from day-1 close, cohort returns by demand group (hot = range raised & above)
hot = co[co.sig_g.str.startswith("Hot", na=False)]; oth = co[~co.sig_g.str.startswith("Hot", na=False)]
def boot(col, mask):
    a = hot[col].dropna().values; b = oth[col].dropna().values
    return np.where(mask, rng.choice(a, N), rng.choice(b, N))
ishot = rev > 0.054
p5 = close * (1 + boot("d1_5", ishot)); p21 = close * (1 + boot("d1_21", ishot))
SLIP, COMM, FXC = 0.003, 0.0035, 0.00002               # day-1/early exit slippage, IBKR per-share commission, FX conversion
def pnl(exitp):
    gross = shares * exitp * (1 - SLIP) - shares * COMM - cost
    return gross / FX - (cost / FX) * FXC * 2           # GBP, ISA: no CGT
out = {}
for name, ex in [("Sell at day-1 close", close), ("Sell half day 1, half day 5", 0.5 * close + 0.5 * p5), ("Sell day 5", p5), ("Sell day 21", p21)]:
    g = pnl(ex)
    out[name] = {"EV": float(g.mean()), "median": float(np.median(g)), "p10": float(np.percentile(g, 10)), "p90": float(np.percentile(g, 90)),
                 "p_loss": float((g < 0).mean()), "EV_pct_alloc": float(g.mean() / (cost / FX).mean()), "EV_pct_applied": float(g.mean() / GBP),
                 "std": float(g.std())}
# cancel rule: cancel if offer > 100 (assumes price talk known before acceptance)
g = pnl(0.5 * close + 0.5 * p5); gc = np.where(offer > 100, 0, g)
out["Half d1 / half d5, cancel if offer > $100"] = {"EV": float(gc.mean()), "median": float(np.median(gc)), "p10": float(np.percentile(gc, 10)), "p90": float(np.percentile(gc, 90)), "p_loss": float((gc < 0).mean())}
# by regime
reg = pd.cut(rev, [-1, 0, 0.054, 0.2, 0.35, 5], labels=["<= $74 (cold)", "$74-78", "$78-89", "$89-100", "> $100"])
G = pd.DataFrame({"reg": reg, "offer": offer, "fill": f, "alloc": cost / FX, "pop": close / offer - 1, "pnl": pnl(close)})
byreg = G.groupby("reg", observed=True).agg(prob=("pnl", lambda x: len(x) / N), offer=("offer", "mean"), fill=("fill", "mean"), alloc=("alloc", "mean"),
                                            pop=("pop", "mean"), p_neg=("pop", lambda x: (x < 0).mean()), ev=("pnl", "mean"))
# sensitivity: hot fill level and source weights
sens = {}
for hf in [0.10, 0.20, 0.30, 0.40]:
    f2 = np.where(rev <= 0, f, np.where(rev <= 0.054, f, hf)); sh2 = np.floor(f2 * USD / offer); c2 = sh2 * offer
    sens[f"hot fill {int(hf*100)}%"] = float(((sh2 * close * (1 - SLIP) - c2) / FX).mean())
for nm, cl in [("model only", closeA), ("Polymarket only", closeB)]:
    sens[nm] = float(((shares * cl * (1 - SLIP) - cost) / FX).mean())
summ = {"application_gbp": GBP, "application_usd": USD, "gbpusd": FX, "offer_mean": float(offer.mean()), "offer_q": {q: float(np.percentile(offer, q)) for q in [10, 50, 90]},
        "fill_mean": float(f.mean()), "alloc_gbp_mean": float((cost / FX).mean()), "alloc_gbp_q": {q: float(np.percentile(cost / FX, q)) for q in [10, 50, 90]},
        "shares_mean": float(shares.mean()), "pop_mean": float((close / offer - 1).mean()), "pop_median": float(np.median(close / offer - 1)),
        "p_close_below_offer": float((close < offer).mean()), "close_mean": float(close.mean())}
json.dump({"summary": summ, "exits": out, "by_regime": byreg.reset_index().astype({"reg": str}).to_dict("records"), "sensitivity": sens}, open("data/ev_trade.json", "w"), indent=1)
pd.set_option("display.width", 200)
print(json.dumps(summ, indent=0)); print(pd.DataFrame(out).T.round(3).to_string()); print(byreg.round(3).to_string()); print({k: round(v) for k, v in sens.items()})

# --- stress: cold/at-range regimes use the cohort's realised pops for comparable revisions (winner's curse made explicit)
cold_pops = co.loc[co.rev <= 0, "pop"].dropna().values; mid_pops = co.loc[(co.rev > 0) & (co.rev <= 0.10), "pop"].dropna().values
close_s = close.copy()
mcold = rev <= 0; mmid = (rev > 0) & (rev <= 0.054)
close_s[mcold] = offer[mcold] * (1 + rng.choice(cold_pops, mcold.sum())); close_s[mmid] = offer[mmid] * (1 + rng.choice(mid_pops, mmid.sum()))
p5s = close_s * (1 + boot("d1_5", ishot))
stress = {}
for name, ex in [("Sell at day-1 close", close_s), ("Sell half day 1, half day 5", 0.5 * close_s + 0.5 * p5s)]:
    g = pnl(ex); stress[name] = {"EV": float(g.mean()), "median": float(np.median(g)), "p10": float(np.percentile(g, 10)), "p90": float(np.percentile(g, 90)), "p_loss": float((g < 0).mean())}
gs = pnl(close_s); stress["cold_regime_ev"] = float(gs[mcold].mean()); stress["cold_pop_mean"] = float((close_s[mcold] / offer[mcold] - 1).mean()); stress["cold_p_neg"] = float((close_s[mcold] < offer[mcold]).mean())
# withdraw-if-cold rule: cancel when price talk is at/below the midpoint (offer <= 74)
gw = np.where(mcold, 0, pnl(0.5 * close_s + 0.5 * p5s))
stress["Half d1/half d5, withdraw if offer <= $74"] = {"EV": float(gw.mean()), "median": float(np.median(gw)), "p10": float(np.percentile(gw, 10)), "p90": float(np.percentile(gw, 90)), "p_loss": float((gw < 0).mean())}
J = json.load(open("data/ev_trade.json")); J["stress"] = stress; json.dump(J, open("data/ev_trade.json", "w"), indent=1)
print("STRESS", json.dumps(stress, indent=0), len(cold_pops), len(mid_pops))
