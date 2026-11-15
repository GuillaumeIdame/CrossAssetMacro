"""Build template.html from parts/: base_v3.html (CSS + chart helpers), body.html, render.js."""
import pathlib
h = pathlib.Path(__file__).parent
old = (h / "parts" / "base_v3.html").read_text()
head = old[:old.index("</style>")].replace("--good:#006300; --font:", "--good:#006300; --st-good:#0ca30c; --st-warn:#fab219; --font:", 1)
head += """.conf{display:inline-flex;align-items:center;gap:5px;font-size:11px;font-weight:650;padding:1px 8px;border-radius:99px;border:1.5px solid var(--c);color:var(--ink);margin-right:4px;white-space:nowrap}
.conf::before{content:"";width:7px;height:7px;border-radius:50%;background:var(--c)}
.concl li{list-style:none;margin-left:-18px}
.stack{display:flex;flex-direction:column;gap:16px}
</style>
"""
js = old[old.index("<script>"):old.index("/* ---------- heat tables ---------- */")]
a = "  const ser = [...o.series]"
js = js.replace(a, """  if (o.band) { let d = ""; o.band.hi.forEach((v, i) => { if (v == null) return; d += (d ? "L" : "M") + X(xs[i]).toFixed(1) + " " + Y(v).toFixed(1); });
    for (let i = o.band.lo.length - 1; i >= 0; i--) { const v = o.band.lo[i]; if (v == null) continue; d += "L" + X(xs[i]).toFixed(1) + " " + Y(v).toFixed(1); }
    if (d) S("path", { d: d + "Z", style: `fill:${o.band.color};fill-opacity:.14;stroke:none` }, svg); }
""" + a, 1)
i0 = js.index("function rowsChart"); i1 = js.index("\n}\n", i0) + 3
rc = js[i0:i1].replace("m = { l: o.ml || 92, r: 40,", "m = { l: o.ml || 92, r: o.mr || 40,")
rc = rc.replace("style: `fill:${s.color}`, tabindex: 0", "style: `fill:${typeof s.color === \"function\" ? s.color(ci) : s.color}`, tabindex: 0")
rc = rc.replace("[{ color: s.color, v: o.tfmt(v), l: s.name }]", "[{ color: typeof s.color === \"function\" ? s.color(ci) : s.color, v: o.tfmt(v), l: s.name }]")
rc = rc.replace('x: v >= 0 ? x1 + 5 : x1 - 5, y: yy + bh - 3, "text-anchor": v >= 0 ? "start" : "end"', 'x: v >= 0 ? x1 + 5 : x0 + 5, y: yy + bh - 3, "text-anchor": "start"')
rc = rc.replace("lt.textContent = o.tfmt(v); }); });", "lt.textContent = o.lab ? o.lab(ci, si, v) : o.tfmt(v); }); });")
assert "o.lab" in rc and "o.mr" in rc and "x0 + 5" in rc
js = js[:i0] + rc + js[i1:]
pre = """const XT = [{ v: 1, l: "D1" }, { v: 21, l: "1m" }, { v: 63, l: "3m" }, { v: 126, l: "6m" }, { v: 189, l: "9m" }, { v: 252, l: "12m" }];
const dayX = Array.from({ length: 253 }, (_, i) => i + 1);
"""
(h / "template.html").write_text(head + "\n" + (h / "parts" / "body.html").read_text() + "\n" + js + pre + (h / "parts" / "render.js").read_text() + "\n</script>\n")
print("assembled")
