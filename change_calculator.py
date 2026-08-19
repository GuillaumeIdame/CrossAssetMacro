"""Measures how much a series has moved over a horizon."""

import numpy as np
import pandas as pd


class ChangeCalculator:
    """Horizon changes, in the unit that suits the series.

    A "price" series (index level, ETF, ratio) moves in log/percent terms; a
    "level" series (yield, spread, VIX) moves in absolute points. Everything
    downstream asks this class rather than deciding for itself.
    """

    def raw_change(self, series: pd.Series, horizon: int, mode: str) -> pd.Series:
        """Change used for scoring: log change for prices, difference for levels."""
        if series.empty:
            return series
        if mode == "price":
            positive = series.where(series > 0)
            return np.log(positive) - np.log(positive.shift(horizon))
        return series - series.shift(horizon)

    def display_change(self, series: pd.Series, horizon: int, mode: str) -> pd.Series:
        """Change used for display: percent for prices, absolute points for levels."""
        if series.empty:
            return series
        if mode == "price":
            previous = series.shift(horizon).where(lambda s: s != 0)
            return (series / previous - 1.0) * 100.0
        return series - series.shift(horizon)

    def year_to_date(self, series: pd.Series, mode: str) -> pd.Series:
        """Change since the first observation of each calendar year."""
        if series.empty:
            return series
        year_start = series.groupby(series.index.year).transform("first")
        if mode == "price":
            base = year_start.where(year_start != 0)
            return (series / base - 1.0) * 100.0
        return series - year_start

    def normalised_change(
        self, series: pd.Series, horizon: int, mode: str, window: int = 252
    ) -> pd.Series:
        """Horizon change divided by its own rolling standard deviation.

        This is what makes a 10bp move in 2s10s and a 1% move in the S&P
        comparable: both become "how many typical moves is this".
        """
        change = self.raw_change(series, horizon, mode)
        volatility = change.rolling(window, min_periods=max(20, window // 5)).std()
        volatility = volatility.where(volatility > 0)
        return (change / volatility).replace([np.inf, -np.inf], np.nan)
