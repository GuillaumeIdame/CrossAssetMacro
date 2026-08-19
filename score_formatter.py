"""Consistent formatting for scores, levels and directional arrows."""

import pandas as pd


class ScoreFormatter:
    """One place that decides how numbers are shown.

    Levels in this engine span Bitcoin at five figures and Copper/Gold at
    0.0015, so a fixed decimal count is useless; significant digits are used
    instead.
    """

    POSITIVE = "#1a7f5a"
    NEGATIVE = "#b3402f"
    NEUTRAL = "#6d6d6d"
    SEVERITY_COLOURS = {
        "alert": "#b3402f",
        "warning": "#c07d1a",
        "confirmation": "#1a7f5a",
        "info": "#4a6fa5",
    }

    def score(self, value: float) -> str:
        if pd.isna(value):
            return "n/a"
        return f"{value:+.0f}"

    def level(self, value: float) -> str:
        if pd.isna(value):
            return "n/a"
        magnitude = abs(value)
        if magnitude >= 1000:
            return f"{value:,.0f}"
        if magnitude >= 10:
            return f"{value:,.2f}"
        if magnitude >= 0.1:
            return f"{value:.3f}"
        return f"{value:.5g}"

    def change(self, value: float, unit: str) -> str:
        if pd.isna(value):
            return "n/a"
        if unit == "%":
            return f"{value:+.2f}%"
        if abs(value) >= 10:
            return f"{value:+.0f}bp"
        return f"{value:+.2f}"

    def percentile(self, value: float) -> str:
        if pd.isna(value):
            return "n/a"
        return f"p{value:.0f}"

    def arrow(self, value: float, threshold: float = 0.0) -> str:
        if pd.isna(value):
            return "-"
        if value > threshold:
            return "^"
        if value < -threshold:
            return "v"
        return "="

    def colour(self, value: float) -> str:
        if pd.isna(value):
            return self.NEUTRAL
        if value > 20:
            return self.POSITIVE
        if value < -20:
            return self.NEGATIVE
        return self.NEUTRAL

    def state_label(self, state: float) -> str:
        if pd.isna(state):
            return "n/a"
        return {1.0: "+1", -1.0: "-1"}.get(float(state), "0")
