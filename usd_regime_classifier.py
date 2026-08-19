"""Classifies the dollar regime and what it implies for global conditions."""

import pandas as pd

from classification import Classification
from market_snapshot import MarketSnapshot


class UsdRegimeClassifier:
    """Strong / neutral / weak dollar, then combined with EM performance.

    The dollar-plus-EM combination is the cleanest free read on global
    financial conditions: dollar up with EM down is global tightening, dollar
    down with EM up is global easing.
    """

    def classify(self, snapshot: MarketSnapshot) -> Classification:
        if not snapshot.has("dxy"):
            return Classification("US dollar", "unavailable",
                                  "DXY did not load", available=False)

        flags = snapshot.trend_flags("dxy")
        above_50 = bool(flags.get("price>50dma", 0) == 1)
        above_200 = bool(flags.get("price>200dma", 0) == 1)
        move_20d = snapshot.change("dxy", 20)

        strong = above_50 and above_200 and move_20d > 0
        weak = (not above_50) and (not above_200) and move_20d < 0
        state = "Strong" if strong else "Weak" if weak else "Neutral"

        evidence = [
            f"DXY {snapshot.level('dxy'):.2f}, {move_20d:+.2f}% over 20d",
            f"above 50dma: {above_50}, above 200dma: {above_200}",
            f"1y percentile {snapshot.percentile('dxy', '1y'):.0f}",
        ]
        return Classification("US dollar", state, self._global_read(snapshot, move_20d), evidence)

    def _global_read(self, snapshot: MarketSnapshot, dollar_move: float) -> str:
        em_move = snapshot.change("eem", 20)
        if pd.isna(em_move) or pd.isna(dollar_move):
            return "dollar trend only; EM comparison unavailable"
        if dollar_move > 0 and em_move < 0:
            return "global tightening: dollar up, EM under pressure"
        if dollar_move < 0 and em_move > 0:
            return "global easing: dollar down, EM outperforming"
        if dollar_move > 0 and em_move > 0:
            return "unusual: dollar and EM rising together - check the driver"
        return "dollar down but EM not participating - risk aversion, not easing"
