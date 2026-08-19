"""The latest reading of one macro factor."""

from dataclasses import dataclass

import pandas as pd


@dataclass
class FactorScore:
    """A factor's current value, its band label and how united its inputs are."""

    key: str
    label: str
    value: float
    band: str
    confidence: float
    change_20d: float
    contributions: pd.DataFrame

    def confidence_label(self) -> str:
        if self.confidence >= 0.70:
            return "high"
        if self.confidence >= 0.45:
            return "medium"
        return "low"

    def weight_shares(self) -> dict:
        """How the factor's weight splits between agreeing, neutral and dissenting signals.

        Confidence is agreeing weight over total weight, so a factor can read
        "low confidence" simply because most of its signals are sitting in the
        neutral band rather than because they contradict each other. These
        three shares make that distinction visible.
        """
        table = self.contributions
        total = table["weight"].sum()
        if total == 0:
            return {"agree": 0.0, "neutral": 0.0, "dissent": 0.0}
        stance = table["state"] * table["sign"] * (1 if self.value >= 0 else -1)
        return {
            "agree": float(table.loc[stance > 0, "weight"].sum() / total),
            "neutral": float(table.loc[stance == 0, "weight"].sum() / total),
            "dissent": float(table.loc[stance < 0, "weight"].sum() / total),
        }
