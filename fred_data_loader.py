"""Downloads daily series from FRED's public CSV endpoint (no API key needed).

Used only for the series Yahoo cannot supply: the 2Y/5Y Treasury points, TIPS
real yields, breakeven inflation, 3-month VIX and ICE BofA credit spreads.
"""

import io
from typing import List

import pandas as pd
import requests

from instrument import Instrument


class FredDataLoader:
    """Fetches one FRED series per request and assembles them into one frame."""

    BASE_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"

    def __init__(self, history_years: int = 12, timeout: int = 30, min_observations: int = 100):
        self.history_years = history_years
        self.timeout = timeout
        self.min_observations = min_observations
        self.rejected = {}

    def _start_date(self) -> str:
        start = pd.Timestamp.today().normalize() - pd.DateOffset(years=self.history_years)
        return start.strftime("%Y-%m-%d")

    def _fetch_one(self, ticker: str) -> pd.Series:
        response = requests.get(
            self.BASE_URL,
            params={"id": ticker, "cosd": self._start_date()},
            timeout=self.timeout,
        )
        response.raise_for_status()
        frame = pd.read_csv(io.StringIO(response.text))
        date_column, value_column = frame.columns[0], frame.columns[1]
        series = pd.Series(
            pd.to_numeric(frame[value_column], errors="coerce").values,
            index=pd.DatetimeIndex(pd.to_datetime(frame[date_column])),
        )
        return series.dropna().sort_index()

    def load(self, instruments: List[Instrument]) -> pd.DataFrame:
        """Return a DataFrame indexed by date, one column per instrument key.

        A series that fails to download is dropped and recorded in
        `self.rejected`; the engine renormalises factor weights around it.
        """
        self.rejected = {}
        columns = {}
        for instrument in instruments:
            try:
                series = self._fetch_one(instrument.ticker)
            except Exception as error:
                self.rejected[instrument.key] = f"{type(error).__name__}: {error}"
                continue
            if len(series) < self.min_observations:
                self.rejected[instrument.key] = f"only {len(series)} observations"
                continue
            columns[instrument.key] = series

        if not columns:
            return pd.DataFrame()
        return pd.DataFrame(columns).sort_index()
