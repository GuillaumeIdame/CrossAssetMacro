"""Writes the plain-English read of what the market is collectively pricing."""

from typing import Dict, List

from divergence import Divergence
from factor_score import FactorScore
from regime_state import RegimeState


class MacroIntuitionWriter:
    """Turns the scores, the regime and the divergences into a short paragraph.

    Deterministic and template-driven on purpose: the same numbers must always
    produce the same words, so a change in the text means a change in the
    market rather than a change in phrasing.
    """

    GROWTH_PHRASES = {
        "up": "Growth is accelerating",
        "flat": "Growth signals are mixed",
        "down": "Growth is deteriorating",
    }
    INFLATION_PHRASES = {
        "up": "inflation pressure is building",
        "flat": "inflation pressure is contained",
        "down": "inflation pressure is fading",
    }

    def write(
        self,
        regime: RegimeState,
        factors: Dict[str, FactorScore],
        divergences: List[Divergence],
    ) -> str:
        return " ".join([
            self._growth_inflation(regime, factors),
            self._conditions(factors),
            self._policy(factors),
            self._contradiction(divergences),
            self._confidence(factors),
        ]).strip()

    # --- sentences -----------------------------------------------------------

    def _growth_inflation(self, regime: RegimeState, factors: Dict[str, FactorScore]) -> str:
        growth = factors["growth"]
        inflation = factors["inflation"]
        opening = self.GROWTH_PHRASES[regime.raw_growth_direction]
        closing = self.INFLATION_PHRASES[regime.raw_inflation_direction]
        sentence = (f"{opening} while {closing} ({growth.label} {growth.value:+.0f}, "
                    f"{inflation.label} {inflation.value:+.0f}), which reads as "
                    f"{regime.raw_cell.lower()}.")
        if regime.is_pending():
            sentence += (f" The confirmed regime is still {regime.cell.lower()} - today's "
                         f"scores have not held long enough to change the classification.")
        if regime.modifiers:
            sentence += f" The move is qualified: {regime.modifiers[0]}."
        return sentence

    def _conditions(self, factors: Dict[str, FactorScore]) -> str:
        liquidity = factors["liquidity"]
        credit = factors["credit"]
        if liquidity.value > 20 and credit.value > 20:
            return (f"Financial conditions are easing and credit is confirming it "
                    f"(liquidity {liquidity.value:+.0f}, credit {credit.value:+.0f}).")
        if liquidity.value < -20 and credit.value < -20:
            return (f"Financial conditions are tightening and credit is already showing it "
                    f"(liquidity {liquidity.value:+.0f}, credit {credit.value:+.0f}).")
        if liquidity.value > 20 and credit.value < -20:
            return (f"Liquidity is improving but credit is not confirming "
                    f"(liquidity {liquidity.value:+.0f}, credit {credit.value:+.0f}) - "
                    f"the easing is not reaching the borrowers who need it.")
        if liquidity.value < -20 and credit.value > 20:
            return (f"Credit is still healthy despite tightening liquidity "
                    f"(liquidity {liquidity.value:+.0f}, credit {credit.value:+.0f}).")
        return (f"Financial conditions are broadly neutral "
                f"(liquidity {liquidity.value:+.0f}, credit {credit.value:+.0f}).")

    def _policy(self, factors: Dict[str, FactorScore]) -> str:
        fed = factors["fed"]
        risk = factors["risk"]
        liquidity = factors["liquidity"]
        if fed.value < -30 and liquidity.value < -20:
            return (f"The rates market is pricing a dovish impulse ({fed.value:+.0f}) but "
                    f"conditions are still tightening, which reads as the Fed being expected "
                    f"to ease because something is breaking rather than because inflation is "
                    f"behaving.")
        if fed.value > 30:
            return (f"Policy is the constraint here: the Fed impulse is hawkish "
                    f"({fed.value:+.0f}) against risk appetite of {risk.value:+.0f}.")
        if fed.value < -30:
            return (f"The Fed impulse is dovish ({fed.value:+.0f}) and is not currently "
                    f"working against risk appetite of {risk.value:+.0f}.")
        return (f"The Fed is not creating a meaningful impulse either way ({fed.value:+.0f}), "
                f"leaving risk appetite ({risk.value:+.0f}) to be driven by growth and credit.")

    def _contradiction(self, divergences: List[Divergence]) -> str:
        alerts = [d for d in divergences if d.severity == "alert"]
        if not alerts:
            confirmations = [d for d in divergences if d.severity == "confirmation"]
            if confirmations:
                return f"Cross-asset evidence is coherent: {confirmations[0].title.lower()}."
            return "No major cross-asset contradiction is currently flagged."
        if len(alerts) == 1:
            return f"The one contradiction to watch is {alerts[0].title.lower()}."
        titles = ", ".join(a.title.lower() for a in alerts[:2])
        return f"The contradictions to watch are {titles}."

    def _confidence(self, factors: Dict[str, FactorScore]) -> str:
        risk = factors["risk"]
        return (f"Confidence in the {risk.band.lower()} reading is {risk.confidence_label()} "
                f"({risk.confidence * 100:.0f}% of risk-factor weight agrees with its sign).")
