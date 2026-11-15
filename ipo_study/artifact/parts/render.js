const ST = D.stats, XA = D.xa, I = D.intra;
const isPts = a => /VIX|10Y/.test(a);
const fmtA = (a, v) => v == null ? "n/a" : /10Y/.test(a) ? num(v, 1) + "bp" : /VIX/.test(a) ? num(v, 2) + " pts" : pct(v, 1);

/* ---------- heat tables (with optional CI lookup per group) ---------- */
function heatCell(td, v, scale = 0.4) { if (v == null || Number.isNaN(v)) { td.textContent = "n/a"; td.className = "n"; return; }
  const t = Math.min(1, Math.abs(v) / scale) * 62; td.className = "h";
  td.style.background = `color-mix(in srgb, var(--${v >= 0 ? "pos" : "neg"}) ${t.toFixed(0)}%, var(--mid))`; td.textContent = pct(v); }
function heatTable(host, groups, cols) {
  host.replaceChildren(); const t = H("table", "", null, host); const th = H("tr", "", null, H("thead", "", null, t));
  H("th", "", "", th); H("th", "", "n", th); cols.forEach(c => H("th", "", c.h, th)); const tb = H("tbody", "", null, t);
  groups.forEach(g => { if (g.title) { const r = H("tr", "grp", null, tb); const h = H("th", "", g.title, r); h.colSpan = cols.length + 2; }
    g.rows.forEach(r => { const tr = H("tr", "", null, tb); H("td", "lab", r.key, tr); H("td", "n", String(r.n), tr);
      cols.forEach(c => { const td = H("td", "", "", tr); const v = r[c.k];
        if (c.fmt === "plain") { td.textContent = (v == null || Number.isNaN(v)) ? "n/a" : (v * 100).toFixed(0) + "%"; td.className = "n"; return; }
        heatCell(td, v, c.scale); const ci = g.ci ? g.ci(r, c.k) : null;
        const tip = e => showTT(e, r.key, [{ v: pct(v), l: c.h }].concat(ci && ci[0] != null ? [{ v: `${pct(ci[0])} to ${pct(ci[1])}`, l: "95% CI of the median" }] : [])
          .concat([{ v: String(r.n), l: "IPOs" }, { v: "", l: (r.names || []).slice(0, 14).join(", ") + ((r.names || []).length > 14 ? " …" : "") }]));
        td.addEventListener("pointermove", tip); td.addEventListener("pointerleave", hideTT); }); }); });
}
const COLS = [{ k: "pop", h: "Day-1 pop (vs offer)", scale: .6 }, { k: "r5", h: "Day 5" }, { k: "r21", h: "Day 21" }, { k: "r63", h: "Day 63" }, { k: "r126", h: "Day 126" }, { k: "r252", h: "Day 252" }, { k: "pct_below_offer63", h: "Below offer by day 63", fmt: "plain" }];
const DCOLS = [{ k: "pop", h: "Day-1 pop (vs offer)", scale: .6 }, { k: "r21", h: "Day 21" }, { k: "r63", h: "Day 63" }, { k: "r126", h: "Day 126" }];
const ciFrom = grp => (r, k) => { const g = ST.groups[grp]; const row = g && g.rows.find(x => x.key === r.key); const m = { pop: "pop_ci", r21: "r21_ci", r63: "r63_ci", r126: "r126_ci" }[k]; return row && m ? row[m] : null; };
const fp = p => p == null ? "n/a" : p < 0.001 ? "<0.001" : p.toFixed(p < 0.1 ? 3 : 2);
function kwLine(el, grps) { const L = { d1_pop: "pop", r21: "day 21", r63: "day 63", r126: "day 126" };
  el.textContent = "Do the groups differ? Kruskal-Wallis " + grps.map(g => { const k = ST.groups[g]; return `${g.toLowerCase()}: ` + Object.keys(L).map(m => `${L[m]} p ${fp(k.kruskal[m])} (q ${fp(k.kruskal_q[m])})`).join(", "); }).join("; ") + "."; }

/* ---------- forest plot: estimate with 95% CI per row ---------- */
function forest(host, o) {
  host.replaceChildren();
  const W = host.clientWidth || 600, narrow = W < 560, rh = narrow ? 40 : 26, ml = narrow ? 8 : Math.min(300, W * 0.42), mr = narrow ? 8 : 150, top = 4;
  const Ht = top + o.rows.length * rh + 26, X = v => ml + (Math.max(o.xmin, Math.min(o.xmax, v)) - o.xmin) / (o.xmax - o.xmin) * (W - ml - mr);
  const svg = S("svg", { width: W, height: Ht, viewBox: `0 0 ${W} ${Ht}`, role: "img", "aria-label": o.aria }, host);
  o.xticks.forEach(t => { S("line", { x1: X(t), x2: X(t), y1: top, y2: Ht - 22, style: `stroke:${t === 0 ? "var(--axis)" : "var(--grid)"};stroke-width:1` }, svg);
    const tx = S("text", { x: X(t), y: Ht - 6, "text-anchor": "middle" }, svg); tx.textContent = o.xfmt(t); });
  o.rows.forEach((r, i) => { const y0 = top + i * rh, yc = narrow ? y0 + 28 : y0 + rh / 2;
    if (r.header) { const tx = S("text", { x: 0, y: y0 + rh - 8, class: "strong" }, svg); tx.textContent = r.label; return; }
    const lt = S("text", { x: narrow ? 0 : ml - 10, y: narrow ? y0 + 13 : yc + 4, "text-anchor": narrow ? "start" : "end", class: "ink" }, svg); lt.textContent = r.label;
    const vt = S("text", { x: narrow ? W : W - mr + 10, y: narrow ? y0 + 13 : yc + 4, "text-anchor": narrow ? "end" : "start", class: "strong" }, svg);
    vt.textContent = o.fmt(r.v) + (r.lo != null ? `  [${o.fmt(r.lo)}, ${o.fmt(r.hi)}]` : "");
    if (r.lo != null) { S("line", { x1: X(r.lo), x2: X(r.hi), y1: yc, y2: yc, style: `stroke:${r.color};stroke-width:2;stroke-linecap:round` }, svg);
      [r.lo, r.hi].forEach(v => S("line", { x1: X(v), x2: X(v), y1: yc - 4, y2: yc + 4, style: `stroke:${r.color};stroke-width:2` }, svg)); }
    S("circle", { cx: X(r.v), cy: yc, r: 5, style: `fill:${r.color};stroke:var(--surface);stroke-width:2` }, svg);
    const hit = S("rect", { x: 0, y: y0, width: W, height: rh, fill: "transparent", tabindex: 0 }, svg);
    const tip = e => showTT(e, r.label, r.tip || [{ v: o.fmt(r.v), l: "estimate" }]);
    hit.addEventListener("pointermove", tip); hit.addEventListener("pointerleave", hideTT);
    hit.addEventListener("focus", () => { const b = hit.getBoundingClientRect(); tip({ clientX: b.left + W / 2, clientY: b.top }); }); hit.addEventListener("blur", hideTT); });
}
const CONF = { High: "var(--st-good)", Medium: "var(--st-warn)", Low: "var(--muted)", "Too few": "var(--muted)" };
function chip(parent, c) { const s = H("span", "conf", c, parent); s.style.setProperty("--c", CONF[c] || "var(--muted)"); return s; }

/* ---------- generic scatter with nearest-point hover ---------- */
function scatter(host, o) {
  host.replaceChildren();
  const W = host.clientWidth || 500, Ht = o.h || 300, m = { l: 46, r: 14, t: 10, b: 32 }, iw = W - m.l - m.r, ih = Ht - m.t - m.b;
  const cl = (v, a, b) => Math.max(a, Math.min(b, v)), X = v => m.l + (cl(v, o.xmin, o.xmax) - o.xmin) / (o.xmax - o.xmin) * iw, Y = v => m.t + (o.ymax - cl(v, o.ymin, o.ymax)) / (o.ymax - o.ymin) * ih;
  const svg = S("svg", { width: W, height: Ht, viewBox: `0 0 ${W} ${Ht}`, role: "img", "aria-label": o.aria }, host);
  o.yticks.forEach(t => { S("line", { x1: m.l, x2: W - m.r, y1: Y(t), y2: Y(t), style: `stroke:${t === 0 ? "var(--axis)" : "var(--grid)"};stroke-width:1` }, svg); const tx = S("text", { x: m.l - 8, y: Y(t) + 4, "text-anchor": "end" }, svg); tx.textContent = o.yfmt(t); });
  o.xticks.forEach(t => { if (t === 0) S("line", { x1: X(t), x2: X(t), y1: m.t, y2: m.t + ih, style: "stroke:var(--axis);stroke-width:1" }, svg); const tx = S("text", { x: X(t), y: Ht - 14, "text-anchor": "middle" }, svg); tx.textContent = o.xfmt(t); });
  const lb = S("text", { x: m.l + iw / 2, y: Ht - 1, "text-anchor": "middle", class: "ink" }, svg); lb.textContent = o.xlabel;
  o.pts.forEach(p => S("circle", { cx: X(p.x), cy: Y(p.y), r: 5, style: `fill:${p.color};stroke:var(--surface);stroke-width:2` }, svg));
  const hi = S("circle", { r: 8, fill: "none", style: "stroke:var(--ink);stroke-width:2", visibility: "hidden" }, svg), ov = S("rect", { x: m.l, y: m.t, width: iw, height: ih, fill: "transparent" }, svg);
  ov.addEventListener("pointermove", e => { const r = ov.getBoundingClientRect(), px = e.clientX - r.left + m.l, py = e.clientY - r.top + m.t; let b = null, bd = 1e9;
    o.pts.forEach(p => { const d = Math.hypot(X(p.x) - px, Y(p.y) - py); if (d < bd) { bd = d; b = p; } });
    if (b && bd < 40) { hi.setAttribute("cx", X(b.x)); hi.setAttribute("cy", Y(b.y)); hi.setAttribute("visibility", "visible"); showTT(e, b.title, b.rows); } else { hi.setAttribute("visibility", "hidden"); hideTT(); } });
  ov.addEventListener("pointerleave", () => { hi.setAttribute("visibility", "hidden"); hideTT(); });
}

/* deterministic bootstrap for small arrays shown in the page */
function bootMean(v, B = 4000) { let s = 12345; const rnd = () => (s = (s * 1103515245 + 12345) % 2147483648) / 2147483648; const n = v.length, ms = [];
  for (let b = 0; b < B; b++) { let t = 0; for (let i = 0; i < n; i++) t += v[Math.floor(rnd() * n)]; ms.push(t / n); } ms.sort((a, b) => a - b); return [ms[Math.floor(.025 * B)], ms[Math.floor(.975 * B)]]; }

/* ---------- header tiles ---------- */
(() => { const a = D.all, t = $("#tiles"), fl = ST.strategies[0], hot = ST.groups["Pricing vs range"].rows.find(r => r.key.startsWith("Priced above"));
  [["IPOs studied", String(a.n), "plus 11 large-listing events"], ["Median day-1 pop", pct(a.pop), "from offer; mean +37%"], ["Allocation flip Sharpe", fl.sr_trade.toFixed(2), "per trade, offer to day-1 close"],
   ["Hot deals at day 63", pct(hot.r63), "priced above first range, n = " + hot.n], ["Close below the open", "60%", "on debut day"], ["Survives correction", "1 effect", "demand predicts the pop"]]
  .forEach(([l, v, d]) => { const c = H("div", "tile", null, t); H("div", "l", l, c); H("div", "v", v, c); H("div", "d", d, c); }); })();

/* ---------- conclusions ---------- */
(() => { const L = $("#concl");
  [["High", "Demand predicts the pop.", "Deals priced above their first filed range popped +31% (median) against +4% for the rest. The price revision and the pop have a rank correlation of 0.67 (q < 0.001). This is the only bucket result that survives a multiple-testing correction."],
   ["High", "Getting an allocation pays.", "Offer to day-1 close averaged +37% (95% CI +23% to +54%) and was positive 79% of the time; per-trade Sharpe 0.72. It only helps if you are allocated."],
   ["Medium", "Hot deals give it back.", "Above-range deals were −20% (median) by day 63 (95% CI −28% to −2%) against +14% for the rest. Shorting them from day 5 to day 63 made +11.5% on average with a 71% hit rate (Wilcoxon p = 0.03); the day-126 difference does not survive correction (q = 0.52)."],
   ["High", "The typical IPO trails QQQ, and the gap grows.", "Median IPO minus QQQ from the day-1 close: −14% at day 63, −34% at day 126 (95% CI −46% to −15%), −39% at day 252 (CI −48% to −10%). This is a statement about the median; the mean is pulled up by a few huge winners (CoreWeave +300%)."],
   ["Medium", "Shorting after week one against QQQ worked for the typical deal.", "Short day 5 to day 63 against QQQ: median +17%, Wilcoxon p = 0.03, hit rate 70%. The mean's CI includes zero (−6% to +20%), so one big winner can wipe out many small gains."],
   ["Low", "Buying the open is the worst entry.", "Open to day-1 close −1.1% (CI −4.3% to +2.2%); 60% of debuts close below their open; open to day 63 −11% median. Consistent, but not significant on its own."],
   ["Low", "Strong first weeks do not predict strong months.", "Day 1 to 5 against day 5 to 63 has a rank correlation of 0.09 (p = 0.57). A squeeze says nothing about the fade that follows."],
   ["Low", "Market cap, sector, season, rates and float are tilts, not effects.", "The medians differ a lot (consumer internet −25% by day 63, software −3%), but no Kruskal-Wallis test survives correction (q ≥ 0.52) and float % shows no relationship at all."],
   ["Low", "No pre-IPO liquidity drain on average.", "Across 11 large listings Bitcoin rose 3.6% in the ten sessions before (p = 0.67) and gold was flat. The week after listing was soft (S&P −1.2%, VIX +2.6) and days 6 to 20 rebounded (S&P +3.1%), but nothing survives correction (q > 0.3) and CoreWeave's April 2025 timing drives much of it."],
   ["Low", "The opening hour leans on the index.", "QQQ, SPY and small caps fell in the opening hour of all four large recent IPOs (about −0.2% to −0.3% abnormal). Four observations."],
   ["Medium", "For Anthropic: decide after the pricing.", "Above $78 puts it in the hot-deal group: bigger pop, weaker three months, and a conditional fade from day 5 with a per-trade Sharpe around 0.4. At or below the range, the cohort shows no fade edge. Either way it is one name, so size for low confidence."]]
  .forEach(([c, b, t]) => { const li = H("li", "", null, L); chip(li, c); H("b", "", " " + b + " ", li); li.append(document.createTextNode(t)); }); })();

/* ---------- trade map ---------- */
legend($("#lg-conf"), [{ name: "High confidence", color: "var(--st-good)" }, { name: "Medium", color: "var(--st-warn)" }, { name: "Low", color: "var(--muted)" }], true);
const SROWS = ST.strategies.map(s => ({ label: s.name, v: s.mean, lo: s.ci_mean[0], hi: s.ci_mean[1], color: CONF[s.confidence],
  tip: [{ v: pct(s.mean, 1), l: "mean per trade" }, { v: `${pct(s.ci_mean[0], 1)} to ${pct(s.ci_mean[1], 1)}`, l: "95% CI" }, { v: pct(s.median, 1), l: "median" }, { v: (s.hit * 100).toFixed(0) + "%", l: "hit rate" },
        { v: fp(s.p_wilcoxon), l: "Wilcoxon p" }, { v: s.sr_trade.toFixed(2), l: "Sharpe per trade" }, { v: s.confidence, l: "confidence" }] }));
register(() => forest($("#ch-forest"), { rows: SROWS, xmin: -.3, xmax: .6, xticks: [-.2, 0, .2, .4, .6], xfmt: v => pct(v), fmt: v => pct(v, 1), aria: "Mean return per strategy with 95% confidence intervals" }));
(() => { const host = $("#tb-strat"), t = H("table", "", null, host), th = H("tr", "", null, H("thead", "", null, t));
  ["Strategy", "n", "Mean", "95% CI", "Median", "Hit", "p(t)", "p(W)", "Sharpe / trade", "Ann.-equiv.", "Realistic", "Confidence"].forEach(h => H("th", "", h, th)); const tb = H("tbody", "", null, t);
  ST.strategies.forEach(s => { const tr = H("tr", "", null, tb); H("td", "lab", s.name, tr); H("td", "n", String(s.n), tr); heatCell(H("td", "", "", tr), s.mean, .3);
    H("td", "n", `${pct(s.ci_mean[0])} to ${pct(s.ci_mean[1])}`, tr); heatCell(H("td", "", "", tr), s.median, .3); H("td", "n", (s.hit * 100).toFixed(0) + "%", tr);
    H("td", "n", fp(s.p_t), tr); H("td", "n", fp(s.p_wilcoxon), tr); H("td", "n", s.sr_trade.toFixed(2), tr); H("td", "n", s.sr_ann_equiv.toFixed(2), tr); H("td", "n", s.sr_realistic.toFixed(2), tr);
    chip(H("td", "", "", tr), s.confidence); }); })();
(() => { const host = $("#tb-sub"), t = H("table", "", null, host), th = H("tr", "", null, H("thead", "", null, t));
  ["Trade", "n", "Mean", "95% CI", "Hit", "p(W)", "Sharpe / trade", "Confidence"].forEach(h => H("th", "", h, th)); const tb = H("tbody", "", null, t);
  Object.entries(ST.subsets).forEach(([k, g]) => { const r = H("tr", "grp", null, tb); const h = H("th", "", `${k} · n = ${g.n}`, r); h.colSpan = 8;
    g.rows.forEach(s => { const tr = H("tr", "", null, tb); H("td", "lab", s.name, tr); H("td", "n", String(s.n), tr); heatCell(H("td", "", "", tr), s.mean, .3);
      H("td", "n", s.ci_mean ? `${pct(s.ci_mean[0])} to ${pct(s.ci_mean[1])}` : "n/a", tr); H("td", "n", (s.hit * 100).toFixed(0) + "%", tr); H("td", "n", fp(s.p_wilcoxon), tr);
      H("td", "n", s.sr_trade != null ? s.sr_trade.toFixed(2) : "n/a", tr); chip(H("td", "", "", tr), s.confidence); }); }); })();
const XROWS = XA.trades.map(t => { const w = t.trade.startsWith("Short") ? "pre" : t.trade.includes("T+1 ") ? "post" : "late", sg = t.trade.startsWith("Short") ? -1 : 1;
  const v = XA.daily[t.asset][w].values.filter(x => x != null).map(x => x * sg), ci = bootMean(v), c = t.p_perm < .05 ? "Medium" : t.p_perm < .1 ? "Medium" : "Low";
  return { label: `${t.asset.replace(/ \(.*\)/, "")}: ${t.trade}`, v: t.mean, lo: ci[0], hi: ci[1], color: CONF[c],
    tip: [{ v: pct(t.mean, 1), l: "mean per event" }, { v: `${pct(ci[0], 1)} to ${pct(ci[1], 1)}`, l: "95% CI" }, { v: pct(t.excess_vs_typical, 1), l: "vs a typical window" }, { v: (t.hit * 100).toFixed(0) + "%", l: "hit rate" },
          { v: fp(t.p_perm), l: "permutation p" }, { v: t.sr_trade.toFixed(2), l: "Sharpe per event" }, { v: t.sr_realistic.toFixed(2), l: "realistic annual Sharpe" }] }; });
register(() => forest($("#ch-forest-x"), { rows: XROWS, xmin: -.15, xmax: .3, xticks: [-.1, 0, .1, .2, .3], xfmt: v => pct(v), fmt: v => pct(v, 1), aria: "Cross-asset trades around listings with 95% CIs" }));
(() => { const host = $("#tb-cal"), t = H("table", "", null, host), th = H("tr", "", null, H("thead", "", null, t)); const a = D.all;
  const hist = { 0: `median pop ${pct(a.pop)}; 60% close below the open`, 4: `median ${pct(a.r5)} from day-1 close`, 20: `median ${pct(a.r21, 1)}`, 62: `median ${pct(a.r63)}; 58% have traded below offer`, 125: `median ${pct(a.r126)}` };
  ["Event", "Trading day", "Date", "Cohort at this point"].forEach(h => H("th", "", h, th)); const tb = H("tbody", "", null, t);
  D.ant_cal.forEach(c => { const tr = H("tr", "", null, tb); H("td", "lab", c.label, tr); H("td", "n", c.day < 0 ? "T−1" : "Day " + (c.day + 1), tr); H("td", "n", c.date, tr); const td = H("td", "n", hist[c.day] || "", tr); td.style.textAlign = "left"; }); })();

/* ---------- path with CI band ---------- */
legend($("#lg-band"), [{ name: "Median, all IPOs (95% CI shaded)", color: "var(--s1)" }, { name: "Median vs QQQ", color: "var(--s2)" }, { name: "SpaceX", color: "var(--ink)" }]);
register(() => { const b = ST.band, xs = b.map(r => r.d);
  lineChart($("#ch-band"), { xs, x0: 1, x1: 252, ymin: 50, ymax: 130, yticks: [60, 80, 100, 120], base: 100, yfmt: v => v, xticks: XT, h: 320, vmarks: [{ x: 126, l: "lock-up ≈ day 126" }],
    tfmt: v => num(v - 100, 1) + "%", xtitle: x => `Day ${x} · n = ${b[x - 1] ? b[x - 1].n : ""}`, aria: "Median IPO path with confidence band",
    band: { lo: b.map(r => 100 + r.lo * 100), hi: b.map(r => 100 + r.hi * 100), color: "var(--s1)" },
    series: [{ name: "Median", color: "var(--s1)", vals: b.map(r => 100 + r.med * 100) }, { name: "Median vs QQQ", color: "var(--s2)", vals: b.map(r => 100 + r.xmed * 100) },
             { name: "SpaceX", color: "var(--ink)", vals: xs.map(d => D.bucket_paths.SpaceX[d - 1] ?? null), top: true }] }); });
register(() => forest($("#ch-days"), { rows: ST.daily.map(r => ({ label: "Day " + r.day, v: r.mean, lo: r.ci[0], hi: r.ci[1], color: r.p_t < .05 ? "var(--neg)" : "var(--s1)",
  tip: [{ v: pct(r.mean, 2), l: "mean" }, { v: pct(r.median, 2), l: "median" }, { v: (r.hit * 100).toFixed(0) + "%", l: "up days" }, { v: fp(r.p_t), l: "t-test p" }, { v: pct(r.xmean, 2), l: "mean vs QQQ" }] })),
  xmin: -.06, xmax: .07, xticks: [-.05, 0, .05], xfmt: v => pct(v), fmt: v => pct(v, 1), aria: "Mean daily return days 2 to 10" }));
heatTable($("#tb-bucket"), [{ rows: D.bucket, ci: ciFrom("Market cap") }], DCOLS); kwLine($("#kw-bucket"), ["Market cap"]);

/* ---------- float & demand ---------- */
const CB = Object.fromEntries(D.cohort.map(c => [c.ticker, c]));
register(() => scatter($("#ch-rev"), { aria: "Price revision vs day-1 pop", xlabel: "Offer vs midpoint of first filed range", xmin: -.5, xmax: .6, ymin: -.2, ymax: 1.6,
  xticks: [-.4, -.2, 0, .2, .4], yticks: [0, .5, 1, 1.5], xfmt: v => pct(v), yfmt: v => pct(v),
  pts: ST.cohort_terms.filter(t => t.revision_pct != null).map(t => { const c = CB[t.ticker]; return { x: t.revision_pct, y: c.d1_pop, color: `var(--${(c.r63 ?? 0) >= 0 ? "pos" : "neg"})`, title: t.name,
    rows: [{ v: pct(t.revision_pct), l: "offer vs first range midpoint" }, { v: pct(c.d1_pop), l: "day-1 pop" }, { v: pct(c.r63), l: "day 63 from day-1 close" }, { v: pct(t.float_pct, 1), l: "float" }, { v: t.demand || "n/a", l: "" }] }; }) }));
(() => { const rows = [], G = ST.groups, add = (g, key, lab) => { const r = G[g].rows.find(x => x.key === key); if (!r) return; rows.push({ header: true, label: `${lab} · n = ${r.n}` });
  [["pop", "Day-1 pop"], ["r21", "Day 21"], ["r63", "Day 63"], ["r126", "Day 126"]].forEach(([k, l]) => rows.push({ label: l, v: r[k], lo: r[k + "_ci"][0], hi: r[k + "_ci"][1], color: r[k] >= 0 ? "var(--pos)" : "var(--neg)",
    tip: [{ v: pct(r[k], 1), l: "median" }, { v: `${pct(r[k + "_ci"][0])} to ${pct(r[k + "_ci"][1])}`, l: "95% CI" }] })); };
  add("Pricing vs range", "Priced above initial range", "Priced above first range"); add("Pricing vs range", "At or below initial range", "At or below first range");
  add("Float %", "Float <8%", "Float under 8% (Anthropic ≈ 4.5%)"); add("Float %", "Float >15%", "Float over 15%");
  register(() => forest($("#ch-deal"), { rows, xmin: -.5, xmax: .7, xticks: [-.4, -.2, 0, .2, .4, .6], xfmt: v => pct(v), fmt: v => pct(v), aria: "Deal structure medians with CIs" })); })();
heatTable($("#tb-deal"), [{ title: "Pricing against first filed range", rows: ST.groups["Pricing vs range"].rows, ci: ciFrom("Pricing vs range") }, { title: "Float (deal size / market cap)", rows: ST.groups["Float %"].rows, ci: ciFrom("Float %") }], DCOLS);
kwLine($("#kw-deal"), ["Pricing vs range", "Float %"]);

/* ---------- intraday ---------- */
const HR = [9, 10, 11, 12, 13, 14, 15], hl = h => `${h}:30`;
register(() => scatter($("#ch-open"), { aria: "Opening pop vs open-to-close", xlabel: "Opening print vs offer", xmin: -.2, xmax: 1.8, ymin: -.4, ymax: .6, xticks: [0, .5, 1, 1.5], yticks: [-.4, -.2, 0, .2, .4, .6], xfmt: v => pct(v, 0, false), yfmt: v => pct(v),
  pts: I.daily.map(d => ({ x: d.open_pop, y: d.oc1, color: `var(--${d.oc1 >= 0 ? "pos" : "neg"})`, title: `${d.name} · ${d.ipo_date}`,
    rows: [{ v: pct(d.open_pop), l: "opening print vs offer" }, { v: pct(d.oc1), l: "open to close" }, { v: pct(d.close_vs_high), l: "close vs day high" }, { v: pct(d.d1_pop), l: "close vs offer" }] })) }));
register(() => { const sp = I.hourly.spacex, xs = sp.map((_, i) => i), days = []; sp.forEach((b, i) => { const dd = b.ts.slice(0, 5); if (!days.length || days[days.length - 1].d !== dd) days.push({ d: dd, i }); });
  lineChart($("#ch-spx"), { xs, x0: 0, x1: sp.length - 1, ymin: 90, ymax: 170, yticks: [100, 120, 140, 160], base: 100, yfmt: v => num(v - 100, 0) + "%", xticks: days.map((d, k) => ({ v: d.i, l: "D" + (k + 1) })), h: 300,
    vmarks: days.slice(1).map(d => ({ x: d.i })), tfmt: v => num(v - 100, 1) + "%", xtitle: x => sp[x].ts + " ET", aria: "SpaceX hourly vs offer", series: [{ name: "Hourly close vs $135 offer", color: "var(--ink)", vals: sp.map(b => b.c * 100) }] }); });
const P = I.hourly.profile, byH = (k, key, minN) => HR.map(h => { const r = P[k].find(x => x.hr === h); return r && r.n >= minN ? r[key] : null; }), nOf = (k, i) => { const r = P[k].find(x => x.hr === HR[i]); return r ? [{ v: String(r.n), l: "IPOs in sample" }] : []; };
const DS = [{ n: "Day 1", c: "var(--s1)", k: 1 }, { n: "Day 2", c: "var(--s2)", k: 2 }, { n: "Day 3", c: "var(--s3)", k: 3 }];
legend($("#lg-vol"), DS.map(s => ({ name: s.n, color: s.c })), true); legend($("#lg-bar"), DS.map(s => ({ name: s.n, color: s.c })), true);
register(() => colsChart($("#ch-vol"), { cats: HR.map(hl), ymin: 0, ymax: .5, yticks: [0, .1, .2, .3, .4, .5], yfmt: v => pct(v, 0, false), tfmt: v => pct(v, 0, false), h: 260, aria: "Share of daily volume by hourly bar",
  series: DS.map(s => ({ name: s.n, color: () => s.c, vals: byH(s.k, "vol", s.k === 1 ? 4 : 1), extra: i => nOf(s.k, i) })) }));
register(() => colsChart($("#ch-bar"), { cats: HR.map(hl), ymin: -.04, ymax: .04, yticks: [-.04, -.02, 0, .02, .04], yfmt: v => pct(v, 0), tfmt: v => pct(v, 1), h: 260, aria: "Median return of each hourly bar",
  series: DS.map(s => ({ name: s.n, color: () => s.c, vals: byH(s.k, "bar_ret", s.k === 1 ? 4 : 1), extra: i => nOf(s.k, i) })) }));
heatTable($("#tb-intra"), [{ rows: I.by_open.map(r => ({ ...r })).concat([{ ...I.all, key: "All 43 IPOs", names: [] }]) }],
  [{ k: "open_pop", h: "Open vs offer", scale: .6 }, { k: "d1_pop", h: "Close vs offer", scale: .6 }, { k: "oc1", h: "Open to close", scale: .2 }, { k: "close_vs_high", h: "Close vs high", scale: .2 },
   { k: "pct_below_open", h: "Below open", fmt: "plain" }, { k: "open_to_D21", h: "Open to day 21", scale: .3 }, { k: "open_to_D63", h: "Open to day 63", scale: .3 }]);

/* ---------- sectors ---------- */
heatTable($("#tb-sector"), [{ rows: D.sector, ci: ciFrom("Sector") }], COLS); kwLine($("#kw-sector"), ["Sector"]);
const mini = $("#mini");
D.sector.forEach(s => { const c = H("div", "", null, mini); H("h3", "", s.key, c); H("div", "sub", `n = ${s.n} · day 63 median ${pct(s.r63)} · day 126 ${pct(s.r126)}`, c); const h = H("div", "chart", null, c);
  register(() => lineChart(h, { xs: dayX, x0: 1, x1: 252, ymin: 40, ymax: 160, yticks: [50, 100, 150], base: 100, yfmt: v => v, xticks: [{ v: 1, l: "D1" }, { v: 63, l: "3m" }, { v: 126, l: "6m" }, { v: 252, l: "12m" }], h: 170, ml: 34, noend: true,
    tfmt: v => num(v - 100, 1) + "%", xtitle: x => `Day ${x}`, aria: s.key + " median path",
    series: [{ name: "All IPOs", color: "var(--muted)", vals: D.all_path, w: 1.5 }, { name: s.key, color: "var(--s1)", vals: D.sector_paths[s.key], w: 2.5, top: true }] })); });

/* ---------- seasonality ---------- */
const QS = [{ name: "Day-1 pop (vs offer)", k: "pop", color: "var(--s1)" }, { name: "Day 63 (from day-1 close)", k: "r63", color: "var(--s2)" }, { name: "Day 126 (from day-1 close)", k: "r126", color: "var(--s3)" }];
legend($("#lg-q"), QS.map(s => ({ name: s.name, color: s.color })), true);
register(() => colsChart($("#ch-q"), { cats: D.quarter.map(q => q.key), ymin: -.4, ymax: .5, yticks: [-.4, -.2, 0, .2, .4], yfmt: v => pct(v), tfmt: v => pct(v), aria: "IPO outcomes by listing quarter",
  series: QS.map(s => ({ name: s.name, color: () => s.color, vals: D.quarter.map(q => q[s.k]), extra: i => { const g = ST.groups["Listing quarter"].rows.find(r => r.key === D.quarter[i].key); const ci = g && g[s.k + "_ci"]; return [{ v: String(D.quarter[i].n), l: "IPOs" }].concat(ci ? [{ v: `${pct(ci[0])} to ${pct(ci[1])}`, l: "95% CI" }] : []); } })) }));
const MN = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
register(() => colsChart($("#ch-month"), { cats: MN, ymin: -1, ymax: 2.2, yticks: [-1, 0, 1, 2], yfmt: v => v + "%", tfmt: v => num(v, 2) + "%", h: 260, aria: "S&P 500 average return by calendar month",
  series: [{ name: "Average monthly return", color: i => (i === 10 || i === 11) ? "var(--s1)" : "var(--axis)", vals: D.spx_month.map(m => m.mean), label: i => i === 10 || i === 11, extra: i => [{ v: D.spx_month[i].hit + "%", l: "months positive" }] }] }));
(() => { const g = D.spx_nov15, rows = [["All years", g.all], ["Midterm years (post-election)", g.midterm], ["Other years", g.other]];
  const host = $("#tb-nov"), t = H("table", "", null, host), th = H("tr", "", null, H("thead", "", null, t));
  ["", "Years", "+1 month", "+3 months", "+12 months", "Up (3m)"].forEach(h => H("th", "", h, th)); const tb = H("tbody", "", null, t);
  rows.forEach(([k, s]) => { const tr = H("tr", "", null, tb); H("td", "lab", k, tr); H("td", "n", String(s.n), tr);
    [s.m1 / 100, s.m3 / 100, s.m12 / 100].forEach(v => heatCell(H("td", "", "", tr), v, .15)); H("td", "n", s.h3.toFixed(0) + "%", tr); }); })();

/* ---------- regimes ---------- */
(() => { const c = D.current, h = $("#chips");
  [["US 10Y yield", c.y10.toFixed(2) + "%", `${num(c.y10_3m * 100, 0)}bp in 3 months`, "Rising"], ["VIX", c.vix.toFixed(1), "Mid band (16 to 22)", "Mid"],
   ["Fed funds", c.fed_level.toFixed(2) + "%", `${num(c.fed_6m * 100, 0)}bp in 6 months`, "Hold / turning"], ["S&P 500 vs 200-day", pct(c.spx_vs_200, 1), `${pct(c.spx_off_high, 1)} from high`, "Above"]]
  .forEach(([k, v, w, tag]) => { const d = H("div", "chip", null, h); H("div", "k", k, d); const vv = H("div", "v", v, d); H("span", "tag", tag, vv); H("div", "w", w, d); }); })();
heatTable($("#tb-regime"), [{ title: "10-year yield trend", rows: D.yld, ci: ciFrom("10Y trend") }, { title: "Fed policy", rows: D.fed }, { title: "VIX level", rows: D.vix, ci: ciFrom("VIX") }], COLS);
kwLine($("#kw-regime"), ["10Y trend", "VIX"]);
const C = D.cohort, t0 = Date.UTC(2020, 8, 1), t1 = Date.UTC(2026, 11, 31), tm = s => { const [y, m, d] = s.split("-").map(Number); return Date.UTC(y, m - 1, d || 1); };
const yrT = []; for (let y = 2021; y <= 2026; y++) yrT.push({ v: Date.UTC(y, 0, 1), l: String(y) });
register(() => { const host = $("#ch-scatter"); host.replaceChildren();
  const W = host.clientWidth || 700, Ht = 300, m = { l: 44, r: 14, t: 10, b: 8 }, iw = W - m.l - m.r, ih = Ht - m.t - m.b;
  const X = v => m.l + (v - t0) / (t1 - t0) * iw, yv = v => Math.max(-1, Math.min(1, v)), YY = v => m.t + (1 - yv(v)) / 2 * ih;
  const svg = S("svg", { width: W, height: Ht, viewBox: `0 0 ${W} ${Ht}`, role: "img", "aria-label": "Day 63 return of each IPO against listing date" }, host);
  [-1, -.5, 0, .5, 1].forEach(t => { S("line", { x1: m.l, x2: W - m.r, y1: YY(t), y2: YY(t), style: `stroke:${t === 0 ? "var(--axis)" : "var(--grid)"};stroke-width:1` }, svg); const tx = S("text", { x: m.l - 8, y: YY(t) + 4, "text-anchor": "end" }, svg); tx.textContent = pct(t); });
  yrT.forEach(t => S("line", { x1: X(t.v), x2: X(t.v), y1: m.t, y2: m.t + ih, style: "stroke:var(--grid);stroke-width:1" }, svg));
  S("line", { x1: X(tm("2026-11-19")), x2: X(tm("2026-11-19")), y1: m.t, y2: m.t + ih, style: "stroke:var(--ink2);stroke-width:1;stroke-dasharray:2 3" }, svg);
  const ant = S("text", { x: X(tm("2026-11-19")) - 5, y: m.t + 12, "text-anchor": "end", class: "strong" }, svg); ant.textContent = "ANT 19 Nov";
  const pts = C.filter(c => c.r63 != null).map(c => ({ c, x: X(tm(c.ipo_date)), y: YY(c.r63) }));
  pts.forEach(p => S("circle", { cx: p.x, cy: p.y, r: 5, style: `fill:var(--${p.c.r63 >= 0 ? "pos" : "neg"});stroke:var(--surface);stroke-width:2` }, svg));
  const hi = S("circle", { r: 8, fill: "none", style: "stroke:var(--ink);stroke-width:2", visibility: "hidden" }, svg), ov = S("rect", { x: m.l, y: m.t, width: iw, height: ih, fill: "transparent" }, svg);
  ov.addEventListener("pointermove", e => { const r = ov.getBoundingClientRect(), px = e.clientX - r.left + m.l, py = e.clientY - r.top + m.t; let b = null, bd = 1e9;
    pts.forEach(p => { const d = Math.hypot(p.x - px, p.y - py); if (d < bd) { bd = d; b = p; } });
    if (b && bd < 40) { hi.setAttribute("cx", b.x); hi.setAttribute("cy", b.y); hi.setAttribute("visibility", "visible"); const c = b.c;
      showTT(e, `${c.name} · ${c.ipo_date}`, [{ v: pct(c.r63), l: "day 63 from day-1 close" }, { v: pct(c.d1_pop), l: "day-1 pop" }, { v: c.sector, l: "" }, { v: c.y10.toFixed(2) + "%", l: `10Y (${num(c.y10_3m_chg * 100, 0)}bp / 3m)` }, { v: c.vix.toFixed(0), l: "VIX" }]); }
    else { hi.setAttribute("visibility", "hidden"); hideTT(); } });
  ov.addEventListener("pointerleave", () => { hi.setAttribute("visibility", "hidden"); hideTT(); });
  const mm = D.macro_monthly, xs = mm.map(r => tm(r.d + "-15"));
  lineChart($("#ch-rates"), { xs, x0: t0, x1: t1, ymin: 0, ymax: 6, yticks: [0, 2, 4, 6], yfmt: v => v + "%", xticks: yrT, h: 150, tfmt: v => v.toFixed(2) + "%", noend: true,
    xtitle: x => new Date(x).toISOString().slice(0, 7), aria: "US 10-year yield and fed funds", vmarks: [{ x: tm("2026-11-19") }],
    series: [{ name: "Fed funds", color: "var(--s2)", vals: mm.map(r => r.ff) }, { name: "US 10Y", color: "var(--s1)", vals: mm.map(r => r.y10) }] }); });

/* ---------- cross-asset ---------- */
(() => { const host = $("#tb-xa"), t = H("table", "", null, host), th = H("tr", "", null, H("thead", "", null, t)), W4 = ["pre", "day0", "post", "late"];
  H("th", "", "", th); W4.forEach(w => H("th", "", XA.windows[w], th)); const tb = H("tbody", "", null, t);
  Object.entries(XA.daily).forEach(([a, r]) => { const tr = H("tr", "", null, tb); H("td", "lab", a, tr);
    W4.forEach(w => { const c = r[w], td = H("td", "h", fmtA(a, c.mean), tr), sc = /10Y/.test(a) ? 15 : /VIX/.test(a) ? 3 : .03, tt0 = Math.min(1, Math.abs(c.excess) / sc) * 62;
      td.style.background = `color-mix(in srgb, var(--${c.excess >= 0 ? "pos" : "neg"}) ${tt0.toFixed(0)}%, var(--mid))`; if (c.p_perm < .05) td.style.fontWeight = 700;
      const tip = e => showTT(e, `${a} · ${XA.windows[w]}`, [{ v: fmtA(a, c.mean), l: "average across 11 listings" }, { v: fmtA(a, c.excess), l: "vs a typical window" }, { v: fmtA(a, c.median), l: "median" },
        { v: (c.hit * 100).toFixed(0) + "%", l: "share up" }, { v: fp(c.p_perm), l: "permutation p" }, { v: fp(c.q), l: "BH q (56 tests)" }, { v: `${fmtA(a, c.loo_min)} to ${fmtA(a, c.loo_max)}`, l: "leave-one-out excess" }, { v: fmtA(a, c.spacex), l: "SpaceX" }]);
      td.addEventListener("pointermove", tip); td.addEventListener("pointerleave", hideTT); }); }); })();
const mx = $("#mini-x");
["Nasdaq 100 (QQQ)", "S&P 500 (SPY)", "Small caps (IWM)", "Speculative growth (ARKK)", "Software (IGV)", "Bitcoin", "Gold (GLD)", "VIX (points)"].forEach(a => {
  const p = XA.paths[a], c = H("div", "", null, mx); H("h3", "", a, c); const r = XA.daily[a]; H("div", "sub", `T+1 to T+5: ${fmtA(a, r.post.mean)} (p ${fp(r.post.p_perm)}) · T+6 to T+20: ${fmtA(a, r.late.mean)} (p ${fp(r.late.p_perm)})`, c); const h = H("div", "chart", null, c);
  const xs = p.band.map(b => b.t), k = isPts(a) ? 1 : 100, all = p.band.flatMap(b => [b.lo, b.hi]).concat(p.spacex.filter(x => x != null)).map(x => x * k);
  let lo = Math.min(...all), hi = Math.max(...all); const pad = (hi - lo) * .08; lo -= pad; hi += pad; const step = (hi - lo) > 30 ? 10 : (hi - lo) > 12 ? 5 : (hi - lo) > 6 ? 2 : 1, yt = [];
  for (let v = Math.ceil(lo / step) * step; v <= hi; v += step) yt.push(v);
  register(() => lineChart(h, { xs, x0: -10, x1: 20, ymin: lo, ymax: hi, yticks: yt, base: 0, yfmt: v => (v > 0 ? "+" : "") + v + (isPts(a) ? "" : "%"), xticks: [{ v: -10, l: "T−10" }, { v: 0, l: "T0" }, { v: 10, l: "T+10" }, { v: 20, l: "T+20" }],
    h: 180, ml: 40, noend: true, vmarks: [{ x: 0 }], tfmt: v => num(v, 1) + (isPts(a) ? " pts" : "%"), xtitle: x => `T${x >= 0 ? "+" : "−"}${Math.abs(x)}`, aria: a + " event path",
    band: { lo: p.band.map(b => b.lo * k), hi: p.band.map(b => b.hi * k), color: "var(--s1)" },
    series: [{ name: "Average", color: "var(--s1)", vals: p.band.map(b => b.mean * k) }, { name: "SpaceX", color: "var(--ink)", vals: p.spacex.map(x => x == null ? null : x * k), w: 1.5, top: true }] })); });
(() => { const host = $("#tb-hour"), t = H("table", "", null, host), th = H("tr", "", null, H("thead", "", null, t));
  ["Asset", "Large: avg", "Large: share down", "Large: t", "All 14: avg", "All 14: share down", "SpaceX"].forEach(h => H("th", "", h, th)); const tb = H("tbody", "", null, t);
  const sx = XA.hourly.find(r => r.ticker === "SPCX");
  Object.entries(XA.hourly_summary).forEach(([a, s]) => { const tr = H("tr", "", null, tb); H("td", "lab", a, tr); const bp = v => v == null || Number.isNaN(v) ? "n/a" : num(v * 1e4, 0) + "bp";
    H("td", "n", bp(s.big.mean_abn), tr); H("td", "n", s.big.n ? (s.big.hit_neg * 100).toFixed(0) + "% of " + s.big.n : "n/a", tr); H("td", "n", s.big.t == null ? "n/a" : s.big.t.toFixed(1), tr);
    H("td", "n", bp(s.all.mean_abn), tr); H("td", "n", s.all.n ? (s.all.hit_neg * 100).toFixed(0) + "% of " + s.all.n : "n/a", tr); H("td", "n", sx && sx[a] ? bp(sx[a].abn) : "n/a", tr); }); })();
(() => { const SH = XA.spacex_hourly, keys = ["Nasdaq 100 (QQQ)", "Bitcoin", "Gold (GLD)", "ARKK"], src = { "Nasdaq 100 (QQQ)": "QQQ", Bitcoin: "Bitcoin", "Gold (GLD)": "Gold (GLD)", ARKK: "ARKK" }, col = ["var(--s1)", "var(--s2)", "var(--s3)", "var(--s4)"];
  legend($("#lg-sh"), keys.map((k, i) => ({ name: k, color: col[i] })));
  const q = SH.QQQ, n = q.length, xs = q.map((_, i) => i), days = []; q.forEach((b, i) => { const dd = b.ts.slice(0, 5); if (!days.length || days[days.length - 1].d !== dd) days.push({ d: dd, i }); });
  const li = days.findIndex(d => d.d === "06-12");
  register(() => lineChart($("#ch-sh"), { xs, x0: 0, x1: n - 1, ymin: 94, ymax: 106, yticks: [95, 100, 105], base: 100, yfmt: v => v, xticks: days.map(d => ({ v: d.i, l: d.d.replace("-", "/") })), h: 260, noend: true,
    vmarks: li >= 0 ? [{ x: days[li].i, l: "SpaceX lists" }] : [], tfmt: v => num(v - 100, 2) + "%", xtitle: x => (q[x] ? q[x].ts : "") + " ET", aria: "Cross-asset hourly around SpaceX listing",
    series: keys.map((k, i) => { const s = SH[src[k]]; const b = s[0].v; return { name: k, color: col[i], vals: xs.map(j => s[j] ? s[j].v / b * 100 : null) }; }) })); })();
register(() => { const R = XA.runup.filter(r => !/IPO ETF/.test(r.asset));
  rowsChart($("#ch-runup"), { cats: R.map(r => r.asset), xmin: -50, xmax: 50, mr: 120, xticks: [-50, -25, 0, 25, 50], xfmt: v => (v + 50) + "th", ml: 170, aria: "Anthropic run-up percentile rank",
    tfmt: v => (v + 50).toFixed(0) + "th pct", lab: (ci, si, v) => `${(v + 50).toFixed(0)}th (${fmtA(R[ci].asset, R[ci].value)})`,
    series: [{ name: "Percentile rank vs all 14-session windows", color: ci => R[ci].pct_rank < .5 ? "var(--neg)" : "var(--pos)", vals: R.map(r => (r.pct_rank - .5) * 100) }] }); });
legend($("#lg-r"), [{ name: "First-day return", color: "var(--s1)" }, { name: "Aftermarket return", color: "var(--s2)" }], true);
register(() => colsChart($("#ch-r"), { cats: ["3Q25", "4Q25", "1Q26", "2Q26", "3Q26"], ymin: -15, ymax: 30, yticks: [-10, 0, 10, 20, 30], yfmt: v => v + "%", tfmt: v => num(v, 1) + "%", h: 230, aria: "Renaissance IPO class returns",
  series: [{ name: "First-day return", color: () => "var(--s1)", vals: [17.0, 12.0, 26.0, 15.2, 6.2] }, { name: "Aftermarket return", color: () => "var(--s2)", vals: [11.2, 0.9, -10.0, -3.9, -5.7] }] }));

/* ---------- Anthropic decision table ---------- */
(() => { const G = ST.groups["Pricing vs range"].rows, hot = G.find(r => r.key.startsWith("Priced above")), cold = G.find(r => r.key.startsWith("At or below")), fs = ST.subsets["Priced above initial range"].rows[2];
  const host = $("#tb-tree"), t = H("table", "", null, host), th = H("tr", "", null, H("thead", "", null, t));
  ["If Anthropic prices…", "n", "Pop", "Day 21", "Day 63", "Day 126", "Historical edge for a non-allocated trader"].forEach(h => H("th", "", h, th)); const tb = H("tbody", "", null, t);
  [["Above $78 (above range)", hot, `Fade from day 5 to day 63: mean ${pct(fs.mean, 1)}, hit ${(fs.hit * 100).toFixed(0)}%, Wilcoxon p ${fp(fs.p_wilcoxon)}, Sharpe ${fs.sr_trade.toFixed(2)} per trade`],
   ["$70 to $78, or below", cold, "No reliable fade; median day 63 was positive. Stand aside or trade the cross-asset rebound."]].forEach(([k, r, txt]) => {
    const tr = H("tr", "", null, tb); H("td", "lab", k, tr); H("td", "n", String(r.n), tr); ["pop", "r21", "r63", "r126"].forEach(m => heatCell(H("td", "", "", tr), r[m], m === "pop" ? .6 : .4));
    const td = H("td", "n", txt, tr); td.style.whiteSpace = "normal"; td.style.textAlign = "left"; td.style.minWidth = "240px"; }); })();

/* ---------- table view ---------- */
(() => { const host = $("#tb-all"), t = H("table", "", null, host), th = H("tr", "", null, H("thead", "", null, t)), TM = Object.fromEntries(ST.cohort_terms.map(x => [x.ticker, x]));
  ["Company", "Sector", "Listed", "Offer $", "Cap $B", "Float", "vs range", "Pop", "Day 5", "Day 21", "Day 63", "Day 126"].forEach(h => H("th", "", h, th)); const tb = H("tbody", "", null, t);
  C.slice().sort((a, b) => a.ipo_date < b.ipo_date ? -1 : 1).forEach(c => { const tr = H("tr", "", null, tb), tm2 = TM[c.ticker] || {};
    H("td", "lab", `${c.name} (${c.ticker})`, tr); H("td", "n", c.sector, tr).style.textAlign = "left"; H("td", "n", c.ipo_date, tr); H("td", "n", String(c.offer), tr); H("td", "n", c.cap_b >= 100 ? "1,770" : (+c.cap_b).toFixed(1), tr);
    H("td", "n", tm2.float_pct != null ? pct(tm2.float_pct, 1, false) : "n/a", tr); H("td", "n", tm2.demand ? tm2.demand.replace(" range", "") : "n/a", tr);
    [c.d1_pop, c.r5, c.r21, c.r63, c.r126].forEach((v, i) => heatCell(H("td", "", "", tr), v, i ? .4 : .6)); }); })();
document.body.addEventListener("pointerleave", hideTT);
