/* STIR Monitor: calculations and drawings. Maths lives in calc.js (window.STIR). */
(function () {
  const S = window.STIR;
  const CURVES = ["SOFR", "Euribor", "SONIA", "CORRA", "SARON", "Aussie Bills"];
  const HEAT = ["SOFR", "Euribor", "SONIA", "CORRA", "SARON"];
  const DEC = ["SOFR", "Euribor", "SONIA", "CORRA"];
  const COLS = ["U26", "Z26", "H27", "M27", "U27", "Z27", "H28", "M28", "U28", "Z28", "H29", "M29"];
  const PAIRS = [["Z26", "Z27", "Z6Z7"], ["Z27", "Z28", "Z7Z8"], ["Z28", "Z29", "Z8Z9"]];
  const FOMC = ["2026-12-09", "2027-01-27", "2027-03-17", "2027-04-28", "2027-06-09", "2027-07-28", "2027-09-15", "2027-11-17"];
  const BOC = ["2026-12-09", "2027-01-27", "2027-03-03", "2027-04-28", "2027-06-02", "2027-07-21", "2027-09-08", "2027-10-27"];
  const DAILY_TF = ["Day", "Week", "Since"], INTRA_TF = ["15m", "30m", "1h", "Since EU Open"];
  const COLOR = { SOFR: "#ff6fae", Euribor: "#4ade80", SONIA: "#fbbf24", CORRA: "#2dd4bf", SARON: "#fb923c", "Aussie Bills": "#d9c7a3" };
  const DAYS = 10;

  window.STIR_UI = window.STIR_UI || { heat_tf: "Day", sent_tf: "Day", curve: "SOFR", curve_tf: "Day", fed_n: 1, boc_n: 1 };
  const UI = window.STIR_UI;

  /* ------------------------------------------------------------------ calculations */
  dash.calc("chg_d", {
    inputs: ["sofr", "euribor", "sonia", "corra", "saron", "aussie"],
    title: "Outright changes · Day / Week / Since",
    description: "Rate change in bp per contract (−Δprice×100): vs prior session, vs last Friday's settle, and vs the close on the 'Since' date.",
    fn: (sofr, euribor, sonia, corra, saron, aussie) => {
      const since = dash.params().since;
      const input = { SOFR: sofr, Euribor: euribor, SONIA: sonia, CORRA: corra, SARON: saron, "Aussie Bills": aussie };
      const COLS = ["U26", "Z26", "H27", "M27", "U27", "Z27", "H28", "M28", "U28", "Z28", "H29", "M29"];
      const rows = [];
      for (const tf of ["Day", "Week", "Since"]) for (const curve of Object.keys(input)) {
        const by = STIR.byContract(input[curve]);
        const row = { curve, tf };
        for (const c of COLS) row[c] = STIR.changesFor(by[c], tf, since, false);
        rows.push(row);
      }
      return rows;
    },
  });

  dash.calc("chg_i", {
    inputs: ["sofr_5m", "euribor_5m", "sonia_5m", "corra_5m", "saron_5m", "aussie_5m"],
    title: "Outright changes · intraday",
    description: "Rate change in bp per contract vs the 5-minute bar 15 min, 30 min and 1 h before the last one, and vs the first bar after 07:00 London today.",
    fn: (sofr, euribor, sonia, corra, saron, aussie) => {
      const input = { SOFR: sofr, Euribor: euribor, SONIA: sonia, CORRA: corra, SARON: saron, "Aussie Bills": aussie };
      const COLS = ["U26", "Z26", "H27", "M27", "U27", "Z27", "H28", "M28", "U28", "Z28", "H29", "M29"];
      const rows = [];
      for (const tf of ["15m", "30m", "1h", "Since EU Open"]) for (const curve of Object.keys(input)) {
        const by = STIR.byContract(input[curve]);
        const row = { curve, tf };
        for (const c of COLS) row[c] = STIR.changesFor(by[c], tf, null, true);
        rows.push(row);
      }
      return rows;
    },
  });

  dash.calc("dec", {
    inputs: ["sofr", "euribor", "sonia", "corra"],
    title: "Dec-to-Dec spread changes",
    description: "Change in price(front Dec) − price(back Dec) in bp, on the day and since last Friday's settle.",
    fn: (sofr, euribor, sonia, corra) => {
      const input = { SOFR: sofr, Euribor: euribor, SONIA: sonia, CORRA: corra };
      const PAIRS = [["Z26", "Z27", "Z6Z7"], ["Z27", "Z28", "Z7Z8"], ["Z28", "Z29", "Z8Z9"]];
      return Object.keys(input).map((curve) => {
        const by = STIR.byContract(input[curve]);
        const row = { curve };
        for (const [f, b, lab] of PAIRS) {
          row["Day " + lab] = STIR.spreadChange(by[f], by[b], "Day");
          row["Week " + lab] = STIR.spreadChange(by[f], by[b], "Week");
        }
        return row;
      });
    },
  });

  dash.calc("sent", {
    inputs: ["sofr", "euribor", "sonia", "corra", "saron", "aussie"],
    title: "Z27 change by curve",
    description: "Rate change in bp of each curve's Z27 contract vs prior session, last Friday's settle, and 1 week, 1, 3 and 6 months ago.",
    fn: (sofr, euribor, sonia, corra, saron, aussie) => {
      const input = { SOFR: sofr, Euribor: euribor, SONIA: sonia, CORRA: corra, SARON: saron, "Aussie Bills": aussie };
      const rows = [];
      for (const tf of ["Day", "Week", "1W", "1M", "3M", "6M"]) for (const curve of Object.keys(input)) {
        rows.push({ curve, tf, change: STIR.changesFor(STIR.byContract(input[curve]).Z27, tf, null, false) });
      }
      return rows;
    },
  });

  dash.calc("fed", {
    inputs: ["zq"],
    title: "Fed meeting pricing",
    description: "Move priced at each FOMC meeting from 30-day Fed Funds futures (CME FedWatch method), as of each of the last 10 sessions. Δ1D is the change in cumulative bp vs the session before.",
    fn: (zq) => {
      const FOMC = ["2026-12-09", "2027-01-27", "2027-03-17", "2027-04-28", "2027-06-09", "2027-07-28", "2027-09-15", "2027-11-17"];
      const by = STIR.byContract(zq);
      const sessions = [...new Set((by.X26 || []).map((r) => r.session))].sort().reverse().slice(0, 11);
      const pathAt = (s) => {
        const monthly = {};
        for (const code in by) {
          const r = STIR.lastOnOrBefore(by[code], s);
          if (r) monthly[STIR.ymKey(2000 + Number(code.slice(1)), STIR.M[code[0]])] = 100 - r.close;
        }
        return STIR.fomcPath(FOMC, monthly);
      };
      const paths = sessions.map(pathAt);
      const rows = [];
      for (let n = 0; n < paths.length - 1; n++) {
        const prev = Object.fromEntries(paths[n + 1].map((r) => [r.meeting, r.cum]));
        for (const r of paths[n]) rows.push({ days_ago: n, session: sessions[n], meeting: r.meeting, move: r.move, cum: r.cum,
          implied: r.implied, start: Math.round(r.start * 1000) / 1000, d1: prev[r.meeting] == null ? null : STIR.r1(r.cum - prev[r.meeting]) });
      }
      return rows;
    },
  });

  dash.calc("boc", {
    inputs: ["corra"],
    title: "BoC meeting pricing (approximate)",
    description: "Overnight-rate path fitted to the quarterly 3M CORRA strip (U26 to Z27): today's rate and the rate after each BoC meeting, solved by least squares with light smoothing, as of each of the last 10 sessions.",
    fn: (corra) => {
      const BOC = ["2026-12-09", "2027-01-27", "2027-03-03", "2027-04-28", "2027-06-02", "2027-07-21", "2027-09-08", "2027-10-27"];
      const USE = ["U26", "Z26", "H27", "M27", "U27", "Z27"];
      const by = STIR.byContract(corra);
      const sessions = [...new Set((by.Z27 || []).map((r) => r.session))].sort().reverse().slice(0, 11);
      const paths = sessions.map((s) => {
        const strip = {};
        for (const c of USE) { const r = by[c] && STIR.lastOnOrBefore(by[c], s); if (r) strip[c] = 100 - r.close; }
        // The fit needs the front of the strip; without U26, Z26 and H27 it is not identified.
        if (!["U26", "Z26", "H27"].every((c) => c in strip) || Object.keys(strip).length < 5) return [];
        return STIR.stripPath(BOC, strip, s);
      });
      const rows = [];
      for (let n = 0; n < paths.length - 1; n++) {
        const prev = Object.fromEntries(paths[n + 1].map((r) => [r.meeting, r.cum]));
        for (const r of paths[n]) rows.push({ days_ago: n, session: sessions[n], meeting: r.meeting, move: r.move, cum: r.cum,
          implied: r.implied, start: r.start, d1: prev[r.meeting] == null ? null : STIR.r1(r.cum - prev[r.meeting]) });
      }
      return rows;
    },
  });

  dash.calc("spk", {
    inputs: ["speakers"],
    title: "Speaker hawkishness scores",
    description: "Score = average hawkishness of today's speech and the previous four; deviation = today minus the average of the previous four.",
    fn: (speakers) => speakers.map((s) => {
      const last4 = typeof s.last4 === "string" ? JSON.parse(s.last4) : s.last4;
      const avg4 = last4.reduce((a, b) => a + b, 0) / last4.length;
      return { name: s.name, score: Math.round(((avg4 * last4.length + Number(s.hawkish)) / (last4.length + 1)) * 10) / 10,
        speeches: last4.length + 1, avg4: Math.round(avg4 * 10) / 10, deviation: Math.round((Number(s.hawkish) - avg4) * 10) / 10 };
    }),
  });

  /* ------------------------------------------------------------------ helpers */
  const fmt = (v, d = 2) => (v == null || isNaN(v) ? "—" : v === 0 ? (0).toFixed(d) : (v > 0 ? "+" : "−") + Math.abs(v).toFixed(d));
  const enc = encodeURIComponent;
  const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const fdate = (s) => { const [y, m, d] = s.split("-"); return `${d} ${MON[+m - 1]} ${y.slice(2)}`; };
  const el = (tag, attrs = {}, text) => {
    const e = document.createElement(tag);
    for (const k in attrs) if (attrs[k] != null) e.setAttribute(k, attrs[k]);
    if (text != null) e.textContent = text;
    return e;
  };
  const dcls = (v) => (v == null || Math.abs(v) < 0.05 ? "s-zero" : v > 0 ? "s-pos" : "s-neg");
  function heatStyle(v, scale) {
    if (v == null) return { cls: "na", style: "" };
    if (Math.abs(v) < 0.005) return { cls: "zero", style: "" };
    const a = 0.14 + 0.66 * Math.sqrt(Math.min(1, Math.abs(v) / (scale || 1)));
    return { cls: "", style: `background:rgba(${v > 0 ? "34,197,94" : "239,68,68"},${a.toFixed(2)})` };
  }
  const argmaxAbs = (vals) => { let i = -1, b = 0; vals.forEach((v, k) => { if (v != null && Math.abs(v) > b) { b = Math.abs(v); i = k; } }); return i; };
  function placeholder(box, st, h) {
    box.replaceChildren(el("div", { class: "s-ph", style: h ? `min-height:${h}px` : null },
      st.status === "error" ? "Failed to load" : st.note ? "Not enough contracts loaded to price the meetings. Refresh to retry." : st.status === "ok" ? "No data" : "—"));
  }
  function labelCell(curve) {
    const td = el("td", { class: "lab" });
    td.append(el("i", { style: `background:${COLOR[curve]}` }), document.createTextNode(curve));
    return td;
  }
  function heatTable(source, rowKey, cols, fields, rows, keyOf, groups, digits = 2) {
    const all = rows.flatMap((r) => fields.map((f) => r[f])).filter((v) => v != null).map(Math.abs);
    const scale = all.length ? Math.max(...all) : 1;
    const t = el("table", { class: "s-heat", "data-source": source, "data-row-key": rowKey });
    const thead = el("thead");
    if (groups) {
      const g = el("tr"); g.append(el("th"));
      for (const [lab, n] of groups) g.append(el("th", { class: "grp", colspan: n }, lab));
      thead.append(g);
    }
    const h = el("tr"); h.append(el("th"));
    cols.forEach((c, i) => h.append(el("th", { "data-field": fields[i] }, c)));
    thead.append(h);
    const tb = el("tbody");
    for (const r of rows) {
      const tr = el("tr", { "data-key": keyOf(r) });
      tr.append(labelCell(r.curve));
      const vals = fields.map((f) => r[f]), mi = argmaxAbs(vals);
      vals.forEach((v, i) => { const hs = heatStyle(v, scale); tr.append(el("td", { class: `hc ${hs.cls}${i === mi ? " max" : ""}`, style: hs.style || null }, fmt(v, digits))); });
      tb.append(tr);
    }
    t.append(thead, tb);
    const wrap = el("div", { class: "s-scroll" }); wrap.append(t);
    return wrap;
  }
  function tooltip(box) {
    let tip = box.querySelector(".s-tip");
    if (!tip) { tip = el("div", { class: "s-tip", hidden: "" }); box.append(tip); }
    return {
      show(ev, text) { const r = box.getBoundingClientRect(); tip.textContent = text; tip.hidden = false;
        const x = Math.min(ev.clientX - r.left + 12, box.clientWidth - tip.offsetWidth - 4); tip.style.left = Math.max(0, x) + "px"; tip.style.top = ev.clientY - r.top - 34 + "px"; },
      hide() { tip.hidden = true; },
    };
  }
  const isIntra = (tf) => INTRA_TF.includes(tf);

  /* ------------------------------------------------------------------ headline */
  dash.draw("hl_sofr", (b) => { const d = dash.data("sent"); const r = d.status === "ok" ? d.data.find((x) => x.curve === "SOFR" && x.tf === "Day") : null; b.textContent = r ? fmt(r.change) : "—"; });
  dash.draw("hl_dec", (b) => { const d = dash.data("fed"); const r = d.status === "ok" ? d.data.find((x) => x.days_ago === 0 && x.meeting === FOMC[0]) : null; b.textContent = r ? fmt(r.move, 1) : "—"; });
  dash.draw("hl_jan", (b) => { const d = dash.data("fed"); const r = d.status === "ok" ? d.data.find((x) => x.days_ago === 0 && x.meeting === FOMC[1]) : null; b.textContent = r ? fmt(r.cum, 1) : "—"; });
  dash.draw("hl_boc", (b) => { const d = dash.data("boc"); const r = d.status === "ok" ? d.data.find((x) => x.days_ago === 0 && x.meeting === BOC[0]) : null; b.textContent = r ? fmt(r.move, 1) : "—"; });

  /* ------------------------------------------------------------------ heatmap */
  dash.draw("heat", (box) => {
    const tf = UI.heat_tf, id = isIntra(tf) ? "chg_i" : "chg_d", d = dash.data(id);
    if (d.status !== "ok" || !d.data) return placeholder(box, d, 190);
    const rows = HEAT.map((c) => d.data.find((r) => r.curve === c && r.tf === tf)).filter(Boolean);
    box.replaceChildren(heatTable(id, "curve,tf", COLS, COLS, rows, (r) => `${enc(r.curve)},${enc(r.tf)}`));
  });

  /* ------------------------------------------------------------------ dec spreads */
  dash.draw("dec", (box) => {
    const d = dash.data("dec");
    if (d.status !== "ok" || !d.data) return placeholder(box, d, 170);
    const labs = PAIRS.map((p) => p[2]);
    const fields = [...labs.map((l) => "Day " + l), ...labs.map((l) => "Week " + l)];
    const rows = DEC.map((c) => d.data.find((r) => r.curve === c)).filter(Boolean);
    box.replaceChildren(heatTable("dec", "curve", [...labs, ...labs], fields, rows, (r) => enc(r.curve), [["DAY", 3], ["THIS WEEK", 3]]));
  });

  /* ------------------------------------------------------------------ sentiment bars */
  dash.draw("sent", (box) => {
    const d = dash.data("sent");
    if (d.status !== "ok" || !d.data) return placeholder(box, d, 230);
    const items = d.data.filter((r) => r.tf === UI.sent_tf && r.change != null).sort((a, b) => a.change - b.change);
    if (!items.length) return placeholder(box, { status: "ok" }, 230);
    const W = Math.max(280, box.clientWidth), rowH = 32, lab = 104, val = 64, H = items.length * rowH + 28;
    const lim = Math.max(2, Math.ceil(Math.max(...items.map((r) => Math.abs(r.change))) * 1.15));
    const x = d3.scaleLinear().domain([-lim, lim]).range([lab, W - val]);
    box.replaceChildren();
    const svg = d3.select(box).append("svg").attr("width", "100%").attr("viewBox", `0 0 ${W} ${H}`).attr("role", "img")
      .attr("aria-label", `Z27 change by curve, ${UI.sent_tf}`);
    const ticks = x.ticks(5);
    svg.append("g").selectAll("line").data(ticks).join("line").attr("x1", x).attr("x2", x).attr("y1", 0).attr("y2", H - 22)
      .attr("stroke", (t) => (t === 0 ? "#6b7385" : "#262e3c")).attr("stroke-dasharray", (t) => (t === 0 ? null : "2 4"));
    svg.append("g").selectAll("text").data(ticks).join("text").attr("class", "s-tick").attr("x", x).attr("y", H - 6)
      .attr("text-anchor", "middle").text((t) => (t === 0 ? "0 bp" : fmt(t, 0)));
    const tip = tooltip(box);
    const g = svg.append("g").selectAll("g").data(items).join("g").attr("transform", (r, i) => `translate(0,${i * rowH + 4})`);
    g.append("rect").attr("x", (r) => Math.min(x(0), x(r.change))).attr("y", 4).attr("height", 18)
      .attr("width", (r) => Math.max(1, Math.abs(x(r.change) - x(0)))).attr("rx", 2).attr("fill", (r) => COLOR[r.curve])
      .on("pointermove", (ev, r) => tip.show(ev, `${r.curve} Z27 · ${fmt(r.change)} bp (${UI.sent_tf})`)).on("pointerleave", () => tip.hide());
    g.append("text").attr("class", "s-blab").attr("x", 0).attr("y", 17).text((r) => r.curve);
    g.append("text").attr("class", (r) => "s-bval " + dcls(r.change)).attr("x", W).attr("y", 17).attr("text-anchor", "end").text((r) => fmt(r.change));
  });

  /* ------------------------------------------------------------------ net change curve */
  dash.draw("curve", (box) => {
    const tf = UI.curve_tf, id = isIntra(tf) ? "chg_i" : "chg_d", d = dash.data(id);
    if (d.status !== "ok" || !d.data) return placeholder(box, d, 300);
    const row = d.data.find((r) => r.curve === UI.curve && r.tf === tf);
    const pts = row ? COLS.map((c) => [c, row[c]]).filter((p) => p[1] != null) : [];
    if (pts.length < 2) return placeholder(box, { status: "ok" }, 300);
    const ys = pts.map((p) => p[1]), imax = ys.indexOf(Math.max(...ys)), imin = ys.indexOf(Math.min(...ys));
    box.setAttribute("data-source", id);
    const W = Math.max(300, box.clientWidth), H = 300, m = { l: 46, r: 18, t: 34, b: 30 };
    const x = d3.scalePoint().domain(pts.map((p) => p[0])).range([m.l, W - m.r]).padding(0.3);
    const lo = Math.min(0, ...ys), hi = Math.max(0, ...ys), pad = (hi - lo || 1) * 0.15;
    const y = d3.scaleLinear().domain([lo - pad, hi + pad]).nice().range([H - m.b, m.t]);
    box.replaceChildren();
    const chipRow = el("div", { class: "s-chips" });
    pts.forEach(([c, v], i) => {
      const ch = el("span", { class: "s-chip" + (i === imax ? " mx" : i === imin ? " mn" : ""), "data-source": id, "data-field": c,
        "data-where": `curve=${enc(UI.curve)}&tf=${enc(tf)}` });
      ch.append(el("b", {}, c), el("span", { class: dcls(v) }, fmt(v)));
      chipRow.append(ch);
    });
    box.append(chipRow);
    const holder = el("div", { class: "s-rel" }); box.append(holder);
    const svg = d3.select(holder).append("svg").attr("width", "100%").attr("viewBox", `0 0 ${W} ${H}`).attr("role", "img")
      .attr("aria-label", `${UI.curve} net change by contract, ${tf}, in bp`);
    const yt = y.ticks(5);
    svg.append("g").selectAll("line").data(yt).join("line").attr("x1", m.l).attr("x2", W - m.r).attr("y1", y).attr("y2", y)
      .attr("stroke", (t) => (t === 0 ? "#6b7385" : "#262e3c")).attr("stroke-dasharray", (t) => (t === 0 ? null : "2 4"));
    svg.append("g").selectAll("text").data(yt).join("text").attr("class", "s-tick").attr("x", m.l - 8).attr("y", (t) => y(t) + 4)
      .attr("text-anchor", "end").text((t) => d3.format("~g")(t));
    const line = d3.line().x((p) => x(p[0])).y((p) => y(p[1])).curve(d3.curveMonotoneX);
    const area = d3.area().x((p) => x(p[0])).y0(y(Math.max(lo, 0) === 0 ? 0 : lo)).y1((p) => y(p[1])).curve(d3.curveMonotoneX);
    svg.append("path").attr("d", area(pts)).attr("fill", "rgba(34,211,238,.08)");
    svg.append("path").attr("d", line(pts)).attr("fill", "none").attr("stroke", "#22d3ee").attr("stroke-width", 2);
    const tip = tooltip(holder);
    const g = svg.append("g").selectAll("g").data(pts).join("g");
    g.append("circle").attr("cx", (p) => x(p[0])).attr("cy", (p) => y(p[1])).attr("r", (p, i) => (i === imax || i === imin ? 6 : 3.5))
      .attr("fill", (p, i) => (i === imax ? "#22c55e" : i === imin ? "#22d3ee" : "#1b212d"))
      .attr("stroke", (p, i) => (i === imax ? "#22c55e" : "#22d3ee")).attr("stroke-width", 1.5)
      .on("pointermove", (ev, p) => tip.show(ev, `${UI.curve} ${p[0]} · ${fmt(p[1])} bp (${tf})`)).on("pointerleave", () => tip.hide());
    g.append("text").attr("class", (p, i) => "s-plab" + (i === imax ? " mx" : i === imin ? " mn" : ""))
      .attr("x", (p) => x(p[0])).attr("y", (p, i) => (i === imin && i !== imax ? y(p[1]) + 18 : y(p[1]) - 10)).attr("text-anchor", "middle")
      .text((p, i) => (i === imax ? "max " : i === imin ? "min " : "") + fmt(p[1]));
    svg.append("g").selectAll("text").data(pts).join("text").attr("class", "s-tick").attr("x", (p) => x(p[0])).attr("y", H - 8)
      .attr("text-anchor", "middle").text((p) => p[0]);
  });

  /* ------------------------------------------------------------------ priced moves */
  function pricedDraw(name, id, meetings) {
    dash.draw(name, (box) => {
      const d = dash.data(id);
      if (d.status !== "ok" || !d.data || !d.data.length) {
        return placeholder(box, d.status === "ok" ? { status: "ok", note: true } : d, 300);
      }
      const maxN = Math.max(...d.data.map((r) => r.days_ago));
      const n = Math.min(UI[name + "_n"], maxN);
      const rows = d.data.filter((r) => r.days_ago === n);
      const moves = rows.map((r) => r.move), mi = argmaxAbs(moves), scale = Math.max(1, ...moves.map(Math.abs));
      const t = el("table", { class: "s-heat s-priced", "data-source": id, "data-row-key": "days_ago,meeting" });
      const h = el("tr");
      [["Meeting", "meeting"], ["Move (bp)", "move"], ["Cum (bp)", "cum"], ["Implied (%)", "implied"], ["Δ 1D (bp)", "d1"]]
        .forEach(([lab, f], i) => h.append(el("th", { "data-field": f, class: i >= 2 ? "r" : i === 0 ? "l" : null }, lab)));
      const thead = el("thead"); thead.append(h);
      const tb = el("tbody");
      rows.forEach((r, i) => {
        const tr = el("tr", { "data-key": `${r.days_ago},${enc(r.meeting)}` });
        tr.append(el("td", { class: "lab" }, fdate(r.meeting)));
        const hs = heatStyle(r.move, scale);
        tr.append(el("td", { class: `hc ${hs.cls}${i === mi ? " max" : ""}`, style: hs.style || null }, fmt(r.move, 1)));
        tr.append(el("td", { class: "num" }, fmt(r.cum, 1)), el("td", { class: "num" }, r.implied.toFixed(3)),
          el("td", { class: "num " + dcls(r.d1) }, fmt(r.d1, 1)));
        tb.append(tr);
      });
      t.append(thead, tb);
      const wrap = el("div", { class: "s-scroll" }); wrap.append(t);
      box.replaceChildren(wrap);
    });
    dash.draw(name + "_n", (b) => {
      const d = dash.data(id);
      const maxN = d.status === "ok" && d.data && d.data.length ? Math.max(...d.data.map((r) => r.days_ago)) : 0;
      UI[name + "_n"] = Math.min(UI[name + "_n"], maxN);
      b.textContent = String(UI[name + "_n"]);
      document.querySelectorAll(`[data-step="${name}"]`).forEach((btn) => {
        btn.disabled = Number(btn.dataset.d) > 0 ? UI[name + "_n"] >= maxN : UI[name + "_n"] <= 0;
      });
    });
    dash.draw(name + "_date", (b) => {
      const d = dash.data(id);
      const r = d.status === "ok" && d.data ? d.data.find((x) => x.days_ago === UI[name + "_n"]) : null;
      b.textContent = r ? `${fdate(r.session)} · start ${r.start.toFixed(3)}%` : "—";
    });
  }
  pricedDraw("fed", "fed", FOMC);
  pricedDraw("boc", "boc", BOC);

  /* ------------------------------------------------------------------ speakers */
  dash.draw("speakers", (box) => {
    const d = dash.data("speakers"), sc = dash.data("spk"), fed = dash.data("fed");
    if (d.status !== "ok" || !d.data || !d.data.length) return placeholder(box, d, 200);
    const score = sc.status === "ok" && sc.data ? Object.fromEntries(sc.data.map((r) => [r.name, r])) : {};
    const f0 = fed.status === "ok" && fed.data ? fed.data.filter((r) => r.days_ago === 0) : [];
    box.replaceChildren();
    for (const s of d.data) {
      const card = el("article", { class: "s-card s-spk", id: "spk-" + String(s.name).toLowerCase().replace(/[^a-z]+/g, "-") });
      const head = el("div", { class: "spk-head" });
      head.append(el("span", { class: "badge" }, s.bank), el("span", { class: "spk-name" }, s.name), el("span", { class: "spk-role" }, s.role));
      const k = score[s.name];
      const sw = el("span", { class: "spk-score" });
      sw.append(el("span", { "data-source": "spk", "data-field": "score", "data-where": `name=${enc(s.name)}` }, k ? k.score.toFixed(1) : "—"),
        document.createTextNode(" ("), el("span", { "data-source": "spk", "data-field": "speeches", "data-where": `name=${enc(s.name)}` }, k ? String(k.speeches) : "—"),
        document.createTextNode(")"));
      const h = Number(s.hawkish), tone = h >= 6 ? "hawk" : h <= 4 ? "dove" : "neut";
      const tag = el("span", { class: "tag " + tone });
      tag.append(document.createTextNode((h >= 6 ? "Hawkish " : h <= 4 ? "Dovish " : "Neutral ")),
        el("span", { "data-source": "speakers", "data-field": "hawkish", "data-where": `name=${enc(s.name)}` }, String(h)), document.createTextNode("/10"));
      head.append(sw, tag, el("span", { class: "spk-date" }, fdate(String(s.date))));
      card.append(head);
      const vote = el("div", { class: "spk-vote" });
      vote.append(el("i", { class: String(s.votes_next) === "true" ? "on" : "off" }), document.createTextNode(s.voting));
      card.append(vote);
      if (k && Math.abs(k.deviation) >= 1.5) {
        const w = el("div", { class: "spk-warn" });
        w.append(document.createTextNode(`⚠ Today ${h}/10 is `),
          el("b", { "data-source": "spk", "data-field": "deviation", "data-where": `name=${enc(s.name)}` }, fmt(k.deviation, 1)),
          document.createTextNode(" vs the average of the last 4 speeches ("),
          el("b", { "data-source": "spk", "data-field": "avg4", "data-where": `name=${enc(s.name)}` }, k.avg4.toFixed(1)),
          document.createTextNode(k.deviation > 0 ? "): notably more hawkish than usual." : "): notably more dovish than usual."));
        card.append(w);
      }
      card.append(el("div", { class: "spk-title" }, s.title), el("p", { class: "spk-headline" }, s.headline));
      const ul = el("ul", { class: "spk-list" });
      const bullets = typeof s.bullets === "string" ? JSON.parse(s.bullets) : s.bullets || [];
      for (const b of bullets) {
        const li = el("li"), m = /^([A-Za-z ]+):\s*(.*)$/.exec(b);
        if (m) li.append(el("b", {}, m[1]), document.createTextNode(" · " + m[2])); else li.textContent = b;
        ul.append(li);
      }
      card.append(ul);
      const rr = el("div", { class: "spk-rr" });
      rr.append(el("h4", {}, "RATES READ"));
      const p = el("p");
      String(s.rates_read).split(/(\{dec\}|\{jan\})/).forEach((part) => {
        if (part === "{dec}" || part === "{jan}") {
          const r = f0.find((x) => x.meeting === (part === "{dec}" ? FOMC[0] : FOMC[1]));
          const f = part === "{dec}" ? "move" : "cum";
          p.append(el("b", { "data-source": "fed", "data-field": f, "data-where": `days_ago=0&meeting=${enc(r ? r.meeting : "")}` },
            r ? `~${Math.round(r[f])}bp` : "—"));
        } else p.append(document.createTextNode(part));
      });
      rr.append(p);
      card.append(rr);
      box.append(card);
    }
  });

  /* ------------------------------------------------------------------ transient-error retry */
  // The connector sometimes answers "org policy check unavailable — retry" when many calls run at once.
  // Re-run such a source up to 3 times, a few seconds apart. Other errors are left to the Sources panel.
  const RETRY = {}, PENDING = {};
  dash.onData(() => {
    for (const id of ["sofr", "euribor", "sonia", "corra", "saron", "aussie", "zq",
      "sofr_5m", "euribor_5m", "sonia_5m", "corra_5m", "saron_5m", "aussie_5m"]) {
      if (id.endsWith("_5m") && !INTRA_TF.includes(UI.heat_tf) && !INTRA_TF.includes(UI.curve_tf)) continue;
      const d = dash.data(id);
      if (d.status !== "error" || PENDING[id] || (RETRY[id] || 0) >= 3) continue;
      if (!/unavailable|retry|timeout|timed out|rate|busy|try again/i.test(d.message || "")) continue;
      RETRY[id] = (RETRY[id] || 0) + 1; PENDING[id] = true;
      setTimeout(() => { PENDING[id] = false; dash.refresh(id); }, 2500 * RETRY[id] + Math.random() * 1500);
    }
  });

  /* ------------------------------------------------------------------ controls */
  const REDRAW = { heat_tf: ["heat"], sent_tf: ["sent"], curve: ["curve"], curve_tf: ["curve"] };
  function syncPills() {
    document.querySelectorAll("[data-pill]").forEach((b) => {
      b.classList.toggle("on", UI[b.dataset.pill] === b.dataset.v);
      b.setAttribute("aria-pressed", UI[b.dataset.pill] === b.dataset.v ? "true" : "false");
    });
  }
  document.querySelectorAll("[data-pill]").forEach((b) => b.addEventListener("click", () => {
    UI[b.dataset.pill] = b.dataset.v; syncPills(); (REDRAW[b.dataset.pill] || []).forEach((n) => dash.draw(n));
  }));
  document.querySelectorAll("[data-step]").forEach((b) => b.addEventListener("click", () => {
    const k = b.dataset.step;
    UI[k + "_n"] = Math.max(0, Math.min(DAYS - 1, UI[k + "_n"] + Number(b.dataset.d)));
    [k, k + "_n", k + "_date"].forEach((n) => dash.draw(n));
  }));
  document.querySelectorAll("input[data-param=since]").forEach((inp) => {
    inp.value = dash.params().since || "2026-10-28";
    inp.addEventListener("change", () => { if (inp.value && inp.validity.valid) dash.setParams({ since: inp.value }); });
    inp.addEventListener("blur", () => { inp.value = dash.params().since || inp.value; });
  });
  syncPills();
})();
