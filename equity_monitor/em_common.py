"""Shared helpers for the Equity Monitor: timestamps, logging, JSON I/O, retries."""

import json
import logging
import math
import os
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent


def now_iso() -> str:
    """UTC timestamp with seconds, the stamp carried by every fetched record."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def today_utc():
    return datetime.now(timezone.utc).date()


def load_config(path: Path = HERE / "monitor_config.json") -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def output_dir(config: dict) -> Path:
    out = HERE / config.get("output_dir", "Sources du dashboard")
    out.mkdir(parents=True, exist_ok=True)
    return out


def setup_logging(run_stamp: str) -> logging.Logger:
    logs = HERE / "logs"
    logs.mkdir(exist_ok=True)
    logger = logging.getLogger("equity_monitor")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s", datefmt="%Y-%m-%dT%H:%M:%S")
    fh = logging.FileHandler(logs / f"run_{run_stamp}.log", encoding="utf-8")
    fh.setFormatter(fmt)
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    logger.addHandler(fh)
    logger.addHandler(sh)
    return logger


def clean(value):
    """Turn NaN / numpy scalars / dates into JSON-safe values; None stays None (rendered as n/a)."""
    if value is None:
        return None
    if isinstance(value, float):
        return None if (math.isnan(value) or math.isinf(value)) else round(value, 6)
    if hasattr(value, "item"):  # numpy scalar
        try:
            return clean(value.item())
        except Exception:
            return None
    if isinstance(value, (datetime,)):
        return value.strftime("%Y-%m-%d")
    if hasattr(value, "isoformat"):
        return value.isoformat()[:10]
    if isinstance(value, dict):
        return {str(k): clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]
    return value


def write_json(path: Path, payload: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(clean(payload), fh, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, path)


def read_json(path: Path):
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return None


def retry(fn, attempts=3, base_delay=2.0, logger=None, what=""):
    """Call fn() up to `attempts` times with exponential backoff; raise the last error."""
    last = None
    for i in range(attempts):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001
            last = exc
            if logger:
                logger.warning("%s: attempt %d/%d failed: %s", what, i + 1, attempts, exc)
            time.sleep(base_delay * (2 ** i))
    raise last


class SymbolLog:
    """One entry per symbol per source, written into run_status.json."""

    def __init__(self):
        self.entries = []

    def add(self, symbol, source, status, detail="", fetched_at=None):
        self.entries.append({
            "symbol": symbol,
            "source": source,
            "status": status,
            "detail": str(detail)[:300],
            "fetched_at": fetched_at or now_iso(),
        })

    def counts(self):
        out = {}
        for e in self.entries:
            out[e["status"]] = out.get(e["status"], 0) + 1
        return out
