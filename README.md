# Cross-Asset Macro Regime Engine

Observe prices → transform them into signals → combine signals into macro factors →
classify the regime → generate a concise macro intuition.

Every run rebuilds the whole history from prices, so today's reading is simply the last
row of the regime timeline. The console view and the Streamlit app read the same result
object and cannot disagree.

## Running it

```bash
py -3.13 -m pip install -r requirements.txt
```

Console panel (the fastest way to sanity-check the numbers):

```bash
py -3.13 run_engine.py
```

Dashboard:

```bash
py -3.13 -m streamlit run streamlit_app.py
```

## The pipeline

| Stage | Class | What it does |
|---|---|---|
| Load | `MarketDataRepository` | Yahoo + FRED, cached to `.cache/`, aligned onto one business-day calendar |
| Derive | `DerivedSeriesBuilder` | ratios (`RatioBuilder`) and curve spreads (`SpreadBuilder`) |
| Describe | `MarketSnapshot` | horizon returns, YTD, z-scores, 1y/5y percentiles, MA structure |
| Score signals | `SignalScoreBuilder` | trend 30% / momentum 30% / z-score 20% / cross-asset confirmation 20% → −100..+100, then +1 / 0 / −1 states |
| Score factors | `FactorScoreBuilder` | weighted, sign-adjusted blend per factor, with agreement confidence |
| Classify | `RegimeClassifier` + five sub-classifiers | Growth × Inflation cell, risk stance, curve / USD / vol / copper-gold / oil regimes |
| Contradict | `DivergenceDetector` | equity-credit, equity-rates, USD-risk, Fed-conditions, commodity-growth, gold-real-rate, breadth, vol term structure, 6-month extremes |
| Narrate | `MacroIntuitionWriter`, `ExpectedLeadershipBuilder` | deterministic paragraph + what the regime implies |

`RegimeEngine` owns the run order; `EngineResult` carries everything out.

## The six factors

| Factor | −100 | +100 | Main inputs |
|---|---|---|---|
| Growth | deterioration | acceleration | copper/gold, HYG/LQD, IWM/SPY, XLI/XLP, XLY/XLP, EM/SPX, oil |
| Inflation | deflationary | inflationary | 10y breakeven, oil, copper, 10y nominal, gold, 10y real (−) |
| Liquidity | tightening | easing | DXY (−), 2Y (−), HYG/LQD, QQQ/SPY, IWM/SPY, BTC, VIX (−) |
| Risk Appetite | risk-off | risk-on | SPX, HYG/LQD, VIX (−), NDX, RUT, EM/SPX, copper/gold, BTC, DXY (−), gold (−) |
| Credit | stress | healthy | HYG/LQD, HY OAS (−), HYG/SPY, IG OAS (−), JNK/LQD, EMB/IEF |
| Fed | dovish | hawkish | 2Y, 2Y−EFFR, 2s10s (−), DXY, 10y real, breakeven (−) |

Weights, signs and band labels all live in `config.yaml` — nothing is hard-coded in the
scoring classes, so re-weighting a factor is a config edit.

## Regime classification

Growth × Inflation with a ±20 neutral band gives a 3×3 grid:

|  | Inflation ↓ | Inflation → | Inflation ↑ |
|---|---|---|---|
| **Growth ↑** | Goldilocks | Expansion | Reflation |
| **Growth →** | Disinflation | Neutral | Late-cycle inflation |
| **Growth ↓** | Deflation | Slowdown | Stagflation |

The risk score supplies the stance (`REFLATION / RISK-ON`), and modifiers cover the
transitions a static cell cannot express — recovery, rolling over, dovish-Fed-into-
tightening-conditions, risk-on-without-credit.

**Hysteresis.** A hard threshold re-labels the regime whenever a score wobbles across
±20, which produced a new "regime" every few sessions in testing. `hysteresis_days: 3`
means a new classification is adopted only after it has held for three consecutive
sessions. The engine reports both readings: the confirmed regime, and today's raw
scores when they disagree ("today's scores point to NEUTRAL / RISK-ON, not yet
confirmed"). Set `hysteresis_days: 1` in `config.yaml` for the unsmoothed classification.

## Confidence

A factor's confidence is the share of its weight whose signal state agrees with the
factor's sign. The Factors tab splits it three ways — agreeing / neutral / dissenting —
because "low confidence" usually means most signals are sitting in the neutral band, not
that they contradict each other. That is a very different message.

## Data sources

Both free, neither needs an API key.

**Yahoo Finance** — all equity indices and ETFs, sector ETFs, credit ETFs, DXY, WTI,
Brent, gold, copper, silver, Bitcoin, VIX, VXN, 10Y and 30Y CBOE yield indices.

**FRED** — the series Yahoo cannot supply usably:

| Series | Why not Yahoo |
|---|---|
| `DGS2`, `DGS5` | Yahoo has no 2Y; `^FVX` currently returns ~18 observations |
| `DGS10`, `DGS30` | used in preference to `^TNX`/`^TYX` so the whole curve comes from one source |
| `T10YIE`, `T5YIE` | no free breakeven series exists on Yahoo |
| `DFII10`, `DFII5` | no free TIPS real yield exists on Yahoo |
| `VXVCLS` | `^VIX3M` returns a single stale print |
| `EFFR` | policy anchor for the 2Y−EFFR path measure |
| `BAMLH0A0HYM2`, `BAMLC0A0CM` | actual HY/IG option-adjusted spreads |

The spec is framed around yfinance; real yields, breakevens and the VIX term structure
appear throughout it (§5, §10, §13, §20) and simply do not exist on Yahoo, so those five
FRED series are what make those parts of the spec computable rather than approximated.

### Known limits

- **Fed funds futures**: only the front contract (`ZQ=F`) resolves on Yahoo, and the
  front contract barely moves with expectations. It is displayed but deliberately not
  scored; the Fed factor uses the 2Y and the 2Y−EFFR path instead.
- **ICE BofA OAS** history starts ~2023 on the FRED CSV endpoint. Factor weights
  renormalise over whatever exists on each date, so the credit score stays on the same
  scale before and after those series switch on.
- **Series print at different times.** The aligned frame is forward-filled by up to five
  days, but every point-in-time reading is taken at each series' own last genuine print
  (`MarketSnapshot.last_observed`), so a 1-day change is never measured against a
  forward-filled copy of itself. `as_of` is the latest date on which all six factors are
  defined.

## Files

One class per file, in dependency order:

```
config.yaml                       all instruments, weights, thresholds, panels
engine_config.py                  EngineConfig
instrument.py                     Instrument
derived_definition.py             DerivedDefinition
signal_definition.py              SignalDefinition
factor_definition.py              FactorDefinition

price_cache.py                    PriceCache
yahoo_data_loader.py              YahooDataLoader
fred_data_loader.py               FredDataLoader
market_data_repository.py         MarketDataRepository
ratio_builder.py                  RatioBuilder
spread_builder.py                 SpreadBuilder
derived_series_builder.py         DerivedSeriesBuilder

change_calculator.py              ChangeCalculator
zscore_calculator.py              ZScoreCalculator
percentile_calculator.py          PercentileCalculator
trend_analyzer.py                 TrendAnalyzer
momentum_scorer.py                MomentumScorer
confirmation_scorer.py            ConfirmationScorer
signal_score_builder.py           SignalScoreBuilder
market_snapshot.py                MarketSnapshot

factor_score.py                   FactorScore
factor_score_builder.py           FactorScoreBuilder

regime_state.py                   RegimeState
regime_classifier.py              RegimeClassifier
classification.py                 Classification
curve_regime_classifier.py        CurveRegimeClassifier
usd_regime_classifier.py          UsdRegimeClassifier
volatility_regime_classifier.py   VolatilityRegimeClassifier
copper_gold_regime_classifier.py  CopperGoldRegimeClassifier
oil_regime_classifier.py          OilRegimeClassifier

divergence.py                     Divergence
divergence_detector.py            DivergenceDetector
macro_intuition_writer.py         MacroIntuitionWriter
expected_leadership_builder.py    ExpectedLeadershipBuilder

engine_result.py                  EngineResult
regime_engine.py                  RegimeEngine
score_formatter.py                ScoreFormatter
chart_builder.py                  ChartBuilder
streamlit_app.py                  MacroRegimeApp
run_engine.py                     EngineCli
```
