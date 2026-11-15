"""Assemble the combined research paper: tables/figures from paper/ (v1) and paper_v2/ (v2), plus new
liquidity-transfer and hypothesis tables (v3). Run make_paper.py and make_paper2.py first.

Usage: python3 ipo_study/paper_full/make_full.py
"""
import json
import shutil
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parent
DATA = ROOT / "data"
for sub in ["v1", "v2", "v3"]:
    (HERE / "tables" / sub).mkdir(parents=True, exist_ok=True)
    (HERE / "figures" / sub).mkdir(parents=True, exist_ok=True)
for src, sub in [(ROOT / "paper", "v1"), (ROOT / "paper_v2", "v2")]:
    for p in (src / "tables").glob("*.tex"):
        txt = p.read_text().replace("figures/", f"figures/{sub}/")
        (HERE / "tables" / sub / p.name).write_text(txt)
    for p in (src / "figures").glob("*.pdf"):
        shutil.copy(p, HERE / "figures" / sub / p.name)

TR = json.loads((DATA / "transfer.json").read_text())
TAB, FIG = HERE / "tables" / "v3", HERE / "figures" / "v3"
B1, O2, A3, RED, INK, MUT, GRID = "#2a78d6", "#eb6834", "#1baf7a", "#e34948", "#0b0b0b", "#898781", "#e1e0d9"
plt.rcParams.update({"font.family": "serif", "font.serif": ["DejaVu Serif"], "font.size": 8.5, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.edgecolor": "#c3c2b7", "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6, "legend.frameon": False,
                     "savefig.bbox": "tight", "pdf.fonttype": 42})


def f(v, d=1, pctf=True):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "--"
    x = v * 100 if pctf else v
    s = f"{abs(x):.{d}f}"
    return s if float(s) == 0 else ("$-$" if x < 0 else "+") + s


def fp(p):
    return "$<$0.001" if p < 0.001 else (f"{p:.3f}" if p < 0.1 else f"{p:.2f}")


def table(name, caption, label, colspec, header, rows, notes, size=r"\small", fit=False):
    body = [rf"\begin{{table}}[!htbp]\centering{size}", rf"\caption{{{caption}}}\label{{{label}}}", r"\resizebox{\linewidth}{!}{" if fit else "",
            r"\begin{threeparttable}", rf"\begin{{tabular}}{{{colspec}}}", r"\toprule", header + r" \\", r"\midrule"] + rows + \
           [r"\bottomrule", r"\end{tabular}", r"\begin{tablenotes}[flushleft]\footnotesize", rf"\item \textit{{Notes:}} {notes}", r"\end{tablenotes}",
            r"\end{threeparttable}", "}" if fit else "", r"\end{table}"]
    (TAB / f"{name}.tex").write_text("\n".join(body) + "\n")


# --- T: liquidity transfer tests
rows = [r"\multicolumn{5}{l}{\textit{Panel A. Peer substitution: own sector ETF minus S\&P~500}} \\"]
for g, r in TR["peer"].items():
    for w, lab in [("pre", "T$-$10 to T$-$1"), ("list", "Listing day to T+5"), ("late", "T+6 to T+20")]:
        v = r[w]; rows.append(rf"\quad {g.replace('$', '\\$')}, {lab} & {v['n']} & {f(v['mean'],2)} & {f(v['null'],2)} & {fp(v['p'])} \\")
rows += [r"\addlinespace", r"\multicolumn{5}{l}{\textit{Panel B. Abnormal volume around large listings (log ratio to prior 60-day mean)}} \\"]
for k, r in TR["volume"].items():
    for w, lab in [("pre", "T$-$10 to T$-$1"), ("list", "Listing week")]:
        if w in r:
            v = r[w]; rows.append(rf"\quad {k.replace('&', '\\&')}, {lab} & {v['n']} & {f(v['mean'],2,pctf=False)} & {f(v['null'],2,pctf=False)} & {fp(v['p'])} \\")
rows += [r"\addlinespace", r"\multicolumn{5}{l}{\textit{Panel C. Correlation of daily returns, T$-$10 to T$-$1 (large listings)}} \\"]
for k, v in TR["corr"].items():
    a, b = k.split("|"); lab = f"{a.replace('-USD','')}--{b.replace('-USD','').replace('IPO','IPO ETF')}"
    rows.append(rf"\quad {lab}: level & 23 & {f(v['level'],2,pctf=False)} & {f(v['null_level'],2,pctf=False)} & {fp(v['p_level'])} \\")
    rows.append(rf"\quad {lab}: change vs prior 10 sessions & 23 & {f(v['shift'],2,pctf=False)} & {f(v['null_shift'],2,pctf=False)} & {fp(v['p_shift'])} \\")
table("t_transfer", "Is liquidity transferred between markets around listings?", "tab:transfer", "lrrrr", r"Test & $n$ & Events & Random dates & $p$", rows,
      "Panel A in percent. Random dates: permutation test against 4,000--5,000 random draws (sector drawn in the cohort's proportions for Panel A). Large listings: proceeds of \\$1bn or more (23 IPOs).",
      size=r"\footnotesize", fit=True)
# episode correlations
rows = []
for k, v in TR["corr"].items():
    a, b = k.split("|"); lab = f"{a.replace('-USD','')}--{b.replace('-USD','').replace('IPO','IPO ETF')}"
    rows.append(rf"{lab} & {f(v['null_level'],2,pctf=False)} & {f(v['level'],2,pctf=False)} & {f(v['spacex_level'],2,pctf=False)} & {f(v['anthropic_level'],2,pctf=False)} \\")
table("t_corr_episodes", "Cross-asset correlation in the ten sessions before listing", "tab:correp", "lrrrr", r"Pair & Random dates & Large listings & SpaceX & Anthropic (to 13 Nov)", rows,
      "Correlation of daily returns over ten sessions. The two 2026 episodes show unusually high co-movement (SPY--gold before SpaceX, SPY--Bitcoin before Anthropic), the signature of a common risk factor rather than of the listings as a group.",
      size=r"\footnotesize")
# --- T: factor betas + mediation
bd = TR["betas"]
rows = [rf"QQQ & {bd['b_qqq']['mean']:.2f} & [{bd['b_qqq']['lo']:.2f}, {bd['b_qqq']['hi']:.2f}] & {bd['b_qqq']['t']:.1f} & {bd['psi_vs_b_qqq']['rho']:+.2f} ({fp(bd['psi_vs_b_qqq']['p'])}) \\",
        rf"High beta $-$ low vol (SPHB$-$SPLV) & {bd['b_beta']['mean']:.2f} & [{bd['b_beta']['lo']:.2f}, {bd['b_beta']['hi']:.2f}] & {bd['b_beta']['t']:.1f} & {bd['psi_vs_b_beta']['rho']:+.2f} ({fp(bd['psi_vs_b_beta']['p'])}) \\",
        rf"Bitcoin & {bd['b_btc']['mean']:.2f} & [{bd['b_btc']['lo']:.2f}, {bd['b_btc']['hi']:.2f}] & {bd['b_btc']['t']:.1f} & {bd['psi_vs_b_btc']['rho']:+.2f} ({fp(bd['psi_vs_b_btc']['p'])}) \\",
        rf"$R^2$ & {bd['r2']['mean']:.2f} & [{bd['r2']['lo']:.2f}, {bd['r2']['hi']:.2f}] & -- & -- \\", r"\midrule",
        rf"\multicolumn{{5}}{{l}}{{\textit{{Decomposing the day 2--63 log return; rank correlation with PSI at listing}}}} \\",
        rf"\quad Total return & & & & {bd['psi_vs_tot']['rho']:+.2f} ({fp(bd['psi_vs_tot']['p'])}) \\",
        rf"\quad Factor-implied part & & & & {bd['psi_vs_fac_ret']['rho']:+.2f} ({fp(bd['psi_vs_fac_ret']['p'])}) \\",
        rf"\quad Idiosyncratic part & & & & {bd['psi_vs_resid_ret']['rho']:+.2f} ({fp(bd['psi_vs_resid_ret']['p'])}) \\"]
rows = [r.replace("+", "$+$") if "(" in r else r for r in rows]
table("t_betas", "The IPO joins the speculative book: factor betas over days 2 to 63", "tab:betas", "lrcrr", r"Factor & Mean beta & 95\% CI & $t$ & $\rho$ with PSI ($p$)", rows,
      "Each IPO's daily log returns on days 2--63 regressed on QQQ, the high-beta spread and Bitcoin; cross-sectional mean of the 43 betas with bootstrap CI and $t$-statistic. "
      "The factor-implied part sums fitted daily returns; the idiosyncratic part sums residuals.", size=r"\footnotesize")
he = TR["reversal"]
rows = [rf"Slope of next-63-day spread return on past-63-day spread return (all days) & {he['slope']:+.2f} & {he['t']:+.1f} & {fp(he['p'])} \\".replace("+", "$+$").replace("-", "$-$", 1)]
for k, v in he["fac63_by_tercile"].items():
    rows.append(rf"High-beta spread over the 63 sessions after listing, {k} tercile (median) & {f(v['median'])}\% & -- & -- \\")
table("t_reversal", "Does crowding mean-revert after stretched listings?", "tab:reversal", "lrrr", r"Test & Estimate & $t$ & $p$", rows,
      "Newey--West $t$ with 63 lags for the time-series regression (1,554 days). No evidence that crowding unwinds systematically after listings, so the post-IPO fade is not just the factor reversing.",
      size=r"\footnotesize", fit=True)

# --- figure: betas distribution and correlation episodes
Bt = pd.DataFrame(TR["beta_rows"])
fig, axs = plt.subplots(1, 2, figsize=(6.8, 2.6))
ax = axs[0]
ax.hist(Bt.b_beta, bins=14, color=O2, alpha=0.85, label="High-beta spread")
ax.hist(Bt.b_btc, bins=14, color=B1, alpha=0.75, label="Bitcoin")
ax.axvline(0, color=INK, lw=0.8); ax.set_xlabel("IPO beta, days 2--63"); ax.set_ylabel("Number of IPOs"); ax.legend(fontsize=7)
ax.set_title("(a) IPOs load on the speculative factors", fontsize=8, loc="left")
ax = axs[1]; keys = list(TR["corr"].keys()); x = np.arange(len(keys))
for j, (k_, lab, col) in enumerate([("null_level", "Random dates", "#c3c2b7"), ("level", "Large listings", B1), ("spacex_level", "SpaceX", INK), ("anthropic_level", "Anthropic", RED)]):
    ax.bar(x + (j - 1.5) * 0.2, [TR["corr"][k][k_] for k in keys], width=0.19, color=col, label=lab)
ax.set_xticks(x, [k.replace("-USD", "").replace("|", "–").replace("IPO", "IPO ETF") for k in keys], fontsize=7); ax.axhline(0, color="#c3c2b7", lw=0.8)
ax.set_ylabel("Correlation, T−10 to T−1"); ax.legend(fontsize=6.5, ncol=2); ax.set_title("(b) Co-movement before listing", fontsize=8, loc="left")
fig.tight_layout(); fig.savefig(FIG / "f_transfer.pdf"); plt.close(fig)
print("done", sorted(p.name for p in TAB.glob("*.tex")))
