"""Inline artifact_data.json into template.html -> index.html (artifact body) and preview.html (full doc for local PDF/screenshot)."""
import json, pathlib
h = pathlib.Path(__file__).parent
import json
d = json.loads((h.parent / "data" / "artifact_data.json").read_text())
d["intra"] = json.loads((h.parent / "data" / "intraday.json").read_text())
data = json.dumps(d)
body = (h / "template.html").read_text().replace("__DATA__", data)
(h / "index.html").write_text(body)
(h / "preview.html").write_text('<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head><body>' + body + "</body></html>")
print(len(body) // 1024, "KB")
