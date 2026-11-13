"""Refresh the STIR strip snapshot from a locally running TWS / IB Gateway (optional).

    pip install ib_insync
    python -m datahub.ibkr_refresh --host 127.0.0.1 --port 7497

Writes data/ibkr_snapshots/stir_strips_<today>.csv in the same schema as the connector capture.
Without TWS this script does nothing harmful: it reports that it could not connect.
"""

import argparse
import sys
from datetime import date

import pandas as pd

from . import DATA_DIR

SPECS = [  # family, symbol, exchange, currency, n contracts
    ("ZQ", "ZQ", "CBOT", "USD", 14), ("SR3", "SR3", "CME", "USD", 10),
    ("ER", "I", "ICEEU", "EUR", 10), ("SON", "SO3", "ICEEU", "GBP", 10),
]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1"); ap.add_argument("--port", type=int, default=7497)
    ap.add_argument("--client-id", type=int, default=17)
    args = ap.parse_args(argv)
    try:
        from ib_insync import IB, Future
    except ImportError:
        print("ib_insync not installed: pip install ib_insync"); return 1
    ib = IB()
    try:
        ib.connect(args.host, args.port, clientId=args.client_id, timeout=10)
    except Exception as error:
        print(f"could not connect to TWS/Gateway: {error}"); return 1
    rows = []
    for family, symbol, exch, ccy, n in SPECS:
        details = ib.reqContractDetails(Future(symbol=symbol, exchange=exch, currency=ccy))
        details = sorted(details, key=lambda d: d.contract.lastTradeDateOrContractMonth)[:n]
        for d in details:
            c = d.contract
            bars = ib.reqHistoricalData(c, endDateTime="", durationStr="5 D", barSizeSetting="1 day",
                                        whatToShow="TRADES", useRTH=False)
            if not bars:
                continue
            last = bars[-1]
            rows.append(dict(contract=c.localSymbol, exchange=exch, family=family, ccy=ccy,
                             contract_month=f"{c.lastTradeDateOrContractMonth[:4]}-{c.lastTradeDateOrContractMonth[4:6]}",
                             last_trading_date=c.lastTradeDateOrContractMonth, close=last.close, close_date=last.date,
                             source="IBKR-TWS", status="live"))
    ib.disconnect()
    if not rows:
        print("no contracts returned"); return 1
    out = DATA_DIR / "ibkr_snapshots" / f"stir_strips_{date.today()}.csv"
    pd.DataFrame(rows).to_csv(out, index=False)
    print(f"wrote {out} ({len(rows)} contracts)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
