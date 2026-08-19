"""Loads every raw series and aligns it onto one business-day calendar."""

import pandas as pd

from engine_config import EngineConfig
from fred_data_loader import FredDataLoader
from price_cache import PriceCache
from yahoo_data_loader import YahooDataLoader


class MarketDataRepository:
    """Owns the raw price frame: download, cache, align, forward-fill.

    Series arrive on different calendars (US holidays, Tokyo holidays, FRED
    publishing lags, crypto trading every day). Everything is reindexed onto a
    single business-day index and forward-filled by a small number of days, so
    the whole engine can assume one aligned frame without inventing data.
    """

    def __init__(self, config: EngineConfig, use_cache: bool = True):
        self.config = config
        self.use_cache = use_cache
        settings = config.data_settings()
        self.history_years = int(settings["history_years"])
        self.fill_limit = int(settings["fill_limit_days"])
        self.cache = PriceCache(ttl_hours=float(settings["cache_hours"]))
        self.yahoo_loader = YahooDataLoader(history_years=self.history_years)
        self.fred_loader = FredDataLoader(history_years=self.history_years)
        self.rejected = {}
        self.raw = pd.DataFrame()
        self.aligned = pd.DataFrame()
        self.observed = pd.DataFrame()

    # --- loading -------------------------------------------------------------

    def _load_source(self, name: str, loader, instruments) -> pd.DataFrame:
        if self.use_cache and self.cache.is_fresh(name):
            cached = self.cache.read(name)
            if cached is not None and not cached.empty:
                return cached
        frame = loader.load(instruments)
        self.rejected.update(loader.rejected)
        if not frame.empty:
            self.cache.write(name, frame)
        return frame

    def load(self) -> pd.DataFrame:
        """Download (or read from cache) and align everything. Returns the frame."""
        self.rejected = {}
        yahoo = self._load_source("yahoo", self.yahoo_loader, self.config.yahoo_instruments())
        fred = self._load_source("fred", self.fred_loader, self.config.fred_instruments())

        frames = [f for f in (yahoo, fred) if not f.empty]
        if not frames:
            raise RuntimeError("no market data could be loaded from Yahoo or FRED")

        self.raw = pd.concat(frames, axis=1).sort_index()
        self.aligned = self._align(self.raw)
        return self.aligned

    def _align(self, frame: pd.DataFrame) -> pd.DataFrame:
        calendar = pd.bdate_range(frame.index.min(), frame.index.max())
        reindexed = frame.reindex(calendar)
        self.observed = reindexed.notna()
        self.observed.index.name = "date"
        aligned = reindexed.ffill(limit=self.fill_limit)
        aligned.index.name = "date"
        return aligned

    def observed_frame(self) -> pd.DataFrame:
        """True where a series genuinely printed, False where the value was carried forward.

        Series close at different times, so the last row of the aligned frame
        can hold yesterday's US equity close next to today's Tokyo close. Point
        -in-time readings use this mask so a one-day change is measured from a
        real print rather than from a forward-filled copy of itself.
        """
        return self.observed

    # --- access --------------------------------------------------------------

    def frame(self) -> pd.DataFrame:
        return self.aligned

    def status(self) -> pd.DataFrame:
        """One row per configured instrument: loaded / rejected, span, last value."""
        rows = []
        for key, instrument in self.config.instruments.items():
            if key in self.aligned.columns and self.aligned[key].notna().any():
                series = self.aligned[key].where(self.observed[key]).dropna()
                rows.append({
                    "key": key,
                    "name": instrument.name,
                    "source": instrument.source,
                    "ticker": instrument.ticker,
                    "status": "loaded",
                    "observations": int(len(series)),
                    "first": series.index[0].date(),
                    "last": series.index[-1].date(),
                    "value": float(series.iloc[-1]),
                    "note": "",
                })
            else:
                rows.append({
                    "key": key,
                    "name": instrument.name,
                    "source": instrument.source,
                    "ticker": instrument.ticker,
                    "status": "unavailable",
                    "observations": 0,
                    "first": None,
                    "last": None,
                    "value": float("nan"),
                    "note": self.rejected.get(key, "not returned"),
                })
        return pd.DataFrame(rows)
