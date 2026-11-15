"""Collect Polymarket CLOB price-history scrapes (saved tool-result files) into data/raw/pm/hist/<token>.json."""
import glob, json, re, sys
from pathlib import Path
out = Path(__file__).parent / "data" / "raw" / "pm" / "hist"
n = 0
for f in glob.glob(sys.argv[1] + "/*.txt"):
    try:
        d = json.load(open(f))
    except Exception:
        continue
    url = (d.get("metadata") or {}).get("sourceURL", "")
    if "prices-history" not in url:
        continue
    tok = re.search(r"market=(\d+)", url).group(1)
    h = json.loads(re.search(r"\{.*\}", d["rawHtml"], re.S).group(0))["history"]
    json.dump(h, open(out / f"{tok}.json", "w")); n += 1
print("saved", n)
