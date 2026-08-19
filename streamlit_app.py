"""Cross-Asset Macro Regime Engine - Streamlit front end.

    streamlit run streamlit_app.py
"""

import pandas as pd
import streamlit as st

from chart_builder import ChartBuilder
from engine_config import EngineConfig
from engine_result import EngineResult
from regime_classifier import RegimeClassifier
from regime_engine import RegimeEngine
from score_formatter import ScoreFormatter


class MacroRegimeApp:
    """Renders one EngineResult across six sections, navigated from the left sidebar.

    The app does no analysis of its own: everything shown here comes off the
    result object, so the console view, the charts and the tables can never
    disagree with each other.
    """

    def __init__(self):
        self.config = EngineConfig()
        self.charts = ChartBuilder()
        self.formatter = ScoreFormatter()

    # --- entry point ---------------------------------------------------------

    SECTIONS = ["Regime", "Factors", "Signals", "Sub-regimes", "History", "Data"]

    def run(self) -> None:
        st.set_page_config(page_title="Cross-Asset Macro Regime Engine",
                           page_icon="=", layout="wide")
        result = self._result()
        section = self._sidebar(result)
        self._header(result)
        if section == "Regime":
            self._regime_tab(result)
        elif section == "Factors":
            self._factors_tab(result)
        elif section == "Signals":
            self._signals_tab(result)
        elif section == "Sub-regimes":
            self._sub_regime_tab(result)
        elif section == "History":
            self._history_tab(result)
        elif section == "Data":
            self._data_tab(result)

    def _result(self) -> EngineResult:
        if "result" not in st.session_state:
            with st.spinner("Loading markets and rebuilding the regime history..."):
                st.session_state["result"] = RegimeEngine().run()
        return st.session_state["result"]

    # --- chrome --------------------------------------------------------------

    def _sidebar(self, result: EngineResult) -> str:
        with st.sidebar:
            st.markdown("### Cross-Asset Macro Regime Engine")
            st.caption(f"As of {result.as_of.date()} - "
                       f"{len(result.factor_history):,} sessions of history rebuilt from prices.")

            section = st.radio("Navigate", self.SECTIONS, label_visibility="collapsed")

            st.markdown("---")
            if st.button("Refresh market data", width="stretch"):
                RegimeEngine().repository.cache.clear()
                st.session_state.pop("result", None)
                st.rerun()

            st.markdown("---")
            st.markdown("**Scoring weights**")
            scoring = self.config.scoring()
            for name, weight in scoring["components"].items():
                st.caption(f"{name}: {weight}%")
            st.caption(f"signal state threshold: +/-{scoring['state_threshold']}")
            regime = self.config.regime_settings()
            st.caption(f"regime neutral band: +/-{regime['neutral_band']}")
            st.caption(f"regime hysteresis: {regime['hysteresis_days']} sessions")

            if result.notes:
                st.markdown("---")
                st.markdown("**Data notes**")
                for note in result.notes:
                    st.caption(note)

        return section

    def _header(self, result: EngineResult) -> None:
        regime = result.regime
        st.markdown(f"## {regime.headline()}")
        line = f"Held for **{result.days_in_regime}** sessions - as of **{result.as_of.date()}**"
        if regime.is_pending():
            line += (f" - today's scores point to **{regime.raw_headline()}**, "
                     f"not yet confirmed")
        st.markdown(line)
        for modifier in regime.modifiers:
            st.warning(modifier, icon=None)

    # --- tab 1: regime -------------------------------------------------------

    def _regime_tab(self, result: EngineResult) -> None:
        columns = st.columns(6)
        for column, score in zip(columns, result.factors.values()):
            with column:
                st.metric(
                    label=score.label,
                    value=self.formatter.score(score.value),
                    delta=None if pd.isna(score.change_20d) else f"{score.change_20d:+.0f} vs 20d",
                )
                st.caption(f"{score.band} - confidence {score.confidence_label()}")

        left, right = st.columns([1, 1])
        with left:
            st.markdown("#### Factor scores")
            st.plotly_chart(self.charts.factor_bars(result.factors), width="stretch")
        with right:
            st.markdown("#### Growth x Inflation")
            st.plotly_chart(
                self.charts.quadrant(
                    result.factor_history, 60,
                    float(self.config.regime_settings()["neutral_band"])),
                width="stretch",
            )

        st.markdown("#### Macro intuition")
        st.info(result.intuition)

        left, right = st.columns([3, 2])
        with left:
            st.markdown("#### Divergences and alerts")
            self._divergences(result)
        with right:
            st.markdown("#### What this regime implies")
            st.dataframe(result.leadership, hide_index=True, width="stretch")

        st.markdown("#### Market panels")
        self._panels(result)

    def _divergences(self, result: EngineResult) -> None:
        if not result.divergences:
            st.caption("Nothing flagged: no configured divergence condition is currently met.")
            return
        for divergence in result.divergences:
            with st.expander(f"{divergence.marker()}  {divergence.title}",
                             expanded=divergence.severity == "alert"):
                st.markdown(divergence.detail)
                for line in divergence.evidence:
                    st.caption(line)

    def _panels(self, result: EngineResult) -> None:
        pairs = [
            ("Rates", "rates", 1), ("Risk", "risk", 1),
            ("Liquidity", "liquidity_arrows", 20), ("Growth", "growth_arrows", 20),
            ("Inflation", "inflation_arrows", 20), ("Commodities", "commodity_arrows", 20),
        ]
        months = st.slider("Panel history window (months)", 6, 60, 24, step=6,
                           key="panel_months")
        st.caption("Each panel chart plots its series as z-scores, so yields, spreads and "
                   "ratios sit on one comparable scale - click a name in the legend to "
                   "isolate it.")
        columns = st.columns(2)
        for index, (title, panel, horizon) in enumerate(pairs):
            with columns[index % 2]:
                st.markdown(f"**{title}**")
                st.dataframe(self._panel_frame(result, panel, horizon),
                             hide_index=True, width="stretch")
                keys = self.config.panel(panel)
                labels = {key: self.config.series_name(key) for key in keys}
                st.plotly_chart(
                    self.charts.panel_history(result.snapshot.zscores, keys, labels, months),
                    width="stretch",
                )

    def _panel_frame(self, result: EngineResult, panel: str, horizon: int) -> pd.DataFrame:
        snapshot = result.snapshot
        rows = []
        for key in self.config.panel(panel):
            if not snapshot.has(key):
                rows.append({"series": self.config.series_name(key), "level": "n/a",
                             f"{horizon}d": "n/a", "1y %ile": "n/a", "z": "n/a"})
                continue
            unit = "%" if self.config.series_mode(key) == "price" else "pts"
            rows.append({
                "series": self.config.series_name(key),
                "level": self.formatter.level(snapshot.level(key)),
                f"{horizon}d": self.formatter.change(snapshot.change(key, horizon), unit),
                "1y %ile": self.formatter.percentile(snapshot.percentile(key, "1y")),
                "z": f"{snapshot.zscore(key):+.1f}" if not pd.isna(snapshot.zscore(key)) else "n/a",
            })
        return pd.DataFrame(rows)

    # --- tab 2: factors ------------------------------------------------------

    def _factors_tab(self, result: EngineResult) -> None:
        labels = {k: v.label for k, v in result.factors.items()}
        st.markdown("#### Factor score history")
        chosen = st.multiselect("Factors", list(labels), default=list(labels),
                                format_func=lambda k: labels[k])
        months = st.slider("Months of history", 6, 120, 24, step=6)
        if chosen:
            st.plotly_chart(
                self.charts.factor_history(result.factor_history, chosen, labels, months),
                width="stretch",
            )

        st.markdown("#### How today's score is built")
        factor_key = st.selectbox("Factor", list(labels), format_func=lambda k: labels[k])
        score = result.factors[factor_key]
        definition = self.config.factors[factor_key]

        shares = score.weight_shares()
        columns = st.columns(4)
        columns[0].metric("Score", self.formatter.score(score.value), score.band)
        columns[1].metric("Agreeing weight", f"{shares['agree'] * 100:.0f}%")
        columns[2].metric("Neutral weight", f"{shares['neutral'] * 100:.0f}%")
        columns[3].metric("Dissenting weight", f"{shares['dissent'] * 100:.0f}%")
        st.caption(f"-100 = {definition.low_label}   |   +100 = {definition.high_label}")

        left, right = st.columns([2, 3])
        with left:
            st.plotly_chart(self.charts.contribution_bars(score.contributions), width="stretch")
        with right:
            st.dataframe(self._contribution_frame(score.contributions),
                         hide_index=True, width="stretch")
        missing = score.contributions.attrs.get("missing_signals", [])
        if missing:
            st.caption("Weights renormalised - these configured signals are unavailable: "
                       + ", ".join(missing))

    def _contribution_frame(self, contributions: pd.DataFrame) -> pd.DataFrame:
        return pd.DataFrame({
            "signal": contributions["name"],
            "weight": contributions["weight"].map(lambda w: f"{w:.0f}%"),
            "sign": contributions["sign"].map(lambda s: "+" if s > 0 else "-"),
            "score": contributions["score"].map(self.formatter.score),
            "state": contributions["state"].map(self.formatter.state_label),
            "contribution": contributions["contribution"].map(lambda c: f"{c:+.1f}"),
            "agrees": contributions["agrees"].map(lambda a: "yes" if a else ""),
        })

    # --- tab 3: signals ------------------------------------------------------

    def _signals_tab(self, result: EngineResult) -> None:
        st.markdown("#### Signal scores")
        st.caption("Each score blends trend, momentum, z-score and cross-asset confirmation. "
                   "State is +1 / 0 / -1 at the configured threshold.")
        keys = [k for k in result.signal_scores.columns]
        table = self._signal_frame(result, keys)
        categories = sorted({self.config.signals[k].category for k in keys})
        chosen = st.multiselect("Categories", categories, default=categories)
        filtered = table[table["category"].isin(chosen)] if chosen else table
        st.dataframe(filtered, hide_index=True, width="stretch", height=560)

        st.markdown("#### Score history")
        heatmap_keys = st.multiselect(
            "Signals to chart", keys,
            default=[k for k in ("spx", "hyg_lqd", "copper_gold", "dxy", "vix", "ust2", "bei10")
                     if k in keys],
            format_func=self.config.series_name,
        )
        if heatmap_keys:
            st.plotly_chart(
                self.charts.signal_heatmap(
                    result.signal_scores, heatmap_keys,
                    {k: self.config.series_name(k) for k in heatmap_keys}, 12),
                width="stretch",
            )

    def _signal_frame(self, result: EngineResult, keys) -> pd.DataFrame:
        snapshot = result.snapshot
        scores = result.signal_scores.iloc[-1]
        states = result.signal_states.iloc[-1]
        rows = []
        for key in keys:
            unit = "%" if self.config.series_mode(key) == "price" else "pts"
            components = result.signal_components
            rows.append({
                "signal": self.config.series_name(key),
                "category": self.config.signals[key].category,
                "as of": str(snapshot.last_observed(key).date()),
                "level": self.formatter.level(snapshot.level(key)),
                "1D": self.formatter.change(snapshot.change(key, 1), unit),
                "5D": self.formatter.change(snapshot.change(key, 5), unit),
                "20D": self.formatter.change(snapshot.change(key, 20), unit),
                "60D": self.formatter.change(snapshot.change(key, 60), unit),
                "120D": self.formatter.change(snapshot.change(key, 120), unit),
                "YTD": self.formatter.change(snapshot.year_to_date(key), unit),
                "z": f"{snapshot.zscore(key):+.1f}",
                "1y %ile": self.formatter.percentile(snapshot.percentile(key, "1y")),
                "5y %ile": self.formatter.percentile(snapshot.percentile(key, "5y")),
                "trend": self.formatter.score(components["trend"][key].iloc[-1]),
                "momentum": self.formatter.score(components["momentum"][key].iloc[-1]),
                "confirm": self.formatter.score(components["confirmation"][key].iloc[-1]),
                "score": self.formatter.score(scores[key]),
                "state": self.formatter.state_label(states[key]),
            })
        return pd.DataFrame(rows)

    # --- tab 4: sub-regimes --------------------------------------------------

    def _sub_regime_tab(self, result: EngineResult) -> None:
        columns = st.columns(2)
        for index, classification in enumerate(result.classifications.values()):
            with columns[index % 2]:
                st.markdown(f"**{classification.topic}**")
                if not classification.available:
                    st.caption(classification.reason)
                    continue
                st.markdown(f"### {classification.state}")
                st.caption(classification.reason)
                for line in classification.evidence:
                    st.caption(f"- {line}")
                st.markdown("---")

        st.markdown("#### Curve spreads")
        matrix = result.classifications["curve"]
        curve_table = self._curve_frame(result)
        if curve_table.empty:
            st.caption("No curve spread could be computed.")
        else:
            st.dataframe(curve_table, hide_index=True, width="stretch")
        st.caption(matrix.reason)

    def _curve_frame(self, result: EngineResult) -> pd.DataFrame:
        snapshot = result.snapshot
        rows = []
        for key in ("s2s10", "s5s10", "s5s30", "s2s30"):
            if not snapshot.has(key):
                continue
            rows.append({
                "spread": self.config.series_name(key),
                "level": f"{snapshot.level(key):.0f}bp",
                "5d": f"{snapshot.change(key, 5):+.0f}bp",
                "20d": f"{snapshot.change(key, 20):+.0f}bp",
                "60d": f"{snapshot.change(key, 60):+.0f}bp",
                "1y %ile": self.formatter.percentile(snapshot.percentile(key, "1y")),
            })
        return pd.DataFrame(rows)

    # --- tab 5: history ------------------------------------------------------

    def _history_tab(self, result: EngineResult) -> None:
        st.markdown("#### Regime timeline")
        months = st.slider("Months", 12, 144, 36, step=12, key="ribbon_months")
        st.plotly_chart(self.charts.regime_ribbon(result.regime_history, months),
                        width="stretch")

        left, right = st.columns([3, 2])
        with left:
            st.markdown("#### Regime changes")
            transitions = result.transitions.copy()
            transitions["changed_on"] = transitions["changed_on"].dt.date
            st.dataframe(transitions[["changed_on", "from", "label", "days_in_previous"]].head(40),
                         hide_index=True, width="stretch", height=420)
        with right:
            st.markdown("#### Time spent in each cell (3y)")
            occupancy = RegimeClassifier(self.config).occupancy(result.regime_history, 3)
            st.plotly_chart(self.charts.occupancy_bars(occupancy), width="stretch")

    # --- tab 6: data ---------------------------------------------------------

    def _data_tab(self, result: EngineResult) -> None:
        st.markdown("#### Source status")
        st.caption("Yahoo Finance for prices; FRED for the series Yahoo cannot supply "
                   "(2Y/5Y Treasuries, TIPS real yields, breakevens, 3-month VIX, ICE BofA "
                   "credit spreads). Both are free and need no API key.")
        status = result.data_status.copy()
        status["value"] = status["value"].map(self.formatter.level)
        st.dataframe(status, hide_index=True, width="stretch", height=620)

        if result.notes:
            st.markdown("#### Notes")
            for note in result.notes:
                st.caption(note)


if __name__ == "__main__":
    MacroRegimeApp().run()
