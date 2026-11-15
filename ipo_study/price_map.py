"""Implied open/close price and market cap vs offer price: signal model vs Polymarket. Output data/price_map.json + table."""
import json
import numpy as np, pandas as pd, statsmodels.formula.api as smf
S = json.load(open("data/signals.json")); P = json.load(open("data/pm.json"))
d = pd.DataFrame(S["cohort"]).dropna(subset=["rev", "CROWD", "open_pop", "pop", "logproc"])
d["lopen"] = np.log1p(d.open_pop); d["lpop"] = np.log1p(d["pop"])
mo = smf.ols("lopen ~ rev + CROWD + logproc", d).fit(); mc = smf.ols("lpop ~ rev + CROWD + logproc", d).fit()
ro, rc = mo.resid.values, mc.resid.values
CR = S["model"]["extrapolation"]["crowd_ant"]; BASIC, DIL = 13.087, 15.89
# Polymarket closing-cap distribution: uniform within brackets
lab = ["<0.6", "0.6-0.9", "0.9-1.2", "1.2-1.25", "1.25-1.5", "1.5-1.75", "1.75-2.0", "2.0-2.25", "2.25-2.5", "2.5-2.75", "2.75-3.0", "3.0+"]
edges = [(0.5, 0.6), (0.6, 0.9), (0.9, 1.2), (1.2, 1.25), (1.25, 1.5), (1.5, 1.75), (1.75, 2.0), (2.0, 2.25), (2.25, 2.5), (2.5, 2.75), (2.75, 3.0), (3.0, 3.5)]
pr = np.array(P["closing_cap"]["p"]); pr = pr / pr.sum(); rng = np.random.default_rng(1)
k = rng.choice(len(edges), 200000, p=pr); cap = np.array([rng.uniform(*edges[i]) for i in k[:20000]])
close_pm = cap * 1000 / BASIC
rows = []
for off in [70, 74, 75, 78, 80, 85, 88, 90, 95, 100, 110, 120]:
    x = pd.DataFrame(dict(rev=[off / 74 - 1], CROWD=[CR], logproc=[np.log(825 * off)]))
    lo, lc = float(mo.predict(x)[0]), float(mc.predict(x)[0])
    so, sc = off * np.exp(lo + ro), off * np.exp(lc + rc)
    rows.append({"offer": off, "rev": off / 74 - 1, "cap_offer_basic": off * BASIC / 1000, "cap_offer_dil": off * DIL / 1000,
                 "open_med": off * np.exp(lo), "open_p10": np.percentile(so, 10), "open_p90": np.percentile(so, 90),
                 "close_med": off * np.exp(lc), "close_p10": np.percentile(sc, 10), "close_p90": np.percentile(sc, 90), "p_close_gt_offer_model": float((sc > off).mean()),
                 "cap_open_basic": off * np.exp(lo) * BASIC / 1000, "cap_close_basic": off * np.exp(lc) * BASIC / 1000,
                 "pm_close_mean": float(close_pm.mean()), "pm_pop_mean": float(close_pm.mean() / off - 1), "pm_pop_median": float(np.median(close_pm) / off - 1),
                 "pm_p_close_gt_offer": float((close_pm > off).mean())})
T = pd.DataFrame(rows)
json.dump({"rows": rows, "pm_close_quantiles": {q: float(np.percentile(close_pm, q)) for q in [10, 25, 50, 75, 90]}, "basic_bn": BASIC, "dil_bn": DIL,
           "open_r2": mo.rsquared, "close_r2": mc.rsquared}, open("data/price_map.json", "w"), indent=1)
pd.set_option("display.width", 250)
print(T.round(3).to_string()); print({q: round(float(np.percentile(close_pm, q)), 1) for q in [10, 25, 50, 75, 90]}, "PM close mean", round(close_pm.mean(), 1))
print("open model", mo.params.round(3).to_dict(), round(mo.rsquared, 2))
