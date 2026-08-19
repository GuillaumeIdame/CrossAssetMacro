"""Console view of the engine: python run_engine.py"""

import textwrap

import pandas as pd

from engine_result import EngineResult
from regime_engine import RegimeEngine
from score_formatter import ScoreFormatter


class EngineCli:
    """Prints the whole regime read as one terminal panel.

    Same numbers as the Streamlit app, useful for a quick morning check or for
    sanity-checking the scores against your own read before trusting the UI.
    """

    WIDTH = 78

    def __init__(self, engine: RegimeEngine = None):
        self.engine = engine or RegimeEngine()
        self.formatter = ScoreFormatter()
        self.lines = []

    # --- layout helpers ------------------------------------------------------

    def _rule(self, character: str = "-") -> None:
        self.lines.append("+" + character * (self.WIDTH - 2) + "+")

    def _row(self, text: str = "") -> None:
        self.lines.append("| " + text.ljust(self.WIDTH - 4)[: self.WIDTH - 4] + " |")

    def _two_columns(self, left: str, right: str) -> None:
        half = (self.WIDTH - 5) // 2
        self._row(left.ljust(half)[:half] + " " + right.ljust(half)[:half])

    def _wrapped(self, text: str) -> None:
        for line in textwrap.wrap(text, width=self.WIDTH - 4):
            self._row(line)

    def _heading(self, title: str) -> None:
        self._rule("=")
        self._row(title.upper())
        self._rule("-")

    # --- sections ------------------------------------------------------------

    def _factors(self, result: EngineResult) -> None:
        self._heading("regime")
        for score in result.factors.values():
            confidence = f"conf {score.confidence * 100:3.0f}% ({score.confidence_label()})"
            self._row(f"  {score.label:<14}{score.value:+7.0f}   {score.band:<24}{confidence}")
        self._row()
        self._row(f"  * CURRENT REGIME: {result.regime.headline()}")
        if result.regime.is_pending():
            self._row(f"    today's scores point to {result.regime.raw_headline()},"
                      f" not yet confirmed")
        for modifier in result.regime.modifiers:
            self._row(f"    note: {modifier}")
        self._row(f"    held for {result.days_in_regime} sessions, as of {result.as_of.date()}")

    def _panels(self, result: EngineResult) -> None:
        snapshot = result.snapshot
        self._heading("market panels")
        rates = result.snapshot.config.panel("rates")
        risk = result.snapshot.config.panel("risk")
        self._two_columns("RATES", "RISK")
        for index in range(max(len(rates), len(risk))):
            left = self._panel_line(snapshot, rates[index]) if index < len(rates) else ""
            right = self._panel_line(snapshot, risk[index]) if index < len(risk) else ""
            self._two_columns(left, right)
        self._row()

        self._two_columns("LIQUIDITY", "GROWTH")
        for left, right in zip(snapshot.config.panel("liquidity_arrows"),
                               snapshot.config.panel("growth_arrows")):
            self._two_columns(self._arrow_line(snapshot, left), self._arrow_line(snapshot, right))
        self._row()

        self._two_columns("INFLATION", "COMMODITIES")
        inflation = snapshot.config.panel("inflation_arrows")
        commodities = snapshot.config.panel("commodity_arrows")
        for index in range(max(len(inflation), len(commodities))):
            left = self._arrow_line(snapshot, inflation[index]) if index < len(inflation) else ""
            right = self._arrow_line(snapshot, commodities[index]) if index < len(commodities) else ""
            self._two_columns(left, right)

    def _panel_line(self, snapshot, key: str) -> str:
        if not snapshot.has(key):
            return f"  {snapshot.config.series_name(key):<20} n/a"
        unit = "%" if snapshot.config.series_mode(key) == "price" else "pts"
        level = self.formatter.level(snapshot.level(key))
        change = self.formatter.change(snapshot.change(key, 1), unit)
        return f"  {snapshot.config.series_name(key)[:14]:<14} {level:>8} {change:>8}"

    def _arrow_line(self, snapshot, key: str) -> str:
        if not snapshot.has(key):
            return f"  {snapshot.config.series_name(key):<22} n/a"
        arrow = self.formatter.arrow(snapshot.change(key, 20))
        percentile = self.formatter.percentile(snapshot.percentile(key, "1y"))
        return f"  {snapshot.config.series_name(key)[:20]:<20} {arrow:>2} {percentile:>5}"

    def _sub_regimes(self, result: EngineResult) -> None:
        self._heading("sub-regimes")
        for classification in result.classifications.values():
            self._row(f"  {classification.topic:<15} {classification.state}")
            self._wrapped(f"      {classification.reason}")
            for line in classification.evidence:
                self._row(f"        {line}")

    def _divergences(self, result: EngineResult) -> None:
        self._heading("divergences / alerts")
        if not result.divergences:
            self._row("  nothing flagged")
            return
        for divergence in result.divergences:
            self._row(f"  {divergence.marker():<3} {divergence.title}")
            for line in divergence.evidence:
                self._row(f"      {line}")

    def _intuition(self, result: EngineResult) -> None:
        self._heading("macro intuition")
        self._wrapped(result.intuition)
        self._row()
        self._row("  EXPECTED LEADERSHIP")
        for _, row in result.leadership.iterrows():
            self._row(f"    {row['asset']:<22} {row['expected']:<6} {row['because'][:42]}")

    def _notes(self, result: EngineResult) -> None:
        if not result.notes:
            return
        self._heading("data notes")
        for note in result.notes:
            self._wrapped(f"  {note}")

    # --- entry point ---------------------------------------------------------

    def render(self, result: EngineResult) -> str:
        self.lines = []
        self._rule("=")
        self._row("CROSS-ASSET MACRO REGIME ENGINE")
        self._factors(result)
        self._panels(result)
        self._sub_regimes(result)
        self._divergences(result)
        self._intuition(result)
        self._notes(result)
        self._rule("=")
        return "\n".join(self.lines)

    def run(self) -> str:
        pd.set_option("display.width", 200)
        result = self.engine.run()
        output = self.render(result)
        print(output)
        return output


if __name__ == "__main__":
    EngineCli().run()
