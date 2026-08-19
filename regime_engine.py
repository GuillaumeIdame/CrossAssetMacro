"""Runs the whole pipeline: prices -> signals -> factors -> regime -> intuition."""

import pandas as pd

from copper_gold_regime_classifier import CopperGoldRegimeClassifier
from curve_regime_classifier import CurveRegimeClassifier
from derived_series_builder import DerivedSeriesBuilder
from divergence_detector import DivergenceDetector
from engine_config import EngineConfig
from engine_result import EngineResult
from expected_leadership_builder import ExpectedLeadershipBuilder
from factor_score_builder import FactorScoreBuilder
from macro_intuition_writer import MacroIntuitionWriter
from market_data_repository import MarketDataRepository
from market_snapshot import MarketSnapshot
from oil_regime_classifier import OilRegimeClassifier
from regime_classifier import RegimeClassifier
from signal_score_builder import SignalScoreBuilder
from usd_regime_classifier import UsdRegimeClassifier
from volatility_regime_classifier import VolatilityRegimeClassifier


class RegimeEngine:
    """Owns the run order and hands back one EngineResult.

    All history is recomputed from prices on every run, so today's reading and
    the score charts are always produced by the same code path - the current
    regime is simply the last row of the regime timeline.
    """

    def __init__(self, config: EngineConfig = None, use_cache: bool = True):
        self.config = config or EngineConfig()
        self.repository = MarketDataRepository(self.config, use_cache=use_cache)
        self.derived_builder = DerivedSeriesBuilder(self.config)
        self.signal_builder = SignalScoreBuilder(self.config)
        self.factor_builder = FactorScoreBuilder(self.config)
        self.regime_classifier = RegimeClassifier(self.config)
        self.divergence_detector = DivergenceDetector()
        self.intuition_writer = MacroIntuitionWriter()
        self.leadership_builder = ExpectedLeadershipBuilder()
        self.classifiers = {
            "curve": CurveRegimeClassifier(),
            "usd": UsdRegimeClassifier(),
            "volatility": VolatilityRegimeClassifier(),
            "copper_gold": CopperGoldRegimeClassifier(),
            "oil": OilRegimeClassifier(),
        }

    def run(self) -> EngineResult:
        prices = self.repository.load()
        series = self.derived_builder.build(prices)
        observed = self.derived_builder.build_observed(self.repository.observed_frame())

        self.signal_builder.build(series)
        self.factor_builder.build(self.signal_builder.scores, self.signal_builder.states)

        as_of = self._resolve_as_of()
        series = series.loc[:as_of]
        signal_scores = self.signal_builder.scores.loc[:as_of]
        signal_states = self.signal_builder.states.loc[:as_of]
        components = {k: v.loc[:as_of] for k, v in self.signal_builder.components.items()}
        factor_history = self.factor_builder.scores.loc[:as_of]
        confidence_history = self.factor_builder.confidence.loc[:as_of]
        self.factor_builder.scores = factor_history
        self.factor_builder.confidence = confidence_history
        self.factor_builder.signal_scores = signal_scores
        self.factor_builder.signal_states = signal_states

        snapshot = MarketSnapshot(self.config, series, observed.loc[:as_of])
        factors = self.factor_builder.latest_all()
        regime_history = self.regime_classifier.classify_history(factor_history)
        regime = self.regime_classifier.classify_latest(factor_history, regime_history)
        classifications = {
            name: classifier.classify(snapshot) for name, classifier in self.classifiers.items()
        }
        divergences = self.divergence_detector.detect(
            snapshot, {k: v.value for k, v in factors.items()}
        )
        intuition = self.intuition_writer.write(regime, factors, divergences)
        leadership = self.leadership_builder.build(regime, factors)

        return EngineResult(
            as_of=as_of,
            series=series,
            snapshot=snapshot,
            signal_scores=signal_scores,
            signal_states=signal_states,
            signal_components=components,
            factor_history=factor_history,
            confidence_history=confidence_history,
            factors=factors,
            regime=regime,
            regime_history=regime_history,
            transitions=self.regime_classifier.transitions(regime_history),
            days_in_regime=self.regime_classifier.time_in_regime(regime_history),
            classifications=classifications,
            divergences=divergences,
            intuition=intuition,
            leadership=leadership,
            data_status=self.repository.status(),
            notes=self._notes(),
        )

    def _resolve_as_of(self) -> pd.Timestamp:
        """Latest date on which every factor could be computed.

        Series publish on different lags, so the last row of the price frame is
        not necessarily a row on which the whole engine is defined. Reporting
        against a partially-defined date would silently drop factor inputs.
        """
        complete = self.factor_builder.scores.dropna(how="any")
        if complete.empty:
            raise RuntimeError("no date has a complete set of factor scores")
        return complete.index[-1]

    def _notes(self) -> list:
        notes = []
        for key, reason in sorted(self.repository.rejected.items()):
            notes.append(f"series '{key}' unavailable: {reason}")
        for key, reason in sorted(self.derived_builder.skipped.items()):
            notes.append(f"derived series '{key}' skipped: {reason}")
        for key, reason in sorted(self.signal_builder.skipped.items()):
            notes.append(f"signal '{key}' not scored: {reason}")
        return notes
