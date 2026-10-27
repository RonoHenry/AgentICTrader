// The Chain & stack layer on the Noculus page (2026-10-24), without a browser: the page's real scripts load as
// separate scripts in one context (as the page's <script> tags do), then the layer is fed a served view and checked
// for what a person would see: the strip of D1 calls with their scores and ticks, the latest close's ranges, POIs
// and draw, the panel's words, nothing while blind, and one question per trading day.
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const STATIC = path.join(__dirname, "..", "..", "..", "algo_research", "replay", "static");

const el = (id) => {
  const node = {
    id, innerHTML: "", textContent: "", value: "", disabled: false, style: {}, children: [],
    classList: { add() {}, remove() {}, toggle() {}, contains: () => false },
    dataset: {}, onclick: null, onchange: null, parentElement: null,
    appendChild() {}, append() {}, replaceChildren() {}, addEventListener() {}, removeEventListener() {},
    querySelectorAll: () => [], querySelector: () => null, getBoundingClientRect: () => ({ left: 0, top: 0, width: 900, height: 500 }),
    setAttribute() {}, getAttribute: () => null, remove() {}, focus() {}, blur() {}, close() {}, showModal() {},
    insertAdjacentHTML() {}, cloneNode() { return el(id); },
  };
  node.parentElement = node;
  return node;
};

const nodes = new Map();
global.document = {
  documentElement: el("html"),
  body: el("body"),
  getElementById: (id) => { if (!nodes.has(id)) nodes.set(id, el(id)); return nodes.get(id); },
  createElement: (t) => el(t),
  querySelector: () => null,
  querySelectorAll: () => [],
  addEventListener() {},
};
global.getComputedStyle = () => ({ getPropertyValue: () => "#888888" });
global.matchMedia = () => ({ addEventListener() {}, matches: false });
global.location = { search: "", href: "" };
global.localStorage = { getItem: () => null, setItem() {}, removeItem() {} };
global.window = global;
global.addEventListener = () => {};
global.ResizeObserver = class { observe() {} unobserve() {} disconnect() {} };
global.MutationObserver = class { observe() {} disconnect() {} };
global.removeEventListener = () => {};
global.innerWidth = 1600; global.innerHeight = 900; global.devicePixelRatio = 1;
global.requestAnimationFrame = (f) => setTimeout(f, 0);
global.setTimeout = setTimeout;
global.confirm = () => false;
global.alert = () => {};
global.URLSearchParams = URLSearchParams;

// Lightweight Charts, as much of it as the page touches at load.
const series = {
  attachPrimitive(p) { if (p && p.attached) p.attached({ requestUpdate() {} }); },
  applyOptions() {}, setData() {}, priceToCoordinate: () => 100, coordinateToPrice: () => 1.1,
  createPriceLine: () => ({ applyOptions() {} }), removePriceLine() {}, priceScale: () => ({ applyOptions() {} }),
  setMarkers() {}, update() {}, data: () => [],
};
const timeScale = {
  applyOptions() {}, fitContent() {}, setVisibleLogicalRange() {}, getVisibleLogicalRange: () => ({ from: 0, to: 10 }),
  logicalToCoordinate: () => 10, coordinateToLogical: () => 1, subscribeVisibleLogicalRangeChange() {},
  scrollToPosition() {}, options: () => ({ rightOffset: 14 }), width: () => 900,
};
global.LightweightCharts = {
  createChart: () => ({
    addCandlestickSeries: () => series, addLineSeries: () => series, addHistogramSeries: () => series,
    applyOptions() {}, timeScale: () => timeScale, priceScale: () => ({ applyOptions() {} }),
    subscribeCrosshairMove() {}, subscribeClick() {}, unsubscribeClick() {}, remove() {},
    takeScreenshot: () => ({}), chartElement: () => el("chart"),
  }),
  CrosshairMode: { Normal: 0, Magnet: 1 },
  PriceScaleMode: { Normal: 0, Logarithmic: 1, Percentage: 2 },
  LineStyle: { Solid: 0, Dotted: 1, Dashed: 2 },
};
global.ReplayUI = { Prefs: { get: (k, d) => d, set() {} }, toolSettings() {}, contextMenu() {} };
global.Shell = { init: async () => {}, setInstrument() {}, refresh() {} };

const asked = [];
let served = { withheld: false, smt: "abstains: one market on this chart", rows: [] };
global.fetch = async (url) => {
  asked.push(String(url));
  if (String(url).startsWith("/api/watch/chain")) return { ok: true, status: 200, json: async () => served };
  return { ok: false, status: 503, json: async () => ({ error: "stub" }), statusText: "stub" };
};
for (const name of ["drawings.js", "settings.js", "motion.js", "noculus.js", "fractal.js", "shell.js", "engine.js"]) {
  vm.runInThisContext(fs.readFileSync(path.join(STATIC, name), "utf8"), { filename: name });
}

const frame = (tf, lo, hi, zone, extra) => ({ tf, range: [lo, hi], position: 0.7, zone, trend: "NEUTRAL", own: "BULLISH",
  draw: null, poi_bull: null, poi_bear: null, reasons: { range: `range ${lo}-${hi}`, own: "toward PDH", poi_bullish: "none",
  poi_bearish: "none" }, ...(extra || {}) });
const votes = { "own-MN1": 1, "own-W1": 1, "own-D1": 1, "H-K": 1, profile: 1, "zone-W1": -1, "zone-D1": 0, structure: 1,
                closes: 1, liquidity: 0, arrays: 1, po3: 1, smt: 0 };
const day = (i, call, next, score) => ({ i, open: 1000 + 86400 * i, close: 1000 + 86400 * (i + 1), frames: [
    frame("MN1", 1.05, 1.15, "PREMIUM"), frame("W1", 1.08, 1.12, "PREMIUM",
      { poi_bull: { low: 1.085, high: 1.09, near: 1.09, kind: "FVG", tf: "W1", formed: 900, reached: null } }),
    frame("D1", 1.095, 1.11, "PREMIUM")],
  links: [{ tf: "MN1", context: "BULLISH", case: "TOP", draw: null, reason: "MN1 top frame" },
          { tf: "W1", context: "BULLISH", case: "WITH_PARENT", draw: null, reason: "W1 with MN1" },
          { tf: "D1", context: "BULLISH", case: "WITH_PARENT", draw: { price: 1.1102, source: "PDH", tf: "D1", kind: "POOL" },
            reason: "MN1 BULLISH ... D1 BULLISH toward D1 PDH 1.1102" }],
  profile: null, votes, score, ranged: true, call, chain_call: 1, next });

const ok = [], bad = [];
const check = (name, cond) => (cond ? ok : bad).push(name);
const calls = [];
const ctx = new Proxy({}, { get: (_, k) => (k === "fillRect" || k === "strokeRect") ? ((...a) => calls.push([k, ...a]))
                                      : () => {}, set: () => true });
const text = (s, x, y, color, align) => calls.push(["fillText", s, x, y, color, align]);
const line = (...a) => calls.push(["line", ...a]);
const texts = () => calls.filter((c) => c[0] === "fillText").map((c) => c[1]);

(async () => {
  vm.runInThisContext(`S.status = { instrument: "EURUSD" }; S.layers.chain = true; S.t = 1000 + 86400 * 3 + 3600;`);
  served.rows = [day(0, 0, -1, 4), day(1, 1, 1, 9), day(2, 1, null, 8)];
  await vm.runInThisContext("loadChain()");
  check("asks for the chain at the clock", /\/api\/watch\/chain\?t=\d+/.test(asked[asked.length - 1]));
  const n = asked.length;
  vm.runInThisContext("S.t += 600"); await vm.runInThisContext("loadChain()");
  check("doesn't ask again before the next D1 close", asked.length === n);
  vm.runInThisContext("S.t += 86400"); await vm.runInThisContext("loadChain()");
  check("asks again once a D1 candle has closed", asked.length === n + 1);

  vm.runInThisContext("paintChain")(ctx, { width: 900, height: 500 }, vm.runInThisContext("palette()"), text, line);
  const rects = calls.filter((c) => c[0] === "fillRect");
  check("a strip cell and a chain bar per D1 close", rects.filter((c) => c[2] === 2).length === 3 && rects.filter((c) => c[2] === 11).length === 3);
  check("each cell carries its score, a tick once right", texts().includes("+4") && texts().includes("+9 ✓") && texts().includes("+8"));
  check("the latest close's W1 range and 50% are labelled", texts().some((t) => /^W1 high 1\.1/.test(t)) && texts().some((t) => /^W1 50% · PREMIUM 70%/.test(t)));
  check("the W1 POI is boxed and named", calls.some((c) => c[0] === "strokeRect") && texts().includes("W1 POI · FVG unreached"));
  check("the chain's draw is drawn", texts().some((t) => /^draw → D1 PDH 1\.1102/.test(t)));
  check("the summary names the call", texts().some((t) => /Chain: D1 BULLISH \(with parent\) · stack \+8 of 13 · call up/.test(t)));

  const html = vm.runInThisContext("chainCard()");
  check("the card gives the score and the call", /Stack <b>\+8<\/b> of 13: <b>up<\/b>/.test(html) && /the chain alone ▲/.test(html));
  check("the card spells out the votes and the frames", /candle profile ▲/.test(html) && /W1 P\/D ▼/.test(html) && /<b>W1<\/b> own BULLISH/.test(html));
  check("the card counts the resolved calls", /1 stack call\(s\) resolved, 1 right/.test(html) && /SMT abstains/.test(html));

  served = { withheld: true, rows: [] };
  vm.runInThisContext("S.t += 86400"); await vm.runInThisContext("loadChain()");
  calls.length = 0;
  vm.runInThisContext("paintChain")(ctx, { width: 900, height: 500 }, vm.runInThisContext("palette()"), text, line);
  check("blind: only a note paints", calls.length === 1 && /hidden until you reveal/.test(texts()[0]));
  check("blind: the card says so", /Hidden: this session is blind/.test(vm.runInThisContext("chainCard()")));

  vm.runInThisContext("S.layers.chain = false"); const before = asked.length; await vm.runInThisContext("loadChain()");
  check("switched off, nothing is asked", asked.length === before && vm.runInThisContext("S.chain.rows.length") === 0);

  for (const x of ok) console.log("  ok   " + x);
  for (const x of bad) console.log("  FAIL " + x);
  console.log(`\n${ok.length} passed, ${bad.length} failed`);
  process.exit(bad.length ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(1); });
