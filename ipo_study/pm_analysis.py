"""Prediction markets: what Polymarket and Kalshi expect for the Anthropic IPO, and a SpaceX calibration.

Usage: python3 ipo_study/pm_analysis.py  -> ipo_study/data/pm.json (+ prints)
Inputs: data/raw/pm/search_0.json (Polymarket event snapshot, 15 Nov 2026), data/raw/pm/hist/<token>.json
        (CLOB price histories), data/raw/pm/kalshi_ipoanthropic.json, data/raw/pm/anthropic_tokens.json

Definitions (from the market rules):
  closing market cap = basic shares outstanding x day-1 closing price
  IPO valuation       = fully diluted shares x final offer price
  % sold              = shares sold (ex greenshoe) / Class A + Class N shares outstanding after the offering
  amount raised       = gross proceeds ex greenshoe
Fully diluted shares are taken as 18.0bn (press-reported $1.33tn at $74 and $1.404tn at $78 both imply ~18.0bn).
Bracket probabilities are mid prices normalised to sum to one; values are spread uniformly inside each bracket.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

DATA = Path(__file__).parent / "data"
RAW = DATA / "raw" / "pm"
RNG = np.random.default_rng(41)
FD_SHARES = 18.0e9
SHARES_SOLD = 825e6
EV = json.load(open(RAW / "search_0.json"))


def event(slug):
    return next(e for e in EV if e["slug"] == slug)


def yes(m):
    op = m.get("outcomePrices"); op = json.loads(op) if isinstance(op, str) else op
    bid, ask = m.get("bestBid"), m.get("bestAsk")
    return float((bid + ask) / 2) if bid is not None and ask is not None else float(op[0])


def dist(slug, edges, drop=("No IPO",)):
    e = event(slug); rows = []
    for m in e["markets"]:
        lab = m.get("groupItemTitle")
        if any(lab.startswith(d) for d in drop):
            continue
        rows.append((lab, yes(m), float(m.get("volume") or 0)))
    p = np.array([r[1] for r in rows]); raw = p.sum(); p = p / p.sum()
    return dict(labels=[r[0] for r in rows], p=p, edges=edges, overround=float(raw), volume=float(sum(r[2] for r in rows)))


def sample(d, n):
    idx = RNG.choice(len(d["p"]), n, p=d["p"])
    lo = np.array([d["edges"][i][0] for i in idx]); hi = np.array([d["edges"][i][1] for i in idx])
    return lo + RNG.random(n) * (hi - lo)


def summ(x):
    return dict(mean=float(np.mean(x)), median=float(np.median(x)), p10=float(np.percentile(x, 10)), p25=float(np.percentile(x, 25)),
                p75=float(np.percentile(x, 75)), p90=float(np.percentile(x, 90)))


def main():
    N = 400_000
    # closing market cap ($tn); refine the <$1.25T bucket with the middle-bracket market
    cc = dist("anthropic-ipo-closing-market-cap-higher-strikes",
              [(0.9, 1.25), (1.25, 1.5), (1.5, 1.75), (1.75, 2.0), (2.0, 2.25), (2.25, 2.5), (2.5, 2.75), (2.75, 3.0), (3.0, 3.5)])
    mid = dist("anthropic-ipo-closing-market-cap-979", [(0.4, 0.6), (0.6, 0.9), (0.9, 1.2), (1.2, 1.5), (1.5, 1.8), (1.8, 2.5)])
    low_mass = cc["p"][0]
    w = np.array([mid["p"][0], mid["p"][1], mid["p"][2], mid["p"][3] * (0.05 / 0.3)]); w = w / w.sum() * low_mass
    ccx = dict(labels=["<0.6T", "0.6-0.9T", "0.9-1.2T", "1.2-1.25T"] + cc["labels"][1:],
               p=np.r_[w, cc["p"][1:]], edges=[(0.45, 0.6), (0.6, 0.9), (0.9, 1.2), (1.2, 1.25)] + cc["edges"][1:])
    ccx["p"] = ccx["p"] / ccx["p"].sum()
    close_cap = sample(ccx, N) * 1e12
    val = dist("what-will-anthropics-ipo-valuation-be", [(1.15, 1.25), (1.25, 1.5), (1.5, 1.75), (1.75, 2.0), (2.0, 2.25), (2.25, 2.5), (2.5, 3.0)])
    valuation = sample(val, N) * 1e12
    raise_ = dist("how-much-will-anthropic-raise-in-its-ipo", [(55, 65), (65, 75), (75, 85), (85, 95), (95, 105), (105, 115), (115, 125), (125, 135), (135, 150)])
    proceeds = sample(raise_, N) * 1e9
    pct = dist("what-percent-of-anthropic-will-be-sold-in-its-ipo", [(0.035, 0.04), (0.04, 0.05), (0.05, 0.06), (0.06, 0.07), (0.07, 0.08), (0.08, 0.09),
                                                                       (0.09, 0.10), (0.10, 0.11), (0.11, 0.12), (0.12, 0.14)])
    pct_sold = sample(pct, N)

    offer_from_val = valuation / FD_SHARES
    offer_from_raise = proceeds / SHARES_SOLD
    basic = SHARES_SOLD / pct_sold
    close_px = close_cap / basic
    pop = close_cap * pct_sold / proceeds - 1  # closing cap / (offer x basic shares) - 1, using offer x basic = proceeds / % sold
    # direct binary markets
    def b(slug):
        return yes(event(slug)["markets"][0])
    direct = dict(close_above_offer=b("anthropic-ipo-closing-price-above-ipo-price-on-first-day"), open_above_offer=b("anthropic-ipo-open-price-above-ipo-price"),
                  flip_btc=b("will-anthropic-flip-btc-by-december-31"))
    date = dist("anthropic-ipo-date", [(i, i + 1) for i in range(12)])
    kal = json.load(open(RAW / "kalshi_ipoanthropic.json"))
    kalshi = {m["yes_sub_title"]: dict(bid=float(m["yes_bid_dollars"]), ask=float(m["yes_ask_dollars"]), last=float(m["last_price_dollars"]), volume=float(m["volume_fp"]))
              for m in kal["events"][0]["markets"] if m["status"] == "active"}

    out = dict(
        snapshot="15 Nov 2026 (Polymarket mid prices; Kalshi bid/ask)",
        closing_cap=dict(labels=ccx["labels"], p=ccx["p"].tolist(), overround=cc["overround"], volume=cc["volume"], summary=summ(close_cap / 1e12)),
        valuation=dict(labels=val["labels"], p=val["p"].tolist(), volume=val["volume"], summary=summ(valuation / 1e12)),
        raised=dict(labels=raise_["labels"], p=raise_["p"].tolist(), volume=raise_["volume"], summary=summ(proceeds / 1e9)),
        pct_sold=dict(labels=pct["labels"], p=pct["p"].tolist(), summary=summ(pct_sold)),
        offer_from_valuation=summ(offer_from_val), offer_from_raise=summ(offer_from_raise),
        p_above_range_val=float((offer_from_val > 78).mean()), p_above_range_raise=float((offer_from_raise > 78).mean()),
        p_below_range_val=float((offer_from_val < 70).mean()),
        basic_shares_bn=summ(basic / 1e9), close_price=summ(close_px), pop=summ(pop), p_pop_pos=float((pop > 0).mean()),
        pop_quantiles={q: float(np.percentile(pop, q)) for q in [5, 10, 25, 50, 75, 90, 95]},
        point=dict(offer=float(np.mean(offer_from_raise)), basic_bn=float(SHARES_SOLD / np.mean(pct_sold) / 1e9), close_cap_tn=float(np.mean(close_cap) / 1e12)),
        direct=direct, date=dict(labels=date["labels"], p=date["p"].tolist()), kalshi=kalshi,
    )
    out["point"]["close_px"] = out["point"]["close_cap_tn"] * 1e12 / (out["point"]["basic_bn"] * 1e9)
    out["point"]["pop"] = out["point"]["close_px"] / out["point"]["offer"] - 1

    # ---------------- history of expectations ----------------
    toks = json.load(open(RAW / "anthropic_tokens.json"))
    def hist_ev(prefix, edges, labels_order):
        series = {}
        for lab in labels_order:
            tok = toks.get(f"{prefix}|{lab}")
            f = RAW / "hist" / f"{tok}.json"
            if tok and f.exists():
                h = pd.DataFrame(json.load(open(f)))
                if len(h):
                    s = pd.Series(h.p.values, index=pd.to_datetime(h.t, unit="s")).resample("D").last()
                    series[lab] = s
        df = pd.DataFrame(series).ffill().dropna(how="all")
        df = df[[c for c in labels_order if c in df]]
        mids = np.array([np.mean(edges[labels_order.index(c)]) for c in df.columns])
        P = df.fillna(0).values; P = P / P.sum(axis=1, keepdims=True)
        evs = P @ mids
        return pd.Series(evs, index=df.index), df
    cc_labels = cc["labels"]
    ev_cc, df_cc = hist_ev("anthropic-ipo-closing-market-cap-higher-strikes", [(1.0, 1.25)] + cc["edges"][1:], cc_labels)
    val_labels = val["labels"]
    ev_val, df_val = hist_ev("what-will-anthropics-ipo-valuation-be", val["edges"], val_labels)
    out["history"] = dict(cc_dates=[d.strftime("%Y-%m-%d") for d in ev_cc.index], cc_ev=ev_cc.round(4).tolist(),
                          val_dates=[d.strftime("%Y-%m-%d") for d in ev_val.index], val_ev=ev_val.round(4).tolist(),
                          cc_p_above_1_5=(df_cc[[c for c in df_cc if c not in ("<$1.25T", "$1.25–$1.5T")]].sum(axis=1) / df_cc.sum(axis=1)).round(4).tolist())
    def at(s, d):
        s2 = s.loc[:d]
        return float(s2.iloc[-1]) if len(s2) else None
    out["milestones"] = {lab: dict(cc_ev=at(ev_cc, d), val_ev=at(ev_val, d)) for lab, d in
                         [("1 Oct 2026", "2026-10-01"), ("S-1 public, 26 Oct", "2026-10-26"), ("Range set, 10 Nov", "2026-11-10"), ("Latest, 15 Nov", "2026-11-15")]}

    # ---------------- SpaceX calibration (end-of-IPO-month market cap market) ----------------
    sx_edges = [(0.8, 1.0), (1.0, 1.5), (1.5, 2.0), (2.0, 2.5), (2.5, 3.0), (3.0, 3.5), (3.5, 4.0)]
    sx_labels = ["<$1.0T", "$1.0-1.5T", "$1.5-2.0T", "$2.0-2.5T", "$2.5-3.0T", "$3.0-3.5T", "$3.5T+"]
    pre = np.array([0.105, 0.115, 0.155, 0.505, 0.20, 0.055, 0.0885])   # 00:00 UTC 12 Jun 2026: after pricing, before trading
    post = np.array([0.05, 0.139, 0.305, 0.455, 0.0705, 0.0065, 0.007])  # 00:00 UTC 13 Jun 2026: after the first close
    mids = np.array([np.mean(e) for e in sx_edges])
    def sxs(p):
        q = p / p.sum(); return dict(p=q.tolist(), ev=float(q @ mids), p_realised=float(q[3]), overround=float(p.sum()))
    shares_sx = 1.77e12 / 135
    out["spacex"] = dict(labels=sx_labels, pre=sxs(pre), post=sxs(post), realised_bracket="$2.0-2.5T", day1_close_cap=160.95 * shares_sx / 1e12,
                         june30_close=None, offer=135.0, note="Market resolved on the end-of-June close; day-1 close cap from $160.95 x 13.1bn shares.")
    json.dump(out, open(DATA / "pm.json", "w"), default=float)

    print("closing cap EV/median ($tn):", {k: round(v, 3) for k, v in out["closing_cap"]["summary"].items()}, "overround", round(cc["overround"], 3), "vol $m", round(cc["volume"] / 1e6, 1))
    print("valuation ($tn):", {k: round(v, 3) for k, v in out["valuation"]["summary"].items()})
    print("raised ($bn):", {k: round(v, 1) for k, v in out["raised"]["summary"].items()}, "| % sold:", {k: round(v * 100, 2) for k, v in out["pct_sold"]["summary"].items()})
    print("offer from valuation:", {k: round(v, 1) for k, v in out["offer_from_valuation"].items()}, "P(>78)", round(out["p_above_range_val"], 3), "P(<70)", round(out["p_below_range_val"], 3))
    print("offer from raise:", {k: round(v, 1) for k, v in out["offer_from_raise"].items()}, "P(>78)", round(out["p_above_range_raise"], 3))
    print("basic shares bn:", {k: round(v, 2) for k, v in out["basic_shares_bn"].items()})
    print("close price:", {k: round(v, 1) for k, v in out["close_price"].items()})
    print("pop:", {k: round(v * 100, 1) for k, v in out["pop"].items()}, "P(pop>0)", round(out["p_pop_pos"], 3), "| direct close>offer", direct)
    print("point estimate:", {k: round(v, 3) for k, v in out["point"].items()})
    print("milestones:", out["milestones"])
    print("SpaceX:", {k: (round(v['ev'], 3), round(v['p_realised'], 3), round(v['overround'], 3)) for k, v in [("pre", out['spacex']['pre']), ("post", out['spacex']['post'])]}, "day1 cap", round(out["spacex"]["day1_close_cap"], 3))
    print("Kalshi:", kalshi)


if __name__ == "__main__":
    main()
