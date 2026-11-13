"""Named series catalogue shared by the three apps.

Each entry: source (yahoo | fred), ticker, name, category, freq (d/w/m/q), mode
(price -> log changes, level -> differences), quality (live | proxy), and the app(s) that use it.
Keeping it in one place means the Data pages of all apps show the same provenance.
"""

from typing import Dict, List

CATALOGUE: Dict[str, dict] = {}


def _add(key, source, ticker, name, category, freq="d", mode="price", quality="live", apps=("cb", "fx", "th"), note=""):
    CATALOGUE[key] = dict(key=key, source=source, ticker=ticker, name=name, category=category,
                          freq=freq, mode=mode, quality=quality, apps=tuple(apps), note=note)


# --- FX spot (Yahoo convention: XXX=X is USD per XXX for EUR/GBP/AUD/NZD, else XXX per USD) ---
for k, t, n in [("eurusd", "EURUSD=X", "EUR/USD"), ("gbpusd", "GBPUSD=X", "GBP/USD"), ("usdjpy", "JPY=X", "USD/JPY"),
                ("usdchf", "CHF=X", "USD/CHF"), ("usdcad", "CAD=X", "USD/CAD"), ("audusd", "AUDUSD=X", "AUD/USD"),
                ("nzdusd", "NZDUSD=X", "NZD/USD"), ("usdsek", "SEK=X", "USD/SEK"), ("usdnok", "NOK=X", "USD/NOK"),
                ("usdmxn", "MXN=X", "USD/MXN"), ("usdzar", "ZAR=X", "USD/ZAR"), ("usdcny", "CNY=X", "USD/CNY"),
                ("usdbrl", "BRL=X", "USD/BRL"), ("usdinr", "INR=X", "USD/INR"), ("usdkrw", "KRW=X", "USD/KRW"),
                ("eurjpy", "EURJPY=X", "EUR/JPY"), ("eurgbp", "EURGBP=X", "EUR/GBP"), ("eurchf", "EURCHF=X", "EUR/CHF"),
                ("audjpy", "AUDJPY=X", "AUD/JPY"), ("cadjpy", "CADJPY=X", "CAD/JPY"), ("dxy", "DX-Y.NYB", "US Dollar Index")]:
    _add(k, "yahoo", t, n, "fx", apps=("fx", "th", "cb"))

# --- Equities / credit / commodities / vol ---
for k, t, n, c in [("spx", "^GSPC", "S&P 500", "equity"), ("ndx", "^NDX", "Nasdaq 100", "equity"), ("rut", "^RUT", "Russell 2000", "equity"),
                   ("sx5e", "^STOXX50E", "Euro Stoxx 50", "equity"), ("dax", "^GDAXI", "DAX", "equity"), ("ftse", "^FTSE", "FTSE 100", "equity"),
                   ("nikkei", "^N225", "Nikkei 225", "equity"), ("eem", "EEM", "EM equities", "equity"), ("spy", "SPY", "SPY", "equity"),
                   ("qqq", "QQQ", "QQQ", "equity"), ("iwm", "IWM", "IWM", "equity"), ("xli", "XLI", "Industrials", "equity"),
                   ("xlp", "XLP", "Staples", "equity"), ("xly", "XLY", "Cons. discretionary", "equity"), ("xle", "XLE", "Energy", "equity"),
                   ("xlf", "XLF", "Financials", "equity"), ("ita", "ITA", "Defence", "equity"), ("kre", "KRE", "Regional banks", "equity"),
                   ("hyg", "HYG", "US HY", "credit"), ("lqd", "LQD", "US IG", "credit"), ("jnk", "JNK", "HY (JNK)", "credit"),
                   ("emb", "EMB", "EM USD sovereign", "credit"), ("tlt", "TLT", "20Y+ UST", "rates"), ("ief", "IEF", "7-10Y UST", "rates"),
                   ("shy", "SHY", "1-3Y UST", "rates"), ("tip", "TIP", "TIPS", "rates"), ("bndx", "BNDX", "Intl bonds (hedged)", "rates"),
                   ("wti", "CL=F", "WTI", "commodity"), ("brent", "BZ=F", "Brent", "commodity"), ("gold", "GC=F", "Gold", "commodity"),
                   ("copper", "HG=F", "Copper", "commodity"), ("silver", "SI=F", "Silver", "commodity"), ("natgas", "NG=F", "Henry Hub", "commodity"),
                   ("gasoline", "RB=F", "RBOB", "commodity"), ("wheat", "ZW=F", "Wheat", "commodity"), ("btc", "BTC-USD", "Bitcoin", "crypto"),
                   ("zt", "ZT=F", "2Y UST future", "rates_fut"), ("zf", "ZF=F", "5Y UST future", "rates_fut"), ("zn", "ZN=F", "10Y UST future", "rates_fut"),
                   ("zb", "ZB=F", "30Y UST future", "rates_fut"), ("es", "ES=F", "S&P e-mini", "equity_fut"), ("zq_front", "ZQ=F", "Fed funds (front)", "stir"),
                   ("sr3_front", "SR3=F", "3M SOFR (front)", "stir")]:
    _add(k, "yahoo", t, n, c)

for k, t, n in [("vix", "^VIX", "VIX"), ("vix3m", "^VIX3M", "VIX 3M"), ("vix9d", "^VIX9D", "VIX 9D"), ("vvix", "^VVIX", "VVIX"),
                ("move", "^MOVE", "MOVE"), ("ovx", "^OVX", "Oil VIX"), ("gvz", "^GVZ", "Gold VIX"), ("skew", "^SKEW", "CBOE SKEW")]:
    _add(k, "yahoo", t, n, "vol", mode="level")

# --- FRED: rates & policy ---
for k, t, n in [("ust1m", "DGS1MO", "UST 1M"), ("ust3m", "DGS3MO", "UST 3M"), ("ust6m", "DGS6MO", "UST 6M"), ("ust1", "DGS1", "UST 1Y"),
                ("ust2", "DGS2", "UST 2Y"), ("ust3", "DGS3", "UST 3Y"), ("ust5", "DGS5", "UST 5Y"), ("ust7", "DGS7", "UST 7Y"),
                ("ust10", "DGS10", "UST 10Y"), ("ust20", "DGS20", "UST 20Y"), ("ust30", "DGS30", "UST 30Y"),
                ("real5", "DFII5", "5Y TIPS real"), ("real10", "DFII10", "10Y TIPS real"), ("bei5", "T5YIE", "5Y breakeven"),
                ("bei10", "T10YIE", "10Y breakeven"), ("fwd5y5y", "T5YIFR", "5y5y forward inflation"),
                ("tp10", "THREEFYTP10", "ACM 10Y term premium"), ("acm1", "THREEFY1", "ACM 1Y fitted yield"), ("acm2", "THREEFY2", "ACM 2Y fitted yield"),
                ("effr", "EFFR", "Effective fed funds"), ("sofr", "SOFR", "SOFR"), ("iorb", "IORB", "IORB"),
                ("fft_upper", "DFEDTARU", "Fed target upper"), ("fft_lower", "DFEDTARL", "Fed target lower"),
                ("ecb_dfr", "ECBDFR", "ECB deposit rate"), ("ecb_mro", "ECBMRRFR", "ECB MRO"), ("estr", "ECBESTRVOLWGTTRMDMNRT", "€STR"),
                ("sonia", "IUDSOIA", "SONIA"), ("tbill3m", "DTB3", "3M T-bill"), ("tbill6m", "DTB6", "6M T-bill")]:
    _add(k, "fred", t, n, "rates", mode="level")

# --- FRED: credit, conditions, liquidity ---
for k, t, n, c, f in [("hy_oas", "BAMLH0A0HYM2", "US HY OAS", "credit", "d"), ("ig_oas", "BAMLC0A0CM", "US IG OAS", "credit", "d"),
                      ("eu_hy_oas", "BAMLHE00EHYIOAS", "Euro HY OAS", "credit", "d"), ("nfci", "NFCI", "Chicago Fed NFCI", "conditions", "w"),
                      ("anfci", "ANFCI", "Adjusted NFCI", "conditions", "w"), ("stlfsi", "STLFSI4", "St Louis Fed stress", "conditions", "w"),
                      ("walcl", "WALCL", "Fed balance sheet", "liquidity", "w"), ("tga", "WTREGEN", "Treasury General Account", "liquidity", "w"),
                      ("rrp", "RRPONTSYD", "ON RRP", "liquidity", "d"), ("cpff", "CPFF", "CP - fed funds spread", "liquidity", "d"),
                      ("vixcls", "VIXCLS", "VIX (FRED)", "vol", "d"), ("vxvcls", "VXVCLS", "VIX 3M (FRED)", "vol", "d")]:
    _add(k, "fred", t, n, c, freq=f, mode="level")

# --- FRED: US macro releases (monthly/weekly) ---
for k, t, n, c, f in [("cpi", "CPIAUCSL", "US CPI", "inflation", "m"), ("core_cpi", "CPILFESL", "US core CPI", "inflation", "m"),
                      ("pce", "PCEPI", "US PCE", "inflation", "m"), ("core_pce", "PCEPILFE", "US core PCE", "inflation", "m"),
                      ("mich_infl", "MICH", "UMich 1Y inflation expectations", "inflation", "m"),
                      ("unrate", "UNRATE", "US unemployment", "labour", "m"), ("payems", "PAYEMS", "US payrolls", "labour", "m"),
                      ("claims", "ICSA", "Initial claims", "labour", "w"), ("cont_claims", "CCSA", "Continuing claims", "labour", "w"),
                      ("jolts", "JTSJOL", "JOLTS openings", "labour", "m"), ("quits", "JTSQUR", "JOLTS quits rate", "labour", "m"),
                      ("ahe", "CES0500000003", "Avg hourly earnings", "labour", "m"), ("hours", "AWHAETP", "Avg weekly hours", "labour", "m"),
                      ("partic", "CIVPART", "Participation rate", "labour", "m"),
                      ("indpro", "INDPRO", "Industrial production", "growth", "m"), ("retail", "RSAFS", "Retail sales", "growth", "m"),
                      ("retail_core", "RSXFS", "Retail sales ex autos", "growth", "m"), ("gdpnow", "GDPNOW", "Atlanta Fed GDPNow", "growth", "q"),
                      ("gdp", "GDPC1", "Real GDP", "growth", "q"), ("houst", "HOUST", "Housing starts", "growth", "m"),
                      ("permit", "PERMIT", "Building permits", "growth", "m"), ("umcsent", "UMCSENT", "UMich sentiment", "growth", "m"),
                      ("manemp", "MANEMP", "Manufacturing employment", "labour", "m"), ("sloos_ci", "DRTSCILM", "SLOOS C&I tightening", "conditions", "q"),
                      ("mortgage30", "MORTGAGE30US", "30Y mortgage rate", "conditions", "w")]:
    _add(k, "fred", t, n, c, freq=f, mode="level", apps=("cb", "th"))

# --- FRED: euro area, UK, Japan (mostly monthly OECD/Eurostat mirrors; lagging) ---
for k, t, n, c, f, q in [("ea_hicp", "CP0000EZ19M086NEST", "Euro area HICP index", "inflation", "m", "live"),
                         ("ea_unemp", "LRHUTTTTEZM156S", "Euro area unemployment", "labour", "m", "proxy"),
                         ("ea_3m", "IR3TIB01EZM156N", "Euro area 3M rate", "rates", "m", "proxy"),
                         ("de_10y", "IRLTLT01DEM156N", "Germany 10Y", "rates", "m", "proxy"), ("fr_10y", "IRLTLT01FRM156N", "France 10Y", "rates", "m", "proxy"),
                         ("it_10y", "IRLTLT01ITM156N", "Italy 10Y", "rates", "m", "proxy"), ("uk_10y", "IRLTLT01GBM156N", "UK 10Y", "rates", "m", "proxy"),
                         ("jp_10y", "IRLTLT01JPM156N", "Japan 10Y", "rates", "m", "proxy"), ("uk_unemp", "LRHUTTTTGBM156S", "UK unemployment", "labour", "m", "proxy"),
                         ("jp_unemp", "LRHUTTTTJPM156S", "Japan unemployment", "labour", "m", "proxy"), ("uk_3m", "IR3TIB01GBM156N", "UK 3M rate", "rates", "m", "proxy"),
                         ("jp_3m", "IR3TIB01JPM156N", "Japan 3M rate", "rates", "m", "proxy"), ("jp_policy", "IRSTCI01JPM156N", "Japan call rate", "rates", "m", "proxy"),
                         ("uk_policy_m", "IRSTCI01GBM156N", "UK overnight (monthly)", "rates", "m", "proxy"),
                         ("ea_bus_conf", "BSCICP02EZM460S", "EA business confidence", "growth", "m", "proxy")]:
    _add(k, "fred", t, n, c, freq=f, mode="level", quality=q, apps=("cb", "fx", "th"))

# --- FRED: BIS REER (monthly) and FRB FX ---
for k, t, n in [("reer_us", "RBUSBIS", "REER US"), ("reer_ea", "RBXMBIS", "REER euro area"), ("reer_uk", "RBGBBIS", "REER UK"),
                ("reer_jp", "RBJPBIS", "REER Japan"), ("reer_ch", "RBCHBIS", "REER Switzerland"), ("reer_au", "RBAUBIS", "REER Australia"),
                ("reer_ca", "RBCABIS", "REER Canada")]:
    _add(k, "fred", t, n, "fx_value", freq="m", mode="price", apps=("fx",))
_add("usd_broad", "fred", "DTWEXBGS", "Broad USD index (Fed)", "fx", mode="price", apps=("fx", "th"))
_add("usd_afe", "fred", "DTWEXAFEGS", "USD vs advanced economies (Fed)", "fx", mode="price", apps=("fx",))
_add("brent_fred", "fred", "DCOILBRENTEU", "Brent (FRED)", "commodity", apps=("th",))


def by_app(app: str) -> List[dict]:
    return [v for v in CATALOGUE.values() if app in v["apps"]]


def yahoo_tickers(keys: List[str]) -> Dict[str, str]:
    return {k: CATALOGUE[k]["ticker"] for k in keys if CATALOGUE[k]["source"] == "yahoo"}


def fred_ids(keys: List[str]) -> Dict[str, str]:
    return {k: CATALOGUE[k]["ticker"] for k in keys if CATALOGUE[k]["source"] == "fred"}
