// Load drawings.js, motion.js, noculus.js and engine.js the way the page does, with the
// browser pieces stubbed, and report whatever the top level throws. A throw here is a blank page.
"use strict";
const fs = require("fs");
const path = require("path");

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
global.fetch = async () => ({ ok: false, status: 503, json: async () => ({ error: "stub" }), statusText: "stub" });
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



// ── a fetch whose server has no Thesis Engine route yet, then one that has it ─────────────
const status = { state: "ready", progress: 1, message: "", instrument: "XAUUSD", variant: "gap", first_day: "2025-03-12",
                 days: 2, start: 1741730400, end: 1741903200, digits: 3, summary: {}, closes: 180, blind: false, revealed_at: null };
const reply = (code, body) => ({ ok: code < 400, status: code, statusText: String(code), json: async () => body });
let routed = false;
const answer = { withheld: false, source: "ORACLE", version: "v2", words: "the week's real side: hindsight, not a call", hindsight: true,
  moves: [{ t: 1741740000, from: "FLAT", to: "THESIS", reason: "ORACLE, bullish", thesis_id: "a", level_id: null },
          { t: 1741743600, from: "THESIS", to: "IN_TRADE", reason: "the hand", thesis_id: "a", level_id: null }],
  now: { t: 1741743600, from: "THESIS", to: "IN_TRADE", reason: "the hand", thesis_id: "a", level_id: null },
  thesis: { id: "a", side: "BULLISH", draw: 2.5, protected: 0.5, since: 1741740000, until: 1742000000, note: "", source: "ORACLE" },
  level: null, theses: [{ id: "a", side: "BULLISH", draw: 2.5, protected: 0.5, since: 1741740000, until: 1742000000, note: "", source: "ORACLE" }],
  levels: [], sweeps: [{ t: 1741743000, price: 1.0, pool: "the M5 swing low 1" }], skips: [],
  trades: [{ placed: 1741743600, filled: 1741743600, closed: null, direction: "LONG", fill: 1.2, stop: 1.0, target: 2.5,
             exit: null, reason: null, net_r: null, risk_spreads: null }],
  orders: [{ placed: 1741743600, ended: null, outcome: null, kind: "LIMIT", direction: "LONG", entry: 1.1, stop: 1.0, target: 2.5 }],
  no_displacement: [{ t: 1741743300, pool: "the Asia low 1", body: 0.1, reach: 0.2 }] };
global.__urls = [];
global.fetch = async (url) => {
  if (url.startsWith("/api/watch/thesis")) {
    global.__urls.push(url);
    if (!routed) return reply(404, { error: "no such path /api/watch/thesis" });
    return /source=ORACLE/.test(url) ? reply(200, { ...answer, any: true, next_trade: 1741800000 })
      : reply(200, { ...answer, source: "SCENARIO", any: false, words: "your calls", hindsight: false, moves: [], now: null,
                     thesis: null, theses: [], sweeps: [], trades: [], next_trade: null });
  }
  if (url === "/api/watch/status") return reply(200, status);
  return reply(200, {});
};

const files = ["drawings.js", "settings.js", "motion.js", "noculus.js", "fractal.js", "shell.js"];
for (const name of files) (0, eval)(fs.readFileSync(path.join(STATIC, name), "utf8"));
global.__status = status;
global.__route = () => { routed = true; };
(0, eval)(fs.readFileSync(path.join(STATIC, "engine.js"), "utf8") + fs.readFileSync(path.join(__dirname, "thesis_probe.txt"), "utf8"));
