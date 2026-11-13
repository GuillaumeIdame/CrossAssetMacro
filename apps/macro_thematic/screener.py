"""T4–T8 — Four screening pillars and the Trade Screener (§1.6–1.7)."""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from datahub import stats, ui

from . import data as D
from . import regime as R
from . import universe as U

DEFAULT_W = dict(valuation=0.35, carry=0.30, seasonality=0.10, positioning=0.25)
SUBPERIODS = [("2000-01-01", "2007-12-31"), ("2008-01-01", "2014-12-31"), ("2015-01-01", "2019-12-31"), ("2020-01-01", "2025-12-31")]


# ---------------------------------------------------------------- valuation
def valuation(ins: U.Instrument, frame: pd.DataFrame, curve_pca: pd.DataFrame) -> dict:
    y = ins.series
    if ins.mode == "price":
        y = np.log(y.dropna())
    lenses = []
    notes = []
    for w in (20, 60, 90):
        tab = stats.univariate_residuals(y, ins.drivers, window=w)
        z, dis = stats.composite_residual(tab)
        if np.isfinite(z):
            lenses.append(z)
        if w == 60:
            tab60 = tab
            if dis:
                notes.append("driver disagreement")
            bad = tab["note"].astype(str).str.contains("unmodelled|degenerate").sum()
            if len(tab) and bad > len(tab) / 2:
                notes.append("NON-STAT")
    reg_z = float(np.median(lenses)) if lenses else np.nan
    pca_z = np.nan
    if ins.asset_class == "rates" and ins.tenor is not None and not curve_pca.empty:
        col = f"ust{int(ins.tenor)}"
        if col in curve_pca.index:
            pca_z = float(curve_pca.loc[col, "pc_resid_z"])
    # sign: for yields positive residual = cheap = favours long(receive); for prices positive = rich
    sign = +1 if ins.mode == "level" else -1
    if ins.mode == "level" and (ins.legs is not None):
        sign = +1  # slope wider than model = steepener cheap? wider slope = steepener rich → sign −1 for steepeners
        sign = -1
    if ins.asset_class == "xmkt":
        sign = -1
    s_reg = sign * reg_z if np.isfinite(reg_z) else np.nan
    s_pca = sign * pca_z if np.isfinite(pca_z) else np.nan
    if np.isfinite(s_reg) and np.isfinite(s_pca):
        if np.sign(s_reg) == np.sign(s_pca):
            s_v = float(np.mean([s_reg, s_pca])); notes.append("both lenses agree")
        else:
            s_v = float(s_reg) * 0.5; notes.append("PCA lens disagrees")
    else:
        s_v = s_reg if np.isfinite(s_reg) else s_pca
    q_v = 1.0
    try:
        r2 = tab60["r2"].dropna().mean()
        q_v = float(np.clip(r2 / 0.3, 0.3, 1.0)) if np.isfinite(r2) else 0.7
    except Exception:
        pass
    return dict(S_V=float(np.clip(s_v * q_v, -3, 3)) if np.isfinite(s_v) else np.nan, reg_z=reg_z, pca_z=pca_z, q_v=q_v, note=", ".join(notes))


# ---------------------------------------------------------------- carry
def _interp_yield(frame, tau):
    pts = {0.25: "ust3m", 1: "ust1", 2: "ust2", 5: "ust5", 10: "ust10", 30: "ust30"}
    xs = sorted(pts)
    vals = {t: D.last(frame, k) for t, k in pts.items()}
    if tau in vals:
        return vals[tau]
    lo = max(t for t in xs if t < tau); hi = min(t for t in xs if t > tau)
    return vals[lo] + (vals[hi] - vals[lo]) * (tau - lo) / (hi - lo)


def rates_carry_bp(frame, tau, h=0.25) -> dict:
    """Carry + rolldown over h years in bp of yield-equivalent, for a long bond at tenor tau."""
    y = _interp_yield(frame, tau); r = D.last(frame, "ust3m")
    dmod = tau / (1 + y / 100) * 0.9 if tau > 1 else tau
    carry = (y - r) * h / max(dmod, 0.1) * 100          # income converted to yield-equivalent bp
    roll = (y - _interp_yield(frame, max(tau - h, 0.25))) * 100
    return dict(carry_bp=carry, roll_bp=roll, total_bp=carry + roll, income_pct=(y - r) * h)


def carry(ins: U.Instrument, frame: pd.DataFrame, gating: float) -> dict:
    out = dict(S_C_raw=np.nan, detail="", quality="unavailable", ir=np.nan)
    if ins.asset_class in ("rates", "rates_fut"):
        vol3m = float(ins.series.dropna().diff(63).std()) if ins.mode == "level" else np.nan
        if ins.tenor is not None:
            c = rates_carry_bp(frame, ins.tenor)
            tot = c["total_bp"]
            out.update(detail=f"carry {c['carry_bp']:+.0f} + roll {c['roll_bp']:+.0f} bp/3m", quality="live")
        elif ins.legs is not None and len(ins.legs) == 2:
            a, b = ins.legs
            tot = rates_carry_bp(frame, a)["total_bp"] - rates_carry_bp(frame, b)["total_bp"]  # steepener: receive a, pay b
            out.update(detail=f"steepener carry+roll {tot:+.0f} bp/3m", quality="live")
        elif ins.legs is not None:
            a, m, b = ins.legs
            tot = 2 * rates_carry_bp(frame, m)["total_bp"] - rates_carry_bp(frame, a)["total_bp"] - rates_carry_bp(frame, b)["total_bp"]
            out.update(detail=f"fly carry+roll {tot:+.0f} bp/3m", quality="live")
        else:  # futures: map to tenor
            t = {"zt": 2, "zf": 5, "zn": 7, "zb": 20}[ins.key]
            c = rates_carry_bp(frame, t); tot = c["total_bp"]
            vol3m = float((np.log(ins.series.dropna()).diff(63).std()) * 100)
            # convert bp to price %: × duration/100
            tot = tot * {"zt": 1.9, "zf": 4.3, "zn": 6.5, "zb": 13}[ins.key] / 100
            out.update(detail=f"implied carry+roll ≈ {tot:+.2f}%/3m (via cash curve)", quality="proxy")
        ir = tot / vol3m if np.isfinite(vol3m) and vol3m > 0 else np.nan
        out.update(ir=ir, S_C_raw=ir)
        # structural vs path-contingent note
    elif ins.asset_class == "fx":
        pol = getattr(ins, "policy_key", None)
        if pol:
            i_for = D.last(frame, pol); i_usd = D.last(frame, "effr")
            if np.isfinite(i_for) and np.isfinite(i_usd):
                c = (i_for - i_usd) * 0.25  # % over 3m, long base
                rv = float(np.log(ins.series.dropna()).diff().iloc[-63:].std() * np.sqrt(63) * 100)
                ir = c / rv if rv > 0 else np.nan
                out.update(S_C_raw=ir, ir=ir, detail=f"i_for {i_for:.2f} − i_usd {i_usd:.2f} → {c:+.2f}%/3m, RV3m {rv:.1f}%", quality="proxy")
        if not np.isfinite(out["ir"]):
            out.update(detail="no public short rate → carry n/a")
    elif ins.asset_class == "commodity":
        out.update(detail="convenience yield needs the second contract (not on Yahoo) → n/a")
    elif ins.asset_class == "equity":
        out.update(detail="equity carry (dividend − funding) not scored")
    elif ins.asset_class == "xmkt":
        out.update(detail="cross-market carry needs foreign repo/funding → n/a")
    if np.isfinite(out["S_C_raw"]):
        out["S_C_raw"] = out["S_C_raw"] * gating
    return out


# ---------------------------------------------------------------- seasonality (two gates)
def seasonality(ins: U.Instrument, month: int) -> dict:
    s = ins.series.dropna()
    if ins.mode == "price":
        m = np.log(s).resample("ME").last().diff().dropna() * 100
    else:
        m = s.resample("ME").last().diff().dropna()
        if ins.legs is None and ins.key.startswith("ust"):
            m = -m  # long = receive → gain when yields fall
        elif ins.legs is not None and len(ins.legs) == 2:
            m = m   # steepener gains when slope widens
    sel = m[m.index.month == month]
    out = dict(S_S=0.0, t_recent=np.nan, subperiods="", note="", hit=np.nan)
    if len(sel) < 3:
        out["note"] = "too few observations"; return out
    rec = sel[sel.index >= "2021-04-01"]
    t_rec = rec.mean() / (rec.std() / np.sqrt(len(rec))) if len(rec) >= 3 and rec.std() > 0 else np.nan
    gate1 = bool(np.isfinite(t_rec) and abs(t_rec) >= 2.25)
    subs = []
    for a, b in SUBPERIODS:
        w = sel[(sel.index >= a) & (sel.index <= b)]
        if len(w) >= 3 and w.std() > 0:
            subs.append(w.mean() / (w.std() / np.sqrt(len(w))))
        else:
            subs.append(np.nan)
    sign_ref = np.sign(t_rec) if np.isfinite(t_rec) else np.sign(sel.mean())
    passed = sum(1 for t in subs if np.isfinite(t) and np.sign(t) == sign_ref and abs(t) >= 1.0)
    available = sum(1 for t in subs if np.isfinite(t))
    gate2 = passed >= 3
    out.update(t_recent=t_rec, subperiods=" / ".join(f"{t:+.1f}" if np.isfinite(t) else "–" for t in subs), hit=float((np.sign(sel) == sign_ref).mean() * 100))
    if available < 3:
        out["note"] = f"only {available}/4 sub-periods in history → gate 2 cannot pass"
    elif gate1 and gate2:
        lam = 0.45
        out["S_S"] = float(sign_ref * min(abs(t_rec) / 2.25, 1.5) * (1 - lam))
        out["note"] = "both gates pass"
    else:
        out["note"] = f"gate1 {'✓' if gate1 else '✗'}, gate2 {passed}/4"
    return out


# ---------------------------------------------------------------- positioning
def positioning(ins: U.Instrument, cftc_m: pd.DataFrame) -> dict:
    cta = stats.cta_ensemble(U.price_proxy(ins))   # trend of the LONG position in the common frame
    ens = cta["ensemble"]
    align = 0.0 if (not np.isfinite(ens) or cta["split"]) else float(2.0 * ens)
    crowd = 0.0; stretch = np.nan; src = "CTA model"
    if cftc_m is not None and not cftc_m.empty and ins.cftc_key in set(cftc_m["key"]):
        row = cftc_m[cftc_m["key"] == ins.cftc_key].iloc[0]
        stretch = float(row["ratio_pct"]); src = "CFTC"
        crowd = 2.0 * max(0.0, stretch - 80) / 20 * (np.sign(row["net"]) if row["net"] != 0 else 1)
        crowd = abs(crowd) * (1 if (np.sign(row["net"]) == np.sign(ens) or not np.isfinite(ens)) else 0)
    elif np.isfinite(ens):
        stretch = float(min(100, abs(ens) * 100))
        crowd = 2.0 * max(0.0, stretch - 80) / 20
    s_p = float(np.clip(align - crowd * np.sign(align if align != 0 else 1), -3, 3))
    return dict(S_P=s_p, align=align, crowd=crowd, stretch=stretch, split=cta["split"], mature=cta["mature"], ensemble=ens, source=src)


# ---------------------------------------------------------------- composite
@st.cache_data(ttl=3600, show_spinner="Scoring the screener universe...")
def run_screener(weights: dict, gating: float, month: int):
    frame, _, _ = D.load_universe()
    cftc_m, _, _ = D.load_cftc()
    univ = U.build(frame)
    curve = frame[["ust2", "ust5", "ust10", "ust30"]].dropna()
    curve_pca = stats.pca_residual(curve, 2, 504) if len(curve) > 100 else pd.DataFrame()
    cal = D.load_calendar()
    today = pd.Timestamp.today().normalize()
    soon = cal[(cal["date"] >= today) & (cal["date"] <= today + pd.Timedelta(days=5)) & (cal["tier"] == 1)]
    rows = []
    for k, ins in univ.items():
        if len(ins.series.dropna()) < 300:
            continue
        v = valuation(ins, frame, curve_pca); c = carry(ins, frame, gating); s = seasonality(ins, month); p = positioning(ins, cftc_m)
        rows.append(dict(key=k, label=ins.label, asset_class=ins.asset_class, region=ins.region, quality=ins.quality, S_V=v["S_V"], S_C_raw=c["S_C_raw"],
                         S_S=s["S_S"], S_P=p["S_P"], val_note=v["note"], reg_z=v["reg_z"], pca_z=v["pca_z"], carry_ir=c["ir"], carry_detail=c["detail"],
                         carry_q=c["quality"], seas_t=s["t_recent"], seas_sub=s["subperiods"], seas_note=s["note"], align=p["align"], crowd=p["crowd"],
                         stretch=p["stretch"], split=p["split"], mature=p["mature"], pos_src=p["source"],
                         event=bool(((soon["region"] == ins.region) | (soon["region"] == "US")).any()) if len(soon) else False,
                         adv_2w=U.adverse_2w_move(ins), long_means=ins.long_means))
    df = pd.DataFrame(rows)
    if df.empty:
        return df, curve_pca
    # cross-sectional carry z within asset class, then clip and penalties
    df["S_C"] = np.nan
    for ac, g in df.groupby("asset_class"):
        ir = g["S_C_raw"]
        if ir.notna().sum() >= 3 and ir.std() > 0:
            z = (ir - ir.mean()) / ir.std()
        else:
            z = ir
        pen = 0.5 * (g["pca_z"].abs() > 2).astype(float) + 0.5 * ((g["carry_ir"] < 1.5) & g["carry_ir"].notna()).astype(float)
        df.loc[g.index, "S_C"] = (z.clip(-3, 3) - pen).where(ir.notna())
    pil = ["S_V", "S_C", "S_S", "S_P"]
    W = np.array([weights["valuation"], weights["carry"], weights["seasonality"], weights["positioning"]])
    def comp(r):
        vals = np.array([r[p] for p in pil], dtype=float); m = np.isfinite(vals)
        if not m.any():
            return np.nan, np.nan
        w = W[m] / W[m].sum()
        return float((vals[m] * w).sum()), float(1 - np.std(vals[m]) / 3.0) if m.sum() > 1 else 0.5
    cc = df.apply(comp, axis=1, result_type="expand")
    df["composite"], df["conviction"] = cc[0], cc[1].clip(0, 1)
    def flags(r):
        f = []
        if r["crowd"] > 0 or (np.isfinite(r["stretch"]) and r["stretch"] >= 80):
            f.append("CROWDED")
        vals = [r[p] for p in pil if np.isfinite(r[p])]
        if len(vals) >= 2 and max(vals) >= 1 and min(vals) <= -1:
            f.append("CONFLICT")
        if r["event"]:
            f.append("EVENT")
        if "NON-STAT" in str(r["val_note"]):
            f.append("NON-STAT")
        if sum(np.isfinite(r[p]) for p in pil) <= 2:
            f.append("THIN")
        return " ".join(f)
    df["flags"] = df.apply(flags, axis=1)
    return df.sort_values("composite", ascending=False).reset_index(drop=True), curve_pca


def render():
    ui.step("T4–T8", "Four screening pillars & Trade Screener (§1.6–1.7)",
            "Which instrument expresses the theme best — cheap, paid to wait, seasonally supported, and not already crowded?")
    with st.sidebar:
        st.markdown("**Screener weights**")
        wv = st.slider("Valuation", 0.0, 1.0, DEFAULT_W["valuation"], 0.05)
        wc = st.slider("Carry", 0.0, 1.0, DEFAULT_W["carry"], 0.05)
        ws = st.slider("Seasonality", 0.0, 1.0, DEFAULT_W["seasonality"], 0.05)
        wp = st.slider("Positioning", 0.0, 1.0, DEFAULT_W["positioning"], 0.05)
    weights = dict(valuation=wv, carry=wc, seasonality=ws, positioning=wp)
    frame, _, _ = D.load_universe()
    table, history = R.state_variables(frame); cls = R.classify(table, history)
    gate = {"Stable": 1.0, "Stable (low RC)": 1.0, "Early transition": 0.5}.get(cls["state"], 0.0)
    month = st.selectbox("Seasonality window (calendar month about to open)", list(range(1, 13)), index=(pd.Timestamp.today().month % 12),
                         format_func=lambda m: pd.Timestamp(2000, m, 1).strftime("%B"))
    st.caption(f"Carry gating from the regime engine: state **{cls['state']}** → carry score × {gate:.1f} (full in Stable, halved in Early transition, carry-longs ≤ 0 in Confirmed transition). Quadrant {cls['quadrant']}, RC {cls['rc']:.2f}.")
    df, curve_pca = run_screener(weights, gate, month)
    if df.empty:
        st.warning("Screener universe empty — data unavailable."); return

    st.markdown(f"**Composite = {wv:.2f}·S_V + {wc:.2f}·S_C + {ws:.2f}·S_S + {wp:.2f}·S_P**, each pillar on ±3, positive favours the canonical long. Conviction = 1 − dispersion/3.")
    classes = st.multiselect("Asset classes", sorted(df["asset_class"].unique()), default=sorted(df["asset_class"].unique()))
    view = df[df["asset_class"].isin(classes)]
    cols = ["label", "asset_class", "composite", "conviction", "S_V", "S_C", "S_S", "S_P", "flags", "long_means", "quality"]
    fmtd = {"composite": "{:+.2f}", "conviction": "{:.2f}", "S_V": "{:+.2f}", "S_C": "{:+.2f}", "S_S": "{:+.2f}", "S_P": "{:+.2f}"}

    st.markdown("#### Read 1 — high composite, high conviction")
    top = view[(view["conviction"] >= 0.5)].sort_values("composite", key=abs, ascending=False).head(12)
    st.dataframe(top[cols].style.format(fmtd).background_gradient(subset=["composite"], cmap="RdYlGn", vmin=-2, vmax=2), use_container_width=True, hide_index=True)
    st.markdown("#### Read 2 — conflict rows (cheap but crowded-short = squeeze; rich but strong and uncrowded = don't fight it yet)")
    conf = view[view["flags"].str.contains("CONFLICT|CROWDED")]
    st.dataframe(conf[cols].style.format(fmtd), use_container_width=True, hide_index=True)
    st.markdown("#### Full table")
    st.dataframe(view[cols + ["val_note", "carry_detail", "seas_t", "seas_sub", "seas_note", "align", "crowd", "stretch", "pos_src", "adv_2w"]]
                 .style.format({**fmtd, "seas_t": "{:+.2f}", "align": "{:+.2f}", "crowd": "{:.2f}", "stretch": "{:.0f}", "adv_2w": "{:.1f}"}),
                 use_container_width=True, hide_index=True, height=520)
    st.markdown(ui.badge("live") + " valuation / positioning (CTA model) · " + ui.badge("proxy") + " carry for futures and FX (cash curve, policy rates) · "
                + ui.badge("unavailable") + " commodity convenience yield, FX carry without a public short rate, CFTC crowd when the file is missing", unsafe_allow_html=True)
    st.caption("Seasonality: window location and significance testing are structurally separated; gate 1 |t| ≥ 2.25 on Apr-2021→now, gate 2 same-sign |t| ≥ 1 in ≥ 3 of 4 fixed sub-periods. With 12 years of history only two sub-periods exist, so S_S is 0 by construction until longer history is loaded — the t-stats are shown for inspection only.")

    with st.expander("Valuation pillar — PCA lens on the UST curve"):
        if not curve_pca.empty:
            st.dataframe(curve_pca.style.format("{:+.2f}"), use_container_width=True)
            st.caption(f"2-PC reconstruction on the 4-point public curve (a 3-PC fit on 4 points leaves a rank-1 residual), 2y window; explained variance {', '.join(f'{e:.1%}' for e in curve_pca.attrs.get('explained', []))}. Cheap on both the univariate and PCA lenses is the highest-quality signal.")
        fig = go.Figure(go.Bar(x=view["label"], y=view["S_V"], marker_color=[D.GREEN if v > 0 else D.RED for v in view["S_V"].fillna(0)]))
        fig.update_layout(height=280, margin=dict(l=10, r=10, t=30, b=80), title="S_V by instrument (+ = cheap in the common frame)")
        st.plotly_chart(fig, use_container_width=True)
    with st.expander("Carry pillar — formulas"):
        st.latex(r"Carry(\tau,h)=[y(\tau)-r_{fund}]\,h \quad Rolldown(\tau,h)=[y(\tau)-y(\tau-h)]\,D_{mod}(\tau-h) \quad CarryRatio=\frac{(Carry+Rolldown)_{ann}}{\sigma_{ann}}")
        st.latex(r"Carry_{fx}\approx i_{dom}-i_{for}\ \text{net of basis} \quad VolAdjCarry=Carry_{fx}/\sigma_{implied}(3m)")
        st.caption("Structural carry (term premium) is split from path-contingent carry (priced cuts that die once delivered) in the narrative, not in the number. Rates, EGB-spread, FX and rates-vol carry are one short-vol, short-liquidity bet: one aggregate de-risk dial (regime gating above) caps total gross.")
