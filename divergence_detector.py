"""Looks for contradictions between markets, not just the direction of each."""

from typing import Dict, List

import pandas as pd

from divergence import Divergence
from market_snapshot import MarketSnapshot


class DivergenceDetector:
    """Turns cross-asset agreement and disagreement into ranked alerts.

    This is the part that separates a dashboard from a strategy tool: a rally
    that credit, small caps and volatility all confirm is a different trade
    from the same rally with credit rolling over underneath it.
    """

    def __init__(self, horizon: int = 20):
        self.horizon = horizon

    def detect(self, snapshot: MarketSnapshot, factor_values: Dict[str, float]) -> List[Divergence]:
        found = []
        found += self._equity_credit(snapshot)
        found += self._equity_rates(snapshot)
        found += self._dollar_risk(snapshot)
        found += self._fed_conditions(snapshot, factor_values)
        found += self._commodity_growth(snapshot)
        found += self._gold_real_rates(snapshot)
        found += self._breadth(snapshot)
        found += self._volatility_term_structure(snapshot)
        found += self._extremes(snapshot)
        found += self._curve(snapshot)
        return sorted(found, key=lambda d: d.rank())

    # --- helpers -------------------------------------------------------------

    def _move(self, snapshot: MarketSnapshot, key: str) -> float:
        return snapshot.change(key, self.horizon)

    def _usable(self, *values) -> bool:
        return not any(pd.isna(v) for v in values)

    # --- individual checks ---------------------------------------------------

    def _equity_credit(self, snapshot) -> List[Divergence]:
        equities = self._move(snapshot, "spx")
        credit = self._move(snapshot, "hyg_lqd")
        if not self._usable(equities, credit):
            return []
        evidence = [f"S&P {equities:+.1f}% / HYG-LQD {credit:+.1f}% over {self.horizon}d"]
        if equities > 1.0 and credit < -0.5:
            return [Divergence("equity_credit", "alert", "Equity rally without credit confirmation",
                               "Equities are advancing while high yield underperforms investment "
                               "grade. Credit normally leads at turning points, so treat the equity "
                               "move as unconfirmed.", evidence)]
        if equities < -1.0 and credit > 0.5:
            return [Divergence("equity_credit", "info", "Credit holding up through equity weakness",
                               "High yield is outperforming investment grade while equities fall - "
                               "so far this looks like an equity de-rating rather than a credit event.",
                               evidence)]
        if equities > 1.0 and credit > 0.3:
            return [Divergence("equity_credit", "confirmation", "Credit confirms the equity rally",
                               "High yield is outperforming investment grade alongside the equity "
                               "advance.", evidence)]
        return []

    def _equity_rates(self, snapshot) -> List[Divergence]:
        equities = self._move(snapshot, "spx")
        real = self._move(snapshot, "real10")
        if not self._usable(equities, real):
            return []
        if equities > 1.0 and real > 0.20:
            return [Divergence("equity_rates", "warning", "Equities resilient to a rising discount rate",
                               "Real yields are rising materially and equities are rising anyway. "
                               "Either growth expectations are improving fast enough to offset it, "
                               "or the equity market is ignoring the tightening.",
                               [f"S&P {equities:+.1f}%, 10Y real yield {real:+.2f}pp over {self.horizon}d"])]
        if equities < -1.0 and real < -0.20:
            return [Divergence("equity_rates", "info", "Falling real yields not supporting equities",
                               "Duration is being bid while equities fall - the market is pricing "
                               "weaker growth rather than easier policy.",
                               [f"S&P {equities:+.1f}%, 10Y real yield {real:+.2f}pp over {self.horizon}d"])]
        return []

    def _dollar_risk(self, snapshot) -> List[Divergence]:
        dollar = self._move(snapshot, "dxy")
        equities = self._move(snapshot, "spx")
        emerging = self._move(snapshot, "eem")
        if not self._usable(dollar, equities, emerging):
            return []
        evidence = [f"DXY {dollar:+.1f}%, S&P {equities:+.1f}%, EM {emerging:+.1f}% over {self.horizon}d"]
        if dollar > 0.5 and equities > 1.0 and emerging > 1.0:
            return [Divergence("dollar_risk", "alert", "Dollar and risk assets rising together",
                               "An unusual combination. It normally means US growth exceptionalism "
                               "or a rates-driven dollar rather than a stress-driven one - worth "
                               "identifying which before sizing risk.", evidence)]
        if dollar < -0.5 and emerging > 1.0:
            return [Divergence("dollar_risk", "confirmation", "Dollar weakness with EM outperformance",
                               "The cleanest signature of easing global financial conditions.",
                               evidence)]
        if dollar > 1.0 and emerging < -1.0:
            return [Divergence("dollar_risk", "warning", "Dollar strength squeezing EM",
                               "Global financial conditions are tightening through the dollar "
                               "channel.", evidence)]
        return []

    def _fed_conditions(self, snapshot, factor_values) -> List[Divergence]:
        fed = factor_values.get("fed", float("nan"))
        liquidity = factor_values.get("liquidity", float("nan"))
        credit = factor_values.get("credit", float("nan"))
        if not self._usable(fed, liquidity):
            return []
        evidence = [f"Fed score {fed:+.0f}, Liquidity score {liquidity:+.0f}, Credit score {credit:+.0f}"]
        if fed < -30 and liquidity < -20:
            return [Divergence("fed_conditions", "alert", "Dovish Fed, tightening conditions",
                               "The rates market is pricing easier policy while financial "
                               "conditions still deteriorate. That is the signature of the Fed "
                               "turning dovish because something is breaking, not because "
                               "inflation is behaving.", evidence)]
        if fed < -30 and liquidity > 20:
            return [Divergence("fed_conditions", "confirmation", "Dovish Fed feeding through to easier conditions",
                               "Policy easing is being transmitted: the dollar, front-end yields "
                               "and credit are all cooperating.", evidence)]
        if fed > 30 and liquidity > 20:
            return [Divergence("fed_conditions", "warning", "Hawkish Fed, conditions still easing",
                               "Financial conditions are loosening despite a hawkish rates "
                               "impulse - historically this invites a further hawkish response.",
                               evidence)]
        return []

    def _commodity_growth(self, snapshot) -> List[Divergence]:
        oil = self._move(snapshot, "wti")
        copper = self._move(snapshot, "copper")
        equities = self._move(snapshot, "spx")
        if not self._usable(oil, copper):
            return []
        evidence = [f"WTI {oil:+.1f}%, Copper {copper:+.1f}%, S&P {equities:+.1f}% over {self.horizon}d"]
        if oil > 3.0 and copper < -1.0 and (pd.isna(equities) or equities < 0):
            return [Divergence("commodity_growth", "alert", "Oil rising against copper and equities",
                               "This is a supply shock rather than healthy reflation: the "
                               "inflation impulse is arriving without the growth that would "
                               "normally accompany it.", evidence)]
        if oil < -3.0 and copper > 1.0:
            return [Divergence("commodity_growth", "confirmation", "Disinflationary growth mix",
                               "Oil falling while copper rises is the rare combination that "
                               "supports both bonds and equities.", evidence)]
        return []

    def _gold_real_rates(self, snapshot) -> List[Divergence]:
        gold = self._move(snapshot, "gold")
        real = self._move(snapshot, "real10")
        if not self._usable(gold, real):
            return []
        if real > 0.15 and gold > 2.0:
            return [Divergence("gold_real", "alert", "Gold rising with real yields",
                               "Gold normally trades inversely to real yields. Both rising "
                               "together points at structural, monetary or geopolitical demand "
                               "rather than a rates trade.",
                               [f"Gold {gold:+.1f}%, 10Y real yield {real:+.2f}pp over {self.horizon}d"])]
        return []

    def _breadth(self, snapshot) -> List[Divergence]:
        equities = self._move(snapshot, "spx")
        small_caps = self._move(snapshot, "iwm_spy")
        if not self._usable(equities, small_caps):
            return []
        if equities > 1.0 and small_caps < -1.0:
            return [Divergence("breadth", "warning", "Index gains are narrowing",
                               "The S&P is advancing while small caps underperform - leadership "
                               "is concentrating rather than broadening.",
                               [f"S&P {equities:+.1f}%, IWM/SPY {small_caps:+.1f}% over {self.horizon}d"])]
        if equities > 1.0 and small_caps > 1.0:
            return [Divergence("breadth", "confirmation", "Broad participation in the rally",
                               "Small caps are outperforming alongside the index.",
                               [f"S&P {equities:+.1f}%, IWM/SPY {small_caps:+.1f}% over {self.horizon}d"])]
        return []

    def _volatility_term_structure(self, snapshot) -> List[Divergence]:
        if not snapshot.has("vix_vix3m"):
            return []
        ratio = snapshot.level("vix_vix3m")
        equities = self._move(snapshot, "spx")
        if pd.isna(ratio):
            return []
        if ratio > 1.10:
            return [Divergence("vol_term", "alert", "VIX curve in steep backwardation",
                               "Near-term volatility is being bid well above three-month - the "
                               "market is paying up for immediate protection.",
                               [f"VIX/VIX3M {ratio:.3f}, VIX {snapshot.level('vix'):.1f}"])]
        if ratio > 1.00 and not pd.isna(equities) and equities > 0:
            return [Divergence("vol_term", "warning", "Backwardated vol curve despite firm equities",
                               "Front-end volatility is above three-month while the index holds - "
                               "a hedging bid that the price action is not yet reflecting.",
                               [f"VIX/VIX3M {ratio:.3f}, S&P {equities:+.1f}% over {self.horizon}d"])]
        return []

    def _extremes(self, snapshot) -> List[Divergence]:
        """Series sitting at a six-month extreme, which is worth saying out loud."""
        found = []
        window = 126
        for key in ("copper_gold", "hyg_lqd", "dxy", "real10", "bei10"):
            if not snapshot.has(key):
                continue
            series = snapshot.frame[key].dropna().tail(window)
            if len(series) < window // 2:
                continue
            latest = float(series.iloc[-1])
            name = snapshot.config.series_name(key)
            if latest >= series.max():
                found.append(Divergence(f"extreme_{key}", "info", f"{name} at a 6-month high",
                                        f"{name} is at its highest level in {len(series)} sessions.",
                                        [f"level {latest:.4g}"]))
            elif latest <= series.min():
                found.append(Divergence(f"extreme_{key}", "info", f"{name} at a 6-month low",
                                        f"{name} is at its lowest level in {len(series)} sessions.",
                                        [f"level {latest:.4g}"]))
        return found

    def _curve(self, snapshot) -> List[Divergence]:
        change = self._move(snapshot, "s2s10")
        if pd.isna(change):
            return []
        if change > 10:
            return [Divergence("curve", "info", "2s10s steepening",
                               f"The curve has steepened {change:.0f}bp over {self.horizon} sessions.",
                               [f"2s10s {snapshot.level('s2s10'):.0f}bp"])]
        if change < -10:
            return [Divergence("curve", "info", "2s10s flattening",
                               f"The curve has flattened {abs(change):.0f}bp over {self.horizon} sessions.",
                               [f"2s10s {snapshot.level('s2s10'):.0f}bp"])]
        return []
