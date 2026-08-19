"""Puts an oil move in context: demand, supply shock or demand destruction."""

import pandas as pd

from classification import Classification
from market_snapshot import MarketSnapshot


class OilRegimeClassifier:
    """Oil alone is ambiguous; oil against copper and equities is not.

    Oil up with copper and equities up is reflation. Oil up with copper and
    equities down is a supply shock, which is a very different inflation - the
    kind that arrives with weaker growth rather than stronger.
    """

    def __init__(self, horizon: int = 20):
        self.horizon = horizon

    def classify(self, snapshot: MarketSnapshot) -> Classification:
        if not snapshot.has("wti"):
            return Classification("Oil", "unavailable", "WTI did not load", available=False)

        oil = snapshot.change("wti", self.horizon)
        copper = snapshot.change("copper", self.horizon)
        equities = snapshot.change("spx", self.horizon)
        if pd.isna(oil) or pd.isna(copper):
            return Classification("Oil", "unavailable", "not enough history", available=False)

        evidence = [
            f"WTI {oil:+.1f}% over {self.horizon}d",
            f"Copper {copper:+.1f}% over {self.horizon}d",
            f"S&P 500 {equities:+.1f}% over {self.horizon}d" if not pd.isna(equities) else "S&P n/a",
            f"WTI 1y percentile {snapshot.percentile('wti', '1y'):.0f}",
        ]

        if oil > 0 and copper > 0:
            state = "Demand-led reflation"
            reason = "oil and copper rising together - an inflation impulse that comes with growth"
        elif oil > 0 and copper < 0:
            state = "Supply shock / stagflationary"
            reason = "oil rising while copper falls - inflation without the growth"
        elif oil < 0 and copper > 0:
            state = "Disinflationary growth"
            reason = "oil falling while copper holds - potentially the best mix for both bonds and equities"
        else:
            state = "Demand destruction"
            reason = "oil and copper falling together - a growth scare, not a disinflation gift"

        if not pd.isna(equities):
            if state == "Supply shock / stagflationary" and equities > 0:
                reason += "; equities are not yet confirming the stress"
            if state == "Demand destruction" and equities > 0:
                reason += "; equities are diverging from the commodity complex"
        return Classification("Oil", state, reason, evidence)
