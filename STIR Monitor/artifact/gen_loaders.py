import json
c = json.load(open("contracts.json"))
IDS = {"SOFR": "sofr", "Euribor": "euribor", "SONIA": "sonia", "CORRA": "corra", "SARON": "saron", "Aussie Bills": "aussie"}

def loader(ds, title, conids, own, other_period, desc):
    m = json.dumps(conids)
    period_line = f'period: "{other_period}", ' if other_period else ""
    return f'''dash.loader("{ds}", {{
  description: "{desc}",
  fn: async ({{ answer, call, args }}) => {{
    const CONTRACTS = {m}; // contract code -> IBKR contract id
    const OWN = "{own}";    // the contract this dataset's own call fetches
    const toRows = (code, a) => {{
      if (!a || a.error || !Array.isArray(a.time)) return {{ code, error: (a && (a.error && (a.error.message || a.error))) || "no bars" }};
      return {{ code, rows: a.time.map((t, i) => ({{ contract: code, time: t,
        session: new Date(Date.parse(t) + 12 * 3600e3).toISOString().slice(0, 10), close: Number(a.close[i]) }})) }};
    }};
    // One contract at a time, retrying transient connector errors, so IBKR isn't flooded.
    const wait = (ms) => new Promise((r) => setTimeout(r, ms));
    const fetchOne = async (code, id, extra) => {{
      let last;
      // Retry anything but a clear permanent refusal, backing off up to ~30 s in total.
      const permanent = /permission|not found|invalid|no such|unknown contract/i;
      for (const delay of [0, 1000, 2000, 4000, 8000, 15000]) {{
        if (delay) await wait(delay);
        try {{
          const r = toRows(code, await call("get_price_history", {{ ...args, ...extra, contract_id: id }}));
          if (r.rows || permanent.test(r.error)) return r;
          last = r;
        }} catch (e) {{
          last = {{ code, error: String((e && e.message) || e) }};
          if (permanent.test(last.error)) return last;
        }}
      }}
      return last;
    }};
    const results = [toRows(OWN, answer)];
    if (!results[0].rows) results[0] = await fetchOne(OWN, CONTRACTS[OWN], {{}});
    for (const [code, id] of Object.entries(CONTRACTS)) {{
      if (code !== OWN) {{ await wait(300); results.push(await fetchOne(code, id, {{ {period_line}}})); }}
    }}
    const ok = results.filter((r) => r.rows && r.rows.length);
    if (!ok.length) throw new Error("IBKR returned no bars: " + results.map((r) => r.code + " " + r.error).join("; "));
    return {{ data: ok.flatMap((r) => r.rows), columns: ["contract", "session", "time", "close"],
      truncated: ok.length < results.length,
      meta: results.filter((r) => r.error).map((r) => ({{ label: "Not loaded: " + r.code, value: String(r.error) }})) }};
  }},
}});
'''

out = []
for cv, spec in c["curves"].items():
    ds = IDS[cv]
    out.append(loader(ds, cv, spec["conids"], "Z27", "ONE_MONTH",
        f"Fetches the rest of the {cv} strip (one month of daily bars each) and stacks them into one table."))
    out.append(loader(ds + "_5m", cv, spec["conids"], "Z27", None,
        f"Fetches 5-minute bars for the rest of the {cv} strip and stacks them into one table."))
out.append(loader("zq", "Fed Funds", c["zq"]["conids"], "X26", None,
    "Fetches every 30-day Fed Funds month through Dec 2027 and stacks them into one table."))
open("loaders.js", "w").write("/* Loaders: each dataset calls IBKR once for its own contract, then fetches the rest of its strip. */\n" + "\n".join(out))

# dataset documents
docs = {}
now = "2026-11-13T10:00:00Z"
for cv, spec in c["curves"].items():
    ds = IDS[cv]
    conid = spec["conids"]["Z27"]
    docs[ds] = {"title": f"{cv} futures · daily", "description": f"Daily closes of the {cv} 3M futures strip from IBKR (Z27 over six months, the rest over one month).",
        "source": {"kind": "call", "connector": "Interactive Brokers (IBKR)", "tool": "get_price_history",
                   "args": {"contract_id": conid, "exchange": spec["exchange"], "security_type": "FUT", "step": "ONE_DAY", "period": "SIX_MONTHS", "outside_rth": True}},
        "edit": {"via": "claude", "at": now}}
    docs[ds + "_5m"] = {"title": f"{cv} futures · 5-min", "description": f"5-minute bars over the last two days for the {cv} 3M futures strip from IBKR.",
        "source": {"kind": "call", "connector": "Interactive Brokers (IBKR)", "tool": "get_price_history",
                   "args": {"contract_id": conid, "exchange": spec["exchange"], "security_type": "FUT", "step": "FIVE_MINS", "period": "TWO_DAYS", "outside_rth": True}},
        "edit": {"via": "claude", "at": now}}
docs["zq"] = {"title": "Fed Funds futures · daily", "description": "Daily closes of 30-day Fed Funds futures (CBOT ZQ), Nov 2026 to Dec 2027, from IBKR.",
    "source": {"kind": "call", "connector": "Interactive Brokers (IBKR)", "tool": "get_price_history",
               "args": {"contract_id": c["zq"]["conids"]["X26"], "exchange": "CBOT", "security_type": "FUT", "step": "ONE_DAY", "period": "ONE_MONTH", "outside_rth": True}},
    "edit": {"via": "claude", "at": now}}
json.dump(docs, open("datasets.json", "w"), indent=1)
print(len(docs), "datasets")
