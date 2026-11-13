"""Charts, palette and session helpers shared by the Macro FX pages."""

import json

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

NAVY, BRONZE, SLATE, HAIR = "#1F3550", "#A9814F", "#55677C", "#D9DEE5"
PALETTE = [NAVY, BRONZE, SLATE, "#7A9CC6", "#C9A77C", "#8FA0B2", "#3E5C80", "#D9B98A"]
LAYOUT = dict(template="plotly_white", margin=dict(l=40, r=20, t=40, b=40), height=360,
              font=dict(family="Segoe UI, Helvetica, Arial", size=12), legend=dict(orientation="h", y=-0.2))


def line(df: pd.DataFrame, title: str = "", yaxis: str = "", height: int = 360, hline=None) -> go.Figure:
    fig = go.Figure()
    for i, c in enumerate(df.columns):
        fig.add_trace(go.Scatter(x=df.index, y=df[c], name=str(c), line=dict(color=PALETTE[i % len(PALETTE)], width=1.6)))
    if hline is not None:
        for h in (hline if isinstance(hline, (list, tuple)) else [hline]):
            fig.add_hline(y=h, line=dict(color=HAIR, width=1, dash="dot"))
    fig.update_layout(title=title, yaxis_title=yaxis, **{**LAYOUT, "height": height})
    return fig


def bars(s: pd.Series, title: str = "", color_by_sign: bool = True, height: int = 320, orientation="v") -> go.Figure:
    colours = [BRONZE if v >= 0 else SLATE for v in s.values] if color_by_sign else NAVY
    if orientation == "h":
        fig = go.Figure(go.Bar(y=[str(i) for i in s.index], x=s.values, orientation="h", marker_color=colours))
    else:
        fig = go.Figure(go.Bar(x=[str(i) for i in s.index], y=s.values, marker_color=colours))
    fig.update_layout(title=title, **{**LAYOUT, "height": height})
    return fig


def heatmap(df: pd.DataFrame, title: str = "", zmid: float = 0.0, zmax: float = 3.0, height: int = 380, fmt=".2f") -> go.Figure:
    fig = go.Figure(go.Heatmap(z=df.values, x=[str(c) for c in df.columns], y=[str(i) for i in df.index],
                               colorscale=[[0, SLATE], [0.5, "#F5F7FA"], [1, BRONZE]], zmid=zmid, zmin=-zmax, zmax=zmax,
                               text=np.round(df.values.astype(float), 2), texttemplate="%{text:" + fmt + "}", colorbar=dict(thickness=10)))
    fig.update_layout(title=title, **{**LAYOUT, "height": height})
    return fig


def gauge_row(scores: dict, directions: dict = None):
    cols = st.columns(len(scores))
    for c, (k, v) in zip(cols, scores.items()):
        d = (directions or {}).get(k)
        c.metric(k, "n/a" if v is None or not np.isfinite(v) else f"{v:+.0f}", None if d is None or not np.isfinite(d) else f"{d:+.0f} (20D)")


def session_list(key: str) -> list:
    if key not in st.session_state:
        st.session_state[key] = []
    return st.session_state[key]


def session_dict(key: str, default: dict) -> dict:
    if key not in st.session_state:
        st.session_state[key] = dict(default)
    return st.session_state[key]


def json_io(key: str, label: str):
    """Download / upload a session_state object as JSON (manual desk inputs survive restarts)."""
    c1, c2 = st.columns(2)
    payload = json.dumps(st.session_state.get(key, {}), default=str, indent=1)
    c1.download_button(f"Download {label} (JSON)", payload, file_name=f"{key}.json", mime="application/json", key=f"dl_{key}")
    up = c2.file_uploader(f"Upload {label} (JSON)", type=["json"], key=f"ul_{key}")
    if up is not None:
        try:
            st.session_state[key] = json.load(up)
            st.success(f"{label} loaded ({len(st.session_state[key])} items)")
        except Exception as e:
            st.error(f"could not read JSON: {e}")


def dfmt(df: pd.DataFrame, nd: int = 2) -> pd.DataFrame:
    out = df.copy()
    for c in out.columns:
        if pd.api.types.is_float_dtype(out[c]):
            out[c] = out[c].round(nd)
    return out


def last(s: pd.Series, default=np.nan):
    s = s.dropna() if isinstance(s, pd.Series) else pd.Series(dtype=float)
    return float(s.iloc[-1]) if len(s) else default


def window_dates(label: str):
    """Hard-coded validation / stress windows."""
    return {
        "COVID Mar-2020": ("2020-02-19", "2020-03-23"), "Fed hiking 2022": ("2022-01-03", "2022-10-31"),
        "UK mini-budget Sep-2022": ("2022-09-22", "2022-09-28"), "Aug-2024 carry unwind": ("2024-07-10", "2024-08-05"),
        "Apr-2025 tariffs": ("2025-04-02", "2025-04-11"), "Bund tantrum 2015": ("2015-04-20", "2015-06-10"),
        "BoJ Jul-2024 hike": ("2024-07-25", "2024-08-05"),
    }.get(label)
