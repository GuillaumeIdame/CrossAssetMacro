"""Turns the raw price frame into the full library of scored series."""

import pandas as pd

from engine_config import EngineConfig
from ratio_builder import RatioBuilder
from spread_builder import SpreadBuilder


class DerivedSeriesBuilder:
    """Appends every configured ratio and spread to the aligned price frame."""

    def __init__(self, config: EngineConfig):
        self.config = config
        self.ratio_builder = RatioBuilder()
        self.spread_builder = SpreadBuilder()
        self.skipped = {}
        self.built = []

    def build(self, frame: pd.DataFrame) -> pd.DataFrame:
        """Return a copy of `frame` with one extra column per derived series.

        A derived series whose inputs did not load is skipped and recorded in
        `self.skipped`, rather than emitted as an all-NaN column.
        """
        self.skipped = {}
        columns = {}
        for key, definition in self.config.derived.items():
            left, right = definition.inputs()
            missing = [k for k in (left, right) if k not in frame.columns or frame[k].isna().all()]
            if missing:
                self.skipped[key] = f"missing input(s): {', '.join(missing)}"
                continue
            if definition.is_ratio():
                columns[key] = self.ratio_builder.build(frame[left], frame[right])
            else:
                columns[key] = self.spread_builder.build(frame[left], frame[right], definition.scale)

        self.built = list(columns.keys())
        if not columns:
            return frame.copy()
        return pd.concat([frame, pd.DataFrame(columns, index=frame.index)], axis=1)

    def build_observed(self, observed: pd.DataFrame) -> pd.DataFrame:
        """Extend the observed mask to the derived series (both legs must have printed)."""
        columns = {}
        for key in self.built:
            definition = self.config.derived[key]
            left, right = definition.inputs()
            columns[key] = observed[left] & observed[right]
        if not columns:
            return observed.copy()
        return pd.concat([observed, pd.DataFrame(columns, index=observed.index)], axis=1)
