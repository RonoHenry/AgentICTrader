// A live session on the page (algo-backtester Requirement 27): started live, opened at the last closed minute,
// following the session as it moves on, staying where the trader stepped back to, and live again after a restart.
// The browser is stubbed as in reconnect_ui.js; timers run fast.
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
const realSetTimeout = setTimeout;
global.setTimeout = (f, ms) => realSetTimeout(f, Math.min(ms || 0, 5));
global.__realSetTimeout = realSetTimeout;
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


// ── a fetch that plays a live session ────────────────────────────────────────────
const calls = [];
const E0 = 1792677600;                                   // the last closed minute when the session opens
const live = { end: E0, version: 0, started: false };
const meta = { instruments: ["XAUUSD"], variants: ["base", "fresh_near_gap"], live: true, first: "2025-01-01", last: "2025-06-30",
               max_days: 5, timeframes: ["M1", "M15"], config: "config/backtests/focus.toml" };
const status = () => ({ state: live.started ? "ready" : "none", progress: 1, message: "", instrument: "XAUUSD", variant: "fresh_near_gap",
                        first_day: "2026-10-22", days: 1, start: E0 - 70000, end: live.end, digits: 3,
                        summary: { orders: 0, trades: 0, total_r: 0 }, closes: 70, blind: false, revealed_at: null,
                        live: true, version: live.version });
const reply = (code, body) => ({ ok: code < 400, status: code, statusText: String(code), json: async () => body });
global.fetch = async (url, init) => {
  const body = init && init.body ? JSON.parse(init.body) : undefined;
  calls.push([url, body]);
  if (url === "/api/watch/meta") return reply(200, meta);
  if (url === "/api/watch/start") { live.started = true; return reply(200, { ...status(), state: "preparing" }); }
  if (url === "/api/watch/status") return reply(200, status());
  if (url === "/api/watch/journal") return reply(200, { rows: [], ideas: [] });
  if (url === "/api/watch/picks") return reply(200, { picks: [] });
  if (url === "/api/watch/noculus") return reply(200, { session: {}, marks: [], trades: [], positions: [], reveal: null, comparison: null });
  if (url.startsWith("/api/watch/noculus/trades")) return reply(200, { trades: [] });
  if (url.startsWith("/api/watch/bars")) {
    const until = Number(/until=(\d+)/.exec(url)[1]);
    return reply(200, { tf: "M15", bars: [{ time: until - 60, open: 1, high: 2, low: 0.5, close: 1.5 }] });
  }
  if (url.startsWith("/api/watch/state")) return reply(200, { state: { t: Number(/t=(\d+)/.exec(url)[1]), arrays: [], pools: [] } });
  if (url.startsWith("/api/watch/model-a")) return reply(200, { set: "model_d1", instances: [] });
  if (url.startsWith("/api/blind")) return reply(200, { days: 0, unread: 0 });
  return reply(200, {});
};

const files = ["drawings.js", "settings.js", "motion.js", "noculus.js", "fractal.js", "shell.js"];
for (const name of files) (0, eval)(fs.readFileSync(path.join(STATIC, name), "utf8"));
global.__calls = calls; global.__live = live; global.__E0 = E0;
(0, eval)(fs.readFileSync(path.join(STATIC, "engine.js"), "utf8") + fs.readFileSync(path.join(__dirname, "live_probe.txt"), "utf8"));
