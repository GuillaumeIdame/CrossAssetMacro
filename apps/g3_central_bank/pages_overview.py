"""Page 1 — Countdown to an event (§1.2) and the process chain."""

import pandas as pd
import streamlit as st

from datahub import calendar, ui

from . import common as C

CHAIN = ["Fundamental assessment", "Expected distribution", "Market distribution", "Market pricing", "Trade", "Kelly size"]
CHAIN_PAGE = {0: "Macro read", 1: "Three distributions", 2: "Market-implied state", 3: "Market-implied state",
              4: "Distribution tree & valuation", 5: "Distribution tree & valuation"}

STAGE_CHECKS = {
    "~2 weeks before": ["Broad growth and inflation assessment written (spot vs forward, hard vs soft)",
                        "Reaction function re-read; committee map (hawks / doves / centrists) current",
                        "Qualitative distribution for the next 3–4 meetings; futures valuation; first options valuation",
                        "Strike map wide: which strikes are relevant at this width?"],
    "~1 week before": ["Update with new data, surveys, Smart Forecasters, central-bank communication",
                       "Re-read market pricing across futures, options, implied distribution",
                       "Distribution narrowing — does the book narrow with it?",
                       "Event-amplification check on positioning (CFTC / CTA rows)"],
    "2-3 days before": ["Expected print and probability distribution refined vs market-implied",
                        "Futures fair value, meeting pricing, options EV, best expression, Kelly size",
                        "Relevant strikes, potential pin, gamma concentration identified",
                        "Exit test: can the position be cut at a reasonable price right after the print?"],
    "post-event": ["Scenario tree vs realised outcome logged", "Positioning read vs reaction logged",
                   "Restart the cycle for the next release"],
}


def render():
    ui.step("1.2", "Countdown to an event",
            "Is current front-end pricing consistent with the assessment of the growth and inflation path and the reaction function?")
    ui.legend()
    cal = C.cal()
    today = pd.Timestamp.today().normalize()

    # --- chain stepper -------------------------------------------------------
    pos = st.session_state.get("chain_position", 0)
    cols = st.columns(len(CHAIN))
    for i, (c, name) in enumerate(zip(cols, CHAIN)):
        style = f"background:{C.BRONZE};color:#fff" if i == pos else f"background:rgba(31,53,80,0.08);color:{C.NAVY}"
        c.markdown(f'<div style="text-align:center;padding:8px 4px;border-radius:6px;font-size:12px;font-weight:700;{style}">{i + 1}. {name}</div>',
                   unsafe_allow_html=True)
    st.session_state["chain_position"] = st.select_slider("Where the desk is in the chain", options=list(range(len(CHAIN))),
                                                          value=pos, format_func=lambda i: CHAIN[i])
    st.caption(f"Next page in the chain: **{CHAIN_PAGE[st.session_state['chain_position']]}**")

    # --- next events per region ---------------------------------------------
    st.subheader("Next tier-1 events")
    up = calendar.upcoming(90, regions=("US", "EA", "UK", "JP", "CH"), cal=cal)
    tier1 = up[up["tier"] == 1]
    cards = st.columns(3)
    for col, region in zip(cards, ("US", "EA", "UK")):
        r = tier1[tier1["region"] == region]
        m = r[r["type"] == "meeting"].head(1)
        with col:
            st.markdown(f"**{C.REGION_LABEL[region]} — {region}**")
            if not m.empty:
                row = m.iloc[0]
                st.metric(f"Next meeting · {row['event']}", row["date"].strftime("%a %d %b %Y"), f"{int(row['days_to'])} days",
                          delta_color="off", help=f"calendar status: {row['status']}")
                st.markdown(ui.badge(row["status"]) + f" &nbsp; <span style='color:{C.SLATE};font-size:12px'>{calendar.countdown_stage(int(row['days_to']))}</span>",
                            unsafe_allow_html=True)
                counts = calendar.counts_before(row["date"], region, cal=cal)
                st.caption(f"Information still to come before the meeting: {counts['inflation']} inflation · {counts['growth']} growth · "
                           f"{counts['labour']} labour releases ({counts['tier1']} tier-1, incl. US)")
            else:
                st.info("No meeting in the next 90 days in the calendar file.")
            rel = r[r["type"] == "release"].head(4)
            for _, e in rel.iterrows():
                st.markdown(f"<span style='font-size:13px'>• {e['date'].strftime('%d %b')} — {e['event']} "
                            f"<span style='color:{C.SLATE}'>({int(e['days_to'])}d)</span> {ui.badge(e['status'])}</span>", unsafe_allow_html=True)

    # --- countdown work table -------------------------------------------------
    st.subheader("Countdown work plan")
    st.markdown("""
| When | Work | Output |
|---|---|---|
| **~2 weeks before** | Broad growth and inflation assessment: spot vs forward, hard vs soft data, historical regime, reaction function | Qualitative distribution; valuation of the next 3–4 meetings; futures valuation; first options valuation. Distribution wide, many strikes relevant |
| **~1 week before** | Update with new data, surveys, Smart Forecasters, central-bank communication | Market pricing re-read across futures, options and the implied distribution. Distribution begins to narrow |
| **2–3 days before** | Refine expected print and probability distribution against the market-implied one | Futures fair value, meeting pricing, options EV, best expression, Kelly size. Relevant strikes, potential pin and gamma concentration identified |
""")
    nxt = tier1[tier1["type"] == "meeting"].head(1)
    days = int(nxt["days_to"].iloc[0]) if not nxt.empty else 99
    stage = calendar.countdown_stage(days).split(":")[0]
    key = next((k for k in STAGE_CHECKS if stage.startswith(k)), "post-event")
    st.markdown(f"**Checklist for the current stage — {stage}**")
    done = C.ss_get("stage_checks", {})
    for i, item in enumerate(STAGE_CHECKS[key]):
        done[f"{key}:{i}"] = st.checkbox(item, value=done.get(f"{key}:{i}", False), key=f"chk_{key}_{i}")
    st.session_state["stage_checks"] = done

    # --- full calendar window -------------------------------------------------
    with st.expander("Full calendar, next 90 days (edit data/g3_calendar.csv to change)"):
        show = up[["date", "days_to", "region", "type", "event", "tier", "gauge", "status", "note"]].copy()
        show["date"] = show["date"].dt.date
        st.dataframe(show, hide_index=True, width="stretch", height=min(600, 38 + 35 * len(show)))
