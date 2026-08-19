"""Combines signal scores into the six macro factor scores."""

import numpy as np
import pandas as pd

from engine_config import EngineConfig
from factor_score import FactorScore


class FactorScoreBuilder:
    """Weighted, sign-adjusted blend of signal scores, computed over full history.

    Weights are renormalised over whatever signals actually exist on each date,
    so a factor whose inputs have different history lengths (HY OAS starts later
    than HYG/LQD, for instance) stays on the same -100..+100 scale throughout
    rather than jumping when a series switches on.
    """

    def __init__(self, config: EngineConfig):
        self.config = config
        self.scores = pd.DataFrame()
        self.confidence = pd.DataFrame()
        self.signal_scores = pd.DataFrame()
        self.signal_states = pd.DataFrame()

    # --- build ---------------------------------------------------------------

    def build(self, signal_scores: pd.DataFrame, signal_states: pd.DataFrame) -> pd.DataFrame:
        self.signal_scores = signal_scores
        self.signal_states = signal_states
        score_columns = {}
        confidence_columns = {}
        for key, definition in self.config.factors.items():
            value, agreement = self._build_one(definition, signal_scores, signal_states)
            score_columns[key] = value
            confidence_columns[key] = agreement
        self.scores = pd.DataFrame(score_columns, index=signal_scores.index)
        self.confidence = pd.DataFrame(confidence_columns, index=signal_scores.index)
        return self.scores

    def _build_one(self, definition, signal_scores, signal_states):
        keys = [k for k in definition.signal_keys() if k in signal_scores.columns]
        index = signal_scores.index
        if not keys:
            empty = pd.Series(index=index, dtype=float)
            return empty, empty

        weights = pd.Series({k: definition.weight_of(k) for k in keys}, dtype=float)
        signs = pd.Series({k: definition.sign_of(k) for k in keys}, dtype=float)

        signed = signal_scores[keys].mul(signs, axis=1)
        weighted = signed.mul(weights, axis=1).sum(axis=1, min_count=1)
        available = signed.notna().mul(weights, axis=1).sum(axis=1)
        value = (weighted / available.where(available > 0)).clip(-100.0, 100.0)

        signed_state = signal_states[keys].mul(signs, axis=1)
        factor_sign = np.sign(value)
        agrees = np.sign(signed_state).eq(factor_sign, axis=0)
        agrees = agrees.mul((factor_sign != 0).astype(float), axis=0)
        agreeing_weight = agrees.mul(weights, axis=1).sum(axis=1)
        agreement = agreeing_weight / available.where(available > 0)
        return value, agreement

    # --- access --------------------------------------------------------------

    def latest(self, factor_key: str) -> FactorScore:
        definition = self.config.factors[factor_key]
        series = self.scores[factor_key].dropna()
        if series.empty:
            raise RuntimeError(f"factor '{factor_key}' could not be computed")
        value = float(series.iloc[-1])
        change_20d = float(value - series.iloc[-21]) if len(series) > 21 else float("nan")
        confidence = float(self.confidence[factor_key].dropna().iloc[-1])
        return FactorScore(
            key=factor_key,
            label=definition.label,
            value=value,
            band=definition.band_for(value),
            confidence=confidence,
            change_20d=change_20d,
            contributions=self.contributions(factor_key),
        )

    def latest_all(self) -> dict:
        return {key: self.latest(key) for key in self.config.factor_keys()}

    def contributions(self, factor_key: str) -> pd.DataFrame:
        """Per-signal breakdown of the factor's latest value."""
        definition = self.config.factors[factor_key]
        keys = [k for k in definition.signal_keys() if k in self.signal_scores.columns]
        latest_scores = self.signal_scores.iloc[-1]
        latest_states = self.signal_states.iloc[-1]
        factor_value = float(self.scores[factor_key].iloc[-1])

        available_weight = sum(
            definition.weight_of(k) for k in keys if not pd.isna(latest_scores[k])
        )
        rows = []
        for key in keys:
            score = float(latest_scores[key])
            sign = definition.sign_of(key)
            weight = definition.weight_of(key)
            signed = score * sign
            share = weight / available_weight if available_weight else float("nan")
            rows.append({
                "signal": key,
                "name": self.config.series_name(key),
                "weight": weight,
                "sign": sign,
                "score": score,
                "signed_score": signed,
                "state": float(latest_states[key]) if not pd.isna(latest_states[key]) else float("nan"),
                "contribution": signed * share,
                "agrees": bool(np.sign(float(latest_states[key]) * sign) == np.sign(factor_value))
                if not pd.isna(latest_states[key]) else False,
            })
        frame = pd.DataFrame(rows)
        missing = [k for k in definition.signal_keys() if k not in keys]
        frame.attrs["missing_signals"] = missing
        return frame.sort_values("contribution", key=abs, ascending=False).reset_index(drop=True)
