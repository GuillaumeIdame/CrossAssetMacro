"""Classifies the yield curve move, and why it is happening."""

import pandas as pd

from classification import Classification
from market_snapshot import MarketSnapshot


class CurveRegimeClassifier:
    """Bull/bear x flattening/steepening, plus a reason for the long-end move.

    The four-way label says what happened; the reason classifier says whether a
    bear steepening is reflationary (breakevens and oil up), growth-driven
    (copper and equities up) or a term-premium/fiscal problem (dollar up,
    equities down). Those are three very different trades.
    """

    def __init__(self, horizon: int = 20, move_threshold: float = 0.05):
        self.horizon = horizon
        self.move_threshold = move_threshold

    def classify(self, snapshot: MarketSnapshot) -> Classification:
        if not (snapshot.has("ust2") and snapshot.has("ust10")):
            return Classification("Yield curve", "unavailable",
                                  "2Y or 10Y yield did not load", available=False)

        front = snapshot.change("ust2", self.horizon)
        back = snapshot.change("ust10", self.horizon)
        spread_change = snapshot.change("s2s10", self.horizon)

        if pd.isna(front) or pd.isna(back):
            return Classification("Yield curve", "unavailable",
                                  "not enough history", available=False)

        direction = "Bull" if (front + back) / 2 < 0 else "Bear"
        shape = "steepening" if spread_change > 0 else "flattening"
        state = f"{direction} {shape}"

        evidence = [
            f"2Y {front:+.2f}pp over {self.horizon}d",
            f"10Y {back:+.2f}pp over {self.horizon}d",
            f"2s10s {spread_change:+.0f}bp over {self.horizon}d",
        ]
        return Classification("Yield curve", state, self._reason(snapshot, direction, shape), evidence)

    def _reason(self, snapshot: MarketSnapshot, direction: str, shape: str) -> str:
        breakeven = snapshot.change("bei10", self.horizon)
        oil = snapshot.change("wti", self.horizon)
        copper = snapshot.change("copper", self.horizon)
        equities = snapshot.change("spx", self.horizon)
        dollar = snapshot.change("dxy", self.horizon)
        real = snapshot.change("real10", self.horizon)

        if direction == "Bear" and shape == "steepening":
            if breakeven > self.move_threshold and oil > 0:
                return "inflation / term-premium shock: breakevens and oil leading the long end"
            if copper > 0 and equities > 0:
                return "growth reflation: cyclicals confirming the rise in yields"
            if dollar > 0 and equities < 0:
                return "term-premium stress: yields, dollar up while equities fall"
            return "long end leading, drivers mixed"
        if direction == "Bear" and shape == "flattening":
            return "front end repricing hawkishly: policy expectations, not growth"
        if direction == "Bull" and shape == "steepening":
            if equities < 0:
                return "easing priced as growth deteriorates - classic late-cycle bull steepener"
            return "front end pricing cuts while the long end holds"
        if real < -self.move_threshold:
            return "real yields falling with the whole curve - duration demand"
        return "long end rallying harder than the front end"
