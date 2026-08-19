"""Classifies the volatility regime from level, percentile and term structure."""

import pandas as pd

from classification import Classification
from market_snapshot import MarketSnapshot


class VolatilityRegimeClassifier:
    """VIX percentile leads, the absolute level is a cross-check.

    VIX 20 in a calm decade and VIX 20 in a violent one mean different things,
    so the percentile drives the label. VIX/VIX3M above 1 (backwardation) is
    treated as a separate near-term stress flag.
    """

    LEVEL_BANDS = [
        (0, 15, "Very calm"),
        (15, 20, "Normal"),
        (20, 25, "Elevated"),
        (25, 30, "Stress"),
        (30, 999, "Crisis territory"),
    ]
    PERCENTILE_BANDS = [
        (0, 20, "Very calm"),
        (20, 50, "Normal"),
        (50, 80, "Elevated"),
        (80, 95, "Stress"),
        (95, 101, "Crisis territory"),
    ]

    def classify(self, snapshot: MarketSnapshot) -> Classification:
        if not snapshot.has("vix"):
            return Classification("Volatility", "unavailable",
                                  "VIX did not load", available=False)

        level = snapshot.level("vix")
        percentile = snapshot.percentile("vix", "1y")
        state = self._band(percentile, self.PERCENTILE_BANDS) if not pd.isna(percentile) \
            else self._band(level, self.LEVEL_BANDS)

        evidence = [
            f"VIX {level:.2f} ({self._band(level, self.LEVEL_BANDS).lower()} by absolute level)",
            f"1y percentile {percentile:.0f}" if not pd.isna(percentile) else "1y percentile n/a",
        ]
        if snapshot.has("vxn"):
            evidence.append(f"VXN {snapshot.level('vxn'):.2f}")
        return Classification("Volatility", state, self._term_structure(snapshot, evidence), evidence)

    def _band(self, value: float, bands) -> str:
        if pd.isna(value):
            return "unavailable"
        for low, high, label in bands:
            if low <= value < high:
                return label
        return bands[-1][2]

    def _term_structure(self, snapshot: MarketSnapshot, evidence: list) -> str:
        if not snapshot.has("vix_vix3m"):
            return "term structure unavailable"
        ratio = snapshot.level("vix_vix3m")
        evidence.append(f"VIX/VIX3M {ratio:.3f}")
        if ratio > 1.10:
            return f"backwardation at {ratio:.2f} - strong near-term stress signal"
        if ratio > 1.00:
            return f"backwardation at {ratio:.2f} - near-term risk being bid"
        if ratio < 0.85:
            return f"steep contango at {ratio:.2f} - complacent front end"
        return f"normal contango at {ratio:.2f}"
