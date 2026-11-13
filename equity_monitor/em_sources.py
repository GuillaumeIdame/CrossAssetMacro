"""Data sources for the Equity Monitor. API only: yfinance, SEC EDGAR, OpenFIGI, MediaWiki.

Every record returned here carries `fetched_at` (UTC). Nothing is filled in: a value
the source does not give stays None and is rendered as "n/a" downstream.
"""

import os
import re
import time
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd
import requests
import yfinance as yf
from bs4 import BeautifulSoup

from em_common import HERE, now_iso, retry

yf.set_tz_cache_location(str(HERE / ".yf_cache"))


# --------------------------------------------------------------------------- Yahoo prices

def _closes_from_download(raw: pd.DataFrame, tickers):
    if raw is None or raw.empty:
        return pd.DataFrame()
    if isinstance(raw.columns, pd.MultiIndex):
        closes = raw["Close"] if "Close" in raw.columns.get_level_values(0) else pd.DataFrame()
    else:
        closes = raw[["Close"]].rename(columns={"Close": tickers[0]}) if "Close" in raw.columns else pd.DataFrame()
    closes = closes.copy()
    closes.index = pd.DatetimeIndex(closes.index).tz_localize(None).normalize()
    return closes


def download_closes(tickers, period, logger, symlog, source_tag="yfinance.download", batch_size=60, interval="1d"):
    """yf.download in batches, retry on error, then a second pass symbol by symbol for the misses.

    Returns (closes DataFrame [date x ticker], meta {ticker: {...}})."""
    tickers = list(dict.fromkeys(t for t in tickers if t))
    frames, meta = [], {}
    for i in range(0, len(tickers), batch_size):
        batch = tickers[i:i + batch_size]
        stamp = now_iso()
        try:
            raw = retry(lambda: yf.download(batch, period=period, interval=interval, auto_adjust=True,
                                            progress=False, threads=True, group_by="column"),
                        attempts=3, base_delay=3.0, logger=logger, what=f"download batch {i // batch_size + 1}")
            closes = _closes_from_download(raw, batch)
        except Exception as exc:  # noqa: BLE001
            logger.error("batch %d failed definitively: %s", i // batch_size + 1, exc)
            closes = pd.DataFrame()
        for t in batch:
            if t in closes.columns and closes[t].notna().sum() > 0:
                s = closes[t].dropna()
                frames.append(s.rename(t))
                meta[t] = {"fetched_at": stamp, "n_obs": int(len(s)), "first": str(s.index[0].date()),
                           "last_close_date": str(s.index[-1].date()), "status": "ok"}
            else:
                meta[t] = {"fetched_at": stamp, "n_obs": 0, "status": "missing"}
        time.sleep(0.5)

    # second pass, one by one, for anything the batch did not return
    missing = [t for t, m in meta.items() if m["status"] == "missing"]
    for t in missing:
        stamp = now_iso()
        try:
            raw = yf.download([t], period=period, interval=interval, auto_adjust=True, progress=False, threads=False,
                              group_by="column")
            closes = _closes_from_download(raw, [t])
            if t in closes.columns and closes[t].notna().sum() > 0:
                s = closes[t].dropna()
                frames.append(s.rename(t))
                meta[t] = {"fetched_at": stamp, "n_obs": int(len(s)), "first": str(s.index[0].date()),
                           "last_close_date": str(s.index[-1].date()), "status": "ok (retry)"}
            else:
                meta[t]["detail"] = "aucune donnee renvoyee par Yahoo"
        except Exception as exc:  # noqa: BLE001
            meta[t]["detail"] = str(exc)[:200]
        time.sleep(0.4)

    for t, m in meta.items():
        symlog.add(t, source_tag, "ok" if m["status"].startswith("ok") else "missing",
                   m.get("detail", f"{m.get('n_obs', 0)} obs, last {m.get('last_close_date', '—')}"), m["fetched_at"])
    if not frames:
        return pd.DataFrame(), meta
    closes = pd.concat(frames, axis=1).sort_index()
    return closes, meta


# --------------------------------------------------------------------------- Yahoo fundamentals

def _df_to_records(df):
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return None
    out = {}
    for idx, row in df.iterrows():
        out[str(idx)] = {str(k): (None if (isinstance(v, float) and np.isnan(v)) else (v.item() if hasattr(v, "item") else v))
                         for k, v in row.items()}
    return out


INFO_KEYS = [
    "longName", "shortName", "currency", "financialCurrency", "exchange", "exchangeTimezoneName", "sector", "industry", "quoteType",
    "marketCap", "enterpriseValue", "forwardPE", "trailingPE", "forwardEps", "trailingEps", "priceToSalesTrailing12Months",
    "enterpriseToEbitda", "enterpriseToRevenue", "freeCashflow", "operatingCashflow", "totalDebt", "totalCash", "ebitda",
    "totalRevenue", "revenueGrowth", "earningsGrowth", "earningsQuarterlyGrowth", "grossMargins", "operatingMargins",
    "profitMargins", "ebitdaMargins", "returnOnEquity", "returnOnAssets", "targetMeanPrice", "targetMedianPrice",
    "targetHighPrice", "targetLowPrice", "recommendationMean", "recommendationKey", "numberOfAnalystOpinions",
    "shortPercentOfFloat", "sharesShort", "shortRatio", "sharesShortPriorMonth", "beta", "dividendYield",
    "exDividendDate", "regularMarketPrice", "regularMarketTime", "fiftyTwoWeekHigh", "fiftyTwoWeekLow", "sharesOutstanding",
]


def fetch_fundamentals(ticker, logger, symlog):
    """info + analyst estimate tables + calendar + earnings history for one symbol. Each block logged."""
    t = yf.Ticker(ticker)
    out = {"ticker": ticker, "fetched_at": now_iso(), "blocks": {}}

    def block(name, fn):
        stamp = now_iso()
        try:
            val = fn()
            out["blocks"][name] = {"fetched_at": stamp, "status": "ok"}
            symlog.add(ticker, f"yfinance.{name}", "ok", "", stamp)
            return val
        except Exception as exc:  # noqa: BLE001
            out["blocks"][name] = {"fetched_at": stamp, "status": "error", "detail": str(exc)[:200]}
            symlog.add(ticker, f"yfinance.{name}", "error", exc, stamp)
            logger.warning("%s %s: %s", ticker, name, exc)
            return None

    info = block("info", lambda: t.info) or {}
    out["info"] = {k: info.get(k) for k in INFO_KEYS}
    out["earnings_estimate"] = _df_to_records(block("earnings_estimate", lambda: t.earnings_estimate))
    out["revenue_estimate"] = _df_to_records(block("revenue_estimate", lambda: t.revenue_estimate))
    out["eps_trend"] = _df_to_records(block("eps_trend", lambda: t.eps_trend))
    out["eps_revisions"] = _df_to_records(block("eps_revisions", lambda: t.eps_revisions))
    out["growth_estimates"] = _df_to_records(block("growth_estimates", lambda: t.growth_estimates))
    cal = block("calendar", lambda: t.calendar) or {}
    out["calendar"] = {k: ([str(x) for x in v] if isinstance(v, list) else (str(v) if hasattr(v, "year") else v))
                       for k, v in cal.items()}
    ed = block("earnings_dates", lambda: t.get_earnings_dates(limit=60))
    rows = []
    if ed is not None and not ed.empty:
        for idx, row in ed.iterrows():
            ts = pd.Timestamp(idx)
            rows.append({
                "datetime_local": ts.strftime("%Y-%m-%dT%H:%M"),
                "date": ts.strftime("%Y-%m-%d"),
                "hour_local": int(ts.hour),
                "eps_estimate": None if pd.isna(row.get("EPS Estimate")) else float(row.get("EPS Estimate")),
                "eps_reported": None if pd.isna(row.get("Reported EPS")) else float(row.get("Reported EPS")),
                "surprise_pct": None if pd.isna(row.get("Surprise(%)")) else float(row.get("Surprise(%)")),
            })
    out["earnings_dates"] = rows
    return out


# --------------------------------------------------------------------------- Yahoo options

def _mid_or_last(row):
    bid, ask, last = row.get("bid"), row.get("ask"), row.get("lastPrice")
    if bid is not None and ask is not None and bid > 0 and ask > 0:
        return float((bid + ask) / 2), "mid"
    if last is not None and not pd.isna(last) and last > 0:
        return float(last), "last"
    return None, None


def _bs_straddle(spot, strike, t_years, sigma):
    from math import erf, exp, log, sqrt
    if sigma <= 0 or t_years <= 0:
        return max(spot - strike, 0) + max(strike - spot, 0)
    d1 = (log(spot / strike) + 0.5 * sigma * sigma * t_years) / (sigma * sqrt(t_years))
    d2 = d1 - sigma * sqrt(t_years)
    N = lambda x: 0.5 * (1 + erf(x / sqrt(2)))
    call = spot * N(d1) - strike * N(d2)
    put = strike * N(-d2) - spot * N(-d1)
    return call + put


def implied_vol_from_straddle(spot, strike, t_years, straddle):
    """Bisection on Black-Scholes (r = 0, q = 0) so the ATM straddle matches its quoted price."""
    if not spot or not straddle or t_years <= 0:
        return None
    lo, hi = 0.01, 5.0
    if _bs_straddle(spot, strike, t_years, hi) < straddle:
        return None
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        if _bs_straddle(spot, strike, t_years, mid) > straddle:
            hi = mid
        else:
            lo = mid
    return 0.5 * (lo + hi)


def fetch_option_metrics(ticker, spot, earnings_date, earnings_timing, logger, symlog, max_days=75):
    """ATM straddle on the first expiry after the next earnings (implied move) and ATM IV near 30 days.

    earnings_timing: 'AMC', 'BMO' or None. For AMC the first usable expiry is strictly after the date."""
    stamp = now_iso()
    out = {"fetched_at": stamp, "implied_move": None, "implied_move_basis": None, "implied_move_expiry": None,
           "straddle": None, "atm_strike": None, "iv_30d": None, "iv_30d_expiry": None, "iv_30d_source": None, "iv_30d_basis": None, "note": None}
    try:
        t = yf.Ticker(ticker)
        expiries = list(t.options or [])
    except Exception as exc:  # noqa: BLE001
        out["note"] = f"chaine d'options indisponible : {str(exc)[:120]}"
        symlog.add(ticker, "yfinance.options", "error", exc, stamp)
        return out
    if not expiries or not spot:
        out["note"] = "pas d'options cotees sur Yahoo"
        symlog.add(ticker, "yfinance.options", "missing", out["note"], stamp)
        return out
    today = date.today()
    exp_dates = [datetime.strptime(e, "%Y-%m-%d").date() for e in expiries]

    def chain_atm(exp):
        oc = t.option_chain(exp.strftime("%Y-%m-%d"))
        calls, puts = oc.calls, oc.puts
        if calls.empty or puts.empty:
            return None
        strikes = sorted(set(calls["strike"]).intersection(set(puts["strike"])))
        if not strikes:
            return None
        k = min(strikes, key=lambda s: abs(s - spot))
        c = calls[calls["strike"] == k].iloc[0].to_dict()
        p = puts[puts["strike"] == k].iloc[0].to_dict()
        cp, cb = _mid_or_last(c)
        pp, pb = _mid_or_last(p)
        basis = "mid" if cb == "mid" and pb == "mid" else "last"
        t_years = max((exp - today).days, 0.5) / 365.0
        iv = implied_vol_from_straddle(spot, float(k), t_years, (cp or 0) + (pp or 0)) if cp and pp else None
        iv_source = "straddle ATM (BS, r=0)" if iv else None
        if iv is None and basis == "mid":  # live quotes: Yahoo's own IV is usable
            ivs = [v for v in (c.get("impliedVolatility"), p.get("impliedVolatility")) if v is not None and not pd.isna(v) and v > 0.01]
            iv = float(np.mean(ivs)) if ivs else None
            iv_source = "yfinance impliedVolatility" if iv else None
        return {"strike": float(k), "call": cp, "put": pp, "basis": basis, "iv": iv, "iv_source": iv_source}

    # implied move around earnings
    if earnings_date:
        ed = earnings_date if isinstance(earnings_date, date) else datetime.strptime(str(earnings_date)[:10], "%Y-%m-%d").date()
        if (ed - today).days <= max_days:
            cands = [e for e in exp_dates if (e > ed if earnings_timing == "AMC" else e >= ed)]
            if cands:
                exp = cands[0]
                try:
                    atm = chain_atm(exp)
                    if atm and atm["call"] and atm["put"]:
                        straddle = atm["call"] + atm["put"]
                        out.update({"implied_move": straddle / spot, "implied_move_basis": atm["basis"],
                                    "implied_move_expiry": exp.isoformat(), "straddle": straddle, "atm_strike": atm["strike"]})
                    else:
                        out["note"] = "straddle ATM sans prix (bid/ask/last nuls)"
                except Exception as exc:  # noqa: BLE001
                    out["note"] = f"chaine {exp}: {str(exc)[:100]}"
            else:
                out["note"] = "aucune echeance cotee apres la date de resultats"
        else:
            out["note"] = f"resultats a plus de {max_days} j : move implicite non calcule"
    # ATM IV closest to 30 calendar days
    try:
        target = today + timedelta(days=30)
        exp30 = min((e for e in exp_dates if e > today), key=lambda e: abs((e - target).days), default=None)
        if exp30:
            atm = chain_atm(exp30)
            if atm and atm["iv"]:
                out["iv_30d"] = atm["iv"]
                out["iv_30d_expiry"] = exp30.isoformat()
                out["iv_30d_source"] = atm["iv_source"]
                out["iv_30d_basis"] = atm["basis"]
    except Exception as exc:  # noqa: BLE001
        out["note"] = (out["note"] or "") + f" | IV30: {str(exc)[:80]}"
    symlog.add(ticker, "yfinance.options", "ok" if (out["implied_move"] or out["iv_30d"]) else "missing", out["note"] or "", stamp)
    return out


# --------------------------------------------------------------------------- SEC EDGAR 13F

class SecClient:
    """data.sec.gov / www.sec.gov with a declared User-Agent and a request budget below 10/s."""

    def __init__(self, user_agent, max_rps=8, logger=None):
        self.headers = {"User-Agent": user_agent, "Accept-Encoding": "gzip, deflate"}
        self.min_interval = 1.0 / max(1, max_rps)
        self._last = 0.0
        self.logger = logger
        self.calls = []

    def get(self, url, **kw):
        wait = self.min_interval - (time.time() - self._last)
        if wait > 0:
            time.sleep(wait)
        stamp = now_iso()
        r = requests.get(url, headers=self.headers, timeout=60, **kw)
        self._last = time.time()
        self.calls.append({"url": url, "status": r.status_code, "fetched_at": stamp})
        r.raise_for_status()
        return r

    def find_cik(self, filer_name):
        r = self.get("https://efts.sec.gov/LATEST/search-index", params={"q": f'"{filer_name}"', "forms": "13F-HR"})
        hits = r.json().get("hits", {}).get("hits", [])
        for h in hits:
            names = h["_source"].get("display_names", [])
            ciks = h["_source"].get("ciks", [])
            if names and ciks and filer_name.lower() in names[0].lower():
                return ciks[0].zfill(10), names[0]
        return None, None

    def submissions(self, cik):
        return self.get(f"https://data.sec.gov/submissions/CIK{cik.zfill(10)}.json").json()

    def list_13f(self, subs):
        rec = subs["filings"]["recent"]
        rows = []
        for form, acc, fdate, rdate, doc in zip(rec["form"], rec["accessionNumber"], rec["filingDate"],
                                                 rec["reportDate"], rec["primaryDocument"]):
            if form in ("13F-HR", "13F-HR/A"):
                rows.append({"form": form, "accession": acc, "filing_date": fdate, "period": rdate, "primary_doc": doc})
        rows.sort(key=lambda r: (r["period"], r["filing_date"]), reverse=True)
        return rows

    def info_table(self, cik, accession):
        folder = accession.replace("-", "")
        base = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{folder}/"
        idx = self.get(base + "index.json").json()
        names = [it["name"] for it in idx["directory"]["item"]]
        xmls = [n for n in names if n.lower().endswith(".xml") and "primary_doc" not in n.lower()]
        if not xmls:
            raise RuntimeError(f"no information table xml in {base}: {names}")
        url = base + xmls[0]
        xml_text = self.get(url).text
        return url, parse_info_table(xml_text)


def parse_info_table(xml_text):
    root = ET.fromstring(xml_text)
    ns_uri = root.tag.split("}")[0].strip("{") if "}" in root.tag else ""
    ns = {"n": ns_uri} if ns_uri else {}
    p = (lambda x: f"n:{x}") if ns_uri else (lambda x: x)
    rows = []
    for it in root.findall(p("infoTable"), ns):
        g = lambda path: (it.findtext("/".join(p(seg) for seg in path.split("/")), namespaces=ns) or "").strip()
        rows.append({
            "issuer": g("nameOfIssuer"), "class": g("titleOfClass"), "cusip": g("cusip").upper(),
            "value_usd": float(g("value") or 0), "shares": float(g("shrsOrPrnAmt/sshPrnamt") or 0),
            "sh_prn": g("shrsOrPrnAmt/sshPrnamtType"), "put_call": g("putCall"), "discretion": g("investmentDiscretion"),
        })
    return rows


EXCLUDED_CLASS_WORDS = ("NOTE", "DEBT", "BOND", "PFD", "PREF", "WT", "WARRANT", "UNIT", "RT", "RIGHT", "DBCV", "CONV")


def long_equity_positions(rows):
    """Long common-equity lines only: shares (not principal), no put/call, no debt/preferred/warrant classes."""
    out = {}
    for r in rows:
        if r["put_call"] or r["sh_prn"] != "SH":
            continue
        cls = r["class"].upper()
        if any(w in cls.split() or w in cls for w in EXCLUDED_CLASS_WORDS):
            continue
        key = r["cusip"]
        if key in out:
            out[key]["value_usd"] += r["value_usd"]
            out[key]["shares"] += r["shares"]
        else:
            out[key] = {k: r[k] for k in ("issuer", "class", "cusip", "value_usd", "shares")}
    return list(out.values())


# --------------------------------------------------------------------------- OpenFIGI

def map_cusips_openfigi(cusips, logger, api_key=None, cache=None):
    """CUSIP -> ticker. CINS (first character a letter) for non-US issuers. 10 jobs per request without key."""
    cache = cache or {}
    result = {c: cache[c] for c in cusips if c in cache and cache[c].get("ticker")}
    todo = [c for c in cusips if c not in result]
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["X-OPENFIGI-APIKEY"] = api_key
    chunk = 100 if api_key else 10
    calls = []
    for i in range(0, len(todo), chunk):
        batch = todo[i:i + chunk]
        jobs = [{"idType": "ID_CINS" if c[:1].isalpha() else "ID_CUSIP", "idValue": c} for c in batch]
        stamp = now_iso()
        try:
            r = retry(lambda: requests.post("https://api.openfigi.com/v3/mapping", json=jobs, headers=headers, timeout=60),
                      attempts=3, base_delay=5.0, logger=logger, what="openfigi")
            calls.append({"status": r.status_code, "fetched_at": stamp, "n": len(batch)})
            if r.status_code == 429:
                time.sleep(60)
                r = requests.post("https://api.openfigi.com/v3/mapping", json=jobs, headers=headers, timeout=60)
            r.raise_for_status()
            for c, job, res in zip(batch, jobs, r.json()):
                data = res.get("data") or []
                pick = _pick_figi(data)
                result[c] = {"ticker": pick.get("ticker") if pick else None, "name": pick.get("name") if pick else None,
                             "exchCode": pick.get("exchCode") if pick else None, "securityType": pick.get("securityType") if pick else None,
                             "idType": job["idType"], "fetched_at": stamp, "error": res.get("error") if not data else None}
        except Exception as exc:  # noqa: BLE001
            logger.error("openfigi batch failed: %s", exc)
            for c in batch:
                result[c] = {"ticker": None, "idType": None, "fetched_at": stamp, "error": str(exc)[:120]}
        time.sleep(2.6 if not api_key else 0.3)
    return result, calls


def _pick_figi(data):
    if not data:
        return None
    equity = [d for d in data if d.get("marketSector") == "Equity"]
    us = [d for d in equity if d.get("exchCode") in ("US", "UN", "UW", "UQ", "UA", "UR", "UP")]
    for pool in (us, equity, data):
        if pool:
            pool = sorted(pool, key=lambda d: 0 if d.get("securityType") in ("Common Stock", "ADR", "REIT", "Depositary Receipt") else 1)
            return pool[0]
    return None


def figi_ticker_to_yahoo(ticker):
    if not ticker:
        return None
    return ticker.replace("/", "-").replace(" ", "-")


# --------------------------------------------------------------------------- Wikipedia (MediaWiki API)

def _wiki_parse(page, user_agent, logger, attempts=6):
    url = "https://en.wikipedia.org/w/api.php"
    params = {"action": "parse", "page": page, "prop": "text|revid", "format": "json", "formatversion": 2, "redirects": 1}
    for i in range(attempts):
        stamp = now_iso()
        r = requests.get(url, params=params, headers={"User-Agent": user_agent}, timeout=60)
        if r.status_code == 429:
            wait = min(int(r.headers.get("Retry-After", "30")), 90) + 1
            logger.warning("wikipedia %s: 429, retry in %ss (%d/%d)", page, wait, i + 1, attempts)
            time.sleep(wait)
            continue
        r.raise_for_status()
        j = r.json()
        if "error" in j:
            raise RuntimeError(j["error"].get("info", "parse error"))
        return j["parse"]["text"], j["parse"].get("revid"), stamp
    raise RuntimeError(f"wikipedia {page}: rate limited after {attempts} attempts")


def _table_with_columns(html, needed):
    soup = BeautifulSoup(html, "lxml")
    best = None
    for tbl in soup.find_all("table"):
        rows = tbl.find_all("tr")
        if len(rows) < 20:
            continue
        hdr = [re.sub(r"\s*\[.*?\]\s*", "", th.get_text(" ", strip=True)).strip() for th in rows[0].find_all(["th", "td"])]
        if all(any(h.lower().startswith(n.lower()) for h in hdr) for n in needed):
            if best is None or len(rows) > len(best[1]):
                best = (hdr, rows[1:])
    return best


def _to_yahoo(sym, index_key, cfg, listing, suffix_map):
    sym = sym.strip().replace("​", "")
    sym = re.sub(r"\s*\[.*?\]", "", sym).strip()
    if not sym:
        return None
    if index_key in ("SPX", "NDX"):
        return sym.replace(".", "-")
    if index_key == "FTSE":
        base = sym.replace(".", "-").rstrip("-")
        return f"{base}.L"
    if "." in sym and sym.rsplit(".", 1)[1].isalpha() and len(sym.rsplit(".", 1)[1]) <= 2:
        return sym  # already Yahoo-formatted (ADS.DE, AI.PA, ASML.AS)
    if cfg.get("suffix"):
        return sym + cfg["suffix"]
    for key, suf in suffix_map.items():
        if listing and key.lower() in listing.lower():
            return sym + suf
    return None


def fetch_constituents(wcfg, logger):
    """Six index compositions via the MediaWiki parse API; tickers converted to Yahoo format."""
    out = {"fetched_at": now_iso(), "indices": {}, "unresolved": [], "errors": {}}
    for key, cfg in wcfg["pages"].items():
        try:
            html, revid, stamp = _wiki_parse(cfg["page"], wcfg["user_agent"], logger)
            needed = [cfg["ticker_col"], cfg["name_col"]]
            found = _table_with_columns(html, needed)
            if not found:
                raise RuntimeError(f"no table with columns {needed}")
            hdr, rows = found
            col = lambda name: next((i for i, h in enumerate(hdr) if h.lower().startswith(name.lower())), None)
            it, iname, isec = col(cfg["ticker_col"]), col(cfg["name_col"]), col(cfg.get("sector_col") or "")
            ilist = col(cfg["listing_col"]) if cfg.get("listing_col") else None
            members = []
            for tr in rows:
                cells = [td.get_text(" ", strip=True) for td in tr.find_all(["td", "th"])]
                if len(cells) <= max(it, iname):
                    continue
                raw = cells[it]
                listing = cells[ilist] if ilist is not None and ilist < len(cells) else None
                y = _to_yahoo(raw, key, cfg, listing, wcfg["listing_suffix"])
                rec = {"raw": raw, "yahoo": y, "name": cells[iname], "sector": cells[isec] if isec is not None and isec < len(cells) else None}
                if y:
                    members.append(rec)
                else:
                    out["unresolved"].append({"index": key, **rec})
            out["indices"][key] = {"page": cfg["page"], "revid": revid, "fetched_at": stamp, "members": members, "count": len(members)}
            logger.info("wikipedia %s: %d members", key, len(members))
        except Exception as exc:  # noqa: BLE001
            logger.error("wikipedia %s failed: %s", key, exc)
            out["errors"][key] = str(exc)[:200]
        time.sleep(1.5)
    return out
