"""Tables and figures for "Reading the Book": subscription signals and the IPO pop (paper 3).

Usage: python3 ipo_study/paper_signals/make_paper3.py  (after signals.py, pm_analysis.py, intraday + crowding scripts)
"""
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import yfinance as yf
from scipy import stats

HERE = Path(__file__).parent
DATA = HERE.parent / "data"
TAB, FIG = HERE / "tables", HERE / "figures"
TAB.mkdir(exist_ok=True); FIG.mkdir(exist_ok=True)
SG = json.loads((DATA / "signals.json").read_text())
PM = json.loads((DATA / "pm.json").read_text())
CO = pd.DataFrame(SG["cohort"])
OV = pd.read_csv(DATA / "oversub.csv")
B1, O2, A3, RED, INK, MUT, GRID = "#2a78d6", "#eb6834", "#1baf7a", "#e34948", "#0b0b0b", "#898781", "#e1e0d9"
GC = {"Cold: at or below first range": B1, "Warm: above first range": A3, "Hot: range raised and priced above it": O2}
plt.rcParams.update({"font.family": "serif", "font.serif": ["DejaVu Serif"], "font.size": 8.5, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.edgecolor": "#c3c2b7", "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6, "legend.frameon": False,
                     "savefig.bbox": "tight", "pdf.fonttype": 42})


def f(v, d=0, sign=True):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "--"
    s = f"{abs(v*100):.{d}f}"
    return s if float(s) == 0 else ("$-$" if v < 0 else ("+" if sign else "")) + s


def num(v, d=2):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "--"
    s = f"{abs(v):.{d}f}"
    return ("$-$" if v < 0 and float(s) != 0 else "") + s


def fp(p):
    return "--" if p is None else ("$<$0.001" if p < 0.001 else (f"{p:.3f}" if p < 0.1 else f"{p:.2f}"))


def table(name, caption, label, colspec, header, rows, notes, size=r"\footnotesize", fit=False, wide=False):
    env = "table*" if wide else "table"
    body = [rf"\begin{{{env}}}[!htbp]\centering{size}", rf"\caption{{{caption}}}\label{{{label}}}", r"\resizebox{\linewidth}{!}{" if fit else "",
            r"\begin{threeparttable}", rf"\begin{{tabular}}{{{colspec}}}", r"\toprule", header + r" \\", r"\midrule"] + rows + \
           [r"\bottomrule", r"\end{tabular}", r"\begin{tablenotes}[flushleft]\footnotesize", rf"\item \textit{{Notes:}} {notes}", r"\end{tablenotes}",
            r"\end{threeparttable}", "}" if fit else "", rf"\end{{{env}}}"]
    (TAB / f"{name}.tex").write_text("\n".join(body) + "\n")


# ---------------- T1 signals summary
rows = [rf"Price revision (offer vs first-range midpoint) & {CO.rev.notna().sum()} & {f(CO.rev.mean(),1)} & {f(CO.rev.median(),1)} & {f(CO.rev.min(),0)} to {f(CO.rev.max(),0)} \\",
        rf"Range revision (final vs first midpoint) & {CO.range_rev.notna().sum()} & {f(CO.range_rev.mean(),1)} & {f(CO.range_rev.median(),1)} & {f(CO.range_rev.min(),0)} to {f(CO.range_rev.max(),0)} \\",
        rf"Offer vs final-range midpoint & {CO.rev_final.notna().sum()} & {f(CO.rev_final.mean(),1)} & {f(CO.rev_final.median(),1)} & {f(CO.rev_final.min(),0)} to {f(CO.rev_final.max(),0)} \\",
        rf"Priced above first range (share) & {CO.above.notna().sum()} & {CO.above.mean()*100:.0f}\% & -- & -- \\",
        rf"Range raised before pricing (share) & {CO.range_raised.notna().sum()} & {CO.range_raised.mean()*100:.0f}\% & -- & -- \\",
        rf"Upsized (share) & {len(CO)} & {CO.upsized.mean()*100:.0f}\% & -- & -- \\",
        rf"Reported oversubscription (times) & {len(OV)} & {OV.oversub.mean():.1f}$\times$ & {OV.oversub.median():.0f}$\times$ & {OV.oversub.min():g}$\times$ to {OV.oversub.max():g}$\times$ \\"]
table("s1_signals", "Book-building signals in the cohort", "tab:s1", "lrrrr", r"Signal & $n$ & Mean & Median & Range", rows,
      "Percent unless stated. Ranges and offer prices from SEC 424B4 prospectuses and pricing releases; upsizing and oversubscription from pricing releases and Reuters, Bloomberg and CNBC reports. SpaceX priced at a fixed \\$135 with no range and is excluded from range-based signals.")

# ---------------- T2 correlation grid
SL = {"rev": "Price revision", "range_rev": "Range revision", "rev_final": "Offer vs final range", "above": "Above first range", "range_raised": "Range raised",
      "upsized": "Upsized", "float_pct": "Float", "logproc": "log proceeds", "CROWD": "Crowding at listing", "PSI": "Positioning (PSI)"}
OL = [("open_pop", "Open vs offer"), ("oc1", "Open$\\to$close"), ("close_vs_high", "Close vs high"), ("pop", "Close vs offer"), ("gap2", "Day-2 gap"),
      ("d1_5", "D1$\\to$D5"), ("d1_63", "D1$\\to$D63")]
cm = {(c["signal"], c["outcome"]): c for c in SG["corr"]}
def cc(s, o):
    c = cm.get((s, o))
    if not c:
        return "--"
    st = "$^{\\dagger}$" if c["q"] < 0.05 else ("$^{*}$" if c["q"] < 0.10 else "")
    return num(c["rho"]) + st
rows = [SL[s] + " & " + " & ".join(cc(s, o) for o, _ in OL) + r" \\" for s in SL]
table("s2_corr", "Which signals predict which part of the debut? Rank correlations", "tab:s2", "l" + "r" * len(OL), "Signal & " + " & ".join(l for _, l in OL), rows,
      "Spearman $\\rho$, 42--43 IPOs. $^{\\dagger}q<0.05$, $^{*}q<0.10$ (Benjamini--Hochberg over all signal--outcome pairs). Close vs offer is the first-day return (``pop''); later returns are measured from the first close.", fit=True)

# ---------------- T3 decomposition
dec = SG["decomposition"]
YL = {"lopen": "log(1+opening pop)", "loc1": "log(1+open$\\to$close)", "lpop": "log(1+first-day return)", "d1_5": "Day 1$\\to$5", "d1_63": "Day 1$\\to$63"}
rows = []
for y, lab in YL.items():
    r = dec[y]
    rows.append(rf"{lab} & {num(r['coef']['rev'])} ({num(r['t']['rev'],1)}) & {num(r['coef']['CROWD'])} ({num(r['t']['CROWD'],1)}) & {num(r['coef']['logproc'])} ({num(r['t']['logproc'],1)}) & {r['r2']:.2f} & {r['n']} \\")
table("s3_decomp", "Demand prices the open; nothing prices the rest of the day", "tab:s3", "lrrrrr", r"Dependent variable & Price revision & Crowding & log proceeds & $R^2$ & $n$", rows,
      f"OLS with HC3 $t$-statistics. Across the cohort the opening print accounts for {SG['share_open']*100:.0f}\\% of the summed log first-day return: on average the stock drifts slightly lower after it opens.")

# ---------------- T4/T5 groups
def gtab(name, key, caption, label):
    g = SG["groups"][key]
    rows = []
    for r in g["rows"]:
        rows.append(rf"{r['key'].replace('%', r'\%')} & {r['n']} & {f(r['open_pop'])} & {f(r['oc1'],1)} & {f(r['close_vs_high'],1)} & {f(r['pop'])} & {r['broke']*100:.0f}\% & {f(r['gap2'],1)} & {f(r['d1_5'],1)} & {f(r['d1_21'],1)} & {f(r['d1_63'])} & {f(r['x63'])} \\")
    kw = g["kw"]
    rows.append(r"\midrule")
    rows.append(rf"Kruskal--Wallis $p$ & & {fp(kw['open_pop'])} & {fp(kw['oc1'])} & & {fp(kw['pop'])} & & & {fp(kw['d1_5'])} & {fp(kw['d1_21'])} & {fp(kw['d1_63'])} & \\")
    table(name, caption, label, "lrrrrrrrrrrr", r"Group & $n$ & Open & Open$\to$close & Close vs high & Pop & Broke & Day-2 gap & D1$\to$5 & D1$\to$21 & D1$\to$63 & D63 vs QQQ", rows,
          "Medians in percent. Broke = share closing day 1 below the offer. Day-2 gap = day-2 open vs day-1 close. Later returns from the first close.", size=r"\scriptsize", fit=True)
gtab("s4_groups", "Book-building signal", "Debut and aftermarket by book-building signal", "tab:s4")
gtab("s5_rev", "Price revision", "Debut and aftermarket by size of price revision", "tab:s5")

# ---------------- T6 oversubscription + roadshow context
m = OV.merge(CO.drop(columns=["oversub"]), on="ticker")
rows = [rf"{r.name} & {r.oversub:g}$\times$ & {f(r.rev)} & {f(r.open_pop)} & {f(r.oc1)} & {f(r.pop)} & {f(r.d1_63)} \\" for r in m.sort_values("oversub").itertuples()]
rho, p = stats.spearmanr(m.oversub, m["pop"])
rows += [r"\midrule", rf"Spearman $\rho$ with oversubscription & & & {num(stats.spearmanr(m.oversub, m.open_pop)[0])} & {num(stats.spearmanr(m.oversub, m.oc1)[0])} & {num(rho)} ($p={p:.2f}$) & {num(stats.spearmanr(m.oversub, m.d1_63)[0])} \\"]
table("s6_oversub", "Headline oversubscription and the debut (7 IPOs with reported book coverage)", "tab:s6", "lrrrrrr",
      r"IPO & Book covered & Price revision & Open & Open$\to$close & Pop & D1$\to$D63", rows,
      "Percent. Book coverage as reported during the roadshow (Reuters, Bloomberg), lower bound when reported as a range. The 20$\\times$ books all traded lower from open to close; headline coverage is a weak and, if anything, inverse signal for the pop.", fit=True)
rows = [r"Anthropic & 10 Nov & \$70--78, 825m shares & $\sim$2$\times$ after day 1; $\sim$6$\times$ after day 3 (12 Nov) & Range unchanged as of 15 Nov; concurrent private placement $\sim$\$26bn \\",
        r"SpaceX & 2 Jun & Fixed \$135, 556m shares & 2$\times$ after day 2; 3.5--4$\times$ near pricing & Pop $+$19\%; peak day 3; below offer by day 23 \\"]
table("s7_roadshow", "Roadshow demand: Anthropic and SpaceX", "tab:s7", "llp{2.7cm}p{3.6cm}p{4.2cm}", r"IPO & Launch & Terms & Reported book & Notes", rows,
      "Reuters and Bloomberg reports of 9 June 2026 (SpaceX) and 12--14 November 2026 (Anthropic). Book coverage figures are banker estimates during the roadshow and can change.", fit=True)

# ---------------- T8 entry/exit matrix
MX = SG["matrix"]
def mcell(v):
    return "--" if not v else f"{f(v['mean'],1)} / {v['hit']*100:.0f} / {num(v['sr'])}"
rows = []
for grp in ["All", "Cold: at or below first range", "Warm: above first range", "Hot: range raised and priced above it"]:
    rows.append(rf"\multicolumn{{6}}{{l}}{{\textit{{{grp}}} ($n={MX[grp]['Buy the day-1 close']['Sell day 5']['n'] if MX[grp]['Buy the day-1 close']['Sell day 5'] else ''}$)}} \\")
    e = MX[grp]
    rows.append(rf"\quad Subscribe at offer & {mcell(e['Subscribe at offer']['Sell at open'])} & {mcell(e['Subscribe at offer']['Sell at day-1 close'])} & {mcell(e['Subscribe at offer']['Sell day 5'])} & {mcell(e['Subscribe at offer']['Sell day 21'])} & {mcell(e['Subscribe at offer']['Sell day 63'])} \\")
    rows.append(rf"\quad Buy the open & -- & {mcell(e['Buy the open']['Sell at day-1 close'])} & {mcell(e['Buy the open']['Sell day 5'])} & {mcell(e['Buy the open']['Sell day 21'])} & {mcell(e['Buy the open']['Sell day 63'])} \\")
    rows.append(rf"\quad Buy the day-1 close & -- & -- & {mcell(e['Buy the day-1 close']['Sell day 5'])} & {mcell(e['Buy the day-1 close']['Sell day 21'])} & {mcell(e['Buy the day-1 close']['Sell day 63'])} \\")
table("s8_matrix", "When to subscribe, when to buy, when to sell: mean return / hit rate / Sharpe per trade", "tab:s8", "llllll",
      r"Entry & Exit at open & Day-1 close & Day 5 & Day 21 & Day 63", rows,
      "Each cell: mean return in percent / share of trades that made money / mean divided by standard deviation. Subscribing assumes a full allocation at the offer, which hot deals rarely give. Costs, borrow and allocation size are ignored.",
      size=r"\scriptsize", fit=True, wide=True)

# ---------------- T9 predictive model + Anthropic
MD = SG["model"]
rows = [rf"{k} & {num(MD['coef'][k],3)} & {num(MD['t'][k],1)} \\" for k in ["Intercept", "rev", "CROWD", "logproc"]]
rows = [r.replace("rev &", "Price revision &").replace("CROWD &", "Crowding at listing &").replace("logproc &", "log proceeds &") for r in rows]
rows += [r"\midrule", rf"$R^2$ (in sample) / leave-one-out $R^2$ & {MD['r2']:.2f} & {MD['r2_loo']:.2f} \\", rf"$n$ & {MD['n']} & \\"]
table("s9_model", "A model of the first-day return from book-building signals", "tab:s9", "lrr", r"Variable & Coefficient & $t$ (HC3)", rows,
      "Dependent variable log(1+first-day return). Leave-one-out $R^2$ refits the model without each IPO and predicts it.")
rows = []
for a in MD["anthropic"]:
    rows.append(rf"{a['label'].replace('$', '\\$')} & \${a['offer']:.1f} & {f(a['rev'])} & {f(a['pred'])} & {f(a['p10'])} to {f(a['p90'])} & {a['p_pos']*100:.0f}\% \\")
rows += [r"\midrule", rf"Same, prediction-market offer, crowding at the cohort median & \${PM['offer_from_raise']['mean']:.1f} & {f(PM['offer_from_raise']['mean']/74-1)} & {f(MD['anthropic_median_crowding'])} & -- & -- \\",
         rf"Prediction markets directly (Polymarket) & \${PM['offer_from_raise']['mean']:.1f} & {f(PM['offer_from_raise']['mean']/74-1)} & {f(PM['pop']['median'])} (median) & {f(PM['pop_quantiles']['10'])} to {f(PM['pop_quantiles']['90'])} & {PM['direct']['close_above_offer']*100:.0f}\% \\"]
table("s10_anthropic", "Anthropic: first-day return implied by the signal model and by prediction markets", "tab:s10", "lrrrrr",
      r"Scenario & Offer & Revision & Expected pop & 80\% range & P(close $>$ offer)", rows,
      f"Model rows use Anthropic's crowding composite on 13 November ({MD['extrapolation']['crowd_ant']:.2f}, below the cohort minimum of {MD['extrapolation']['crowd_min']:.2f}) and proceeds of 825 million shares at the offer, far above any cohort deal; both are extrapolations. "
      "Ranges add the model's residuals. The last row is the market-implied distribution of Section~6.", fit=True)

# ---------------- T11 prediction-market snapshot (compact)
rows = [rf"Day-1 closing market cap (\$tn) & {PM['closing_cap']['summary']['mean']:.2f} & {PM['closing_cap']['summary']['median']:.2f} & {PM['closing_cap']['summary']['p10']:.2f}--{PM['closing_cap']['summary']['p90']:.2f} \\",
        rf"Offer implied by valuation market (\$) & {PM['offer_from_valuation']['mean']:.1f} & {PM['offer_from_valuation']['median']:.1f} & {PM['offer_from_valuation']['p10']:.1f}--{PM['offer_from_valuation']['p90']:.1f} \\",
        rf"Offer implied by amount-raised market (\$) & {PM['offer_from_raise']['mean']:.1f} & {PM['offer_from_raise']['median']:.1f} & {PM['offer_from_raise']['p10']:.1f}--{PM['offer_from_raise']['p90']:.1f} \\",
        rf"Day-1 closing share price (\$) & {PM['close_price']['mean']:.1f} & {PM['close_price']['median']:.1f} & {PM['close_price']['p10']:.1f}--{PM['close_price']['p90']:.1f} \\",
        rf"First-day return (\%) & {f(PM['pop']['mean'])} & {f(PM['pop']['median'])} & {f(PM['pop']['p10'])} to {f(PM['pop']['p90'])} \\",
        rf"P(offer $>$ \$78): valuation / amount raised & \multicolumn{{3}}{{l}}{{{PM['p_above_range_val']*100:.0f}\% / {PM['p_above_range_raise']*100:.0f}\%}} \\",
        rf"P(close $>$ offer), P(open $>$ offer), direct markets & \multicolumn{{3}}{{l}}{{{PM['direct']['close_above_offer']*100:.1f}\%, {PM['direct']['open_above_offer']*100:.0f}\%}} \\",
        rf"Kalshi: IPO before 20 Nov; Goldman Sachs lead-left & \multicolumn{{3}}{{l}}{{97--98\%; 99\%}} \\"]
table("s11_pm", "What prediction markets expect (15 November 2026)", "tab:s11", "lrrr", r"Quantity & Mean & Median & 10th--90th percentile", rows,
      "Polymarket bracket markets combined by Monte Carlo; fully diluted shares 18.0bn, basic shares implied by the share-sold market ($\\approx$12.6bn), 825 million shares sold. See the companion paper for definitions and the SpaceX calibration.")
sx = PM["spacex"]
rows = [rf"{l.replace('$', '\\$')} & {sx['pre']['p'][i]*100:.0f}\% & {sx['post']['p'][i]*100:.0f}\% \\" for i, l in enumerate(sx["labels"])]
rows += [r"\midrule", rf"Expected value (\$tn) & {sx['pre']['ev']:.2f} & {sx['post']['ev']:.2f} \\", rf"Outcome & \multicolumn{{2}}{{l}}{{\$2.0--2.5tn bracket; day-1 close \${sx['day1_close_cap']:.2f}tn}} \\"]
table("s12_sx", "Calibration check: SpaceX end-of-IPO-month market cap (Polymarket)", "tab:s12", "lrr", r"Bracket & Before trading & After day 1", rows,
      "Normalised mid prices at 00:00 UTC on 12 and 13 June 2026.")

# ================= FIGURES
# F1 scatter revision vs open pop / pop
fig, axs = plt.subplots(1, 2, figsize=(6.8, 2.8), sharex=True)
for ax, y, ttl in [(axs[0], "open_pop", "(a) Opening print vs offer"), (axs[1], "pop", "(b) Day-1 close vs offer")]:
    for g, col in GC.items():
        s = CO[CO.sig_g == g]; ax.scatter(s.rev * 100, s[y] * 100, s=20, color=col, edgecolors="white", linewidths=0.6, label=g.split(":")[0], zorder=3)
    ok = CO.dropna(subset=["rev", y]); z = np.polyfit(ok.rev * 100, ok[y] * 100, 1); xx = np.linspace(-45, 60, 10); ax.plot(xx, np.polyval(z, xx), color=MUT, ls="--", lw=1)
    ax.set_title(ttl, fontsize=8, loc="left"); ax.set_xlabel("Price revision vs first-range midpoint (%)"); ax.axhline(0, color="#c3c2b7", lw=0.8)
axs[0].set_ylabel("%"); axs[0].legend(fontsize=6.5, loc="upper left")
fig.tight_layout(); fig.savefig(FIG / "f1_rev.pdf"); plt.close(fig)

# F2 debut anatomy by group
order = ["Cold: at or below first range", "Warm: above first range", "Hot: range raised and priced above it"]
G = {r["key"]: r for r in SG["groups"]["Book-building signal"]["rows"]}
fig, ax = plt.subplots(figsize=(6.4, 2.6)); x = np.arange(4); labs = ["Open vs offer", "Open→close", "Close vs high", "Close vs offer"]
for j, k in enumerate(order):
    r = G[k]; ax.bar(x + (j - 1) * 0.26, [r["open_pop"] * 100, r["oc1"] * 100, r["close_vs_high"] * 100, r["pop"] * 100], width=0.24, color=GC[k], label=f"{k.split(':')[0]} (n={r['n']})")
ax.set_xticks(x, labs); ax.axhline(0, color="#c3c2b7", lw=0.8); ax.set_ylabel("Median (%)"); ax.legend(fontsize=7)
fig.savefig(FIG / "f2_anatomy.pdf"); plt.close(fig)

# F3 hourly path from the first print, hot vs others (IPOs with hourly debut data)
names = SG["hourly"]["names"]; hot = set(SG["hourly"]["hot"])
paths = {"Hot": [], "Other": []}
for t in names:
    h = yf.Ticker(t).history(period="730d", interval="60m"); h.index = h.index.tz_convert("America/New_York"); h = h[h.Volume > 0]
    days = sorted(set(h.index.date))[:3]
    g = h[h.index.date <= days[-1]]
    series = (g.Close / g.Open.iloc[0] - 1).values[:22]
    paths["Hot" if t in hot else "Other"].append(series)
fig, ax = plt.subplots(figsize=(6.4, 2.6))
for k, col in [("Hot", O2), ("Other", B1)]:
    L = min(len(s) for s in paths[k]); M = np.array([s[:L] for s in paths[k]])
    ax.plot(np.arange(L) + 1, np.nanmedian(M, axis=0) * 100, color=col, marker="o", ms=3, label=f"{k} (n={len(paths[k])})")
ax.axhline(0, color="#c3c2b7", lw=0.8); ax.set_xlabel("Hourly bars since the first print (about 7 per session)"); ax.set_ylabel("vs opening print (%)"); ax.legend(fontsize=7)
fig.savefig(FIG / "f3_hourly.pdf"); plt.close(fig)

# F4 close-to-close days 1-10 by group
fig, ax = plt.subplots(figsize=(6.0, 2.6))
for k in order:
    v = SG["cpath"][k]; ax.plot(range(1, len(v["mean"]) + 1), np.array(v["mean"]) * 100, color=GC[k], marker="o", ms=3, label=f"{k.split(':')[0]} (n={v['n']})")
ax.axhline(0, color="#c3c2b7", lw=0.8); ax.set_xlabel("Trading day"); ax.set_ylabel("Mean cumulative return from day-1 close (%)"); ax.legend(fontsize=7)
fig.savefig(FIG / "f4_c2c.pdf"); plt.close(fig)

# F5 entry/exit heatmap (mean returns) for All / Hot / Cold
fig, axs = plt.subplots(1, 3, figsize=(7.2, 2.3), sharey=True)
exits = ["Sell at open", "Sell at day-1 close", "Sell day 5", "Sell day 21", "Sell day 63"]; ents = ["Subscribe at offer", "Buy the open", "Buy the day-1 close"]
for ax, grp in zip(axs, ["All", "Hot: range raised and priced above it", "Cold: at or below first range"]):
    M = np.full((3, 5), np.nan)
    for i, e in enumerate(ents):
        for j, x_ in enumerate(exits):
            v = MX[grp][e].get(x_)
            if v: M[i, j] = v["mean"] * 100
    im = ax.imshow(M, cmap="RdBu", vmin=-60, vmax=60, aspect="auto")
    for i in range(3):
        for j in range(5):
            if not np.isnan(M[i, j]): ax.text(j, i, f"{M[i,j]:+.0f}", ha="center", va="center", fontsize=6.5, color="white" if abs(M[i, j]) > 35 else "black")
    ax.set_xticks(range(5), ["Open", "Close", "D5", "D21", "D63"], fontsize=6.5); ax.set_title(grp.split(":")[0], fontsize=8, loc="left"); ax.grid(False)
axs[0].set_yticks(range(3), ["Subscribe", "Buy open", "Buy close"], fontsize=7)
fig.tight_layout(); fig.savefig(FIG / "f5_matrix.pdf"); plt.close(fig)

# F6 Anthropic: model vs prediction market
fig, axs = plt.subplots(1, 2, figsize=(6.8, 2.6))
ax = axs[0]
labs = ["Model, range mid", "Model, top of range", "Model, PM offer", "Model, PM offer,\nmedian crowding", "Polymarket"]
A = MD["anthropic"]; vals = [A[3]["pred"], A[2]["pred"], A[0]["pred"], MD["anthropic_median_crowding"], PM["pop"]["median"]]
lo = [A[3]["p10"], A[2]["p10"], A[0]["p10"], np.nan, PM["pop_quantiles"]["10"]]; hi = [A[3]["p90"], A[2]["p90"], A[0]["p90"], np.nan, PM["pop_quantiles"]["90"]]
y = np.arange(len(labs))[::-1]
for yy, v, l, h_, c in zip(y, vals, lo, hi, [MUT, MUT, B1, B1, O2]):
    if not np.isnan(l): ax.plot([l * 100, h_ * 100], [yy, yy], color=c, lw=2)
    ax.plot(v * 100, yy, "o", color=c, ms=6)
ax.axvline(0, color="#c3c2b7", lw=0.8); ax.set_yticks(y, labs, fontsize=6.5); ax.set_xlabel("First-day return (%), 80% range"); ax.set_title("(a) Anthropic's pop: model vs market", fontsize=8, loc="left"); ax.grid(axis="y", visible=False)
ax = axs[1]
ax.plot([1, 3], [2, 6], "o-", color=O2, label="Anthropic (reported)"); ax.plot([2, 6], [2, 3.75], "s-", color=INK, label="SpaceX (reported)")
ax.set_xlabel("Roadshow day"); ax.set_ylabel("Book coverage (×)"); ax.legend(fontsize=7); ax.set_title("(b) Book build", fontsize=8, loc="left")
fig.tight_layout(); fig.savefig(FIG / "f6_anthropic.pdf"); plt.close(fig)
print("paper3 assets:", sorted(p.name for p in TAB.glob("*.tex")), sorted(p.name for p in FIG.glob("*.pdf")))
