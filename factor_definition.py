"""One of the six macro factors and how it is assembled from signals."""

from dataclasses import dataclass
from typing import Dict, List, Tuple


@dataclass(frozen=True)
class FactorDefinition:
    """A weighted combination of signal scores, plus its band labels.

    `weights` maps a signal key to (weight, sign). The sign flips a signal so
    that "the series is going up" contributes positively to the factor -- e.g.
    the dollar rising is negative for liquidity, so DXY carries sign -1 there.
    """

    key: str
    label: str
    low_label: str
    high_label: str
    weights: Dict[str, Tuple[float, int]]
    bands: List[Tuple[float, float, str]]

    def signal_keys(self) -> List[str]:
        return list(self.weights.keys())

    def weight_of(self, signal_key: str) -> float:
        return self.weights[signal_key][0]

    def sign_of(self, signal_key: str) -> int:
        return self.weights[signal_key][1]

    def band_for(self, value: float) -> str:
        for low, high, label in self.bands:
            if low <= value < high:
                return label
        return self.bands[-1][2]
