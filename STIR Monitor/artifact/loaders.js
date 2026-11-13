/* Loaders: each dataset calls IBKR once for its own contract, then fetches the rest of its strip. */
dash.loader("sofr", {
  description: "Fetches the rest of the SOFR strip (one month of daily bars each) and stacks them into one table.",
  fn: async ({ answer, call, args }) => {
    const CONTRACTS = {"U26": 385575844, "Z26": 385575900, "H27": 385575880, "M27": 385575861, "U27": 385575841, "Z27": 385575897, "H28": 385575879, "M28": 385575856, "U28": 385575837, "Z28": 385575894, "H29": 385575874, "M29": 395594167, "Z29": 426903945}; // contract code -> IBKR contract id
    const OWN = "Z27";    // the contract this dataset's own call fetches
    const toRows = (code, a) => {
      if (!a || a.error || !Array.isArray(a.time)) return { code, error: (a && (a.error && (a.error.message || a.error))) || "no bars" };
      return { code, rows: a.time.map((t, i) => ({ contract: code, time: t,
        session: new Date(Date.parse(t) + 12 * 3600e3).toISOString().slice(0, 10), close: Number(a.close[i]) })) };
    };
    // One contract at a time, retrying transient connector errors, so IBKR isn't flooded.
    const wait = (ms) => new Promise((r) => setTimeout(r, ms));
    const fetchOne = async (code, id, extra) => {
      let last;
      for (let attempt = 0; attempt < 4; attempt++) {
        if (attempt) await wait(1000 * 2 ** (attempt - 1));
        try {
          const r = toRows(code, await call("get_price_history", { ...args, ...extra, contract_id: id }));
          if (r.rows || !/unavailable|retry|timeout|timed out|rate|busy|try again/i.test(r.error)) return r;
          last = r;
        } catch (e) { last = { code, error: String((e && e.message) || e) }; }
      }
      return last;
    };
    const results = [toRows(OWN, answer)];
    if (!results[0].rows) results[0] = await fetchOne(OWN, CONTRACTS[OWN], {});
    for (const [code, id] of Object.entries(CONTRACTS)) {
      if (code !== OWN) results.push(await fetchOne(code, id, { period: "ONE_MONTH", }));
    }
    const ok = results.filter((r) => r.rows && r.rows.length);
    if (!ok.length) throw new Error("IBKR returned no bars: " + results.map((r) => r.code + " " + r.error).join("; "));
    return { data: ok.flatMap((r) => r.rows), columns: ["contract", "session", "time", "close"],
      truncated: ok.length < results.length,
      meta: results.filter((r) => r.error).map((r) => ({ label: "Not loaded: " + r.code, value: String(r.error) })) };
  },
});

dash.loader("sofr_5m", {
  description: "Fetches 5-minute bars for the rest of the SOFR strip and stacks them into one table.",
  fn: async ({ answer, call, args }) => {
    const CONTRACTS = {"U26": 385575844, "Z26": 385575900, "H27": 385575880, "M27": 385575861, "U27": 385575841, "Z27": 385575897, "H28": 385575879, "M28": 385575856, "U28": 385575837, "Z28": 385575894, "H29": 385575874, "M29": 395594167, "Z29": 426903945}; // contract code -> IBKR contract id
    const OWN = "Z27";    // the contract this dataset's own call fetches
    const toRows = (code, a) => {
      if (!a || a.error || !Array.isArray(a.time)) return { code, error: (a && (a.error && (a.error.message || a.error))) || "no bars" };
      return { code, rows: a.time.map((t, i) => ({ contract: code, time: t,
        session: new Date(Date.parse(t) + 12 * 3600e3).toISOString().slice(0, 10), close: Number(a.close[i]) })) };
    };
    // One contract at a time, retrying transient connector errors, so IBKR isn't flooded.
    const wait = (ms) => new Promise((r) => setTimeout(r, ms));
    const fetchOne = async (code, id, extra) => {
      let last;
      for (let attempt = 0; attempt < 4; attempt++) {
        if (attempt) await wait(1000 * 2 ** (attempt - 1));
        try {
          const r = toRows(code, await call("get_price_history", { ...args, ...extra, contract_id: id }));
          if (r.rows || !/unavailable|retry|timeout|timed out|rate|busy|try again/i.test(r.error)) return r;
          last = r;
        } catch (e) { last = { code, error: String((e && e.message) || e) }; }
      }
      return last;
    };
    const results = [toRows(OWN, answer)];
    if (!results[0].rows) results[0] = await fetchOne(OWN, CONTRACTS[OWN], {});
    for (const [code, id] of Object.entries(CONTRACTS)) {
      if (code !== OWN) results.push(await fetchOne(code, id, { }));
    }
    const ok = results.filter((r) => r.rows && r.rows.length);
    if (!ok.length) throw new Error("IBKR returned no bars: " + results.map((r) => r.code + " " + r.error).join("; "));
    return { data: ok.flatMap((r) => r.rows), columns: ["contract", "session", "time", "close"],
      truncated: ok.length < results.length,
      meta: results.filter((r) => r.error).map((r) => ({ label: "Not loaded: " + r.code, value: String(r.error) })) };
  },
});

dash.loader("euribor", {
  description: "Fetches the rest of the Euribor strip (one month of daily bars each) and stacks them into one table.",
  fn: async ({ answer, call, args }) => {
    const CONTRACTS = {"Z26": 460390619, "H27": 476937869, "M27": 496885442, "U27": 514365267, "Z27": 532513522, "H28": 550554822, "M28": 567287312, "U28": 586941459, "Z28": 604446222, "H29": 619453618, "M29": 638255978, "Z29": 673605902}; // contract code -> IBKR contract id
    const OWN = "Z27";    // the contract this dataset's own call fetches
    const toRows = (code, a) => {
      if (!a || a.error || !Array.isArray(a.time)) return { code, error: (a && (a.error && (a.error.message || a.error))) || "no bars" };
      return { code, rows: a.time.map((t, i) => ({ contract: code, time: t,
        session: new Date(Date.parse(t) + 12 * 3600e3).toISOString().slice(0, 10), close: Number(a.close[i]) })) };
    };
    // One contract at a time, retrying transient connector errors, so IBKR isn't flooded.
    const wait = (ms) => new Promise((r) => setTimeout(r, ms));
    const fetchOne = async (code, id, extra) => {
      let last;
      for (let attempt = 0; attempt < 4; attempt++) {
        if (attempt) await wait(1000 * 2 ** (attempt - 1));
        try {
          const r = toRows(code, await call("get_price_history", { ...args, ...extra, contract_id: id }));
          if (r.rows || !/unavailable|retry|timeout|timed out|rate|busy|try again/i.test(r.error)) return r;
          last = r;
        } catch (e) { last = { code, error: String((e && e.message) || e) }; }
      }
      return last;
    };
    const results = [toRows(OWN, answer)];
    if (!results[0].rows) results[0] = await fetchOne(OWN, CONTRACTS[OWN], {});
    for (const [code, id] of Object.entries(CONTRACTS)) {
      if (code !== OWN) results.push(await fetchOne(code, id, { period: "ONE_MONTH", }));
    }
    const ok = results.filter((r) => r.rows && r.rows.length);
    if (!ok.length) throw new Error("IBKR returned no bars: " + results.map((r) => r.code + " " + r.error).join("; "));
    return { data: ok.flatMap((r) => r.rows), columns: ["contract", "session", "time", "close"],
      truncated: ok.length < results.length,
      meta: results.filter((r) => r.error).map((r) => ({ label: "Not loaded: " + r.code, value: String(r.error) })) };
  },
});

dash.loader("euribor_5m", {
  description: "Fetches 5-minute bars for the rest of the Euribor strip and stacks them into one table.",
  fn: async ({ answer, call, args }) => {
    const CONTRACTS = {"Z26": 460390619, "H27": 476937869, "M27": 496885442, "U27": 514365267, "Z27": 532513522, "H28": 550554822, "M28": 567287312, "U28": 586941459, "Z28": 604446222, "H29": 619453618, "M29": 638255978, "Z29": 673605902}; // contract code -> IBKR contract id
    const OWN = "Z27";    // the contract this dataset's own call fetches
    const toRows = (code, a) => {
      if (!a || a.error || !Array.isArray(a.time)) return { code, error: (a && (a.error && (a.error.message || a.error))) || "no bars" };
      return { code, rows: a.time.map((t, i) => ({ contract: code, time: t,
        session: new Date(Date.parse(t) + 12 * 3600e3).toISOString().slice(0, 10), close: Number(a.close[i]) })) };
    };
    // One contract at a time, retrying transient connector errors, so IBKR isn't flooded.
    const wait = (ms) => new Promise((r) => setTimeout(r, ms));
    const fetchOne = async (code, id, extra) => {
      let last;
      for (let attempt = 0; attempt < 4; attempt++) {
        if (attempt) await wait(1000 * 2 ** (attempt - 1));
        try {
          const r = toRows(code, await call("get_price_history", { ...args, ...extra, contract_id: id }));
          if (r.rows || !/unavailable|retry|timeout|timed out|rate|busy|try again/i.test(r.error)) return r;
          last = r;
        } catch (e) { last = { code, error: String((e && e.message) || e) }; }
      }
      return last;
    };
    const results = [toRows(OWN, answer)];
    if (!results[0].rows) results[0] = await fetchOne(OWN, CONTRACTS[OWN], {});
    for (const [code, id] of Object.entries(CONTRACTS)) {
      if (code !== OWN) results.push(await fetchOne(code, id, { }));
    }
    const ok = results.filter((r) => r.rows && r.rows.length);
    if (!ok.length) throw new Error("IBKR returned no bars: " + results.map((r) => r.code + " " + r.error).join("; "));
    return { data: ok.flatMap((r) => r.rows), columns: ["contract", "session", "time", "close"],
      truncated: ok.length < results.length,
      meta: results.filter((r) => r.error).map((r) => ({ label: "Not loaded: " + r.code, value: String(r.error) })) };
  },
});

dash.loader("sonia", {
  description: "Fetches the rest of the SONIA strip (one month of daily bars each) and stacks them into one table.",
  fn: async ({ answer, call, args }) => {
    const CONTRACTS = {"U26": 522330868, "Z26": 522330875, "H27": 522330878, "M27": 522330880, "U27": 522330885, "Z27": 532672437, "H28": 550757251, "M28": 567487151, "U28": 587120949, "Z28": 604606769, "H29": 619665648, "M29": 638529419, "Z29": 673696352}; // contract code -> IBKR contract id
    const OWN = "Z27";    // the contract this dataset's own call fetches
    const toRows = (code, a) => {
      if (!a || a.error || !Array.isArray(a.time)) return { code, error: (a && (a.error && (a.error.message || a.error))) || "no bars" };
      return { code, rows: a.time.map((t, i) => ({ contract: code, time: t,
        session: new Date(Date.parse(t) + 12 * 3600e3).toISOString().slice(0, 10), close: Number(a.close[i]) })) };
    };
    // One contract at a time, retrying transient connector errors, so IBKR isn't flooded.
    const wait = (ms) => new Promise((r) => setTimeout(r, ms));
    const fetchOne = async (code, id, extra) => {
      let last;
      for (let attempt = 0; attempt < 4; attempt++) {
        if (attempt) await wait(1000 * 2 ** (attempt - 1));
        try {
          const r = toRows(code, await call("get_price_history", { ...args, ...extra, contract_id: id }));
          if (r.rows || !/unavailable|retry|timeout|timed out|rate|busy|try again/i.test(r.error)) return r;
          last = r;
        } catch (e) { last = { code, error: String((e && e.message) || e) }; }
      }
      return last;
    };
    const results = [toRows(OWN, answer)];
    if (!results[0].rows) results[0] = await fetchOne(OWN, CONTRACTS[OWN], {});
    for (const [code, id] of Object.entries(CONTRACTS)) {
      if (code !== OWN) results.push(await fetchOne(code, id, { period: "ONE_MONTH", }));
    }
    const ok = results.filter((r) => r.rows && r.rows.length);
    if (!ok.length) throw new Error("IBKR returned no bars: " + results.map((r) => r.code + " " + r.error).join("; "));
    return { data: ok.flatMap((r) => r.rows), columns: ["contract", "session", "time", "close"],
      truncated: ok.length < results.length,
      meta: results.filter((r) => r.error).map((r) => ({ label: "Not loaded: " + r.code, value: String(r.error) })) };
  },
});

dash.loader("sonia_5m", {
  description: "Fetches 5-minute bars for the rest of the SONIA strip and stacks them into one table.",
  fn: async ({ answer, call, args }) => {
    const CONTRACTS = {"U26": 522330868, "Z26": 522330875, "H27": 522330878, "M27": 522330880, "U27": 522330885, "Z27": 532672437, "H28": 550757251, "M28": 567487151, "U28": 587120949, "Z28": 604606769, "H29": 619665648, "M29": 638529419, "Z29": 673696352}; // contract code -> IBKR contract id
    const OWN = "Z27";    // the contract this dataset's own call fetches
    const toRows = (code, a) => {
      if (!a || a.error || !Array.isArray(a.time)) return { code, error: (a && (a.error && (a.error.message || a.error))) || "no bars" };
      return { code, rows: a.time.map((t, i) => ({ contract: code, time: t,
        session: new Date(Date.parse(t) + 12 * 3600e3).toISOString().slice(0, 10), close: Number(a.close[i]) })) };
    };
    // One contract at a time, retrying transient connector errors, so IBKR isn't flooded.
    const wait = (ms) => new Promise((r) => setTimeout(r, ms));
    const fetchOne = async (code, id, extra) => {
      let last;
      for (let attempt = 0; attempt < 4; attempt++) {
        if (attempt) await wait(1000 * 2 ** (attempt - 1));
        try {
          const r = toRows(code, await call("get_price_history", { ...args, ...extra, contract_id: id }));
          if (r.rows || !/unavailable|retry|timeout|timed out|rate|busy|try again/i.test(r.error)) return r;
          last = r;
        } catch (e) { last = { code, error: String((e && e.message) || e) }; }
      }
      return last;
    };
    const results = [toRows(OWN, answer)];
    if (!results[0].rows) results[0] = await fetchOne(OWN, CONTRACTS[OWN], {});
    for (const [code, id] of Object.entries(CONTRACTS)) {
      if (code !== OWN) results.push(await fetchOne(code, id, { }));
    }
    const ok = results.filter((r) => r.rows && r.rows.length);
    if (!ok.length) throw new Error("IBKR returned no bars: " + results.map((r) => r.code + " " + r.error).join("; "));
    return { data: ok.flatMap((r) => r.rows), columns: ["contract", "session", "time", "close"],
      truncated: ok.length < results.length,
      meta: results.filter((r) => r.error).map((r) => ({ label: "Not loaded: " + r.code, value: String(r.error) })) };
  },
});

dash.loader("corra", {
  description: "Fetches the rest of the CORRA strip (one month of daily bars each) and stacks them into one table.",
  fn: async ({ answer, call, args }) => {
    const CONTRACTS = {"U26": 673862030, "Z26": 692702513, "H27": 711212024, "M27": 730222881, "U27": 749194870, "Z27": 769776256, "H28": 793332605, "M28": 815079941, "U28": 839464247, "Z28": 865768709, "H29": 893127400, "M29": 924816580}; // contract code -> IBKR contract id
    const OWN = "Z27";    // the contract this dataset's own call fetches
    const toRows = (code, a) => {
      if (!a || a.error || !Array.isArray(a.time)) return { code, error: (a && (a.error && (a.error.message || a.error))) || "no bars" };
      return { code, rows: a.time.map((t, i) => ({ contract: code, time: t,
        session: new Date(Date.parse(t) + 12 * 3600e3).toISOString().slice(0, 10), close: Number(a.close[i]) })) };
    };
    // One contract at a time, retrying transient connector errors, so IBKR isn't flooded.
    const wait = (ms) => new Promise((r) => setTimeout(r, ms));
    const fetchOne = async (code, id, extra) => {
      let last;
      for (let attempt = 0; attempt < 4; attempt++) {
        if (attempt) await wait(1000 * 2 ** (attempt - 1));
        try {
          const r = toRows(code, await call("get_price_history", { ...args, ...extra, contract_id: id }));
          if (r.rows || !/unavailable|retry|timeout|timed out|rate|busy|try again/i.test(r.error)) return r;
          last = r;
        } catch (e) { last = { code, error: String((e && e.message) || e) }; }
      }
      return last;
    };
    const results = [toRows(OWN, answer)];
    if (!results[0].rows) results[0] = await fetchOne(OWN, CONTRACTS[OWN], {});
    for (const [code, id] of Object.entries(CONTRACTS)) {
      if (code !== OWN) results.push(await fetchOne(code, id, { period: "ONE_MONTH", }));
    }
    const ok = results.filter((r) => r.rows && r.rows.length);
    if (!ok.length) throw new Error("IBKR returned no bars: " + results.map((r) => r.code + " " + r.error).join("; "));
    return { data: ok.flatMap((r) => r.rows), columns: ["contract", "session", "time", "close"],
      truncated: ok.length < results.length,
      meta: results.filter((r) => r.error).map((r) => ({ label: "Not loaded: " + r.code, value: String(r.error) })) };
  },
});

dash.loader("corra_5m", {
  description: "Fetches 5-minute bars for the rest of the CORRA strip and stacks them into one table.",
  fn: async ({ answer, call, args }) => {
    const CONTRACTS = {"U26": 673862030, "Z26": 692702513, "H27": 711212024, "M27": 730222881, "U27": 749194870, "Z27": 769776256, "H28": 793332605, "M28": 815079941, "U28": 839464247, "Z28": 865768709, "H29": 893127400, "M29": 924816580}; // contract code -> IBKR contract id
    const OWN = "Z27";    // the contract this dataset's own call fetches
    const toRows = (code, a) => {
      if (!a || a.error || !Array.isArray(a.time)) return { code, error: (a && (a.error && (a.error.message || a.error))) || "no bars" };
      return { code, rows: a.time.map((t, i) => ({ contract: code, time: t,
        session: new Date(Date.parse(t) + 12 * 3600e3).toISOString().slice(0, 10), close: Number(a.close[i]) })) };
    };
    // One contract at a time, retrying transient connector errors, so IBKR isn't flooded.
    const wait = (ms) => new Promise((r) => setTimeout(r, ms));
    const fetchOne = async (code, id, extra) => {
      let last;
      for (let attempt = 0; attempt < 4; attempt++) {
        if (attempt) await wait(1000 * 2 ** (attempt - 1));
        try {
          const r = toRows(code, await call("get_price_history", { ...args, ...extra, contract_id: id }));
          if (r.rows || !/unavailable|retry|timeout|timed out|rate|busy|try again/i.test(r.error)) return r;
          last = r;
        } catch (e) { last = { code, error: String((e && e.message) || e) }; }
      }
      return last;
    };
    const results = [toRows(OWN, answer)];
    if (!results[0].rows) results[0] = await fetchOne(OWN, CONTRACTS[OWN], {});
    for (const [code, id] of Object.entries(CONTRACTS)) {
      if (code !== OWN) results.push(await fetchOne(code, id, { }));
    }
    const ok = results.filter((r) => r.rows && r.rows.length);
    if (!ok.length) throw new Error("IBKR returned no bars: " + results.map((r) => r.code + " " + r.error).join("; "));
    return { data: ok.flatMap((r) => r.rows), columns: ["contract", "session", "time", "close"],
      truncated: ok.length < results.length,
      meta: results.filter((r) => r.error).map((r) => ({ label: "Not loaded: " + r.code, value: String(r.error) })) };
  },
});

dash.loader("saron", {
  description: "Fetches the rest of the SARON strip (one month of daily bars each) and stacks them into one table.",
  fn: async ({ answer, call, args }) => {
    const CONTRACTS = {"U26": 731474013, "Z26": 731474017, "H27": 731474020, "M27": 731474027, "U27": 749028975, "Z27": 769600238, "H28": 793079360, "M28": 815022017, "U28": 839389488, "Z28": 865628077, "H29": 893044170, "M29": 924670929}; // contract code -> IBKR contract id
    const OWN = "Z27";    // the contract this dataset's own call fetches
    const toRows = (code, a) => {
      if (!a || a.error || !Array.isArray(a.time)) return { code, error: (a && (a.error && (a.error.message || a.error))) || "no bars" };
      return { code, rows: a.time.map((t, i) => ({ contract: code, time: t,
        session: new Date(Date.parse(t) + 12 * 3600e3).toISOString().slice(0, 10), close: Number(a.close[i]) })) };
    };
    // One contract at a time, retrying transient connector errors, so IBKR isn't flooded.
    const wait = (ms) => new Promise((r) => setTimeout(r, ms));
    const fetchOne = async (code, id, extra) => {
      let last;
      for (let attempt = 0; attempt < 4; attempt++) {
        if (attempt) await wait(1000 * 2 ** (attempt - 1));
        try {
          const r = toRows(code, await call("get_price_history", { ...args, ...extra, contract_id: id }));
          if (r.rows || !/unavailable|retry|timeout|timed out|rate|busy|try again/i.test(r.error)) return r;
          last = r;
        } catch (e) { last = { code, error: String((e && e.message) || e) }; }
      }
      return last;
    };
    const results = [toRows(OWN, answer)];
    if (!results[0].rows) results[0] = await fetchOne(OWN, CONTRACTS[OWN], {});
    for (const [code, id] of Object.entries(CONTRACTS)) {
      if (code !== OWN) results.push(await fetchOne(code, id, { period: "ONE_MONTH", }));
    }
    const ok = results.filter((r) => r.rows && r.rows.length);
    if (!ok.length) throw new Error("IBKR returned no bars: " + results.map((r) => r.code + " " + r.error).join("; "));
    return { data: ok.flatMap((r) => r.rows), columns: ["contract", "session", "time", "close"],
      truncated: ok.length < results.length,
      meta: results.filter((r) => r.error).map((r) => ({ label: "Not loaded: " + r.code, value: String(r.error) })) };
  },
});

dash.loader("saron_5m", {
  description: "Fetches 5-minute bars for the rest of the SARON strip and stacks them into one table.",
  fn: async ({ answer, call, args }) => {
    const CONTRACTS = {"U26": 731474013, "Z26": 731474017, "H27": 731474020, "M27": 731474027, "U27": 749028975, "Z27": 769600238, "H28": 793079360, "M28": 815022017, "U28": 839389488, "Z28": 865628077, "H29": 893044170, "M29": 924670929}; // contract code -> IBKR contract id
    const OWN = "Z27";    // the contract this dataset's own call fetches
    const toRows = (code, a) => {
      if (!a || a.error || !Array.isArray(a.time)) return { code, error: (a && (a.error && (a.error.message || a.error))) || "no bars" };
      return { code, rows: a.time.map((t, i) => ({ contract: code, time: t,
        session: new Date(Date.parse(t) + 12 * 3600e3).toISOString().slice(0, 10), close: Number(a.close[i]) })) };
    };
    // One contract at a time, retrying transient connector errors, so IBKR isn't flooded.
    const wait = (ms) => new Promise((r) => setTimeout(r, ms));
    const fetchOne = async (code, id, extra) => {
      let last;
      for (let attempt = 0; attempt < 4; attempt++) {
        if (attempt) await wait(1000 * 2 ** (attempt - 1));
        try {
          const r = toRows(code, await call("get_price_history", { ...args, ...extra, contract_id: id }));
          if (r.rows || !/unavailable|retry|timeout|timed out|rate|busy|try again/i.test(r.error)) return r;
          last = r;
        } catch (e) { last = { code, error: String((e && e.message) || e) }; }
      }
      return last;
    };
    const results = [toRows(OWN, answer)];
    if (!results[0].rows) results[0] = await fetchOne(OWN, CONTRACTS[OWN], {});
    for (const [code, id] of Object.entries(CONTRACTS)) {
      if (code !== OWN) results.push(await fetchOne(code, id, { }));
    }
    const ok = results.filter((r) => r.rows && r.rows.length);
    if (!ok.length) throw new Error("IBKR returned no bars: " + results.map((r) => r.code + " " + r.error).join("; "));
    return { data: ok.flatMap((r) => r.rows), columns: ["contract", "session", "time", "close"],
      truncated: ok.length < results.length,
      meta: results.filter((r) => r.error).map((r) => ({ label: "Not loaded: " + r.code, value: String(r.error) })) };
  },
});

dash.loader("aussie", {
  description: "Fetches the rest of the Aussie Bills strip (one month of daily bars each) and stacks them into one table.",
  fn: async ({ answer, call, args }) => {
    const CONTRACTS = {"Z26": 531965339, "H27": 549862528, "M27": 566601074, "U27": 584371135, "Z27": 602063179, "H28": 618689022, "M28": 635922922, "U28": 652809927, "Z28": 670498964, "H29": 768512916, "M29": 791433012, "Z29": 838267871}; // contract code -> IBKR contract id
    const OWN = "Z27";    // the contract this dataset's own call fetches
    const toRows = (code, a) => {
      if (!a || a.error || !Array.isArray(a.time)) return { code, error: (a && (a.error && (a.error.message || a.error))) || "no bars" };
      return { code, rows: a.time.map((t, i) => ({ contract: code, time: t,
        session: new Date(Date.parse(t) + 12 * 3600e3).toISOString().slice(0, 10), close: Number(a.close[i]) })) };
    };
    // One contract at a time, retrying transient connector errors, so IBKR isn't flooded.
    const wait = (ms) => new Promise((r) => setTimeout(r, ms));
    const fetchOne = async (code, id, extra) => {
      let last;
      for (let attempt = 0; attempt < 4; attempt++) {
        if (attempt) await wait(1000 * 2 ** (attempt - 1));
        try {
          const r = toRows(code, await call("get_price_history", { ...args, ...extra, contract_id: id }));
          if (r.rows || !/unavailable|retry|timeout|timed out|rate|busy|try again/i.test(r.error)) return r;
          last = r;
        } catch (e) { last = { code, error: String((e && e.message) || e) }; }
      }
      return last;
    };
    const results = [toRows(OWN, answer)];
    if (!results[0].rows) results[0] = await fetchOne(OWN, CONTRACTS[OWN], {});
    for (const [code, id] of Object.entries(CONTRACTS)) {
      if (code !== OWN) results.push(await fetchOne(code, id, { period: "ONE_MONTH", }));
    }
    const ok = results.filter((r) => r.rows && r.rows.length);
    if (!ok.length) throw new Error("IBKR returned no bars: " + results.map((r) => r.code + " " + r.error).join("; "));
    return { data: ok.flatMap((r) => r.rows), columns: ["contract", "session", "time", "close"],
      truncated: ok.length < results.length,
      meta: results.filter((r) => r.error).map((r) => ({ label: "Not loaded: " + r.code, value: String(r.error) })) };
  },
});

dash.loader("aussie_5m", {
  description: "Fetches 5-minute bars for the rest of the Aussie Bills strip and stacks them into one table.",
  fn: async ({ answer, call, args }) => {
    const CONTRACTS = {"Z26": 531965339, "H27": 549862528, "M27": 566601074, "U27": 584371135, "Z27": 602063179, "H28": 618689022, "M28": 635922922, "U28": 652809927, "Z28": 670498964, "H29": 768512916, "M29": 791433012, "Z29": 838267871}; // contract code -> IBKR contract id
    const OWN = "Z27";    // the contract this dataset's own call fetches
    const toRows = (code, a) => {
      if (!a || a.error || !Array.isArray(a.time)) return { code, error: (a && (a.error && (a.error.message || a.error))) || "no bars" };
      return { code, rows: a.time.map((t, i) => ({ contract: code, time: t,
        session: new Date(Date.parse(t) + 12 * 3600e3).toISOString().slice(0, 10), close: Number(a.close[i]) })) };
    };
    // One contract at a time, retrying transient connector errors, so IBKR isn't flooded.
    const wait = (ms) => new Promise((r) => setTimeout(r, ms));
    const fetchOne = async (code, id, extra) => {
      let last;
      for (let attempt = 0; attempt < 4; attempt++) {
        if (attempt) await wait(1000 * 2 ** (attempt - 1));
        try {
          const r = toRows(code, await call("get_price_history", { ...args, ...extra, contract_id: id }));
          if (r.rows || !/unavailable|retry|timeout|timed out|rate|busy|try again/i.test(r.error)) return r;
          last = r;
        } catch (e) { last = { code, error: String((e && e.message) || e) }; }
      }
      return last;
    };
    const results = [toRows(OWN, answer)];
    if (!results[0].rows) results[0] = await fetchOne(OWN, CONTRACTS[OWN], {});
    for (const [code, id] of Object.entries(CONTRACTS)) {
      if (code !== OWN) results.push(await fetchOne(code, id, { }));
    }
    const ok = results.filter((r) => r.rows && r.rows.length);
    if (!ok.length) throw new Error("IBKR returned no bars: " + results.map((r) => r.code + " " + r.error).join("; "));
    return { data: ok.flatMap((r) => r.rows), columns: ["contract", "session", "time", "close"],
      truncated: ok.length < results.length,
      meta: results.filter((r) => r.error).map((r) => ({ label: "Not loaded: " + r.code, value: String(r.error) })) };
  },
});

dash.loader("zq", {
  description: "Fetches every 30-day Fed Funds month through Dec 2027 and stacks them into one table.",
  fn: async ({ answer, call, args }) => {
    const CONTRACTS = {"X26": 529748903, "Z26": 535970161, "F27": 542225066, "G27": 547336122, "H27": 553809378, "J27": 559306114, "K27": 564976869, "M27": 570640401, "N27": 576721296, "Q27": 582769437, "U27": 589145411, "V27": 594762279, "X27": 600696458, "Z27": 605997126}; // contract code -> IBKR contract id
    const OWN = "X26";    // the contract this dataset's own call fetches
    const toRows = (code, a) => {
      if (!a || a.error || !Array.isArray(a.time)) return { code, error: (a && (a.error && (a.error.message || a.error))) || "no bars" };
      return { code, rows: a.time.map((t, i) => ({ contract: code, time: t,
        session: new Date(Date.parse(t) + 12 * 3600e3).toISOString().slice(0, 10), close: Number(a.close[i]) })) };
    };
    // One contract at a time, retrying transient connector errors, so IBKR isn't flooded.
    const wait = (ms) => new Promise((r) => setTimeout(r, ms));
    const fetchOne = async (code, id, extra) => {
      let last;
      for (let attempt = 0; attempt < 4; attempt++) {
        if (attempt) await wait(1000 * 2 ** (attempt - 1));
        try {
          const r = toRows(code, await call("get_price_history", { ...args, ...extra, contract_id: id }));
          if (r.rows || !/unavailable|retry|timeout|timed out|rate|busy|try again/i.test(r.error)) return r;
          last = r;
        } catch (e) { last = { code, error: String((e && e.message) || e) }; }
      }
      return last;
    };
    const results = [toRows(OWN, answer)];
    if (!results[0].rows) results[0] = await fetchOne(OWN, CONTRACTS[OWN], {});
    for (const [code, id] of Object.entries(CONTRACTS)) {
      if (code !== OWN) results.push(await fetchOne(code, id, { }));
    }
    const ok = results.filter((r) => r.rows && r.rows.length);
    if (!ok.length) throw new Error("IBKR returned no bars: " + results.map((r) => r.code + " " + r.error).join("; "));
    return { data: ok.flatMap((r) => r.rows), columns: ["contract", "session", "time", "close"],
      truncated: ok.length < results.length,
      meta: results.filter((r) => r.error).map((r) => ({ label: "Not loaded: " + r.code, value: String(r.error) })) };
  },
});
