"""Intraday patterns of IPO debut days.

(1) Daily OHLC for all 43 cohort IPOs: opening pop, open->close drift, fade from the high,
    day-2 gap, and returns measured from the OPEN (what a frenzy buyer at the open pays).
(2) Hourly bars (Yahoo keeps ~730 days) for IPOs since Jan 2025: hour-of-day return and volume
    profile on days 1-3, delayed-open times, timing of the day's high/low, SpaceX hourly path.

Usage: python3 ipo_study/ipo_intraday.py   -> ipo_study/data/intraday.json (+ prints)
Caveat: the hourly sample is small (~17 IPOs, all 2025-26); bar = 60 min starting 09:30 ET.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

sys.path.insert(0, str(Path(__file__).parent))
from ipo_enriched import COHORT  # noqa: E402

HERE = Path(__file__).parent
enr = pd.read_csv(HERE / "data" / "enriched_cohort.csv").set_index("ticker")


def hist(t, **kw):
    h = yf.Ticker(t).history(auto_adjust=False, **kw)
    h.index = h.index.tz_convert("America/New_York") if h.index.tz is not None else h.index
    return h


def main():
    rows = []
    for tk, nm, off, cap, sec in COHORT:
        h = hist(tk, period="max")
        h.index = h.index.tz_localize(None) if h.index.tz is not None else h.index
        o, hi, lo, c = (h[k] for k in ["Open", "High", "Low", "Close"])
        r = dict(ticker=tk, name=nm, sector=sec, ipo_date=str(h.index[0].date()), offer=off, cap_b=cap,
                 open_pop=o.iloc[0] / off - 1, d1_pop=c.iloc[0] / off - 1, oc1=c.iloc[0] / o.iloc[0] - 1,
                 hi_vs_open=hi.iloc[0] / o.iloc[0] - 1, close_vs_high=c.iloc[0] / hi.iloc[0] - 1,
                 gap2=o.iloc[1] / c.iloc[0] - 1, oc2=c.iloc[1] / o.iloc[1] - 1,
                 d2_close_vs_d1=c.iloc[1] / c.iloc[0] - 1)
        for hz in (5, 21, 63):
            r[f"open_to_D{hz}"] = c.iloc[hz - 1] / o.iloc[0] - 1 if len(c) >= hz else np.nan
            r[f"close_to_D{hz}"] = c.iloc[hz - 1] / c.iloc[0] - 1 if len(c) >= hz else np.nan
        r["closed_below_open"] = bool(c.iloc[0] < o.iloc[0])
        r["closed_below_offer"] = bool(c.iloc[0] < off)
        rows.append(r)
    d = pd.DataFrame(rows)
    d["open_bin"] = pd.cut(d.open_pop, [-1, 0.10, 0.40, 9], labels=["Open <10% over offer", "Open 10-40%", "Open >40%"]).astype(str)
    d.to_csv(HERE / "data" / "intraday_daily.csv", index=False)

    def agg(g):
        return dict(n=len(g), open_pop=g.open_pop.median(), d1_pop=g.d1_pop.median(), oc1=g.oc1.median(), hi_vs_open=g.hi_vs_open.median(),
                    close_vs_high=g.close_vs_high.median(), pct_below_open=g.closed_below_open.mean(), gap2=g.gap2.median(), oc2=g.oc2.median(),
                    open_to_D5=g.open_to_D5.median(), open_to_D21=g.open_to_D21.median(), open_to_D63=g.open_to_D63.median(),
                    close_to_D5=g.close_to_D5.median(), close_to_D21=g.close_to_D21.median())
    out = {"all": agg(d), "by_open": [dict(key=k, **agg(g), names=list(g.ticker)) for k, g in d.groupby("open_bin")],
           "daily": json.loads(d[["ticker", "name", "sector", "ipo_date", "open_pop", "d1_pop", "oc1", "hi_vs_open", "close_vs_high", "gap2", "oc2",
                                  "closed_below_open"]].round(4).to_json(orient="records"))}
    out["by_open"].sort(key=lambda x: ["Open <10% over offer", "Open 10-40%", "Open >40%"].index(x["key"]))

    # ---------- hourly -------------
    hp, vol_rows, high_hr, low_hr, first_bar = {1: [], 2: [], 3: []}, {1: [], 2: [], 3: []}, [], [], []
    fh = []
    used = []
    sp_path = None
    hour_tk = [c for c in COHORT if c[0] not in ("SKHY",) and pd.Timestamp(enr.loc[c[0], "ipo_date"]) >= pd.Timestamp("2025-01-01")]
    for tk, nm, off, *_ in hour_tk:
        h = hist(tk, period="730d", interval="60m")
        h = h[h.index >= pd.Timestamp(enr.loc[tk, "ipo_date"]).tz_localize("America/New_York")]
        h = h[h.Volume > 0]
        if h.empty or str(h.index[0].date()) != enr.loc[tk, "ipo_date"]:
            continue  # hourly feed is missing the debut session (e.g. ETOR): skip rather than mislabel day 2 as day 1
        used.append(tk)
        days = sorted(set(h.index.date))[:3]
        for k, day in enumerate(days, start=1):
            g = h[(h.index.date == day) & (h.Volume > 0)]  # drop placeholder bars before a delayed open
            op = g.Open.iloc[0]
            if k == 1:
                first_bar.append(dict(ticker=tk, start=g.index[0].strftime("%H:%M"), bars=len(g)))
                high_hr.append(int(g.index[g.High.values.argmax()].hour)); low_hr.append(int(g.index[g.Low.values.argmin()].hour))
                fh.append(dict(t=tk, hi_first=bool(g.High.values.argmax() == 0), lo_first=bool(g.Low.values.argmin() == 0), hi_first2=bool(g.High.values.argmax() <= 1), lo_first2=bool(g.Low.values.argmin() <= 1)))
            tot = g.Volume.sum()
            for ts, b in g.iterrows():
                hp[k].append(dict(t=tk, hr=ts.hour, bar_ret=b.Close / b.Open - 1, cum=b.Close / op - 1))
                vol_rows[k].append(dict(t=tk, hr=ts.hour, vs=b.Volume / tot))
        if tk == "SPCX":
            g = h[h.index.date <= sorted(set(h.index.date))[4]]  # first five trading days
            sp_path = [dict(ts=ts.strftime("%m-%d %H:%M"), o=round(b.Open / off, 4), c=round(b.Close / off, 4)) for ts, b in g.iterrows()]
    prof = {}
    for k in (1, 2, 3):
        a = pd.DataFrame(hp[k]); v = pd.DataFrame(vol_rows[k])
        prof[k] = [dict(hr=int(hr), bar_ret=float(g.bar_ret.median()), mean_ret=float(g.bar_ret.mean()), cum=float(g.cum.median()), n=int(len(g)),
                        vol=float(v[v.hr == hr].vs.median()), pos=float((g.bar_ret > 0).mean())) for hr, g in a.groupby("hr")]
    out["hourly"] = dict(n_ipos=len(used), names=used, profile=prof, first_bar=first_bar,
                         high_hr=pd.Series(high_hr).value_counts().sort_index().to_dict(), low_hr=pd.Series(low_hr).value_counts().sort_index().to_dict(),
                         spacex=sp_path, first_hour=dict(n=len(fh), hi_first=sum(x['hi_first'] for x in fh), lo_first=sum(x['lo_first'] for x in fh), hi_first2=sum(x['hi_first2'] for x in fh), lo_first2=sum(x['lo_first2'] for x in fh)))
    json.dump(out, open(HERE / "data" / "intraday.json", "w"), default=float)

    pd.set_option("display.width", 220, "display.max_columns", 30)
    print("ALL", {k: round(v, 3) for k, v in out["all"].items()})
    print(pd.DataFrame(out["by_open"]).drop(columns=["names"]).round(3).to_string(index=False))
    print("closed below open %", round(d.closed_below_open.mean(), 2), "below offer", round(d.closed_below_offer.mean(), 2))
    print("corr open_pop vs oc1 (spearman)", round(d[["open_pop", "oc1"]].corr(method="spearman").iloc[0, 1], 2))
    print("first-hour hi/lo", out["hourly"]["first_hour"]); print("first bars", [(x["ticker"], x["start"]) for x in first_bar])
    print("high hour", out["hourly"]["high_hr"], "low hour", out["hourly"]["low_hr"])
    for k in (1, 2, 3):
        print("day", k); print(pd.DataFrame(prof[k]).round(4).to_string(index=False))


if __name__ == "__main__":
    main()
