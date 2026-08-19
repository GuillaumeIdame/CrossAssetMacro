"""Plotly figures for the dashboard."""

from typing import Dict, List

import pandas as pd
import plotly.graph_objects as go

from factor_score import FactorScore
from score_formatter import ScoreFormatter


class ChartBuilder:
    """Every figure the app draws, built from the same tables the engine produced."""

    CELL_COLOURS = {
        "Goldilocks": "#2e8b57",
        "Expansion": "#4f9d69",
        "Reflation": "#d97706",
        "Disinflation": "#4a86c5",
        "Neutral": "#9ca3af",
        "Late-cycle inflation": "#c2740a",
        "Slowdown": "#c9a227",
        "Deflation": "#3b6fa0",
        "Stagflation": "#b3402f",
    }

    def __init__(self):
        self.formatter = ScoreFormatter()

    # --- factor views --------------------------------------------------------

    def factor_bars(self, factors: Dict[str, FactorScore]) -> go.Figure:
        scores = list(factors.values())[::-1]
        figure = go.Figure(go.Bar(
            x=[s.value for s in scores],
            y=[s.label for s in scores],
            orientation="h",
            marker_color=[self.formatter.colour(s.value) for s in scores],
            text=[f"{s.value:+.0f}  {s.band}" for s in scores],
            textposition="outside",
            hovertemplate="%{y}: %{x:+.1f}<extra></extra>",
        ))
        figure.update_layout(
            xaxis=dict(range=[-105, 105], zeroline=True, zerolinewidth=1, title="score"),
            margin=dict(l=10, r=10, t=10, b=30),
            height=300,
            showlegend=False,
        )
        for boundary in (-60, -30, 30, 60):
            figure.add_vline(x=boundary, line_width=1, line_dash="dot", line_color="#d0d0d0")
        return figure

    def factor_history(self, history: pd.DataFrame, keys: List[str], labels: Dict[str, str],
                       months: int = 24) -> go.Figure:
        window = history.loc[history.index >= history.index[-1] - pd.DateOffset(months=months)]
        figure = go.Figure()
        for key in keys:
            figure.add_trace(go.Scatter(
                x=window.index, y=window[key], name=labels.get(key, key), mode="lines"
            ))
        figure.add_hline(y=0, line_width=1, line_color="#b0b0b0")
        for boundary in (-60, -30, 30, 60):
            figure.add_hline(y=boundary, line_width=1, line_dash="dot", line_color="#e0e0e0")
        figure.update_layout(
            yaxis=dict(range=[-105, 105], title="score"),
            margin=dict(l=10, r=10, t=10, b=30),
            height=380,
            legend=dict(orientation="h", y=-0.15),
        )
        return figure

    def quadrant(self, history: pd.DataFrame, trail_days: int = 60,
                 neutral_band: float = 20.0) -> go.Figure:
        trail = history.tail(trail_days)
        figure = go.Figure()
        figure.add_trace(go.Scatter(
            x=trail["inflation"], y=trail["growth"], mode="lines+markers",
            line=dict(color="#9ca3af", width=1),
            marker=dict(size=4, color="#9ca3af"),
            name=f"last {trail_days} sessions",
            hovertemplate="inflation %{x:+.0f}, growth %{y:+.0f}<extra></extra>",
        ))
        figure.add_trace(go.Scatter(
            x=[trail["inflation"].iloc[-1]], y=[trail["growth"].iloc[-1]],
            mode="markers", marker=dict(size=16, color="#111111", symbol="circle"),
            name="today",
            hovertemplate="today: inflation %{x:+.0f}, growth %{y:+.0f}<extra></extra>",
        ))
        figure.add_hline(y=0, line_width=1, line_color="#b0b0b0")
        figure.add_vline(x=0, line_width=1, line_color="#b0b0b0")
        for boundary in (-neutral_band, neutral_band):
            figure.add_hline(y=boundary, line_width=1, line_dash="dot", line_color="#e0e0e0")
            figure.add_vline(x=boundary, line_width=1, line_dash="dot", line_color="#e0e0e0")

        labels = [
            (60, 60, "Reflation"), (-60, 60, "Goldilocks"),
            (60, -60, "Stagflation"), (-60, -60, "Deflation"),
        ]
        for x, y, text in labels:
            figure.add_annotation(x=x, y=y, text=text, showarrow=False,
                                  font=dict(size=11, color="#9ca3af"))
        figure.update_layout(
            xaxis=dict(range=[-100, 100], title="Inflation score"),
            yaxis=dict(range=[-100, 100], title="Growth score"),
            margin=dict(l=10, r=10, t=10, b=30),
            height=420,
            showlegend=False,
        )
        return figure

    def contribution_bars(self, contributions: pd.DataFrame) -> go.Figure:
        table = contributions.iloc[::-1]
        figure = go.Figure(go.Bar(
            x=table["contribution"], y=table["name"], orientation="h",
            marker_color=[self.formatter.colour(v * 4) for v in table["contribution"]],
            hovertemplate="%{y}: %{x:+.1f} of the factor score<extra></extra>",
        ))
        figure.update_layout(
            xaxis=dict(title="contribution to factor score", zeroline=True),
            margin=dict(l=10, r=10, t=10, b=30),
            height=max(260, 26 * len(table)),
            showlegend=False,
        )
        return figure

    # --- regime views --------------------------------------------------------

    def regime_ribbon(self, regime_history: pd.DataFrame, months: int = 36) -> go.Figure:
        window = regime_history.loc[
            regime_history.index >= regime_history.index[-1] - pd.DateOffset(months=months)
        ]
        figure = go.Figure()
        block_start = window.index[0]
        current = window["cell"].iloc[0]
        for timestamp, cell in zip(window.index, window["cell"]):
            if cell != current:
                self._add_block(figure, block_start, timestamp, current)
                block_start, current = timestamp, cell
        self._add_block(figure, block_start, window.index[-1], current)
        figure.update_layout(
            yaxis=dict(visible=False, range=[0, 1]),
            margin=dict(l=10, r=10, t=10, b=30),
            height=140,
            showlegend=True,
            legend=dict(orientation="h", y=-0.4),
        )
        return figure

    def _add_block(self, figure: go.Figure, start, end, cell: str) -> None:
        existing = {trace.name for trace in figure.data}
        figure.add_trace(go.Scatter(
            x=[start, end, end, start, start], y=[0, 0, 1, 1, 0],
            fill="toself", mode="lines", line=dict(width=0),
            fillcolor=self.CELL_COLOURS.get(cell, "#9ca3af"),
            name=cell, legendgroup=cell, showlegend=cell not in existing,
            hovertemplate=f"{cell}<extra></extra>",
        ))

    def occupancy_bars(self, occupancy: pd.DataFrame) -> go.Figure:
        figure = go.Figure(go.Bar(
            x=occupancy["share"], y=occupancy["cell"], orientation="h",
            marker_color=[self.CELL_COLOURS.get(c, "#9ca3af") for c in occupancy["cell"]],
            text=[f"{s:.0f}%" for s in occupancy["share"]], textposition="outside",
        ))
        figure.update_layout(
            xaxis=dict(title="share of sessions (%)"),
            margin=dict(l=10, r=10, t=10, b=30),
            height=max(220, 30 * len(occupancy)),
            showlegend=False,
        )
        return figure

    # --- series views --------------------------------------------------------

    def panel_history(self, zscores: pd.DataFrame, keys: List[str], labels: Dict[str, str],
                      months: int = 24) -> go.Figure:
        """Time series for one market panel, plotted as z-scores.

        Panel series live on different units (a yield in percent, a spread in
        basis points, a ratio) so a shared z-score axis is what makes them
        comparable on one chart, rather than raw levels that would swamp each
        other's scale.
        """
        available = [k for k in keys if k in zscores.columns]
        if not available:
            return go.Figure()
        window = zscores.loc[
            zscores.index >= zscores.index[-1] - pd.DateOffset(months=months), available
        ]
        figure = go.Figure()
        for key in available:
            figure.add_trace(go.Scatter(
                x=window.index, y=window[key], name=labels.get(key, key), mode="lines",
                hovertemplate="%{fullData.name}: %{y:+.2f}<extra></extra>",
            ))
        figure.add_hline(y=0, line_width=1, line_color="#b0b0b0")
        figure.update_layout(
            yaxis=dict(title="z-score"),
            margin=dict(l=10, r=10, t=10, b=30),
            height=300,
            legend=dict(orientation="h", y=-0.25),
        )
        return figure

    def signal_heatmap(self, signal_scores: pd.DataFrame, keys: List[str],
                       labels: Dict[str, str], months: int = 12) -> go.Figure:
        window = signal_scores.loc[
            signal_scores.index >= signal_scores.index[-1] - pd.DateOffset(months=months), keys
        ]
        figure = go.Figure(go.Heatmap(
            z=window.T.to_numpy(), x=window.index, y=[labels.get(k, k) for k in keys],
            zmin=-100, zmax=100, colorscale="RdYlGn", colorbar=dict(title="score"),
            hovertemplate="%{y}<br>%{x|%Y-%m-%d}: %{z:+.0f}<extra></extra>",
        ))
        figure.update_layout(
            margin=dict(l=10, r=10, t=10, b=30), height=max(300, 18 * len(keys))
        )
        return figure
