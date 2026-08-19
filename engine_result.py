"""Everything one run of the engine produces."""

from dataclasses import dataclass, field
from typing import Dict, List

import pandas as pd

from classification import Classification
from divergence import Divergence
from factor_score import FactorScore
from market_snapshot import MarketSnapshot
from regime_state import RegimeState


@dataclass
class EngineResult:
    """The three outputs the spec asks for - state, evidence, intuition - plus history."""

    as_of: pd.Timestamp
    series: pd.DataFrame
    snapshot: MarketSnapshot
    signal_scores: pd.DataFrame
    signal_states: pd.DataFrame
    signal_components: Dict[str, pd.DataFrame]
    factor_history: pd.DataFrame
    confidence_history: pd.DataFrame
    factors: Dict[str, FactorScore]
    regime: RegimeState
    regime_history: pd.DataFrame
    transitions: pd.DataFrame
    days_in_regime: int
    classifications: Dict[str, Classification]
    divergences: List[Divergence]
    intuition: str
    leadership: pd.DataFrame
    data_status: pd.DataFrame
    notes: List[str] = field(default_factory=list)

    def summary_table(self) -> pd.DataFrame:
        return pd.DataFrame([
            {
                "factor": score.label,
                "score": score.value,
                "band": score.band,
                "20d change": score.change_20d,
                "confidence": score.confidence_label(),
            }
            for score in self.factors.values()
        ])
