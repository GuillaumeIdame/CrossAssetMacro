"""The classified market regime at a point in time."""

from dataclasses import dataclass, field
from typing import List


@dataclass
class RegimeState:
    """Primary growth/inflation cell, plus the risk overlay and any modifier.

    Two readings are carried. The confirmed one is what the engine reports: it
    only changes once a new classification has persisted (see the hysteresis
    setting). The raw one is what today's scores say on their own. When they
    disagree, a regime change is in progress but not yet confirmed - which is
    itself useful information rather than something to hide.
    """

    as_of: str
    cell: str
    icon: str
    growth_direction: str
    inflation_direction: str
    risk_stance: str
    raw_cell: str
    raw_growth_direction: str
    raw_inflation_direction: str
    raw_risk_stance: str
    modifiers: List[str] = field(default_factory=list)

    def headline(self) -> str:
        return f"{self.cell.upper()} / {self.risk_stance.upper()}"

    def raw_headline(self) -> str:
        return f"{self.raw_cell.upper()} / {self.raw_risk_stance.upper()}"

    def is_pending(self) -> bool:
        return self.raw_headline() != self.headline()
