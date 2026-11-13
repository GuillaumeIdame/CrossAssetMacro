"""T14 — Daily one-pager and the operating cycle (§4.3–4.4)."""

import numpy as np
import pandas as pd
import streamlit as st

from datahub import ui

from . import confirmation as C
from . import crowding as K
from . import data as D
from . import regime as R
from . import screener as S
from . import themes as T


def compose() -> str:
    frame, _, _ = D.load_universe()
    table, hist = R.state_variables(frame); cls = R.classify(table, hist)
    conf = C.confirmation_table(frame, 20); dv = C.divergences(frame, 20)
    notes = st.session_state.get("divergence_notes", {})
    unresolved = [r["divergence"] for _, r in dv.iterrows() if r["active"] and not notes.get(r["divergence"])]
    resolved = [f"{r['divergence']} → {notes.get(r['divergence'])}" for _, r in dv.iterrows() if r["active"] and notes.get(r["divergence"])]
    crowd, _ = K.crowding_table()
    gate = {"Stable": 1.0, "Stable (low RC)": 1.0, "Early transition": 0.5}.get(cls["state"], 0.0)
    scr, _ = S.run_screener(S.DEFAULT_W, gate, pd.Timestamp.today().month % 12 + 1)
    T.init_state()
    today = pd.Timestamp.today().strftime("%Y-%m-%d")
    lines = [f"# Macro Thematic — daily one-pager · {today}", "",
             "## State", f"* Regime: **{cls['quadrant']}** · RC {cls['rc']:.2f} · {cls['state']} ({cls['days_in']} days in quadrant)", f"* Playbook: {cls['playbook']}",
             "* State variables: " + ", ".join(f"{r['variable']} z {r['z']:+.1f} (m {r['m']:+.1f})" for _, r in table.iterrows() if np.isfinite(r["z"])), "",
             "## Evidence"]
    for _, r in conf.iterrows():
        lines.append(f"* {r['narrative']}: {r['confirmed']} confirmed, breadth {r['breadth_classes']}")
    lines.append("* Divergences resolved: " + ("; ".join(resolved) if resolved else "none active/resolved"))
    lines.append("* Divergences UNRESOLVED: " + (", ".join(unresolved) if unresolved else "none"))
    lines += ["", "## Positioning"]
    if not crowd.empty:
        top3 = crowd.head(3)
        lines.append("* Top-3 crowding: " + "; ".join(f"{r['label']} C {r['C']:.0f} ({r['band']}, crowd {r['crowd_direction']})" for _, r in top3.iterrows()))
        cross = crowd[(crowd["C"] >= 65)]
        lines.append("* Threshold crossings (C ≥ 65): " + (", ".join(cross["label"]) if len(cross) else "none"))
    lines += ["", "## Action"]
    if not scr.empty:
        best = scr[(scr["conviction"] >= 0.5) & (~scr["flags"].str.contains("CROWDED"))].sort_values("composite", key=abs, ascending=False)
        if len(best):
            b = best.iloc[0]
            side = "LONG" if b["composite"] > 0 else "SHORT"
            lines.append(f"* Best trade: {side} {b['label']} — composite {b['composite']:+.2f}, conviction {b['conviction']:.2f} ({b['long_means']}); worst 2w move {b['adv_2w']:.1f}")
        avoid = scr[scr["flags"].str.contains("CROWDED")].head(3)
        lines.append("* Avoid: " + (", ".join(f"{r['label']} ({r['flags']})" for _, r in avoid.iterrows()) if len(avoid) else "none flagged"))
        wait = scr[scr["flags"].str.contains("CONFLICT")].head(3)
        lines.append("* Wait for dislocation: " + (", ".join(wait["label"]) if len(wait) else "none"))
    for t in st.session_state["themes"]:
        lines.append(f"* Theme {t['name']}: {t.get('_stage', 'stage n/a')} · edge {t.get('_edge', float('nan')):+.1f} {t.get('unit','')} · expression: {t.get('expression','')}")
    return "\n".join(lines)


def render():
    ui.step("T14", "Daily one-pager & operating cycle (§4.3–4.4)", "State · Evidence · Positioning · Action — out before the market opens.")
    with st.spinner("Composing from the live pages..."):
        md = compose()
    st.markdown(md)
    st.download_button("Download one-pager (Markdown)", md, file_name=f"macro_thematic_onepager_{pd.Timestamp.today():%Y%m%d}.md")
    st.markdown("#### Operating cycle")
    st.dataframe(pd.DataFrame([
        ["Pre-market", "Regime refresh, overnight moves vs confirmation map, event risk, one-pager out"],
        ["Morning", "Positioning updates, CTA proxy, options/skew; divergences resolved in writing"],
        ["Intraday", "Transition monitoring, vol shocks, liquidity in held expressions"],
        ["Post-close", "Recompute momentum/z-scores, factor exposures, theme states, quality re-rank"],
        ["Friday", "CFTC deep dive, replication validation, carry/valuation re-fit, stress refresh"],
        ["Event-driven", "Unwind tree and portfolio stress within the hour of a major shock"]], columns=["When", "Process"]), use_container_width=True, hide_index=True)
    cal = D.load_calendar(); today = pd.Timestamp.today().normalize()
    up = cal[(cal["date"] >= today) & (cal["date"] <= today + pd.Timedelta(days=10))]
    st.markdown("#### Event risk, next 10 days " + ui.badge("estimated"), unsafe_allow_html=True)
    st.dataframe(up[["date", "region", "event", "tier", "gauge", "status"]], use_container_width=True, hide_index=True)
