"""Enriched IPO study: sectors, calendar seasonality and macro regimes (post-COVID, n~41).

Usage:  python3 ipo_study/ipo_enriched.py
Writes: ipo_study/data/enriched_cohort.csv and ipo_study/data/artifact_data.json

Offer prices are public pricing figures from memory/earlier verification; the first-day pop
computed from them was sanity-checked against remembered debut pops. Market caps at offer are
APPROXIMATE (+/-20%). The universe is a hand-picked set of notable US IPOs (selection bias,
e.g. no 2022 names because the window was effectively shut).
"""
import json
from io import StringIO
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import yfinance as yf

HERE = Path(__file__).parent
DATA = HERE / "data"

SW, CI, FN, HC, CS, IE = ("Software, AI & semis", "Consumer internet", "Fintech & financials",
                          "Healthcare", "Consumer & leisure", "Industrials, energy & space")
# ticker, name, offer, approx cap at offer $B, sector
COHORT = [
    ("SNOW", "Snowflake", 120, 33, SW), ("U", "Unity", 52, 13.6, SW), ("ARM", "Arm", 51, 54, SW),
    ("KVYO", "Klaviyo", 30, 8, SW), ("ALAB", "Astera Labs", 36, 5.5, SW), ("CRWV", "CoreWeave", 40, 23, SW),
    ("FIG", "Figma", 33, 19.3, SW), ("DUOL", "Duolingo", 102, 3.7, SW), ("RBRK", "Rubrik", 32, 5.6, SW),
    ("NTSK", "Netskope", 19, 7.7, SW), ("SAIL", "SailPoint", 23, 12.8, SW), ("TOST", "Toast", 40, 20, SW),
    ("ABNB", "Airbnb", 68, 47, CI), ("DASH", "DoorDash", 102, 39, CI), ("CPNG", "Coupang", 35, 60, CI),
    ("CART", "Instacart", 30, 9.9, CI), ("RDDT", "Reddit", 34, 6.4, CI), ("BMBL", "Bumble", 43, 8, CI),
    ("STUB", "StubHub", 23.5, 8.6, CI), ("COMP", "Compass", 18, 8.1, CI),
    ("HOOD", "Robinhood", 38, 32, FN), ("AFRM", "Affirm", 49, 12, FN), ("CRCL", "Circle", 31, 6.9, FN),
    ("CHYM", "Chime", 27, 11.6, FN), ("KLAR", "Klarna", 40, 15.1, FN), ("ETOR", "eToro", 52, 4.2, FN),
    ("FIGR", "Figure", 25, 5.3, FN), ("GEMI", "Gemini", 28, 3.3, FN), ("OSCR", "Oscar Health", 39, 8, FN),
    ("MDLN", "Medline", 29, 40, HC), ("TEM", "Tempus AI", 37, 6.1, HC), ("WAY", "Waystar", 21, 3.7, HC),
    ("HNGE", "Hinge Health", 32, 2.6, HC),
    ("CAVA", "Cava", 22, 2.5, CS), ("BIRK", "Birkenstock", 46, 8.6, CS), ("VIK", "Viking", 24, 10.4, CS),
    ("IBTA", "Ibotta", 88, 2.7, CS),
    ("RIVN", "Rivian", 78, 66, IE), ("LINE", "Lineage", 82, 18, IE), ("SARO", "StandardAero", 24, 8, IE),
    ("NXT", "Nextracker", 24, 3.5, IE), ("VG", "Venture Global", 25, 20, IE), ("SPCX", "SpaceX", 135, 1770, IE),
]
HZ = [1, 3, 5, 10, 21, 63, 126, 252]


def fred(sid):
    t = requests.get(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}", timeout=30).text
    df = pd.read_csv(StringIO(t), index_col=0, parse_dates=True)
    return pd.to_numeric(df.iloc[:, 0], errors="coerce").dropna()


def close(t, start=None):
    h = yf.Ticker(t).history(period="max", auto_adjust=False)
    s = h["Close"]; s.index = s.index.tz_localize(None)
    return s


def bucket(c):
    return "Mega >=100B" if c >= 100 else "Large 30-100B" if c >= 30 else "Mid 10-30B" if c >= 10 else "Small <10B"


def main():
    spx, vix, tnx = close("^GSPC"), close("^VIX"), close("^TNX")
    ff = fred("FEDFUNDS")  # monthly effective fed funds
    ma200 = spx.rolling(200).mean()

    rows, paths = [], {}
    for tk, nm, off, cap, sec in COHORT:
        px = close(tk)
        d0 = px.index[0]
        prev = d0 - pd.Timedelta(days=1)
        r = dict(ticker=tk, name=nm, sector=sec, ipo_date=d0.date().isoformat(), offer=off, cap_b=cap,
                 bucket=bucket(cap), d1_pop=px.iloc[0] / off - 1)
        for h in HZ[1:]:
            r[f"r{h}"] = px.iloc[h - 1] / px.iloc[0] - 1 if len(px) >= h else np.nan  # from D1 close
        r["ro63"] = px.iloc[62] / off - 1 if len(px) >= 63 else np.nan  # from offer
        r["ro126"] = px.iloc[125] / off - 1 if len(px) >= 126 else np.nan
        r["below_offer_63"] = bool((px.iloc[:63] < off).any())
        # regime at IPO date (last data strictly before listing)
        v = vix.asof(prev); s_ = spx.asof(prev); m = ma200.asof(prev)
        f_now = ff.asof(prev); f_6 = ff.asof(prev - pd.Timedelta(days=182))
        y_now = tnx.asof(prev); y_3 = tnx.asof(prev - pd.Timedelta(days=91))
        r.update(vix=v, fed_6m_chg=f_now - f_6, y10=y_now, y10_3m_chg=y_now - y_3,
                 spx_vs_200=s_ / m - 1, spx_6m=s_ / spx.asof(prev - pd.Timedelta(days=182)) - 1)
        r["month"] = d0.month
        r["quarter"] = f"Q{(d0.month - 1) // 3 + 1}"
        r["year"] = d0.year
        rows.append(r)
        paths[tk] = (px.iloc[:253] / px.iloc[0]).reset_index(drop=True)
    df = pd.DataFrame(rows)
    df["fed"] = np.where(df.fed_6m_chg >= 0.5, "Fed hiking", np.where(df.fed_6m_chg <= -0.5, "Fed easing", "Fed on hold"))
    df["vix_reg"] = pd.cut(df.vix, [0, 16, 22, 100], labels=["VIX <16", "VIX 16-22", "VIX >22"]).astype(str)
    df["trend"] = np.where(df.spx_vs_200 > 0, "S&P above 200d", "S&P below 200d")
    df["yld"] = np.where(df.y10_3m_chg > 0.3, "10Y rising", np.where(df.y10_3m_chg < -0.3, "10Y falling", "10Y flat"))
    df.to_csv(DATA / "enriched_cohort.csv", index=False)

    def agg(g):
        return dict(n=len(g), pop=g.d1_pop.median(), r5=g.r5.median(), r21=g.r21.median(), r63=g.r63.median(),
                    r126=g.r126.median(), n126=int(g.r126.notna().sum()), r252=g.r252.median(),
                    pct_down63=(g.r63.dropna() < 0).mean(), pct_down126=(g.r126.dropna() < 0).mean(), pct_below_offer63=g.below_offer_63.mean())

    def table(col, order=None):
        out = []
        for k, g in df.groupby(col):
            d = agg(g); d["key"] = k; d["names"] = list(g.ticker); out.append(d)
        if order:
            out.sort(key=lambda x: order.index(x["key"]) if x["key"] in order else 99)
        return out

    sec_order = [SW, CI, FN, HC, CS, IE]
    out = {
        "all": agg(df), "n": len(df),
        "sector": table("sector", sec_order), "quarter": table("quarter", ["Q1", "Q2", "Q3", "Q4"]),
        "bucket": table("bucket", ["Small <10B", "Mid 10-30B", "Large 30-100B", "Mega >=100B"]),
        "fed": table("fed", ["Fed easing", "Fed on hold", "Fed hiking"]),
        "vix": table("vix_reg", ["VIX <16", "VIX 16-22", "VIX >22"]),
        "trend": table("trend"), "yld": table("yld", ["10Y falling", "10Y flat", "10Y rising"]),
        "year": table("year"),
        "cohort": [{k: (None if (isinstance(v, float) and np.isnan(v)) else v) for k, v in r.items()}
                   for r in df.round(4).to_dict("records")],
    }
    # sector median paths (D1 close = 100), up to 252 days, only where >=3 names alive
    sp = {}
    for sec in sec_order:
        tk = df[df.sector == sec].ticker
        m = pd.DataFrame({t: paths[t] for t in tk})
        med = (m.median(axis=1) * 100).where(m.notna().sum(axis=1) >= 3)
        sp[sec] = [None if np.isnan(x) else round(float(x), 1) for x in med.iloc[:253]]
    out["sector_paths"] = sp
    # SpaceX + bucket median paths
    pb = {}
    for bk in ["Small <10B", "Mid 10-30B", "Large 30-100B"]:
        tk = df[df.bucket == bk].ticker
        m = pd.DataFrame({t: paths[t] for t in tk})
        med = (m.median(axis=1) * 100).where(m.notna().sum(axis=1) >= 3)
        pb[bk] = [None if np.isnan(x) else round(float(x), 1) for x in med.iloc[:253]]
    pb["SpaceX"] = [round(float(x) * 100, 1) for x in paths["SPCX"].dropna()]
    out["bucket_paths"] = pb

    allm = pd.DataFrame(paths)
    out["all_path"] = [None if np.isnan(x) else round(float(x), 1)
                       for x in (allm.median(axis=1) * 100).where(allm.notna().sum(axis=1) >= 5).iloc[:253]]
    mt = pd.concat([tnx.resample("ME").last(), vix.resample("ME").mean(), ff.resample("ME").last()], axis=1, keys=["y10", "vix", "ff"])
    mt = mt[mt.index >= "2020-06-01"].ffill()
    out["macro_monthly"] = [dict(d=i.strftime("%Y-%m"), y10=round(float(r.y10), 2), vix=round(float(r.vix), 1), ff=round(float(r.ff), 2))
                            for i, r in mt.iterrows()]

    # ---- market seasonality: S&P 500 since 1950 --------------------------------------
    s = spx[spx.index >= "1950-01-01"]
    mret = s.resample("ME").last().pct_change().dropna()
    mm = mret.groupby(mret.index.month).agg(["mean", "median", lambda x: (x > 0).mean()])
    mm.columns = ["mean", "median", "hit"]
    out["spx_month"] = [dict(m=int(i), mean=round(r["mean"] * 100, 2), hit=round(r["hit"] * 100)) for i, r in mm.iterrows()]
    ev = []
    for y in range(1950, 2026):
        a = s.asof(pd.Timestamp(y, 11, 15))
        ev.append(dict(year=y, mid=(y - 1950) % 4 == 0, to21=s.asof(pd.Timestamp(y, 11, 15) + pd.Timedelta(days=30)) / a - 1,
                       to63=s.asof(pd.Timestamp(y, 11, 15) + pd.Timedelta(days=91)) / a - 1,
                       to252=s.asof(pd.Timestamp(y + 1, 11, 15)) / a - 1))
    ev = pd.DataFrame(ev)
    def st(g): return dict(n=len(g), m1=g.to21.mean() * 100, m3=g.to63.mean() * 100, m12=g.to252.mean() * 100,
                           h1=(g.to21 > 0).mean() * 100, h3=(g.to63 > 0).mean() * 100, h12=(g.to252 > 0).mean() * 100)
    out["spx_nov15"] = dict(all=st(ev), midterm=st(ev[ev.mid]), other=st(ev[~ev.mid]))

    # ---- current regime snapshot (13 Nov 2026) ----------------------------------------
    t = spx.index[-1]
    cur = dict(date=str(t.date()), vix=float(vix.iloc[-1]), y10=float(tnx.iloc[-1]),
               y10_3m=float(tnx.iloc[-1] - tnx.asof(t - pd.Timedelta(days=91))),
               fed_6m=float(ff.iloc[-1] - ff.asof(t - pd.Timedelta(days=182))), fed_level=float(ff.iloc[-1]),
               spx_vs_200=float(spx.iloc[-1] / ma200.iloc[-1] - 1), spx_6m=float(spx.iloc[-1] / spx.asof(t - pd.Timedelta(days=182)) - 1),
               spx_off_high=float(spx.iloc[-1] / spx.cummax().iloc[-1] - 1))
    out["current"] = cur
    json.dump(out, open(DATA / "artifact_data.json", "w"), default=float)

    pd.set_option("display.width", 220, "display.max_columns", 30)
    for k in ["sector", "quarter", "fed", "vix", "yld", "trend", "year", "bucket"]:
        print(f"\n== {k}")
        print(pd.DataFrame(out[k]).drop(columns=["names"]).round(3).to_string(index=False))
    print("\nS&P Nov15:", json.dumps(out["spx_nov15"], default=float, indent=0)[:900])
    print("\ncurrent", cur)
    print("\nspx months", [(m["m"], m["mean"], m["hit"]) for m in out["spx_month"]])


if __name__ == "__main__":
    main()
