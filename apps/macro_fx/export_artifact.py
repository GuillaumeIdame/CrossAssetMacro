"""Export the Macro FX toolkit as a self-contained HTML artifact.

    python -m apps.macro_fx.export_artifact            # writes export/macro_fx.html

Everything the Streamlit pages compute is recomputed here without a Streamlit runtime (the
page modules' functions are pure apart from `st.cache_data`, which degrades to an in-memory
cache when no runtime is present) and embedded as one JSON payload; the page's JavaScript
handles the interactive parts (pair selectors, manual inputs, Kelly, book aggregation).
"""

import json
import logging
import math
import sys
import warnings
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

warnings.filterwarnings("ignore")
logging.getLogger("streamlit").setLevel(logging.ERROR)

from datahub import calendar, stats  # noqa: E402

from . import common, data, factors, macro, positioning, regime, risk, seasonality, strategies, valuation  # noqa: E402

TEMPLATE = Path(__file__).with_name("artifact_template.html")
OUT = ROOT / "export" / "macro_fx.html"


# --- helpers -----------------------------------------------------------------------------------
def _f(x, nd=4):
    try:
        if x is None or (isinstance(x, float) and not math.isfinite(x)) or pd.isna(x):
            return None
    except Exception:
        pass
    if isinstance(x, (np.floating, float)):
        return round(float(x), nd)
    if isinstance(x, (np.integer, int)):
        return int(x)
    if isinstance(x, (np.bool_, bool)):
        return bool(x)
    if isinstance(x, (pd.Timestamp, datetime)):
        return x.strftime("%Y-%m-%d")
    if hasattr(x, "isoformat"):
        return x.isoformat()
    return x


def rows(df: pd.DataFrame, nd=4):
    out = []
    for _, r in df.iterrows():
        out.append({k: _f(v, nd) for k, v in r.items()})
    return out


def weekly(s: pd.Series, years=3, nd=4):
    s = s.dropna()
    if s.empty:
        return {"dates": [], "values": []}
    s = s.iloc[-(252 * years):]
    w = s.resample("W-FRI").last().dropna()
    return {"dates": [d.strftime("%Y-%m-%d") for d in w.index], "values": [_f(v, nd) for v in w.values]}


def daily(s: pd.Series, n=780, nd=5):
    s = s.dropna().iloc[-n:]
    return {"dates": [d.strftime("%Y-%m-%d") for d in s.index], "values": [_f(v, nd) for v in s.values]}


def z_last(s: pd.Series, win=504):
    return _f(stats.last_z(s.dropna(), win))


# --- blocks -------------------------------------------------------------------------------------
def block_factors(df, fac_out):
    fac = fac_out["factors"]
    cum = (fac.fillna(0).cumsum() * 100).iloc[-756:]
    cum = cum - cum.iloc[0]
    rets = data.returns(df)
    table = []
    eps_series = {}
    for c, b in fac_out["betas"].items():
        e = fac_out["eps"][c].dropna()
        e20 = e.rolling(20).sum()
        table.append(dict(ccy=c, pair=data.PAIR_LABEL[c], beta_USD=_f(common.last(b["F_USD"])), beta_Carry=_f(common.last(b["F_Carry"])),
                          beta_Mom=_f(common.last(b["F_Mom"])), eps_20D_pct=_f(100 * common.last(e20)), eps_20D_z=z_last(e20),
                          ret_20D_pct=_f(100 * rets[c].iloc[-20:].sum())))
        eps_series[c] = {"cum60_pct": weekly(100 * e.rolling(60).sum(), 2), "z20": weekly(stats.zscore(e20, 504), 2)}
    heads = {}
    for f in fac.columns:
        s = fac[f].dropna()
        heads[f] = dict(d1=_f(100 * s.iloc[-1]), d20=_f(100 * s.iloc[-20:].sum()))
    ranks = fac_out["ranks"].copy()
    ranks.index.name = "ccy"
    val = []
    for label in ("Apr-2025 tariffs", "Aug-2024 carry unwind"):
        a, b = common.window_dates(label)
        w = fac.loc[a:b]
        val.append(dict(label=label, window=f"{a} → {b}", **({f: _f(100 * w[f].sum(), 2) for f in fac.columns} if not w.empty else {"note": "outside loaded history"})))
    coincide = bool((ranks["w_carry"] - ranks["w_mom"]).abs().sum() < 1e-9)
    return dict(heads=heads, cum={f: weekly(cum[f], 3, 3) for f in cum.columns}, table=table, eps=eps_series,
                ranks=rows(ranks.reset_index()), validation=val, legs_coincide=coincide)


def block_macro(df):
    ccys = ["USD"] + data.CCYS
    growth = {c: daily(macro.growth_composite(df, c), 780, 3) for c in ccys}
    real = {c: daily(macro.real_1y1y_proxy(df, c), 780, 3) for c in ccys}
    cols = [c for c in macro.TOT_DEFAULT.columns if c in df.columns]
    comm = np.log(df[cols].astype(float)).diff().dropna(how="all").iloc[-780:]
    commodity_returns = {"dates": [d.strftime("%Y-%m-%d") for d in comm.index], **{c: [_f(v, 5) for v in comm[c].fillna(0).values] for c in cols}}
    tot_w = {c: {k: float(macro.TOT_DEFAULT.loc[c, k]) for k in macro.TOT_DEFAULT.columns} for c in macro.TOT_DEFAULT.index}
    quality = {c: dict(growth="proxy" if growth[c]["values"] else "unavailable",
                       real="proxy" if real[c]["values"] else "unavailable") for c in ccys}
    return dict(ccys=ccys, growth=growth, real=real, commodity_returns=commodity_returns, tot_weights=tot_w, quality=quality,
                growth_series={c: macro.GROWTH_SERIES.get(c, []) for c in ccys})


def block_valuation(df):
    out = {}
    for w in (20, 60, 120):
        tab = valuation.valuation_table(df, w)
        zcols = [c for c in tab.columns if c not in ("ccy", "pair", "composite_z", "disagreement", "n_drivers") and not c.endswith("R²")]
        out[str(w)] = dict(drivers=zcols, rows=rows(tab, 3))
    reer = []
    for c in ["USD"] + data.CCYS:
        z, mser = valuation.reer_stretch(df, c)
        reer.append(dict(currency=c, reer_z_10y=_f(z, 2), last=mser.index[-1].strftime("%Y-%m") if mser is not None else None,
                         haircut=bool(np.isfinite(z) and abs(z) >= 2)))
    return dict(windows=out, reer=reer, quality={c: dict(short=data.quality_of(c, "short"), long=data.quality_of(c, "long"),
                                                       equity=data.quality_of(c, "equity"), inflation=data.quality_of(c, "inflation")) for c in data.CCYS})


def block_positioning(df):
    status, source, met = positioning.cftc_block()
    rv = positioning.realised_vol_table(df)
    today = pd.Timestamp.today().normalize()
    meetings = []
    for c, region in positioning.REGION.items():
        mts = calendar.meetings(region, start=today, end=today + pd.Timedelta(days=28))
        for _, mt in mts.iterrows():
            meetings.append(dict(date=mt["date"].strftime("%Y-%m-%d"), currency=c, event=mt["event"], status=mt["status"]))
    cftc_rows = rows(met, 3) if not met.empty else []
    return dict(cftc_status=status, cftc_source=source, cftc=cftc_rows, rv=rows(rv, 3), meetings=meetings,
                cftc_key={c: positioning.CFTC_KEY.get(c) for c in data.CCYS})


def block_seasonality(fx_long):
    out = {}
    for c in data.CCYS:
        tab = seasonality.screen(fx_long, c)
        if tab.empty:
            out[c] = dict(rows=[], start=None, end=None, yearly={}); continue
        px = fx_long[c].dropna()
        yearly = {}
        for name, month, d0, d1 in seasonality.windows():
            r = seasonality.window_returns(px, month, d0, d1) * 1e4
            yearly[name] = {int(y): _f(v, 1) for y, v in r.items()}
        out[c] = dict(rows=rows(tab, 3), start=px.index[0].strftime("%Y-%m-%d"), end=px.index[-1].strftime("%Y-%m-%d"), yearly=yearly)
    return dict(pairs=out, params=dict(t_gate=seasonality.T_GATE, lam=seasonality.LAMBDA, cost_bp=seasonality.COST_BP,
                                      recent_start=seasonality.RECENT_START, subperiods=seasonality.SUBPERIODS))


def block_regime(df, ax):
    S = ax["scores"].dropna(how="all")
    last = S.iloc[-1]; prev = S.iloc[-21] if len(S) > 21 else last
    axes = {k: dict(level=_f(last[k], 1), direction=_f(last[k] - prev[k], 1)) for k in S.columns}
    raw = {}
    for name, z in ax["raw"].items():
        if z.empty:
            raw[name] = {}; continue
        r = z.dropna(how="all").iloc[-1]
        raw[name] = {k: _f(v, 2) for k, v in r.items()}
    q = regime.quadrant_series(S)
    cur = q.iloc[-1]
    path = q.iloc[-120:]
    validation = []
    for lab, (a, b) in [("Mar-2020", ("2020-03-01", "2020-03-31")), ("2022 rates shock", ("2022-06-01", "2022-10-31")), ("Apr-2025", ("2025-04-01", "2025-04-30"))]:
        w = q.loc[a:b]
        validation.append(dict(label=lab, quadrant=(w["quadrant"].value_counts().index[0] if len(w) else "outside history")))
    decides = {"USD": "Express vs USD or as crosses; net USD delta with or against regime", "Global Risk": "Cyclical vs defensive tilt",
               "Liquidity": "Gross ceiling; carry size; whether dislocations revert (easing) or extend (stress). Cross-currency basis not public → not included",
               "Carry Health": "Carry and short-vol sleeve sizing; price of insurance (RR from the manual surface if typed)", "Real Yield": "Feeds the quadrant; rates-driven vs risk-driven USD"}
    return dict(axes=axes, history={k: weekly(S[k], 3, 1) for k in S.columns}, raw=raw, decides=decides,
                quadrant=dict(confirmed=cur["confirmed"] if isinstance(cur["confirmed"], str) else None, current=cur["quadrant"],
                              days_in=int(cur["days_in"]), migrating=bool(cur["migrating"]),
                              path={"dates": [d.strftime("%Y-%m-%d") for d in path.index], "usd": [_f(v, 1) for v in path["USD"]], "ry": [_f(v, 1) for v in path["Real Yield"]]}),
                playbook=regime.PLAYBOOK, validation=validation)


def block_strategies(df):
    lt = strategies.lifecycle_table(df)
    ot = positioning.options_table(df)
    carry = []
    for c in data.G10:
        cd = common.last(data.carry_diff(df, c))
        carry.append(dict(ccy=c, carry_pp=_f(cd, 3), rv60=_f(ot.loc[c, "rv60"], 2) if c in ot.index else None))
    return dict(lifecycle=rows(lt, 3), carry=carry, playbook=strategies.PLAYBOOK, conviction_weights=strategies.CONVICTION_WEIGHTS,
                spot_last={c: _f(common.last(data.spot(df, c)), 5) for c in data.CCYS})


def block_risk(df, fac):
    rets = data.returns(df)
    fc = risk.factor_changes(df)
    expo = {}
    for c in data.CCYS:
        y = rets[c].dropna()
        row = {}
        for name in fc.columns:
            b = stats.beta_dollar_per_sigma(y, fc[name].dropna(), 60)
            row[name] = dict(beta=_f(b["beta"], 5), sigma=_f(b["sigma_x"], 5), per_sigma_1m=_f(b["dollar_per_sigma"] * 1e6, 0), r2=_f(b["r2"], 3))
        for f in fac.columns:
            b = stats.beta_dollar_per_sigma(y, fac[f].dropna(), 60)
            row[f] = dict(beta=_f(b["beta"], 5), sigma=_f(b["sigma_x"], 5), per_sigma_1m=_f(b["dollar_per_sigma"] * 1e6, 0), r2=_f(b["r2"], 3))
        expo[c] = row
    episodes = []
    for ep in risk.EPISODES:
        a, b = common.window_dates(ep)
        w = rets.loc[a:b]
        if w.empty:
            episodes.append(dict(episode=ep, window=f"{a}→{b}", status="outside loaded history", moves={})); continue
        mv = w.sum()
        episodes.append(dict(episode=ep, window=f"{a}→{b}", status="ok", moves={c: _f(100 * mv.get(c, np.nan), 2) for c in data.CCYS}))
    # daily returns last 2y per pair so the browser can compute book vol / CED
    r2y = rets.iloc[-504:]
    daily_rets = {"dates": [d.strftime("%Y-%m-%d") for d in r2y.index], **{c: [_f(v, 5) if np.isfinite(v) else 0 for v in r2y[c].values] for c in data.CCYS}}
    return dict(exposures=expo, factors=list(fc.columns), structure_factors=list(fac.columns), episodes=episodes,
                shock_grid=risk.SHOCK_GRID, vol_budget=risk.VOL_BUDGET, daily_returns=daily_rets)


def block_provenance(m):
    st_ = m["status"].copy()
    keep = ["key", "name", "source", "ticker", "quality", "freq", "status", "last", "value", "note"]
    st_ = st_[keep]
    return dict(status=rows(st_, 4), notes=m["notes"], n_loaded=int((st_["status"] == "loaded").sum()), n_total=int(len(st_)))


def _json_default(o):
    if hasattr(o, "isoformat"):
        return o.isoformat()
    if isinstance(o, (np.floating,)):
        return None if not np.isfinite(o) else float(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    raise TypeError(type(o))


def build_payload():
    m = data.load_all(); df = m["df"]
    fac_out = factors.build_factors(df)
    ax = regime.axes(df)
    spots = data.spots(df)
    payload = dict(
        meta=dict(generated=datetime.now().strftime("%Y-%m-%d %H:%M"), as_of=df.dropna(how="all").index[-1].strftime("%Y-%m-%d"),
                  pairs=[dict(ccy=c, label=data.PAIR_LABEL[c], g10=c in data.G10) for c in data.CCYS],
                  companion="https://claude.ai/artifact/1cv2QGVTZjcfMFwg4SjwLG"),
        spots={c: weekly(spots[c], 3, 5) for c in spots.columns},
        factors=block_factors(df, fac_out),
        macro=block_macro(df),
        valuation=block_valuation(df),
        positioning=block_positioning(df),
        seasonality=block_seasonality(m["fx_long"]),
        regime=block_regime(df, ax),
        strategies=block_strategies(df),
        risk=block_risk(df, fac_out["factors"]),
        provenance=block_provenance(m),
    )
    return payload


def main():
    payload = build_payload()
    js = json.dumps(payload, separators=(",", ":"), allow_nan=False, default=_json_default).replace("</", "<\\/")
    html = TEMPLATE.read_text(encoding="utf-8").replace("/*__DATA__*/", js)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(html, encoding="utf-8")
    print(f"wrote {OUT} ({OUT.stat().st_size / 1e6:.2f} MB; payload {len(js) / 1e6:.2f} MB)")


if __name__ == "__main__":
    main()
