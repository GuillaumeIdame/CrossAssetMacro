"""One cross-asset contradiction or confirmation worth flagging."""

from dataclasses import dataclass, field
from typing import List


@dataclass
class Divergence:
    """An alert, warning, confirmation or observation about cross-asset agreement."""

    key: str
    severity: str
    title: str
    detail: str
    evidence: List[str] = field(default_factory=list)

    ORDER = {"alert": 0, "warning": 1, "confirmation": 2, "info": 3}

    def rank(self) -> int:
        return self.ORDER.get(self.severity, 9)

    def marker(self) -> str:
        return {"alert": "!!", "warning": "!", "confirmation": "+", "info": "-"}.get(self.severity, "-")
