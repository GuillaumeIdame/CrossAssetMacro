"""Cross-asset event study around large US IPO listings (close-to-close and hourly).

Usage:  python3 ipo_study/xasset_event.py   -> ipo_study/data/xasset.json

Daily: windows relative to the listing day T0 (first trading close):
  pre  = close T-11 -> close T-1   (10 sessions before)
  day0 = close T-1  -> close T0
  post = close T0   -> close T+5
  late = close T+5  -> close T+20
Significance: permutation test. 10,000 draws of 11 random dates (2020-06 to 2026-11) give the null
distribution of the 11-event average; p = two-sided share of draws at least as far from the null mean.
Also a cumulative event-time path T-10..T+20 with a bootstrap 90% band across events.
Hourly: for listings with Yahoo 60m data, asset return in the IPO's first trading hour and the hour
after, versus the same clock hour on the prior 20 sessions (abnormal = event bar - mean of those).
Anthropic: each asset's 14-session return into 13 Nov 2026 ranked against every 14-session window
since 2020 (empirical percentile).
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

DATA = Path(__file__).parent / "data"
RNG = np.random.default_rng(11)
EVENTS = [("2020-09-16", "Snowflake", 3.4), ("2020-12-09", "DoorDash + Airbnb", 6.9), ("2021-03-11", "Coupang", 4.6),
          ("2021-07-29", "Robinhood", 2.1), ("2021-11-10", "Rivian", 11.9), ("2023-09-14", "Arm", 4.9),
          ("2024-07-25", "Lineage", 4.4), ("2025-03-28", "CoreWeave", 1.5), ("2025-12-17", "Medline", 6.3),
          ("2026-06-12", "SpaceX", 75.0), ("2026-07-10", "SK hynix ADR", 26.5)]
ASSETS = {"S&P 500 (SPY)": ("SPY", "pct"), "Nasdaq 100 (QQQ)": ("QQQ", "pct"), "Small caps (IWM)": ("IWM", "pct"),
          "Speculative growth (ARKK)": ("ARKK", "pct"), "Semis (SMH)": ("SMH", "pct"), "Software (IGV)": ("IGV", "pct"),
          "Bitcoin": ("BTC-USD", "pct"), "Gold (GLD)": ("GLD", "pct"), "Long Treasuries (TLT)": ("TLT", "pct"),
          "Dollar (UUP)": ("UUP", "pct"), "High yield (HYG)": ("HYG", "pct"), "VIX (points)": ("^VIX", "pts"),
          "US 10Y (bp)": ("^TNX", "bp"), "Recent IPOs (IPO ETF)": ("IPO", "pct")}
WIN = {"pre": (-11, -1), "day0": (-1, 0), "post": (0, 5), "late": (5, 20)}
WLAB = {"pre": "T-10 to T-1", "day0": "Listing day", "post": "T+1 to T+5", "late": "T+6 to T+20"}


def chg(s, i0, i1, kind):
    a, b = s.iloc[i0], s.iloc[i1]
    return (b - a) * (100 if kind == "bp" else 1) if kind in ("pts", "bp") else b / a - 1


def main():
    tick = [v[0] for v in ASSETS.values()]
    px = yf.download(tick, start="2020-03-01", progress=False, auto_adjust=True)["Close"]
    cal = px["SPY"].dropna().index
    px = px.reindex(cal).ffill()
    lo, hi = cal.get_loc(cal[cal >= "2020-06-01"][0]), len(cal) - 21
    ev_idx = [cal.get_indexer([pd.Timestamp(d)], method="bfill")[0] for d, *_ in EVENTS]

    daily, paths = {}, {}
    for name, (t, kind) in ASSETS.items():
        s = px[t]
        res = {}
        for w, (a, b) in WIN.items():
            evv = np.array([chg(s, i + a, i + b, kind) for i in ev_idx], float)
            allv = np.array([chg(s, i + a, i + b, kind) for i in range(lo, hi)], float)
            allv = allv[~np.isnan(allv)]
            ok = ~np.isnan(evv)
            draws = RNG.choice(allv, (10_000, ok.sum())).mean(axis=1)
            mu0 = allv.mean()
            p = float((np.abs(draws - mu0) >= abs(evv[ok].mean() - mu0)).mean())
            res[w] = dict(values=[None if np.isnan(x) else float(x) for x in evv], mean=float(np.nanmean(evv)), median=float(np.nanmedian(evv)),
                          hit=float((evv[ok] > 0).mean()), null_mean=float(mu0), p_perm=p, excess=float(evv[ok].mean() - mu0),
                          spacex=float(evv[-2]) if ok[-2] else None)
        daily[name] = res
        # event-time cumulative path T-10..T+20, relative to close T-11
        M = []
        for i in ev_idx:
            base = s.iloc[i - 11]
            seg = s.iloc[i - 11:i + 21].values
            M.append((seg - base) * (100 if kind == "bp" else 1) if kind in ("pts", "bp") else seg / base - 1)
        M = np.array(M, float)
        band = []
        for k in range(M.shape[1]):
            col = M[:, k][~np.isnan(M[:, k])]
            bs = RNG.choice(col, (5000, len(col))).mean(axis=1)
            band.append(dict(t=k - 10, mean=float(col.mean()), lo=float(np.percentile(bs, 5)), hi=float(np.percentile(bs, 95))))
        sp = M[-2]
        paths[name] = dict(band=band, spacex=[None if np.isnan(x) else float(x) for x in sp])

    # cross-asset trades around listings (per-event), with permutation p from above
    trades = []
    for name in ["Bitcoin", "Speculative growth (ARKK)", "Gold (GLD)", "Nasdaq 100 (QQQ)", "Semis (SMH)", "Software (IGV)", "Recent IPOs (IPO ETF)"]:
        for w, sign, lab, hold in [("pre", -1, "Short T-10 to T-1", 10), ("post", 1, "Long T+1 to T+5", 5), ("late", 1, "Long T+6 to T+20", 15)]:
            v = np.array([x for x in daily[name][w]["values"] if x is not None]) * sign
            ex = v - sign * daily[name][w]["null_mean"]
            sr = v.mean() / v.std(ddof=1)
            trades.append(dict(asset=name, trade=lab, n=len(v), mean=float(v.mean()), excess_vs_typical=float(ex.mean()), hit=float((v > 0).mean()),
                               p_perm=daily[name][w]["p_perm"], sr_trade=float(sr), sr_ann_equiv=float(sr * np.sqrt(252 / hold)),
                               sr_realistic=float(sr * np.sqrt(len(EVENTS) / 6.2))))

    # Anthropic run-up percentile: 14 sessions to 13 Nov 2026
    end = cal.get_loc(cal[cal <= "2026-11-13"][-1])
    runup = []
    for name, (t, kind) in ASSETS.items():
        s = px[t]
        v = chg(s, end - 14, end, kind)
        allv = np.array([chg(s, i - 14, i, kind) for i in range(lo + 14, end + 1)], float)
        allv = allv[~np.isnan(allv)]
        runup.append(dict(asset=name, value=float(v), pct_rank=float((allv < v).mean()), z=float((v - allv.mean()) / allv.std())))

    # ---------------- hourly ----------------
    hourly = []
    HA = {"QQQ": "QQQ", "SPY": "SPY", "Bitcoin": "BTC-USD", "Gold (GLD)": "GLD", "ARKK": "ARKK", "IWM": "IWM"}
    hev = [("CRWV", "CoreWeave", 1.5), ("MDLN", "Medline", 6.3), ("SPCX", "SpaceX", 75.0), ("SKHY", "SK hynix ADR", 26.5),
           ("FIG", "Figma", 1.2), ("CRCL", "Circle", 1.05), ("KLAR", "Klarna", 1.37), ("CHYM", "Chime", 0.86), ("VG", "Venture Global", 1.75),
           ("SAIL", "SailPoint", 1.38), ("NTSK", "Netskope", 0.91), ("STUB", "StubHub", 0.8), ("ETOR", "eToro", 0.62), ("FIGR", "Figure", 0.79),
           ("GEMI", "Gemini", 0.43), ("HNGE", "Hinge Health", 0.44)]
    H = {}
    for k, t in HA.items():
        h = yf.Ticker(t).history(period="730d", interval="60m")
        h.index = h.index.tz_convert("America/New_York")
        H[k] = h
    spx_path = {}
    for tk, nm, deal in hev:
        ih = yf.Ticker(tk).history(period="730d", interval="60m")
        ih.index = ih.index.tz_convert("America/New_York")
        ih = ih[ih.Volume > 0]
        if ih.empty:
            continue
        t_open = ih.index[0]
        ipo_daily = yf.Ticker(tk).history(period="max").index[0].date()
        if t_open.date() != ipo_daily:
            continue  # hourly feed missing the debut session
        row = dict(ticker=tk, name=nm, deal_b=deal, open_bar=t_open.strftime("%Y-%m-%d %H:%M"))
        for k, h in H.items():
            key = t_open.floor("h") if k == "Bitcoin" else t_open  # crypto bars start on the hour
            hh = h[(h.index.time == key.time()) & (h.index.dayofweek < 5)]
            hist = hh[(hh.index < key)].tail(20)
            bar = h.loc[h.index == key]
            nxt = h[h.index > t_open].head(1)
            if bar.empty or hist.empty:
                continue
            r0 = float(bar.Close.iloc[0] / bar.Open.iloc[0] - 1)
            base = float((hist.Close / hist.Open - 1).mean())
            row[k] = dict(bar=r0, abn=r0 - base, sd=float((hist.Close / hist.Open - 1).std()),
                          next=float(nxt.Close.iloc[0] / nxt.Open.iloc[0] - 1) if not nxt.empty else None)
        hourly.append(row)
        if tk == "SPCX":  # hourly path T-1 .. T+4 sessions for QQQ, Bitcoin, Gold
            d0 = t_open.normalize()
            for k in ["QQQ", "Bitcoin", "Gold (GLD)", "ARKK"]:
                h = H[k]
                seg = h[(h.index >= d0 - pd.Timedelta(days=4)) & (h.index <= d0 + pd.Timedelta(days=8))]
                if k == "Bitcoin":
                    seg = seg[(seg.index.hour >= 9) & (seg.index.hour <= 15) & (seg.index.dayofweek < 5)]
                spx_path[k] = [dict(ts=i.strftime("%m-%d %H:%M"), v=float(c)) for i, c in seg.Close.items()]
    def agg(rows, key):
        v = np.array([r[key]["abn"] for r in rows if key in r], float)
        z = np.array([r[key]["abn"] / r[key]["sd"] for r in rows if key in r and r[key]["sd"] > 0], float)
        return dict(n=len(v), mean_abn=float(v.mean()), hit_neg=float((v < 0).mean()), mean_z=float(z.mean()),
                    t=float(z.mean() / (z.std(ddof=1) / np.sqrt(len(z)))) if len(z) > 2 else None)
    big = [r for r in hourly if r["deal_b"] >= 1.4]
    hsum = {k: dict(all=agg(hourly, k), big=agg(big, k)) for k in HA}

    out = dict(events=[dict(date=d, name=n, deal_b=b) for d, n, b in EVENTS], windows=WLAB, daily=daily, paths=paths, trades=trades,
               runup=runup, hourly=hourly, hourly_summary=hsum, spacex_hourly=spx_path)
    json.dump(out, open(DATA / "xasset.json", "w"), default=float)

    pd.set_option("display.width", 250)
    print("DAILY mean (excess vs typical), p_perm")
    for name, r in daily.items():
        print(f"{name:28s}", "  ".join(f"{w}: {r[w]['mean']*(1 if 'VIX' in name or '10Y' in name else 100):+6.2f} (ex {r[w]['excess']*(1 if 'VIX' in name or '10Y' in name else 100):+5.2f}, p={r[w]['p_perm']:.2f}, SpX {('%.2f'% (r[w]['spacex']*(1 if 'VIX' in name or '10Y' in name else 100))) if r[w]['spacex'] is not None else 'na'})" for w in WIN))
    print("\nTRADES"); print(pd.DataFrame(trades).round(3).to_string(index=False))
    print("\nRUNUP"); print(pd.DataFrame(runup).round(3).to_string(index=False))
    print("\nHOURLY summary"); print(json.dumps(hsum, indent=0)[:1500])
    print([ (r["ticker"], r["open_bar"], round(r.get("QQQ",{}).get("abn",np.nan)*100,2), round(r.get("Bitcoin",{}).get("abn",np.nan)*100,2)) for r in hourly])


if __name__ == "__main__":
    main()
