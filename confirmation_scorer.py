"""Cross-asset confirmation: is the rest of the market agreeing with this signal?"""

from typing import Dict, List, Tuple

import pandas as pd


class ConfirmationScorer:
    """Scores a signal by whether its configured peers are moving in agreement.

    This is the component that separates "the S&P is up" from "the S&P is up
    and credit, small caps and volatility all agree". Peers are scored on their
    own 20-day momentum, never on their composite score, so the measure stays
    independent of the signal being scored.
    """

    def score(
        self,
        confirmers: List[Tuple[str, int]],
        peer_momentum: Dict[str, pd.Series],
        index: pd.Index,
    ) -> pd.Series:
        available = [(key, sign) for key, sign in confirmers if key in peer_momentum]
        if not available:
            return pd.Series(index=index, dtype=float)
        contributions = pd.DataFrame({
            key: peer_momentum[key].reindex(index) * sign for key, sign in available
        })
        return contributions.mean(axis=1)
