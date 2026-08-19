"""Converts every configured series into a -100..+100 signal score."""

import numpy as np
import pandas as pd

from confirmation_scorer import ConfirmationScorer
from engine_config import EngineConfig
from momentum_scorer import MomentumScorer
from trend_analyzer import TrendAnalyzer
from zscore_calculator import ZScoreCalculator


class SignalScoreBuilder:
    """Blends trend, momentum, z-score and cross-asset confirmation.

    Default weights follow the scoring philosophy in the spec: trend 30%,
    momentum 30%, z-score 20%, confirmation 20%. Components that are not yet
    defined (short history, no confirmers configured) are dropped and the
    remaining weights renormalised, so a signal is never quietly pulled towards
    zero by a missing input.

    Everything is computed over the full history, so today's score is simply
    the last row -- and the same table drives the score charts and the regime
    timeline.
    """

    def __init__(self, config: EngineConfig):
        self.config = config
        scoring = config.scoring()
        self.component_weights = {k: float(v) for k, v in scoring["components"].items()}
        self.state_threshold = float(scoring["state_threshold"])
        self.zscore_squash = float(scoring["zscore_squash"])
        self.confirmation_horizon = int(scoring["confirmation_horizon"])
        self.trend_analyzer = TrendAnalyzer(scoring["moving_averages"])
        self.momentum_scorer = MomentumScorer(
            horizon_weights={int(h): float(w) for h, w in scoring["momentum_horizons"].items()},
            squash=float(scoring["momentum_squash"]),
            volatility_window=int(scoring["zscore_window"]),
        )
        self.zscore_calculator = ZScoreCalculator(int(scoring["zscore_window"]))
        self.confirmation_scorer = ConfirmationScorer()
        self.components = {}
        self.scores = pd.DataFrame()
        self.states = pd.DataFrame()
        self.skipped = {}

    # --- build ---------------------------------------------------------------

    def build(self, frame: pd.DataFrame) -> pd.DataFrame:
        """Return the score table (dates x signals) and populate the components."""
        self.skipped = {}
        usable = {}
        for key, definition in self.config.signals.items():
            if key not in frame.columns or frame[key].notna().sum() < 260:
                self.skipped[key] = "series missing or shorter than one year"
                continue
            usable[key] = definition

        index = frame.index
        levels = {key: frame[key] for key in usable}
        peer_momentum = {
            key: self.momentum_scorer.horizon_score(
                levels[key], definition.mode, self.confirmation_horizon
            )
            for key, definition in usable.items()
        }

        trend = {}
        momentum = {}
        zscore = {}
        confirmation = {}
        for key, definition in usable.items():
            series = levels[key]
            trend[key] = self.trend_analyzer.score(series)
            momentum[key] = self.momentum_scorer.score(series, definition.mode)
            zscore[key] = np.tanh(
                self.zscore_calculator.zscore(series) / self.zscore_squash
            ) * 100.0
            confirmation[key] = self.confirmation_scorer.score(
                definition.confirmers, peer_momentum, index
            )

        self.components = {
            "trend": pd.DataFrame(trend, index=index),
            "momentum": pd.DataFrame(momentum, index=index),
            "zscore": pd.DataFrame(zscore, index=index),
            "confirmation": pd.DataFrame(confirmation, index=index),
        }
        self.scores = self._combine(index, list(usable.keys()))
        self.states = self._states(self.scores)
        return self.scores

    def _combine(self, index: pd.Index, keys: list) -> pd.DataFrame:
        weighted_total = pd.DataFrame(0.0, index=index, columns=keys)
        weight_total = pd.DataFrame(0.0, index=index, columns=keys)
        for name, weight in self.component_weights.items():
            component = self.components[name].reindex(columns=keys)
            weighted_total = weighted_total.add(component.fillna(0.0) * weight, fill_value=0.0)
            weight_total = weight_total.add(component.notna() * weight, fill_value=0.0)
        combined = weighted_total / weight_total.where(weight_total > 0)
        return combined.clip(-100.0, 100.0)

    def _states(self, scores: pd.DataFrame) -> pd.DataFrame:
        states = pd.DataFrame(0.0, index=scores.index, columns=scores.columns)
        states = states.mask(scores > self.state_threshold, 1.0)
        states = states.mask(scores < -self.state_threshold, -1.0)
        return states.where(scores.notna())
