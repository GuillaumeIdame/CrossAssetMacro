"""Where does today's level sit within its own distribution?"""

import pandas as pd


class PercentileCalculator:
    """Rolling percentile rank, in percent (0 = lowest in window, 100 = highest).

    VIX at 18 says little; VIX at the 35th percentile of the last year says a lot.
    """

    def percentile(self, series: pd.Series, window: int) -> pd.Series:
        if series.empty:
            return series
        min_periods = max(60, window // 4)
        rank = series.rolling(window, min_periods=min_periods).rank(pct=True)
        return rank * 100.0
