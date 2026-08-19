"""Moving-average structure: the directional state behind the snapshot."""

from typing import Dict, List

import pandas as pd


class TrendAnalyzer:
    """Scores the moving-average stack from -100 (fully bearish) to +100.

    With the default 20/50/200 windows there are five conditions: price above
    each average, and each average above the next one. All five true means a
    clean uptrend; none true means a clean downtrend.
    """

    def __init__(self, windows: List[int] = None):
        self.windows = sorted(windows or [20, 50, 200])

    def moving_averages(self, series: pd.Series) -> Dict[int, pd.Series]:
        return {w: series.rolling(w, min_periods=w).mean() for w in self.windows}

    def flags(self, series: pd.Series) -> pd.DataFrame:
        """Boolean-valued (as float, NaN where undefined) trend conditions."""
        averages = self.moving_averages(series)
        conditions = {}
        for window in self.windows:
            average = averages[window]
            conditions[f"price>{window}dma"] = (series > average).where(average.notna())
        for shorter, longer in zip(self.windows, self.windows[1:]):
            conditions[f"{shorter}dma>{longer}dma"] = (
                (averages[shorter] > averages[longer])
                .where(averages[shorter].notna() & averages[longer].notna())
            )
        return pd.DataFrame(conditions).astype(float)

    def score(self, series: pd.Series) -> pd.Series:
        if series.empty:
            return series
        flags = self.flags(series)
        if flags.empty:
            return pd.Series(index=series.index, dtype=float)
        share = flags.mean(axis=1).where(flags.notna().all(axis=1))
        return share * 200.0 - 100.0
