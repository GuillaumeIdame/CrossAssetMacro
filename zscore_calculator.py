"""Rolling standardisation: is today's level unusual for this series?"""

import numpy as np
import pandas as pd


class ZScoreCalculator:
    """Rolling z-score of a level against its own recent history."""

    def __init__(self, window: int = 252):
        self.window = window
        self.min_periods = max(60, window // 4)

    def zscore(self, series: pd.Series) -> pd.Series:
        if series.empty:
            return series
        mean = series.rolling(self.window, min_periods=self.min_periods).mean()
        deviation = series.rolling(self.window, min_periods=self.min_periods).std()
        deviation = deviation.where(deviation > 0)
        return ((series - mean) / deviation).replace([np.inf, -np.inf], np.nan)
