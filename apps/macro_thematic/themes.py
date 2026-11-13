"""T13 — Theme tracker: theme records, scenarios, Bayesian update, lifecycle (§1.4–1.5)."""

import copy

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from datahub import kelly, ui

from . import confirmation as C
from . import data as D

ODDS_BANDS = {"near-certain (≥85%)": 0.9, "likely (60–85%)": 0.72, "toss-up (40–60%)": 0.5, "unlikely (15–40%)": 0.27, "tail (<15%)": 0.08}

EXAMPLE_THEMES = [
    dict(name="Stagflation / supply shock", kind="regime", status="example", catalyst="Energy supply disruption; Brent > $90 with OPEC+ discipline",
         mechanism="Energy ↑ → headline inflation ↑, term premium ↑, growth equities ↓; central banks caught between mandates",
         competing="Demand destruction arrives fast: oil fades, breakevens roll over, growth scare dominates → bull-steepener instead",
         asset_map="5s30s / 10s30s bear-steepener, gold and oil calls, long EUR puts", narrative="Supply inflation",
         expression="5s30s bear-steepener (delta-one) + Brent call spread", invalidation="Brent < $80 and 5y5y BE back below 2.2% for 10 sessions",
         priced_bp=10.0, unit="bp on 5s30s", news_intensity=60,
         scenarios=[dict(name="Escalation, oil +20%", prob=0.25, outcome=35), dict(name="Grind higher, oil flat-up", prob=0.40, outcome=12),
                    dict(name="De-escalation, oil −15%", prob=0.25, outcome=-10), dict(name="Demand scare", prob=0.10, outcome=-25)]),
    dict(name="Fiscal-dominance shift", kind="regime", status="example", catalyst="Deficit path re-rated; long-end auctions tail; credibility switch flips",
         mechanism="Long end cheapens independently of the policy path; sovereign spreads widen; currency weakens with yields up",
         competing="Treasury shortens issuance / Fed slows QT: term premium capped, curve bull-flattens on growth",
         asset_map="Steepeners, ASW, sovereign CDS, curve options", narrative="Policy repricing",
         expression="10s30s steepener; long 30Y payer swaption (convex)", invalidation="ACM 10Y TP falls > 20 bp over 20 sessions with DXY stable",
         priced_bp=5.0, unit="bp on 10s30s", news_intensity=45,
         scenarios=[dict(name="Switch confirmed", prob=0.30, outcome=30), dict(name="Slow drift", prob=0.40, outcome=8), dict(name="Reversal", prob=0.30, outcome=-12)]),
    dict(name="Disinflation / soft landing", kind="regime", status="example", catalyst="Core inflation 3m annualised back at target; labour cooling without breaking",
         mechanism="Cuts repriced in, bull-steepening, risk-on; carry baskets healthy", competing="Sticky services inflation: cuts priced out, bear-flattening, USD bid",
         asset_map="Front-end receivers, long equity and EM FX, carry baskets", narrative="Demand growth",
         expression="Long 2Y outright / receive 1y1y; long EM FX basket", invalidation="Core CPI 3m ann. > 3.5% or claims trend < −10% y/y",
         priced_bp=-40.0, unit="bp cumulative cuts 12m", news_intensity=50,
         scenarios=[dict(name="Cuts delivered faster", prob=0.30, outcome=-75), dict(name="As priced", prob=0.45, outcome=-40), dict(name="Cuts priced out", prob=0.25, outcome=0)]),
    dict(name="Trade policy / tariffs", kind="event", status="example", catalyst="Tariff round announcement / court ruling / retaliation window",
         mechanism="Goods-price impulse, growth drag, CNH/AUD weak; convex vol", competing="Negotiated carve-outs: impulse fades, risk-on relief rally",
         asset_map="Bear-steepener, long Brent, short risk FX, long convex vol", narrative="Supply inflation",
         expression="Long AUD puts / short AUD/JPY; SPX put spread", invalidation="Tariff round shelved; AUD/JPY above pre-announcement high",
         priced_bp=-2.0, unit="% on AUD/JPY", news_intensity=70,
         scenarios=[dict(name="Full round + retaliation", prob=0.30, outcome=-6), dict(name="Partial", prob=0.40, outcome=-2), dict(name="Shelved", prob=0.30, outcome=3)]),
]


def init_state():
    if "themes" not in st.session_state:
        st.session_state["themes"] = copy.deepcopy(EXAMPLE_THEMES)
    if "quality" not in st.session_state:
        st.session_state["quality"] = {}


QUALITY_CRITERIA = ["catalyst", "mechanism", "valuation", "carry", "direction", "confirmation", "positioning", "seasonality", "vol/skew", "EV & asymmetry"]


def lifecycle(breadth: int, saturation: float) -> str:
    if saturation < 40:
        return "Emerging — entry zone" if breadth >= 2 else "Emerging (thin breadth) — small"
    if saturation < 65:
        return "Established — hold, add on dislocation" if breadth >= 3 else "Established (narrow) — watch breadth"
    if breadth >= 3:
        return "Consensus — no adds, convex fades only"
    return "Decaying — exit"


def saturation(frame, theme, cftc_metrics) -> dict:
    """Mean percentile of price extension, positioning (if CFTC), news intensity (manual), valuation gap."""
    parts = {}
    # price extension: average 1y percentile of the theme's canonical assets (by narrative)
    assets = {"Supply inflation": ["brent", "bei10"], "Policy repricing": ["ust30", "tp10"], "Demand growth": ["spx", "copper"],
              "Liquidity expansion": ["eem", "dxy"], "Credit stress": ["hy_oas", "vix"]}.get(theme.get("narrative"), ["spx"])
    ext = [D.pct_rank(D.series(frame, a), 252) for a in assets]
    ext = [e for e in ext if np.isfinite(e)]
    parts["price extension"] = (float(np.mean(ext)), "live") if ext else (np.nan, "unavailable")
    if cftc_metrics is not None and not cftc_metrics.empty:
        parts["positioning"] = (float(cftc_metrics["ratio_pct"].mean()), "live")
    else:
        parts["positioning"] = (np.nan, "unavailable")
    parts["news intensity"] = (float(theme.get("news_intensity", 50)), "manual")
    # valuation gap: |edge| relative to scenario std
    sc = theme.get("scenarios", [])
    if sc:
        mom = kelly.moments([s["prob"] for s in sc], [s["outcome"] for s in sc])
        gap = abs(mom["mean"] - float(theme.get("priced_bp", 0))) / mom["std"] if mom["std"] > 0 else 0
        parts["valuation gap"] = (float(min(100, 100 * (1 - np.exp(-gap)))), "live")
    vals = [v for v, q in parts.values() if np.isfinite(v)]
    return dict(S=float(np.mean(vals)) if vals else np.nan, parts=parts)


def render():
    ui.step("T13", "Theme tracker — theme & scenarios, narrative record (§1.4–1.5)",
            "What question is the market asking, what are the answers with odds, and where is the edge versus what is priced?")
    init_state()
    frame, _, _ = D.load_universe()
    cftc_m, cftc_status, _ = D.load_cftc()
    themes = st.session_state["themes"]

    c1, c2, c3 = st.columns([3, 1, 1])
    names = [t["name"] for t in themes]
    sel = c1.selectbox("Theme", names + ["+ new theme"])
    if sel == "+ new theme":
        new_name = c2.text_input("Name")
        if c3.button("Create") and new_name:
            themes.append(dict(name=new_name, kind="regime", status="draft", catalyst="", mechanism="", competing="", asset_map="", narrative="Demand growth",
                               expression="", invalidation="", priced_bp=0.0, unit="bp", news_intensity=50,
                               scenarios=[dict(name="Base", prob=0.5, outcome=0.0), dict(name="Alt", prob=0.5, outcome=0.0)]))
            st.rerun()
        return
    t = themes[names.index(sel)]
    if c3.button("Delete theme"):
        themes.remove(t); st.rerun()

    st.markdown(f"**Record** {ui.badge(t.get('status', 'manual'))}", unsafe_allow_html=True)
    a, b = st.columns(2)
    t["kind"] = a.selectbox("Classed as", ["regime", "event"], index=0 if t.get("kind") == "regime" else 1, key=f"kind_{sel}")
    t["narrative"] = b.selectbox("Confirmation narrative", list(C.NARRATIVES.keys()), index=list(C.NARRATIVES.keys()).index(t.get("narrative", "Demand growth")), key=f"nar_{sel}")
    t["catalyst"] = st.text_input("Catalyst", t.get("catalyst", ""), key=f"cat_{sel}")
    t["mechanism"] = st.text_area("Mechanism (transmission)", t.get("mechanism", ""), key=f"mech_{sel}", height=70)
    t["competing"] = st.text_area("Competing narrative (mandatory)", t.get("competing", ""), key=f"comp_{sel}", height=70)
    if not t["competing"].strip():
        st.error("Competing narrative is mandatory — the record is incomplete.")
    t["asset_map"] = st.text_input("Expected asset map", t.get("asset_map", ""), key=f"am_{sel}")
    t["expression"] = st.text_input("Preferred expression", t.get("expression", ""), key=f"ex_{sel}")
    t["invalidation"] = st.text_input("Invalidation (so a colleague could enforce it)", t.get("invalidation", ""), key=f"inv_{sel}")

    st.markdown("#### Scenarios — mutually exclusive and exhaustive on the axis")
    sc = pd.DataFrame(t["scenarios"])
    sc = st.data_editor(sc, num_rows="dynamic", use_container_width=True, key=f"sc_{sel}",
                        column_config={"prob": st.column_config.NumberColumn("prob", min_value=0.0, max_value=1.0, step=0.05, format="%.2f"),
                                       "outcome": st.column_config.NumberColumn(f"outcome ({t.get('unit','bp')})")})
    sc = sc.dropna(subset=["prob", "outcome"])
    t["scenarios"] = sc.to_dict("records")
    x1, x2, x3 = st.columns(3)
    t["unit"] = x1.text_input("Outcome unit", t.get("unit", "bp"), key=f"unit_{sel}")
    t["priced_bp"] = x2.number_input(f"Δ priced by the market ({t['unit']})", value=float(t.get("priced_bp", 0.0)), key=f"pr_{sel}")
    t["news_intensity"] = x3.slider("News intensity percentile (manual)", 0, 100, int(t.get("news_intensity", 50)), key=f"ni_{sel}")
    st.caption("Odds bands: near-certain ≥85 · likely 60–85 · toss-up 40–60 · unlikely 15–40 · tail <15. Written before the event, anchored to prediction markets, OIS-implied odds and nowcasts.")

    if len(sc) >= 2:
        probs = kelly.normalise(sc["prob"].tolist()); mom = kelly.moments(probs, sc["outcome"].tolist())
        edge = mom["mean"] - float(t["priced_bp"])
        ui.kpi_row([("E[Δ]", f"{mom['mean']:+.1f} {t['unit']}"), ("σ[Δ]", f"{mom['std']:.1f}"), ("Entropy H", f"{mom['entropy']:.2f} / {np.log(len(sc)):.2f} max"),
                    ("Skew", f"{mom['skew']:+.2f}"), ("Edge = E[Δ] − Δ_priced", f"{edge:+.1f} {t['unit']}")])
        if abs(mom["skew"]) > 0.5 and abs(edge) < 0.5 * mom["std"]:
            st.info("Modal scenario roughly priced but tails lopsided → skewed distribution: favour a convex expression (see Leg choice).")
        fig = go.Figure(go.Bar(x=sc["name"], y=probs, marker_color=D.NAVY, text=[f"{o:+.0f}" for o in sc["outcome"]], textposition="outside"))
        fig.add_vline(x=-0.5, line=dict(width=0))
        fig.update_layout(height=260, margin=dict(l=10, r=10, t=30, b=10), title="Scenario probabilities (labels = outcome)", yaxis_title="p")
        st.plotly_chart(fig, use_container_width=True)
        t["_mom"] = mom; t["_edge"] = edge

        with st.expander("Bayesian update — p_post ∝ p_prior · L(evidence | s_i)"):
            lik = []
            cols = st.columns(len(sc))
            for i, (c, name) in enumerate(zip(cols, sc["name"])):
                lik.append(c.slider(f"L(evidence|{name})", 0.0, 1.0, 0.5, 0.05, key=f"lik_{sel}_{i}"))
            post = kelly.normalise(probs * np.array(lik))
            upd = pd.DataFrame({"scenario": sc["name"], "prior": probs, "likelihood": lik, "posterior": post})
            st.dataframe(upd.style.format({"prior": "{:.2f}", "likelihood": "{:.2f}", "posterior": "{:.2f}"}), hide_index=True, use_container_width=True)
            if st.button("Adopt posterior as new odds", key=f"adopt_{sel}"):
                for s, p in zip(t["scenarios"], post):
                    s["prob"] = float(p)
                st.rerun()

    st.markdown("#### Lifecycle — breadth B and saturation S")
    conf = C.confirmation_table(frame, 20)
    row = conf[conf["narrative"] == t["narrative"]]
    B = int(row["breadth_classes"].iloc[0]) if len(row) else 0
    sat = saturation(frame, t, cftc_m)
    stage = lifecycle(B, sat["S"]) if np.isfinite(sat["S"]) else "n/a"
    ui.kpi_row([("Breadth B (asset classes confirming)", f"{B} / 6", None, row["detail"].iloc[0] if len(row) else None),
                ("Saturation S", f"{sat['S']:.0f}" if np.isfinite(sat["S"]) else "n/a"), ("Stage", stage)])
    st.markdown(" · ".join(f"{k}: {v:.0f} {ui.badge(q)}" if np.isfinite(v) else f"{k}: n/a {ui.badge(q)}" for k, (v, q) in sat["parts"].items()), unsafe_allow_html=True)
    if cftc_m is None or cftc_m.empty:
        st.caption(f"Positioning component: {cftc_status}")
    t["_B"], t["_S"], t["_stage"] = B, sat["S"], stage

    st.markdown("#### Theme transmission templates (§1.4)")
    st.dataframe(pd.DataFrame([
        ["Stagflation / supply shock", "Energy ↑, term premium ↑, growth equities ↓", "5s30s / 10s30s bear-steepener, gold and oil calls, long EUR puts"],
        ["Fiscal-dominance shift", "Long end cheapens independent of policy path; sovereign spreads widen", "Steepeners, ASW, sovereign CDS, curve options"],
        ["Disinflation / soft landing", "Cuts repriced in, bull-steepening, risk-on", "Front-end receivers, long equity and EM FX, carry baskets"],
        ["Banking / liquidity stress", "Front-end rally, credit wider, USD bid", "Long 2y, long CDX IG protection, long USD, index puts vs basket"],
        ["Trade policy / tariffs", "Goods-price impulse, growth drag, CNH/AUD weak", "Bear-steepener, long Brent, short risk FX, long convex vol"]],
        columns=["Active theme", "Transmission", "Where the expression lives"]), use_container_width=True, hide_index=True)

    st.download_button("Download themes & book (JSON)", D.state_json(), file_name="macro_thematic_state.json")
    up = st.file_uploader("Load state JSON", type="json", key="state_up")
    if up is not None:
        D.load_state_json(up.read().decode()); st.success("State loaded"); st.rerun()
