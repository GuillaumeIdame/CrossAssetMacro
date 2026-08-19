"""On-disk cache for downloaded series, so a rerun does not re-hit the network."""

import time
from pathlib import Path

import pandas as pd


class PriceCache:
    """Stores a DataFrame as CSV under .cache/ and serves it back within a TTL."""

    def __init__(self, directory: str = None, ttl_hours: float = 6.0):
        self.directory = Path(directory) if directory else Path(__file__).with_name(".cache")
        self.directory.mkdir(parents=True, exist_ok=True)
        self.ttl_seconds = ttl_hours * 3600.0

    def _path(self, name: str) -> Path:
        return self.directory / f"{name}.csv"

    def is_fresh(self, name: str) -> bool:
        path = self._path(name)
        if not path.exists():
            return False
        return (time.time() - path.stat().st_mtime) < self.ttl_seconds

    def read(self, name: str):
        path = self._path(name)
        if not path.exists():
            return None
        frame = pd.read_csv(path, index_col=0, parse_dates=True)
        frame.index = pd.DatetimeIndex(frame.index)
        return frame.sort_index()

    def write(self, name: str, frame: pd.DataFrame) -> None:
        frame.to_csv(self._path(name))

    def clear(self) -> None:
        for path in self.directory.glob("*.csv"):
            path.unlink()
