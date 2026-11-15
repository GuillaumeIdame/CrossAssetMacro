"""Tables and figures for "Sympathy or Substitution?" (paper 4). Run after beta_trade.py."""
import json
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
import pandas as pd

HERE = Path(__file__).parent; DATA = HERE.parent / "data"; TAB, FIG = HERE / "tables", HERE / "figures"
D = json.loads((DATA / "beta.json").read_text()); MAP = json.loads((DATA / "raw/beta/map.json").read_text())
SG = pd.DataFrame(json.loads((DATA / "signals.json").read_text())["cohort"]).set_index("ticker")
B1, O2, A3, RED, INK, MUT, GRID, PUR = "#2a78d6", "#eb6834", "#1baf7a", "#e34948", "#0b0b0b", "#898781", "#e1e0d9", "#7b5ea7"
plt.rcParams.update({"font.family": "serif", "font.serif": ["DejaVu Serif"], "font.size": 8.5, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.edgecolor": "#c3c2b7", "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6, "legend.frameon": False, "savefig.bbox": "tight", "pdf.fonttype": 42})

def f(v, d=1):
    if v is None or (isinstance(v, float) and np.isnan(v)): return "--"
    s = f"{abs(v*100):.{d}f}"; return s if float(s) == 0 else ("$-$" if v < 0 else "+") + s
def num(v, d=2):
    if v is None or (isinstance(v, float) and np.isnan(v)): return "--"
    s = f"{abs(v):.{d}f}"; return ("$-$" if v < 0 and float(s) != 0 else "") + s
def fp(p): return "--" if p is None else ("$<$0.001" if p < 0.001 else (f"{p:.3f}" if p < 0.1 else f"{p:.2f}"))
def table(name, caption, label, colspec, header, rows, notes, size=r"\footnotesize", fit=False):
    body = [r"\begin{table}[!htbp]\centering" + size, rf"\caption{{{caption}}}\label{{{label}}}", r"\resizebox{\linewidth}{!}{" if fit else "", r"\begin{threeparttable}",
            rf"\begin{{tabular}}{{{colspec}}}", r"\toprule", header + r" \\", r"\midrule"] + rows + [r"\bottomrule", r"\end{tabular}",
            r"\begin{tablenotes}[flushleft]\footnotesize", rf"\item \textit{{Notes:}} {notes}", r"\end{tablenotes}", r"\end{threeparttable}", "}" if fit else "", r"\end{table}"]
    (TAB / f"{name}.tex").write_text("\n".join(body) + "\n")
def srow(lab, s):
    if s.get("n", 0) < 3: return rf"{lab} & {s.get('n',0)} & -- & -- & -- & -- & -- \\"
    return rf"{lab} & {s['n']} & {f(s['mean'])} & {f(s['median'])} & [{f(s['ci'][0])}, {f(s['ci'][1])}] & {fp(s['t_p'])} & {s['pos']*100:.0f}\% \\"

WL = {"pre20": "Days $-20$ to $-1$", "run10": "Days $-10$ to $-1$ (roadshow)", "run5": "Days $-5$ to $-1$", "d0": "Day 0 (first trade)", "d0_oc": "Day 0, open to close",
      "d1_5": "Days 1 to 5", "d1_21": "Days 1 to 21", "d1_63": "Days 1 to 63"}
E = D["event"]; R = D["robust"]
rows = [r"\multicolumn{7}{l}{\textit{Comparable listed companies (equal-weight basket per IPO)}} \\"] + [srow(r"\quad " + l, E["peer"][w]) for w, l in WL.items()]
rows += [r"\multicolumn{7}{l}{\textit{Listed stakeholders (Amazon, Ford, Shopify, Nvidia, Coinbase, Google, DXYZ)}} \\"] + [srow(r"\quad " + l, E["holder"][w]) for w, l in WL.items() if w in ("run10", "d0", "d1_5", "d1_21")]
rows += [r"\midrule", rf"\multicolumn{{7}}{{l}}{{Placebo percentile of the actual mean (400 random event dates): day 0 {R['placebo']['d0']['pct']*100:.0f}\%, days 1--21 {R['placebo']['d1_21']['pct']*100:.0f}\%, days 1--63 {R['placebo']['d1_63']['pct']*100:.0f}\%}} \\"]
table("b1_event", "How related stocks trade around an IPO: abnormal returns against Nasdaq-100", "tab:b1", "lrrrrrr", r"Window & $n$ & Mean & Median & 95\% CI & $p$ & Share $>0$", rows,
      f"Percent. Abnormal return = stock return minus a market model on QQQ estimated over days $-260$ to $-21$. {E['n_peers']} peer--IPO pairs ({len(set(r['peer'] for r in D['peer_rows'] if r['kind'] == 'peer'))} distinct stocks) across {E['n_ipos']} IPOs; one basket per IPO. CI by bootstrap, $p$ from a $t$-test across IPO baskets. Placebo: the same peers on random dates within $\\pm$1 year, using full-sample market models.", fit=True)

G = D["groups"]; rows = []
for g in ["Hot", "Not hot", "Pop > 30%", "Pop <= 30%"]:
    rows.append(rf"{g.replace('%', r'\%').replace('<=', r'$\le$').replace('>', '$>$')} & {G[g]['d0']['n']} & {f(G[g]['run10']['mean'])} & {f(G[g]['d0']['mean'])} & {f(G[g]['d1_5']['mean'])} & {f(G[g]['d1_21']['mean'])} & {f(G[g]['d1_63']['mean'])} \\")
rows.append(rf"Mann--Whitney $p$, hot vs not & & {fp(G['MW_p']['run10'])} & {fp(G['MW_p']['d0'])} & {fp(G['MW_p']['d1_5'])} & {fp(G['MW_p']['d1_21'])} & {fp(G['MW_p']['d1_63'])} \\")
rows.append(r"\midrule")
for k, lab in [("only2021", "2021 IPOs only"), ("ex2021", "Excluding 2021"), ("since2023", "IPOs since 2023")]:
    rows.append(rf"{lab} & {R[k]['d0']['n']} & -- & {f(R[k]['d0']['mean'])} & -- & {f(R[k]['d1_21']['mean'])} ($p$={fp(R[k]['d1_21']['t_p'])}) & {f(R[k]['d1_63']['mean'])} ($p$={fp(R[k]['d1_63']['t_p'])}) \\")
table("b2_groups", "Peer abnormal returns by IPO demand and by vintage", "tab:b2", "lrrrrrr", r"Group & $n$ & Days $-10$ to $-1$ & Day 0 & Days 1--5 & Days 1--21 & Days 1--63", rows,
      "Mean peer-basket abnormal return, percent. Hot = range raised and priced above it.", fit=True)

XL = {("d0", "open_pop"): "Peers day 0 vs IPO opening pop", ("d0", "pop"): "Peers day 0 vs IPO first-day return", ("d0", "oc1"): "Peers day 0 vs IPO open-to-close",
      ("d1_5", "ipo_d1_5"): "Peers days 1--5 vs IPO days 1--5", ("d1_21", "ipo_d1_21"): "Peers days 1--21 vs IPO days 1--21", ("d1_63", "ipo_d1_63"): "Peers days 1--63 vs IPO days 1--63",
      ("run10", "pop"): "Peers roadshow run-up vs IPO first-day return", ("d1_63", "pop"): "Peers days 1--63 vs IPO first-day return"}
rows = [rf"{XL[(x['peer'], x['ipo'])]} & {num(x['rho'])} & {fp(x['p'])} & {x['n']} \\" for x in D["xs"]]
table("b3_xs", "Does a bigger debut move peers more? Cross-section of 43 IPOs", "tab:b3", "lrrr", r"Pair & Spearman $\rho$ & $p$ & $n$", rows,
      "Peer returns are basket abnormal returns; IPO returns are raw. Only the 63-day co-movement is significant: IPO and peers fade together over a quarter, but the size of the debut does not move peers on the day.")

C = D["comove"]; rows = []
for c, lab in [("corr", "Correlation, IPO vs peer basket"), ("bq", "Beta to QQQ"), ("bt", "Beta to the theme (peer basket ex-QQQ)"), ("vol", "Volatility, IPO / peer basket"), ("r2", "$R^2$ (QQQ + theme)"), ("bbq", "Peer basket beta to QQQ")]:
    rows.append(rf"{lab} & {num(C[c+'_early']['median'])} & {num(C[c+'_mid']['median'])} & {num(C[c+'_seasoned']['median'])} \\")
rows += [r"\midrule", rf"Wilcoxon $p$, days 1--21 vs 64--190: correlation {fp(C['paired_corr_early_vs_seasoned_p'])}; theme beta {fp(C['paired_bt_early_vs_seasoned_p'])} & & & \\"]
LL = D["leadlag_daily"]
rows += [r"\midrule", r"\multicolumn{4}{l}{\textit{Pooled daily panel, days 1--21, excess returns over QQQ, clustered by IPO}} \\",
         rf"Peers today on IPO today & {num(LL['same_day']['coef'],3)} & $t$={num(LL['same_day']['t'],1)} & $n$={LL['same_day']['n']} \\",
         rf"Peers tomorrow on IPO today & {num(LL['ipo_leads']['coef'],3)} & $t$={num(LL['ipo_leads']['t'],1)} & \\",
         rf"IPO tomorrow on peers today & {num(LL['peers_lead']['coef'],3)} & $t$={num(LL['peers_lead']['t'],1)} & \\"]
table("b4_comove", "Daily co-movement: new issues trade on their own at first", "tab:b4", "lrrr", r"Median across IPOs & Days 1--21 & Days 22--63 & Days 64--190", rows,
      "Daily returns. Theme beta from a regression of the IPO's return on QQQ and on the peer basket orthogonalised to QQQ.", fit=True)

HW = D["hourly"]["by_window"]; PO = D["hourly"]["pooled"]; HL = D["hourly"]["leadlag"]
rows = [rf"Correlation, IPO vs peers (excess of QQQ) & {num(HW['d1_5']['corr']['median'])} & {num(HW['d6_21']['corr']['median'])} & {num(HW['d22_63']['corr']['median'])} \\",
        rf"Beta of peers on the IPO & {num(HW['d1_5']['beta_b_on_y']['median'],3)} & {num(HW['d6_21']['beta_b_on_y']['median'],3)} & {num(HW['d22_63']['beta_b_on_y']['median'],3)} \\",
        rf"Beta of the IPO on peers & {num(HW['d1_5']['beta_y_on_b']['median'])} & {num(HW['d6_21']['beta_y_on_b']['median'])} & {num(HW['d22_63']['beta_y_on_b']['median'])} \\",
        r"\midrule", r"\multicolumn{4}{l}{\textit{Pooled hourly panel, days 1--63, clustered by IPO}} \\",
        rf"Peers on IPO, same hour, days 6--63 & {num(PO['yx']['coef'],3)} & $t$={num(PO['yx']['t'],1)} & $n$={PO['n']} \\",
        rf"\quad extra in days 1--5 & {num(PO['yx:early']['coef'],3)} & $t$={num(PO['yx:early']['t'],1)} & \\",
        rf"Peers next hour on IPO, days 1--5 / later & {num(HL['ipo_leads_1h_early']['coef'],3)} / {num(HL['ipo_leads_1h_later']['coef'],3)} & $t$={num(HL['ipo_leads_1h_early']['t'],1)} / {num(HL['ipo_leads_1h_later']['t'],1)} & \\",
        rf"IPO next hour on peers, days 1--5 / later & {num(HL['peers_lead_1h_early']['coef'],2)} / {num(HL['peers_lead_1h_later']['coef'],2)} & $t$={num(HL['peers_lead_1h_early']['t'],1)} / {num(HL['peers_lead_1h_later']['t'],1)} & \\"]
table("b5_hourly", "Intraday: is there a beta trade from the IPO to its peers?", "tab:b5", "lrrr", r"Median across 14 IPOs & Days 1--5 & Days 6--21 & Days 22--63", rows,
      "60-minute bars, excess of QQQ, overnight gaps excluded. IPOs listed since January 2025: Venture Global, SailPoint, CoreWeave, Hinge Health, Circle, Chime, Figma, Klarna, Figure, Gemini, StubHub, Netskope, Medline, SpaceX.", fit=True)

D1 = pd.DataFrame(D["hourly"]["day1"]); rows = []
for r in D1.itertuples():
    rows.append(rf"{SG.loc[r.ipo,'name']} & {r.first_print} & {', '.join(r.peers)} & {f(r.pre)} ({num(r.pre_z,1)}) & {f(r.post)} ({num(r.post_z,1)}) & {f(r.ipo_oc)} & {f(r.pop,0)} \\")
S1 = D["hourly"]["day1_summary"]
rows += [r"\midrule", rf"Mean & & & {f(S1['pre']['mean'])} ($p$={fp(S1['pre']['t_p'])}) & {f(S1['post']['mean'])} ($p$={fp(S1['post']['t_p'])}) & & \\"]
table("b6_day1", "Day 1 on the clock: peers before and after the IPO's first print", "tab:b6", "lllrrrr",
      r"IPO & First print (ET) & Peers / stakeholders & Peers: close$\to$first print & Peers: first print$\to$close & IPO open$\to$close & Pop", rows,
      "Peer basket return minus QQQ over the same clock window, percent; in brackets a $z$-score against the same clock window on the 20 previous sessions. First print = the hourly bar containing the IPO's opening trade.", size=r"\scriptsize", fit=True)

A = D["anthropic"]; RK = D["ant_rank"]; rows = []
for t in ["NBIS", "CRWV", "NVDA", "AVGO", "ORCL", "PLTR", "MSFT", "AMZN", "GOOGL", "SMH", "IGV", "ARKK", "QQQ"]:
    a = A[t]; rk = f"{RK[t]*100:.0f}" if t in RK else "--"
    rows.append(rf"{t} & {a['kind']} & {num(a['beta'],1)} & {f(a['raw_since_sep30'])} & {f(a['raw_since_s1'])} & {f(a['raw_roadshow'])} & {f(a['car20'])} & {rk} \\")
    if t == "GOOGL": rows.append(r"\midrule")
table("b7_ant", "Stocks related to Anthropic into the IPO (to 13 November 2026)", "tab:b7", "llrrrrrr",
      r"Ticker & Role & Beta & Since 30 Sep & Since S-1 (26 Oct) & Roadshow week & 20-day abnormal & Cohort pct", rows,
      "Raw returns except the 20-day abnormal return (vs QQQ market model). Roadshow week = 9 to 13 November. Cohort pct = percentile of the 20-day abnormal return within the 20-day pre-IPO abnormal returns of the cohort's " + str(E['n_peers']) + " peer--IPO pairs. Holders = listed companies with a stake in Anthropic.", fit=True)

SX, CW = D["spacex"], D["coreweave"]
rows = [rf"SpaceX (12 Jun 2026) & {t} & {f(v['run20'])} & {f(v['d0'])} & {f(v['d1_5'])} & {f(v['d1_21'])} \\" for t, v in SX.items()]
rows += [r"\midrule"] + [rf"CoreWeave (28 Mar 2025) & {t} & {f(v['run20'])} & {f(v['d0'])} & {f(v['d1_5'])} & {f(v['d1_21'])} \\" for t, v in CW.items()]
table("b8_cases", "The two closest precedents: SpaceX's proxies and CoreWeave's peers", "tab:b8", "llrrrr", r"IPO & Stock & Days $-20$ to $-1$ & Day 0 & Days 1--5 & Days 1--21", rows,
      "Abnormal returns against a QQQ market model, percent. DXYZ (Destiny Tech100) is a listed closed-end fund that held SpaceX shares; Google is a SpaceX shareholder; Rocket Lab and AST SpaceMobile were traded as listed space proxies.")

# scenario map
ll = D["leadlag_daily"]["same_day"]["coef"]; hb = PO["yx"]["coef"] + PO["yx:early"]["coef"]
rows = []
for pop in [-0.10, 0.10, 0.30, 0.60]:
    rows.append(rf"{f(pop,0)} & {f(ll*pop)} & {f(hb*pop,2)} \\")
table("b9_map", "What the cohort's betas imply for peers if Anthropic moves", "tab:b9", "rrr", r"Anthropic move vs QQQ & Peers, daily beta ({:.3f}) & Peers, intraday beta days 1--5 ({:.3f})".format(ll, hb), rows,
      "Mechanical mapping using the pooled coefficients of Tables~\\ref{tab:b4} and~\\ref{tab:b5}; it ignores the proxy unwind seen in SpaceX and Circle, which went the other way (Section~6).")

# ======== figures
p = E["path"]; x = np.array(p["day"]); fig, ax = plt.subplots(figsize=(6.4, 2.6))
ax.fill_between(x, np.array(p["lo"]) * 100, np.array(p["hi"]) * 100, color=B1, alpha=0.15, lw=0); ax.plot(x, np.array(p["mean"]) * 100, color=B1)
ax.axvline(0, color=O2, lw=1, ls="--"); ax.axhline(0, color="#c3c2b7", lw=0.8); ax.set_xlabel("Trading days relative to the IPO's first trade"); ax.set_ylabel("Peer CAR vs QQQ (%)")
ax.text(0.5, ax.get_ylim()[1] * 0.85, "first trade", color=O2, fontsize=7); fig.savefig(FIG / "g1_path.pdf"); plt.close(fig)

fig, axs = plt.subplots(1, 2, figsize=(6.8, 2.5))
ax = axs[0]; lab = ["Days 1–21", "22–63", "64–190"]; ax.bar(lab, [C["corr_early"]["median"], C["corr_mid"]["median"], C["corr_seasoned"]["median"]], color=[O2, MUT, B1])
ax.set_title("(a) Daily correlation, IPO vs peers", fontsize=8, loc="left"); ax.set_ylabel("Median")
ax = axs[1]; lab = ["Days 1–5", "6–21", "22–63"]; ax.bar(lab, [HW[w]["beta_b_on_y"]["median"] for w in ["d1_5", "d6_21", "d22_63"]], color=[O2, MUT, B1])
ax.set_title("(b) Hourly beta of peers on the IPO", fontsize=8, loc="left")
fig.tight_layout(); fig.savefig(FIG / "g2_comove.pdf"); plt.close(fig)

fig, ax = plt.subplots(figsize=(6.4, 2.6)); o = D1.sort_values("post_z"); yy = np.arange(len(o))
ax.barh(yy - 0.2, o.pre_z, height=0.38, color=MUT, label="Close → first print"); ax.barh(yy + 0.2, o.post_z, height=0.38, color=B1, label="First print → close")
ax.set_yticks(yy, [SG.loc[t, "name"] for t in o.ipo], fontsize=7); ax.axvline(0, color="#c3c2b7"); ax.axvline(-2, color=RED, lw=0.8, ls=":"); ax.axvline(2, color=RED, lw=0.8, ls=":")
ax.set_xlabel("Peer abnormal return, z-score vs the same clock window on the prior 20 sessions"); ax.legend(fontsize=7, loc="lower right"); ax.grid(axis="y", visible=False)
fig.savefig(FIG / "g3_day1.pdf"); plt.close(fig)

fig, axs = plt.subplots(2, 2, figsize=(7.0, 4.6)); cols = [RED, PUR, A3, MUT]
for ax, (ipo, cs) in zip(axs.flat, D["cases"].items()):
    grid_ = sorted(set().union(*[set(v["x"]) for v in cs.values()])); pos = {k: i for i, k in enumerate(grid_)}
    days_ = sorted(set(k[:10] for k in grid_))
    for d_ in days_[1:]: ax.axvline(min(i for k, i in pos.items() if k.startswith(d_)) - 0.5, color="#c3c2b7", lw=0.6, ls=":")
    for j, (t, v) in enumerate(cs.items()):
        n = [pos[k] for k in v["x"]]
        if t == ipo: ax.plot(n, np.array(v["y"]) * 100, color=O2, lw=2, label=f"{t} (from first print)"); continue
        ax.plot(n, np.array(v["y"]) * 100, color=INK if t == "QQQ" else cols[(j - 2) % 4], lw=1, ls="--" if t == "QQQ" else "-", label=t)
    ax.axhline(0, color="#c3c2b7", lw=0.8); ax.set_title(f"{SG.loc[ipo,'name']}: first three sessions", fontsize=8, loc="left"); ax.legend(fontsize=6, ncol=2)
    ax.set_xlabel("Hourly bars (dotted lines = new session)"); ax.set_ylabel("vs prior close / first print (%)")
fig.tight_layout(); fig.savefig(FIG / "g4_cases.pdf"); plt.close(fig)

Cd = pd.read_csv(DATA / "raw/beta/daily_close.csv", index_col=0, parse_dates=True)
fig, axs = plt.subplots(1, 2, figsize=(7.0, 2.7)); cc = {"NBIS": RED, "CRWV": O2, "NVDA": PUR, "AVGO": A3, "AMZN": B1, "GOOGL": MUT, "QQQ": INK}
ax = axs[0]; s = Cd.loc["2026-09-30":, list(cc)]; s = s / s.iloc[0] - 1
for t, c in cc.items(): ax.plot(s.index, s[t] * 100, color=c, lw=1.6 if t in ("NBIS", "AMZN") else 1, ls="--" if t == "QQQ" else "-", label=t)
for d_, l_ in [("2026-10-26", "S-1"), ("2026-11-10", "range")]: ax.axvline(pd.Timestamp(d_), color="#c3c2b7", lw=0.8); ax.text(pd.Timestamp(d_), 12, l_, fontsize=6.5, color=MUT)
ax.xaxis.set_major_locator(mdates.WeekdayLocator(byweekday=0, interval=2)); ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b")); ax.set_ylabel("Since 30 Sep (%)"); ax.legend(fontsize=6, ncol=2, loc="lower left"); ax.set_title("(a) Daily, since 30 September", fontsize=8, loc="left")
ax = axs[1]; AW = D["ant_week"]
for t, v in AW.items(): ax.plot(np.arange(len(v["x"])), np.array(v["y"]) * 100, color=cc[t], ls="--" if t == "QQQ" else "-", lw=1, label=t)
ax.axhline(0, color="#c3c2b7", lw=0.8); ax.set_xlabel("Hourly bars, 9–13 November"); ax.set_title("(b) Roadshow week, hourly", fontsize=8, loc="left")
fig.tight_layout(); fig.savefig(FIG / "g5_ant.pdf"); plt.close(fig)
print(sorted(x.name for x in TAB.glob("*.tex")), sorted(x.name for x in FIG.glob("*.pdf")))

# appendix peer map
rows = []
for ipo, (pe, ho) in MAP["peers"].items():
    rows.append(rf"{SG.loc[ipo,'name']} ({ipo}) & {', '.join(pe)} & {', '.join(ho) if ho else '--'} \\")
rows.append(rf"Anthropic (ANT) & {', '.join(MAP['anthropic']['peers'])} & {', '.join(MAP['anthropic']['holders'])} \\")
body = [r"{\scriptsize", r"\begin{longtable}{lll}", r"\toprule IPO & Comparables & Listed stakeholders \\ \midrule \endhead"] + rows + [r"\bottomrule", r"\end{longtable}}"]
(TAB / "b0_map.tex").write_text("\n".join(body) + "\n")
