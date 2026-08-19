"""What the classified regime implies about cross-asset leadership."""

from typing import Dict, List

import pandas as pd

from factor_score import FactorScore
from regime_state import RegimeState


class ExpectedLeadershipBuilder:
    """Maps the regime cell onto expected winners and losers, then adjusts.

    These are the regime's textbook implications, not a forecast: the point is
    to make the classification falsifiable. If the regime says cyclicals should
    lead and they are not, that is information.
    """

    BASE = {
        "Goldilocks": [
            ("Equities", "up", "earnings support without a rates constraint"),
            ("Cyclicals", "up", "growth improving"),
            ("Small caps", "up", "domestic growth and easier conditions"),
            ("Credit", "up", "spreads compress into improving growth"),
            ("Duration", "up", "contained inflation lets bonds rally with equities"),
            ("US dollar", "down", "capital rotates out of the safety trade"),
        ],
        "Expansion": [
            ("Equities", "up", "growth is the dominant driver"),
            ("Cyclicals", "up", "the cycle is the trade"),
            ("Credit", "up", "default risk falling"),
            ("Commodities", "up", "demand-led"),
            ("Duration", "flat", "no strong inflation or growth-scare pull"),
        ],
        "Reflation": [
            ("Equities", "up", "nominal growth supports earnings"),
            ("Cyclicals", "up", "operating leverage into rising nominal demand"),
            ("Commodities", "up", "the inflation impulse itself"),
            ("Breakevens", "up", "inflation expectations repricing"),
            ("Duration", "down", "yields rise, long bonds underperform"),
            ("Credit", "up", "still healthy, but watch spreads if yields overshoot"),
        ],
        "Disinflation": [
            ("Duration", "up", "falling inflation with steady growth is the bond trade"),
            ("Equities", "up", "multiple expansion from a lower discount rate"),
            ("Commodities", "down", "the source of the disinflation"),
            ("US dollar", "flat", "depends on whether the Fed follows"),
        ],
        "Neutral": [
            ("Equities", "flat", "no dominant macro driver"),
            ("Duration", "flat", "range-bound"),
            ("Carry", "up", "the environment that rewards carry over direction"),
        ],
        "Late-cycle inflation": [
            ("Commodities", "up", "inflation without growth confirmation"),
            ("Duration", "down", "inflation risk premium"),
            ("Equities", "flat", "margin pressure against nominal support"),
            ("Gold", "up", "monetary and inflation hedge demand"),
        ],
        "Slowdown": [
            ("Duration", "up", "growth deterioration is the bond bid"),
            ("Defensives", "up", "earnings resilience premium"),
            ("Cyclicals", "down", "the cycle is rolling over"),
            ("Credit", "down", "spreads widen before defaults appear"),
        ],
        "Deflation": [
            ("Equities", "down", "earnings and multiple both under pressure"),
            ("Credit", "down", "spread widening leads the equity move"),
            ("Commodities", "down", "demand destruction"),
            ("US dollar", "up", "initially, on the dash for cash"),
            ("Volatility", "up", "regime is unstable"),
            ("Duration", "up", "eventually, once policy responds"),
        ],
        "Stagflation": [
            ("Equities", "down", "margins compress into weaker demand"),
            ("Credit", "down", "financing costs rise as growth falls"),
            ("US dollar", "up", "policy stays tight into weakness"),
            ("Oil", "up", "often the source of the shock"),
            ("Gold", "up", "the hedge that works when both stocks and bonds struggle"),
            ("Duration", "flat", "ambiguous - inflation and growth pull opposite ways"),
        ],
    }

    def build(self, regime: RegimeState, factors: Dict[str, FactorScore]) -> pd.DataFrame:
        rows = [
            {"asset": asset, "expected": direction, "because": reason}
            for asset, direction, reason in self.BASE.get(regime.cell, self.BASE["Neutral"])
        ]
        rows += self._adjustments(factors)
        return pd.DataFrame(rows)

    def _adjustments(self, factors: Dict[str, FactorScore]) -> List[dict]:
        extra = []
        if factors["credit"].value < -30:
            extra.append({"asset": "High yield", "expected": "down",
                          "because": "the credit score is already in stress territory, which "
                                     "overrides the regime's default"})
        if factors["liquidity"].value > 40:
            extra.append({"asset": "Long-duration equity", "expected": "up",
                          "because": "strongly easing liquidity favours the longest-duration "
                                     "risk assets"})
        if factors["liquidity"].value < -40:
            extra.append({"asset": "Long-duration equity", "expected": "down",
                          "because": "severe tightening hits the longest-duration risk assets first"})
        if factors["fed"].value > 40:
            extra.append({"asset": "Front-end rates", "expected": "down",
                          "because": "a strongly hawkish impulse keeps repricing the front end"})
        return extra
