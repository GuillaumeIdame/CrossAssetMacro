"""Cross-asset / liquidity panel around mega-IPOs: SpaceX (listed 2026-06-12) vs the
run-up to Anthropic (public S-1 2026-10-26, marketing from 2026-11-10, listing
reportedly as soon as 2026-11-19).

Usage:  python3 ipo_study/liquidity_panel.py
Writes: ipo_study/data/panel_prices.csv, event_windows.csv, net_liquidity.csv,
        and PNG charts in ipo_study/charts/
"""
from io import StringIO
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import requests
import yfinance as yf

HERE = Path(__file__).parent
DATA, CH = HERE / "data", HERE / "charts"
DATA.mkdir(exist_ok=True)
CH.mkdir(exist_ok=True)

ASSETS = {  # name -> yahoo ticker, kind ("pct" = % change, "pts" = level change)
    "S&P 500": ("^GSPC", "pct"), "Nasdaq": ("^IXIC", "pct"), "VIX": ("^VIX", "pts"),
    "Gold": ("GC=F", "pct"), "Bitcoin": ("BTC-USD", "pct"), "US10Y yld (%)": ("^TNX", "pts"),
    "DXY": ("DX-Y.NYB", "pct"), "IPO ETF": ("IPO", "pct"), "NVDA": ("NVDA", "pct"),
    "MSTR (BTC beta)": ("MSTR", "pct"), "HYG": ("HYG", "pct"), "TLT": ("TLT", "pct"),
    "CoreWeave": ("CRWV", "pct"), "SpaceX": ("SPCX", "pct"),
}
SPACEX_T0 = pd.Timestamp("2026-06-12")
ANTH_SPUB, ANTH_MKT = pd.Timestamp("2026-10-26"), pd.Timestamp("2026-11-10")


def fred(series: str) -> pd.Series:
    r = requests.get(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}", timeout=30)
    r.raise_for_status()
    df = pd.read_csv(StringIO(r.text), index_col=0, parse_dates=True)
    return pd.to_numeric(df.iloc[:, 0], errors="coerce").dropna()


def main() -> None:
    px = yf.download([v[0] for v in ASSETS.values()], start="2026-01-01", progress=False,
                     auto_adjust=True)["Close"]
    px = px.rename(columns={v[0]: k for k, v in ASSETS.items()})
    px = px[list(ASSETS)]
    px.to_csv(DATA / "panel_prices.csv")
    # trading calendar = US equity days (S&P rows); crypto/others are ffilled onto it
    cal = px["S&P 500"].dropna().index
    px = px.reindex(cal).ffill()
    btc_live = yf.Ticker("BTC-USD").history(period="5d")["Close"]

    # ---- Fed net liquidity = WALCL - TGA - ON RRP (all in $bn) -------------------------
    walcl, tga, rrp = fred("WALCL") / 1e3, fred("WTREGEN") / 1e3, fred("RRPONTSYD")
    idx = pd.date_range("2026-01-01", cal[-1], freq="D")
    nl = pd.concat([walcl.reindex(idx).ffill(), tga.reindex(idx).ffill(),
                    rrp.reindex(idx).ffill().fillna(0)], axis=1, keys=["WALCL", "TGA", "RRP"])
    nl["NET_LIQ"] = nl.WALCL - nl.TGA - nl.RRP
    for s, nm in [("WRMFSL", "RETAIL_MMF"), ("WIMFSL", "INST_MMF")]:
        nl[nm] = fred(s).reindex(idx).ffill()
    nl.to_csv(DATA / "net_liquidity.csv", index_label="date")
    nlc = nl.reindex(cal)

    def window(a: pd.Timestamp, b: pd.Timestamp, label: str) -> dict:
        a, b = cal[cal.get_indexer([a], method="bfill")[0]], cal[cal.get_indexer([b], method="ffill")[0]]
        row = {"window": label, "start": a.date(), "end": b.date(),
               "trading_days": int(cal.get_loc(b) - cal.get_loc(a))}
        for k, (_, kind) in ASSETS.items():
            x0, x1 = px.at[a, k], px.at[b, k]
            if pd.isna(x0) or pd.isna(x1):
                row[k] = np.nan
            else:
                row[k] = (x1 - x0) if kind == "pts" else (x1 / x0 - 1) * 100
        row["NetLiq $bn"] = nlc.at[b, "NET_LIQ"] - nlc.at[a, "NET_LIQ"]
        row["TGA $bn"] = nlc.at[b, "TGA"] - nlc.at[a, "TGA"]
        row["RRP $bn"] = nlc.at[b, "RRP"] - nlc.at[a, "RRP"]
        return row

    k = lambda t0, n: cal[cal.get_loc(t0) + n]  # noqa: E731
    t0 = SPACEX_T0
    last = cal[-1]
    n_pre = int(cal.get_loc(cal[cal.get_indexer([last], method="ffill")[0]])
                - cal.get_loc(cal[cal.get_indexer([ANTH_SPUB], method="bfill")[0]]))
    rows = [
        window(k(t0, -1 - n_pre), k(t0, -1), f"SpaceX pre-listing (same {n_pre}d length as Anthropic run-up)"),
        window(k(t0, -1), k(t0, 3), "SpaceX frenzy  T-1 -> T+3"),
        window(k(t0, 3), k(t0, 21), "SpaceX reversion T+3 -> T+21"),
        window(k(t0, 21), k(t0, 41), "SpaceX T+21 -> T+41 (lock-up/earnings unlocks begin)"),
        window(k(t0, -1), k(t0, 63), "SpaceX T-1 -> T+63"),
        window(k(t0, -1), last, "SpaceX T-1 -> latest"),
        window(ANTH_SPUB, last, f"Anthropic run-up: public S-1 {ANTH_SPUB.date()} -> latest"),
        window(ANTH_MKT, last, f"Anthropic marketing: {ANTH_MKT.date()} -> latest"),
        window(cal[-6], last, "Anthropic last 5 trading days"),
    ]
    ew = pd.DataFrame(rows)
    ew.to_csv(DATA / "event_windows.csv", index=False)
    pd.set_option("display.width", 250, "display.max_columns", 40)
    print(ew.round(1).T.to_string(header=False))
    print("\nlatest BTC prints:", btc_live.round(0).to_dict())
    print("latest net liq $bn:", nl.NET_LIQ.dropna().iloc[-1].round(0), "TGA", nl.TGA.dropna().iloc[-1].round(0),
          "RRP", nl.RRP.dropna().iloc[-1].round(2))

    # ---- charts --------------------------------------------------------------------
    plt.rcParams.update({"font.size": 9, "axes.spines.top": False, "axes.spines.right": False})
    # 1. SpaceX path vs offer with cross-asset indexed to T-1
    fig, ax = plt.subplots(2, 1, figsize=(9, 7), sharex=True, gridspec_kw={"height_ratios": [1.2, 1]})
    sp = px["SpaceX"].loc[t0:]
    ax[0].plot(sp.index, sp / 135, color="#1f77b4", lw=1.8)
    ax[0].axhline(1, color="grey", ls="--", lw=0.8)
    ax[0].set_title("SpaceX (SPCX) close / $135 offer price"); ax[0].set_ylabel("x offer")
    base = px.loc[k(t0, -1):]
    for nm, c in [("Bitcoin", "#f7931a"), ("Gold", "#d4af37"), ("Nasdaq", "#2ca02c"), ("S&P 500", "#7f7f7f")]:
        ax[1].plot(base.index, base[nm] / base[nm].iloc[0] * 100, label=nm, color=c, lw=1.4)
    ax[1].axvline(t0, color="k", lw=0.6, ls=":"); ax[1].legend(ncol=4, frameon=False)
    ax[1].set_title("Cross-asset, indexed to day before SpaceX listing = 100")
    fig.tight_layout(); fig.savefig(CH / "spacex_path_cross_asset.png", dpi=140); plt.close(fig)

    # 2. Anthropic run-up window: indexed to Oct 21 close
    b = px.loc["2026-10-15":]
    fig, ax = plt.subplots(1, 2, figsize=(10, 3.8))
    for nm, c in [("Bitcoin", "#f7931a"), ("Gold", "#d4af37"), ("Nasdaq", "#2ca02c"),
                  ("MSTR (BTC beta)", "#9467bd"), ("S&P 500", "#7f7f7f")]:
        ax[0].plot(b.index, b[nm] / b[nm].iloc[0] * 100, label=nm, color=c, lw=1.4)
    ax[0].axvline(ANTH_SPUB, color="k", ls=":", lw=0.7); ax[0].axvline(ANTH_MKT, color="k", ls=":", lw=0.7)
    ax[0].legend(frameon=False, fontsize=7); ax[0].set_title("Run-up to Anthropic (15 Oct = 100)")
    ax[1].plot(b.index, b["US10Y yld (%)"], color="#d62728", label="US10Y %")
    ax2 = ax[1].twinx(); ax2.plot(b.index, b["VIX"], color="#1f77b4", label="VIX")
    ax[1].set_title("US10Y (red, lhs) and VIX (blue, rhs)")
    for a in ax: a.tick_params(axis="x", rotation=30)
    fig.tight_layout(); fig.savefig(CH / "anthropic_runup_cross_asset.png", dpi=140); plt.close(fig)

    # 3. cohort median path from D1 close, by bucket
    paths = pd.read_csv(DATA / "cohort_paths.csv", index_col=0)
    summ = pd.read_csv(DATA / "cohort_summary.csv")
    post = summ[summ.group == "post"]
    fig, ax = plt.subplots(figsize=(9, 4.6))
    for bk, c in [("2 Large $30-100B", "#1f77b4"), ("3 Mid $10-30B", "#ff7f0e"), ("4 Small <$10B", "#2ca02c")]:
        tk = post[post.bucket == bk].ticker
        rel = paths[tk].div(paths[tk].iloc[0]).iloc[:253]
        ax.plot(rel.index + 1, rel.median(axis=1), label=f"{bk} (n={len(tk)}) median", color=c, lw=1.6)
    sx = paths["SPCX"].dropna(); ax.plot(sx.index + 1, sx / sx.iloc[0], color="k", lw=1.6, label="SpaceX (Mega)")
    ax.axhline(1, color="grey", lw=0.7, ls="--"); ax.axvline(126, color="grey", lw=0.7, ls=":")
    ax.set_xlabel("trading days since IPO (D1 close = 1.0)"); ax.legend(frameon=False)
    ax.set_title("Post-COVID IPO price path from first-day close, by market-cap bucket")
    fig.tight_layout(); fig.savefig(CH / "cohort_paths_by_bucket.png", dpi=140); plt.close(fig)


if __name__ == "__main__":
    main()
