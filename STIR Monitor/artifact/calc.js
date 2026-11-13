/* STIR maths shared by the calcs and drawings. Pure functions, no I/O. */
(function (root) {
  const DAY = 86400e3;
  const M = { F: 1, G: 2, H: 3, J: 4, K: 5, M: 6, N: 7, Q: 8, U: 9, V: 10, X: 11, Z: 12 };
  const r2 = (x) => Math.round(x * 100) / 100;
  const r1 = (x) => Math.round(x * 10) / 10;
  const iso = (d) => new Date(d).toISOString().slice(0, 10);
  const addDays = (s, n) => iso(Date.parse(s + "T00:00:00Z") + n * DAY);

  /* rows [{contract, session|time, close}] -> {code: rows sorted by time} */
  function byContract(rows) {
    const out = {};
    for (const r of rows || []) {
      const c = Number(r.close);
      if (!isFinite(c) || c <= 0) continue;
      (out[r.contract] = out[r.contract] || []).push({ ...r, close: c });
    }
    for (const k in out) out[k].sort((a, b) => (a.time < b.time ? -1 : a.time > b.time ? 1 : 0));
    return out;
  }

  /* rate change in bp: rates up = price down = positive */
  const rateChange = (last, ref) => (last == null || ref == null ? null : r2(-(last - ref) * 100));

  function lastOnOrBefore(series, session) {
    let v = null;
    for (const r of series) if (r.session <= session) v = r; else break;
    return v;
  }

  function mondayOf(session) {
    const d = new Date(session + "T00:00:00Z");
    return iso(d.getTime() - ((d.getUTCDay() + 6) % 7) * DAY);
  }

  /* reference close for a daily timeframe */
  function dailyRef(series, tf, since) {
    if (!series || series.length < 1) return null;
    const last = series[series.length - 1];
    let ref = null;
    if (tf === "Day") ref = series.length > 1 ? series[series.length - 2] : null;
    else if (tf === "Week" || tf === "Since") {
      const cut = tf === "Week" ? mondayOf(last.session) : null;
      for (const r of series) {
        if (tf === "Week" ? r.session < cut : r.session <= since) ref = r; else break;
      }
    } else {
      const back = { "1W": 7, "1M": 30, "3M": 91, "6M": 182 }[tf];
      ref = lastOnOrBefore(series, addDays(last.session, -back));
    }
    return ref ? ref.close : null;
  }

  function londonParts(t) {
    const p = new Intl.DateTimeFormat("en-GB", { timeZone: "Europe/London", year: "numeric", month: "2-digit",
      day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).formatToParts(new Date(t));
    const g = (k) => p.find((x) => x.type === k).value;
    return { day: `${g("year")}-${g("month")}-${g("day")}`, hm: `${g("hour")}:${g("minute")}` };
  }

  /* reference close for an intraday timeframe (5-minute bars) */
  function intradayRef(series, tf) {
    if (!series || !series.length) return null;
    const lastT = Date.parse(series[series.length - 1].time);
    if (tf === "Since EU Open") {
      const today = londonParts(lastT).day;
      for (const r of series) {
        const p = londonParts(Date.parse(r.time));
        if (p.day === today && p.hm >= "07:00") return r.close;
      }
      return null;
    }
    const cut = lastT - { "15m": 15, "30m": 30, "1h": 60 }[tf] * 60e3;
    let ref = null;
    for (const r of series) if (Date.parse(r.time) <= cut) ref = r; else break;
    return ref ? ref.close : null;
  }

  function changesFor(series, tf, since, intraday) {
    if (!series || !series.length) return null;
    const last = series[series.length - 1].close;
    return rateChange(last, intraday ? intradayRef(series, tf) : dailyRef(series, tf, since));
  }

  /* change of price(front) - price(back), in bp */
  function spreadChange(f, b, tf) {
    if (!f || !b || !f.length || !b.length) return null;
    const rf = dailyRef(f, tf), rb = dailyRef(b, tf);
    if (rf == null || rb == null) return null;
    return r2(((f[f.length - 1].close - b[b.length - 1].close) - (rf - rb)) * 100);
  }

  /* ---------- FOMC path from 30D Fed Funds (CME FedWatch method) ---------- */
  const daysInMonth = (y, m) => new Date(Date.UTC(y, m, 0)).getUTCDate();
  const ymKey = (y, m) => `${y}-${String(m).padStart(2, "0")}`;
  const nextYM = (y, m) => (m === 12 ? [y + 1, 1] : [y, m + 1]);
  const prevYM = (y, m) => (m === 1 ? [y - 1, 12] : [y, m - 1]);

  function fomcPath(meetings, monthly) {
    const mm = new Set(meetings.map((d) => d.slice(0, 7)));
    const rows = [];
    let pre = null, base = null;
    for (let i = 0; i < meetings.length; i++) {
      const [y, m, d] = meetings[i].split("-").map(Number);
      const k = ymKey(y, m);
      if (monthly[k] == null) break;
      if (i === 0) {
        const pk = ymKey(...prevYM(y, m));
        if (monthly[pk] == null || mm.has(pk)) break;
        pre = base = monthly[pk];
      }
      const n = daysInMonth(y, m), nk = ymKey(...nextYM(y, m));
      let post;
      if (monthly[nk] != null && !mm.has(nk)) post = monthly[nk];
      else if (n - d > 0) post = (monthly[k] * n - pre * d) / (n - d);
      else break;
      rows.push({ meeting: meetings[i], move: r1((post - pre) * 100), cum: r1((post - base) * 100),
        implied: Math.round(post * 1000) / 1000, start: base });
      pre = post;
    }
    return rows;
  }

  /* ---------- BoC path fitted to the quarterly 3M CORRA strip ---------- */
  function thirdWed(y, m) {
    const d = new Date(Date.UTC(y, m - 1, 15));
    return iso(d.getTime() + ((3 - d.getUTCDay() + 7) % 7) * DAY);
  }
  function immPeriod(code) {
    const m = M[code[0]], y = 2000 + Number(code.slice(1));
    const [ey, em] = m <= 9 ? [y, m + 3] : [y + 1, m - 9];
    return [thirdWed(y, m), thirdWed(ey, em)];
  }

  function solve(A, b) { /* least squares via normal equations + Gauss-Jordan */
    const n = A[0].length, N = Array.from({ length: n }, () => new Array(n + 1).fill(0));
    A.forEach((row, r) => { for (let i = 0; i < n; i++) { for (let j = 0; j < n; j++) N[i][j] += row[i] * row[j]; N[i][n] += row[i] * b[r]; } });
    for (let c = 0; c < n; c++) {
      let p = c; for (let r = c + 1; r < n; r++) if (Math.abs(N[r][c]) > Math.abs(N[p][c])) p = r;
      [N[c], N[p]] = [N[p], N[c]];
      if (Math.abs(N[c][c]) < 1e-12) return null;
      for (let r = 0; r < n; r++) if (r !== c) { const f = N[r][c] / N[c][c]; for (let j = c; j <= n; j++) N[r][j] -= f * N[c][j]; }
    }
    return N.map((row, i) => row[n] / row[i]);
  }

  /* Unknowns: today's overnight rate r0 and the rate after each meeting. Each contract's
     implied rate is the simple average of that path over its reference quarter; days
     already past are taken at r0. Light smoothing on the change between consecutive moves. */
  function stripPath(meetings, strip, asof, smooth = 0.2) {
    const periods = Object.entries(strip).map(([c, r]) => [c, r, ...immPeriod(c)]).filter((p) => p[3] > asof);
    if (!periods.length) return [];
    const horizon = periods.reduce((a, p) => (p[3] > a ? p[3] : a), asof);
    const mts = meetings.filter((m) => m >= asof && m < horizon);
    const n = mts.length + 1;
    if (n < 2) return [];
    const A = [], b = [];
    for (const [, rate, start, end] of periods) {
      const row = new Array(n).fill(0);
      let d = start, total = 0;
      while (d < end) {
        const k = d < asof ? 0 : mts.filter((m) => m < d).length;
        row[k] += 1; total += 1; d = addDays(d, 1);
      }
      A.push(row.map((x) => x / total)); b.push(rate);
    }
    for (let i = 2; i < n; i++) {
      const row = new Array(n).fill(0); row[i] = smooth; row[i - 1] = -2 * smooth; row[i - 2] = smooth;
      A.push(row); b.push(0);
    }
    const x = solve(A, b);
    if (!x) return [];
    return mts.map((m, i) => ({ meeting: m, move: r1((x[i + 1] - x[i]) * 100), cum: r1((x[i + 1] - x[0]) * 100),
      implied: Math.round(x[i + 1] * 1000) / 1000, start: Math.round(x[0] * 1000) / 1000 }));
  }

  root.STIR = { byContract, changesFor, spreadChange, dailyRef, intradayRef, fomcPath, stripPath, immPeriod,
    ymKey, M, r1, r2, lastOnOrBefore };
})(typeof window !== "undefined" ? window : globalThis);
