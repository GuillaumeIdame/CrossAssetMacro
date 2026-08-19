"""Builds relative-value ratios such as IWM/SPY or Copper/Gold."""

import numpy as np
import pandas as pd


class RatioBuilder:
    """Divides one series by another, guarding against zero denominators."""

    def build(self, numerator: pd.Series, denominator: pd.Series) -> pd.Series:
        if numerator.empty or denominator.empty:
            return pd.Series(dtype=float)
        safe_denominator = denominator.where(denominator != 0)
        ratio = numerator / safe_denominator
        return ratio.replace([np.inf, -np.inf], np.nan)
