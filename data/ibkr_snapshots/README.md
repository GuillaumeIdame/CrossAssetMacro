# IBKR strip snapshots

One CSV per capture date, `stir_strips_YYYY-MM-DD.csv`, holding the settlement/last close of the
front STIR contracts (30-day Fed Funds `ZQ`, 3M SOFR `SR3`, 3M Euribor `I`/`ER`, 3M SONIA `SO3`).

Captured through the Interactive Brokers connector (delayed data, 10–15 min). The G3 Central
Bank app reads the most recent file. Refresh options:

1. Ask Claude (IBKR connector attached) to recapture the strips → new CSV in this folder.
2. Run `python -m datahub.ibkr_refresh` with TWS / IB Gateway open locally (uses `ib_insync`).
3. Paste a strip by hand in the app's **Market pricing** page (the editor writes the same schema).

Columns: contract, exchange, family, ccy, contract_month, last_trading_date, close, close_date, source, status.
