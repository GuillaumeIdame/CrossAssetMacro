"""Export the G3 Central Bank toolkit as a self-contained HTML artifact.

    python -m apps.g3_central_bank.export_artifact            # writes export/g3_central_bank.html

Computes everything the Streamlit pages compute (without Streamlit), embeds it as JSON in the
HTML template `artifact_template.html`, and leaves the interactive maths (bootstrap re-solve,
scenario trees, Kelly, shocks) to the page's JavaScript.
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from datahub import calendar, fred, loader, stir  # noqa: E402
from datahub.catalogue import CATALOGUE  # noqa: E402

from .pages_macro import CELLS, COMPONENTS, GAUGE_W, REACTION  # noqa: E402  (pure data + transforms)
from .pages_overview import CHAIN, STAGE_CHECKS  # noqa: E402
from .pages_distributions import DEFAULTS as DIST_DEFAULTS  # noqa: E402
from .common import FAMILY_META, REGION_LABEL, SERIES  # noqa: E402

TEMPLATE = Path(__file__).with_name("artifact_template.html")
OUT = ROOT / "export" / "g3_central_bank.html"
EURIBOR_BASIS_BP = 12.0


# --- helpers ---------------------------------------------------------------------------------
def _series(res, key):
    out = pd.Series(dtype=float)
    if key in res.frame.columns:
        obs = res.observed[key]
        out = res.frame.loc[obs[obs].index, key].dropna()
    if out.empty and CATALOGUE.get(key, {}).get("source") == "fred":
        try:
            out = fred.one(CATALOGUE[key]["ticker"], start="2010-01-01")
        except Exception:
            out = pd.Series(dtype=float)
    return out


def _last(res, key):
    s = _series(res, key)
    if s.empty:
        return None, None
    return float(s.iloc[-1]), str(s.index[-1].date())


def _num(x):
    if x is None:
        return None
    try:
        xf = float(x)
    except (TypeError, ValueError):
        return None
    return None if not np.isfinite(xf) else round(xf, 6)


def _ts(s: pd.Series, years=3, weekly=False, nd=4):
    s = s.dropna()
    if s.empty:
        return {"t": [], "v": []}
    s = s[s.index >= (pd.Timestamp.today() - pd.DateOffset(years=years))]
    if weekly and len(s) > 400:
        s = s.resample("W-FRI").last().dropna()
    return {"t": [d.strftime("%Y-%m-%d") for d in s.index], "v": [round(float(v), nd) for v in s.values]}


# --- macro gauges ------------------------------------------------------------------------------
def components(res):
    rows = []
    for region, gauge, horizon, label, key, tf, ref, inv, unit in COMPONENTS:
        s = (_series(res, "ust10") - _series(res, "ust2")).dropna() if key == "__2s10s" else _series(res, key)
        base = dict(region=region, gauge=gauge, horizon=horizon, component=label, key=key, unit=unit, inverted=bool(inv),
                    quality=("live" if key == "__2s10s" else CATALOGUE.get(key, {}).get("quality", "live")))
        if s.empty:
            rows.append(dict(base, value=None, ref=None, scale=None, z=None, last=None, stale=True, quality="unavailable", history={"t": [], "v": []}))
            continue
        t = tf(s).dropna()
        if t.empty:
            continue
        hist = t.iloc[-120:] if len(t) > 120 else t
        reference = float(hist.mean()) if ref == "mean" else float(ref)
        sd = float(hist.std()) if np.isfinite(hist.std()) else np.nan
        z = (float(t.iloc[-1]) - reference) / sd if sd and sd > 0 else np.nan
        if inv and np.isfinite(z):
            z = -z
        z = float(np.clip(z, -3, 3)) if np.isfinite(z) else None
        last_date = t.index[-1]
        stale = (pd.Timestamp.today() - last_date).days > 400
        h = t.iloc[-180:]
        rows.append(dict(base, value=_num(t.iloc[-1]), ref=_num(reference), scale=_num(sd), z=_num(z), last=str(last_date.date()), stale=bool(stale),
                         quality=("stale" if stale else base["quality"]),
                         history={"t": [d.strftime("%Y-%m-%d") for d in h.index], "v": [round(float(v), 4) for v in h.values]}))
    return rows


def gauges(comp, region):
    out = {}
    for gauge in ("inflation", "growth", "labour"):
        for horizon in ("spot", "forward"):
            zs = [r["z"] for r in comp if r["region"] == region and r["gauge"] == gauge and r["horizon"] == horizon and r["z"] is not None and not r["stale"]]
            out[f"{gauge}:{horizon}"] = int(np.clip(round(float(np.mean(zs))), -2, 2)) if zs else None
    return out


# --- strips ----------------------------------------------------------------------------------
def family_payload(family, res):
    meta = FAMILY_META[family]
    try:
        s = stir.strip(family)
    except Exception:
        s = pd.DataFrame()
    spot, spot_date = _last(res, meta["spot"])
    basis = EURIBOR_BASIS_BP if family == "ER" else 0.0
    out = dict(family=family, label=meta["label"], region=meta["region"], spot_key=meta["spot"], spot_label=meta["spot_label"],
               spot=spot, spot_date=spot_date, usd_per_bp=meta["usd_per_bp"], ccy=meta["ccy"], basis_bp=basis,
               contracts=[], meetings=[], A=[], frac_future=[], steps_bp=[], fit_error_bp=None, source=None, close_date=None)
    if s.empty or spot is None:
        return out
    today = pd.Timestamp.today().normalize()
    s = s[s["win_end"] >= today].reset_index(drop=True)
    mts = calendar.meetings(meta["region"], start=today, end=s["win_end"].max())
    # window fractions (same construction as datahub.stir.bootstrap)
    A = np.zeros((len(s), len(mts))); frac = np.ones(len(s))
    for i, c in s.iterrows():
        days = pd.date_range(max(c["win_start"], today), c["win_end"], freq="D")
        full = pd.date_range(c["win_start"], c["win_end"], freq="D")
        frac[i] = len(days) / max(len(full), 1)
        for k, e in enumerate(mts["effective"].values):
            A[i, k] = (days >= e).sum() / max(len(days), 1)
    try:
        bs = stir.bootstrap(family, s, spot, basis_bp=basis)
    except Exception:
        bs = pd.DataFrame()
    out["contracts"] = [dict(contract=str(c["contract"]), month=str(c["contract_month"]), close=_num(c["close"]), implied=_num(c["implied_rate"]),
                             win_start=str(pd.Timestamp(c["win_start"]).date()), win_end=str(pd.Timestamp(c["win_end"]).date()),
                             ltd=(str(pd.Timestamp(c["last_trading_date"]).date()) if pd.notna(c.get("last_trading_date")) else str(pd.Timestamp(c["win_start"]).date())),
                             chg_1d_bp=_num(c["chg_1d"] * 100) if "chg_1d" in s.columns else None,
                             chg_1w_bp=_num(c["chg_1w"] * 100) if "chg_1w" in s.columns else None) for _, c in s.iterrows()]
    out["meetings"] = [dict(date=str(pd.Timestamp(m["date"]).date()), event=str(m["event"]), status=str(m["status"]),
                            effective=str(pd.Timestamp(m["effective"]).date())) for _, m in mts.iterrows()]
    out["A"] = np.round(A, 5).tolist(); out["frac_future"] = np.round(frac, 5).tolist()
    out["steps_bp"] = [round(float(x), 3) for x in bs["step_bp"]] if not bs.empty else []
    out["fit_error_bp"] = _num(bs.attrs.get("fit_error_bp")) if not bs.empty else None
    out["source"] = str(s["source"].iloc[0]); out["close_date"] = str(pd.to_datetime(s["close_date"]).max().date()) if "close_date" in s.columns else None
    return out


# --- main ------------------------------------------------------------------------------------
def build():
    res = loader.load(SERIES, years=15)
    cal = calendar.load()
    today = pd.Timestamp.today().normalize()
    comp = components(res)
    payload = dict(generated=str(pd.Timestamp.now().round("min")), today=str(today.date()),
                   regions={"US": "Fed", "EA": "ECB", "UK": "BoE"}, region_label=REGION_LABEL,
                   chain=CHAIN, stage_checks=STAGE_CHECKS, cells={f"{k[0]},{k[1]}": v for k, v in CELLS.items()},
                   gauge_weights=GAUGE_W, reaction=REACTION, dist_defaults=DIST_DEFAULTS,
                   components=comp, gauges={r: gauges(comp, r) for r in ("US", "EA", "UK")})
    # calendar
    up = calendar.upcoming(120, regions=("US", "EA", "UK", "JP", "CH"), cal=cal)
    payload["calendar"] = [dict(date=str(r["date"].date()), days=int(r["days_to"]), region=r["region"], type=r["type"], event=r["event"],
                                tier=int(r["tier"]), gauge=r["gauge"], status=r["status"], note=str(r["note"])) for _, r in up.iterrows()]
    allm = cal[(cal["type"] == "meeting") & (cal["date"] >= today)]
    payload["meetings_all"] = [dict(date=str(r["date"].date()), region=r["region"], event=r["event"], status=r["status"]) for _, r in allm.iterrows()]
    payload["counts_before"] = {}
    for region in ("US", "EA", "UK"):
        m = up[(up["region"] == region) & (up["type"] == "meeting")].head(1)
        if not m.empty:
            payload["counts_before"][region] = calendar.counts_before(m.iloc[0]["date"], region, cal=cal)
    # families
    payload["families"] = {f: family_payload(f, res) for f in ("ZQ", "SR3", "ER", "SON")}
    payload["snapshot_file"] = (stir.latest_snapshot_path() or "").split("/")[-1]
    # market-implied state
    state = {}
    for k in ("effr", "sofr", "estr", "sonia", "ecb_dfr", "iorb", "fft_upper", "fft_lower", "ust1", "ust2", "ust5", "ust10", "ust30",
              "bei5", "bei10", "fwd5y5y", "real10", "tp10", "vix", "move", "nfci", "hy_oas"):
        v, d = _last(res, k)
        state[k] = dict(value=v, date=d, name=CATALOGUE[k]["name"], quality=CATALOGUE[k]["quality"])
    y1, y2 = state["ust1"]["value"], state["ust2"]["value"]
    state["fwd1y1y"] = dict(value=(((1 + y2 / 100) ** 2 / (1 + y1 / 100) - 1) * 100 if y1 is not None and y2 is not None else None),
                            date=state["ust2"]["date"], name="1y1y (from par 1y/2y)", quality="proxy")
    payload["state"] = state
    # credibility switch
    tp, u10, u2 = _series(res, "tp10"), _series(res, "ust10"), _series(res, "ust2")
    cred = None
    if not tp.empty and not u10.empty and not u2.empty:
        df = pd.concat([tp, u10, u2], axis=1, keys=["tp", "y10", "y2"]).dropna()
        n = min(63, len(df) - 1)
        d = df.iloc[-1] - df.iloc[-1 - n]
        cred = dict(d10=_num(d["y10"] * 100), dtp=_num(d["tp"] * 100), dexp=_num((d["y10"] - d["tp"]) * 100), d2=_num(d["y2"] * 100), last=str(df.index[-1].date()),
                    series={"exp": _ts(df["y10"] - df["tp"], 3, True), "tp": _ts(df["tp"], 3, True), "y2": _ts(df["y2"], 3, True)})
    payload["credibility"] = cred
    # time series for charts
    payload["series"] = {k: _ts(_series(res, k), 3, True) for k in ("ust2", "ust10", "effr", "sofr", "estr", "sonia", "bei10", "fwd5y5y", "tp10", "vix", "move", "nfci", "hy_oas")}
    # provenance
    st = res.status.copy()
    st["first"] = st["first"].astype(str); st["last"] = st["last"].astype(str)
    payload["provenance"] = [dict(key=r["key"], name=r["name"], source=r["source"], ticker=r["ticker"], quality=r["quality"], freq=r["freq"],
                                  status=r["status"], last=r["last"], value=_num(r["value"]), note=str(r["note"])) for _, r in st.iterrows()]
    return payload


def _clean(o):
    """Replace NaN/inf anywhere in the payload with None and numpy scalars with Python ones."""
    if isinstance(o, dict):
        return {str(k): _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (float, np.floating)):
        return None if not np.isfinite(o) else float(o)
    if isinstance(o, (pd.Timestamp,)):
        return str(o.date())
    return o


def main():
    payload = _clean(build())
    html = TEMPLATE.read_text(encoding="utf-8")
    data = json.dumps(payload, separators=(",", ":"), allow_nan=False).replace("</", "<\\/")
    html = html.replace("__DATA__", data)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(html, encoding="utf-8")
    print(f"wrote {OUT} ({OUT.stat().st_size / 1e6:.2f} MB; payload {len(data) / 1e6:.2f} MB)")


if __name__ == "__main__":
    main()
