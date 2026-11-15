"""Download daily and hourly bars for IPOs, their listed peers and stakeholders, and the market (for beta_trade.py)."""
import json, time
from pathlib import Path
import pandas as pd
import yfinance as yf

OUT = Path(__file__).parent / "data/raw/beta"
OUT.mkdir(parents=True, exist_ok=True)
# peers: listed comparables at IPO date; holders: listed companies with an economic stake in the issuer
PEERS = {
 "SNOW": (["MDB", "DDOG", "NET"], []), "U": (["EA", "TTWO"], []), "ARM": (["NVDA", "AMD", "QCOM", "AVGO"], []),
 "KVYO": (["HUBS", "BRZE"], ["SHOP"]), "ALAB": (["AVGO", "MRVL", "CRDO"], []), "CRWV": (["NBIS", "ORCL", "SMCI"], ["NVDA"]),
 "FIG": (["ADBE", "WIX"], []), "DUOL": (["CHGG", "COUR"], []), "RBRK": (["CRWD", "PANW", "NTNX"], []), "NTSK": (["ZS", "CRWD", "PANW", "NET"], []),
 "SAIL": (["OKTA", "CYBR", "CRWD"], []), "TOST": (["XYZ", "FOUR", "PAR"], []), "ABNB": (["BKNG", "EXPE"], []), "DASH": (["UBER", "LYFT"], []),
 "CPNG": (["AMZN", "MELI", "SE"], []), "CART": (["DASH", "UBER", "KR"], []), "RDDT": (["META", "PINS", "SNAP"], []), "BMBL": (["MTCH"], []),
 "STUB": (["EB", "LYV", "SEAT"], []), "COMP": (["Z", "RDFN", "EXPI"], []), "HOOD": (["SCHW", "IBKR", "COIN"], []), "AFRM": (["PYPL", "XYZ", "UPST"], []),
 "CRCL": (["HOOD"], ["COIN"]), "CHYM": (["SOFI", "NU", "DAVE"], []), "KLAR": (["AFRM", "PYPL", "SEZL"], []), "ETOR": (["HOOD", "COIN", "IBKR"], []),
 "FIGR": (["SOFI", "UPST", "COIN"], []), "GEMI": (["COIN", "HOOD", "CRCL"], []), "OSCR": (["UNH", "HUM", "CLOV"], []), "MDLN": (["OMI", "CAH", "MCK"], []),
 "TEM": (["GH", "NTRA"], []), "WAY": (["EVH", "PHR"], []), "HNGE": (["TDOC", "HIMS"], []), "CAVA": (["CMG", "SG", "WING"], []),
 "BIRK": (["DECK", "CROX", "NKE"], []), "VIK": (["RCL", "CCL", "NCLH"], []), "IBTA": (["CART", "TTD"], []), "RIVN": (["TSLA", "LCID"], ["AMZN", "F"]),
 "LINE": (["COLD", "PLD"], []), "SARO": (["HEI", "TDG", "FTAI"], []), "NXT": (["ARRY", "SHLS", "FSLR"], []), "VG": (["LNG", "NFE"], []),
 "SPCX": (["RKLB", "ASTS"], ["GOOGL", "DXYZ"]),
}
ANT = {"peers": ["NBIS", "CRWV", "ORCL", "NVDA", "AVGO", "PLTR", "MSFT"], "holders": ["AMZN", "GOOGL"]}
MKT = ["QQQ", "SPY", "IGV", "SMH", "ARKK"]

if __name__ == "__main__":
    json.dump({"peers": PEERS, "anthropic": ANT}, open(OUT / "map.json", "w"), indent=1)
    tick = sorted(set(PEERS) | {t for p, h in PEERS.values() for t in p + h} | set(ANT["peers"] + ANT["holders"]) | set(MKT))
    d = yf.download(tick, start="2019-06-01", end="2026-11-14", auto_adjust=True, progress=False, threads=False)
    d["Close"].to_csv(OUT / "daily_close.csv"); d["Open"].to_csv(OUT / "daily_open.csv")
    print("daily", d["Close"].shape, "missing:", [t for t in tick if d["Close"][t].dropna().empty])
    recent = [k for k in PEERS if k in "VG SAIL CRWV ETOR HNGE CRCL CHYM FIG KLAR FIGR GEMI STUB NTSK MDLN SPCX".split()]
    htick = sorted(set(recent) | {t for k in recent for t in PEERS[k][0] + PEERS[k][1]} | set(ANT["peers"] + ANT["holders"]) | set(MKT))
    frames = {}
    for t in htick:
        for k in range(3):
            try:
                h = yf.Ticker(t).history(period="730d", interval="60m", auto_adjust=True)
                if len(h): break
            except Exception as e:
                print(t, e)
            time.sleep(2)
        if h.empty:
            continue
        h.index = h.index.tz_convert("America/New_York")
        frames[t] = h[h.Volume > 0][["Open", "Close"]]
        time.sleep(0.3)
    H = pd.concat({t: f for t, f in frames.items()}, axis=1)
    H.to_pickle(OUT / "hourly.pkl")
    print("hourly", H.shape, "empty:", [t for t, f in frames.items() if f.empty])
