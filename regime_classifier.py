"""Maps the growth and inflation scores onto a named regime."""

import pandas as pd

from engine_config import EngineConfig
from regime_state import RegimeState


class RegimeClassifier:
    """Growth x Inflation gives the primary cell; risk appetite gives the stance.

    A neutral band around zero turns the spec's 2x2 into a 3x3, so a market
    that is genuinely undecided is labelled "Neutral" rather than being forced
    into Goldilocks or Stagflation by a score of +3.

    Hard thresholds also flip on noise: a growth score oscillating between 19
    and 21 would otherwise re-label the regime every other day. `hysteresis_days`
    requires a new label to hold for several consecutive sessions before it is
    adopted. Set it to 1 in config.yaml to see the raw, unsmoothed classification.
    """

    def __init__(self, config: EngineConfig):
        settings = config.regime_settings()
        self.neutral_band = float(settings["neutral_band"])
        self.cells = settings["cells"]
        self.recovery_threshold = float(settings["recovery_change_threshold"])
        self.recovery_lookback = int(settings["recovery_lookback"])
        self.hysteresis_days = int(settings.get("hysteresis_days", 3))

    # --- direction helpers ---------------------------------------------------

    def direction(self, value: float) -> str:
        if pd.isna(value):
            return "flat"
        if value > self.neutral_band:
            return "up"
        if value < -self.neutral_band:
            return "down"
        return "flat"

    def _direction_series(self, values: pd.Series) -> pd.Series:
        directions = pd.Series("flat", index=values.index, dtype=object)
        directions = directions.mask(values > self.neutral_band, "up")
        directions = directions.mask(values < -self.neutral_band, "down")
        return directions

    def risk_stance(self, risk_value: float) -> str:
        if pd.isna(risk_value):
            return "Neutral"
        if risk_value > self.neutral_band:
            return "Risk-on"
        if risk_value < -self.neutral_band:
            return "Risk-off"
        return "Neutral"

    # --- classification ------------------------------------------------------

    def classify_history(self, factor_scores: pd.DataFrame) -> pd.DataFrame:
        growth_direction = self._direction_series(factor_scores["growth"])
        inflation_direction = self._direction_series(factor_scores["inflation"])
        risk = factor_scores["risk"].map(self.risk_stance)

        raw_key = growth_direction + "|" + inflation_direction + "|" + risk
        stable_key = self._stabilise(raw_key)

        parts = stable_key.str.split("|", expand=True)
        parts.columns = ["growth_direction", "inflation_direction", "risk_stance"]
        cell = (parts["growth_direction"] + "|" + parts["inflation_direction"]).map(
            lambda k: self.cells[k]["name"]
        )
        return pd.DataFrame({
            "growth_direction": parts["growth_direction"],
            "inflation_direction": parts["inflation_direction"],
            "cell": cell,
            "risk_stance": parts["risk_stance"],
            "label": cell.str.upper() + " / " + parts["risk_stance"].str.upper(),
            "raw_label": raw_key,
        }, index=factor_scores.index)

    def _stabilise(self, raw_key: pd.Series) -> pd.Series:
        """Adopt a new label only once it has persisted for `hysteresis_days`."""
        if self.hysteresis_days <= 1 or raw_key.empty:
            return raw_key
        values = raw_key.tolist()
        current = values[0]
        candidate = current
        streak = 0
        stabilised = []
        for value in values:
            if value == current:
                candidate, streak = current, 0
            elif value == candidate:
                streak += 1
                if streak >= self.hysteresis_days:
                    current, streak = candidate, 0
            else:
                candidate, streak = value, 1
                if streak >= self.hysteresis_days:
                    current = candidate
            stabilised.append(current)
        return pd.Series(stabilised, index=raw_key.index, dtype=object)

    def classify_latest(self, factor_scores: pd.DataFrame, history: pd.DataFrame) -> RegimeState:
        row = history.iloc[-1]
        cell = self.cells[f"{row['growth_direction']}|{row['inflation_direction']}"]
        raw_growth, raw_inflation, raw_risk = row["raw_label"].split("|")
        raw_cell = self.cells[f"{raw_growth}|{raw_inflation}"]
        return RegimeState(
            as_of=str(factor_scores.index[-1].date()),
            cell=cell["name"],
            icon=cell["icon"],
            growth_direction=row["growth_direction"],
            inflation_direction=row["inflation_direction"],
            risk_stance=row["risk_stance"],
            raw_cell=raw_cell["name"],
            raw_growth_direction=raw_growth,
            raw_inflation_direction=raw_inflation,
            raw_risk_stance=raw_risk,
            modifiers=self._modifiers(factor_scores),
        )

    def _modifiers(self, factor_scores: pd.DataFrame) -> list:
        """Transition tags the static cell cannot express."""
        modifiers = []
        latest = factor_scores.iloc[-1]
        lookback = min(self.recovery_lookback, len(factor_scores) - 1)
        if lookback <= 0:
            return modifiers
        previous = factor_scores.iloc[-1 - lookback]

        growth_change = latest["growth"] - previous["growth"]
        if latest["growth"] < 0 and growth_change > self.recovery_threshold:
            modifiers.append("recovery: growth turning up from a low base")
        if latest["growth"] > 0 and growth_change < -self.recovery_threshold:
            modifiers.append("rolling over: growth fading from a high base")
        if latest["fed"] < -30 and latest["liquidity"] < -20:
            modifiers.append("dovish Fed but tightening conditions")
        if latest["credit"] < -30 and latest["risk"] > 20:
            modifiers.append("risk-on without credit confirmation")
        return modifiers

    # --- history helpers -----------------------------------------------------

    def transitions(self, history: pd.DataFrame) -> pd.DataFrame:
        """Dates on which the regime label changed, newest first."""
        label = history["label"]
        changed = label.ne(label.shift())
        changes = history.loc[changed, ["cell", "risk_stance", "label"]].copy()
        changes["from"] = label.shift().loc[changed].to_numpy()
        durations = pd.Series(changes.index).diff().dt.days.to_numpy()
        changes["days_in_previous"] = durations
        changes = changes.reset_index()
        changes = changes.rename(columns={changes.columns[0]: "changed_on"})
        return changes.iloc[::-1].reset_index(drop=True)

    def time_in_regime(self, history: pd.DataFrame) -> int:
        """Number of consecutive sessions the current label has held."""
        label = history["label"]
        current = label.iloc[-1]
        streak = 0
        for value in label.iloc[::-1]:
            if value != current:
                break
            streak += 1
        return streak

    def occupancy(self, history: pd.DataFrame, years: float = 3.0) -> pd.DataFrame:
        """Share of sessions spent in each cell over a trailing window."""
        cutoff = history.index[-1] - pd.DateOffset(years=int(years))
        window = history.loc[history.index >= cutoff]
        counts = window["cell"].value_counts()
        return pd.DataFrame({
            "cell": counts.index,
            "sessions": counts.to_numpy(),
            "share": (counts / len(window) * 100.0).to_numpy(),
        })
