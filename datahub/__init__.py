"""datahub - shared data layer for the three Investment Process Streamlit apps.

Sources, in order of preference:
  * Yahoo Finance (yfinance)   - prices: equities, FX, futures, vol indices, ETFs
  * FRED (public CSV endpoint) - rates, policy rates, breakevens, macro releases, OAS, BIS REER
  * IBKR                       - STIR strips (snapshot CSV captured through the connector, or
                                 live through ib_insync when TWS/Gateway is running)
  * CFTC COT                   - positioning (download when reachable, else a CSV dropped in data/cftc)

Everything that is not an observed market print is labelled: ``proxy`` (built from public
data with a documented approximation) or ``synthetic`` (generated, never to be traded on).
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
CACHE_DIR = ROOT / ".cache"

__all__ = ["ROOT", "DATA_DIR", "CACHE_DIR"]
