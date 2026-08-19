"""Result of one of the specialised regime classifiers."""

from dataclasses import dataclass, field
from typing import List


@dataclass
class Classification:
    """A named state plus the evidence that produced it."""

    topic: str
    state: str
    reason: str
    evidence: List[str] = field(default_factory=list)
    available: bool = True
