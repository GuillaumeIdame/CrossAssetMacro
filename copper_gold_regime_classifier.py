"""The copper/gold vs real-yields 2x2."""

import pandas as pd

from classification import Classification
from market_snapshot import MarketSnapshot


class CopperGoldRegimeClassifier:
    """Growth appetite (copper/gold) crossed with the real discount rate.

    Copper/gold rising says growth is being preferred to safety. Whether real
    yields confirm decides if that is healthy reflation or a liquidity-driven
    melt-up; both falling together is the recession signature.
    """

    CELLS = {
        ("up", "up"): ("Growth / reflation", "cyclical strength confirmed by higher real yields"),
        ("up", "down"): ("Strong growth on easy money", "cyclicals rallying while the discount rate falls"),
        ("down", "up"): ("Tightening", "real yields rising while growth appetite fades - the painful combination"),
        ("down", "down"): ("Deflation / recession", "growth appetite and real yields falling together"),
    }

    def __init__(self, horizon: int = 60):
        self.horizon = horizon

    def classify(self, snapshot: MarketSnapshot) -> Classification:
        if not snapshot.has("copper_gold"):
            return Classification("Copper / Gold", "unavailable",
                                  "copper or gold did not load", available=False)

        ratio_move = snapshot.change("copper_gold", self.horizon)
        real_move = snapshot.change("real10", self.horizon)
        if pd.isna(ratio_move):
            return Classification("Copper / Gold", "unavailable",
                                  "not enough history", available=False)

        evidence = [
            f"Copper/Gold {ratio_move:+.1f}% over {self.horizon}d",
            f"1y percentile {snapshot.percentile('copper_gold', '1y'):.0f}",
        ]
        if pd.isna(real_move):
            direction = "rising" if ratio_move > 0 else "falling"
            return Classification(
                "Copper / Gold", f"Growth appetite {direction}",
                "real yields unavailable, so the 2x2 cannot be completed", evidence)

        evidence.append(f"10Y real yield {real_move:+.2f}pp over {self.horizon}d")
        cell = ("up" if ratio_move > 0 else "down", "up" if real_move > 0 else "down")
        state, reason = self.CELLS[cell]
        return Classification("Copper / Gold", state, reason, evidence)
