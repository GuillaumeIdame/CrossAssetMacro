"""§1.5 — Seasonality: two gates (recent-sample t ≥ 2.25 AND same-sign significance in ≥ 3 of 4 fixed sub-periods)."""

import numpy as np
import pandas as pd
import streamlit as st

from datahub import ui

from . import common, data

SUBPERIODS = [("2000-01-01", "2007-12-31"), ("2008-01-01", "2014-12-31"), ("2015-01-01", "2019-12-31"), ("2020-01-01", "2025-12-31")]
RECENT_START = "2021-04-01"
T_GATE, LAMBDA, COST_BP = 2.25, 0.45, 2.0


def windows():
    """Calendar windows: 12 months and 24 half-months (fixed before any testing — location and significance are separated)."""
    out = []
    for m in range(1, 13):
        out.append((f"M{m:02d}", m, 1, 31))
        out.append((f"M{m:02d}a", m, 1, 15))
        out.append((f"M{m:02d}b", m, 16, 31))
    return out


def window_returns(px: pd.Series, month: int, d0: int, d1: int) -> pd.Series:
    """Log return of the window per year (first close on/after d0 to last close on/before d1)."""
    px = px.dropna(); out = {}
    for y in sorted(set(px.index.year)):
        sub = px[(px.index.year == y) & (px.index.month == month) & (px.index.day >= d0) & (px.index.day <= d1)]
        if len(sub) >= 5:
            out[y] = float(np.log(sub.iloc[-1] / sub.iloc[0]))
    return pd.Series(out)


def tstat(x: pd.Series) -> float:
    x = x.dropna()
    return float(x.mean() / (x.std(ddof=1) / np.sqrt(len(x)))) if len(x) >= 3 and x.std(ddof=1) > 0 else np.nan


@st.cache_data(ttl=3600, show_spinner=False)
def screen(fx_long: pd.DataFrame, ccy: str) -> pd.DataFrame:
    if fx_long.empty or ccy not in fx_long.columns:
        return pd.DataFrame()
    px = fx_long[ccy].dropna()
    today = pd.Timestamp.today().normalize()
    rows = []
    for name, month, d0, d1 in windows():
        r = window_returns(px, month, d0, d1)
        if r.empty:
            continue
        recent = r[r.index >= pd.Timestamp(RECENT_START).year]
        t_recent = tstat(recent)
        sign = np.sign(recent.mean()) if len(recent) else 0
        dots = []
        for a, b in SUBPERIODS:
            sp = r[(r.index >= pd.Timestamp(a).year) & (r.index <= pd.Timestamp(b).year)]
            t = tstat(sp)
            dots.append(bool(np.isfinite(t) and abs(t) >= 1.0 and np.sign(sp.mean()) == sign))
        gate1 = bool(np.isfinite(t_recent) and abs(t_recent) >= T_GATE)
        gate2 = sum(dots) >= 3
        # next occurrence of the window start
        start = pd.Timestamp(year=today.year, month=month, day=d0)
        if start < today - pd.Timedelta(days=(d1 - d0)):
            start = pd.Timestamp(year=today.year + 1, month=month, day=d0)
        days_to = (start - today).days
        end = pd.Timestamp(year=start.year, month=month, day=min(d1, 28 if month == 2 else 30 if month in (4, 6, 9, 11) else 31))
        status = "active" if start <= today <= end else ("upcoming" if 0 < days_to <= 30 else "closed/far")
        prox = np.exp(-max(days_to, 0) / 10.0)
        ev_net = sign * r.mean() * 1e4 - COST_BP
        score = sign * min(abs(t_recent) / T_GATE, 1.5) * prox * (1 - LAMBDA) if (gate1 and gate2) else 0.0
        rows.append(dict(window=name, start=start.date(), end=end.date(), days_to_entry=days_to, status=status, n_years=len(r),
                         t_recent=t_recent, gate1=gate1, dots=sum(dots), gate2=gate2, survivor=gate1 and gate2,
                         hit_rate=float((np.sign(r) == sign).mean()) if sign else np.nan, mean_bp=r.mean() * 1e4,
                         ev_net_bp=ev_net, sharpe_per_occ=float(r.mean() / r.std()) if r.std() > 0 else np.nan, score=score,
                         robustness="".join("●" if d else "○" for d in dots)))
    out = pd.DataFrame(rows)
    return out.sort_values(["survivor", "days_to_entry"], ascending=[False, True]) if not out.empty else out


def render():
    ui.step("5", "Seasonality — two gates", "Locate the window on 2000–2025 → Gate 1: |t| ≥ 2.25 on Apr-2021→now → Gate 2: same-sign significance in ≥ 3 of 4 fixed sub-periods → EV × λ (0.45).", "live")
    m = data.load_all(); fx_long = m["fx_long"]
    if fx_long.empty:
        st.warning("Long FX history (FRED H.10) unavailable; the screener needs 2000+ history."); return
    ccy = st.selectbox("Pair", data.CCYS, format_func=lambda c: data.PAIR_LABEL[c], key="fx_seas_ccy")
    px = fx_long[ccy].dropna() if ccy in fx_long.columns else pd.Series(dtype=float)
    if px.empty:
        st.warning("No long history for this pair."); return
    st.caption(f"History used: FRED H.10 daily {ccy} from {px.index[0].date()} to {px.index[-1].date()} (USD per {ccy}; positive = {ccy} up). "
               "Windows are the 12 calendar months and 24 half-months, fixed before testing: there is no 'select by max t on window W' path. Sub-period boundaries are never tuned.")
    tab = screen(fx_long, ccy)
    surv = tab[tab["survivor"]]
    c1, c2, c3 = st.columns(3)
    c1.metric("Windows tested", len(tab)); c2.metric("Survivors (both gates)", len(surv)); c3.metric("Next survivor opens in", f"{int(surv['days_to_entry'].min())} d" if len(surv) else "—")
    st.markdown("**Survivors** — overlay on entry timing and size of trades that exist for other reasons, ≤ 10–20% of risk; standalone only with a written flow mechanism (month/quarter-end rebalancing, coupon repatriation, JPY fiscal year).")
    cols = ["window", "start", "end", "days_to_entry", "status", "n_years", "t_recent", "robustness", "hit_rate", "ev_net_bp", "sharpe_per_occ", "score"]
    st.dataframe(common.dfmt(surv[cols]) if len(surv) else pd.DataFrame(columns=cols), use_container_width=True, hide_index=True)
    with st.expander("All windows (audit record)"):
        st.dataframe(common.dfmt(tab[cols + ["gate1", "dots", "gate2"]]), use_container_width=True, hide_index=True)
    st.caption("Score S_S = dir·min(|t|/2.25, 1.5)·prox·(1−λ), prox = exp(−days-to-entry/10); zero unless both gates pass. EV net of a 2bp round trip. "
               "Governance: log realised vs expected hit rate (drift = decay alarm), retire fading windows, re-admit annually; orthogonalise the sleeve against trend, carry, value, momentum before sizing.")
    if len(tab):
        pick = st.selectbox("Inspect window", tab["window"].tolist(), key="fx_seas_pick")
        w = next(x for x in windows() if x[0] == pick)
        r = window_returns(px, w[1], w[2], w[3]) * 1e4
        st.plotly_chart(common.bars(r, f"{data.PAIR_LABEL[ccy]} — {pick} return per year (bp)"), use_container_width=True)
