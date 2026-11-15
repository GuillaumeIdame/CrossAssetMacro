"""Tables and figures for paper v2: "Positioning, not plumbing".

Usage: python3 ipo_study/paper_v2/make_paper2.py   (after positioning.py and positioning_ipo.py)
Writes ipo_study/paper_v2/figures/*.pdf and ipo_study/paper_v2/tables/*.tex
"""
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats

HERE = Path(__file__).parent
DATA = HERE.parent / "data"
FIG, TAB = HERE / "figures", HERE / "tables"
FIG.mkdir(exist_ok=True); TAB.mkdir(exist_ok=True)
P = json.loads((DATA / "positioning.json").read_text())
PI = json.loads((DATA / "positioning_ipo.json").read_text())
ST = json.loads((DATA / "stats.json").read_text())
XA = json.loads((DATA / "xasset.json").read_text())
CO = pd.read_csv(DATA / "enriched_cohort.csv").merge(pd.read_csv(DATA / "deal_terms.csv")[["ticker", "revision_pct", "demand"]], on="ticker")
RNG = np.random.default_rng(3)

B1, O2, A3, Y4, RED, INK, MUT, GRID = "#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e34948", "#0b0b0b", "#898781", "#e1e0d9"
plt.rcParams.update({"font.family": "serif", "font.serif": ["DejaVu Serif"], "font.size": 8.5, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.edgecolor": "#c3c2b7", "axes.linewidth": 0.8, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6,
                     "xtick.color": "#52514e", "ytick.color": "#52514e", "axes.labelcolor": "#52514e", "legend.frameon": False,
                     "lines.linewidth": 1.6, "savefig.bbox": "tight", "pdf.fonttype": 42})


def f(v, d=1, sign=True, pctf=True):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "--"
    x = v * 100 if pctf else v
    s = f"{abs(x):.{d}f}"
    if float(s) == 0:
        return s
    return ("$-$" if x < 0 else ("+" if sign else "")) + s


def num(v, d=2):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "--"
    s = f"{abs(v):.{d}f}"
    return ("$-$" if v < 0 and float(s) != 0 else "") + s


def fp(p):
    if p is None or (isinstance(p, float) and np.isnan(p)):
        return "--"
    return "$<$0.001" if p < 0.001 else (f"{p:.3f}" if p < 0.1 else f"{p:.2f}")


def stars(p):
    return "" if p is None else ("$^{***}$" if p < 0.01 else "$^{**}$" if p < 0.05 else "$^{*}$" if p < 0.10 else "")


def esc(s):
    return str(s).replace("&", r"\&").replace("%", r"\%").replace("$", r"\$").replace("_", r"\_").replace(">=", r"$\geq$").replace("<", r"$<$").replace(">", r"$>$")


def bh(p):
    p = np.asarray(p, float); n = len(p); o = np.argsort(p)
    q = np.empty(n); q[o] = np.minimum.accumulate((p[o] * n / np.arange(1, n + 1))[::-1])[::-1]
    return np.minimum(q, 1)


def table(name, caption, label, colspec, header, rows, notes, size=r"\small", wide=False, fit=False):
    env = "table*" if wide else "table"
    body = [rf"\begin{{{env}}}[!htbp]\centering{size}", rf"\caption{{{caption}}}\label{{{label}}}", r"\resizebox{\linewidth}{!}{" if fit else "",
            r"\begin{threeparttable}", rf"\begin{{tabular}}{{{colspec}}}", r"\toprule", header + r" \\", r"\midrule"] + rows + \
           [r"\bottomrule", r"\end{tabular}", r"\begin{tablenotes}[flushleft]\footnotesize", rf"\item \textit{{Notes:}} {notes}", r"\end{tablenotes}",
            r"\end{threeparttable}", "}" if fit else "", rf"\end{{{env}}}"]
    (TAB / f"{name}.tex").write_text("\n".join(body) + "\n")


VARS = [("rv21", "S\\&P 500 realised vol, 21d", "low", False), ("mom63", "S\\&P 500 return, 63d", "high", True),
        ("vix_term", "VIX / VIX3M", "low", False), ("beta63", "High beta vs low vol (SPHB/SPLV), 63d", "high", True),
        ("mtum63", "Momentum vs market (MTUM/SPY), 63d", "high", True), ("btc_mom63", "Bitcoin return, 63d", "high", True),
        ("lev_net", "CFTC leveraged funds net / OI, E-mini", "high", False), ("am_net", "CFTC asset managers net / OI, E-mini", "high", False),
        ("margin_yoy", "Margin debt growth, YoY (Fed Z.1)", "high", True), ("PSI", "Positioning stretch index (PSI)", "high", False)]
VLAB = {v[0]: v[1] for v in VARS}
TS = pd.DataFrame({k: v for k, v in P["ts"].items() if k != "dates"}, index=pd.to_datetime(P["ts"]["dates"]))
if "mtum63" not in TS:  # weekly MTUM-vs-SPY 63d relative return (same definition as positioning.py)
    import yfinance as yf
    _m = yf.download(["MTUM", "SPY"], start="2019-06-01", progress=False, auto_adjust=True)["Close"]
    _r = _m["MTUM"] / _m["SPY"]; _r = _r / _r.shift(63) - 1
    TS["mtum63"] = _r.reindex(TS.index, method="ffill")

# ======================================================== T1: variables
rows = []
for k, lab, stretched, ispct in VARS:
    s = TS[k].loc["2020-06-01":].dropna()
    a = P["anthropic"]["Latest (13 Nov 2026)"]
    sx = next(e for e in P["states"] if e["name"] == "SpaceX")
    fm = (lambda v: f(v, 1)) if ispct else (lambda v: num(v, 2) if k != "rv21" else f(v, 1, sign=False))
    if k == "rv21":
        fm = lambda v: f(v, 1, sign=False)
    rows.append(rf"{lab} & {stretched} & {fm(s.mean())} & {fm(s.std()) if k!='PSI' else num(s.std(),2)} & {fm(sx[k])} ({sx[k+'_pct']*100:.0f}) & {fm(a[k])} ({a[k+'_pct']*100:.0f}) \\".replace("$-$", "$-$"))
table("t1_vars", "State variables: definitions, sample moments and current readings", "tab:vars", "lcrrrr",
      r"Variable & Stretched when & Mean & SD & SpaceX (pct) & 13 Nov 2026 (pct)", rows,
      "Sample June 2020 to November 2026. Returns and volatilities in percent; ratios as levels. Percentile rank against all days in the sample in brackets. "
      "SpaceX readings are taken 11 sessions before its listing. PSI is the equal-weighted mean of the z-scores of $-$RV21, momentum 63d, $-$VIX/VIX3M, high beta vs low vol, and Bitcoin momentum.",
      size=r"\footnotesize", fit=True)

# ======================================================== T2: event states
rows = []
for e in P["states"]:
    def pc(c):
        return "--" if e[c + "_pct"] is None else f"{e[c+'_pct']*100:.0f}"
    rows.append(rf"{e['date']} & {esc(e['name'])} & {e['proceeds_b']:g} & {pc('rv21')} & {pc('mom63')} & {pc('vix_term')} & {pc('beta63')} & {pc('mtum63')} & {pc('btc_mom63')} & {pc('lev_net')} & {pc('margin_yoy')} & {num(e['PSI'],2)} & {pc('PSI')} \\")
rows.append(r"\midrule")
for lab, a in P["anthropic"].items():
    def pa(c):
        return "--" if a[c + "_pct"] is None else f"{a[c+'_pct']*100:.0f}"
    rows.append(rf"-- & {esc(lab)} & -- & {pa('rv21')} & {pa('mom63')} & {pa('vix_term')} & {pa('beta63')} & {pa('mtum63')} & {pa('btc_mom63')} & {pa('lev_net')} & {pa('margin_yoy')} & {num(a['PSI'],2)} & {pa('PSI')} \\")
table("t2_states", "Market state before each large listing (percentile ranks)", "tab:states", "llrrrrrrrrrrr",
      r"Listed & Company & \$bn & RV21 & Mom63 & VIX/3M & $\beta$ spread & MTUM & BTC & Lev.\ funds & Margin & PSI & PSI pct", rows,
      "Percentile ranks (0--100) of each state variable against all days June 2020 to November 2026, measured at T$-$11 (the close before the pre-listing window). "
      "Low RV21 and low VIX/VIX3M are the stretched readings for those columns. Anthropic's T$-$11 is 3 November 2026; its S-1 became public on 26 October.", size=r"\scriptsize", wide=True, fit=True)

# ======================================================== T3: matched placebo split
A_LIST = ["S&P 500", "Nasdaq 100", "Small caps", "Spec. growth (ARKK)", "Bitcoin", "Gold", "High beta - low vol", "Momentum - market", "Cross-asset momentum L/S"]
rows = []
for a in A_LIST:
    r = P["responses"][a]
    cells = []
    for w in ["pre", "post"]:
        x = r[w]
        cells += [f"{f(x['hi'],2)}{stars(x['p_hi'])}", f(x["null_hi"], 2), f"{f(x['lo'],2)}{stars(x['p_lo'])}", f(x["null_lo"], 2)]
    rows.append(esc(a) + " & " + " & ".join(cells) + r" \\")
table("t3_split", "Event windows split by positioning, against a state-matched placebo", "tab:split", "lrrrrrrrr",
      r"& \multicolumn{4}{c}{T$-$10 to T$-$1} & \multicolumn{4}{c}{Listing day to T+5} \\ \cmidrule(lr){2-5}\cmidrule(lr){6-9}"
      r" Asset & Stretched & Placebo & Not str. & Placebo & Stretched & Placebo & Not str. & Placebo", rows,
      f"Average log return in percent. Stretched = PSI at T$-$11 above its sample median ({P['n_hi']} of {len(P['events'])} events). Placebo = average over all days in the same PSI half. "
      "Stars: permutation $p$ of the event average against 5,000 draws from the matched placebo days ($^{*}p<0.10$, $^{**}p<0.05$).", size=r"\footnotesize", fit=True)

# ======================================================== T4: HAC regressions
regs = list(P["reg"].values())
q = bh([r["p_inter"] for r in regs])
rows = []
for r, qq in zip(regs, q):
    se = r["d_inter"] / r["t_inter"] if r["t_inter"] else np.nan
    rows.append(rf"{esc(r['asset'])} & {r['window']} & {num(r['b_psi']*100,2)} ({num(r['t_psi'],1)}) & {num(r['c_event']*100,2)} ({num(r['t_event'],1)}) & {num(r['d_inter']*100,2)} ({num(r['t_inter'],1)}) & {fp(r['p_inter'])} & {qq:.2f} \\")
    r["q"] = float(qq); r["se"] = float(se)
table("t4_reg", "Panel regressions: does a large listing in a stretched market move assets more than a stretched day?", "tab:reg", "llrrrrr",
      r"Asset & Window & PSI ($t$) & Event ($t$) & Event$\times$PSI ($t$) & $p$ & $q$", rows,
      "Each row regresses the window return starting at every day $s$ (June 2020 to October 2026) on PSI$_s$, an event dummy (1 if $s$ is a listing's T$-$11) and their interaction. "
      "Coefficients in percent per unit of PSI (one PSI unit is about 1.5 standard deviations of the index); Newey--West $t$-statistics with lags equal to the window length. $q$: Benjamini--Hochberg across the 27 interaction tests.",
      size=r"\scriptsize", fit=True)

# ======================================================== T5: per-variable correlations with event moves
vc = pd.DataFrame(P["var_corr"]); vc["q"] = bh(vc.p.values)
top = vc.sort_values("p").head(14)
rows = [rf"{VLAB[r.var]} & {esc(r.asset)} & {'pre' if r.window=='pre' else 'post'} & {num(r.rho,2)} & {fp(r.p)} & {r.q:.2f} \\" for r in top.itertuples()]
table("t5_varcorr", "Which state variables line up with the event-window moves?", "tab:varcorr", "lllrrr", r"State at T$-$11 & Asset & Window & $\rho$ & $p$ & $q$", rows,
      f"Spearman correlation across the {len(P['events'])} large listings between the state variable and the event-window return. The 14 smallest $p$-values of {len(vc)} tests are shown; $q$ adjusts across all {len(vc)}.",
      size=r"\footnotesize")

# ======================================================== T6-T9: IPO stock vs positioning
T = PI["terciles"]
rows = [rf"{k} & {v['n']} & {num(v['psi'],2)} & {f(v['pop'],0)} & {f(v['r21'],0)} & {f(v['r63'],0)} & {f(v['x63'],0)} \\" for k, v in T.items()]
table("t6_terciles", "IPO outcomes by positioning at listing (PSI terciles)", "tab:terciles", "lrrrrrr",
      r"PSI tercile & $n$ & Median PSI & Pop & Day 21 & Day 63 & Day 63 vs QQQ", rows,
      "Medians in percent. PSI is the last weekly reading before listing. Returns after day 1 are measured from the first close.")
fam = PI["family"]
rows = [rf"{VLAB[r['var']]} & {dict(pop='Pop', r63='Day 63', x63='Day 63 vs QQQ')[r['outcome']]} & {num(r['rho'],2)} & {fp(r['p'])} & {r['q']:.3f} \\" for r in sorted(fam, key=lambda x: x["p"])[:14]]
table("t7_ipocorr", "Positioning at listing and IPO outcomes: rank correlations", "tab:ipocorr", "llrrr", r"State variable & Outcome & $\rho$ & $p$ & $q$", rows,
      f"43 IPOs. The 14 smallest $p$-values of {len(fam)} tests (8 state variables $\\times$ 3 outcomes); $q$ adjusts across all {len(fam)}.", size=r"\footnotesize")
R = PI["regs"]
def rr(key, var):
    r = R[key]
    return f"{num(r['coef'][var],2)} ({num(r['t'][var],1)})" if var in r["coef"] else "--"
rows = []
for y, lab in [("pop", "First-day return"), ("r63", "Day 63 return"), ("x63", "Day 63 vs QQQ")]:
    k1, k2 = f"{y} ~ PSI", f"{y} ~ PSI + rev + logcap"
    rows.append(rf"{lab} & (1) & {rr(k1,'PSI')} & -- & -- & {R[k1]['r2']:.2f} & {R[k1]['n']} \\")
    rows.append(rf" & (2) & {rr(k2,'PSI')} & {rr(k2,'rev')} & {rr(k2,'logcap')} & {R[k2]['r2']:.2f} & {R[k2]['n']} \\")
table("t8_ipo_reg", "Cross-sectional regressions: positioning versus demand", "tab:iporeg", "llrrrrr", r"Dependent variable & Spec. & PSI & Price revision & log market value & $R^2$ & $n$", rows,
      "OLS with HC3 robust $t$-statistics in brackets. Returns as decimals. Price revision = offer vs midpoint of the first filed range. Demand drives the pop; positioning drives the fade.", size=r"\footnotesize")
base, ex = PI["base"], PI["ex2021"]
lo_ = min(PI["loyo"].values()); hi_ = max(PI["loyo"].values())
rows = [rf"Full sample, day 63 & {base['r63']['n']} & {num(base['r63']['rho'],2)} & {fp(base['r63']['p'])} \\",
        rf"Full sample, day 63 vs QQQ & {base['x63']['n']} & {num(base['x63']['rho'],2)} & {fp(base['x63']['p'])} \\",
        rf"Excluding 2021 listings, day 63 & {ex['r63']['n']} & {num(ex['r63']['rho'],2)} & {fp(ex['r63']['p'])} \\",
        rf"Excluding 2021 listings, day 63 vs QQQ & {ex['x63']['n']} & {num(ex['x63']['rho'],2)} & {fp(ex['x63']['p'])} \\",
        rf"Leave one listing year out, day 63 (range) & -- & {num(hi_,2)} to {num(lo_,2)} & -- \\",
        rf"Year-block bootstrap 95\% CI, day 63 & -- & [{num(PI['block_ci_r63'][0],2)}, {num(PI['block_ci_r63'][1],2)}] & -- \\",
        rf"Full sample, first-day return & {base['pop']['n']} & {num(base['pop']['rho'],2)} & {fp(base['pop']['p'])} \\",
        rf"PSI vs price revision & {PI['corr_psi_rev']['n']} & {num(PI['corr_psi_rev']['rho'],2)} & {fp(PI['corr_psi_rev']['p'])} \\"]
table("t9_robust", "Robustness of the PSI--fade relationship", "tab:robust", "lrrr", r"Test & $n$ & $\rho$ & $p$", rows,
      "Spearman correlations between PSI at listing and the outcome. The year-block bootstrap resamples listing years with replacement (5,000 draws), allowing for clustering of IPOs in hot windows.", size=r"\footnotesize")

# ======================================================== T10: conditional strategies + T11: 2x2
names_t = {k: set(v["names"]) for k, v in T.items()}
CO["d5_63"] = (1 + CO.r63) / (1 + CO.r5) - 1
def strat(x, hold):
    x = pd.Series(x).dropna().values
    bs = RNG.choice(x, (10000, len(x))).mean(axis=1)
    sr = x.mean() / x.std(ddof=1)
    return dict(n=len(x), mean=x.mean(), lo=np.percentile(bs, 2.5), hi=np.percentile(bs, 97.5), hit=(x > 0).mean(),
                pw=stats.wilcoxon(x).pvalue, sr=sr, sra=sr * np.sqrt(252 / hold), srr=sr * np.sqrt(len(x) / 5.75 / 1.0))
rows = []
for lab, mask, sign, hold, col in [("Short day 5 to 63, all IPOs", CO.ticker.notna(), -1, 58, "d5_63"),
                                    ("Short day 5 to 63, high-PSI tercile", CO.ticker.isin(names_t["High PSI"]), -1, 58, "d5_63"),
                                    ("Short day 5 to 63, low-PSI tercile", CO.ticker.isin(names_t["Low PSI"]), -1, 58, "d5_63"),
                                    ("Long day 1 to 63, low-PSI tercile", CO.ticker.isin(names_t["Low PSI"]), 1, 62, "r63"),
                                    ("Short day 5 to 63, high PSI and above range", CO.ticker.isin(names_t["High PSI"]) & (CO.demand == "Above range"), -1, 58, "d5_63")]:
    s = strat(sign * CO.loc[mask, col], hold)
    rows.append(rf"{lab} & {s['n']} & {f(s['mean'])} & [{f(s['lo'],0)}, {f(s['hi'],0)}] & {s['hit']*100:.0f} & {fp(s['pw'])} & {num(s['sr'],2)} & {num(s['srr'],2)} \\")
table("t10_strat", "Positioning-conditioned strategies on the IPO stock", "tab:strat", "lrrcrrrr", r"Strategy & $n$ & Mean & 95\% CI & Hit & $p_W$ & SR$_\text{trade}$ & SR$_\text{real}$", rows,
      "Percent per trade; shorts report the short-seller's return. SR$_\\text{real}$ scales the per-trade Sharpe by the square root of the number of qualifying IPOs per year in the cohort (5.75 years). "
      "The tercile split uses the full-sample PSI distribution, so these are in-sample results; costs and borrow are ignored.", size=r"\footnotesize", fit=True)
CO["psi"] = CO.ticker.map({t: k for k, v in names_t.items() for t in v})
CO["psi_hi"] = np.where(CO.psi == "High PSI", "High PSI", np.where(CO.psi.notna(), "Low or mid PSI", None))
CO["dem"] = np.where(CO.demand == "Above range", "Above range", np.where(CO.demand.notna(), "At or below", None))
rows = []
for a in ["High PSI", "Low or mid PSI"]:
    cells = []
    for b in ["Above range", "At or below"]:
        g = CO[(CO.psi_hi == a) & (CO.dem == b)]
        cells.append(f"{len(g)} & {f(g.d1_pop.median(),0)} & {f(g.r63.median(),0)}" if len(g) else "0 & -- & --")
    rows.append(f"{a} & " + " & ".join(cells) + r" \\")
table("t11_2x2", "Positioning and demand together", "tab:2x2", "lrrrrrr",
      r"& \multicolumn{3}{c}{Priced above first range} & \multicolumn{3}{c}{At or below range} \\ \cmidrule(lr){2-4}\cmidrule(lr){5-7} PSI at listing & $n$ & Pop & Day 63 & $n$ & Pop & Day 63", rows,
      "Medians in percent. Day 63 measured from the first close.", size=r"\footnotesize")

# ======================================================== T12: baseline recap
b = {r["d"]: r for r in ST["band"]}
hot = next(r for r in ST["groups"]["Pricing vs range"]["rows"] if r["key"].startswith("Priced above"))
rows = [rf"Median first-day return (43 IPOs) & {f(CO.d1_pop.median())} & -- \\",
        rf"Median, day-1 close to day 63 & {f(b[63]['med'])} & [{f(b[63]['lo'],0)}, {f(b[63]['hi'],0)}] \\",
        rf"Median vs QQQ, day-1 close to day 126 & {f(b[126]['xmed'])} & [{f(b[126]['xlo'],0)}, {f(b[126]['xhi'],0)}] \\",
        rf"Above-range deals, median day 63 & {f(hot['r63'])} & [{f(hot['r63_ci'][0],0)}, {f(hot['r63_ci'][1],0)}] \\",
        rf"Bitcoin, T$-$10 to T$-$1, 11 large listings & {f(XA['daily']['Bitcoin']['pre']['mean'])} & $p={XA['daily']['Bitcoin']['pre']['p_perm']:.2f}$ \\",
        rf"S\&P 500, T+1 to T+5, 11 large listings & {f(XA['daily']['S&P 500 (SPY)']['post']['mean'])} & $p={XA['daily']['S&P 500 (SPY)']['post']['p_perm']:.2f}$ \\"]
table("t12_recap", "Unconditional results from the companion note", "tab:recap", "lrc", r"Statistic & Estimate (\%) & 95\% CI or $p$", rows,
      "From \\citet{frenzyfade2026}. Brackets: bootstrap 95\\% CI of the median. Cross-asset $p$-values from permutation tests against random dates; none survives a correction for 56 tests.", size=r"\footnotesize")

# ======================================================== T13: SpaceX vs Anthropic
sx = next(e for e in P["states"] if e["name"] == "SpaceX")
a1, a2, a3 = P["anthropic"]["Anthropic S-1 public (26 Oct 2026)"], P["anthropic"]["Anthropic, T-11 (3 Nov 2026)"], P["anthropic"]["Latest (13 Nov 2026)"]
rows = []
for k, lab, stretched, ispct in VARS:
    fm = (lambda v: f(v, 1)) if ispct else (lambda v: num(v, 2))
    if k == "rv21":
        fm = lambda v: f(v, 1, sign=False)
    rows.append(rf"{lab} & {fm(sx[k])} ({sx[k+'_pct']*100:.0f}) & {fm(a1[k])} ({a1[k+'_pct']*100:.0f}) & {fm(a2[k])} ({a2[k+'_pct']*100:.0f}) & {fm(a3[k])} ({a3[k+'_pct']*100:.0f}) \\")
table("t13_case", "SpaceX and Anthropic: the state of positioning", "tab:case", "lrrrr",
      r"Variable & SpaceX, T$-$11 & ANT, S-1 public & ANT, T$-$11 & ANT, 13 Nov", rows,
      "Value (percentile rank since June 2020). SpaceX T$-$11 = 27 May 2026; Anthropic S-1 public = 26 October 2026; Anthropic T$-$11 = 3 November 2026.", size=r"\footnotesize", fit=True)
rows = []
for k, lab in [("Bitcoin", "Bitcoin"), ("MSTR", "MSTR"), ("Spec. growth (ARKK)", "ARKK"), ("Semis", "Semis (SMH)"), ("Nasdaq 100", "Nasdaq 100"), ("Gold", "Gold"),
               ("High beta - low vol", "High beta $-$ low vol"), ("Momentum - market", "Momentum $-$ market")]:
    sxv = P["responses"][k]["pre"]["values"][-2]
    rows.append(rf"{lab} & {f(sxv,1)} & {f(P['ant_move'][k],1)} \\")
table("t14_moves", "The sell-offs: SpaceX pre-listing window and Anthropic so far", "tab:moves", "lrr", r"Asset & SpaceX, T$-$10 to T$-$1 & Anthropic, 3--13 Nov", rows,
      "Log returns in percent. Anthropic's window covers 8 of its 10 pre-listing sessions.", size=r"\footnotesize")

# ======================================================== FIGURES
# F1 PSI time series with events
fig, ax = plt.subplots(figsize=(6.8, 2.8))
psi = TS.PSI.loc["2020-06-01":]
ax.plot(psi.index, psi.values, color=B1, lw=1.2)
ax.axhline(P["psi_median"], color=MUT, lw=0.8, ls="--"); ax.text(psi.index[5], P["psi_median"] + 0.08, "sample median", color=MUT, fontsize=7)
for e in P["states"]:
    d = pd.Timestamp(e["s_date"]); col = INK if e["name"] in ("SpaceX", "SK hynix ADR") else O2
    ax.plot(d, e["PSI"], "o", color=col, ms=4.5 if col == INK else 3.5, mec="white", mew=0.6, zorder=3)
sx_d = pd.Timestamp(sx["s_date"]); ax.annotate("SpaceX", (sx_d, sx["PSI"]), xytext=(-40, 14), textcoords="offset points", fontsize=7, arrowprops=dict(arrowstyle="-", color=MUT, lw=0.6))
ad = pd.Timestamp("2026-11-03"); ax.plot(ad, a2["PSI"], "D", color=RED, ms=4.5, zorder=4)
ax.annotate("Anthropic T$-$11", (ad, a2["PSI"]), xytext=(-75, -18), textcoords="offset points", fontsize=7, arrowprops=dict(arrowstyle="-", color=MUT, lw=0.6))
ax.set_ylabel("PSI (mean z-score)"); ax.set_title("Positioning stretch index, weekly; orange = large listings (T$-$11)", fontsize=8, loc="left")
fig.savefig(FIG / "f1_psi.pdf"); plt.close(fig)

# F2 state dashboard percentiles
keys = [v[0] for v in VARS]
fig, ax = plt.subplots(figsize=(6.6, 3.6)); y = np.arange(len(keys))[::-1]
for j, (lab, src, col) in enumerate([("SpaceX, T$-$11", sx, INK), ("Anthropic, S-1 public", a1, Y4), ("Anthropic, 13 Nov", a3, RED)]):
    ax.barh(y + (1 - j) * 0.26, [src[k + "_pct"] * 100 for k in keys], height=0.24, color=col, label=lab)
ax.set_yticks(y, [VLAB[k].replace("\\&", "&") for k in keys], fontsize=7); ax.set_xlim(0, 100); ax.axvline(50, color=MUT, lw=0.7, ls=":")
ax.set_xlabel("Percentile rank since June 2020"); ax.legend(fontsize=7, loc="lower right"); ax.grid(axis="y", visible=False)
fig.savefig(FIG / "f2_dashboard.pdf"); plt.close(fig)

# F3 scatter PSI vs day 63 + F4 terciles
d = pd.DataFrame(PI.get("rows", []))
co2 = CO.copy()
psi_at = {}
for _, r in co2.iterrows():
    s = TS.PSI.loc[:pd.Timestamp(r.ipo_date) - pd.Timedelta(days=1)]
    psi_at[r.ticker] = s.iloc[-1]
co2["PSI"] = co2.ticker.map(psi_at)
fig, axs = plt.subplots(1, 2, figsize=(6.8, 2.9), gridspec_kw={"width_ratios": [1.2, 1]})
ax = axs[0]
colr = [O2 if dmd == "Above range" else B1 for dmd in co2.demand]
ax.scatter(co2.PSI, co2.r63 * 100, s=22, c=colr, edgecolors="white", linewidths=0.7, zorder=3)
zf = np.polyfit(co2.PSI, co2.r63 * 100, 1); xx = np.linspace(co2.PSI.min(), co2.PSI.max(), 10); ax.plot(xx, np.polyval(zf, xx), color=MUT, ls="--", lw=1)
for t in ["SPCX", "CRWV", "AFRM", "FIG"]:
    r = co2[co2.ticker == t].iloc[0]; ax.annotate(t, (r.PSI, r.r63 * 100), xytext=(4, 3), textcoords="offset points", fontsize=6.5, color="#52514e")
ax.set_ylim(-80, 120); ax.set_xlabel("PSI at listing"); ax.set_ylabel("Day-1 close to day 63 (%)")
ax.set_title("(a) Stretched markets, deeper fades ($\\rho=-0.51$)", fontsize=8, loc="left"); ax.text(0.98, 0.95, "orange: priced above range\nblue: at or below", transform=ax.transAxes, ha="right", va="top", fontsize=6.5, color="#52514e")
ax = axs[1]; labs = list(T.keys()); x = np.arange(4)
for j, (lab, col) in enumerate(zip(labs, [B1, MUT, RED])):
    v = T[lab]; ax.bar(x + (j - 1) * 0.26, [v["pop"] * 100, v["r21"] * 100, v["r63"] * 100, v["x63"] * 100], width=0.24, color=col, label=f"{lab} (n={v['n']})")
ax.set_xticks(x, ["Pop", "Day 21", "Day 63", "D63 vs QQQ"], fontsize=7); ax.axhline(0, color="#c3c2b7", lw=0.8); ax.legend(fontsize=6.5); ax.set_ylabel("Median (%)")
ax.set_title("(b) Outcomes by PSI tercile", fontsize=8, loc="left")
fig.tight_layout(); fig.savefig(FIG / "f3_ipo.pdf"); plt.close(fig)

# F4 interaction forest
fig, ax = plt.subplots(figsize=(6.6, 4.4)); yy = np.arange(len(regs))[::-1]
for y_, r in zip(yy, regs):
    col = RED if r["p_inter"] < 0.05 else (Y4 if r["p_inter"] < 0.10 else MUT)
    ax.plot([(r["d_inter"] - 1.96 * r["se"]) * 100, (r["d_inter"] + 1.96 * r["se"]) * 100], [y_, y_], color=col, lw=1.8)
    ax.plot(r["d_inter"] * 100, y_, "o", color=col, ms=4.5, mec="white", mew=0.8)
ax.axvline(0, color="#c3c2b7", lw=0.9); ax.set_yticks(yy, [f"{r['asset']} · {r['window']}" for r in regs], fontsize=6.5); ax.grid(axis="y", visible=False)
ax.set_xlabel("Event × PSI coefficient (% per PSI unit), 95% HAC CI"); ax.set_title("Extra move around large listings per unit of positioning stretch", fontsize=8, loc="left")
fig.savefig(FIG / "f4_inter.pdf"); plt.close(fig)

# F5 momentum unwind and leverage
fig, axs = plt.subplots(1, 2, figsize=(6.8, 2.7))
ax = axs[0]; z = TS.loc["2025-06-01":]
ax.plot(z.index, z.beta63 * 100, color=O2, label="High beta vs low vol, 63d"); ax.plot(z.index, z.mtum63 * 100 if "mtum63" in z else z.beta63 * 0, color=B1, label="Momentum vs market, 63d")
for dd, lab in [("2026-06-12", "SpaceX"), ("2026-11-19", "ANT")]:
    ax.axvline(pd.Timestamp(dd), color=MUT, lw=0.7, ls=":"); ax.text(pd.Timestamp(dd), ax.get_ylim()[1] * 0.92 if ax.get_ylim()[1] > 0 else 1, lab, fontsize=6.5, color=MUT, ha="right")
ax.axhline(0, color="#c3c2b7", lw=0.8); ax.legend(fontsize=6.5, loc="lower left"); ax.set_ylabel("%"); ax.set_title("(a) Crowded risk trades unwound before ANT", fontsize=8, loc="left")
ax.tick_params(axis="x", labelsize=6.5)
ax = axs[1]; fm = P["finra"]
ax.bar(range(len(fm)), [v / 1e6 for _, v in fm], color=[RED if m == "Jun-26" else "#c3c2b7" for m, _ in fm])
ax.set_xticks(range(len(fm)), [m for m, _ in fm], rotation=60, fontsize=6); ax.set_ylim(1.1, 1.55); ax.set_ylabel("$ trillion")
ax.set_title("(b) FINRA margin debt peaked in the SpaceX month", fontsize=8, loc="left")
fig.tight_layout(); fig.savefig(FIG / "f5_unwind.pdf"); plt.close(fig)
print("ok", sorted(p.name for p in FIG.glob("*.pdf")), len(list(TAB.glob("*.tex"))))
