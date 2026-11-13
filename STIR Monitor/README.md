# STIR Monitor

Streamlit short-rates monitor. Market data comes from **Interactive Brokers** (TWS / IB Gateway API),
with **yfinance** as a fallback for SOFR and Fed Funds.

```bash
cd "STIR Monitor"
pip install -r requirements.txt
streamlit run app.py
```

## IBKR setup

1. Run TWS or IB Gateway and log in.
2. Enable the API: *Configure → API → Settings → Enable ActiveX and Socket Clients*.
   Read-only is fine.
3. Ports: TWS 7496 live / 7497 paper, Gateway 4001 / 4002. Set the default in `config.yaml`
   or change it in the sidebar under **IBKR connection**.
4. Market data: `market_data_type: 3` (delayed, free) works without subscriptions. Set it to 1
   if you have real-time subscriptions for CME, CBOT, ICE Futures Europe, Eurex, Montréal (CDE)
   and ASX 24 (SNFE). Historical bars for some exchanges may still need a subscription. Any
   contract that returns nothing is listed in **Data status**.

The app opens a short connection per refresh, with client IDs `client_id`, +1 and +2. Daily
bars are cached for 1 h, 5-min bars for 5 min, last prices for 60 s.

## Sources by widget

| Widget | Source |
|---|---|
| Net change heatmap, Dec spreads, Z27 bars, curve chart | IBKR: 3M SOFR (CME), 3M Euribor (ICE), 3M SONIA (ICE), 3M CORRA (CDE), 3M SARON (Eurex), 90D bills (ASX). SOFR falls back to Yahoo `SR3<M><YY>.CME` |
| Priced moves: Fed | 30D Fed Funds (CBOT ZQ) from IBKR, or Yahoo `ZQ<M><YY>.CBT`. Meeting-by-meeting FedWatch method, starting from EFFR |
| Priced moves: BoC | 3M CORRA strip from IBKR, starting from the CORRA fixing. **Approximate**: no monthly CORRA future exists, so the path is a smoothed least-squares fit to the quarterly contracts |
| Overnight fixings | FRED (SOFR, EFFR, €STR, SONIA), Bank of Canada Valet (CORRA), RBA F1 (cash rate, 3M BAB) |
| Bonds curve view | Yahoo `^IRX ^FVX ^TNX ^TYX` |
| Speakers | `speakers.json` (manual) + federalreserve.gov speeches RSS. RATES READ pricing is filled live |

Contracts are pinned by IBKR contract ID in `config.yaml` (checked 13 Nov 2026). Add new
contracts there as they list. `—` in a table means the contract has expired or isn't listed
(e.g. Euribor and ASX bills expire in their contract month, so there's no U26).

**Meeting dates** in `config.yaml` come from the official calendars:
- FOMC: federalreserve.gov. The 2027 dates are tentative, and the 26–27 Oct 2027 strategy
  meeting is excluded.
- BoC: the 2027 schedule published 15 Jul 2026.

**Show mock rows** fills any curve that returned no data with MOCK-tagged values. Leave it off
for real use.

## Files

- `app.py`: Streamlit layout and widgets
- `config.yaml`: provider, IBKR connection, contract IDs, FOMC/BoC dates, fixing IDs, colours
- `stir/calc.py`: pure maths (bp changes, reference points, Dec spreads, FOMC path, CORRA strip fit)
- `stir/sources.py`: data adapters (IBKR via ib_async, Yahoo, FRED, BoC, RBA, Fed RSS)
- `stir/mock.py`: labelled mock data for curves with no free feed
- `stir/ui.py`: CSS and HTML table/card builders
- `mockup.html`: the original static design mockup
- `tests/`: `python -m pytest tests`

## Conventions

- Rate change (bp) = −(price change) × 100, so positive = hawkish.
- Spread = price(front) − price(back).
- Day = vs prior settle; Week = vs last Friday's settle; Since = vs close on the sidebar date;
  Since EU Open = vs the first bar after 07:00 London.
