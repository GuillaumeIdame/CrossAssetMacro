"""Descriptive statistics for every series: returns, z-scores, percentiles, trend."""

from typing import List

import pandas as pd

from change_calculator import ChangeCalculator
from engine_config import EngineConfig
from percentile_calculator import PercentileCalculator
from trend_analyzer import TrendAnalyzer
from zscore_calculator import ZScoreCalculator


class MarketSnapshot:
    """Everything you would want to say about a series without scoring it.

    Holds full-history tables so that both the current reading and the charts
    come from the same numbers, and answers the three questions the spec asks
    of every variable: how far has it moved, is that unusual, and where does it
    sit in its own range.
    """

    def __init__(self, config: EngineConfig, frame: pd.DataFrame, observed: pd.DataFrame = None):
        self.config = config
        self.frame = frame
        self.observed = observed if observed is not None else frame.notna()
        self.observed = self.observed.reindex(index=frame.index, columns=frame.columns).fillna(False)
        scoring = config.scoring()
        self.horizons = [int(h) for h in scoring["return_horizons"]]
        self.percentile_windows = {k: int(v) for k, v in scoring["percentile_windows"].items()}
        self.change_calculator = ChangeCalculator()
        self.zscore_calculator = ZScoreCalculator(int(scoring["zscore_window"]))
        self.percentile_calculator = PercentileCalculator()
        self.trend_analyzer = TrendAnalyzer(scoring["moving_averages"])
        self.changes = self._build_changes()
        self.ytd = self._build_ytd()
        self.zscores = self._build_zscores()
        self.percentiles = self._build_percentiles()
        self.trend_scores = self._build_trend_scores()

    # --- construction --------------------------------------------------------

    def _modes(self) -> dict:
        return {key: self.config.series_mode(key) for key in self.frame.columns}

    def _build_changes(self) -> dict:
        modes = self._modes()
        return {
            horizon: pd.DataFrame({
                key: self.change_calculator.display_change(self.frame[key], horizon, modes[key])
                for key in self.frame.columns
            }, index=self.frame.index)
            for horizon in self.horizons
        }

    def _build_ytd(self) -> pd.DataFrame:
        modes = self._modes()
        return pd.DataFrame({
            key: self.change_calculator.year_to_date(self.frame[key], modes[key])
            for key in self.frame.columns
        }, index=self.frame.index)

    def _build_zscores(self) -> pd.DataFrame:
        return pd.DataFrame({
            key: self.zscore_calculator.zscore(self.frame[key]) for key in self.frame.columns
        }, index=self.frame.index)

    def _build_percentiles(self) -> dict:
        return {
            name: pd.DataFrame({
                key: self.percentile_calculator.percentile(self.frame[key], window)
                for key in self.frame.columns
            }, index=self.frame.index)
            for name, window in self.percentile_windows.items()
        }

    def _build_trend_scores(self) -> pd.DataFrame:
        return pd.DataFrame({
            key: self.trend_analyzer.score(self.frame[key]) for key in self.frame.columns
        }, index=self.frame.index)

    # --- point-in-time access ------------------------------------------------

    def as_of(self):
        return self.frame.index[-1]

    def has(self, key: str) -> bool:
        return key in self.frame.columns and self.frame[key].notna().any()

    def last_observed(self, key: str):
        """The last date this series genuinely printed, rather than was carried forward."""
        if key not in self.observed.columns:
            return self.frame.index[-1]
        printed = self.observed.index[self.observed[key].to_numpy()]
        return printed[-1] if len(printed) else self.frame.index[-1]

    def _read(self, table: pd.DataFrame, key: str) -> float:
        if table is None or key not in table.columns:
            return float("nan")
        series = table[key].loc[: self.last_observed(key)].dropna()
        return float(series.iloc[-1]) if not series.empty else float("nan")

    def level(self, key: str) -> float:
        return self._read(self.frame, key)

    def change(self, key: str, horizon: int) -> float:
        return self._read(self.changes.get(horizon), key)

    def year_to_date(self, key: str) -> float:
        return self._read(self.ytd, key)

    def zscore(self, key: str) -> float:
        return self._read(self.zscores, key)

    def percentile(self, key: str, window: str = "1y") -> float:
        return self._read(self.percentiles.get(window), key)

    def trend_score(self, key: str) -> float:
        return self._read(self.trend_scores, key)

    def trend_flags(self, key: str) -> pd.Series:
        if not self.has(key):
            return pd.Series(dtype=float)
        flags = self.trend_analyzer.flags(self.frame[key]).loc[: self.last_observed(key)]
        return flags.iloc[-1]

    # --- tables --------------------------------------------------------------

    def table(self, keys: List[str] = None) -> pd.DataFrame:
        """One row per series with level, horizon changes, z-score and percentiles."""
        keys = keys or [k for k in self.frame.columns if self.has(k)]
        rows = []
        for key in keys:
            if not self.has(key):
                continue
            row = {
                "key": key,
                "name": self.config.series_name(key),
                "unit": "%" if self.config.series_mode(key) == "price" else "pts",
                "as_of": self.last_observed(key).date(),
                "level": self.level(key),
            }
            for horizon in self.horizons:
                row[f"{horizon}D"] = self.change(key, horizon)
            row["YTD"] = self.year_to_date(key)
            row["z"] = self.zscore(key)
            for window in self.percentile_windows:
                row[f"pct_{window}"] = self.percentile(key, window)
            row["trend"] = self.trend_score(key)
            rows.append(row)
        return pd.DataFrame(rows)
