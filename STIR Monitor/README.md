# STIR Monitor

Streamlit short-rates monitor built on **free data only** (no API keys).

```bash
cd "STIR Monitor"
pip install -r requirements.txt
streamlit run app.py
```

## What is live and where it comes from

| Widget | Source | Notes |
|---|---|---|
| Overnight fixings | FRED (SOFR, EFFR, €STR, SONIA), Bank of Canada Valet (CORRA), RBA table F1 (cash rate, 3M BAB) | daily, published with a 1-day lag |
| Net change heatmap (SOFR row) | Yahoo Finance, CME 3M SOFR futures `SR3<M><YY>.CME` | 5-min bars, ~10 min delayed |
| Dec spreads (SOFR) | same as above | Z6Z7 / Z7Z8 / Z8Z9 |
| Z27 sentiment (SOFR) | same as above | Day, Week, 1W–6M |
| Net change curve | SOFR strip or UST yield indices (`^IRX ^FVX ^TNX ^TYX`) | |
| Priced moves – Fed | Yahoo, 30D Fed Funds futures `ZQ<M><YY>.CBT` + EFFR | CME FedWatch-style meeting-by-meeting path, N-days-ago stepper |
| Speaker cards | `speakers.json` (manual) + Fed speeches RSS | RATES READ pricing filled live |

**No free feed exists** for Euribor, SONIA, CORRA, SARON or Aussie Bills futures, or for CORRA
(BoC) meeting pricing. Those rows show up only with **Show mock rows** on in the sidebar, and are
tagged `MOCK`. To make them live, add an adapter in `stir/sources.py` that returns
`{contract_code: pd.Series of prices}` and wire it in `app.py`.

The sidebar **Data status** panel lists every feed that failed to load. The app never fills a
failed live feed with invented numbers.

## Files

- `app.py`: Streamlit layout and widgets
- `config.yaml`: tickers, contract list, FOMC dates (check the provisional 2027 dates), fixing IDs, colours
- `stir/calc.py`: pure maths (bp changes, reference points per timeframe, Dec spreads, FOMC path)
- `stir/sources.py`: free-data adapters (Yahoo, FRED, BoC, RBA, Fed RSS)
- `stir/mock.py`: labelled mock data for curves with no free feed
- `stir/ui.py`: CSS and HTML table/card builders
- `mockup.html`: the original static design mockup
- `tests/`: `python -m pytest tests`

## Conventions

- Rate change (bp) = −(price change) × 100, so positive = hawkish.
- Spread = price(front) − price(back).
- Day = vs prior settle; Week = vs last Friday's settle; Since = vs close on the sidebar date;
  Since EU Open = vs the first bar after 07:00 London.
