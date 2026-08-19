"""Builds yield spreads such as 2s10s, scaled into basis points."""

import pandas as pd


class SpreadBuilder:
    """Subtracts one yield series from another and rescales the result."""

    def build(self, long_leg: pd.Series, short_leg: pd.Series, scale: float = 100.0) -> pd.Series:
        if long_leg.empty or short_leg.empty:
            return pd.Series(dtype=float)
        return (long_leg - short_leg) * scale
