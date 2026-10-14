// The blind replay page (market-narrative Requirement 10; update 2026-10-14b).
// Read the open, then play the day forward as if it were live, drawing as you go.
"use strict";

const $ = (id) => document.getElementById(id);
const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
const pad = (n) => String(n).padStart(2, "0");
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const WD = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const GROUPS = [["M1", "M2", "M3", "M4", "M5", "M10", "M15", "M20", "M30", "M45"],
                ["H1", "H3", "H4", "H6", "H7", "H8", "H12"], ["D1", "W1", "MN1"]];
const SPEEDS = [
  { label: "1m per second", step: "M1", ms: 1000 }, { label: "1m per ½ s", step: "M1", ms: 500 },
  { label: "1m per ⅕ s", step: "M1", ms: 200 }, { label: "5m per ½ s", step: "M5", ms: 500 },
  { label: "15m per ½ s", step: "M15", ms: 500 }, { label: "1h per ½ s", step: "H1", ms: 500 },
];
const JUMPS = ["20:00", "00:00", "02:00", "03:00", "05:00", "07:00", "08:30", "09:30", "10:00", "11:00", "13:30", "16:00"];
const TOOLS = [
  { type: null, icon: "↖", title: "Cursor (Esc)" },
  { type: "hline", icon: "―", title: "Horizontal line (Alt+H)", key: "h" },
  { type: "hray", icon: "⟶", title: "Horizontal ray: liquidity (Alt+J)", key: "j" },
  { type: "trend", icon: "╱", title: "Trend line (Alt+T)", key: "t" },
  { type: "rect", icon: "▭", title: "Box: a PD array, with its 50% line (Alt+R)", key: "r" },
  { type: "fib", icon: "≣", title: "Fib / SD projection: click the 1, then the 0 (Alt+F)", key: "f" },
  { type: "long", icon: "▲", title: "Long position: entry, stop, target (Alt+L)", key: "l" },
  { type: "short", icon: "▼", title: "Short position: entry, stop, target (Alt+S)", key: "s" },
  { type: "vline", icon: "│", title: "Vertical line (Alt+V)", key: "v" },
  { type: "text", icon: "T", title: "Text (Alt+N)", key: "n" },
];
const KINDS = ["OB", "FVG", "BREAKER", "IFVG", "BPR", "LIQUIDITY", "OTHER"];
const S = { meta: null, state: null, tf: "M15", tfSec: 900, bars: [], playing: false, speed: 1, pick: null,
            saveTimer: null, busy: false };

// ── the chart ─────────────────────────────────────────────────────────────
const chart = LightweightCharts.createChart($("chart"), {
  autoSize: true,
  layout: { background: { color: "transparent" }, textColor: css("--muted"), fontSize: 12 },
  grid: { vertLines: { color: css("--grid") }, horzLines: { color: css("--grid") } },
  crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
  rightPriceScale: { borderColor: css("--line") },
  timeScale: { borderColor: css("--line"), timeVisible: true, secondsVisible: false, rightOffset: 12,
               shiftVisibleRangeOnNewBar: true, tickMarkFormatter: (t) => timeLabel(t, false) },
  localization: { timeFormatter: (t) => timeLabel(t, true) },
});
const series = chart.addCandlestickSeries({ borderVisible: false });
function palette() {
  return { ink: css("--ink"), muted: css("--muted"), accent: css("--accent"), up: css("--up"), bad: css("--bad"),
           panel: css("--panel") };
}
function paint() {
  const up = css("--up"), down = css("--down");
  series.applyOptions({ upColor: up, downColor: down, wickUpColor: up, wickDownColor: down });
  chart.applyOptions({ layout: { textColor: css("--muted") },
                       grid: { vertLines: { color: css("--grid") }, horzLines: { color: css("--grid") } } });
  draw.refresh();
}
matchMedia("(prefers-color-scheme: dark)").addEventListener("change", paint);

// Bar times are New York wall-clock seconds. Until the reveal, the axis shows weekday and time only.
function timeLabel(t, long) {
  const d = new Date(t * 1000);
  const daily = S.tfSec >= 86400;
  if (S.state && S.state.date) {
    const ymd = d.toISOString().slice(0, 10);
    return daily ? ymd : (long ? ymd + " " : "") + WD[d.getUTCDay()] + " " + pad(d.getUTCHours()) + ":" + pad(d.getUTCMinutes());
  }
  if (S.tfSec > 86400) return long ? "—" : "";
  if (daily) return WD[new Date((t + 7 * 3600) * 1000).getUTCDay()];   // a D1 candle opens 17:00 on its eve
  return WD[d.getUTCDay()] + " " + pad(d.getUTCHours()) + ":" + pad(d.getUTCMinutes());
}

// Logical positions for any time, so drawings sit right on every timeframe.
const timeline = {
  index(t) {
    const b = S.bars;
    let lo = 0, hi = b.length - 1, ans = -1;
    while (lo <= hi) { const mid = (lo + hi) >> 1; if (b[mid].time <= t) { ans = mid; lo = mid + 1; } else hi = mid - 1; }
    return ans;
  },
  toLogical(t) {
    const b = S.bars;
    if (!b.length) return 0;
    const i = this.index(t);
    if (i < 0) return (t - b[0].time) / S.tfSec;
    const frac = (t - b[i].time) / S.tfSec;
    return i + (i === b.length - 1 ? frac : Math.min(frac, 0.999));
  },
  toTime(l) {
    const b = S.bars;
    if (!b.length) return 0;
    const i = Math.floor(l);
    if (i < 0) return b[0].time + Math.round(l * S.tfSec);
    if (i >= b.length) return b[b.length - 1].time + Math.round((l - (b.length - 1)) * S.tfSec);
    return b[i].time + Math.round((l - i) * S.tfSec);
  },
  barAt(l) { const b = S.bars; return b.length ? b[Math.max(0, Math.min(b.length - 1, Math.round(l)))] : null; },
};

const draw = new Drawings(chart, series, {
  container: $("chart"), timeline, palette,
  digits: () => (S.meta ? S.meta.digits : 2),
  onChange: (items) => scheduleSave(items),
  onSelect: (item) => renderProps(item),
  picking: () => !!S.pick,
  onPick: (at) => finishPick(at),
  onError: (text) => say(text),
});
paint();

// ── API ───────────────────────────────────────────────────────────────────
async function api(path, body) {
  const init = body === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json" },
                                          body: JSON.stringify(body) };
  const r = await fetch(path, init);
  const j = await r.json();
  if (!r.ok) throw new Error(j.error || r.statusText);
  return j;
}
function say(text) { $("msg").textContent = text || ""; }
async function act(fn) { say(""); try { await fn(); } catch (e) { say(e.message); } }

function scheduleSave(items) {
  clearTimeout(S.saveTimer);
  S.saveTimer = setTimeout(() => act(async () => onState(await api("/api/drawings", { drawings: items }))), 400);
}

// ── loading a day ─────────────────────────────────────────────────────────
async function boot() {
  S.meta = await api("/api/meta");
  buildTfs(); buildTools(); buildReplay();
  await loadDay(await api("/api/state"));
}
let openLine = null;
function markOpen() {                             // the day's open, a reference on every timeframe
  if (openLine) series.removePriceLine(openLine);
  openLine = series.createPriceLine({ price: S.state.open_price, color: css("--muted"), lineWidth: 1,
                                      lineStyle: LightweightCharts.LineStyle.Dotted, axisLabelVisible: false, title: "day open" });
}
async function loadDay(state) {
  S.state = state;
  markOpen();
  draw.load(state.drawings);
  renderHeader(); renderPanel(); renderReplay(); renderProps(null); markLinked();
  await loadBars(true);
  renderSummary();
}
function onState(state) {
  const fresh = !S.state || state.status !== S.state.status || state.open_epoch !== S.state.open_epoch;
  S.state = state;
  renderHeader();
  if (fresh) { renderPanel(); renderReplay(); } else renderLive();
  markLinked();
}

async function loadBars(fit) {
  const range = chart.timeScale().getVisibleLogicalRange();
  const data = await api("/api/bars?tf=" + S.tf);
  S.bars = data.bars;
  series.applyOptions({ priceFormat: { type: "price", precision: S.meta.digits, minMove: Math.pow(10, -S.meta.digits) } });
  series.setData(S.bars);
  const n = S.bars.length;
  if (fit || !range) chart.timeScale().setVisibleLogicalRange({ from: Math.max(0, n - 150), to: n + 10 });
  draw.refresh();
}

// ── timeframes, tools, replay controls ────────────────────────────────────
function tfLabel(tf) {
  if (tf === "MN1") return "M";
  if (tf === "W1") return "W";
  if (tf === "D1") return "D";
  return tf[0] === "M" ? tf.slice(1) + "m" : tf.slice(1) + "H";
}
function buildTfs() {
  const box = $("tfs");
  GROUPS.forEach((group, gi) => {
    if (gi) { const s = document.createElement("span"); s.className = "sep"; box.appendChild(s); }
    for (const tf of group) {
      const b = document.createElement("button");
      b.textContent = tfLabel(tf); b.dataset.tf = tf; b.title = tf;
      b.onclick = () => setTf(tf);
      box.appendChild(b);
    }
  });
  markTf();
}
function markTf() { for (const b of $("tfs").querySelectorAll("button")) b.classList.toggle("on", b.dataset.tf === S.tf); }
function setTf(tf) {
  act(async () => {
    S.tf = tf;
    S.tfSec = S.meta.timeframes.find((x) => x.tf === tf).seconds;
    markTf();
    await loadBars(true);
  });
}
function buildTools() {
  const nav = $("tools");
  TOOLS.forEach((tool, i) => {
    const b = document.createElement("button");
    b.textContent = tool.icon; b.title = tool.title; b.dataset.type = tool.type || "";
    b.onclick = () => { S.pick = null; draw.use(tool.type); markTool(); };
    nav.appendChild(b);
    if (i === 0) { const s = document.createElement("span"); s.className = "sep"; nav.appendChild(s); }
  });
  const sep = document.createElement("span"); sep.className = "sep"; nav.appendChild(sep);
  const toggle = (icon, title, get, set) => {
    const b = document.createElement("button");
    b.textContent = icon; b.title = title;
    const mark = () => b.classList.toggle("on", get());
    b.onclick = () => { set(!get()); mark(); draw.refresh(); };
    mark(); nav.appendChild(b);
  };
  toggle("🧲", "Magnet: snap to open, high, low, close", () => draw.magnet, (v) => { draw.magnet = v; });
  toggle("👁", "Hide drawings", () => draw.hidden, (v) => { draw.hidden = v; });
  const undo = document.createElement("button");
  undo.textContent = "↶"; undo.title = "Undo (Ctrl+Z)"; undo.onclick = () => draw.undo(); nav.appendChild(undo);
  const clear = document.createElement("button");
  clear.textContent = "🗑"; clear.title = "Remove all drawings";
  clear.onclick = () => { if (confirm("Remove every drawing on this day?")) draw.clearAll(); };
  nav.appendChild(clear);
  markTool();
}
function markTool() {
  for (const b of $("tools").querySelectorAll("button[data-type]")) b.classList.toggle("on", (b.dataset.type || null) === draw.tool);
}
function buildReplay() {
  SPEEDS.forEach((s, i) => { const o = document.createElement("option"); o.value = i; o.textContent = s.label; $("speed").appendChild(o); });
  $("speed").value = S.speed;
  $("speed").onchange = () => { S.speed = Number($("speed").value); };
  JUMPS.forEach((t) => { const o = document.createElement("option"); o.value = t; o.textContent = t + " NY"; $("jump").appendChild(o); });
  $("jump").onchange = () => {
    const to = $("jump").value; $("jump").value = "";
    if (to) act(async () => { stop(); await advance({ to }, 0); });
  };
  $("play").onclick = () => togglePlay();
  $("stepBtn").onclick = () => act(async () => { stop(); await advance({ step: SPEEDS[S.speed].step }, 0); });
  $("reveal").onclick = () => act(async () => {
    if (!confirm("End the day and reveal it? Nothing can be added to the read or the trades afterwards.")) return;
    stop();
    onState(await api("/api/reveal", {}));
    await loadBars(false);
    renderSummary();
  });
}
function renderReplay() {
  const live = S.state && S.state.status === "INTRADAY";
  for (const id of ["play", "speed", "stepBtn", "jump", "reveal"]) $(id).disabled = !live;
  $("play").textContent = S.playing ? "⏸ Pause" : "▶ Play";
  $("replayHint").textContent = S.state && S.state.status === "READING" ? "Save your read to start the day." :
    S.state && S.state.status === "REVEALED" ? "Day revealed." : "Candles inside a minute are simulated (open, high/low, close).";
}

// ── playing the day ───────────────────────────────────────────────────────
function stop() { S.playing = false; renderReplay(); }
function togglePlay() {
  if (S.playing) { stop(); return; }
  S.playing = true; renderReplay();
  (async () => {
    while (S.playing && S.state.status === "INTRADAY") {
      const sp = SPEEDS[S.speed];
      const t0 = performance.now();
      try { await advance({ step: sp.step }, sp.ms); } catch (e) { say(e.message); break; }
      const wait = sp.ms - (performance.now() - t0);
      if (wait > 0) await sleep(wait);
    }
    stop();
  })();
}
async function advance(move, ms) {
  if (S.busy) return;
  S.busy = true;
  try {
    const last = S.bars[S.bars.length - 1];
    const res = await api("/api/advance", { ...move, tf: S.tf, since: last ? last.time : null });
    await applyUpdate(res.update, ms);
    onState(res);
  } finally { S.busy = false; }
}
function put(bar) {
  const n = S.bars.length, last = S.bars[n - 1];
  if (last && last.time === bar.time) S.bars[n - 1] = bar;
  else if (!last || bar.time > last.time) S.bars.push(bar);
  else return;
  series.update(bar);
}
async function applyUpdate(u, ms) {
  if (!u || u.tf !== S.tf) { await loadBars(false); return; }
  if (!u.bars.length) return;
  try {
    const head = u.bars.slice(0, -1), target = u.bars[u.bars.length - 1];
    for (const b of head) put(b);
    if (ms >= 150 && u.m1.length === 1) {         // let the minute print: open, then its extremes, then the close
      const m = u.m1[0];
      const path = m.close >= m.open ? [m.open, m.low, m.high] : [m.open, m.high, m.low];
      const last = S.bars[S.bars.length - 1];
      let cur = last && last.time === target.time ? { ...last }
        : { time: target.time, open: m.open, high: m.open, low: m.open, close: m.open };
      for (const p of path) {
        cur = { ...cur, high: Math.max(cur.high, p), low: Math.min(cur.low, p), close: p };
        series.update(cur);
        draw.refresh();
        await sleep(ms / 5);
      }
    }
    put(target);
  } catch (e) {                                   // the chart got out of step: redraw it from the server
    await loadBars(false);
  }
  draw.refresh();
}

// ── header and panels ─────────────────────────────────────────────────────
const fmt = (x) => (x == null ? "—" : Number(x).toFixed(S.meta ? S.meta.digits : 2));
function renderHeader() {
  const s = S.state;
  $("inst").textContent = s.instrument;
  $("status").textContent = { READING: "Reading the open", INTRADAY: "Live", REVEALED: "Revealed" }[s.status];
  $("status").className = "pill " + s.status;
  $("when").textContent = s.revealed_until_ny + " New York";
  $("price").textContent = fmt(s.price);
  $("dateLabel").textContent = s.date || "";
  $("left").textContent = s.remaining + " days left";
  $("showDate").style.display = s.date ? "none" : "";
}
$("showDate").onclick = () => act(async () => {
  if (!confirm("Show this day's date? Seeing it may bring back memories, so the day records that you looked.")) return;
  onState(await api("/api/show-date", {}));
  chart.applyOptions({});
});

function pickable(id, placeholder) {
  return `<input type="number" step="any" id="${id}" placeholder="${placeholder || ""}">` +
         `<button class="pick boxed" data-pick="${id}" title="Pick from the chart">◎</button>`;
}
function wirePicks(root) {
  for (const b of root.querySelectorAll("[data-pick]")) {
    b.onclick = () => { S.pick = b.dataset.pick; draw.use(null); markTool(); document.body.classList.add("picking");
                        say("Click the chart to pick the price."); };
  }
}
function finishPick(at) {
  const el = $(S.pick);
  S.pick = null;
  document.body.classList.remove("picking");
  say("");
  if (el) { el.value = at.p.toFixed(S.meta.digits); el.dispatchEvent(new Event("input", { bubbles: true })); }
}
function num(id) { const el = $(id); if (!el || el.value === "") return null; const v = Number(el.value); return isFinite(v) ? v : null; }
function escape(t) { return String(t).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])); }
function seg(id, onPick, current) {
  const box = $(id);
  for (const b of box.children) {
    b.classList.toggle("on", b.dataset.v === current);
    b.onclick = () => { for (const o of box.children) o.classList.toggle("on", o === b); onPick(b.dataset.v); };
  }
}

function renderPanel() {
  const s = S.state, p = $("panel");
  if (s.status === "READING") {
    p.innerHTML = `
      <h2>Your read at the open</h2>
      <div class="hint">${s.weekday}'s candle opens now at ${fmt(s.open_price)}. Mark the chart with the tools on the left:
        they are saved with the read. Then write the thesis.</div>
      <div class="row"><label>Bias</label><span class="seg" id="bias">
        <button data-v="BULLISH">Bullish</button><button data-v="BEARISH">Bearish</button><button data-v="NO_THESIS">No thesis</button></span></div>
      <div id="levels">
        <div class="row"><label>Draw</label>${pickable("draw", "target")}</div>
        <div class="row"><label>Invalidation</label>${pickable("inv", "wrong past")}</div>
        <div class="row"><label>Key array</label>
          <select id="akind"><option value="">none</option>${KINDS.map((k) => `<option>${k}</option>`).join("")}</select>
          <select id="atf">${["MN1", "W1", "D1", "H12", "H8", "H7", "H6", "H4", "H3", "H1", "M45", "M30", "M20", "M15", "M10", "M5", "M4", "M3", "M2", "M1"]
            .map((t) => `<option ${t === "H4" ? "selected" : ""}>${t}</option>`).join("")}</select>
          <button class="boxed" id="fromBox" title="Use the selected box">from box</button></div>
        <div class="row"><label></label>${pickable("alow", "low")}</div>
        <div class="row"><label></label>${pickable("ahigh", "high")}</div>
      </div>
      <div class="row"><label>Confidence</label><span class="seg" id="conf">
        <button data-v="1">1</button><button data-v="2">2</button><button data-v="3">3</button></span></div>
      <div class="row"><label></label><label><input type="checkbox" id="remembered"> I remember this period</label></div>
      <textarea id="note" placeholder="The story: the phase, the array that matters, the sentiment, the draw and why"></textarea>
      <div class="row"><button class="primary" id="saveRead">Save read — it locks, the day starts</button></div>`;
    let bias = null, conf = 2;
    seg("bias", (v) => { bias = v; $("levels").style.opacity = v === "NO_THESIS" ? 0.4 : 1; }, null);
    seg("conf", (v) => { conf = Number(v); }, "2");
    wirePicks(p);
    $("fromBox").onclick = () => {
      const d = draw.selected;
      if (!d || d.type !== "rect") { say("Select a box on the chart first."); return; }
      const [a, b] = d.points.map((q) => q.p);
      $("alow").value = Math.min(a, b).toFixed(S.meta.digits); $("ahigh").value = Math.max(a, b).toFixed(S.meta.digits);
      if (d.kind) $("akind").value = d.kind;
      if (d.tf) $("atf").value = d.tf;
    };
    $("saveRead").onclick = () => act(async () => {
      if (!bias) throw new Error("bias: choose bullish, bearish or no thesis");
      const body = { bias, confidence: conf, remembered: $("remembered").checked, note: $("note").value,
                     draw: num("draw"), invalidation: num("inv") };
      if ($("akind").value) Object.assign(body, { array_kind: $("akind").value, array_tf: $("atf").value,
                                                 array_low: num("alow"), array_high: num("ahigh") });
      clearTimeout(S.saveTimer);
      await api("/api/drawings", { drawings: draw.items });   // the read keeps the chart as it is now
      onState(await api("/api/read", body));
    });
  } else if (s.status === "INTRADAY") {
    p.innerHTML = readCard() + `
      <h2>Trades</h2>
      <div class="hint">Place a long or short with the position tools, then "Place trade" in its settings. Or type one:</div>
      <div class="row"><span class="seg" id="dir"><button data-v="LONG">Long</button><button data-v="SHORT">Short</button></span></div>
      <div class="row"><label>Entry</label>${pickable("entry")}</div>
      <div class="row"><label>Stop</label>${pickable("stop")}</div>
      <div class="row"><label>Target</label>${pickable("target")}</div>
      <div class="row"><button class="boxed" id="mark">Place trade</button></div>
      <div id="trades"></div>`;
    let dir = "LONG";
    seg("dir", (v) => { dir = v; }, "LONG");
    wirePicks(p);
    $("mark").onclick = () => act(async () => {
      onState(await api("/api/trade", { direction: dir, entry: num("entry"), stop: num("stop"), target: num("target") }));
    });
    renderLive();
  } else {
    const sc = s.scores, n = s.narrative || {}, t = sc.thesis;
    const cls = { DRAW: "good", INVALIDATED: "bad", NEITHER: "neutral", NO_THESIS: "muted" }[t.outcome];
    p.innerHTML = `<h2>${s.weekday} ${s.date}</h2>` + readCard() + `
      <div class="card">Thesis: <span class="${cls}">${t.outcome.replace("_", " ")}</span>
        ${t.p_coin != null ? `<div class="muted">A coin flip reaches the draw first ${(t.p_coin * 100).toFixed(0)}% of the time from these distances.</div>` : ""}
        ${t.direction_right != null ? `<div>Direction: ${t.direction_right ? '<span class="good">right</span>' : '<span class="bad">wrong</span>'}</div>` : ""}</div>
      <div class="card"><table>
        <tr><td>Day</td><td>${n.direction || "—"}</td></tr>
        <tr><td>Open / close</td><td>${fmt(n.open)} / ${fmt(n.close)}</td></tr>
        <tr><td>High</td><td>${fmt(n.high)} at ${nyTime(n.t_high)}</td></tr>
        <tr><td>Low</td><td>${fmt(n.low)} at ${nyTime(n.t_low)}</td></tr>
        <tr><td>False move</td><td>${n.false_move != null ? fmt(n.false_move) : "—"}</td></tr></table></div>
      ${s.trades.map((tr, i) => tradeCard(tr, sc.trades[i])).join("")}
      <h2>Your narrative</h2>
      <div class="hint">How the day formed, in your words. Drawings you add now are kept as the narrative, apart from the read.</div>
      <textarea id="story" placeholder="Where it manipulated, what it delivered to, and what you'd do differently">${escape(s.narrative_note || "")}</textarea>
      <div class="row"><button class="boxed" id="saveStory">Save narrative</button>
        <span class="spacer"></span><button class="primary" id="next">Next day ▸</button></div>`;
    $("saveStory").onclick = () => act(async () => { onState(await api("/api/narrative", { text: $("story").value })); say("Saved."); });
    $("next").onclick = () => act(async () => { stop(); await loadDay(await api("/api/next", {})); });
  }
}
function renderLive() {
  const box = $("trades");
  if (box) box.innerHTML = S.state.trades.map((tr) => tradeCard(tr, tr.live)).join("");
}
function readCard() {
  const r = S.state.read;
  if (!r) return "";
  const lv = r.bias === "NO_THESIS" ? "" : `<div>Draw ${fmt(r.draw)} · invalidation ${fmt(r.invalidation)}</div>` +
    (r.array_low != null ? `<div>Key array: ${r.array_tf} ${r.array_kind} ${fmt(r.array_low)}–${fmt(r.array_high)}</div>` : "");
  return `<h2>Your read (locked)</h2><div class="card"><b>${r.bias.replace("_", " ")}</b>, confidence ${r.confidence}${r.remembered ? ", remembered" : ""}
    ${lv}${r.note ? `<div class="muted">${escape(r.note)}</div>` : ""}</div>`;
}
function tradeCard(t, score) {
  const rr = Math.abs(t.target - t.entry) / Math.abs(t.entry - t.stop);
  let res = "";
  if (score) {
    const r = score.r != null ? ` ${score.r >= 0 ? "+" : ""}${score.r.toFixed(2)}R` : "";
    const cls = score.outcome === "TARGET" || (score.r || 0) > 0 ? "good" : score.outcome === "STOP" || (score.r || 0) < 0 ? "bad" : "neutral";
    res = ` → <span class="${cls}">${score.outcome}${r}</span>`;
  }
  return `<div class="card">${t.direction} at ${t.marked_ny}: ${fmt(t.entry)}, stop ${fmt(t.stop)}, target ${fmt(t.target)} (R:R ${rr.toFixed(1)})${res}</div>`;
}
function nyTime(iso) {
  if (!iso) return "—";
  return new Date(iso).toLocaleTimeString("en-US", { timeZone: "America/New_York", hour: "2-digit", minute: "2-digit", hour12: false });
}

// A position drawing shows the trade placed from it, live.
function markLinked() {
  const byDrawing = {};
  for (const t of S.state.trades) if (t.drawing) byDrawing[t.drawing] = t;
  for (const d of draw.items) {
    const t = byDrawing[d.id];
    if (!t) { delete d.status; continue; }
    const live = t.live || (S.state.scores ? S.state.scores.trades[S.state.trades.indexOf(t)] : null);
    d.status = live ? live.outcome + (live.r != null ? ` ${live.r >= 0 ? "+" : ""}${live.r.toFixed(2)}R` : "") : "placed";
  }
  draw.refresh();
}

// ── the selected drawing's settings ───────────────────────────────────────
function renderProps(d) {
  const box = $("props");
  if (!d) { box.innerHTML = ""; return; }
  const name = { hline: "Horizontal line", hray: "Horizontal ray", vline: "Vertical line", trend: "Trend line", rect: "Box",
                 fib: "Fib / SD", long: "Long position", short: "Short position", text: "Text" }[d.type];
  let html = `<h2>${name}</h2>`;
  if (d.type === "rect") {
    html += `<div class="row"><label>Side</label><span class="seg" id="pdir"><button data-v="bullish">Bullish</button>
               <button data-v="bearish">Bearish</button><button data-v="neutral">Other</button></span></div>
             <div class="row"><label>Array</label><select id="pkind"><option value="">—</option>${KINDS.map((k) => `<option ${d.kind === k ? "selected" : ""}>${k}</option>`).join("")}</select>
               <select id="ptf"><option value="">TF</option>${S.meta.timeframes.map((x) => `<option ${d.tf === x.tf ? "selected" : ""}>${x.tf}</option>`).join("")}</select></div>
             <div class="row"><label>High</label><input type="number" step="any" id="pp0"></div>
             <div class="row"><label>Low</label><input type="number" step="any" id="pp1"></div>
             <div class="row"><label></label><label><input type="checkbox" id="pmid"> 50% line (CE / MT)</label>
               <label><input type="checkbox" id="pext"> extend right</label></div>`;
  }
  if (d.type === "hline" || d.type === "hray") html += `<div class="row"><label>Price</label><input type="number" step="any" id="pp0"></div>`;
  if (d.type === "fib") {
    html += `<div class="row"><label>Levels</label><input type="text" id="plevels" style="width:100%"></div>
             <div class="row"><label></label><label><input type="checkbox" id="pext"> extend right</label></div>`;
  }
  if (d.type === "long" || d.type === "short") {
    const placed = S.state.trades.some((t) => t.drawing === d.id);
    html += `<div class="row"><label>Entry</label><input type="number" step="any" id="pp0"></div>
             <div class="row"><label>Stop</label><input type="number" step="any" id="pp1"></div>
             <div class="row"><label>Target</label><input type="number" step="any" id="pp2"></div>
             <div class="row"><label></label><label><input type="checkbox" id="pext"> extend right</label></div>
             <div class="row">${placed ? '<span class="good">Placed as a trade</span>' :
               `<button class="primary" id="placeTrade" ${S.state.status === "INTRADAY" ? "" : "disabled"}>Place trade at ${S.state.revealed_until_ny}</button>`}</div>`;
  }
  if (d.type === "text") html += `<div class="row"><label>Text</label><input type="text" id="ptext" style="width:100%"></div>`;
  if (d.type !== "text") html += `<div class="row"><label>Label</label><input type="text" id="plabel" placeholder="e.g. PDH, NWOG, Asia low"></div>`;
  html += `<div class="row"><label>Colour</label><input type="color" id="pcolor"></div>
           <div class="row"><button class="boxed danger" id="pdel">Delete (Del)</button></div>`;
  box.innerHTML = html;

  const set = (change) => { draw.update(d, change); };
  const pointInput = (id, i) => {
    const el = $(id); if (!el) return;
    el.value = d.points[i].p.toFixed(S.meta.digits);
    el.onchange = () => { const v = Number(el.value); if (isFinite(v)) { const pts = d.points.map((q) => ({ ...q })); pts[i].p = v; set({ points: pts }); } };
  };
  if (d.type === "rect") {
    const hiIdx = d.points[0].p >= d.points[1].p ? 0 : 1;
    pointInput("pp0", hiIdx); pointInput("pp1", 1 - hiIdx);
    seg("pdir", (v) => set({ direction: v, color: undefined }), d.direction || "neutral");
    $("pkind").onchange = () => set({ kind: $("pkind").value || undefined });
    $("ptf").onchange = () => set({ tf: $("ptf").value || undefined });
    $("pmid").checked = !!d.mid; $("pmid").onchange = () => set({ mid: $("pmid").checked });
  } else {
    pointInput("pp0", 0); pointInput("pp1", 1); pointInput("pp2", 2);
  }
  if ($("pext")) { $("pext").checked = !!d.extend; $("pext").onchange = () => set({ extend: $("pext").checked }); }
  if ($("plevels")) {
    $("plevels").value = (d.levels || FIB_LEVELS).join(", ");
    $("plevels").onchange = () => {
      const levels = $("plevels").value.split(",").map((x) => Number(x.trim())).filter((x) => isFinite(x));
      if (levels.length) set({ levels });
    };
  }
  if ($("ptext")) { $("ptext").value = d.text || ""; $("ptext").onchange = () => set({ text: $("ptext").value }); }
  if ($("plabel")) { $("plabel").value = d.label || ""; $("plabel").onchange = () => set({ label: $("plabel").value || undefined }); }
  const pal = palette();
  $("pcolor").value = /^#[0-9a-f]{6}$/i.test(d.color || "") ? d.color : "#2563eb";
  $("pcolor").onchange = () => set({ color: $("pcolor").value });
  $("pdel").onclick = () => draw.remove(d);
  if ($("placeTrade")) {
    $("placeTrade").onclick = () => act(async () => {
      const [entry, stop, target] = d.points.map((q) => q.p);
      onState(await api("/api/trade", { direction: d.type === "long" ? "LONG" : "SHORT", entry, stop, target, drawing: d.id }));
      renderProps(d);
    });
  }
  void pal;
}

// ── keys ──────────────────────────────────────────────────────────────────
document.addEventListener("keydown", (e) => {
  const typing = /INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName);
  if (e.key === "Escape") { S.pick = null; document.body.classList.remove("picking"); draw.use(null); draw.select(null); markTool(); return; }
  if (typing) return;
  if ((e.key === "Delete" || e.key === "Backspace") && draw.selected) { e.preventDefault(); draw.remove(draw.selected); return; }
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "z") { e.preventDefault(); draw.undo(); return; }
  if (e.altKey) {
    const tool = TOOLS.find((t) => t.key === e.key.toLowerCase());
    if (tool) { e.preventDefault(); S.pick = null; draw.use(tool.type); markTool(); }
    return;
  }
  if (S.state && S.state.status === "INTRADAY") {
    if (e.key === " ") { e.preventDefault(); togglePlay(); }
    else if (e.key === "ArrowRight") { e.preventDefault(); act(async () => { stop(); await advance({ step: e.shiftKey ? "H1" : SPEEDS[S.speed].step }, 0); }); }
  }
});
new MutationObserver(markTool).observe($("chart"), { attributes: true, attributeFilter: ["style"] });

// ── summary ───────────────────────────────────────────────────────────────
async function renderSummary() {
  const m = await api("/api/summary");
  if (!m.revealed) { $("summary").textContent = "No revealed days yet."; return; }
  const pct = (x) => (x == null ? "—" : (x * 100).toFixed(0) + "%");
  $("summary").innerHTML = `<table>
    <tr><td>Days revealed</td><td>${m.revealed} (${m.thesis_days} with a thesis)</td></tr>
    <tr><td>Draw reached first</td><td>${pct(m.draw_rate)} ${m.draw_interval ? `[${pct(m.draw_interval[0])}, ${pct(m.draw_interval[1])}]` : ""}</td></tr>
    <tr><td>Coin flip from your levels</td><td>${pct(m.mean_p_coin)}</td></tr>
    <tr><td>Direction right</td><td>${pct(m.direction_accuracy)}</td></tr>
    <tr><td>Trades (not filled)</td><td>${m.trades} (${m.not_filled})</td></tr>
    <tr><td>Mean R / total R</td><td>${m.mean_r == null ? "—" : m.mean_r.toFixed(2)} / ${m.total_r.toFixed(1)}</td></tr></table>
    <div class="hint">Your edge shows when "draw reached first" beats the coin flip from your levels, over many days.</div>`;
}

boot().catch((e) => { $("panel").innerHTML = `<div class="card">${escape(e.message)}</div>`; });
