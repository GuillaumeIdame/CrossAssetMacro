"""Export the Macro Thematic toolkit as one self-contained HTML artifact.

    python -m apps.macro_thematic.export_artifact            # writes export/macro_thematic.html

Everything the Streamlit pages compute is computed here with the same functions (they are plain
Python; only the `render()` functions depend on Streamlit) and embedded as one JSON payload. The
browser does the interactive part (scenario odds, screener weights, book sizing, stress, one-pager)
in JavaScript and persists manual inputs through the artifact `db` capability.
"""

import json
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

from datahub import stats  # noqa: E402
from apps.macro_thematic import confirmation as C  # noqa: E402
from apps.macro_thematic import crowding as K  # noqa: E402
from apps.macro_thematic import data as D  # noqa: E402
from apps.macro_thematic import legs as L  # noqa: E402
from apps.macro_thematic import regime as R  # noqa: E402
from apps.macro_thematic import risk as RK  # noqa: E402
from apps.macro_thematic import screener as S  # noqa: E402
from apps.macro_thematic import themes as T  # noqa: E402
from apps.macro_thematic import universe as U  # noqa: E402

OUT = ROOT / "export" / "macro_thematic.html"
TEMPLATE = Path(__file__).with_name("artifact_template.html")


def f(x, nd=4):
    """JSON-safe float (NaN/inf -> None)."""
    try:
        if x is None:
            return None
        v = float(x)
        if not math.isfinite(v):
            return None
        return round(v, nd)
    except Exception:
        return None


def rows(df: pd.DataFrame, nd=4):
    out = []
    for _, r in df.iterrows():
        o = {}
        for k, v in r.items():
            if isinstance(v, (np.floating, float)):
                o[k] = f(v, nd)
            elif isinstance(v, (np.integer,)):
                o[k] = int(v)
            elif isinstance(v, (np.bool_, bool)):
                o[k] = bool(v)
            elif isinstance(v, (pd.Timestamp, datetime)):
                o[k] = v.strftime("%Y-%m-%d")
            elif v is None or (isinstance(v, float) and math.isnan(v)):
                o[k] = None
            else:
                o[k] = str(v) if not isinstance(v, (int, str)) else v
        out.append(o)
    return out


def weekly(s: pd.Series, years=3, nd=3):
    s = s.dropna()
    if s.empty:
        return {"dates": [], "values": []}
    s = s[s.index >= s.index[-1] - pd.DateOffset(years=years)].resample("W-FRI").last().dropna()
    return {"dates": [d.strftime("%Y-%m-%d") for d in s.index], "values": [f(v, nd) for v in s.values]}


def main():
    errors = {}
    payload = {"generated": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")}
    frame, observed, status = D.load_universe()
    univ = U.build(frame)
    payload["as_of"] = {"frame_last": frame.index[-1].strftime("%Y-%m-%d"),
                        "spx": D.series(frame, "spx").index[-1].strftime("%Y-%m-%d"),
                        "ust10": D.series(frame, "ust10").index[-1].strftime("%Y-%m-%d")}

    # ---------------- regime (T1/T2)
    try:
        table, history = R.state_variables(frame)
        cls = R.classify(table, history)
        cr = R.credibility(frame)
        hist_w = history.resample("W-FRI").last().dropna(how="all")
        hist_w = hist_w[hist_w.index >= hist_w.index[-1] - pd.DateOffset(years=2)]
        labels = cls["labels"]
        lab_w = labels.resample("W-FRI").last().dropna() if len(labels) else pd.Series(dtype=object)
        lab_w = lab_w[lab_w.index >= hist_w.index[0]] if len(hist_w) else lab_w
        pp = D.load_policy_path()
        payload["regime"] = {
            "variables": rows(table),
            "quadrant": cls["quadrant"], "playbook": cls["playbook"], "rc": f(cls["rc"], 3), "days_in": int(cls["days_in"]),
            "against": int(cls["against"]), "state": cls["state"], "behaviour": cls["behaviour"],
            "confirms": R.CONFIRMS, "weights": R.WEIGHTS,
            "history": {"dates": [d.strftime("%Y-%m-%d") for d in hist_w.index], **{c: [f(v, 3) for v in hist_w[c].values] for c in hist_w.columns}},
            "ribbon": {"dates": [d.strftime("%Y-%m-%d") for d in lab_w.index], "labels": list(lab_w.values)},
            "credibility": {k: (f(v, 3) if not isinstance(v, str) else v) for k, v in cr.items()},
            "policy_path": {"cum_12m_bp": f(pp.get("cum_12m_bp"), 1), "source": pp.get("source"), "spot": f(pp.get("spot"), 3)} if pp and "cum_12m_bp" in pp else None,
        }
    except Exception as e:  # pragma: no cover
        errors["regime"] = repr(e); cls = {"state": "n/a", "quadrant": "n/a", "rc": float("nan")}

    # ---------------- confirmation & divergence (T3)
    try:
        payload["confirmation"] = {str(h): rows(C.confirmation_table(frame, h)) for h in (20, 60)}
        payload["divergences"] = {str(h): rows(C.divergences(frame, h)) for h in (20, 60)}
        payload["narratives"] = {k: [(a, b, c) for a, b, c in v] for k, v in C.NARRATIVES.items()}
    except Exception as e:
        errors["confirmation"] = repr(e)

    # ---------------- themes (T13) — examples + the pieces the browser needs for saturation
    try:
        conf20 = C.confirmation_table(frame, 20)
        breadth = {r["narrative"]: int(r["breadth_classes"]) for _, r in conf20.iterrows()}
        sat_assets = {"Supply inflation": ["brent", "bei10"], "Policy repricing": ["ust30", "tp10"], "Demand growth": ["spx", "copper"],
                      "Liquidity expansion": ["eem", "dxy"], "Credit stress": ["hy_oas", "vix"]}
        ext = {}
        for nar, keys in sat_assets.items():
            vals = [D.pct_rank(D.series(frame, a), 252) for a in keys]
            vals = [v for v in vals if np.isfinite(v)]
            ext[nar] = f(np.mean(vals), 1) if vals else None
        payload["themes"] = {"examples": T.EXAMPLE_THEMES, "breadth_by_narrative": breadth, "price_extension_by_narrative": ext,
                             "quality_criteria": T.QUALITY_CRITERIA, "odds_bands": T.ODDS_BANDS}
    except Exception as e:
        errors["themes"] = repr(e)

    # ---------------- screener (T4–T8)
    try:
        gate = {"Stable": 1.0, "Stable (low RC)": 1.0, "Early transition": 0.5}.get(cls["state"], 0.0)
        month = pd.Timestamp.today().month % 12 + 1
        scr, curve_pca = S.run_screener(S.DEFAULT_W, gate, month)
        keep = ["key", "label", "asset_class", "region", "quality", "S_V", "S_C", "S_S", "S_P", "val_note", "reg_z", "pca_z", "carry_ir", "carry_detail",
                "carry_q", "seas_t", "seas_sub", "seas_note", "align", "crowd", "stretch", "split", "mature", "pos_src", "event", "adv_2w", "long_means", "composite", "conviction", "flags"]
        payload["screener"] = {"rows": rows(scr[keep]), "weights": S.DEFAULT_W, "gate": gate, "month": int(month),
                               "curve_pca": {k: {"pc_resid": f(v["pc_resid"], 3), "pc_resid_z": f(v["pc_resid_z"], 3)} for k, v in curve_pca.iterrows()} if not curve_pca.empty else {},
                               "pca_explained": [f(x, 3) for x in curve_pca.attrs.get("explained", [])] if not curve_pca.empty else []}
    except Exception as e:
        errors["screener"] = repr(e)

    # ---------------- crowding (T9/T10)
    try:
        crowd, cftc_status = K.crowding_table()
        payload["crowding"] = {"rows": rows(crowd), "weights": K.CROWD_W, "cftc_status": cftc_status, "shocks": K.SHOCKS}
    except Exception as e:
        errors["crowding"] = repr(e)

    # ---------------- vol premium / legs (§2)
    try:
        vol = {}
        series_plot = {}
        for lab, (pk, ivk, ivlab) in L.THEME_ASSETS.items():
            rv20, rv60 = L.realised(frame, pk, 20), L.realised(frame, pk, 60)
            e_rv = (0.6 * rv20 + 0.4 * rv60).dropna()
            entry = {"price_key": pk, "iv_source": ivlab, "rv20": f(rv20.iloc[-1], 2) if len(rv20) else None, "rv60": f(rv60.iloc[-1], 2) if len(rv60) else None,
                     "e_rv": f(e_rv.iloc[-1], 2) if len(e_rv) else None}
            ps = L.premium_state(frame, pk, ivk, None)
            if ps.get("quality") != "unavailable":
                entry.update({k: (f(v, 3) if not isinstance(v, str) else v) for k, v in ps.items() if k != "series"})
                series_plot[lab] = weekly(ps["series"], 2, 2)
            else:
                entry["quality"] = "manual"
            vol[lab] = entry
        skew, vvix, vix, vix3m = (D.series(frame, k) for k in ("skew", "vvix", "vix", "vix3m"))
        secs = [L.realised(frame, k, 20) for k in ("xli", "xlp", "xly", "xle", "xlf")]
        idx_rv = L.realised(frame, "spx", 20)
        impl_corr = (idx_rv ** 2 / pd.concat(secs, axis=1).mean(axis=1) ** 2).dropna()
        payload["vol"] = {"assets": vol, "vrp_series": series_plot,
                          "tail": {"skew": f(D.last(frame, "skew"), 1), "skew_20d": f(D.diff(skew, 20), 1), "vvix": f(D.last(frame, "vvix"), 1), "vvix_20d": f(D.diff(vvix, 20), 1),
                                   "vvix_pct": f(D.pct_rank(vvix), 0), "vix_term": f(vix.iloc[-1] / vix3m.iloc[-1], 3) if len(vix) and len(vix3m) else None,
                                   "corr_proxy": f(impl_corr.iloc[-1], 3) if len(impl_corr) else None, "corr_proxy_20d": f(D.diff(impl_corr, 20), 3)}}
    except Exception as e:
        errors["vol"] = repr(e)

    # ---------------- instruments, betas, correlations, episodes (§3)
    try:
        ff = RK.factor_frame(frame)
        factors = list(ff.columns)
        inst_meta, betas, daily = {}, {}, {}
        for k, ins in univ.items():
            s = ins.series.dropna()
            if len(s) < 300:
                continue
            dy = RK.instrument_daily(ins).dropna()
            inst_meta[k] = {"label": ins.label, "asset_class": ins.asset_class, "mode": ins.mode, "unit": "bp" if ins.mode == "level" else "%",
                            "legs": ins.legs, "long_means": ins.long_means, "adv_2w": f(U.adverse_2w_move(ins), 3), "std_1d": f(dy.iloc[-60:].std(), 4),
                            "quality": ins.quality, "last": f(s.iloc[-1], 4), "last_date": s.index[-1].strftime("%Y-%m-%d")}
            b = {}
            for fac in factors:
                x = ff[fac].dropna()
                bb = stats.beta_dollar_per_sigma(dy, x, 60)
                df = pd.concat([dy, x], axis=1, keys=["p", "x"]).dropna().iloc[-250:]
                up, dn = df[df["x"] > 0], df[df["x"] < 0]
                bu = np.polyfit(up["x"], up["p"], 1)[0] if len(up) > 20 else np.nan
                bd = np.polyfit(dn["x"], dn["p"], 1)[0] if len(dn) > 20 else np.nan
                b[fac] = {"beta": f(bb["beta"], 5), "r2": f(bb["r2"], 3), "beta_up": f(bu, 5), "beta_dn": f(bd, 5)}
            betas[k] = b
            daily[k] = dy
        dd = pd.DataFrame(daily).dropna(how="all")
        dd3 = dd[dd.index >= dd.index[-1] - pd.DateOffset(years=3)].fillna(0.0)
        corr60 = dd.iloc[-60:].corr().fillna(0)
        spx_r = dd3["spx"] if "spx" in dd3.columns else dd3.mean(axis=1)
        tail_days = spx_r[spx_r <= spx_r.quantile(0.10)].index
        corr_tail = dd3.loc[tail_days].corr().fillna(0)
        keys = list(dd3.columns)
        fac_sig = {fac: f(ff[fac].dropna().iloc[-60:].std(), 4) for fac in factors}
        cov = ff.iloc[-250:].cov()
        episodes = {}
        for name, (a, b_) in RK.EPISODES.items():
            if pd.Timestamp(a) < ff.index.min():
                episodes[name] = {"status": "outside loaded history"}; continue
            w = ff.loc[a:b_]
            wi = dd.loc[a:b_]
            episodes[name] = {"status": "ok", "start": a, "end": b_, "factor_moves": {fac: f(w[fac].sum(), 2) for fac in factors},
                              "instrument_moves": {k: f(wi[k].sum(), 3) for k in keys if k in wi.columns}}
        payload["risk"] = {"factors": factors, "factor_sigma": fac_sig, "factor_cov": {fa: {fb: f(cov.loc[fa, fb], 6) for fb in factors} for fa in factors},
                           "instruments": inst_meta, "betas": betas, "corr_keys": keys,
                           "corr60": [[f(corr60.loc[a, b_], 3) for b_ in keys] for a in keys],
                           "corr_tail": [[f(corr_tail.loc[a, b_], 3) for b_ in keys] for a in keys],
                           "daily": {"dates": [d.strftime("%Y-%m-%d") for d in dd3.index], **{k: [f(v, 4) for v in dd3[k].values] for k in keys}},
                           "episodes": episodes, "parametric": RK.PARAMETRIC, "example_book": RK.EXAMPLE_BOOK, "book_vol": RK.BOOK_VOL}
    except Exception as e:
        errors["risk"] = repr(e)

    # ---------------- calendar, provenance
    try:
        cal = D.load_calendar(); today = pd.Timestamp.today().normalize()
        up = cal[(cal["date"] >= today) & (cal["date"] <= today + pd.Timedelta(days=14))]
        payload["calendar"] = rows(up[["date", "region", "event", "tier", "gauge", "status"]])
    except Exception as e:
        errors["calendar"] = repr(e)
    try:
        st = status.copy()
        st["first"] = st["first"].astype(str); st["last"] = st["last"].astype(str)
        payload["provenance"] = rows(st[["key", "name", "source", "ticker", "quality", "freq", "status", "last", "value", "note"]], 4)
        _, cftc_status, cftc_source = D.load_cftc()
        payload["cftc_status"] = cftc_status
    except Exception as e:
        errors["provenance"] = repr(e)
    payload["errors"] = errors

    blob = json.dumps(payload, separators=(",", ":"), default=str).replace("</", "<\\/")
    html = TEMPLATE.read_text(encoding="utf-8").replace("__PAYLOAD__", blob)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(html, encoding="utf-8")
    print(f"wrote {OUT} ({OUT.stat().st_size/1e6:.2f} MB; payload {len(blob)/1e6:.2f} MB); errors: {errors or 'none'}")
    return payload


if __name__ == "__main__":
    main()
