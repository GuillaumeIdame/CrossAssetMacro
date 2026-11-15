"""Does positioning explain the mega-IPO cross-asset pattern?

Hypothesis (SpaceX, Anthropic): large IPOs hit risky assets only when the market is stretched:
low realised vol (vol-targeting leverage high), strong momentum, crowded high-beta / momentum
longs, complacent vol curve, high leveraged-fund futures exposure, fast margin-debt growth.

Usage:  python3 ipo_study/positioning.py   -> ipo_study/data/positioning.json (+ prints)

State variables (measured at T-11, the close before the pre-listing window; all backward-looking):
  rv21       S&P 500 21-day realised vol (annualised)           low  = stretched
  mom63      S&P 500 63-day return                              high = stretched
  vix_term   VIX / VIX3M                                        low  = stretched (steep contango)
  beta63     SPHB / SPLV 63-day relative return (high beta vs low vol)   high = stretched
  mtum63     MTUM / SPY 63-day relative return (momentum crowding)       high = stretched
  btc_mom63  Bitcoin 63-day return                              high = stretched
  lev_net    CFTC leveraged funds net long / open interest, E-mini S&P (weekly, used 3 days after the Tuesday report date)
  am_net     CFTC asset managers net long / open interest
  margin_yoy Fed Z.1 margin accounts at brokers, YoY growth (quarterly, used ~100 days after quarter start)
  PSI        positioning stretch index = mean z-score of (-rv21, mom63, -vix_term, beta63, btc_mom63)
Tests
  1. State-matched placebo: event-window move vs random dates drawn from days in the same PSI half.
  2. Panel regression on every day (2020-06 to 2026-10): y = a + b*PSI + c*Event + d*Event*PSI, Newey-West SEs.
  3. Spearman correlation across events between PSI (and each state variable) and the window move.
  4. Cross-asset momentum long-short (top-4 minus bottom-4 of 12 assets by 63-day return) around events.
  5. IPO-stock outcomes against the state at listing (43 IPOs).
"""
import json
from io import StringIO
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import statsmodels.api as sm
import yfinance as yf
from scipy import stats

DATA = Path(__file__).parent / "data"
RNG = np.random.default_rng(21)

# large listings, proceeds >= $1bn; listings within the same week merged (proceeds summed)
EVENTS = [("2020-09-16", "Snowflake + Unity", 4.66), ("2020-12-09", "DoorDash + Airbnb", 6.86), ("2021-01-13", "Affirm", 1.21),
          ("2021-02-11", "Bumble", 2.15), ("2021-03-03", "Oscar Health", 1.42), ("2021-03-11", "Coupang", 4.55), ("2021-07-29", "Robinhood", 2.09),
          ("2021-11-10", "Rivian", 11.93), ("2023-09-14", "Arm", 4.87), ("2023-10-11", "Birkenstock", 1.48), ("2024-05-01", "Viking", 1.54),
          ("2024-07-25", "Lineage", 4.44), ("2024-10-02", "StandardAero", 1.44), ("2025-01-24", "Venture Global", 1.75), ("2025-02-13", "SailPoint", 1.38),
          ("2025-03-28", "CoreWeave", 1.50), ("2025-06-05", "Circle", 1.05), ("2025-07-31", "Figma", 1.22), ("2025-09-10", "Klarna + Figure + Gemini", 2.58),
          ("2025-12-17", "Medline", 6.27), ("2026-06-12", "SpaceX", 75.0), ("2026-07-10", "SK hynix ADR", 26.5)]
ANT_T0 = "2026-11-19"
ASSETS = {"S&P 500": "SPY", "Nasdaq 100": "QQQ", "Small caps": "IWM", "Spec. growth (ARKK)": "ARKK", "Semis": "SMH", "Software": "IGV",
          "Bitcoin": "BTC-USD", "Gold": "GLD", "Long Treasuries": "TLT", "High yield": "HYG", "Dollar": "UUP", "MSTR": "MSTR"}
FACTORS = {"High beta - low vol": ("SPHB", "SPLV"), "Momentum - market": ("MTUM", "SPY")}
WIN = {"pre": (0, 10), "post": (10, 16), "late": (16, 31)}  # offsets from s = T-11: pre = T-11..T-1, post = T-1..T+5, late = T+5..T+20
WLAB = {"pre": "T-10 to T-1", "post": "Listing day to T+5", "late": "T+6 to T+20"}


def fred(sid):
    t = requests.get(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}", timeout=30).text
    s = pd.read_csv(StringIO(t), index_col=0, parse_dates=True).iloc[:, 0]
    return pd.to_numeric(s, errors="coerce").dropna()


def main():
    tick = sorted(set(list(ASSETS.values()) + [x for p in FACTORS.values() for x in p] + ["^VIX", "^VIX3M", "^GSPC"]))
    px = yf.download(tick, start="2019-06-01", progress=False, auto_adjust=True)["Close"]
    cal = px["SPY"].dropna().index
    px = px.reindex(cal).ffill()
    lr = np.log(px)

    # ---------------- state variables ----------------
    st = pd.DataFrame(index=cal)
    r = px["^GSPC"].pct_change()
    st["rv21"] = r.rolling(21).std() * np.sqrt(252)
    st["mom63"] = px["^GSPC"] / px["^GSPC"].shift(63) - 1
    st["vix_term"] = px["^VIX"] / px["^VIX3M"]
    st["beta63"] = (px["SPHB"] / px["SPLV"]) / (px["SPHB"] / px["SPLV"]).shift(63) - 1
    st["mtum63"] = (px["MTUM"] / px["SPY"]) / (px["MTUM"] / px["SPY"]).shift(63) - 1
    st["btc_mom63"] = px["BTC-USD"] / px["BTC-USD"].shift(63) - 1
    st["btc_rv30"] = px["BTC-USD"].pct_change().rolling(30).std() * np.sqrt(365)
    cf = pd.DataFrame(json.load(open(DATA / "raw" / "cftc_es_tff.json")))
    cf["d"] = pd.to_datetime(cf.report_date_as_yyyy_mm_dd.str[:10]) + pd.Timedelta(days=3)  # published Friday
    for c in ["lev_money_positions_long", "lev_money_positions_short", "asset_mgr_positions_long", "asset_mgr_positions_short", "open_interest_all"]:
        cf[c] = cf[c].astype(float)
    cf["lev_net"] = (cf.lev_money_positions_long - cf.lev_money_positions_short) / cf.open_interest_all
    cf["am_net"] = (cf.asset_mgr_positions_long - cf.asset_mgr_positions_short) / cf.open_interest_all
    cf = cf.set_index("d")[["lev_net", "am_net"]].sort_index()
    st = st.join(cf.reindex(cal, method="ffill"))
    mg = fred("BOGZ1FL663067003Q")
    mg_yoy = (mg / mg.shift(4) - 1)
    mg_yoy.index = mg_yoy.index + pd.Timedelta(days=100)  # Z.1 publication lag
    st["margin_yoy"] = mg_yoy.reindex(cal, method="ffill")
    samp = st.loc["2020-06-01":"2026-11-13"]
    z = (samp - samp.mean()) / samp.std()
    st_z = (st - samp.mean()) / samp.std()
    st["PSI"] = pd.concat([-st_z.rv21, st_z.mom63, -st_z.vix_term, st_z.beta63, st_z.btc_mom63], axis=1).mean(axis=1)
    pct = lambda col, v: float((samp[col].dropna() < v).mean()) if col != "PSI" else float((st.loc["2020-06-01":"2026-11-13", "PSI"].dropna() < v).mean())

    # ---------------- series for outcomes ----------------
    ser = {k: lr[v] for k, v in ASSETS.items()}
    for k, (a, b) in FACTORS.items():
        ser[k] = lr[a] - lr[b]
    mom_univ = ["SPY", "QQQ", "IWM", "ARKK", "SMH", "IGV", "BTC-USD", "GLD", "TLT", "HYG", "UUP", "MSTR"]

    lo = cal.get_loc(cal[cal >= "2020-06-01"][0])
    last_s = len(cal) - 32
    idx_all = np.arange(lo, last_s)
    ev_s = []  # index of T-11
    for d, *_ in EVENTS:
        t0 = cal.get_indexer([pd.Timestamp(d)], method="bfill")[0]
        ev_s.append(t0 - 11)
    ev_s = np.array(ev_s)

    def win_ret(series, s, w):
        a, b = WIN[w]
        return float(series.iloc[s + b] - series.iloc[s + a])

    def momls(s, w):
        a, b = WIN[w]
        m = (px[mom_univ].iloc[s] / px[mom_univ].iloc[s - 63] - 1).sort_values()
        top, bot = m.index[-4:], m.index[:4]
        rr = np.log(px[mom_univ].iloc[s + b] / px[mom_univ].iloc[s + a])
        return float(rr[top].mean() - rr[bot].mean())

    psi = st["PSI"]
    hi_days = np.array([i for i in idx_all if psi.iloc[i] >= psi.iloc[idx_all].median()])
    lo_days = np.array([i for i in idx_all if psi.iloc[i] < psi.iloc[idx_all].median()])
    ev_hi = np.array([psi.iloc[s] >= psi.iloc[idx_all].median() for s in ev_s])

    # ---------------- 1. event state table ----------------
    cols = ["rv21", "mom63", "vix_term", "beta63", "mtum63", "btc_mom63", "lev_net", "am_net", "margin_yoy", "PSI"]
    states = []
    for (d, n, p), s in zip(EVENTS, ev_s):
        row = dict(date=d, name=n, proceeds_b=p, s_date=str(cal[s].date()))
        for c in cols:
            v = st[c].iloc[s]; row[c] = None if pd.isna(v) else float(v); row[c + "_pct"] = None if pd.isna(v) else pct(c, v)
        states.append(row)
    t0a = cal.get_indexer([pd.Timestamp("2026-11-13")], method="ffill")[0]  # latest data; ANT T-11 = 3 Nov 2026
    s_ant = cal.get_indexer([pd.Timestamp("2026-11-03")], method="ffill")[0]
    ant = {}
    for lab, s in [("Anthropic, T-11 (3 Nov 2026)", s_ant), ("Latest (13 Nov 2026)", t0a), ("Anthropic S-1 public (26 Oct 2026)", cal.get_indexer([pd.Timestamp("2026-10-26")], method="ffill")[0])]:
        row = {}
        for c in cols:
            v = st[c].iloc[s]; row[c] = None if pd.isna(v) else float(v); row[c + "_pct"] = None if pd.isna(v) else pct(c, v)
        ant[lab] = row

    # ---------------- 2. responses, split by state, matched placebo ----------------
    resp = {}
    for k, sr in list(ser.items()) + [("Cross-asset momentum L/S", None)]:
        res = {}
        for w in WIN:
            f = (lambda s: momls(s, w)) if sr is None else (lambda s: win_ret(sr, s, w))
            ev = np.array([f(s) for s in ev_s])
            null_all = np.array([f(s) for s in idx_all[::2]])  # every other day keeps it fast
            null_hi = np.array([f(s) for s in hi_days[::2]]); null_lo = np.array([f(s) for s in lo_days[::2]])
            def perm(vals, null):
                vals = vals[~np.isnan(vals)]; null = null[~np.isnan(null)]
                dr = RNG.choice(null, (5000, len(vals))).mean(axis=1)
                return float((np.abs(dr - null.mean()) >= abs(vals.mean() - null.mean())).mean())
            e_hi, e_lo = ev[ev_hi], ev[~ev_hi]
            rho, prho = stats.spearmanr([psi.iloc[s] for s in ev_s], ev)
            res[w] = dict(all=float(np.nanmean(ev)), p_all=perm(ev, null_all), null_all=float(np.nanmean(null_all)),
                          hi=float(np.nanmean(e_hi)), n_hi=int(len(e_hi)), null_hi=float(np.nanmean(null_hi)), p_hi=perm(e_hi, null_hi),
                          lo=float(np.nanmean(e_lo)), n_lo=int(len(e_lo)), null_lo=float(np.nanmean(null_lo)), p_lo=perm(e_lo, null_lo),
                          rho_psi=float(rho), p_rho=float(prho), values=[float(x) for x in ev])
        resp[k] = res

    # ---------------- 3. panel regression with HAC ----------------
    reg = {}
    E = np.zeros(len(cal)); E[ev_s] = 1
    for k in ["S&P 500", "Nasdaq 100", "Small caps", "Spec. growth (ARKK)", "Bitcoin", "Gold", "High beta - low vol", "Momentum - market", "Cross-asset momentum L/S"]:
        sr = ser.get(k)
        for w in ["pre", "post", "late"]:
            ys, xs = [], []
            for s in idx_all:
                y = momls(s, w) if sr is None else win_ret(sr, s, w)
                if np.isnan(y) or np.isnan(psi.iloc[s]):
                    continue
                ys.append(y); xs.append([psi.iloc[s], E[s], E[s] * psi.iloc[s]])
            X = sm.add_constant(np.array(xs)); m = sm.OLS(np.array(ys), X).fit(cov_type="HAC", cov_kwds={"maxlags": WIN[w][1] - WIN[w][0]})
            reg[f"{k}|{w}"] = dict(asset=k, window=w, b_psi=float(m.params[1]), t_psi=float(m.tvalues[1]), c_event=float(m.params[2]), t_event=float(m.tvalues[2]),
                                   d_inter=float(m.params[3]), t_inter=float(m.tvalues[3]), p_inter=float(m.pvalues[3]), n=int(m.nobs), r2=float(m.rsquared))

    # ---------------- 4. per-variable correlation across events (pre window, risk assets) ----------------
    var_corr = []
    for c in cols:
        x = np.array([st[c].iloc[s] for s in ev_s], float)
        for k in ["Bitcoin", "Spec. growth (ARKK)", "Nasdaq 100", "High beta - low vol", "Cross-asset momentum L/S"]:
            for w in ["pre", "post"]:
                y = np.array(resp[k][w]["values"]); ok = ~np.isnan(x) & ~np.isnan(y)
                if ok.sum() >= 8:
                    rho, p = stats.spearmanr(x[ok], y[ok]); var_corr.append(dict(var=c, asset=k, window=w, n=int(ok.sum()), rho=float(rho), p=float(p)))

    # ---------------- 5. SpaceX / SK hynix / Anthropic: actual vs state-implied ----------------
    cases = []
    for name, s in [("SpaceX", ev_s[-2]), ("SK hynix ADR", ev_s[-1])]:
        row = dict(name=name, PSI=float(psi.iloc[s]), PSI_pct=pct("PSI", psi.iloc[s]))
        for k in ["Bitcoin", "Spec. growth (ARKK)", "Nasdaq 100", "Gold", "High beta - low vol", "Cross-asset momentum L/S"]:
            g = reg.get(f"{k}|pre")
            y = momls(s, "pre") if ser.get(k) is None else win_ret(ser[k], s, "pre")
            row[k] = dict(actual=y, implied_typical=float(np.nanmean([momls(i, "pre") if ser.get(k) is None else win_ret(ser[k], i, "pre") for i in (hi_days if psi.iloc[s] >= psi.iloc[idx_all].median() else lo_days)[::3]])))
        cases.append(row)
    # Anthropic run-up: 3 Nov -> 13 Nov (8 sessions of its pre-window so far)
    ant_move = {k: float(sr.iloc[t0a] - sr.iloc[s_ant]) for k, sr in ser.items()}

    # ---------------- 6. IPO stock outcomes vs state at listing ----------------
    co = pd.read_csv(DATA / "enriched_cohort.csv")
    rows = []
    for _, rr in co.iterrows():
        s = cal.get_indexer([pd.Timestamp(rr.ipo_date)], method="bfill")[0] - 1
        rows.append(dict(ticker=rr.ticker, PSI=psi.iloc[s], rv21=st.rv21.iloc[s], mom63=st.mom63.iloc[s], lev_net=st.lev_net.iloc[s], beta63=st.beta63.iloc[s],
                         pop=rr.d1_pop, r21=rr.r21, r63=rr.r63))
    ipo = pd.DataFrame(rows)
    ipo_corr = []
    for c in ["PSI", "rv21", "mom63", "beta63", "lev_net"]:
        for y in ["pop", "r21", "r63"]:
            ok = ipo[[c, y]].dropna(); rho, p = stats.spearmanr(ok[c], ok[y]); ipo_corr.append(dict(var=c, outcome=y, n=len(ok), rho=float(rho), p=float(p)))
    ipo["psi_hi"] = ipo.PSI >= ipo.PSI.median()
    ipo_split = {str(k): dict(n=int(len(g)), pop=float(g["pop"].median()), r21=float(g.r21.median()), r63=float(g.r63.median())) for k, g in ipo.groupby("psi_hi")}

    # time series for charts
    ts = st.loc["2020-06-01":, ["rv21", "mom63", "vix_term", "beta63", "btc_mom63", "lev_net", "am_net", "margin_yoy", "PSI"]].resample("W-FRI").last()
    out = dict(events=[dict(date=d, name=n, proceeds_b=p) for d, n, p in EVENTS], windows=WLAB, states=states, anthropic=ant, responses=resp, reg=reg,
               var_corr=var_corr, cases=cases, ant_move=ant_move, ipo_corr=ipo_corr, ipo_split=ipo_split, psi_median=float(psi.iloc[idx_all].median()),
               n_hi=int(ev_hi.sum()), ts=dict(dates=[d.strftime("%Y-%m-%d") for d in ts.index], **{c: [None if pd.isna(v) else float(v) for v in ts[c]] for c in ts.columns}),
               finra=[("Oct-25", 1183654), ("Nov-25", 1214321), ("Dec-25", 1225597), ("Jan-26", 1279042), ("Feb-26", 1253192), ("Mar-26", 1220922), ("Apr-26", 1304281),
                      ("May-26", 1415557), ("Jun-26", 1502072), ("Jul-26", 1417225), ("Aug-26", 1453832), ("Sep-26", 1480054), ("Oct-26", 1448360)])
    json.dump(out, open(DATA / "positioning.json", "w"), default=float)

    pd.set_option("display.width", 250, "display.max_columns", 40)
    S = pd.DataFrame(states)[["date", "name", "rv21", "mom63", "vix_term", "beta63", "btc_mom63", "lev_net", "margin_yoy", "PSI", "PSI_pct"]]
    print(S.round(3).to_string(index=False)); print("ANT", {k: {c: round(v, 3) for c, v in r.items() if v is not None and not c.endswith('_pct') or c == 'PSI_pct'} for k, r in ant.items()})
    print("\nPSI median", round(out["psi_median"], 3), "events hi", out["n_hi"], "of", len(EVENTS))
    for k, res in resp.items():
        print(f"{k:26s}", " | ".join(f"{w}: all {res[w]['all']*100:+.2f} (p{res[w]['p_all']:.2f}) hi {res[w]['hi']*100:+.2f} vs {res[w]['null_hi']*100:+.2f} (p{res[w]['p_hi']:.2f}) lo {res[w]['lo']*100:+.2f} vs {res[w]['null_lo']*100:+.2f} (p{res[w]['p_lo']:.2f}) rho {res[w]['rho_psi']:+.2f} (p{res[w]['p_rho']:.2f})" for w in WIN))
    print("\nREG (event x PSI interaction)")
    print(pd.DataFrame(reg.values())[["asset", "window", "b_psi", "t_psi", "c_event", "t_event", "d_inter", "t_inter", "p_inter"]].round(4).to_string(index=False))
    vc = pd.DataFrame(var_corr); print("\nVAR CORR p<0.1"); print(vc[vc.p < 0.1].round(3).to_string(index=False))
    print("\nCASES", json.dumps(cases, default=float)[:1500]); print("ANT move", {k: round(v * 100, 2) for k, v in ant_move.items()})
    print("\nIPO corr"); print(pd.DataFrame(ipo_corr).round(3).to_string(index=False)); print(ipo_split)


if __name__ == "__main__":
    main()
