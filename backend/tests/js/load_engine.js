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

const order = ["drawings.js", "settings.js", "motion.js", "noculus.js", "shell.js", "engine.js"];
for (const name of order) {
  const file = path.join(STATIC, name);
  if (!fs.existsSync(file)) { console.log(`MISSING ${name}`); continue; }
  try {
    // eslint-disable-next-line no-eval
    (0, eval)(fs.readFileSync(file, "utf8"));
    console.log(`  ok   ${name}`);
  } catch (e) {
    console.log(`  THROW ${name}: ${e.constructor.name}: ${e.message}`);
    console.log(String(e.stack).split("\n").slice(0, 6).map((l) => "        " + l.trim()).join("\n"));
    process.exitCode = 1;
  }
}
console.log("\nwindow.Noculus:", typeof global.Noculus, " window.Drawings:", typeof global.Drawings,
            " window.Motion:", typeof global.Motion);
