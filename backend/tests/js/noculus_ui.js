// A walk-through of noculus.js without a browser: stub the few DOM and chart pieces it touches,
// then arm each tool, click a candle, draw, delete, place and close a trade, and reveal.
// Checks what a human would look for: the right body goes to the server, the panel lists what
// came back, the boxes and the trade lines paint, and nothing throws.
"use strict";
const fs = require("fs");
const path = require("path");

const SRC = path.join(__dirname, "..", "..", "..", "algo_research", "replay", "static", "noculus.js");

// ── the smallest DOM the module uses ─────────────────────────────────────────
const classList = () => {
  const set = new Set();
  return { set, add: (c) => set.add(c), remove: (c) => set.delete(c), contains: (c) => set.has(c),
           toggle: (c, on) => (on === undefined ? (set.has(c) ? set.delete(c) : set.add(c)) : on ? set.add(c) : set.delete(c)) };
};

class El {
  constructor(id) {
    this.id = id || ""; this._html = ""; this.value = ""; this.disabled = false;
    this.onclick = null; this.onchange = null; this.classList = classList(); this.dataset = {};
    this.nodes = new Map();                       // children looked up by id, kept across renders
  }
  get innerHTML() { return this._html; }
  set innerHTML(v) { this._html = String(v); }
  querySelectorAll(sel) {
    const attr = /\[data-([\w-]+)]/.exec(sel);
    if (!attr) return [];
    const key = attr[1].replace(/-(\w)/g, (_, c) => c.toUpperCase());
    const out = [];
    for (const m of this._html.matchAll(new RegExp(`data-${attr[1]}="([^"]+)"`, "g"))) {
      const el = new El();
      el.dataset[key] = m[1];
      out.push(el);
    }
    return out;
  }
  querySelector(sel) {
    const id = sel.replace("#", "");
    if (!this._html.includes(`id="${id}"`)) return null;
    if (!this.nodes.has(id)) this.nodes.set(id, new El(id));
    return this.nodes.get(id);
  }
}

global.document = { body: { classList: classList() } };
global.window = {};
global.confirm = () => true;

const SECONDS = { M1: 60, M5: 300, M15: 900, M30: 1800, H1: 3600, H4: 14400, D1: 86400, W1: 604800 };
const BARS = Array.from({ length: 40 }, (_, i) => ({ time: 1790539200 + i * 900, open: 1.1, high: 1.11, low: 1.09, close: 1.105 }));

// ── the chart pieces ────────────────────────────────────────────────────────
let primitive = null, paints = 0, drawn = [];
const series = { attachPrimitive(p) { primitive = p; p.attached({ requestUpdate: () => { paints++; } }); } };
const ctx = { save() {}, restore() {}, beginPath() {}, moveTo() {}, lineTo() {}, stroke() {}, fillRect() {}, strokeRect() {},
              setLineDash() {}, fillText(s) { drawn.push(s); }, set font(v) {}, set textBaseline(v) {}, set textAlign(v) {},
              set fillStyle(v) {}, set strokeStyle(v) {}, set lineWidth(v) {} };

// ── the session the page would be looking at ────────────────────────────────
const sent = [];
let journal = { session: { instrument: "EURUSD" }, marks: [], trades: [], reveal: null, comparison: null };
let status = { instrument: "EURUSD", first_day: "2026-09-30", days: 1, blind: true, revealed_at: null, summary: {} };
const said = [];

async function api(p, b) {
  sent.push([p, b]);
  if (p === "/api/watch/noculus") return JSON.parse(JSON.stringify(journal));
  if (p === "/api/watch/noculus/mark") {
    if (b.tf === "H4" && b.tool === "IFVG") throw new Error("no H4 close beyond it yet: it is still an FVG");
    const m = { id: `m${journal.marks.length + 1}`, tool: b.tool, tf: b.tf, direction: b.tool === "OB" ? -1 : 1,
                low: 1.0905, high: 1.0925, mid: 1.0915, formed_at: b.candle + SECONDS[b.tf],
                candles: [b.candle - 2 * SECONDS[b.tf], b.candle - SECONDS[b.tf], b.candle], clock: b.t,
                note: b.note || "", deleted_at: null };
    journal.marks.push(m);
    return m;
  }
  if (p === "/api/watch/noculus/unmark") {
    const m = journal.marks.find((x) => x.id === b.id);
    m.deleted_at = b.t;
    return m;
  }
  if (p === "/api/watch/noculus/place") {
    const long = b.direction === "LONG";                // the server's own rule: the stop sits behind the entry
    if (long ? b.stop >= 1.105 : b.stop <= 1.105) {
      throw new Error(`stop: ${long ? "below" : "above"} the entry (1.10500)`);
    }
    const x = { id: `t${journal.trades.length + 1}`, direction: b.direction, kind: b.kind, price: b.price || null,
                stop: b.stop, target: b.target, expiry: null, mark: b.mark || null, placed_at: b.t, note: b.note || "",
                state: "PENDING", fill: null, fill_bid: null, filled_at: null, exit: null, exit_bid: null, exit_at: null,
                outcome: null, risk: null, gross_r: null, net_r: null, commission_r: null, mfe_r: null, mae_r: null,
                live_r: null, ambiguous: false, settled_to: b.t };
    journal.trades.push(x);
    return x;
  }
  if (p.startsWith("/api/watch/noculus/trades")) {
    for (const x of journal.trades) {
      if (x.state === "PENDING") Object.assign(x, { state: "OPEN", fill: 1.1051, fill_bid: 1.105, filled_at: BARS[21].time,
                                                    risk: 0.002, live_r: 0.35 });
    }
    return { trades: JSON.parse(JSON.stringify(journal.trades)) };
  }
  if (p === "/api/watch/noculus/close") {
    const x = journal.trades.find((y) => y.id === b.id);
    Object.assign(x, { state: "CLOSED", outcome: "MANUAL", exit: 1.1058, exit_at: b.t, net_r: 0.33, live_r: null });
    return JSON.parse(JSON.stringify(x));
  }
  if (p === "/api/watch/reveal") { status = { ...status, revealed_at: b.t }; return status; }
  if (p === "/api/watch/noculus/comparison") {
    return { clock: b === undefined ? 0 : 0, arrays: { counts: { mine: 1, matched: 1, mine_only: 0, engine_only: 4 },
             by_kind: { FVG: { mine: 1, matched: 1 } }, by_tf: { M15: { mine: 1, matched: 1 } },
             matched: [], mine_only: [], engine_only: [] },
             trades: { days: [{ day: "2026-09-30", pairs: [{ mine: { direction: "LONG", entry: 1.1051, outcome: "MANUAL", net_r: 0.33 },
                                 engine: { direction: "SHORT", entry: 1.104, outcome: "STOP", net_r: -1 }, same_side: false,
                                 apart_minutes: 12.5 }], mine_only: [], engine_only: [], mine_r: 0.33, engine_r: -1,
                               disagreed: true }],
                       totals: { mine: 1, engine: 1, mine_r: 0.33, engine_r: -1, days_apart: 1 } } };
  }
  throw new Error("unexpected " + p);
}

const panel = new El("noculus");
eval(fs.readFileSync(SRC, "utf8"));                   // installs window.Noculus
const Noculus = global.window.Noculus;

const CLOCK = BARS[20].time + 900;
let revealed = null;
const opts = {
  box: panel, palette: () => ({ good: "#1a9c5b", warn: "#c08a00", muted: "#888888", accent: "#3b7ddd", bad: "#c0392b" }),
  timeline: { barAt: (i) => BARS[Math.max(0, Math.min(BARS.length - 1, Math.round(i)))] },
  seconds: (tf) => SECONDS[tf], timeframes: Object.keys(SECONDS), tf: () => "M15", digits: () => 5,
  clock: () => CLOCK, status: () => status, api, say: (t) => said.push(t), refresh: () => { paints++; },
  timeLabel: (t) => "Wed " + new Date(t * 1000).getUTCHours() + ":00", X: (t) => (t - BARS[0].time) / 900 * 8,
  Y: (p) => 400 - (p - 1.09) * 10000, onReveal: async (s) => { revealed = s; },
};

const ok = [], bad = [];
const check = (name, cond) => (cond ? ok : bad).push(name);
const last = (a) => a[a.length - 1];

(async () => {
  const n = new Noculus({}, series, opts);
  check("a primitive is attached", !!primitive);
  await n.sync();
  check("the journal is read while blind", sent[0][0] === "/api/watch/noculus");
  check("the panel is headed Noculus", panel.innerHTML.includes("<h2>Noculus</h2>"));
  check("it offers the four tools", ["FVG", "IFVG", "OB", "BRK"].every((t) =>
    panel.querySelector("#nTools").innerHTML.includes(`data-arm="${t}"`)));
  check("nothing marked yet", panel.querySelector("#nMarks").innerHTML.includes("No marks yet."));
  check("no trades yet", panel.querySelector("#nTrades").innerHTML.includes("No trades yet."));
  check("the ticket is there", panel.innerHTML.includes('id="nPlace"') && panel.innerHTML.includes('id="nKind"'));
  check("the limit price starts off", panel.querySelector("#nPrice").disabled === true);
  check("a reveal button is there", panel.innerHTML.includes('id="nReveal"'));

  // ── marks ────────────────────────────────────────────────────────────────
  n.arm("FVG");
  check("arming sets the cursor", n.armed() && document.body.classList.contains("picking"));
  check("it says what to click", /Click the gap's third candle/.test(last(said)));
  await n.pick({ index: 20 });
  const [p1, b1] = last(sent);
  check("the click posts a mark", p1 === "/api/watch/noculus/mark");
  check("on the chart's timeframe", b1.tf === "M15" && b1.tool === "FVG");
  check("at the clicked candle", b1.candle === BARS[20].time && b1.t === CLOCK);
  check("the tool is put down", !n.armed() && !document.body.classList.contains("picking"));
  check("the panel lists it", panel.querySelector("#nMarks").innerHTML.includes("M15 FVG"));
  check("and it can be tied to a trade", panel.querySelector("#nMark").innerHTML.includes('value="m1"'));

  n.tf = "H1"; n.arm("OB");
  await n.pick({ index: 23 });
  const b2 = last(sent)[1];
  check("an H1 mark floors to the H1 candle", b2.tf === "H1" && b2.candle === Math.floor(BARS[23].time / 3600) * 3600);
  check("the block's direction goes with it", b2.direction === 0);
  n.dir = -1; n.arm("OB"); await n.pick({ index: 23 });
  check("a chosen direction goes with it", last(sent)[1].direction === -1);

  const before = n.marks.length;
  n.tf = "H4"; n.arm("IFVG");
  await n.pick({ index: 30 });
  check("a refusal is shown", last(said).includes("still an FVG"));
  check("and nothing is kept", n.marks.length === before);

  // ── the ticket ───────────────────────────────────────────────────────────
  n.armField("nStop", "stop");
  check("a price field can be picked", n.armed() && n.field === "nStop");
  await n.pick({ index: 20, p: 1.1035 });
  check("the click fills the field", panel.querySelector("#nStop").value === "1.10350" && !n.armed());
  panel.querySelector("#nTarget").value = "1.1090";
  panel.querySelector("#nKind").value = "MARKET";
  panel.querySelector("#nNote").value = "my long";
  await n.place();
  const [p3, b3] = last(sent);
  check("the ticket posts a trade", p3 === "/api/watch/noculus/place");
  check("with the side, the stop and the target", b3.direction === "LONG" && b3.stop === 1.1035 && b3.target === 1.109);
  check("and the clock", b3.t === CLOCK && b3.kind === "MARKET");
  check("the panel lists it as waiting", panel.querySelector("#nTrades").innerHTML.includes("waiting"));
  check("the fields are cleared", panel.querySelector("#nStop").value === "");

  n.side = "SHORT";
  panel.querySelector("#nStop").value = "1.1000";       // a short with the stop below: the server refuses
  panel.querySelector("#nTarget").value = "1.0900";
  await n.place();
  check("a refused ticket says why", last(said).includes("above the entry"));

  // the clock moves: the trade fills and shows its live R
  await n.tick();
  check("the clock settles the trades", last(sent)[0].startsWith("/api/watch/noculus/trades"));
  check("an open trade shows its live R", panel.querySelector("#nTrades").innerHTML.includes("+0.35R now"));
  check("and offers to close it", panel.querySelector("#nTrades").innerHTML.includes('data-close="t1"'));

  // ── the chart ────────────────────────────────────────────────────────────
  drawn = [];
  n.paint(ctx, { width: 900, height: 500 });
  check("every mark is drawn with its label", drawn.filter((s) => s.startsWith("mine: M15 FVG")).length === 1);
  check("the open trade is drawn", drawn.some((s) => s.startsWith("mine: LONG +0.35R")));

  await n.closeTrade("t1");
  check("closing by hand is posted", last(sent)[0] === "/api/watch/noculus/close");
  check("and the R is shown", panel.querySelector("#nTrades").innerHTML.includes("MANUAL +0.33R"));
  check("with the day's total", panel.querySelector("#nTrades").innerHTML.includes("1 closed"));
  drawn = [];
  n.paint(ctx, { width: 900, height: 500 });
  check("the closed trade is drawn with its outcome", drawn.some((s) => s.includes("MANUAL +0.33R")));

  await n.unmark("m1");
  check("a deleted mark leaves the chart", !n.marks.some((m) => m.id === "m1"));
  check("and stays in the journal", journal.marks.some((m) => m.id === "m1" && m.deleted_at === CLOCK));

  // ── reveal ───────────────────────────────────────────────────────────────
  await n.reveal();
  check("reveal is posted", sent.some(([p]) => p === "/api/watch/reveal"));
  check("the page is told", revealed && revealed.revealed_at === CLOCK);
  n.render();
  check("the tools are gone", !panel.innerHTML.includes("data-arm=") && !panel.innerHTML.includes('id="nPlace"'));
  check("it says when it was revealed", panel.innerHTML.includes("Revealed at"));
  check("the trades are still listed", panel.querySelector("#nTrades").innerHTML.includes("MANUAL"));
  const diff = panel.querySelector("#nDiff").innerHTML;
  check("the comparison is shown", diff.includes("You against the engine"));
  check("it counts the marks the engine also had", diff.includes("1 of your 1 marks"));
  check("it names the engine's arrays you didn't mark", diff.includes("4 of its own"));
  check("it puts the day's trades side by side", diff.includes("the other side") && diff.includes("12.5 min apart"));
  check("and flags the day", diff.includes("read differently"));
  check("marking is over", !n.marking && !n.armed());

  status = { ...status, blind: false, revealed_at: null };
  await n.sync();
  check("an open session shows no Noculus panel", panel.innerHTML === "");

  console.log(ok.map((s) => "  ok   " + s).join("\n"));
  if (bad.length) console.log(bad.map((s) => "  FAIL " + s).join("\n"));
  console.log(`\n${ok.length} ok, ${bad.length} failed`);
  process.exit(bad.length ? 1 : 0);
})();
