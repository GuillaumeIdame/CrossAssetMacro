"""Small on-disk cache (parquet) with a TTL, shared by every loader."""

import time
from pathlib import Path
from typing import Optional

import pandas as pd

from . import CACHE_DIR


class DiskCache:
    def __init__(self, directory: Path = CACHE_DIR, ttl_hours: float = 6.0):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.ttl = ttl_hours * 3600.0

    def _path(self, name: str) -> Path:
        safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in name)
        return self.directory / f"{safe}.parquet"

    def fresh(self, name: str) -> bool:
        p = self._path(name)
        return p.exists() and (time.time() - p.stat().st_mtime) < self.ttl

    def read(self, name: str) -> Optional[pd.DataFrame]:
        p = self._path(name)
        if not p.exists():
            return None
        try:
            return pd.read_parquet(p)
        except Exception:
            return None

    def write(self, name: str, frame: pd.DataFrame) -> None:
        try:
            frame.to_parquet(self._path(name))
        except Exception:
            pass

    def age_hours(self, name: str) -> Optional[float]:
        p = self._path(name)
        if not p.exists():
            return None
        return (time.time() - p.stat().st_mtime) / 3600.0

    def clear(self) -> None:
        for p in self.directory.glob("*.parquet"):
            p.unlink()
