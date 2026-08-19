"""Multi-horizon momentum, volatility-normalised and squashed to -100..+100."""

from typing import Dict

import numpy as np
import pandas as pd

from change_calculator import ChangeCalculator


class MomentumScorer:
    """Blends 5d / 20d / 60d / 120d moves into one directional score.

    Each horizon is divided by its own rolling volatility first, so an unusual
    move counts more than a large one, and a tanh squash keeps a single violent
    day from saturating the whole factor.
    """

    def __init__(self, horizon_weights: Dict[int, float] = None, squash: float = 1.5,
                 volatility_window: int = 252):
        self.horizon_weights = horizon_weights or {5: 0.40, 20: 0.30, 60: 0.20, 120: 0.10}
        self.squash = squash
        self.volatility_window = volatility_window
        self.change_calculator = ChangeCalculator()

    def horizon_score(self, series: pd.Series, mode: str, horizon: int) -> pd.Series:
        normalised = self.change_calculator.normalised_change(
            series, horizon, mode, self.volatility_window
        )
        return np.tanh(normalised / self.squash) * 100.0

    def score(self, series: pd.Series, mode: str) -> pd.Series:
        if series.empty:
            return series
        scores = pd.DataFrame({
            horizon: self.horizon_score(series, mode, horizon)
            for horizon in self.horizon_weights
        })
        weights = pd.Series(self.horizon_weights, dtype=float)
        weighted = scores.mul(weights, axis=1).sum(axis=1, min_count=1)
        available = scores.notna().mul(weights, axis=1).sum(axis=1)
        return weighted / available.where(available > 0)
