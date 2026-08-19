"""A series computed from two downloaded series (a ratio or a spread)."""

from dataclasses import dataclass


@dataclass(frozen=True)
class DerivedDefinition:
    """Definition of a ratio (A / B) or a spread ((A - B) * scale)."""

    key: str
    kind: str
    left: str
    right: str
    name: str
    category: str
    mode: str
    scale: float = 1.0

    def is_ratio(self) -> bool:
        return self.kind == "ratio"

    def is_spread(self) -> bool:
        return self.kind == "spread"

    def inputs(self) -> tuple:
        return (self.left, self.right)
