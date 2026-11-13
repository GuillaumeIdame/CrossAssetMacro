"""Equity Monitor — daily refresh. Writes the JSON sources of the dashboard.

Usage:  py -3.13 update_monitor.py [--skip-breadth] [--skip-options] [--skip-13f] [--skip-wiki]

Files written to "Sources du dashboard/":
  universe.json, prices.json, quotes.json, events.json, breadth.json, constituents.json,
  sa_13f.json, risk.json, run_status.json and data.js (bundle for file:// use of index.html).
"""

import argparse
import json
import os
import sys
import time
import traceback
from datetime import date, datetime, timedelta, timezone

import numpy as np
import pandas as pd

from em_common import SymbolLog, load_config, now_iso, output_dir, read_json, setup_logging, write_json, today_utc
from em_metrics import (TRADING_DAYS, beta_block, breadth_block, correlation_matrix, earnings_reactions, f,
                        horizon_return, idio_contribution, market_stats, mean_reversion_signal, momentum_signal,
                        next_13f_deadline, option_expiries, percentile_of_last, realized_vol, timing_from_hour, to_usd)
from em_sources import (SecClient, download_closes, fetch_constituents, fetch_fundamentals, fetch_option_metrics,
                        figi_ticker_to_yahoo, long_equity_positions, map_cusips_openfigi)


def previous_weekday(d: date) -> date:
    d = d - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


class MonitorRun:
    def __init__(self, args):
        self.args = args
        self.cfg = load_config()
        self.out = output_dir(self.cfg)
        self.started = now_iso()
        self.run_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        self.log = setup_logging(self.run_id)
        self.symlog = SymbolLog()
        self.steps = {}
        self.errors = []
        self.today = today_utc()
        self.expected_close = previous_weekday(self.today)

    # ------------------------------------------------------------------ step runner
    def step(self, name, fn, critical=False):
        t0 = time.time()
        self.steps[name] = {"status": "running", "started_at": now_iso()}
        self.log.info("=== %s", name)
        try:
            res = fn()
            self.steps[name].update({"status": "ok", "finished_at": now_iso(), "seconds": round(time.time() - t0, 1)})
            return res
        except Exception as exc:  # noqa: BLE001
            tb = traceback.format_exc()
            self.log.error("%s FAILED: %s\n%s", name, exc, tb)
            self.steps[name].update({"status": "error", "finished_at": now_iso(), "seconds": round(time.time() - t0, 1),
                                     "error": str(exc)[:300]})
            self.errors.append({"step": name, "error": str(exc)[:300], "at": now_iso()})
            if critical:
                raise
            return None

    # ------------------------------------------------------------------ 13F
    def run_13f(self):
        scfg = self.cfg["sec"]
        prev = read_json(self.out / "sa_13f.json") or {}
        if self.args.skip_13f and prev:
            self.log.info("13F skipped, reusing previous file")
            return prev
        sec = SecClient(scfg["user_agent"], scfg.get("max_requests_per_second", 8), self.log)
        cik = scfg.get("cik")
        name = scfg["filer_name"]
        if not cik:
            cik, name = sec.find_cik(name)
            if not cik:
                raise RuntimeError(f"CIK introuvable pour {scfg['filer_name']} via efts.sec.gov")
        subs = sec.submissions(cik)
        filings = sec.list_13f(subs)
        if not filings:
            raise RuntimeError("aucun 13F-HR dans les soumissions")
        latest = filings[0]
        url, rows = sec.info_table(cik, latest["accession"])
        longs = long_equity_positions(rows)
        total = sum(p["value_usd"] for p in longs) or 1.0
        # previous quarter for changes
        prior = next((fl for fl in filings if fl["period"] < latest["period"]), None)
        prior_pos = {}
        if prior:
            try:
                _, prow = sec.info_table(cik, prior["accession"])
                prior_pos = {p["cusip"]: p for p in long_equity_positions(prow)}
            except Exception as exc:  # noqa: BLE001
                self.log.warning("prior 13F unreadable: %s", exc)
        # CUSIP -> ticker (OpenFIGI), with cache from the previous file
        cache = {p["cusip"]: {"ticker": p.get("figi_ticker"), "name": p.get("figi_name"), "exchCode": p.get("figi_exch"),
                              "securityType": p.get("figi_type"), "idType": p.get("figi_idtype"), "fetched_at": p.get("figi_fetched_at")}
                 for p in prev.get("positions", []) if p.get("figi_ticker")}
        api_key = os.environ.get(scfg.get("openfigi_api_key_env", "OPENFIGI_API_KEY")) or None
        mapping, figi_calls = map_cusips_openfigi([p["cusip"] for p in longs], self.log, api_key=api_key, cache=cache)
        positions = []
        for p in sorted(longs, key=lambda x: -x["value_usd"]):
            m = mapping.get(p["cusip"], {})
            yahoo = figi_ticker_to_yahoo(m.get("ticker"))
            pp = prior_pos.get(p["cusip"])
            if pp is None:
                change = "nouvelle"
            elif p["shares"] > pp["shares"] * 1.001:
                change = "renforcée"
            elif p["shares"] < pp["shares"] * 0.999:
                change = "allégée"
            else:
                change = "inchangée"
            positions.append({
                **p, "weight": p["value_usd"] / total, "yahoo": yahoo, "figi_ticker": m.get("ticker"), "figi_name": m.get("name"),
                "figi_exch": m.get("exchCode"), "figi_type": m.get("securityType"), "figi_idtype": m.get("idType"),
                "figi_fetched_at": m.get("fetched_at"), "figi_error": m.get("error"),
                "change_vs_prior": change, "prior_shares": pp["shares"] if pp else None,
                "shares_change_pct": f(p["shares"] / pp["shares"] - 1) if pp and pp["shares"] else None,
            })
            self.symlog.add(p["cusip"], "openfigi", "ok" if yahoo else "missing", f"{p['issuer']} -> {yahoo}", m.get("fetched_at"))
        exited = [{"issuer": v["issuer"], "cusip": k, "prior_value_usd": v["value_usd"]} for k, v in prior_pos.items()
                  if k not in {p["cusip"] for p in longs}]
        derivatives = [r for r in rows if r["put_call"]]
        return {
            "generated_at": now_iso(), "filer": name, "cik": cik,
            "filing": {**latest, "info_table_url": url, "fetched_at": now_iso()},
            "prior_filing": prior,
            "total_long_equity_usd": total, "n_positions": len(positions),
            "positions": positions, "exited_since_prior": exited,
            "derivative_lines_excluded": [{k: r[k] for k in ("issuer", "class", "put_call", "value_usd")} for r in derivatives],
            "all_filings": filings,
            "sec_calls": sec.calls, "openfigi_calls": figi_calls,
            "note": "Positions longues en actions (SH, sans put/call, sans dette/preferred/warrants). Poids = valeur / total actions longues. "
                    "Le 13F est publie jusqu'a 45 jours apres la fin du trimestre : les positions datent de la periode indiquee.",
        }

    # ------------------------------------------------------------------ Wikipedia
    def run_constituents(self):
        prev = read_json(self.out / "constituents.json")
        if self.args.skip_wiki and prev:
            self.log.info("wikipedia skipped, reusing previous file")
            prev["reused_from_previous_run"] = True
            return prev
        res = fetch_constituents(self.cfg["wikipedia"], self.log)
        res["generated_at"] = now_iso()
        # fall back index by index to the previous file where this run failed
        if prev:
            for key, err in res["errors"].items():
                if key in prev.get("indices", {}):
                    res["indices"][key] = {**prev["indices"][key], "reused_from_previous_run": True, "reuse_reason": err}
                    self.log.warning("%s: previous composition reused (%s)", key, err)
        for key, idx in res["indices"].items():
            self.symlog.add(f"wikipedia:{key}", "mediawiki.parse", "ok" if not idx.get("reused_from_previous_run") else "stale",
                            f"{idx['count']} tickers", idx.get("fetched_at"))
        return res

    # ------------------------------------------------------------------ universe
    def build_universe(self, sa13f):
        cfg = self.cfg
        symbols, groups = {}, {}
        for key, ix in cfg["indices"].items():
            symbols[ix["ticker"]] = {"key": key, "name": ix["name"], "type": "index", "group": "Indices", "currency": ix["currency"], "proxy": ix.get("proxy")}
        groups["Indices"] = [ix["ticker"] for ix in cfg["indices"].values()]
        for key, fx in cfg["fx"].items():
            symbols[fx["ticker"]] = {"key": key, "name": fx["name"], "type": "fx", "group": "FX", "currency": "USD"}
        groups["FX"] = [fx["ticker"] for fx in cfg["fx"].values()]
        groups["Vol"] = []
        for key, v in cfg["implied_vol"].items():
            if v["ticker"]:
                symbols[v["ticker"]] = {"key": key, "name": v["name"], "type": "vol", "group": "Vol", "currency": "pts", "index": v["index"]}
                groups["Vol"].append(v["ticker"])
        for gname, tickers in cfg["stock_groups"].items():
            groups[gname] = list(tickers)
            for t in tickers:
                symbols[t] = {"key": t, "name": t, "type": "stock", "group": gname, "currency": "USD"}
        sa_group = "13F Situational Awareness"
        groups[sa_group] = []
        for p in (sa13f or {}).get("positions", []):
            y = p.get("yahoo")
            if not y:
                continue
            if y in symbols:  # overlap with Mag7+AMD: keep the first group, record the weight
                symbols[y]["weight_13f"] = p["weight"]
                continue
            symbols[y] = {"key": y, "name": p.get("figi_name") or p["issuer"], "type": "stock", "group": sa_group, "currency": "USD",
                          "weight_13f": p["weight"], "cusip": p["cusip"], "change_13f": p["change_vs_prior"]}
            groups[sa_group].append(y)
        groups["ETFs"] = []
        for e in cfg["etfs"]:
            symbols[e["ticker"]] = {"key": e["ticker"], "name": f"{e['name']} — {e['line']}", "type": "etf", "group": "ETFs", "currency": None,
                                    "underlying": e["underlying"], "line": e["line"], "held": e.get("held", True)}
            groups["ETFs"].append(e["ticker"])
        return {"generated_at": now_iso(), "groups": groups, "symbols": symbols,
                "index_keys": {k: v["ticker"] for k, v in cfg["indices"].items()},
                "fx_keys": {k: v["ticker"] for k, v in cfg["fx"].items()},
                "note_13f": "Panier issu du dernier 13F-HR de Situational Awareness LP (sa_13f.json), jamais code en dur."}

    # ------------------------------------------------------------------ prices
    def run_prices(self, universe):
        tickers = list(universe["symbols"].keys())
        closes, meta = download_closes(tickers, f"{self.cfg['history_years']}y", self.log, self.symlog, batch_size=40)
        # currencies from fast_info for ETFs (GBp vs GBP matters)
        import yfinance as yf
        for t, s in universe["symbols"].items():
            if s["type"] == "etf":
                stamp = now_iso()
                try:
                    cur = yf.Ticker(t).fast_info.get("currency")
                    s["currency"] = cur
                    self.symlog.add(t, "yfinance.fast_info", "ok", f"currency={cur}", stamp)
                except Exception as exc:  # noqa: BLE001
                    s["currency"] = "GBp" if t.endswith(".L") else "EUR"
                    self.symlog.add(t, "yfinance.fast_info", "error", f"{exc}; devise supposee {s['currency']}", stamp)
        payload = {"generated_at": now_iso(), "period": f"{self.cfg['history_years']}y", "interval": "1d", "adjusted": True,
                   "expected_last_close": self.expected_close.isoformat(), "symbols": {}}
        for t in tickers:
            m = meta.get(t, {"status": "missing", "fetched_at": now_iso()})
            if t in closes.columns:
                s = closes[t].dropna()
                last = s.index[-1].date()
                payload["symbols"][t] = {
                    "currency": universe["symbols"][t].get("currency"), "fetched_at": m["fetched_at"], "n_obs": int(len(s)),
                    "dates": [d.strftime("%Y-%m-%d") for d in s.index], "close": [round(float(v), 6) for v in s.values],
                    "last_close_date": last.isoformat(), "stale": last < self.expected_close,
                    "stale_note": None if last >= self.expected_close else f"derniere cloture {last} < attendue {self.expected_close} (jour ferie ou donnee manquante)",
                }
            else:
                payload["symbols"][t] = {"currency": universe["symbols"][t].get("currency"), "fetched_at": m["fetched_at"], "n_obs": 0,
                                         "dates": [], "close": [], "last_close_date": None, "stale": True, "stale_note": m.get("detail", "aucune donnee")}
        return closes, payload

    # ------------------------------------------------------------------ fundamentals
    def run_fundamentals(self, universe):
        out = {}
        stocks = [t for t, s in universe["symbols"].items() if s["type"] == "stock"]
        for i, t in enumerate(stocks):
            self.log.info("fundamentals %s (%d/%d)", t, i + 1, len(stocks))
            out[t] = fetch_fundamentals(t, self.log, self.symlog)
            time.sleep(0.3)
        return out

    # ------------------------------------------------------------------ options
    def run_options(self, universe, fundamentals, closes, upcoming):
        out = {}
        if self.args.skip_options:
            return out
        for t, s in universe["symbols"].items():
            if s["type"] != "stock" or t not in closes.columns:
                continue
            spot = float(closes[t].dropna().iloc[-1])
            up = upcoming.get(t) or {}
            out[t] = fetch_option_metrics(t, spot, up.get("date"), up.get("timing"), self.log, self.symlog)
            time.sleep(0.3)
        return out

    # ------------------------------------------------------------------ breadth
    def run_breadth(self, constituents, closes, universe):
        if self.args.skip_breadth:
            prev = read_json(self.out / "breadth.json")
            if prev:
                prev["reused_from_previous_run"] = True
                return prev, {}
        mag7 = set(self.cfg["mag7"])
        all_members = []
        for key, idx in constituents.get("indices", {}).items():
            all_members += [m["yahoo"] for m in idx["members"] if m.get("yahoo")]
        all_members = list(dict.fromkeys(all_members))
        sub_log = SymbolLog()
        cons_closes, meta = download_closes(all_members, "1y", self.log, sub_log, source_tag="yfinance.download(constituents)", batch_size=60)
        missing = [t for t, m in meta.items() if not m["status"].startswith("ok")]
        self.log.info("constituents: %d requested, %d with prices, %d missing", len(all_members), len(cons_closes.columns), len(missing))
        res = {"generated_at": now_iso(), "fetched_at": now_iso(), "window": "1y", "indices": {}, "unresolved_on_yahoo": missing,
               "survivorship_note": "Compositions actuelles (Wikipedia) appliquees a tout l'historique : les sortants ne sont pas dans l'echantillon, "
                                    "ce qui flatte les mesures de largeur (biais de survie).",
               "constituent_log": meta}
        for key, idx in constituents.get("indices", {}).items():
            members = [m["yahoo"] for m in idx["members"] if m.get("yahoo") and m["yahoo"] in cons_closes.columns]
            ix_ticker = self.cfg["indices"][key]["ticker"]
            ix_close = closes[ix_ticker] if ix_ticker in closes.columns else None
            block = breadth_block(cons_closes[members], ix_close)
            block["members_total"] = idx["count"]
            block["members_missing"] = [m["yahoo"] for m in idx["members"] if m.get("yahoo") and m["yahoo"] not in cons_closes.columns]
            block["composition_fetched_at"] = idx.get("fetched_at")
            block["composition_reused"] = bool(idx.get("reused_from_previous_run"))
            if key in ("SPX", "NDX"):
                m7 = [t for t in members if t in mag7]
                rest = [t for t in members if t not in mag7]
                if m7 and rest:
                    r1 = lambda cols, n: f((cons_closes[cols].iloc[-1] / cons_closes[cols].iloc[-1 - n] - 1).mean()) if len(cons_closes) > n else None
                    block["mag7_vs_rest"] = {"mag7_ew_1m": r1(m7, 21), "rest_ew_1m": r1(rest, 21), "mag7_ew_3m": r1(m7, 63), "rest_ew_3m": r1(rest, 63),
                                             "mag7_members": m7, "n_rest": len(rest)}
            res["indices"][key] = block
        return res, cons_closes

    # ------------------------------------------------------------------ assembly
    def assemble(self, universe, closes, prices_payload, fundamentals, sa13f, constituents):
        cfg = self.cfg
        syms = universe["symbols"]
        fx = pd.DataFrame({k: closes[v] for k, v in universe["fx_keys"].items() if v in closes.columns}).ffill()
        usd = {}
        for t, s in syms.items():
            if t in closes.columns and s["type"] in ("stock", "etf", "index"):
                usd[t] = to_usd(closes[t], s.get("currency") or "USD", fx)
        spx = closes[universe["index_keys"]["SPX"]]
        ndx = closes[universe["index_keys"]["NDX"]]
        sox_t = universe["index_keys"]["SOX"]
        sox = closes[sox_t] if sox_t in closes.columns else usd.get(cfg["indices"]["SOX"].get("proxy"))
        sox_label = sox_t if sox_t in closes.columns else f"{cfg['indices']['SOX'].get('proxy')} (USD, proxy)"
        sx5e_usd = usd.get(universe["index_keys"]["SX5E"])
        spx_r = {h: horizon_return(spx, n) for h, n in TRADING_DAYS.items()}

        quotes = {"generated_at": now_iso(), "stocks": {}, "indices": {}, "etfs": {}, "fx": {}, "notes": {}}
        risk = {"generated_at": now_iso(), "betas": {}, "vol": {"indices": {}, "stocks": {}}, "correlations": {}, "signals": {}, "thresholds": cfg["signals"],
                "vol_thresholds": cfg["vol_thresholds"], "sox_benchmark": sox_label}
        events = {"generated_at": now_iso(), "today": self.today.isoformat(), "upcoming": {}, "reactions": {}, "calendar": []}
        upcoming = {}

        # ---- stocks
        for t, s in syms.items():
            if s["type"] != "stock":
                continue
            fd = fundamentals.get(t) or {}
            info = fd.get("info") or {}
            row = {"ticker": t, "name": info.get("longName") or s["name"], "group": s["group"], "currency": "USD",
                   "sector": info.get("sector"), "industry": info.get("industry"), "fetched_at": fd.get("fetched_at"), "sources": fd.get("blocks", {})}
            if t in closes.columns:
                row["market"] = market_stats(closes[t])
                row["market"]["stale"] = prices_payload["symbols"][t]["stale"]
                b = {"SPX": beta_block(usd[t], spx), "NDX": beta_block(usd[t], ndx)}
                if sox is not None:
                    b["SOX"] = beta_block(usd[t], sox)
                risk["betas"][t] = b
                beta1y = b["SPX"]["beta_1y"]
                row["beta_spx_1y"] = beta1y
                row["idio"] = {"1m": idio_contribution(usd[t], spx, beta1y, 21), "3m": idio_contribution(usd[t], spx, beta1y, 63)}
                row["market"]["idio_1m"] = row["idio"]["1m"]["idio_part"]
                row["market"]["idio_1d"] = f(row["market"]["r_1d"] - beta1y * spx_r["1D"]) if beta1y is not None and row["market"].get("r_1d") is not None and spx_r["1D"] is not None else None
            else:
                row["market"] = {"stale": True}
            # fundamentals
            mcap, ev = info.get("marketCap"), info.get("enterpriseValue")
            ebitda, debt, cash = info.get("ebitda"), info.get("totalDebt"), info.get("totalCash")
            fcf = info.get("freeCashflow")
            est = fd.get("earnings_estimate") or {}
            trend = fd.get("eps_trend") or {}
            revs = fd.get("eps_revisions") or {}
            rev_est = fd.get("revenue_estimate") or {}
            price = (row["market"] or {}).get("last") or info.get("regularMarketPrice")

            def rev(period, col):
                tr = trend.get(period) or {}
                cur, old = tr.get("current"), tr.get(col)
                return f(cur / old - 1) if cur and old else None

            fin_cur, quote_cur = info.get("financialCurrency"), info.get("currency")
            cur_mismatch = bool(fin_cur and quote_cur and fin_cur != quote_cur)
            row["valuation"] = {
                "market_cap": mcap, "enterprise_value": ev, "pe_fwd": f(info.get("forwardPE")), "pe_trailing": f(info.get("trailingPE")),
                "ev_ebitda": None if cur_mismatch else f(info.get("enterpriseToEbitda")),
                "ev_sales": None if cur_mismatch else f(info.get("enterpriseToRevenue")),
                "fcf_yield": None if cur_mismatch else (f(fcf / mcap) if fcf and mcap else None),
                "financial_currency": fin_cur,
                "currency_note": f"comptes en {fin_cur}, cotation en {quote_cur} : ratios EV et FCF de Yahoo non homogenes, mis a n/a" if cur_mismatch else None,
                "net_debt_ebitda": f((debt - cash) / ebitda) if ebitda and debt is not None and cash is not None and ebitda > 0 else None,
                "net_debt": f(debt - cash) if debt is not None and cash is not None else None,
            }
            e0y, e1y = (est.get("0y") or {}), (est.get("+1y") or {})
            row["growth"] = {
                "revenue_growth_yoy": f(info.get("revenueGrowth")), "eps_growth_yoy": f(info.get("earningsGrowth")),
                "revenue_growth_fy": f((rev_est.get("0y") or {}).get("growth")), "revenue_growth_fy1": f((rev_est.get("+1y") or {}).get("growth")),
                "eps_fy": f(e0y.get("avg")), "eps_fy1": f(e1y.get("avg")),
                "eps_fy1_vs_fy": f(e1y["avg"] / e0y["avg"] - 1) if e0y.get("avg") and e1y.get("avg") and e0y["avg"] > 0 else None,
                "eps_growth_fy": f(e0y.get("growth")), "eps_growth_fy1": f(e1y.get("growth")),
            }
            row["quality"] = {"gross_margin": f(info.get("grossMargins")), "operating_margin": f(info.get("operatingMargins")),
                              "net_margin": f(info.get("profitMargins")), "roe": f(info.get("returnOnEquity")), "roa": f(info.get("returnOnAssets"))}
            r0y = revs.get("0y") or {}
            r0q = revs.get("0q") or {}
            row["sentiment"] = {
                "rev_q_7d": rev("0q", "7daysAgo"), "rev_q_30d": rev("0q", "30daysAgo"), "rev_q_90d": rev("0q", "90daysAgo"),
                "rev_fy_7d": rev("0y", "7daysAgo"), "rev_fy_30d": rev("0y", "30daysAgo"), "rev_fy_90d": rev("0y", "90daysAgo"),
                "rev_fy1_30d": rev("+1y", "30daysAgo"),
                "up_30d_fy": r0y.get("upLast30days"), "down_30d_fy": r0y.get("downLast30days"),
                "up_30d_q": r0q.get("upLast30days"), "down_30d_q": r0q.get("downLast30days"),
                "recommendation_mean": f(info.get("recommendationMean")), "recommendation_key": info.get("recommendationKey"),
                "n_analysts": info.get("numberOfAnalystOpinions"), "target_mean": f(info.get("targetMeanPrice")),
                "upside": f(info.get("targetMeanPrice") / price - 1) if info.get("targetMeanPrice") and price else None,
                "short_pct_float": f(info.get("shortPercentOfFloat")), "short_ratio": f(info.get("shortRatio")),
            }
            row["weight_13f"] = s.get("weight_13f")
            row["change_13f"] = s.get("change_13f")
            # events: next earnings
            eds = fd.get("earnings_dates") or []
            cal = fd.get("calendar") or {}
            future = sorted([e for e in eds if e["date"] >= self.today.isoformat()], key=lambda e: e["date"])
            nxt = None
            cal_dates = cal.get("Earnings Date") or []
            if cal_dates:
                nxt = {"date": str(cal_dates[0])[:10], "date_range_end": str(cal_dates[-1])[:10] if len(cal_dates) > 1 else None,
                       "eps_consensus": f(cal.get("Earnings Average")), "revenue_consensus": f(cal.get("Revenue Average")), "source": "yfinance.calendar"}
                match = next((e for e in future if e["date"] == nxt["date"]), future[0] if future else None)
                nxt["timing"] = timing_from_hour(match["hour_local"]) if match else None
                if nxt["eps_consensus"] is None and match:
                    nxt["eps_consensus"] = match.get("eps_estimate")
            elif future:
                e = future[0]
                nxt = {"date": e["date"], "eps_consensus": e.get("eps_estimate"), "timing": timing_from_hour(e["hour_local"]), "source": "yfinance.get_earnings_dates"}
            if nxt and nxt["date"] < self.today.isoformat():
                # Yahoo's calendar still shows the last publication: fall back to the next listed date, else n/a
                last_pub = nxt["date"]
                nxt = ({"date": future[0]["date"], "eps_consensus": future[0].get("eps_estimate"), "timing": timing_from_hour(future[0]["hour_local"]),
                        "source": "yfinance.get_earnings_dates"} if future else
                       {"date": None, "eps_consensus": None, "timing": None, "source": "yfinance.calendar",
                        "note": f"prochaine date non publiée par Yahoo (dernière publication {last_pub})", "last_publication": last_pub})
            if nxt and nxt.get("date"):
                nxt["days_to"] = (date.fromisoformat(nxt["date"]) - self.today).days
                nxt["confirmed"] = not bool(nxt.get("date_range_end")) or nxt.get("date_range_end") == nxt["date"]
            elif nxt:
                nxt["days_to"] = None
            upcoming[t] = nxt
            exd = cal.get("Ex-Dividend Date")
            if exd and str(exd)[:10] >= self.today.isoformat():
                events["calendar"].append({"date": str(exd)[:10], "type": "ex-dividende", "symbol": t, "label": f"{t} ex-dividende", "source": "yfinance.calendar", "fetched_at": fd.get("fetched_at")})
            # reactions
            if t in closes.columns:
                rows_, summ = earnings_reactions(closes[t], spx, eds, today=self.today)
                events["reactions"][t] = {"rows": rows_, "summary": summ, "source": "yfinance.get_earnings_dates + prices", "fetched_at": fd.get("fetched_at")}
            quotes["stocks"][t] = row

        # ---- indices
        for t, s in syms.items():
            if s["type"] != "index" or t not in closes.columns:
                continue
            m = market_stats(closes[t])
            m["stale"] = prices_payload["symbols"][t]["stale"]
            m_usd = market_stats(usd[t]) if s["currency"] != "USD" else None
            b = {"SPX": beta_block(usd[t], spx)} if t != universe["index_keys"]["SPX"] else {}
            quotes["indices"][t] = {"ticker": t, "key": s["key"], "name": s["name"], "currency": s["currency"], "market": m, "market_usd": m_usd,
                                    "beta_spx_1y": (b.get("SPX") or {}).get("beta_1y"), "fetched_at": prices_payload["symbols"][t]["fetched_at"]}
            if b:
                risk["betas"][t] = b
        for t, s in syms.items():
            if s["type"] == "vol" and t in closes.columns:
                v = closes[t].dropna()
                quotes["indices"][t] = {"ticker": t, "key": s["key"], "name": s["name"], "currency": "pts", "market": market_stats(v),
                                        "fetched_at": prices_payload["symbols"][t]["fetched_at"]}
                quotes["indices"][t]["market"]["stale"] = prices_payload["symbols"][t]["stale"]
        # ---- ETFs
        for t, s in syms.items():
            if s["type"] != "etf":
                continue
            if t not in closes.columns:
                quotes["etfs"][t] = {"ticker": t, "name": s["name"], "market": {"stale": True}, "fetched_at": prices_payload["symbols"][t]["fetched_at"]}
                continue
            m = market_stats(closes[t])
            m["stale"] = prices_payload["symbols"][t]["stale"]
            mu = market_stats(usd[t])
            und_t = universe["index_keys"][s["underlying"]]
            und = closes[und_t] if und_t in closes.columns else None
            track = {}
            if und is not None:
                for h, n in (("1M", 21), ("3M", 63), ("YTD", None)):
                    e_r = horizon_return(usd[t], n) if n else market_stats(usd[t]).get("r_ytd")
                    i_r = horizon_return(und, n) if n else market_stats(und).get("r_ytd")
                    track[h] = {"etf_usd": e_r, "index": i_r, "gap": f(e_r - i_r) if e_r is not None and i_r is not None else None}
            b = {"SPX": beta_block(usd[t], spx), "NDX": beta_block(usd[t], ndx)}
            if sox is not None:
                b["SOX"] = beta_block(usd[t], sox)
            risk["betas"][t] = b
            quotes["etfs"][t] = {"ticker": t, "name": s["name"], "line": s["line"], "underlying": s["underlying"], "underlying_ticker": und_t,
                                 "currency": s.get("currency"), "market": m, "market_usd": mu, "tracking_usd": track,
                                 "beta_spx_1y": b["SPX"]["beta_1y"], "fetched_at": prices_payload["symbols"][t]["fetched_at"]}
        for k, t in universe["fx_keys"].items():
            if t in closes.columns:
                quotes["fx"][t] = {"ticker": t, "key": k, "market": market_stats(closes[t]), "fetched_at": prices_payload["symbols"][t]["fetched_at"]}
                quotes["fx"][t]["market"]["stale"] = prices_payload["symbols"][t]["stale"]

        # ---- vol implied vs realized (indices)
        for key, v in cfg["implied_vol"].items():
            ix_t = universe["index_keys"][v["index"]]
            if not v["ticker"]:
                risk["vol"]["indices"][key] = {"available": False, "reason": v["reason"], "index": v["index"],
                                               "rv_1m": realized_vol(closes[ix_t], 21) if ix_t in closes.columns else None}
                continue
            if v["ticker"] not in closes.columns:
                risk["vol"]["indices"][key] = {"available": False, "reason": "serie absente de Yahoo ce jour", "index": v["index"]}
                continue
            iv = closes[v["ticker"]].dropna()
            ixs = closes[ix_t].dropna()
            rv1 = realized_vol(ixs, 21)
            rv_series = np.log(ixs).diff().rolling(21).std() * np.sqrt(252) * 100
            spread_series = (iv.reindex(rv_series.index) - rv_series).dropna()
            risk["vol"]["indices"][key] = {
                "available": True, "ticker": v["ticker"], "index": v["index"], "iv": f(iv.iloc[-1]), "iv_date": str(iv.index[-1].date()),
                "iv_pct_1y": percentile_of_last(iv), "iv_chg_1m": f(iv.iloc[-1] - iv.iloc[-22]) if len(iv) > 22 else None,
                "rv_1m": rv1, "rv_3m": realized_vol(ixs, 63), "spread": f(iv.iloc[-1] / 100 - rv1) if rv1 else None,
                "spread_pct_1y": percentile_of_last(spread_series), "rv_1m_pct_1y": percentile_of_last(rv_series.dropna()),
                "history_1y": {"dates": [str(d.date()) for d in iv.index[-252:]], "iv": [f(x) for x in iv.values[-252:]],
                               "rv_1m": [f(x) for x in rv_series.reindex(iv.index[-252:], method="ffill").values]},
                "fetched_at": prices_payload["symbols"][v["ticker"]]["fetched_at"],
            }
        self._fx = fx
        self._usd = usd
        self._spx_r = spx_r
        self._sox = sox
        self._sx5e_usd = sx5e_usd
        return quotes, risk, events, upcoming

    # ------------------------------------------------------------------ second pass: options, signals, correlations
    def finish(self, universe, closes, quotes, risk, events, upcoming, options, breadth):
        cfg = self.cfg
        syms = universe["symbols"]
        usd, spx_r = self._usd, self._spx_r
        vt = cfg["vol_thresholds"]
        # upcoming earnings + implied vs historical move
        for t, nxt in upcoming.items():
            opt = options.get(t) or {}
            summ = (events["reactions"].get(t) or {}).get("summary") or {}
            hist = summ.get("avg_abs_move")
            im = opt.get("implied_move")
            rec = {**(nxt or {"date": None, "days_to": None}), "ticker": t, "implied_move": im, "implied_move_basis": opt.get("implied_move_basis"),
                   "implied_move_expiry": opt.get("implied_move_expiry"), "straddle": opt.get("straddle"), "atm_strike": opt.get("atm_strike"),
                   "hist_avg_abs_move": hist, "ratio_implied_hist": f(im / hist) if im and hist else None, "options_note": opt.get("note"),
                   "options_fetched_at": opt.get("fetched_at")}
            events["upcoming"][t] = rec
            if nxt and nxt.get("date") and nxt["days_to"] is not None and 0 <= nxt["days_to"] <= 30:
                events["calendar"].append({"date": nxt["date"], "type": "earnings", "symbol": t, "timing": nxt.get("timing"),
                                           "label": f"{t} résultats" + (f" ({nxt['timing']})" if nxt.get("timing") else ""),
                                           "eps_consensus": nxt.get("eps_consensus"), "implied_move": im, "hist_avg_abs_move": hist,
                                           "ratio": rec["ratio_implied_hist"], "confirmed": nxt.get("confirmed"), "source": nxt.get("source")})
            # stock vol block
            if t in closes.columns:
                px = closes[t].dropna()
                rv_series = (np.log(px).diff().rolling(21).std() * np.sqrt(252)).dropna()
                iv = opt.get("iv_30d")
                rv1 = realized_vol(px, 21)
                risk["vol"]["stocks"][t] = {
                    "iv_30d": iv, "iv_expiry": opt.get("iv_30d_expiry"), "iv_source": opt.get("iv_30d_source"), "iv_basis": opt.get("iv_30d_basis"),
                    "rv_1m": rv1, "rv_3m": realized_vol(px, 63),
                    "spread": f(iv - rv1) if iv and rv1 else None,
                    "iv_pct_vs_rv_1y": f((rv_series.iloc[-252:] < iv).mean() * 100) if iv and len(rv_series) > 60 else None,
                    "rv_1m_pct_1y": percentile_of_last(rv_series),
                    "note": "Percentile = rang de l'IV 30 j dans la distribution 1 an de la vol realisee 21 j (Yahoo ne fournit pas d'historique d'IV par action).",
                    "fetched_at": opt.get("fetched_at"),
                }
                p = risk["vol"]["stocks"][t]["iv_pct_vs_rv_1y"]
                risk["vol"]["stocks"][t]["flag"] = None if p is None else ("chère" if p >= vt["expensive_pct"] else ("bon marché" if p <= vt["cheap_pct"] else None))
        # fixed calendar items
        dl = next_13f_deadline(self.today)
        if dl:
            events["calendar"].append({"date": dl["deadline"], "type": "13F", "symbol": "SEC", "label": f"Date limite 13F (trimestre clos le {dl['quarter_end']})", "source": "regle 13f-1 : 45 j"})
            events["f13_deadline"] = dl
        for e in option_expiries(self.today, 45):
            events["calendar"].append({"date": e["date"], "type": "options", "symbol": "—", "label": e["type"], "source": "calendrier (3e vendredi)"})
            if e["quad"]:
                events["calendar"].append({"date": e["date"], "type": "rebalancement", "symbol": "SPX", "label": "Rebalancement trimestriel S&P (effectif après clôture)", "source": "calendrier S&P DJI"})
        events["calendar"] = sorted([c for c in events["calendar"] if c["date"] and (date.fromisoformat(c["date"]) - self.today).days <= 45], key=lambda c: c["date"])
        events["horizon_days"] = 30
        # signals
        sig = {"momentum_us": {}, "mean_reversion_eu": {}, "earnings_flag_days": cfg["signals"]["momentum_us"]["earnings_flag_days"]}
        for t, row in quotes["stocks"].items():
            m = row.get("market") or {}
            if not m.get("last"):
                continue
            s = momentum_signal(m, spx_r["3M"], cfg["signals"]["momentum_us"])
            d2e = (events["upcoming"].get(t) or {}).get("days_to")
            s["earnings_soon"] = d2e is not None and 0 <= d2e <= cfg["signals"]["momentum_us"]["earnings_flag_days"]
            s["days_to_earnings"] = d2e
            s["inputs"] = {k: m.get(k) for k in ("last", "ma50", "ma200", "r_3m", "idio_1m", "z_20d", "rsi_14")}
            s["spx_r_3m"] = spx_r["3M"]
            sig["momentum_us"][t] = s
            row["signal"] = ("Momentum" + ("*" if s["earnings_soon"] else "")) if s["active"] else None
        for key in ("SX5E", "DAX", "CAC", "FTSE"):
            t = universe["index_keys"][key]
            q = quotes["indices"].get(t)
            if not q:
                continue
            s = mean_reversion_signal(q["market"], cfg["signals"]["mean_reversion_eu"])
            s["inputs"] = {k: q["market"].get(k) for k in ("z_20d", "rsi_14", "last", "ma50", "ma200")}
            sig["mean_reversion_eu"][t] = s
            q["signal"] = s["state"] if s["active"] else None
        risk["signals"] = sig
        # correlations (60d, USD)
        win = cfg["correlation_window_days"]
        thr = cfg["correlation_pair_threshold"]
        smgb = "SMGB.L"
        corr = {"window_days": win, "threshold": thr}
        if smgb in usd:
            others = {t: usd[t] for t, s in syms.items() if t in usd and t != smgb and s["type"] in ("stock", "index")}
            frame = pd.DataFrame({smgb: usd[smgb], **others})
            cm = correlation_matrix(frame, win)
            if cm["matrix"]:
                i = cm["symbols"].index(smgb)
                corr["smgb_vs_universe"] = sorted([{"symbol": s_, "corr": cm["matrix"][i][j]} for j, s_ in enumerate(cm["symbols"]) if s_ != smgb and cm["matrix"][i][j] is not None],
                                                  key=lambda x: -x["corr"])
                corr["smgb_note"] = "SMGB.L converti en USD (GBPUSD) ; cloture Londres 16:30 vs New York 16:00 : correlations quotidiennes sous-estimees pour les titres US."
        basket = [t for t in universe["groups"].get("13F Situational Awareness", []) if t in usd]
        extra = [t for t in cfg["stock_groups"].get("Mag7+AMD", []) if t in usd and t in ("NVDA", "AMD")]
        bframe = pd.DataFrame({t: usd[t] for t in basket + extra})
        cm = correlation_matrix(bframe, win)
        pairs = []
        for i, a in enumerate(cm["symbols"]):
            for j, b in enumerate(cm["symbols"]):
                if j > i and cm["matrix"][i][j] is not None and cm["matrix"][i][j] > thr:
                    pairs.append({"a": a, "b": b, "corr": cm["matrix"][i][j]})
        corr["basket_matrix"] = cm
        corr["pairs_above_threshold"] = sorted(pairs, key=lambda p: -p["corr"])
        if cm["matrix"]:
            vals = [cm["matrix"][i][j] for i in range(len(cm["symbols"])) for j in range(len(cm["symbols"])) if j > i and cm["matrix"][i][j] is not None]
            corr["basket_avg_pair_corr"] = f(np.mean(vals)) if vals else None
        risk["correlations"] = corr
        # market reading
        risk["market_reading"] = self.market_reading(universe, quotes, risk, events, breadth)
        return quotes, risk, events

    # ------------------------------------------------------------------ reading (5 lines)
    def market_reading(self, universe, quotes, risk, events, breadth):
        pct = lambda x: "n/a" if x is None else f"{x * 100:+.1f}%"
        lines = []
        spx = quotes["indices"].get(universe["index_keys"]["SPX"], {}).get("market", {})
        ndx = quotes["indices"].get(universe["index_keys"]["NDX"], {}).get("market", {})
        sx5e = quotes["indices"].get(universe["index_keys"]["SX5E"], {}).get("market", {})
        movers = sorted([(t, r["market"]) for t, r in quotes["stocks"].items() if r.get("market", {}).get("r_1d") is not None], key=lambda x: -abs(x[1]["r_1d"]))[:3]
        mv = "; ".join(f"{t} {pct(m['r_1d'])} (idio {pct(m.get('idio_1d'))}, β {m and quotes['stocks'][t].get('beta_spx_1y') and round(quotes['stocks'][t]['beta_spx_1y'], 2)})" for t, m in movers)
        lines.append(f"Ce qui bouge — SPX {pct(spx.get('r_1d'))} / NDX {pct(ndx.get('r_1d'))} / SX5E {pct(sx5e.get('r_1d'))} sur 1 j ; "
                     f"plus gros mouvements du panier : {mv or 'n/a'}. Un idio proche de 0 = mouvement expliqué par le beta.")
        vi = risk["vol"]["indices"]
        vix, vxn = vi.get("VIX", {}), vi.get("VXN", {})
        exp_ = [t for t, v in risk["vol"]["stocks"].items() if v.get("flag") == "chère"]
        cheap = [t for t, v in risk["vol"]["stocks"].items() if v.get("flag") == "bon marché"]
        ratios = sorted([(t, u["ratio_implied_hist"]) for t, u in events["upcoming"].items() if u.get("ratio_implied_hist")], key=lambda x: -x[1])
        rtxt = ", ".join(f"{t} ×{r:.1f}" for t, r in ratios[:3]) if ratios else "aucun move implicite calculable"
        lvl = lambda v: "n/a" if v.get("iv") is None else f"{v['iv']:.1f}"
        lines.append(f"Vol — VIX {lvl(vix)} ({'n/a' if vix.get('iv_pct_1y') is None else f'{vix['iv_pct_1y']:.0f}e pct 1 an'}, spread vs réalisée SPX {pct(vix.get('spread'))}), "
                     f"VXN {lvl(vxn)} ({'n/a' if vxn.get('iv_pct_1y') is None else f'{vxn['iv_pct_1y']:.0f}e pct'}) ; IV chère (≥ {self.cfg['vol_thresholds']['expensive_pct']}e pct) : {', '.join(exp_) or 'aucune'} ; bon marché : {', '.join(cheap) or 'aucune'} ; "
                     f"moves implicites vs historique les plus chers : {rtxt}.")
        mom = [t + ("*" if s["earnings_soon"] else "") for t, s in risk["signals"]["momentum_us"].items() if s["active"]]
        mr = [f"{universe['symbols'][t]['key']} {s['state']}" for t, s in risk["signals"]["mean_reversion_eu"].items() if s["active"]]
        lines.append(f"Signaux — momentum US actif : {', '.join(mom) or 'aucun'} ; mean reversion Europe : {', '.join(mr) or 'aucune'} (* = résultats ≤ {risk['signals']['earnings_flag_days']} j).")
        soon = [c for c in events["calendar"] if (date.fromisoformat(c["date"]) - self.today).days <= 7]
        lines.append("Événements 7 j — " + ("; ".join(f"{c['date']} {c['label']}" + (f" (move impl. {pct(c['implied_move'])} vs hist {pct(c['hist_avg_abs_move'])})" if c.get("implied_move") else "") for c in soon) or "rien de programmé."))
        corr = risk["correlations"]
        top = corr.get("smgb_vs_universe", [])[:3]
        w13 = sorted([(t, s.get("weight_13f")) for t, s in universe["symbols"].items() if s.get("weight_13f")], key=lambda x: -x[1])[:3]
        b = breadth or {}
        bn = b.get("indices", {}).get("NDX", {})
        lines.append(f"Concentration semis — corrélation 60 j moyenne du panier 13F {corr.get('basket_avg_pair_corr') and round(corr['basket_avg_pair_corr'], 2)}, "
                     f"{len(corr.get('pairs_above_threshold', []))} paires > {corr.get('threshold')} ; SMGB le plus corrélé à {', '.join(f'{x['symbol']} ({x['corr']:.2f})' for x in top) or 'n/a'} ; "
                     f"top 13F : {', '.join(f'{t} {w * 100:.0f}%' for t, w in w13) or 'n/a'} ; NDX {'n/a' if bn.get('pct_above_ma50') is None else round(bn['pct_above_ma50'])}% des titres > MM50 (au {bn.get('as_of', 'n/a')}).")
        return lines

    # ------------------------------------------------------------------ main
    def run(self):
        try:
            sa13f = self.step("13F Situational Awareness (SEC EDGAR + OpenFIGI)", self.run_13f) or read_json(self.out / "sa_13f.json") or {}
            if sa13f.get("positions") is None:
                sa13f = read_json(self.out / "sa_13f.json") or {}
            constituents = self.step("Compositions d'indices (Wikipedia API)", self.run_constituents) or read_json(self.out / "constituents.json") or {"indices": {}}
            universe = self.step("Univers", lambda: self.build_universe(sa13f), critical=True)
            closes, prices_payload = self.step("Prix (yfinance)", lambda: self.run_prices(universe), critical=True)
            fundamentals = self.step("Fondamentaux et estimations (yfinance)", lambda: self.run_fundamentals(universe)) or {}
            quotes, risk, events, upcoming = self.step("Calculs marché / beta / événements", lambda: self.assemble(universe, closes, prices_payload, fundamentals, sa13f, constituents), critical=True)
            options = self.step("Options : move implicite et IV (yfinance)", lambda: self.run_options(universe, fundamentals, closes, upcoming)) or {}
            breadth_res = self.step("Breadth locale (constituants)", lambda: self.run_breadth(constituents, closes, universe))
            breadth = breadth_res[0] if breadth_res else {"indices": {}, "error": "breadth non calculee"}
            quotes, risk, events = self.step("Signaux, corrélations, lecture", lambda: self.finish(universe, closes, quotes, risk, events, upcoming, options, breadth), critical=True)
            status = "ok" if not self.errors else "partial"
        except Exception as exc:  # noqa: BLE001
            status = "error"
            self.errors.append({"step": "fatal", "error": str(exc)[:300], "at": now_iso()})
            self.write_status(status)
            (self.out.parent / "LAST_ERROR.txt").write_text(f"{now_iso()} {exc}\n{traceback.format_exc()}", encoding="utf-8")
            raise
        # write files
        write_json(self.out / "sa_13f.json", sa13f)
        write_json(self.out / "constituents.json", constituents)
        write_json(self.out / "universe.json", universe)
        write_json(self.out / "prices.json", prices_payload)
        write_json(self.out / "quotes.json", quotes)
        write_json(self.out / "events.json", events)
        write_json(self.out / "breadth.json", breadth)
        write_json(self.out / "risk.json", risk)
        self.write_status(status)
        self.bundle()
        if status == "ok" and (self.out.parent / "LAST_ERROR.txt").exists():
            (self.out.parent / "LAST_ERROR.txt").unlink()
        return status

    def write_status(self, status):
        stale = []
        p = read_json(self.out / "prices.json")
        if p:
            stale = [t for t, s in p["symbols"].items() if s.get("stale")]
        payload = {
            "run_id": self.run_id, "status": status, "started_at": self.started, "finished_at": now_iso(),
            "expected_last_close": self.expected_close.isoformat(), "steps": self.steps, "errors": self.errors,
            "symbol_log_counts": self.symlog.counts(), "symbol_log": self.symlog.entries, "stale_symbols": stale,
            "python": sys.version.split()[0], "args": vars(self.args),
        }
        risk = read_json(self.out / "risk.json")
        if risk and risk.get("market_reading"):
            payload["market_reading"] = risk["market_reading"]
        write_json(self.out / "run_status.json", payload)

    def bundle(self):
        """data.js: every JSON in one global so index.html works from file:// (no fetch) as well as from a server."""
        names = ["universe", "prices", "quotes", "events", "breadth", "constituents", "sa_13f", "risk", "run_status", "backtest"]
        parts = []
        for n in names:
            p = self.out / f"{n}.json"
            parts.append(f'"{n}": ' + (p.read_text(encoding="utf-8") if p.exists() else "null"))
        (self.out / "data.js").write_text("window.EQUITY_MONITOR_DATA = {" + ",".join(parts) + "};\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-breadth", action="store_true")
    ap.add_argument("--skip-options", action="store_true")
    ap.add_argument("--skip-13f", action="store_true")
    ap.add_argument("--skip-wiki", action="store_true")
    ap.add_argument("--bundle-only", action="store_true", help="only rebuild data.js from the existing JSON files")
    args = ap.parse_args()
    run = MonitorRun(args)
    if args.bundle_only:
        run.bundle()
        return 0
    status = run.run()
    run.log.info("run %s finished: %s", run.run_id, status)
    return 0 if status in ("ok", "partial") else 1


if __name__ == "__main__":
    sys.exit(main())
