# Data availability matrix

Probed on 2026-11-13 from the build environment. "Live" = observed market or official print pulled
automatically; "proxy" = built from public data with a documented approximation; "manual" = typed
into the app; "unavailable" = no public source, block shows as unavailable (never faked).

## Sources that work without a key

| Source | What | Freshness | Notes |
|---|---|---|---|
| Yahoo Finance (`yfinance`) | Equity indices & ETFs, G10/EM FX spot, DXY, commodities, Treasury futures (ZT/ZF/ZN/ZB), **individual 30-day fed funds contracts** (`ZQZ26.CBT` …), vol indices (VIX, VIX3M, VIX9D, VVIX, MOVE, OVX, GVZ, SKEW), BTC | daily, same day | Rate-limited: one bulk download per app, cached 6h in `.cache/`. 3M SOFR contracts on Yahoo return a single print — not usable for history. No Bund/Gilt/Euribor/SONIA futures. |
| FRED (public CSV) | UST 1M–30Y, TIPS 5/10, breakevens, 5y5y, ACM term premium, EFFR, SOFR, IORB, target range, ECB DFR/MRO, €STR, SONIA, HY/IG/EUR-HY OAS, NFCI, STLFSI, WALCL, TGA, ON RRP, CPI/core CPI/PCE/core PCE, UNRATE, payrolls, claims, JOLTS, AHE, hours, participation, IP, retail sales, GDPNow, housing, UMich, SLOOS, mortgage rate, Fed broad USD, BIS REER (US, EA, UK, JP, CH, AU, CA), Brent/WTI, Henry Hub | daily (rates), weekly, monthly | 1–2 day lag on daily series. EA/UK/JP series are OECD monthly mirrors with 1–10 month lags (labelled proxy). |
| IBKR connector (via Claude) | Futures ladders and delayed prices for ZQ, SR3, Euribor (ICEEU `I`), SONIA (ICEEU `SO3`), Schatz/Bobl/Bund/Buxl/OAT/BTP, options chains (FOP) | delayed 10–15 min | Snapshot CSV committed in `data/ibkr_snapshots/`; refresh through the connector or `datahub/ibkr_refresh.py` with TWS. Options IV/greeks available per contract through the connector (not wired automatically). |

## Blocked from this environment (work on a desktop with open internet)

CFTC (cftc.gov, publicreporting.cftc.gov), ECB SDW, BoE IADB, BLS API, NY Fed markets API, CME,
Polymarket/Kalshi, Atlanta Fed, Trading Economics. The loaders try them and fall back cleanly:
CFTC accepts the annual `FinFutYY.txt` / `deacotYY` files dropped in `data/cftc/`.

## Per-process coverage

### G3 Central Bank
| Block | Status | Source |
|---|---|---|
| Macro gauges US (spot/forward) | live | FRED |
| Macro gauges EA/UK | proxy (lagging monthly) | FRED/OECD/Eurostat |
| Fed funds strip, meeting path | live, daily | Yahoo individual ZQ contracts |
| SOFR 3M / Euribor / SONIA strips | live snapshot (dated) | IBKR connector |
| 2y, 1y1y proxy, breakevens, term premium | live | FRED |
| Consensus / Smart Forecasters | manual | no public survey feed |
| STIR option surface, event vol | manual (IV inputs) | no public surface; IBKR FOP chains possible via connector |
| Meeting calendar | confirmed 2026–27 (Fed), provisional (ECB/BoE 2027), estimated releases | `data/g3_calendar.csv` |

### Macro FX
| Block | Status | Source |
|---|---|---|
| Spot, factor decomposition, momentum | live | Yahoo |
| Carry ranks | proxy | FRED policy/short rates (daily US/EA/UK, monthly others) |
| 1Y1Y real-rate differential | proxy | US from FRED, others monthly |
| Terms of trade | proxy | Yahoo commodity baskets |
| Fiscal impulse | manual | — |
| Valuation regressions, REER stretch | live / proxy | Yahoo + FRED (BIS REER monthly) |
| CFTC positioning | unavailable here → local files | CFTC |
| FX option surface (ATM, RR, BF) | manual | no public OTC surface |
| Seasonality screener | live (history from Yahoo start) | Yahoo |
| Regime axes | live / proxy (no cross-currency basis) | Yahoo + FRED |

### Macro Thematic
| Block | Status | Source |
|---|---|---|
| Six-variable regime engine | live / proxy (ISM → IP/UMich/GDPNow) | FRED + Yahoo |
| Policy variable | live | ZQ strip bootstrap |
| Liquidity (WALCL − TGA − RRP), NFCI | live | FRED |
| Credit, vol, confirmations | live | FRED + Yahoo |
| Valuation / carry / seasonality pillars | live / proxy | FRED curve + Yahoo |
| Positioning pillar | CTA replication live; CFTC via local files | Yahoo / CFTC |
| Options layer (VRP, skew) | live for index vol (VIX, MOVE, OVX, GVZ, SKEW); manual otherwise | Yahoo |
| Stress episodes | live for windows inside 12y history | Yahoo + FRED |
