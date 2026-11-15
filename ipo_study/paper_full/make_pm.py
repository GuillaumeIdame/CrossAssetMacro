"""Tables and figures for the prediction-market section (run after pm_analysis.py). Writes tables/v4 and figures/v4."""
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

HERE = Path(__file__).parent
DATA = HERE.parent / "data"
TAB, FIG = HERE / "tables" / "v4", HERE / "figures" / "v4"
TAB.mkdir(parents=True, exist_ok=True); FIG.mkdir(parents=True, exist_ok=True)
PM = json.loads((DATA / "pm.json").read_text())
ST = json.loads((DATA / "stats.json").read_text())
PI = json.loads((DATA / "positioning_ipo.json").read_text())
EV = json.loads((DATA / "raw" / "pm" / "search_0.json").read_text())
B1, O2, A3, RED, INK, MUT, GRID = "#2a78d6", "#eb6834", "#1baf7a", "#e34948", "#0b0b0b", "#898781", "#e1e0d9"
plt.rcParams.update({"font.family": "serif", "font.serif": ["DejaVu Serif"], "font.size": 8.5, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.edgecolor": "#c3c2b7", "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6, "legend.frameon": False,
                     "savefig.bbox": "tight", "pdf.fonttype": 42})


def table(name, caption, label, colspec, header, rows, notes, size=r"\footnotesize", fit=False):
    body = [rf"\begin{{table}}[!htbp]\centering{size}", rf"\caption{{{caption}}}\label{{{label}}}", r"\resizebox{\linewidth}{!}{" if fit else "",
            r"\begin{threeparttable}", rf"\begin{{tabular}}{{{colspec}}}", r"\toprule", header + r" \\", r"\midrule"] + rows + \
           [r"\bottomrule", r"\end{tabular}", r"\begin{tablenotes}[flushleft]\footnotesize", rf"\item \textit{{Notes:}} {notes}", r"\end{tablenotes}",
            r"\end{threeparttable}", "}" if fit else "", r"\end{table}"]
    (TAB / f"{name}.tex").write_text("\n".join(body) + "\n")


esc = lambda s: str(s).replace("$", r"\$").replace("%", r"\%").replace("–", "--").replace("&", r"\&").replace("<", r"$<$").replace(">", r"$>$")
pc = lambda v, d=0: f"{v*100:.{d}f}\\%"

# ---- T1: the markets
vol = {e["slug"]: e.get("volume") or 0 for e in EV}
d = PM["direct"]
rows = [
    rf"Closing market cap, day 1 (Polymarket) & {vol['anthropic-ipo-closing-market-cap-higher-strikes']/1e6:.1f} & Basic shares $\times$ day-1 close & \$1.25--1.5tn {pc(PM['closing_cap']['p'][4])}; $>$\$1.5tn {pc(sum(PM['closing_cap']['p'][5:]))} \\",
    rf"IPO valuation (Polymarket) & {vol['what-will-anthropics-ipo-valuation-be']/1e6:.1f} & Fully diluted shares $\times$ offer & \$1.25--1.5tn {pc(PM['valuation']['p'][1])}; \$1.5--1.75tn {pc(PM['valuation']['p'][2])} \\",
    rf"Amount raised (Polymarket) & {vol['how-much-will-anthropic-raise-in-its-ipo']/1e6:.2f} & Gross proceeds ex greenshoe & \$65--75bn {pc(PM['raised']['p'][1])}; $<$\$65bn {pc(PM['raised']['p'][0])} \\",
    rf"Share of company sold (Polymarket) & {vol['what-percent-of-anthropic-will-be-sold-in-its-ipo']/1e6:.2f} & Shares sold / Class A+N & 6--7\% {pc(PM['pct_sold']['p'][3])} \\",
    rf"Close above offer on day 1 (Polymarket) & {vol['anthropic-ipo-closing-price-above-ipo-price-on-first-day']/1e6:.2f} & Binary & Yes {pc(d['close_above_offer'],1)} \\",
    rf"Open above offer (Polymarket) & {vol['anthropic-ipo-open-price-above-ipo-price']/1e6:.2f} & Binary & Yes {pc(d['open_above_offer'])} \\",
    rf"IPO date (Polymarket) & {vol['anthropic-ipo-date']/1e6:.2f} & Listing date & 19 Nov {pc(PM['date']['p'][4])} \\",
    rf"IPO announced before 20 Nov (Kalshi) & {PM['kalshi']['Before Nov 20, 2026']['volume']/1e6:.2f} & Binary & Yes {PM['kalshi']['Before Nov 20, 2026']['bid']*100:.0f}--{PM['kalshi']['Before Nov 20, 2026']['ask']*100:.0f}\% \\",
    rf"Market cap above Bitcoin's by 31 Dec (Polymarket) & {vol['will-anthropic-flip-btc-by-december-31']/1e6:.2f} & Binary & Yes {pc(d['flip_btc'])} \\"]
table("pm1_markets", "Prediction markets on the Anthropic IPO (15 November 2026)", "tab:pm1", "lrll", r"Market & Volume (\$m) & Resolves on & Main prices", rows,
      "Polymarket mid prices; Kalshi bid--ask in cents. Kalshi also lists the lead bank (Goldman Sachs 99\\%) and S\\&P sector (Information Technology 93\\%) but no price or valuation markets. "
      "Thin Polymarket markets on the opening price, the day-1 move and day-1 volume (each under \\$2,000 traded, spreads of 20--50 points) are excluded.", fit=True)

# ---- T2: implied numbers
def q(s, k, f=lambda v: f"{v:.2f}"):
    return " & ".join(f(s[x]) for x in ["mean", "median", "p10", "p25", "p75", "p90"])
rows = [rf"IPO valuation, fully diluted (\$tn) & {q(PM['valuation']['summary'], 0)} \\",
        rf"Offer price from valuation (\$) & {q(PM['offer_from_valuation'], 0, lambda v: f'{v:.1f}')} \\",
        rf"Offer price from amount raised (\$) & {q(PM['offer_from_raise'], 0, lambda v: f'{v:.1f}')} \\",
        rf"Basic shares outstanding (bn) & {q(PM['basic_shares_bn'], 0)} \\",
        rf"Closing market cap, day 1 (\$tn) & {q(PM['closing_cap']['summary'], 0)} \\",
        rf"Day-1 closing share price (\$) & {q(PM['close_price'], 0, lambda v: f'{v:.1f}')} \\",
        rf"First-day return vs offer (\%) & {q(PM['pop'], 0, lambda v: f'{v*100:+.0f}'.replace('-', '$-$'))} \\"]
table("pm2_implied", "What the markets imply for pricing day and the first close", "tab:pm2", "lrrrrrr", r"Quantity & Mean & Median & P10 & P25 & P75 & P90", rows,
      f"Monte Carlo (400,000 draws) from the bracket markets, with probability spread uniformly inside each bracket and the markets treated as independent. Fully diluted shares 18.0bn (press-reported \\$1.33tn at \\$74 and \\$1.404tn at \\$78); "
      f"825 million shares sold. Basic shares = shares sold / fraction sold. First-day return = closing cap $\\times$ fraction sold / proceeds $-$ 1. "
      f"P(offer $>$ \\$78) = {PM['p_above_range_val']*100:.0f}\\% from the valuation market and {PM['p_above_range_raise']*100:.0f}\\% from the amount raised; P(first-day return $>$ 0) = {PM['p_pop_pos']*100:.0f}\\% against {d['close_above_offer']*100:.1f}\\% in the direct market.", fit=True)

# ---- T3: evolution
ms = PM["milestones"]
rows = [rf"{k} & {('--' if v['val_ev'] is None else f'{v['val_ev']:.2f}')} & {('--' if v['cc_ev'] is None else f'{v['cc_ev']:.2f}')} \\" for k, v in ms.items() if v["cc_ev"] is not None]
table("pm3_history", "How expectations moved: expected valuation and closing market cap (\\$tn)", "tab:pm3", "lrr", r"Date & Expected IPO valuation & Expected day-1 closing market cap", rows,
      "Expected values from daily closing prices of each bracket, normalised; bracket mid-points (\\$1.125tn for the lowest closing-cap bracket).")

# ---- T4: SpaceX calibration
sx = PM["spacex"]
rows = [rf"{esc(l)} & {sx['pre']['p'][i]*100:.0f}\% & {sx['post']['p'][i]*100:.0f}\% & {'resolved' if l.startswith('$2.0') else ''} \\" for i, l in enumerate(sx["labels"])]
rows += [r"\midrule", rf"Expected value (\$tn) & {sx['pre']['ev']:.2f} & {sx['post']['ev']:.2f} & day-1 close {sx['day1_close_cap']:.2f} \\"]
table("pm4_spacex", "Calibration: SpaceX market cap at the end of its IPO month (Polymarket)", "tab:pm4", "lrrl", r"Bracket & Before trading & After day 1 & Outcome", rows,
      "Mid prices normalised at 00:00 UTC on 12 June 2026 (after pricing, before trading) and 13 June (after the first close). The market resolved on the 30 June close in the \\$2.0--2.5tn bracket; SpaceX's day-1 closing market cap was about \\$2.11tn ($\\$160.95\\times13.1$bn shares).")

# ---- T5: combine with cohort
fs = lambda v: ("$-$" if v < 0 else "+") + f"{abs(v)*100:.0f}\\%"
T = PI["terciles"]
offer, close = PM["point"]["offer"], PM["point"]["close_px"]
rows = []
g2 = {"High PSI, above range": (0.35, -0.28, 12), "Low or mid PSI, above range": (0.32, -0.05, 16), "Low or mid PSI, at or below range": (0.04, 0.16, 12)}
for k, (pop, r63, n) in g2.items():
    rows.append(rf"{k} & {n} & {fs(pop)} & {fs(r63)} & {offer*(1+pop):.0f} & {offer*(1+pop)*(1+r63):.0f} \\")
rows.append(r"\midrule")
pm_pop = PM["point"]["pop"]
for k, r63 in [("Prediction-market close, low/mid-PSI fade", -0.05), ("Prediction-market close, high-PSI fade", -0.28)]:
    rows.append(rf"{k} & -- & {fs(pm_pop)} & {fs(r63)} & {close:.0f} & {close*(1+r63):.0f} \\")
table("pm5_paths", "Combining market expectations with the cohort: illustrative price paths", "tab:pm5", "lrrrrr",
      rf"Scenario & Cohort $n$ & Pop & Day 1$\to$63 & Day-1 close (\$) & Day 63 (\$)", rows,
      f"Cohort rows apply the median pop and day-63 return of each cell of Table~\\ref{{tab:2x2}} to an offer of \\${offer:.0f}, the expected offer implied by the amount-raised market. "
      f"The last two rows start from the market-implied day-1 close of \\${close:.0f}. Illustrative only; Anthropic is far larger than any cohort IPO.")

# ================= figures
fig, axs = plt.subplots(1, 3, figsize=(7.0, 2.6), gridspec_kw={"width_ratios": [1.2, 1, 1]})
ax = axs[0]; lab = [l.replace("–", "-").replace("$", "") for l in PM["closing_cap"]["labels"]]
ax.bar(range(len(lab)), np.array(PM["closing_cap"]["p"]) * 100, color=B1)
ax.set_xticks(range(len(lab)), lab, rotation=70, fontsize=6); ax.set_ylabel("Probability (%)"); ax.set_title("(a) Day-1 closing market cap", fontsize=8, loc="left")
ax = axs[1]; h = PM["history"]
ax.plot(pd.to_datetime(h["cc_dates"]), h["cc_ev"], color=B1, label="Closing cap")
ax.plot(pd.to_datetime(h["val_dates"]), h["val_ev"], color=O2, label="IPO valuation")
for dd, l in [("2026-10-26", "S-1"), ("2026-11-10", "range")]:
    ax.axvline(pd.Timestamp(dd), color=MUT, lw=0.7, ls=":"); ax.text(pd.Timestamp(dd), ax.get_ylim()[1], l, fontsize=6.5, color=MUT, ha="right", va="top")
ax.set_ylabel("Expected value ($tn)"); ax.legend(fontsize=6.5); ax.tick_params(axis="x", labelsize=6, rotation=40); ax.set_title("(b) Expectations over time", fontsize=8, loc="left")
ax = axs[2]
rng = np.random.default_rng(1)
qs = PM["pop_quantiles"]; xs = [qs[k] * 100 for k in ["5", "10", "25", "50", "75", "90", "95"]] if "5" in qs else [qs[k] * 100 for k in sorted(qs, key=float)]
ax.barh([0], [xs[-2] - xs[1]], left=[xs[1]], height=0.35, color="#cde2fb"); ax.barh([0], [xs[4] - xs[2]], left=[xs[2]], height=0.35, color="#86b6ef")
ax.plot([xs[3]], [0], "o", color=B1, ms=7)
for v, l, c in [(0.315, "Cohort: above range", O2), (0.092, "Cohort: low PSI", A3), (0.268, "Cohort: high PSI", RED), (0.192, "Cohort: all", INK)]:
    ax.axvline(v * 100, color=c, lw=1); ax.text(v * 100, 0.32, l, rotation=90, fontsize=6, color=c, va="bottom", ha="right")
ax.set_yticks([]); ax.set_xlabel("First-day return (%)"); ax.set_title("(c) Implied pop vs cohort medians", fontsize=8, loc="left"); ax.set_ylim(-0.4, 0.9)
fig.tight_layout(); fig.savefig(FIG / "f_pm.pdf"); plt.close(fig)
print("pm tables/figures written")
