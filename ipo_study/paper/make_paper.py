"""Generate figures (vector PDF) and LaTeX tables for the research paper from the analysis outputs.

Usage:  python3 ipo_study/paper/make_paper.py     (then compile main.tex, or upload the folder to Overleaf)
Inputs: ipo_study/data/{stats,xasset,intraday,artifact_data}.json, enriched_cohort.csv, deal_terms.csv
Writes: ipo_study/paper/figures/*.pdf and ipo_study/paper/tables/*.tex
"""
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

HERE = Path(__file__).parent
DATA = HERE.parent / "data"
FIG, TAB = HERE / "figures", HERE / "tables"
FIG.mkdir(exist_ok=True)
TAB.mkdir(exist_ok=True)

ST = json.loads((DATA / "stats.json").read_text())
XA = json.loads((DATA / "xasset.json").read_text())
IN = json.loads((DATA / "intraday.json").read_text())
AD = json.loads((DATA / "artifact_data.json").read_text())
CO = pd.read_csv(DATA / "enriched_cohort.csv")
DT = pd.read_csv(DATA / "deal_terms.csv")
CO = CO.merge(DT[["ticker", "proceeds_m", "float_pct", "revision_pct", "demand", "upsized"]], on="ticker", how="left")


def bh(p):
    p = np.asarray(p, float); n = len(p); o = np.argsort(p)
    q = np.empty(n); q[o] = np.minimum.accumulate((p[o] * n / np.arange(1, n + 1))[::-1])[::-1]
    return np.minimum(q, 1)


# Anthropic trading calendar (same rule as the web build): day 1 = 19 Nov 2026, NYSE holidays
_bd = pd.offsets.CustomBusinessDay(holidays=pd.to_datetime(["2026-11-26", "2026-12-25", "2027-01-01", "2027-01-18", "2027-02-15", "2027-03-26", "2027-05-31", "2027-06-18"]))
AD["ant_cal"] = [dict(label=l, day=k, date=(pd.Timestamp("2026-11-19") + k * _bd).strftime("%a %d %b %Y")) for l, k in
                 [("Pricing (after the close)", -1), ("Day 1: first trade", 0), ("Day 5", 4), ("Day 13: SpaceX lock-up expiry", 12), ("Day 21", 20), ("Day 63", 62), ("Day 126 (about 180 days)", 125)]]

_keys = [(a, w) for a in XA["daily"] for w in XA["daily"][a]]
for (a, w), qq in zip(_keys, bh([XA["daily"][a][w]["p_perm"] for a, w in _keys])):  # Benjamini-Hochberg across the 56 windows
    r = XA["daily"][a][w]
    r["q"] = float(qq)
    r["median"] = float(np.median([v for v in r["values"] if v is not None]))

# palette (validated categorical slots) and chart chrome
B1, O2, A3, Y4, RED, INK, MUT, GRID = "#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e34948", "#0b0b0b", "#898781", "#e1e0d9"
plt.rcParams.update({"font.family": "serif", "font.serif": ["DejaVu Serif"], "font.size": 8.5, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.edgecolor": "#c3c2b7", "axes.linewidth": 0.8, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6,
                     "xtick.color": "#52514e", "ytick.color": "#52514e", "axes.labelcolor": "#52514e", "legend.frameon": False,
                     "lines.linewidth": 1.6, "savefig.bbox": "tight", "pdf.fonttype": 42})


# ------------------------------------------------------------------ helpers
def f(v, d=1, sign=True, pctf=True):
    """Format a number for LaTeX (true minus sign)."""
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "--"
    x = v * 100 if pctf else v
    s = f"{abs(x):.{d}f}"
    if float(s) == 0:
        return s
    return ("$-$" if x < 0 else ("+" if sign else "")) + s


def fp(p):
    if p is None or (isinstance(p, float) and np.isnan(p)):
        return "--"
    return "$<$0.001" if p < 0.001 else (f"{p:.3f}" if p < 0.1 else f"{p:.2f}")


def stars(p):
    return "" if p is None else ("$^{***}$" if p < 0.01 else "$^{**}$" if p < 0.05 else "$^{*}$" if p < 0.10 else "")


def ci(c, d=0):
    return f"[{f(c[0], d)}, {f(c[1], d)}]" if c and c[0] is not None else "--"


def esc(s):
    return str(s).replace("&", r"\&").replace("%", r"\%").replace("$", r"\$").replace("_", r"\_").replace(">=", r"$\geq$").replace("<", r"$<$").replace(">", r"$>$")


def write(name, body):
    (TAB / f"{name}.tex").write_text(body)


def table(name, caption, label, colspec, header, rows, notes, size=r"\small", wide=False, fit=False):
    env = "table*" if wide else "table"
    body = [rf"\begin{{{env}}}[!htbp]\centering{size}", rf"\caption{{{caption}}}\label{{{label}}}", r"\resizebox{\linewidth}{!}{" if fit else "", r"\begin{threeparttable}",
            rf"\begin{{tabular}}{{{colspec}}}", r"\toprule", header + r" \\", r"\midrule"]
    body += rows
    body += [r"\bottomrule", r"\end{tabular}", r"\begin{tablenotes}[flushleft]\footnotesize", rf"\item \textit{{Notes:}} {notes}", r"\end{tablenotes}",
             r"\end{threeparttable}", "}" if fit else "", rf"\end{{{env}}}"]
    write(name, "\n".join(body) + "\n")


# ------------------------------------------------------------------ Table 1: sample
n = len(CO)
sec = CO.sector.value_counts()
rows = [rf"IPOs in sample & {n} \\", rf"Listing window & {CO.ipo_date.min()} to {CO.ipo_date.max()} \\",
        rf"Median market value at offer (\$bn) & {CO.cap_b.median():.1f} \\", rf"Median gross proceeds (\$m) & {CO.proceeds_m.median():,.0f} \\",
        rf"Median float (proceeds / market value) & {CO.float_pct.median()*100:.1f}\% \\",
        rf"Priced above first filed range & {(CO.demand=='Above range').sum()} of {CO.demand.notna().sum()} \\",
        rf"Upsized & {(CO.upsized==True).sum()} \\",
        rf"Median / mean first-day return & {f(CO.d1_pop.median())}\% / {f(CO.d1_pop.mean())}\% \\", r"\midrule",
        r"\multicolumn{2}{l}{\textit{Sector composition}} \\"] + [rf"\quad {esc(k)} & {v} \\" for k, v in sec.items()] + [r"\midrule",
        r"\multicolumn{2}{l}{\textit{Market value at offer}} \\"] + [rf"\quad {esc(k)} & {v} \\" for k, v in CO.bucket.value_counts().reindex(['Small <10B', 'Mid 10-30B', 'Large 30-100B', 'Mega >=100B']).items()]
table("t1_sample", "Sample description", "tab:sample", "lr", r"& Value", rows,
      "Hand-selected notable US IPOs priced between September 2020 and June 2026. Deal terms from SEC 424B4 prospectuses and pricing releases. "
      "Direct listings and the SK hynix ADR cross-listing are excluded from IPO-level statistics.")

# ------------------------------------------------------------------ Table 2: horizons
band = {r["d"]: r for r in ST["band"]}
rows = [rf"Offer to day-1 close (first-day return) & {n} & {f(CO.d1_pop.mean())} & {f(CO.d1_pop.median())} & {ci(ST['strategies'][0]['ci_median'])} & {(CO.d1_pop<0).mean()*100:.0f} & -- & -- \\"]
for h, col in [(5, "r5"), (21, "r21"), (63, "r63"), (126, "r126"), (252, "r252")]:
    x = CO[col].dropna(); b = band.get(h)
    rows.append(rf"Day-1 close to day {h} & {len(x)} & {f(x.mean())} & {f(x.median())} & {ci([b['lo'], b['hi']]) if b else '--'} & {(x<0).mean()*100:.0f} & {f(b['xmed']) if b else '--'} & {ci([b['xlo'], b['xhi']]) if b else '--'} \\")
table("t2_horizons", "Aftermarket returns by horizon", "tab:horizons", "lrrrcrrc",
      r"Window & $n$ & Mean & Median & 95\% CI (median) & \% $<0$ & Med.\ vs QQQ & 95\% CI", rows,
      "Returns in percent. Horizons are trading days counted from the first close (day 1). ``vs QQQ'' subtracts the QQQ return over the same dates. "
      "Confidence intervals are 10,000-draw bootstrap percentile intervals of the median.", wide=True, fit=True)

# ------------------------------------------------------------------ Table 3: day by day
rows = [rf"Day {r['day']} & {f(r['mean'],2)} & {ci(r['ci'],2)} & {f(r['median'],2)} & {r['hit']*100:.0f} & {fp(r['p_t'])}{stars(r['p_t'])} & {f(r['xmean'],2)} \\" for r in ST["daily"]]
table("t3_daily", "Close-to-close returns, days 2 to 10", "tab:daily", "lrcrrrr", r"Day & Mean & 95\% CI & Median & \% up & $p$ ($t$-test) & Mean vs QQQ", rows,
      "Percent. 43 IPOs. Stars: $^{*}p<0.10$, $^{**}p<0.05$, $^{***}p<0.01$ (unadjusted). With nine days tested, the day-6 result does not survive a Bonferroni or Benjamini--Hochberg correction.")


# ------------------------------------------------------------------ Table 4/5: buckets
def bucket_panel(title, grp, keys_label=None):
    g = ST["groups"][grp]
    out = [rf"\multicolumn{{7}}{{l}}{{\textit{{{title}}}}} \\"]
    for r in g["rows"]:
        out.append(rf"\quad {esc(keys_label.get(r['key'], r['key']) if keys_label else r['key'])} & {r['n']} & {f(r['pop'],0)} & {f(r['r21'],0)} & {f(r['r63'],0)} & {ci(r['r63_ci'])} & {f(r['r126'],0)} \\")
    k, q = g["kruskal"], g.get("kruskal_q", {})
    out.append(rf"\quad \footnotesize Kruskal--Wallis $p$ ($q$) & & \footnotesize {fp(k['d1_pop'])} ({fp(q.get('d1_pop'))}) & \footnotesize {fp(k['r21'])} ({fp(q.get('r21'))}) & \multicolumn{{2}}{{c}}{{\footnotesize {fp(k['r63'])} ({fp(q.get('r63'))})}} & \footnotesize {fp(k['r126'])} ({fp(q.get('r126'))}) \\")
    out.append(r"\addlinespace")
    return out


hdr = r"& $n$ & Pop & Day 21 & Day 63 & 95\% CI (day 63) & Day 126"
rows = bucket_panel("Panel A. Market value at offer", "Market cap") + bucket_panel("Panel B. Sector", "Sector") + bucket_panel("Panel C. Listing quarter", "Listing quarter")
table("t4_buckets", "Median returns by market value, sector and listing quarter", "tab:buckets", "lrrrrcr", hdr, rows,
      "Medians in percent. Pop is the first-day return from the offer; later columns are measured from the day-1 close. "
      "$q$ = Benjamini--Hochberg adjusted across all 28 bucket tests in Tables~\\ref{tab:buckets} and \\ref{tab:regimes}.", size=r"\footnotesize")
rows = bucket_panel("Panel A. 10-year yield, 3-month change before listing", "10Y trend") + bucket_panel("Panel B. VIX level at listing", "VIX") + \
       bucket_panel("Panel C. Float (proceeds / market value)", "Float %") + bucket_panel("Panel D. Final price vs first filed range", "Pricing vs range")
table("t5_regimes", "Median returns by macro regime and deal structure", "tab:regimes", "lrrrrcr", hdr, rows,
      "As Table~\\ref{tab:buckets}. 10Y rising/falling: more than $\\pm$30bp over the three months before listing. "
      "Demand proxy: offer price relative to the first filed range \\citep{hanley1993}; only 3 deals priced below range, so they are pooled with within-range deals.", size=r"\footnotesize")

# ------------------------------------------------------------------ Table 6: correlations
rows = [rf"{esc(c['label'])} & {c['n']} & {c['rho']:+.2f} & {fp(c['p'])} & {fp(c['q'])} \\".replace("+", "$+$").replace("-0.", "$-$0.") for c in ST["corr"]]
table("t6_corr", "Spearman rank correlations", "tab:corr", "lrrrr", r"Pair & $n$ & $\rho$ & $p$ & $q$ (BH)", rows,
      "Returns measured from the day-1 close unless stated. The squeeze test uses non-overlapping windows (days 1--5 vs days 5--63). $q$ adjusts across the 11 correlations.")

# ------------------------------------------------------------------ Table 7: intraday by opening pop
rows = []
for r in IN["by_open"] + [dict(IN["all"], key="All IPOs")]:
    rows.append(rf"{esc(r['key'])} & {r['n']} & {f(r['open_pop'],0)} & {f(r['d1_pop'],0)} & {f(r['oc1'])} & {f(r['close_vs_high'])} & {r['pct_below_open']*100:.0f} & {f(r['open_to_D21'])} & {f(r['open_to_D63'])} \\")
rows.insert(-1, r"\midrule")
table("t7_intraday", "Debut-day shape by size of the opening print", "tab:intraday", "lrrrrrrrr",
      r"Opening print vs offer & $n$ & Open & Close & Open$\to$close & Close vs high & \% below open & Open$\to$D21 & Open$\to$D63", rows,
      "Medians in percent from daily open, high and close. The last two columns measure returns from the opening price, the entry available to a buyer without an allocation.", wide=True, fit=True)

# hourly profile table
pr = IN["hourly"]["profile"]
def hp(day, hr, key):
    r = next((x for x in pr[str(day)] if x["hr"] == hr), None)
    if not r or (day == 1 and r["n"] < 4):
        return "--"
    return f"{r[key]*100:.0f}" if key == "vol" else f(r[key], 1)
rows = [rf"{h}:30 & {hp(1,h,'vol')} & {hp(2,h,'vol')} & {hp(3,h,'vol')} & {hp(1,h,'bar_ret')} & {hp(2,h,'bar_ret')} & {hp(3,h,'bar_ret')} \\" for h in range(9, 16)]
fh = IN["hourly"]["first_hour"]
table("t8_hourly", "Hourly profile of the first three sessions", "tab:hourly", "lrrrrrr",
      r"Bar (ET) & \multicolumn{3}{c}{Share of day's volume (\%)} & \multicolumn{3}{c}{Median bar return (\%)} \\ \cmidrule(lr){2-4}\cmidrule(lr){5-7} & Day 1 & Day 2 & Day 3 & Day 1 & Day 2 & Day 3", rows,
      f"{IN['hourly']['n_ipos']} IPOs since January 2025 whose hourly feed includes the debut session. Day-1 bars with fewer than four IPOs trading are omitted (most debuts open between 11:30 and 13:30 ET). "
      f"The debut-day high fell in the first trading hour for {fh['hi_first']} of {fh['n']} IPOs.")

# ------------------------------------------------------------------ Table 9/10: strategies
rows = []
for s in ST["strategies"]:
    rows.append(rf"{esc(s['name'])} & {s['n']} & {f(s['mean'])} & {ci(s['ci_mean'])} & {f(s['median'])} & {s['hit']*100:.0f} & {fp(s['p_t'])} & {fp(s['p_wilcoxon'])} & {s['sr_trade']:.2f} & {s['sr_ann_equiv']:.2f} & {s['sr_realistic']:.2f} & {s['confidence']} \\".replace("& -", "& $-$"))
rows.insert(8, r"\midrule")
table("t9_strategies", "Trading strategies on the IPO stock: returns, significance and implied Sharpe ratios", "tab:strategies", "lrrcrrrrrrrl",
      r"Strategy & $n$ & Mean & 95\% CI & Median & Hit & $p_t$ & $p_W$ & SR$_\text{trade}$ & SR$_\text{ann}$ & SR$_\text{real}$ & Conf.", rows,
      "Percent per trade; short trades report the short-seller's return. $p_t$: one-sample $t$-test; $p_W$: Wilcoxon signed-rank. SR$_\\text{trade}$ = mean/sd per trade; "
      "SR$_\\text{ann}$ = SR$_\\text{trade}\\sqrt{252/h}$ for holding period $h$ (an upper bound); SR$_\\text{real}$ = SR$_\\text{trade}\\sqrt{7.5}$, the number of cohort IPOs per year. "
      "Confidence: High if the CI excludes zero and $p_W<0.05$; Medium if $\\min(p_t,p_W)<0.10$; otherwise Low. Lower block subtracts QQQ.", size=r"\scriptsize", wide=True, fit=True)
rows = []
for k, g in ST["subsets"].items():
    rows.append(rf"\multicolumn{{7}}{{l}}{{\textit{{{esc(k)}}} ($n={g['n']}$)}} \\")
    for s in g["rows"]:
        rows.append(rf"\quad {esc(s['name'])} & {f(s['mean'])} & {ci(s['ci_mean'])} & {s['hit']*100:.0f} & {fp(s['p_wilcoxon'])} & {s['sr_trade']:.2f} & {s['confidence']} \\".replace("& -", "& $-$"))
table("t10_subsets", "Strategies on the subsets closest to Anthropic", "tab:subsets", "lrcrrrl", r"Subset / trade & Mean & 95\% CI & Hit & $p_W$ & SR$_\text{trade}$ & Conf.", rows,
      "As Table~\\ref{tab:strategies}. Anthropic is a large, low-float software/AI listing pricing into a rising-yield market; whether it prices above range is known only on 18 November.", size=r"\footnotesize")

# ------------------------------------------------------------------ Table 11/12/13: cross-asset
W4 = ["pre", "day0", "post", "late"]
def xf(a, v):
    return f(v, 1, pctf=not ("VIX" in a or "10Y" in a)) if "10Y" not in a else f(v, 1, pctf=False)
rows = []
for a, r in XA["daily"].items():
    rows.append(esc(a) + " & " + " & ".join(xf(a, r[w]["mean"]) + stars(r[w]["p_perm"]) for w in W4) + " & " + xf(a, r["post"]["median"]) + " & " + f"{min(r[w]['q'] for w in W4):.2f}" + r" \\")
table("t11_xasset", "Cross-asset moves around 11 large US listings", "tab:xasset", "lrrrrrr",
      r"Asset & T$-$10 to T$-$1 & Listing day & T+1 to T+5 & T+6 to T+20 & Median T+1--5 & min $q$", rows,
      "Average across events; percent except VIX (points) and US 10Y (basis points). Stars from a permutation test against 10,000 draws of 11 random dates since mid-2020 "
      "($^{*}p<0.10$, $^{**}p<0.05$). min $q$ is the smallest Benjamini--Hochberg $q$ across the asset's four windows (56 tests in total); none is below 0.30.", size=r"\footnotesize")
rows = [rf"{esc(t['asset'])} & {esc(t['trade'])} & {f(t['mean'])} & {f(t['excess_vs_typical'])} & {t['hit']*100:.0f} & {fp(t['p_perm'])} & {t['sr_trade']:.2f} & {t['sr_realistic']:.2f} \\".replace("& -", "& $-$") for t in XA["trades"]]
table("t12_xtrades", "Cross-asset trades around large listings", "tab:xtrades", "llrrrrrr", r"Asset & Trade & Mean & vs typical & Hit & $p$ & SR$_\text{event}$ & SR$_\text{real}$", rows,
      "Percent per event, 11 events. ``vs typical'' subtracts the average of all same-length windows. SR$_\\text{real}$ scales by $\\sqrt{1.8}$ listings per year.", size=r"\scriptsize")
sx = next(r for r in XA["hourly"] if r["ticker"] == "SPCX")
rows = []
for a, s in XA["hourly_summary"].items():
    b, al = s["big"], s["all"]
    rows.append(rf"{esc(a)} & {b['mean_abn']*1e4:+.0f} & {b['hit_neg']*100:.0f}\% & {b['t']:+.1f} & {al['mean_abn']*1e4:+.0f} & {al['hit_neg']*100:.0f}\% & {sx[a]['abn']*1e4:+.0f} \\".replace("+", "$+$").replace("-", "$-$"))
table("t13_hour", "Abnormal return of other assets in the hour an IPO opens", "tab:hour", "lrrrrrr",
      r"Asset & \multicolumn{3}{c}{Large deals ($n=4$)} & \multicolumn{2}{c}{All ($n=14$)} & SpaceX \\ \cmidrule(lr){2-4}\cmidrule(lr){5-6} & bp & \% down & $t$ & bp & \% down & bp", rows,
      "Return in the IPO's first trading hour minus the average of the same clock hour over the prior 20 sessions, in basis points. Large deals: proceeds of \\$1.4bn or more (CoreWeave, Medline, SpaceX, Venture Global).")

# ------------------------------------------------------------------ Table 14/15: Anthropic
rows = [rf"{esc(r['asset'])} & {xf(r['asset'], r['value'])} & {r['pct_rank']*100:.0f} & {r['z']:+.2f} \\".replace("+", "$+$").replace("-", "$-$") for r in XA["runup"]]
table("t14_runup", "How unusual is the run-up to Anthropic?", "tab:runup", "lrrr", r"Asset & 14-session move & Percentile & $z$", rows,
      "Move over the 14 sessions to 13 November 2026, ranked against every 14-session window since mid-2020.", size=r"\footnotesize")
hot = next(r for r in ST["groups"]["Pricing vs range"]["rows"] if r["key"].startswith("Priced above"))
cold = next(r for r in ST["groups"]["Pricing vs range"]["rows"] if r["key"].startswith("At or below"))
fs = ST["subsets"]["Priced above initial range"]["rows"][2]
rows = [rf"Above \$78 (above range) & {hot['n']} & {f(hot['pop'],0)} & {f(hot['r21'],0)} & {f(hot['r63'],0)} & {f(hot['r126'],0)} & Fade day 5$\to$63: {f(fs['mean'])}\%, hit {fs['hit']*100:.0f}\%, $p_W={fp(fs['p_wilcoxon'])}$ \\",
        rf"\$70--78 or below & {cold['n']} & {f(cold['pop'],0)} & {f(cold['r21'],0)} & {f(cold['r63'],0)} & {f(cold['r126'],0)} & No reliable fade \\"]
table("t15_tree", "Conditional outlook by Anthropic's pricing", "tab:tree", "lrrrrrp{5.2cm}", r"Anthropic prices\ldots & $n$ & Pop & D21 & D63 & D126 & Historical edge (no allocation)", rows,
      "Cohort medians in percent for the two demand groups. Anthropic's range is \\$70--78 for 825 million shares.", size=r"\footnotesize", wide=True)
rows = [rf"{esc(c['label'])} & {('T$-$1' if c['day'] < 0 else 'Day ' + str(c['day'] + 1))} & {c['date']} \\" for c in AD["ant_cal"]]
table("t16_cal", "Anthropic event calendar", "tab:cal", "llr", r"Event & Trading day & Date", rows,
      "Day 1 = first close (19 November 2026). NYSE holidays applied (Thanksgiving, Christmas, New Year, MLK, Presidents' Day, Good Friday). SpaceX's 8 December lock-up expiry is Anthropic's day 13.")

# ------------------------------------------------------------------ Appendix tables
rows = []
for _, r in CO.sort_values("ipo_date").iterrows():
    rows.append(rf"{esc(r['name'])} & {r.ticker} & {r.ipo_date} & {esc(r.sector.split(',')[0].split(' &')[0])} & {r.offer:g} & {r.cap_b:,.1f} & {r.proceeds_m:,.0f} & {r.float_pct*100:.1f} & {esc(str(r.demand).replace(' range','')) if isinstance(r.demand, str) else '--'} & {f(r.d1_pop,0)} & {f(r.r21,0)} & {f(r.r63,0)} \\")
lt = [r"\begin{scriptsize}\setlength{\tabcolsep}{2.6pt}", r"\begin{longtable}{llllrrrrlrrr}", r"\caption{The IPO cohort}\label{tab:cohort}\\", r"\toprule",
      r"Company & Ticker & Listed & Sector & Offer & Cap \$bn & Proceeds \$m & Float \% & vs range & Pop & D21 & D63 \\", r"\midrule", r"\endfirsthead",
      r"\toprule Company & Ticker & Listed & Sector & Offer & Cap \$bn & Proceeds \$m & Float \% & vs range & Pop & D21 & D63 \\ \midrule", r"\endhead",
      r"\bottomrule \multicolumn{12}{l}{\scriptsize Returns in percent; D21/D63 from the day-1 close. Sources: SEC 424B4, company pricing releases, Yahoo Finance.} \\ \endlastfoot"] + rows + [r"\end{longtable}", r"\end{scriptsize}"]
write("a1_cohort", "\n".join(lt) + "\n")
rows = [rf"{e['date']} & {esc(e['name'])} & {e['deal_b']:g} \\" for e in XA["events"]]
table("a2_events", "Large-listing events used in the cross-asset study", "tab:events", "llr", r"Listing date & Company & Proceeds (\$bn)", rows,
      "DoorDash and Airbnb listed one day apart and are treated as one event. SK hynix is a cross-listing of an already-public company.")

# ================================================================== FIGURES
# F1: path with CI band
b = ST["band"]; d = [r["d"] for r in b]
fig, ax = plt.subplots(figsize=(6.6, 3.0))
ax.fill_between(d, [100 + r["lo"] * 100 for r in b], [100 + r["hi"] * 100 for r in b], color=B1, alpha=0.14, lw=0, label="95% CI (median)")
ax.plot(d, [100 + r["med"] * 100 for r in b], color=B1, label="Median IPO")
ax.plot(d, [100 + r["xmed"] * 100 for r in b], color=O2, label="Median IPO minus QQQ")
sp = AD["bucket_paths"]["SpaceX"]; ax.plot(range(1, len(sp) + 1), sp, color=INK, lw=1.2, label="SpaceX")
ax.axhline(100, color="#c3c2b7", lw=0.8); ax.axvline(126, color=MUT, lw=0.8, ls=":"); ax.text(128, 128, "day 126 (lock-up)", color=MUT, fontsize=7)
ax.set_xlim(1, 252); ax.set_ylim(50, 135); ax.set_xlabel("Trading days since IPO"); ax.set_ylabel("Index, day-1 close = 100")
ax.set_xticks([1, 21, 63, 126, 189, 252]); ax.legend(ncol=4, fontsize=7.5, loc="upper center", bbox_to_anchor=(0.5, 1.13))
fig.savefig(FIG / "f1_path.pdf"); plt.close(fig)

# F2: sector small multiples
fig, axs = plt.subplots(2, 3, figsize=(6.6, 3.6), sharex=True, sharey=True)
for ax, s in zip(axs.flat, AD["sector"]):
    k = s["key"]; v = AD["sector_paths"][k]
    ax.plot(range(1, 254), [np.nan if x is None else x for x in AD["all_path"]], color=MUT, lw=1)
    ax.plot(range(1, 254), [np.nan if x is None else x for x in v], color=B1, lw=1.6)
    ax.axhline(100, color="#c3c2b7", lw=0.7); ax.set_title(f"{k} (n={s['n']})", fontsize=7.5); ax.set_ylim(40, 170); ax.set_xticks([1, 63, 126, 252])
fig.supxlabel("Trading days since IPO", fontsize=8); fig.supylabel("Day-1 close = 100", fontsize=8)
fig.tight_layout(); fig.savefig(FIG / "f2_sectors.pdf"); plt.close(fig)

# F3: revision vs pop + demand medians
fig, axs = plt.subplots(1, 2, figsize=(6.6, 2.8), gridspec_kw={"width_ratios": [1.15, 1]})
ax = axs[0]; c = CO.dropna(subset=["revision_pct"])
ax.scatter(c.revision_pct * 100, c.d1_pop * 100, s=22, c=[B1 if x >= 0 else RED for x in c.r63.fillna(0)], edgecolors="white", linewidths=0.8, zorder=3)
z = np.polyfit(c.revision_pct * 100, c.d1_pop * 100, 1); xx = np.linspace(-45, 60, 10); ax.plot(xx, np.polyval(z, xx), color=MUT, lw=1, ls="--")
ax.set_xlabel("Offer vs midpoint of first filed range (%)"); ax.set_ylabel("First-day return (%)"); ax.set_title("(a) Demand and the pop", fontsize=8, loc="left")
ax.text(-44, 140, "blue: up by day 63\nred: down by day 63", fontsize=6.5, color="#52514e")
ax = axs[1]; labs = ["Pop", "Day 21", "Day 63", "Day 126"]; ks = ["pop", "r21", "r63", "r126"]; x = np.arange(4)
for j, (r, col, lab) in enumerate([(hot, O2, "Above range"), (cold, B1, "At/below range")]):
    m = [r[k] * 100 for k in ks]; lo = [r[k + "_ci"][0] * 100 for k in ks]; hi = [r[k + "_ci"][1] * 100 for k in ks]
    xs = x + (j - 0.5) * 0.28
    ax.errorbar(xs, m, yerr=[np.subtract(m, lo), np.subtract(hi, m)], fmt="o", color=col, ms=4.5, capsize=2.5, lw=1.4, label=f"{lab} (n={r['n']})")
ax.axhline(0, color="#c3c2b7", lw=0.8); ax.set_xticks(x, labs); ax.set_ylabel("Median (%), 95% CI"); ax.legend(fontsize=7, loc="upper right")
ax.set_title("(b) Hot deals give it back", fontsize=8, loc="left")
fig.tight_layout(); fig.savefig(FIG / "f3_demand.pdf"); plt.close(fig)

# F4: intraday 2x2
fig, axs = plt.subplots(2, 2, figsize=(6.6, 4.8))
ax = axs[0, 0]; dd = pd.DataFrame(IN["daily"])
ax.scatter(dd.open_pop * 100, dd.oc1 * 100, s=18, c=[B1 if v >= 0 else RED for v in dd.oc1], edgecolors="white", linewidths=0.7, zorder=3)
ax.axhline(0, color="#c3c2b7", lw=0.8); ax.set_xlabel("Opening print vs offer (%)"); ax.set_ylabel("Open to close (%)"); ax.set_title("(a) Opening pop vs rest of day 1", fontsize=8, loc="left")
spx = IN["hourly"]["spacex"]; ax = axs[0, 1]
ax.plot(range(len(spx)), [(r["c"] - 1) * 100 for r in spx], color=INK, lw=1.4)
bounds = [i for i in range(1, len(spx)) if spx[i]["ts"][:5] != spx[i - 1]["ts"][:5]]
for i in bounds: ax.axvline(i - 0.5, color=MUT, lw=0.6, ls=":")
ax.set_xticks([0] + bounds, [f"D{k+1}" for k in range(len(bounds) + 1)]); ax.set_ylabel("% above $135 offer"); ax.set_title("(b) SpaceX hourly, first five sessions", fontsize=8, loc="left")
for k, (ax, key, ttl) in enumerate([(axs[1, 0], "vol", "(c) Share of day's volume by hour"), (axs[1, 1], "bar_ret", "(d) Median hourly bar return")]):
    hrs = np.arange(9, 16)
    for j, (day, col) in enumerate([(1, B1), (2, O2), (3, A3)]):
        vals = []
        for h in hrs:
            r = next((x for x in pr[str(day)] if x["hr"] == h), None)
            vals.append(np.nan if (r is None or (day == 1 and r["n"] < 4)) else r[key] * 100)
        ax.bar(hrs + (j - 1) * 0.27, vals, width=0.25, color=col, label=f"Day {day}")
    ax.axhline(0, color="#c3c2b7", lw=0.8); ax.set_xticks(hrs, [f"{h}:30" for h in hrs], fontsize=6.5); ax.set_title(ttl, fontsize=8, loc="left"); ax.legend(fontsize=6.5)
    ax.set_ylabel("%")
fig.tight_layout(); fig.savefig(FIG / "f4_intraday.pdf"); plt.close(fig)

# F5: forest of strategies
S = ST["strategies"]; colmap = {"High": "#0ca30c", "Medium": Y4, "Low": MUT}
fig, ax = plt.subplots(figsize=(6.6, 3.4)); ys = np.arange(len(S))[::-1]
for y, s in zip(ys, S):
    ax.plot([s["ci_mean"][0] * 100, s["ci_mean"][1] * 100], [y, y], color=colmap[s["confidence"]], lw=2, solid_capstyle="round")
    ax.plot(s["mean"] * 100, y, "o", color=colmap[s["confidence"]], ms=5.5, mec="white", mew=1)
ax.axvline(0, color="#c3c2b7", lw=0.9); ax.set_yticks(ys, [s["name"] for s in S], fontsize=7); ax.set_xlabel("Mean return per trade (%), 95% bootstrap CI")
for k, c in colmap.items(): ax.plot([], [], "o", color=c, label=k)
ax.legend(title="Confidence", fontsize=7, title_fontsize=7, loc="lower right"); ax.grid(axis="y", visible=False)
fig.savefig(FIG / "f5_forest.pdf"); plt.close(fig)

# F6: cross-asset event paths 2x4
names = ["Nasdaq 100 (QQQ)", "S&P 500 (SPY)", "Small caps (IWM)", "Speculative growth (ARKK)", "Software (IGV)", "Bitcoin", "Gold (GLD)", "VIX (points)"]
fig, axs = plt.subplots(2, 4, figsize=(6.8, 3.6), sharex=True)
for ax, a in zip(axs.flat, names):
    p = XA["paths"][a]; k = 1 if "VIX" in a else 100; t = [r["t"] for r in p["band"]]
    ax.fill_between(t, [r["lo"] * k for r in p["band"]], [r["hi"] * k for r in p["band"]], color=B1, alpha=0.15, lw=0)
    ax.plot(t, [r["mean"] * k for r in p["band"]], color=B1, lw=1.4); ax.plot(t, [np.nan if v is None else v * k for v in p["spacex"]], color=INK, lw=0.9)
    ax.axvline(0, color=MUT, lw=0.6, ls=":"); ax.axhline(0, color="#c3c2b7", lw=0.6); ax.set_title(a.replace(" (points)", " (pts)"), fontsize=7); ax.tick_params(labelsize=6.5)
fig.supxlabel("Sessions relative to listing (T0)", fontsize=8); fig.supylabel("Cumulative move (%; VIX in points)", fontsize=8)
fig.tight_layout(); fig.savefig(FIG / "f6_xasset.pdf"); plt.close(fig)

# F7: run-up percentile
R = [r for r in XA["runup"] if "IPO ETF" not in r["asset"]]
fig, ax = plt.subplots(figsize=(6.0, 3.0)); ys = np.arange(len(R))[::-1]
ax.barh(ys, [(r["pct_rank"] - 0.5) * 100 for r in R], color=[RED if r["pct_rank"] < 0.5 else B1 for r in R], height=0.6)
ax.set_yticks(ys, [r["asset"] for r in R], fontsize=7); ax.set_xlim(-50, 50); ax.set_xticks([-50, -25, 0, 25, 50], ["0th", "25th", "50th", "75th", "100th"])
ax.set_xlabel("Percentile rank of the 14-session move to 13 Nov 2026"); ax.axvline(0, color="#c3c2b7", lw=0.9); ax.grid(axis="y", visible=False)
fig.savefig(FIG / "f7_runup.pdf"); plt.close(fig)

# F8: seasonality
fig, axs = plt.subplots(1, 2, figsize=(6.6, 2.5))
q = AD["quarter"]; x = np.arange(len(q))
for j, (k, col, lab) in enumerate([("pop", B1, "Pop"), ("r63", O2, "Day 63"), ("r126", A3, "Day 126")]):
    axs[0].bar(x + (j - 1) * 0.26, [r[k] * 100 for r in q], width=0.24, color=col, label=lab)
axs[0].set_xticks(x, [r["key"] for r in q]); axs[0].axhline(0, color="#c3c2b7", lw=0.8); axs[0].legend(fontsize=6.5); axs[0].set_ylabel("Median (%)"); axs[0].set_title("(a) IPOs by listing quarter", fontsize=8, loc="left")
m = AD["spx_month"]; axs[1].bar(range(12), [r["mean"] for r in m], color=[B1 if i in (10, 11) else "#c3c2b7" for i in range(12)])
axs[1].set_xticks(range(12), list("JFMAMJJASOND")); axs[1].set_ylabel("Avg monthly return (%)"); axs[1].set_title("(b) S&P 500 by month, 1950--2025", fontsize=8, loc="left")
fig.tight_layout(); fig.savefig(FIG / "f8_season.pdf"); plt.close(fig)
print("figures:", sorted(p.name for p in FIG.glob("*.pdf")))
print("tables:", sorted(p.name for p in TAB.glob("*.tex")))
