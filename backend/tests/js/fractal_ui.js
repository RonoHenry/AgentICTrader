// A walk-through of fractal.js without a browser (algo-backtester task 337): the trader's indicator on Noculus.
// Stubs the chart and the few DOM pieces it touches, then plays the clock and checks what a person would see:
// the view is asked for at the clock and not again until a candle closes; going back, another timeframe or a
// changed input asks again; boxes, lines and labels paint in the theme; the timer counts down with the clock;
// the dialog changes an input; a refused input is said, not thrown.
"use strict";
const fs = require("fs");
const path = require("path");

const SRC = path.join(__dirname, "..", "..", "..", "algo_research", "replay", "static", "fractal.js");

global.window = {};
let primitive = null, paints = 0;
const series = { attachPrimitive(p) { primitive = p; p.attached({ requestUpdate: () => { paints++; } }); } };
const calls = [];
const ctx = new Proxy({}, {
  get: (_, k) => (k === "save" || k === "restore" || k === "beginPath" || k === "stroke" || k === "setLineDash") ? (() => calls.push([k]))
    : (k === "fillRect" || k === "strokeRect" || k === "moveTo" || k === "lineTo" || k === "fillText") ? ((...a) => calls.push([k, ...a]))
    : undefined,
  set: (_, k, v) => { calls.push(["set", k, v]); return true; },
});

const VIEW = (clock, extra = {}) => ({
  tf: "M15", clock, read_to: clock, refresh_at: clock + 900, events: [{ t: clock - 900, kind: "c2", dir: "bear", text: "Bearish C2 (15m-4H)" }],
  dashboard: { asset: "XAUUSD", ltf: "15m", htf1: "4H", htf2: "off", bias: "Neutral", valid: true, fvg: "4H", smt: ["DXY", "EURUSD"],
               remaining: "01:00:00", htf_end: clock + 3600 },
  items: [
    { k: "box", l: "zone", x1: clock - 3600, y1: 2750, x2: clock, y2: 2745, fill: "#f23645@0.06", border: null },
    { k: "box", l: "candles", x1: clock + 9000, y1: 2752, x2: clock + 10800, y2: 2748, fill: "ink@1", border: "ink@1" },
    { k: "line", l: "cisd", x1: clock - 7200, y1: 2747, x2: clock - 3600, y2: 2747, c: "#f23645@1", s: "solid", w: 2 },
    { k: "line", l: "vt", x1: clock - 7200, y1: 2760, x2: clock - 7200, y2: 2740, c: "ink@0.3", s: "solid", w: 1, ext: "both" },
    { k: "line", l: "liq", x1: clock - 7200, y1: 2735, x2: clock, y2: 2735, c: "ink@1", s: "dotted", w: 1 },
    { k: "label", l: "c2", x: clock - 5400, y: 2755, t: "C2", c: "ink@1", st: "down", sz: "small" },
    { k: "label", l: "htf_label", x: clock + 12000, y: 2760, t: "4H\n\n(01:00:00)", c: "ink@1", st: "down", sz: "large" },
    { k: "label", l: "fvg", x: clock, y: 2747.5, t: "FVG-4H", c: "#787b86@1", st: "right", sz: "small" },
  ],
  ...extra,
});

let clock = 1738080000, tf = "M15", status = { instrument: "XAUUSD" };
const asked = [];
let refuse = false;
async function api(p) {
  asked.push(p);
  if (p === "/api/watch/fractal-defaults") {
    return { settings: { fractal_mode: "Automatic", bias: "Neutral", max_display: 4, proj_show: false, dash_show: true },
             modes: ["Automatic", "Intraday", "Scalp", "Swing", "Quarterly", "Custom"], draw_only: ["bias", "proj_show", "dash_show"] };
  }
  if (p.startsWith("/api/watch/fractal?")) {
    if (refuse) throw new Error("max_display: at least 4");
    const q = new URLSearchParams(p.split("?")[1]);
    return VIEW(Number(q.get("t")), { tf: q.get("tf") });
  }
  throw new Error("unexpected " + p);
}

const said = [], prefs = {};
let built = null;
global.window.ReplayUI = {
  el: (tag, attrs, ...kids) => ({ tag, attrs: attrs || {}, kids: kids.flat(), value: "", checked: false, onchange: null, append(...k) { this.kids.push(...k); } }),
  dialog: (title, tabs, footer) => { built = { title, tabs, footer, closed: false }; return { close() { built.closed = true; } }; },
};
eval(fs.readFileSync(SRC, "utf8"));
const FractalPOI = global.window.FractalPOI;

const fp = new FractalPOI({}, series, {
  X: (t) => (t - 1738070000) / 900 * 8, Y: (p) => 400 - (p - 2740) * 10, palette: () => ({ ink: "#131722" }),
  api, tf: () => tf, clock: () => clock, status: () => status, instruments: () => ["DXY", "EURUSD", "XAUUSD"],
  prefs: { get: (k, d) => (k in prefs ? prefs[k] : d), set: (k, v) => { prefs[k] = v; } }, say: (t) => said.push(t),
  refresh: () => {}, onView: () => {},
});

const ok = [], bad = [];
const check = (name, cond) => (cond ? ok : bad).push(name);
const fetches = () => asked.filter((p) => p.startsWith("/api/watch/fractal?")).length;

(async () => {
  await fp.tick();
  check("asks for the view at the clock on the chart's timeframe", /tf=M15&t=1738080000&s=%7B%7D/.test(asked[asked.length - 1]));
  check("loads the defaults once", asked.filter((p) => p === "/api/watch/fractal-defaults").length === 1);
  clock += 300; await fp.tick();
  check("doesn't ask again before a candle closes", fetches() === 1);
  clock += 600; await fp.tick();
  check("asks again once the candle has closed (refresh_at)", fetches() === 2);
  clock -= 3600; await fp.tick();
  check("asks again when the clock goes back", fetches() === 3);
  tf = "M5"; await fp.tick();
  check("asks again on another timeframe", fetches() === 4 && /tf=M5/.test(asked[asked.length - 1]));

  calls.length = 0;
  fp.paint(ctx, { width: 900, height: 500 });
  const rects = calls.filter((c) => c[0] === "fillRect"), texts = calls.filter((c) => c[0] === "fillText").map((c) => c[1]);
  check("paints both boxes", rects.length === 2);
  check("paints the labels", texts.includes("C2") && texts.includes("FVG-4H") && texts.includes("4H"));
  check("the HTF timer counts from the clock", texts.includes("(01:00:00)"));
  check("a vertical line spans the pane", calls.some((c) => c[0] === "lineTo" && c[2] === 500));
  check("the indicator's black is the theme's ink", calls.some((c) => c[0] === "set" && c[1] === "fillStyle" && c[2] === "rgba(19,23,34,1)"));
  check("dotted lines are dotted", calls.some((c) => c[0] === "setLineDash"));
  clock += 600;
  calls.length = 0; fp.paint(ctx, { width: 900, height: 500 });
  check("the timer moves with the clock between fetches", calls.some((c) => c[0] === "fillText" && c[1] === "(50:00)"));

  const html = fp.panel();
  check("the dashboard names the alignment and the partners", /XAUUSD · 15m \/ 4H \/ off/.test(html) && /DXY, EURUSD/.test(html));
  check("the events go to the log", fp.events().length === 1 && /Bearish C2/.test(fp.events()[0].text));

  await fp.dialog();
  check("the dialog opens with the indicator's tabs", built && built.title === "Fractal + POI" &&
        built.tabs.map((t) => t.name).join(",") === "Inputs,Model,HTF,Liquidity,FVG & SMT");
  const body = { kids: [], append(...k) { this.kids.push(...k); } };
  built.tabs[0].build(body);
  const biasRow = body.kids.find((r) => r.kids && r.kids[0] && r.kids[0].kids && r.kids[0].kids[0] === "Bias");
  const select = biasRow.kids[1];
  select.value = "Bearish"; select.onchange();
  await new Promise((r) => setTimeout(r, 0)); await fp.busy;
  check("a changed input is kept in this browser and asked for", prefs["watch.fractal"].bias === "Bearish" &&
        /bias%22%3A%22Bearish/.test(asked[asked.length - 1]));
  select.value = "Neutral"; select.onchange();
  await new Promise((r) => setTimeout(r, 0)); await fp.busy;
  check("an input back at its default is dropped", !("bias" in prefs["watch.fractal"]));

  refuse = true; clock += 3600;
  await fp.tick();
  check("a refused input is said, and the last view kept", said.some((t) => /Fractal \+ POI: max_display/.test(t)) && fp.view !== null);
  refuse = false;

  fp.setOn(false);
  calls.length = 0; fp.paint(ctx, { width: 900, height: 500 });
  check("switched off, nothing paints and nothing is asked", calls.length === 0 && fp.panel() === "" && fp.events().length === 0);
  status = null; fp.setOn(true); const before = asked.length; await fp.tick();
  check("no session, no question", asked.length === before);

  for (const n of ok) console.log("  ok   " + n);
  for (const n of bad) console.log("  FAIL " + n);
  console.log(`\n${ok.length} passed, ${bad.length} failed`);
  process.exit(bad.length ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(1); });
