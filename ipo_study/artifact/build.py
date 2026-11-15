"""Assemble every analysis output into one data object and inline it into template.html.

Writes index.html (artifact body) and preview.html (full document for local screenshots / PDF).
Adds: Benjamini-Hochberg q-values, medians and leave-one-out ranges for the cross-asset tests,
and Anthropic's trading-day calendar (T0 = 19 Nov 2026, NYSE holidays applied).
"""
import json
import pathlib

import numpy as np
import pandas as pd

h = pathlib.Path(__file__).parent
DATA = h.parent / "data"


def bh(p):
    p = np.asarray(p, float); n = len(p); o = np.argsort(p)
    q = np.empty(n); q[o] = np.minimum.accumulate((p[o] * n / np.arange(1, n + 1))[::-1])[::-1]
    return [float(min(1, x)) for x in q]


d = json.loads((DATA / "artifact_data.json").read_text())
d["intra"] = json.loads((DATA / "intraday.json").read_text())
d["stats"] = json.loads((DATA / "stats.json").read_text())
xa = json.loads((DATA / "xasset.json").read_text())

# robustness for cross-asset daily windows
keys = [(a, w) for a in xa["daily"] for w in xa["daily"][a]]
qs = bh([xa["daily"][a][w]["p_perm"] for a, w in keys])
for (a, w), q in zip(keys, qs):
    r = xa["daily"][a][w]
    v = np.array([x for x in r["values"] if x is not None], float)
    loo = [np.delete(v, i).mean() - r["null_mean"] for i in range(len(v))]
    r.update(q=q, loo_min=float(min(loo)), loo_max=float(max(loo)), median=float(np.median(v)), robust=bool(np.sign(min(loo)) == np.sign(max(loo))))
d["xa"] = xa

# Anthropic trading calendar
hol = pd.to_datetime(["2026-11-26", "2026-12-25", "2027-01-01", "2027-01-18", "2027-02-15", "2027-03-26", "2027-05-31", "2027-06-18"])
bd = pd.offsets.CustomBusinessDay(holidays=hol)
t0 = pd.Timestamp("2026-11-19")
cal = [dict(label=lab, day=k, date=(t0 + k * bd).strftime("%a %d %b %Y")) for lab, k in
       [("Pricing (after close)", -1), ("Day 1: first trade", 0), ("Day 5", 4), ("Day 21", 20), ("Day 63", 62), ("Day 126 (about 180 days, lock-up)", 125)]]
d["ant_cal"] = cal

data = json.dumps(d).replace("NaN", "null")
body = (h / "template.html").read_text().replace("__DATA__", data)
(h / "index.html").write_text(body)
(h / "preview.html").write_text('<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head><body>' + body + "</body></html>")
print(len(body) // 1024, "KB;", [(c["label"], c["date"]) for c in cal])
print("xasset robust & q<0.2:", [(a, w, round(xa["daily"][a][w]["q"], 3)) for a, w in keys if xa["daily"][a][w]["q"] < 0.3])
print("robust (LOO same sign) & p<0.1:", [(a, w, round(xa["daily"][a][w]["p_perm"], 3)) for a, w in keys if xa["daily"][a][w]["robust"] and xa["daily"][a][w]["p_perm"] < 0.1])
