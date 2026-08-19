"""Downloads daily closes from Yahoo Finance."""

from typing import List

import pandas as pd
import yfinance as yf

from instrument import Instrument


class YahooDataLoader:
    """Pulls adjusted daily closes for a list of instruments in one request."""

    def __init__(self, history_years: int = 12, min_observations: int = 100):
        self.history_years = history_years
        self.min_observations = min_observations
        self.rejected = {}

    def load(self, instruments: List[Instrument]) -> pd.DataFrame:
        """Return a DataFrame indexed by date, one column per instrument key.

        Tickers that come back empty or far too short (Yahoo periodically serves
        a single stale print for some indices) are dropped and recorded in
        `self.rejected` rather than silently poisoning the scores.
        """
        self.rejected = {}
        if not instruments:
            return pd.DataFrame()

        tickers = [i.ticker for i in instruments]
        raw = yf.download(
            tickers,
            period=f"{self.history_years}y",
            interval="1d",
            auto_adjust=True,
            progress=False,
            threads=True,
        )
        closes = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw[["Close"]]

        columns = {}
        for instrument in instruments:
            if instrument.ticker not in closes.columns:
                self.rejected[instrument.key] = "ticker not returned by Yahoo"
                continue
            series = closes[instrument.ticker].dropna()
            if len(series) < self.min_observations:
                self.rejected[instrument.key] = f"only {len(series)} observations"
                continue
            columns[instrument.key] = series

        if not columns:
            return pd.DataFrame()
        frame = pd.DataFrame(columns)
        frame.index = pd.DatetimeIndex(frame.index).tz_localize(None)
        return frame.sort_index()
