// Drive drawings.js's own mouse handlers with a stubbed chart: the magnet's three modes, Shift while drawing
// a line, Shift while dragging one of its ends, and that Shift alone (no tool) still measures.
"use strict";
const fs = require("fs");
const path = require("path");

const handlers = {}, winHandlers = {};
const container = {
  style: {}, addEventListener: (ev, f) => { handlers[ev] = f; },
  getBoundingClientRect: () => ({ left: 0, top: 0, width: 1000, height: 600 }),
};
global.window = { addEventListener: (ev, f) => { winHandlers[ev] = f; } };
global.document = { addEventListener() {} };

// 10 px per bar, 10 px per price unit; price 100 at the top.
const BARS = Array.from({ length: 80 }, (_, i) => ({ time: 1000 + i * 60, open: 50, high: 60, low: 40, close: 55 }));
const ts = { coordinateToLogical: (x) => x / 10, logicalToCoordinate: (l) => l * 10, width: () => 1000 };
const chart = { timeScale: () => ts, applyOptions() {} };
const series = { attachPrimitive(p) { p.attached({ requestUpdate() {} }); },
                 coordinateToPrice: (y) => 100 - y / 10, priceToCoordinate: (p) => (100 - p) * 10 };
const timeline = { toTime: (i) => 1000 + i * 60, toLogical: (t) => (t - 1000) / 60,
                   barAt: (i) => BARS[Math.max(0, Math.min(BARS.length - 1, Math.round(i)))] };

eval(fs.readFileSync(path.join(__dirname, "..", "..", "..", "algo_research", "replay", "static", "drawings.js"), "utf8"));
const Drawings = global.window.Drawings;
let saved = null;
const draw = new Drawings(chart, series, {
  container, timeline, digits: () => 2, palette: () => ({}), template: () => null, tf: () => "M15",
  onChange: (items) => { saved = items; }, onSelect() {}, onEdit() {}, onContext() {}, onPick() {},
  picking: () => false, onError() {},
});

const ok = [], bad = [];
const check = (name, cond, detail) => (cond ? ok : bad).push(name + (cond || !detail ? "" : `  (${detail})`));
const ev = (x, y, shiftKey = false) => ({ button: 0, clientX: x, clientY: y, shiftKey, stopPropagation() {}, preventDefault() {} });
const yOf = (p) => (100 - p) * 10;

// ── the magnet ───────────────────────────────────────────────────────────────
// The bar under x=200 has O 50, H 60, L 40, C 55. A pointer at price 47 is 30 px from the open and 70 from the low.
draw.magnet = "weak";
check("weak: far from every price, no snap", draw.at(200, yOf(47), true).p === 47, draw.at(200, yOf(47), true).p);
check("weak: near the high, snaps to it", draw.at(200, yOf(59.2), true).p === 60, draw.at(200, yOf(59.2), true).p);
draw.magnet = "strong";
check("strong: always the nearest of the four", draw.at(200, yOf(47), true).p === 50, draw.at(200, yOf(47), true).p);
check("strong: far above the bar, the high", draw.at(200, yOf(90), true).p === 60, draw.at(200, yOf(90), true).p);
draw.magnet = false;
check("off: no snap at all", draw.at(200, yOf(59.2), true).p === 59.2, draw.at(200, yOf(59.2), true).p);
draw.magnet = true;
check("legacy true still means weak", draw.at(200, yOf(59.2), true).p === 60 && draw.at(200, yOf(47), true).p === 47);

// ── Shift keeps a line level ─────────────────────────────────────────────────
draw.magnet = false;
draw.use("trend");
handlers.mousedown(ev(100, yOf(30)));                       // the first end at price 30
handlers.mousemove(ev(400, yOf(70), true));                 // Shift: the preview stays at 30
check("Shift: the preview lies level", draw.mouse && draw.mouse.p === 30, draw.mouse && draw.mouse.p);
handlers.mousedown(ev(400, yOf(70), true));                 // the second end, with Shift
const level = saved && saved[saved.length - 1];
check("Shift: the line is drawn level", level && level.points[0].p === 30 && level.points[1].p === 30,
      level && JSON.stringify(level.points));
check("Shift: the time still follows the pointer", level && level.points[1].t === timeline.toTime(40));

draw.use("trend");
handlers.mousedown(ev(100, yOf(30)));
handlers.mousedown(ev(400, yOf(70)));                       // no Shift
const free = saved[saved.length - 1];
check("no Shift: the line goes where you point", free.points[1].p === 70, free.points[1].p);

// Shift does not flatten a fib (it would collapse it).
draw.use("fib");
handlers.mousedown(ev(100, yOf(30)));
handlers.mousedown(ev(400, yOf(70), true));
const fib = saved[saved.length - 1];
check("Shift leaves a fib alone", fib.type === "fib" && fib.points[1].p === 70, fib.points[1].p);

// ── Shift while dragging one end ─────────────────────────────────────────────
draw.select(free);
const end = { x: 400, y: yOf(70) };
draw.drag = { item: free, handle: 1, start: draw.at(end.x, end.y, false), points: JSON.parse(JSON.stringify(free.points)), moved: false };
handlers.mousemove(ev(500, yOf(85), true));
check("Shift on a dragged end: level with the other end", free.points[1].p === 30, free.points[1].p);
draw.drag = null;

// ── Shift with no tool still measures ────────────────────────────────────────
draw.cancel();
handlers.mousedown(ev(300, yOf(50), true));
check("Shift + drag with no tool still measures", !!draw.measure && !draw.measure.done);
winHandlers.mouseup();

console.log(ok.map((s) => "  ok   " + s).join("\n"));
if (bad.length) console.log(bad.map((s) => "  FAIL " + s).join("\n"));
console.log(`\n${ok.length} ok, ${bad.length} failed`);
process.exit(bad.length ? 1 : 0);
