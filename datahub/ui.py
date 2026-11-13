"""Shared Streamlit chrome: process-step headers, provenance badges, data-health tables."""

import pandas as pd
import streamlit as st

NAVY, BRONZE, SLATE = "#1F3550", "#A9814F", "#55677C"
QUALITY_COLOURS = {"live": "#2E7D32", "proxy": "#B26A00", "synthetic": "#B71C1C", "estimated": "#B26A00",
                   "manual": "#455A64", "unavailable": "#9E9E9E"}


def page(title: str, icon: str = "📈"):
    st.set_page_config(page_title=title, page_icon=icon, layout="wide")
    st.markdown(
        """<style>
        .ip-badge{display:inline-block;padding:1px 8px;border-radius:10px;font-size:11px;font-weight:700;color:#fff;margin-left:6px}
        .ip-step{border-left:4px solid #A9814F;padding:4px 12px;margin:6px 0 12px 0;background:rgba(169,129,79,0.07)}
        .ip-step h3{margin:0;color:#1F3550} .ip-step p{margin:2px 0 0 0;color:#55677C;font-size:13px}
        .ip-q{font-style:italic;color:#55677C}
        </style>""", unsafe_allow_html=True)


def badge(quality: str) -> str:
    colour = QUALITY_COLOURS.get(quality, "#607D8B")
    return f'<span class="ip-badge" style="background:{colour}">{quality.upper()}</span>'


def step(number: str, title: str, question: str = "", quality: str = ""):
    """Header for one step of the investment-process chain."""
    b = badge(quality) if quality else ""
    q = f'<p class="ip-q">{question}</p>' if question else ""
    st.markdown(f'<div class="ip-step"><h3>{number} · {title}{b}</h3>{q}</div>', unsafe_allow_html=True)


def note(text: str):
    st.caption(text)


def health(status: pd.DataFrame, title: str = "Data provenance"):
    """Compact status table with colours by quality and a count of unavailable series."""
    if status is None or status.empty:
        st.info("No data loaded.")
        return
    n_bad = int((status["status"] != "loaded").sum())
    st.markdown(f"**{title}** — {len(status) - n_bad} series loaded, {n_bad} unavailable")
    show = status[["key", "name", "source", "ticker", "quality", "freq", "status", "last", "value", "note"]].copy()
    st.dataframe(show, use_container_width=True, hide_index=True, height=min(600, 38 + 35 * len(show)))


def kpi_row(items):
    """items: list of (label, value, delta_or_None, help_or_None)."""
    cols = st.columns(len(items))
    for c, it in zip(cols, items):
        label, value = it[0], it[1]
        delta = it[2] if len(it) > 2 else None
        help_ = it[3] if len(it) > 3 else None
        c.metric(label, value, delta, help=help_)


def fmt(x, nd=2, suffix=""):
    try:
        if x is None or pd.isna(x):
            return "n/a"
        return f"{x:,.{nd}f}{suffix}"
    except Exception:
        return str(x)


def legend():
    st.markdown(
        badge("live") + " observed market / official print &nbsp; " + badge("proxy") +
        " built from public data with a documented approximation &nbsp; " + badge("estimated") +
        " calendar date by rule, verify &nbsp; " + badge("manual") + " typed in by the desk &nbsp; " +
        badge("synthetic") + " generated, never traded on", unsafe_allow_html=True)
