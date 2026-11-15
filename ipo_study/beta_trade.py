"""Do IPO debuts move related listed stocks? Daily event study, co-movement betas and hourly tests. Output data/beta.json."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import stats

R = Path(__file__).parent / "data"
M = json.load(open(R / "raw/beta/map.json"))
C = pd.read_csv(R / "raw/beta/daily_close.csv", index_col=0, parse_dates=True)
O = pd.read_csv(R / "raw/beta/daily_open.csv", index_col=0, parse_dates=True)
H = pd.read_pickle(R / "raw/beta/hourly.pkl")
SG = pd.DataFrame(json.load(open(R / "signals.json"))["cohort"]).set_index("ticker")
RET = C.pct_change(fill_method=None)
rng = np.random.default_rng(7)


def boot(x, n=4000):
    x = np.asarray(x, float); x = x[~np.isnan(x)]
    if len(x) < 3: return [np.nan, np.nan]
    b = rng.choice(x, (n, len(x))).mean(1); return [float(np.percentile(b, 2.5)), float(np.percentile(b, 97.5))]


def summ(x):
    x = pd.Series(x, dtype=float).dropna()
    if len(x) < 3: return {"n": int(len(x))}
    return {"n": int(len(x)), "mean": float(x.mean()), "median": float(x.median()), "ci": boot(x), "t_p": float(stats.ttest_1samp(x, 0).pvalue),
            "w_p": float(stats.wilcoxon(x).pvalue), "pos": float((x > 0).mean())}


def mm_ar(tick, d0_idx, est=(-260, -21)):
    """Market-model (QQQ) abnormal returns for ticker, indexed by event day."""
    r = RET[tick]; q = RET["QQQ"]
    w = slice(max(d0_idx + est[0], 1), d0_idx + est[1])
    y, x = r.iloc[w], q.iloc[w]; ok = y.notna() & x.notna()
    if ok.sum() < 60: return None
    b = np.polyfit(x[ok], y[ok], 1)
    ar = r - (b[1] + b[0] * q)
    return ar, b[0]


# ---------------- A. daily event study on peers
rows, paths = [], {}
for ipo, (peers, holders) in M["peers"].items():
    d0 = pd.Timestamp(SG.loc[ipo, "ipo_date"]); i0 = C.index.searchsorted(d0)
    for kind, lst in [("peer", peers), ("holder", holders)]:
        for p in lst:
            if p not in C or C[p].iloc[:i0].dropna().size < 120: continue
            res = mm_ar(p, i0)
            if res is None: continue
            ar, b = res; ev = ar.iloc[i0 - 20: i0 + 64].values
            if len(ev) < 84: ev = np.r_[ev, [np.nan] * (84 - len(ev))]
            # day-0 split: prior close -> peer open, peer open -> close (abnormal vs QQQ same window)
            oc_p = C[p].iloc[i0] / O[p].iloc[i0] - 1; oc_q = C["QQQ"].iloc[i0] / O["QQQ"].iloc[i0] - 1
            rows.append({"ipo": ipo, "peer": p, "kind": kind, "beta": b, "run10": np.nansum(ev[10:20]), "run5": np.nansum(ev[15:20]), "d0": ev[20],
                         "d0_oc": oc_p - b * oc_q, "d1_5": np.nansum(ev[21:26]), "d1_21": np.nansum(ev[21:42]), "d1_63": np.nansum(ev[21:84]),
                         "d0_5": np.nansum(ev[20:26]), "pre20": np.nansum(ev[0:20])})
            paths[(ipo, p)] = ev
P = pd.DataFrame(rows)
B = P.groupby(["ipo", "kind"]).mean(numeric_only=True).reset_index()   # equal-weight basket per IPO
BP = B[B.kind == "peer"].set_index("ipo")
WIN = ["pre20", "run10", "run5", "d0", "d0_oc", "d0_5", "d1_5", "d1_21", "d1_63"]
event = {"peer": {w: summ(BP[w]) for w in WIN}, "holder": {w: summ(B[B.kind == "holder"].set_index("ipo")[w]) for w in WIN},
         "peer_level": {w: summ(P[P.kind == "peer"][w]) for w in WIN}, "n_ipos": int(BP.shape[0]), "n_peers": int((P.kind == "peer").sum())}
# path (mean CAR across IPO baskets) days -20..+63
pa = {}
for ipo in BP.index:
    ev = np.nanmean([paths[k] for k in paths if k[0] == ipo and P[(P.ipo == ipo) & (P.peer == k[1])].kind.iloc[0] == "peer"], axis=0); pa[ipo] = ev
PA = pd.DataFrame(pa).T
car = PA.fillna(0).cumsum(axis=1) - PA.fillna(0).iloc[:, :20].sum(axis=1).values[:, None]   # CAR rebased to day -1 close = 0
event["path"] = {"day": list(range(-20, 64)), "mean": car.mean().tolist(), "lo": [boot(car[c])[0] for c in car], "hi": [boot(car[c])[1] for c in car]}

# by demand group / pop size
BP = BP.join(SG[["sig_g", "open_pop", "pop", "oc1", "d1_5", "d1_21", "d1_63", "CROWD"]].rename(columns={"d1_5": "ipo_d1_5", "d1_21": "ipo_d1_21", "d1_63": "ipo_d1_63"}))
BP["hot"] = BP.sig_g.str.startswith("Hot")
groups = {}
for name, m in [("Hot", BP.hot), ("Not hot", ~BP.hot), ("Pop > 30%", BP["pop"] > 0.30), ("Pop <= 30%", BP["pop"] <= 0.30)]:
    groups[name] = {w: summ(BP.loc[m, w]) for w in ["run10", "d0", "d1_5", "d1_21", "d1_63"]}
for w in ["run10", "d0", "d1_5", "d1_21", "d1_63"]:
    groups.setdefault("MW_p", {})[w] = float(stats.mannwhitneyu(BP.loc[BP.hot, w].dropna(), BP.loc[~BP.hot, w].dropna()).pvalue)
# cross-section: peer reaction vs IPO outcome
xs = []
for a, b_ in [("d0", "open_pop"), ("d0", "pop"), ("d0", "oc1"), ("d1_5", "ipo_d1_5"), ("d1_21", "ipo_d1_21"), ("d1_63", "ipo_d1_63"), ("run10", "pop"), ("d1_63", "pop")]:
    s = BP[[a, b_]].dropna(); r, p = stats.spearmanr(s[a], s[b_]); xs.append({"peer": a, "ipo": b_, "rho": float(r), "p": float(p), "n": len(s)})

# ---------------- B. daily co-movement: IPO vs peer basket, early vs seasoned
co = []
for ipo in BP.index:
    peers = [p for p in M["peers"][ipo][0] if p in C]; d0 = pd.Timestamp(SG.loc[ipo, "ipo_date"]); i0 = C.index.searchsorted(d0)
    bask = RET[peers].mean(axis=1); q = RET["QQQ"]; y = RET[ipo]
    out = {"ipo": ipo}
    for lab, w in [("early", slice(i0 + 1, i0 + 22)), ("mid", slice(i0 + 22, i0 + 64)), ("seasoned", slice(i0 + 64, i0 + 190))]:
        df = pd.DataFrame({"y": y.iloc[w], "b": bask.iloc[w], "q": q.iloc[w]}).dropna()
        if len(df) < 15: continue
        # orthogonalise basket to QQQ, then y on QQQ + basket residual: beta to the theme beyond the market
        bres = df.b - np.polyval(np.polyfit(df.q, df.b, 1), df.q)
        f = sm.OLS(df.y, sm.add_constant(pd.DataFrame({"q": df.q, "theme": bres}))).fit()
        out[f"bq_{lab}"] = f.params["q"]; out[f"bt_{lab}"] = f.params["theme"]; out[f"r2_{lab}"] = f.rsquared
        out[f"corr_{lab}"] = df.y.corr(df.b); out[f"vol_{lab}"] = df.y.std() / df.b.std()
        out[f"bbq_{lab}"] = np.polyfit(df.q, df.b, 1)[0]
    co.append(out)
CO = pd.DataFrame(co).set_index("ipo")
comove = {c: summ(CO[c]) for c in CO.columns}
comove["paired_corr_early_vs_seasoned_p"] = float(stats.wilcoxon(*CO[["corr_early", "corr_seasoned"]].dropna().values.T).pvalue)
comove["paired_bt_early_vs_seasoned_p"] = float(stats.wilcoxon(*CO[["bt_early", "bt_seasoned"]].dropna().values.T).pvalue)

# lead-lag pooled panel days 1-21: does the IPO's excess return today predict the basket's tomorrow?
pan = []
for ipo in BP.index:
    peers = [p for p in M["peers"][ipo][0] if p in C]; i0 = C.index.searchsorted(pd.Timestamp(SG.loc[ipo, "ipo_date"]))
    q = RET["QQQ"]; bx = RET[peers].mean(axis=1) - q; yx = RET[ipo] - q
    w = slice(i0 + 1, i0 + 22)
    pan.append(pd.DataFrame({"ipo": ipo, "y": yx.iloc[w].values, "b": bx.iloc[w].values, "b_next": bx.shift(-1).iloc[w].values, "y_next": yx.shift(-1).iloc[w].values}))
PN = pd.concat(pan).dropna()
def clus(f, df):
    m = sm.OLS.from_formula(f, df).fit(cov_type="cluster", cov_kwds={"groups": pd.factorize(df.ipo)[0]}); return m
leadlag = {}
for nm, f in [("same_day", "b ~ y"), ("ipo_leads", "b_next ~ y"), ("peers_lead", "y_next ~ b")]:
    m = clus(f, PN); x = f.split("~")[1].strip()
    leadlag[nm] = {"coef": float(m.params[x]), "t": float(m.tvalues[x]), "p": float(m.pvalues[x]), "r2": float(m.rsquared), "n": int(m.nobs)}

# ---------------- C. hourly
HR = {}
def hret(t):
    s = H[t].dropna(); r = s.Close / s.Close.shift(1) - 1
    first = s.index.normalize() != pd.Series(s.index.normalize(), index=s.index).shift(1).values
    r[first] = s.Close[first] / s.Open[first] - 1        # no overnight gaps
    return r
cache = {}
def hr(t):
    if t not in cache: cache[t] = hret(t)
    return cache[t]
recent = [k for k in "VG SAIL CRWV HNGE CRCL CHYM FIG KLAR FIGR GEMI STUB NTSK MDLN SPCX".split()]
hrows, panel_h, day1 = [], [], []
for ipo in recent:
    peers = [p for p in M["peers"][ipo][0] + M["peers"][ipo][1] if p in H.columns.get_level_values(0) and H[p].dropna().size]
    y = hr(ipo); q = hr("QQQ"); days = sorted(set(y.index.date)); d1 = days[0]
    peers = [p for p in peers if (H[p].dropna().index.date < d1).sum() > 150 and (H[p].dropna().index.date == d1).any()]
    print(ipo, d1, peers)
    bask = pd.concat([hr(p) for p in peers], axis=1).mean(axis=1)
    df = pd.DataFrame({"y": y, "b": bask, "q": q}).dropna()
    df["day"] = [days.index(d) + 1 if d in days else np.nan for d in df.index.date]
    df["yx"] = df.y - df.q; df["bx"] = df.b - df.q
    for lab, lo, hi in [("d1_5", 1, 5), ("d6_21", 6, 21), ("d22_63", 22, 63)]:
        s = df[(df.day >= lo) & (df.day <= hi)]
        if len(s) < 10: continue
        hrows.append({"ipo": ipo, "win": lab, "corr": s.yx.corr(s.bx), "beta_b_on_y": np.polyfit(s.yx, s.bx, 1)[0], "beta_y_on_b": np.polyfit(s.bx, s.yx, 1)[0], "n": len(s)})
    s = df[(df.day >= 1) & (df.day <= 63)].copy(); s["ipo"] = ipo; s["early"] = (s.day <= 5).astype(int)
    s["bx_next"] = s.bx.shift(-1); s["yx_next"] = s.yx.shift(-1); panel_h.append(s)
    # day 1 clock: peer basket abnormal move from prior close to IPO first print, and first print -> close, vs 20 placebo days same clock
    t0 = y[y.index.date == d1].index[0]; pq = []
    for p in peers + ["QQQ"]:
        s_ = H[p].dropna(); prev = s_[s_.index.date < d1].Close.iloc[-1]; dd = s_[s_.index.date == d1]
        at = dd[dd.index < t0].Close.iloc[-1] if (dd.index < t0).any() else dd.Open.iloc[0]
        pq.append((p, at / prev - 1, dd.Close.iloc[-1] / at - 1))
    pqd = pd.DataFrame(pq, columns=["t", "pre", "post"]).set_index("t")
    bpre = pqd.drop("QQQ").pre.mean() - pqd.loc["QQQ", "pre"]; bpost = pqd.drop("QQQ").post.mean() - pqd.loc["QQQ", "post"]
    # placebo: same clock on the 20 sessions before
    pl = []
    qd = H["QQQ"].dropna(); alld = sorted(set(qd.index.date)); k = alld.index(d1)
    for dd_ in alld[k - 20:k]:
        vals = []
        for p in peers + ["QQQ"]:
            s_ = H[p].dropna(); dd = s_[s_.index.date == dd_]; prev = s_[s_.index.date < dd_]
            if dd.empty or prev.empty: vals.append((np.nan, np.nan)); continue
            cut = dd[dd.index.time < t0.time()]
            at = cut.Close.iloc[-1] if len(cut) else dd.Open.iloc[0]
            vals.append((at / prev.Close.iloc[-1] - 1, dd.Close.iloc[-1] / at - 1))
        v = np.array(vals); pl.append((np.nanmean(v[:-1, 0]) - v[-1, 0], np.nanmean(v[:-1, 1]) - v[-1, 1]))
    pl = np.array(pl)
    day1.append({"ipo": ipo, "first_print": t0.strftime("%H:%M"), "peers": peers, "pre": bpre, "post": bpost, "pre_z": (bpre - pl[:, 0].mean()) / pl[:, 0].std(),
                 "post_z": (bpost - pl[:, 1].mean()) / pl[:, 1].std(), "ipo_oc": float(y[y.index.date == d1].add(1).prod() - 1),
                 "pop": float(SG.loc[ipo, "pop"]), "open_pop": float(SG.loc[ipo, "open_pop"])})
HRW = pd.DataFrame(hrows); D1 = pd.DataFrame(day1); PH = pd.concat(panel_h).dropna(subset=["yx", "bx"])
hourly = {"by_window": {w: {c: summ(HRW[HRW.win == w][c]) for c in ["corr", "beta_b_on_y", "beta_y_on_b"]} for w in ["d1_5", "d6_21", "d22_63"]},
          "per_ipo": HRW.round(4).to_dict("records"), "day1": D1.round(4).to_dict("records"),
          "day1_summary": {c: summ(D1[c]) for c in ["pre", "post", "pre_z", "post_z"]},
          "day1_rho_post_vs_ipo_oc": [float(v) for v in stats.spearmanr(D1.post, D1.ipo_oc)], "day1_rho_pre_vs_open_pop": [float(v) for v in stats.spearmanr(D1.pre, D1.open_pop)]}
# pooled hourly: same-hour beta of peers on IPO, early (days 1-5) vs later, and lead-lag
m = sm.OLS.from_formula("bx ~ yx*early", PH).fit(cov_type="cluster", cov_kwds={"groups": pd.factorize(PH.ipo)[0]})
hourly["pooled"] = {k: {"coef": float(m.params[k]), "t": float(m.tvalues[k]), "p": float(m.pvalues[k])} for k in ["yx", "yx:early", "early"]}
hourly["pooled"]["n"] = int(m.nobs)
PL = PH.dropna(subset=["bx_next", "yx_next"])
for nm, f in [("ipo_leads_1h", "bx_next ~ yx"), ("peers_lead_1h", "yx_next ~ bx")]:
    for lab, sub in [("early", PL[PL.early == 1]), ("later", PL[PL.early == 0])]:
        mm = sm.OLS.from_formula(f, sub).fit(cov_type="cluster", cov_kwds={"groups": pd.factorize(sub.ipo)[0]}); x = f.split("~")[1].strip()
        hourly.setdefault("leadlag", {})[f"{nm}_{lab}"] = {"coef": float(mm.params[x]), "t": float(mm.tvalues[x]), "p": float(mm.pvalues[x]), "n": int(mm.nobs)}

# ---------------- D. Anthropic run-up: related stocks since 30 Sep 2026 and since roadshow launch
A = M["anthropic"]; anth = {}
i_s = C.index.searchsorted(pd.Timestamp("2026-09-30")); i_s1 = C.index.searchsorted(pd.Timestamp("2026-10-26")); i_rs = C.index.searchsorted(pd.Timestamp("2026-11-09"))
for t in A["peers"] + A["holders"] + ["QQQ", "SMH", "IGV", "ARKK"]:
    res = mm_ar(t, i_s) if t != "QQQ" else None
    beta = res[1] if res else 1.0
    ar = RET[t] - beta * RET["QQQ"]
    anth[t] = {"beta": float(beta), "raw_since_sep30": float(C[t].iloc[-1] / C[t].iloc[i_s] - 1), "raw_since_s1": float(C[t].iloc[-1] / C[t].iloc[i_s1 - 1] - 1),
               "raw_roadshow": float(C[t].iloc[-1] / C[t].iloc[i_rs] - 1), "car_since_sep30": float(ar.iloc[i_s + 1:].sum()),
               "car_roadshow": float(ar.iloc[i_rs + 1:].sum()), "car20": float(ar.iloc[-20:].sum()), "kind": "holder" if t in A["holders"] else ("peer" if t in A["peers"] else "index")}
# Cohort benchmark for "roadshow" window: peer CAR over the 5 days before listing = run5; and 20 days = pre20
# implied mapping: hourly peer beta on the IPO (days 1-5) x Anthropic expected move
spx = {}
for t in ["GOOGL", "DXYZ", "RKLB", "ASTS"]:
    i0 = C.index.searchsorted(pd.Timestamp("2026-06-12")); res = mm_ar(t, i0)
    if res is None: continue
    ar = res[0]; spx[t] = {"run20": float(ar.iloc[i0 - 20:i0].sum()), "run5": float(ar.iloc[i0 - 5:i0].sum()), "d0": float(ar.iloc[i0]), "d1_5": float(ar.iloc[i0 + 1:i0 + 6].sum()),
                           "d1_21": float(ar.iloc[i0 + 1:i0 + 22].sum()), "path": (ar.iloc[i0 - 20:i0 + 22].cumsum() - ar.iloc[i0 - 20:i0].sum()).tolist()}
crwv = {}
for t in ["NBIS", "ORCL", "SMCI", "NVDA"]:
    i0 = C.index.searchsorted(pd.Timestamp("2025-03-28")); res = mm_ar(t, i0)
    if res is None: continue
    ar = res[0]; crwv[t] = {"run20": float(ar.iloc[i0 - 20:i0].sum()), "d0": float(ar.iloc[i0]), "d1_5": float(ar.iloc[i0 + 1:i0 + 6].sum()), "d1_21": float(ar.iloc[i0 + 1:i0 + 22].sum())}

# ---------------- E. robustness: placebo dates, ex-2021, ex-overlap
qq = RET["QQQ"]; FULL = {}
for t in set(P.peer):
    ok = RET[t].notna() & qq.notna(); bb = np.polyfit(qq[ok], RET[t][ok], 1); FULL[t] = RET[t] - (bb[1] + bb[0] * qq)
def basket_car(ipo, i0, lo, hi):
    ps = [p for p in M["peers"][ipo][0] if p in FULL]
    v = [FULL[p].iloc[i0 + lo:i0 + hi].sum(min_count=1) for p in ps if FULL[p].iloc[:i0].notna().sum() > 120]
    return np.nanmean(v) if v else np.nan
I0 = {ipo: C.index.searchsorted(pd.Timestamp(SG.loc[ipo, "ipo_date"])) for ipo in BP.index}
act = {w: np.nanmean([basket_car(i, I0[i], lo, hi) for i in I0]) for w, (lo, hi) in {"d0": (0, 1), "d1_21": (1, 22), "d1_63": (1, 64), "run10": (-10, 0)}.items()}
pl = {w: [] for w in act}
for k in range(400):
    sh = {i: I0[i] + int(rng.integers(-250, 250)) for i in I0}
    sh = {i: v for i, v in sh.items() if 260 < v < len(C) - 70}
    for w, (lo, hi) in {"d0": (0, 1), "d1_21": (1, 22), "d1_63": (1, 64), "run10": (-10, 0)}.items():
        pl[w].append(np.nanmean([basket_car(i, v, lo, hi) for i, v in sh.items()]))
placebo = {w: {"actual": float(act[w]), "placebo_mean": float(np.mean(pl[w])), "pct": float((np.array(pl[w]) <= act[w]).mean())} for w in act}
yr = pd.to_datetime(SG.loc[BP.index, "ipo_date"]).dt.year
robust = {"ex2021": {w: summ(BP.loc[yr[BP.index] != 2021, w]) for w in ["d0", "d1_21", "d1_63"]},
          "only2021": {w: summ(BP.loc[yr[BP.index] == 2021, w]) for w in ["d0", "d1_21", "d1_63"]},
          "since2023": {w: summ(BP.loc[yr[BP.index] >= 2023, w]) for w in ["d0", "d1_21", "d1_63"]}, "placebo": placebo}
# peer-level percentile of Anthropic's AI-basket run-up vs cohort pre20 distribution
pre20 = P[P.kind == "peer"].pre20.dropna()
ant_rank = {t: float((pre20 <= anth[t]["car20"]).mean()) for t in A["peers"] + A["holders"]}
# hourly paths for case studies: IPO and proxies on days 1-3, rebased to prior close (proxies) / IPO first print
cases = {}
for ipo, prox in [("SPCX", ["RKLB", "ASTS", "DXYZ", "GOOGL"]), ("CRCL", ["COIN", "HOOD"]), ("CRWV", ["NBIS", "NVDA", "ORCL"]), ("FIG", ["ADBE", "WIX"])]:
    d1 = sorted(set(H[ipo].dropna().index.date))[0]; qd = sorted(set(H["QQQ"].dropna().index.date)); k = qd.index(d1)
    win = qd[k - 1:k + 3]; cs = {}
    for t in [ipo, "QQQ"] + prox:
        s_ = H[t].dropna(); s_ = s_[(s_.index.date >= win[1]) & (s_.index.date <= win[-1])]
        base = s_.Open.iloc[0] if t == ipo else H[t].dropna()[H[t].dropna().index.date == win[0]].Close.iloc[-1]
        cs[t] = {"x": [str(i) for i in s_.index], "y": (s_.Close / base - 1).round(4).tolist()}
    cases[ipo] = cs
# Anthropic roadshow week hourly
aw = {}
for t in ["NBIS", "CRWV", "NVDA", "AMZN", "GOOGL", "QQQ"]:
    s_ = H[t].dropna(); s_ = s_[s_.index >= "2026-11-09"]; base = H[t].dropna()[H[t].dropna().index.date < pd.Timestamp("2026-11-09").date()].Close.iloc[-1]
    aw[t] = {"x": [str(i) for i in s_.index], "y": (s_.Close / base - 1).round(4).tolist()}

out = {"robust": robust, "ant_rank": ant_rank, "cases": cases, "ant_week": aw, "event": event, "groups": groups, "xs": xs, "comove": comove, "comove_table": CO.round(4).reset_index().to_dict("records"), "leadlag_daily": leadlag,
       "hourly": hourly, "anthropic": anth, "spacex": spx, "coreweave": crwv, "peer_rows": P.round(5).to_dict("records"), "basket": BP.reset_index().round(5).to_dict("records")}
json.dump(out, open(R / "beta.json", "w"), default=lambda o: None if (isinstance(o, float) and np.isnan(o)) else (o.item() if hasattr(o, "item") else str(o)), indent=1)

def pr(d, k): return f"{k}: n={d.get('n')} mean={d.get('mean', np.nan)*100:+.2f}% med={d.get('median', np.nan)*100:+.2f}% ci=({d.get('ci',[np.nan]*2)[0]*100:+.2f},{d.get('ci',[np.nan]*2)[1]*100:+.2f}) p={d.get('t_p', np.nan):.3f} pos={d.get('pos', np.nan):.2f}"
print("== peer basket CAR (n IPOs)", event["n_ipos"]);  [print(" ", pr(event["peer"][w], w)) for w in WIN]
print("== holders");  [print(" ", pr(event["holder"][w], w)) for w in WIN]
print("== groups"); [print(" ", g, {w: round(v.get("mean", np.nan) * 100, 2) for w, v in d.items()} if g != "MW_p" else d) for g, d in groups.items()]
print("== xs"); [print(" ", x) for x in xs]
print("== comove"); [print(" ", k, round(v.get("median", np.nan), 3) if isinstance(v, dict) else v) for k, v in comove.items()]
print("== leadlag daily", leadlag)
print("== hourly windows"); [print(" ", w, {c: round(v.get("median", np.nan), 3) for c, v in d.items()}) for w, d in hourly["by_window"].items()]
print("== hourly pooled", hourly["pooled"]); print("== hourly leadlag", hourly["leadlag"])
print("== day1"); print(D1.drop(columns="peers").round(3).to_string()); print({k: (round(v.get('mean', np.nan), 4), round(v.get('t_p', np.nan), 3)) for k, v in hourly["day1_summary"].items()}, hourly["day1_rho_post_vs_ipo_oc"], hourly["day1_rho_pre_vs_open_pop"])
print("== anthropic"); print(pd.DataFrame(anth).T.round(3).to_string())
print("== robust", json.dumps({k: ({w: (round(v.get('mean',np.nan)*100,2), round(v.get('t_p',np.nan),3), v['n']) for w, v in d.items()} if k != "placebo" else d) for k, d in robust.items()}, default=str))
print("== ant_rank", {k: round(v, 3) for k, v in ant_rank.items()})
print("== spacex", {k: {a: round(b, 3) for a, b in v.items() if a != "path"} for k, v in spx.items()})
print("== coreweave", {k: {a: round(b, 3) for a, b in v.items()} for k, v in crwv.items()})
