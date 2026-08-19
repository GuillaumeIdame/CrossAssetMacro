"""Loads config.yaml into typed definition objects."""

from pathlib import Path
from typing import Dict, List

import yaml

from derived_definition import DerivedDefinition
from factor_definition import FactorDefinition
from instrument import Instrument
from signal_definition import SignalDefinition


class EngineConfig:
    """Single source of truth for instruments, signals, factors and thresholds."""

    def __init__(self, path: str = None):
        self.path = Path(path) if path else Path(__file__).with_name("config.yaml")
        with open(self.path, "r", encoding="utf-8") as handle:
            self.raw = yaml.safe_load(handle)
        self.instruments = self._build_instruments()
        self.derived = self._build_derived()
        self.signals = self._build_signals()
        self.factors = self._build_factors()

    # --- construction --------------------------------------------------------

    def _build_instruments(self) -> Dict[str, Instrument]:
        built = {}
        for key, spec in self.raw["instruments"].items():
            built[key] = Instrument(
                key=key,
                source=spec["source"],
                ticker=spec["ticker"],
                name=spec["name"],
                category=spec["category"],
                mode=spec["mode"],
                scored=spec.get("scored", True),
            )
        return built

    def _build_derived(self) -> Dict[str, DerivedDefinition]:
        built = {}
        for key, spec in self.raw["derived"].items():
            if spec["kind"] == "ratio":
                left, right = spec["numerator"], spec["denominator"]
            else:
                left, right = spec["long"], spec["short"]
            built[key] = DerivedDefinition(
                key=key,
                kind=spec["kind"],
                left=left,
                right=right,
                name=spec["name"],
                category=spec["category"],
                mode=spec["mode"],
                scale=float(spec.get("scale", 1.0)),
            )
        return built

    def _build_signals(self) -> Dict[str, SignalDefinition]:
        built = {}
        for key, spec in self.raw["signals"].items():
            source = self.instruments.get(key) or self.derived.get(key)
            if source is None:
                raise KeyError(f"signal '{key}' has no matching instrument or derived series")
            confirmers = [(c["signal"], int(c["sign"])) for c in (spec or {}).get("confirmers", [])]
            built[key] = SignalDefinition(
                key=key,
                name=source.name,
                category=source.category,
                mode=source.mode,
                confirmers=confirmers,
            )
        return built

    def _build_factors(self) -> Dict[str, FactorDefinition]:
        built = {}
        for key, spec in self.raw["factors"].items():
            weights = {
                signal: (float(w["weight"]), int(w["sign"]))
                for signal, w in spec["weights"].items()
            }
            bands = [(float(b[0]), float(b[1]), b[2]) for b in spec["bands"]]
            built[key] = FactorDefinition(
                key=key,
                label=spec["label"],
                low_label=spec["low"],
                high_label=spec["high"],
                weights=weights,
                bands=bands,
            )
        return built

    # --- lookups -------------------------------------------------------------

    def yahoo_instruments(self) -> List[Instrument]:
        return [i for i in self.instruments.values() if i.is_yahoo()]

    def fred_instruments(self) -> List[Instrument]:
        return [i for i in self.instruments.values() if i.is_fred()]

    def series_name(self, key: str) -> str:
        source = self.instruments.get(key) or self.derived.get(key)
        return source.name if source else key

    def series_mode(self, key: str) -> str:
        source = self.instruments.get(key) or self.derived.get(key)
        return source.mode if source else "price"

    def signal_keys(self) -> List[str]:
        return list(self.signals.keys())

    def factor_keys(self) -> List[str]:
        return list(self.factors.keys())

    # --- scalar settings -----------------------------------------------------

    def scoring(self) -> dict:
        return self.raw["scoring"]

    def data_settings(self) -> dict:
        return self.raw["data"]

    def regime_settings(self) -> dict:
        return self.raw["regime"]

    def panel(self, name: str) -> List[str]:
        return self.raw["panels"][name]
