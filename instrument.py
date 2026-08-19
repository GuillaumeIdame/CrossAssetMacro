"""A single downloadable market series."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Instrument:
    """One raw series pulled from an external source.

    `mode` decides how a change over N days is measured downstream:
    "price" uses a log change (strictly positive series), "level" uses a plain
    difference (yields, spreads, anything that can sit at or below zero).
    """

    key: str
    source: str
    ticker: str
    name: str
    category: str
    mode: str
    scored: bool = True

    def is_yahoo(self) -> bool:
        return self.source == "yahoo"

    def is_fred(self) -> bool:
        return self.source == "fred"
