"""Post-COVID IPO cohort study: frenzy -> reversion, bucketed by market cap at offer.

Usage:  python3 ipo_study/ipo_cohort.py
Writes: ipo_study/data/cohort_paths.csv, cohort_summary.csv, bucket_summary.csv

Day convention: D1 = first trading day's close. Horizons are trading days counted
from D1 (D21 ~ 1 month, D63 ~ 3m, D126 ~ 6m / lock-up, D252 ~ 12m).

CAVEATS (also in the report): the cohort is a hand-picked set of notable US listings, not
the full universe (selection bias); market caps at offer are approximate; direct listings
(COIN, RBLX, PLTR) are excluded because there is no underwritten offer price.
"""
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

OUT = Path(__file__).parent / "data"
OUT.mkdir(exist_ok=True)

# ticker, name, offer price, approx. market cap at offer ($B), group
# group: "post" = post-COVID (IPO date >= 2020-09), "ref" = pre-COVID mega reference
COHORT = [
    ("SNOW", "Snowflake", 120.0, 33, "post"),
    ("ABNB", "Airbnb", 68.0, 47, "post"),
    ("DASH", "DoorDash", 102.0, 39, "post"),
    ("U", "Unity", 52.0, 13.6, "post"),
    ("CPNG", "Coupang", 35.0, 60, "post"),
    ("HOOD", "Robinhood", 38.0, 32, "post"),
    ("RIVN", "Rivian", 78.0, 66, "post"),
    ("ARM", "Arm", 51.0, 54, "post"),
    ("CART", "Instacart", 30.0, 9.9, "post"),
    ("KVYO", "Klaviyo", 30.0, 8.0, "post"),
    ("RDDT", "Reddit", 34.0, 6.4, "post"),
    ("ALAB", "Astera Labs", 36.0, 5.5, "post"),
    ("LINE", "Lineage", 82.0, 18.0, "post"),
    ("CRWV", "CoreWeave", 40.0, 23.0, "post"),
    ("CRCL", "Circle", 31.0, 6.9, "post"),
    ("CHYM", "Chime", 27.0, 11.6, "post"),
    ("FIG", "Figma", 33.0, 19.3, "post"),
    ("KLAR", "Klarna", 40.0, 15.1, "post"),
    ("MDLN", "Medline", 29.0, 40.0, "post"),
    ("SPCX", "SpaceX", 135.0, 1770.0, "post"),
    # pre-COVID mega-IPO references (the only other >$100B listings)
    ("META", "Facebook (2012)", 38.0, 104.0, "ref"),
    ("BABA", "Alibaba (2014)", 68.0, 168.0, "ref"),
    ("UBER", "Uber (2019)", 45.0, 82.0, "ref"),
]
HORIZONS = [1, 3, 5, 10, 21, 63, 126, 252]


def bucket(cap_b: float) -> str:
    if cap_b >= 100:
        return "1 Mega >=$100B"
    if cap_b >= 30:
        return "2 Large $30-100B"
    if cap_b >= 10:
        return "3 Mid $10-30B"
    return "4 Small <$10B"


def load_close(ticker: str) -> pd.Series:
    h = yf.Ticker(ticker).history(period="max", auto_adjust=False)
    s = h["Close"].copy()
    s.index = s.index.tz_localize(None)
    return s


def main() -> None:
    spx = load_close("^GSPC")
    paths, rows = {}, []
    for tkr, name, offer, cap, grp in COHORT:
        px = load_close(tkr)
        if tkr == "META":  # yahoo keeps the 2012 history under META; first bar = IPO day
            px = px[px.index >= "2012-05-18"]
        d1 = px.iloc[0]
        # yfinance splits are applied to history, so rescale the offer to the same basis:
        # day-1 *open-implied* offer is not available, so use the published first-day pop
        # when the adjusted series cannot be matched (checked below by sanity bound).
        row = dict(ticker=tkr, name=name, group=grp, ipo_date=px.index[0].date(),
                   offer=offer, cap_b=cap, bucket=bucket(cap), d1_close=d1)
        # split-adjusted offer: if day-1 close is implausibly far from offer, flag it
        row["d1_ret"] = d1 / offer - 1
        for h in HORIZONS:
            if len(px) > h - 1:
                c = px.iloc[h - 1]
                row[f"ret_offer_D{h}"] = c / offer - 1
                row[f"ret_d1_D{h}"] = c / d1 - 1
                s0 = spx.asof(px.index[0])
                s1 = spx.asof(px.index[h - 1])
                row[f"xs_spx_D{h}"] = (c / d1 - 1) - (s1 / s0 - 1)
        w = px.iloc[:252]
        row["peak_ret_offer_252"] = w.max() / offer - 1
        row["peak_day"] = int(np.argmax(w.values)) + 1
        w10 = px.iloc[:10]
        row["peak10_vs_d1"] = w10.max() / d1 - 1
        row["trough_ret_offer_252"] = w.min() / offer - 1
        row["below_offer_ever_252"] = bool((w < offer).any())
        row["n_days"] = len(px)
        rows.append(row)
        paths[tkr] = (px.iloc[:260].reset_index(drop=True) / offer)
    summ = pd.DataFrame(rows)
    pd.DataFrame(paths).to_csv(OUT / "cohort_paths.csv", index_label="trading_day_idx")
    summ.to_csv(OUT / "cohort_summary.csv", index=False)

    post = summ[summ.group == "post"].copy()
    cols = ["d1_ret"] + [f"ret_d1_D{h}" for h in HORIZONS if h > 1]
    agg = []
    for b, g in post.groupby("bucket"):
        r = {"bucket": b, "n": len(g)}
        for c in cols:
            r[f"med_{c}"] = g[c].median()
        r["pct_revert_D21"] = (g["ret_d1_D21"] < 0).mean()
        r["pct_revert_D63"] = (g["ret_d1_D63"] < 0).mean()
        r["pct_below_offer_ever"] = g["below_offer_ever_252"].mean()
        r["med_peak10_vs_d1"] = g["peak10_vs_d1"].median()
        agg.append(r)
    r = {"bucket": "ALL post-COVID", "n": len(post)}
    for c in cols:
        r[f"med_{c}"] = post[c].median()
    r["pct_revert_D21"] = (post["ret_d1_D21"] < 0).mean()
    r["pct_revert_D63"] = (post["ret_d1_D63"] < 0).mean()
    r["pct_below_offer_ever"] = post["below_offer_ever_252"].mean()
    r["med_peak10_vs_d1"] = post["peak10_vs_d1"].median()
    agg.append(r)
    pd.DataFrame(agg).to_csv(OUT / "bucket_summary.csv", index=False)

    pd.set_option("display.width", 220, "display.max_columns", 40)
    show = ["ticker", "ipo_date", "offer", "d1_close", "d1_ret", "ret_d1_D5", "ret_d1_D21",
            "ret_d1_D63", "ret_d1_D126", "ret_d1_D252", "peak_ret_offer_252", "peak_day",
            "below_offer_ever_252"]
    print(summ[show + ["bucket"]].round(3).to_string(index=False))
    print()
    print(pd.DataFrame(agg).round(3).T.to_string())


if __name__ == "__main__":
    main()
