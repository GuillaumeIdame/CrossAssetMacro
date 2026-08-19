"""A series that gets converted into a -100..+100 signal score."""

from dataclasses import dataclass, field
from typing import List, Tuple


@dataclass(frozen=True)
class SignalDefinition:
    """One scored indicator.

    `confirmers` are (peer_key, sign) pairs used for the cross-asset
    confirmation component: a peer with sign +1 is expected to move the same
    way as this signal, a peer with sign -1 the opposite way.
    """

    key: str
    name: str
    category: str
    mode: str
    confirmers: List[Tuple[str, int]] = field(default_factory=list)
