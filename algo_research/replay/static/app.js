// The blind replay page (market-narrative Requirements 10 and 11; updates 2026-10-14b and 2026-10-14c).
// Read the open, then play the day forward as if it were live, drawing as you go.
"use strict";

const { Prefs, CHART_DEFAULTS } = window.ReplayUI;
const $ = (id) => document.getElementById(id);
const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
const pad = (n) => String(n).padStart(2, "0");
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const WD = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const GROUPS = [["M1", "M2", "M3", "M4", "M5", "M10", "M15", "M20", "M30", "M45"],
                ["H1", "H3", "H4", "H6", "H7", "H8", "H12"], ["D1", "W1", "MN1"]];
const ALL_TFS = GROUPS.flat();
const SPEEDS = [
  { label: "1m per second", step: "M1", ms: 1000 }, { label: "1m per ½ s", step: "M1", ms: 500 },
  { label: "1m per ⅕ s", step: "M1", ms: 200 }, { label: "5m per ½ s", step: "M5", ms: 500 },
  { label: "15m per ½ s", step: "M15", ms: 500 }, { label: "1h per ½ s", step: "H1", ms: 500 },
];
const JUMPS = ["20:00", "00:00", "02:00", "03:00", "05:00", "07:00", "08:30", "09:30", "10:00", "11:00", "13:30", "16:00"];
// The tool strip, in TradingView's order: lines, shapes, fib, measures and positions, text.
const TOOLS = [
  { type: null, icon: "↖", title: "Cursor (Esc)" }, "-",
  { type: "trend", icon: "╱", title: "Trend line (Alt+T)", key: "t" },
  { type: "ray", icon: "↗", title: "Ray" },
  { type: "extended", icon: "⤢", title: "Extended line (Alt+E)", key: "e" },
  { type: "hline", icon: "―", title: "Horizontal line (Alt+H)", key: "h" },
  { type: "hray", icon: "⟶", title: "Horizontal ray: liquidity (Alt+J)", key: "j" },
  { type: "vline", icon: "│", title: "Vertical line (Alt+V)", key: "v" },
  { type: "arrow", icon: "➚", title: "Arrow (Alt+A)", key: "a" }, "-",
  { type: "rect", icon: "▭", title: "Box: a PD array, with its 50% line (Alt+R)", key: "r" },
  { type: "channel", icon: "▱", title: "Parallel channel: start, end, width (Alt+C)", key: "c" },
  { type: "path", icon: "✎", title: "Brush: drag to draw (Alt+B)", key: "b" }, "-",
  { type: "fib", icon: "≣", title: "Fib / SD projection: click the 1, then the 0 (Alt+F)", key: "f" },
  { type: "fibext", icon: "⋰", title: "Trend-based fib extension: A, B, then C (Alt+X)", key: "x" }, "-",
  { type: "range", icon: "⇕", title: "Date & price range (Alt+M; or Shift + drag to measure)", key: "m" },
  { type: "long", icon: "▲", title: "Long position: entry, stop, target (Alt+L)", key: "l" },
  { type: "short", icon: "▼", title: "Short position: entry, stop, target (Alt+S)", key: "s" }, "-",
  { type: "text", icon: "T", title: "Text (Alt+N)", key: "n" },
];
const KINDS = ["OB", "FVG", "BREAKER", "IFVG", "BPR", "LIQUIDITY", "OTHER"];
const S = { meta: null, state: null, tf: Prefs.get("tf", "M15"), tfSec: 900, bars: [], playing: false,
            speed: Prefs.get("speed", 1), pick: null, saveTimer: null, busy: false,
            chartPrefs: { ...CHART_DEFAULTS, ...Prefs.get("chart", {}) } };

// ── the chart ─────────────────────────────────────────────────────────────
const chart = LightweightCharts.createChart($("chart"), {
  autoSize: true,
  layout: { background: { color: "transparent" }, textColor: css("--muted"), fontSize: 12 },
  crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
  rightPriceScale: { borderColor: css("--line") },
  timeScale: { borderColor: css("--line"), timeVisible: true, secondsVisible: false, rightOffset: 12,
               shiftVisibleRangeOnNewBar: true, tickMarkFormatter: (t) => timeLabel(t, false) },
  localization: { timeFormatter: (t) => timeLabel(t, true) },
});
const series = chart.addCandlestickSeries({ borderVisible: false });
function palette() {
  return { ink: css("--ink"), muted: css("--muted"), accent: css("--accent"), up: css("--up"), down: css("--down"),
           bad: css("--bad"), panel: css("--panel"), background: css("--bg") };
}
function rgba(color, a) {
  const m = /^#([0-9a-f]{6})$/i.exec(color);
  if (!m) return color;
  const n = parseInt(m[1], 16);
  return `rgba(${n >> 16}, ${(n >> 8) & 255}, ${n & 255}, ${a})`;
}
function hexOf(color) {                                   // css colours can be rgb(): the colour inputs need #rrggbb
  const m = /rgba?\((\d+),\s*(\d+),\s*(\d+)/.exec(color);
  return m ? "#" + [m[1], m[2], m[3]].map((x) => Number(x).toString(16).padStart(2, "0")).join("") : color;
}

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

const templates = Prefs.get("templates", {});
const draw = new Drawings(chart, series, {
  container: $("chart"), timeline, palette, tf: () => S.tf,
  digits: () => (S.meta ? S.meta.digits : 2),
  template: (type) => templates[type],
  onChange: (items) => { scheduleSave(items); renderObjects(); },
  onSelect: (item) => { renderProps(item); renderObjects(); },
  onEdit: (item, start) => editDrawing(item, start),
  onContext: (item, x, y) => (item ? drawingMenu(item, x, y) : chartMenu(x, y)),
  picking: () => !!S.pick,
  onPick: (at) => finishPick(at),
  onError: (text) => say(text),
});
const uiCtx = {
  palette, kinds: KINDS, timeframes: ALL_TFS, tf: () => S.tf, digits: () => (S.meta ? S.meta.digits : 2),
  timeLabel: (t) => timeLabel(t, true), say: (t) => say(t),
  saveTemplate: (type, look) => { templates[type] = look; Prefs.set("templates", templates); draw.refresh(); },
};
function editDrawing(item, start) { window.ReplayUI.toolSettings(draw, item, uiCtx, start); }
const motion = new Motion(chart, series, {
  container: $("chart"), draw, prefs: Prefs, palette, bars: () => S.bars, tfSeconds: () => S.tfSec,
  now: () => (S.state ? S.state.revealed_until_epoch : null),
  onChange: () => { draw.refresh(); sessionsUpdate(); },
});

// ── sessions: day separators, the day and midnight opens, killzone shading ──
let sessionsUpdate = () => {};
series.attachPrimitive({
  attached(param) { sessionsUpdate = param.requestUpdate; }, detached() {}, updateAllViews() {},
  paneViews() {
    return [{ zOrder: () => "bottom", renderer: () => ({
      draw: (target) => target.useMediaCoordinateSpace(({ context, mediaSize }) => paintSessions(context, mediaSize)),
    }) }];
  },
});
const ZONES = [["kzAsia", 1200, 1440], ["kzLondon", 120, 300], ["kzNyAm", 420, 600], ["kzNyPm", 810, 960]];
function paintSessions(ctx, size) {
  const p = S.chartPrefs, b = S.bars;
  if (!b.length || S.tfSec >= 86400) return;
  const ts = chart.timeScale(), range = ts.getVisibleLogicalRange();
  if (!range) return;
  const from = Math.max(0, Math.floor(range.from) - 2), to = Math.min(b.length - 1, Math.ceil(range.to) + 2);
  const half = ts.options().barSpacing / 2;
  const x = (i) => ts.logicalToCoordinate(i);
  const minute = (t) => (((t % 86400) + 86400) % 86400) / 60;
  const dayOf = (t) => Math.floor((t - 61200) / 86400);              // trading days start 17:00 wall
  ctx.save();
  if (S.tfSec <= 3600 && ZONES.some(([k]) => p[k])) {
    let run = null;
    const flush = () => { if (run) { ctx.fillStyle = rgba(p[run.key + "Color"], p.kzOpacity); ctx.fillRect(x(run.i) - half, 0, x(run.j) - x(run.i) + 2 * half, size.height); } run = null; };
    for (let i = from; i <= to; i++) {
      const m = minute(b[i].time);
      const zone = ZONES.find(([k, a, z]) => p[k] && m >= a && m < z);
      const key = zone ? zone[0] : null;
      if (run && (key !== run.key || dayOf(b[i].time) !== run.day)) flush();
      if (key) { if (!run) run = { key, i, j: i, day: dayOf(b[i].time) }; else run.j = i; }
    }
    flush();
  }
  for (let i = from; i <= to; i++) {
    const day = dayOf(b[i].time);
    const first = i === 0 || dayOf(b[i - 1].time) !== day;
    if (!first) continue;
    let end = i;
    while (end + 1 < b.length && dayOf(b[end + 1].time) === day) end++;
    const xEnd = end === b.length - 1 ? size.width : x(end) + half;
    if (p.separators && i > 0) {
      ctx.strokeStyle = rgba(hexOf(css("--muted")), 0.45); ctx.setLineDash([3, 4]); ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(x(i) - half, 0); ctx.lineTo(x(i) - half, size.height); ctx.stroke(); ctx.setLineDash([]);
    }
    const level = (k, price, label, dash) => {
      const y = series.priceToCoordinate(price);
      if (y === null) return;
      ctx.strokeStyle = css("--muted"); ctx.setLineDash(dash); ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(x(k) - half, y); ctx.lineTo(xEnd, y); ctx.stroke(); ctx.setLineDash([]);
      ctx.fillStyle = css("--muted"); ctx.font = "11px system-ui, sans-serif"; ctx.textBaseline = "bottom";
      ctx.fillText(label, Math.max(x(k) - half, 0) + 3, y - 2);
    };
    if (p.dayOpen) level(i, b[i].open, "day open", [1, 3]);
    if (p.midnightOpen) {
      let k = i;
      while (k <= end && minute(b[k].time) >= 1020) k++;                // the first bar at or after 00:00
      if (k <= end) level(k, b[k].open, "00:00 open", [6, 3]);
    }
  }
  ctx.restore();
}

function applyChartPrefs(p) {
  S.chartPrefs = { ...CHART_DEFAULTS, ...p };
  p = S.chartPrefs;
  if (p.theme === "auto") delete document.documentElement.dataset.theme; else document.documentElement.dataset.theme = p.theme;
  const up = p.upColor || css("--up"), down = p.downColor || css("--down");
  series.applyOptions({ upColor: up, downColor: down, borderVisible: !!p.borders, borderUpColor: up, borderDownColor: down,
                        wickUpColor: p.wicksLikeBody ? up : p.upWick || up, wickDownColor: p.wicksLikeBody ? down : p.downWick || down });
  const modes = { normal: LightweightCharts.PriceScaleMode.Normal, log: LightweightCharts.PriceScaleMode.Logarithmic,
                  percent: LightweightCharts.PriceScaleMode.Percentage };
  chart.applyOptions({
    layout: { background: { color: p.background || "transparent" }, textColor: css("--muted") },
    grid: { vertLines: { visible: p.gridV, color: css("--grid") }, horzLines: { visible: p.gridH, color: css("--grid") } },
    crosshair: { mode: p.crosshair === "magnet" ? LightweightCharts.CrosshairMode.Magnet : LightweightCharts.CrosshairMode.Normal },
    rightPriceScale: { mode: modes[p.scaleMode] || modes.normal, autoScale: true, borderColor: css("--line") },   // a manual range: motion.js
    timeScale: { borderColor: css("--line") },
    watermark: { visible: !!p.watermark, text: `${S.meta ? S.meta.instrument : ""} · ${tfLabel(S.tf)}`, fontSize: 56,
                 color: rgba(hexOf(css("--muted")), 0.14), horzAlign: "center", vertAlign: "center" },
  });
  draw.refresh(); sessionsUpdate();
}
matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => applyChartPrefs(S.chartPrefs));

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
  if (!ALL_TFS.includes(S.tf)) S.tf = "M15";
  S.tfSec = S.meta.timeframes.find((x) => x.tf === S.tf).seconds;
  buildTfs(); buildTools(); buildFavBar(); buildReplay();
  applyChartPrefs(S.chartPrefs);
  await loadDay(await api("/api/state"));
}
async function loadDay(state) {
  S.state = state;
  draw.load(state.drawings);
  renderHeader(); renderPanel(); renderReplay(); renderProps(null); markLinked(); renderObjects();
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
  draw.refresh(); sessionsUpdate();
}

// ── timeframes: favourites in the bar, every one in the menu ──────────────
function tfLabel(tf) {
  if (tf === "MN1") return "M";
  if (tf === "W1") return "W";
  if (tf === "D1") return "D";
  return tf[0] === "M" ? tf.slice(1) + "m" : tf.slice(1) + "H";
}
const favTfs = () => Prefs.get("favTfs", ALL_TFS);
function buildTfs() {
  const box = $("tfs"), favs = favTfs();
  box.replaceChildren();
  let group = -1;
  for (const tf of ALL_TFS) {
    if (!favs.includes(tf) && tf !== S.tf) continue;
    const g = GROUPS.findIndex((gr) => gr.includes(tf));
    if (group >= 0 && g !== group) box.append(Object.assign(document.createElement("span"), { className: "sep" }));
    group = g;
    const b = document.createElement("button");
    b.textContent = tfLabel(tf); b.dataset.tf = tf; b.title = tf;
    b.classList.toggle("on", tf === S.tf);
    b.onclick = () => setTf(tf);
    box.append(b);
  }
  const more = document.createElement("button");
  more.textContent = "▾"; more.title = "All timeframes; star your favourites";
  more.onclick = (e) => tfMenu(e.currentTarget);
  box.append(more);
}
function tfMenu(anchor) {
  const { el } = window.ReplayUI;
  const favs = new Set(favTfs());
  const panel = el("div", { class: "menu tfmenu" });
  GROUPS.forEach((group, gi) => {
    if (gi) panel.append(el("div", { class: "menu-sep" }));
    for (const tf of group) {
      const star = el("button", { class: "star", title: favs.has(tf) ? "Remove from favourites" : "Add to favourites" }, favs.has(tf) ? "★" : "☆");
      star.onclick = (e) => {
        e.stopPropagation();
        if (favs.has(tf)) favs.delete(tf); else favs.add(tf);
        Prefs.set("favTfs", ALL_TFS.filter((x) => favs.has(x)));
        star.textContent = favs.has(tf) ? "★" : "☆";
        buildTfs();
      };
      panel.append(el("div", { class: "menu-row" + (tf === S.tf ? " on" : "") },
        el("button", { class: "grow", onclick: () => { close(); setTf(tf); } }, tf), star));
    }
  });
  document.body.append(panel);
  const r = anchor.getBoundingClientRect();
  panel.style.left = Math.min(r.left, window.innerWidth - panel.offsetWidth - 6) + "px";
  panel.style.top = r.bottom + 4 + "px";
  const outside = (e) => { if (!panel.contains(e.target) && e.target !== anchor) close(); };
  function close() { panel.remove(); window.removeEventListener("mousedown", outside, true); }
  setTimeout(() => window.addEventListener("mousedown", outside, true), 0);
}
function setTf(tf) {
  act(async () => {
    S.tf = tf; Prefs.set("tf", tf);
    S.tfSec = S.meta.timeframes.find((x) => x.tf === tf).seconds;
    buildTfs();
    applyChartPrefs(S.chartPrefs);
    await loadBars(true);
  });
}

// ── tools: the strip, favourites, toggles ─────────────────────────────────
const favTools = () => Prefs.get("favTools", ["rect", "hray", "fib", "long", "short"]);
function toolButton(tool) {
  const b = document.createElement("button");
  b.textContent = tool.icon; b.title = tool.title; b.dataset.type = tool.type || "";
  b.onclick = () => { S.pick = null; document.body.classList.remove("picking"); draw.use(tool.type); markTool(); };
  if (tool.type) {
    b.oncontextmenu = (e) => {
      e.preventDefault();
      const favs = favTools(), on = favs.includes(tool.type);
      window.ReplayUI.contextMenu(e.clientX, e.clientY, [{ label: on ? "Remove from favourites" : "Add to favourites", action: () => {
        Prefs.set("favTools", on ? favs.filter((x) => x !== tool.type) : [...favs, tool.type]); buildTools(); buildFavBar();
      } }]);
    };
  }
  return b;
}
function buildTools() {
  const nav = $("tools"), favs = favTools();
  nav.replaceChildren();
  for (const tool of TOOLS) {
    if (tool === "-") { nav.append(Object.assign(document.createElement("span"), { className: "sep" })); continue; }
    const b = toolButton(tool);
    if (tool.type && favs.includes(tool.type)) b.classList.add("fav");
    nav.append(b);
  }
  nav.append(Object.assign(document.createElement("span"), { className: "sep" }));
  const toggle = (icon, title, get, set) => {
    const b = document.createElement("button");
    b.textContent = icon; b.title = title;
    const mark = () => b.classList.toggle("on", get());
    b.onclick = () => { set(!get()); mark(); draw.refresh(); };
    mark(); nav.append(b);
  };
  toggle("🧲", "Magnet: snap to open, high, low, close", () => draw.magnet, (v) => { draw.magnet = v; });
  toggle("📌", "Stay in drawing mode", () => draw.keepTool, (v) => { draw.keepTool = v; });
  toggle("👁", "Hide all drawings", () => draw.hidden, (v) => { draw.hidden = v; });
  const action = (icon, title, fn) => { const b = document.createElement("button"); b.textContent = icon; b.title = title; b.onclick = fn; nav.append(b); };
  action("↶", "Undo (Ctrl+Z)", () => draw.undo());
  action("🗑", "Remove all drawings", () => { if (confirm("Remove every drawing on this day?")) draw.clearAll(); });
  markTool();
}
function markTool() {
  for (const b of document.querySelectorAll("#tools button[data-type], #favbar button[data-type]")) {
    b.classList.toggle("on", (b.dataset.type || null) === draw.tool);
  }
}
function buildFavBar() {
  const bar = $("favbar"), favs = favTools();
  bar.replaceChildren();
  bar.style.display = favs.length ? "" : "none";
  const grip = document.createElement("span");
  grip.className = "grip"; grip.textContent = "⋮⋮"; grip.title = "Drag to move";
  bar.append(grip);
  for (const type of favs) { const tool = TOOLS.find((t) => t.type === type); if (tool) bar.append(toolButton(tool)); }
  const pos = Prefs.get("favbarPos", null);
  if (pos) { bar.style.left = pos.left + "px"; bar.style.top = pos.top + "px"; }
  grip.onmousedown = (e) => {
    e.preventDefault();
    const host = $("chartWrap").getBoundingClientRect(), r = bar.getBoundingClientRect(), dx = e.clientX - r.left, dy = e.clientY - r.top;
    const move = (m) => { bar.style.left = Math.max(0, m.clientX - host.left - dx) + "px"; bar.style.top = Math.max(0, m.clientY - host.top - dy) + "px"; };
    const up = () => { window.removeEventListener("mousemove", move); window.removeEventListener("mouseup", up);
                       Prefs.set("favbarPos", { left: parseInt(bar.style.left, 10), top: parseInt(bar.style.top, 10) }); };
    window.addEventListener("mousemove", move); window.addEventListener("mouseup", up);
  };
  markTool();
}
new MutationObserver(markTool).observe($("chart"), { attributes: true, attributeFilter: ["style"] });

// ── context menus ─────────────────────────────────────────────────────────
function drawingMenu(d, x, y) {
  window.ReplayUI.contextMenu(x, y, [
    { label: "Settings…", key: "double-click", action: () => editDrawing(d) },
    { label: "Clone", action: () => draw.clone(d) },
    { label: d.locked ? "Unlock" : "Lock", action: () => draw.toggle(d, "locked") },
    { label: "Hide", action: () => draw.toggle(d, "hidden") },
    { label: "Bring to front", action: () => { draw.snapshot(); draw.items = [...draw.items.filter((q) => q !== d), d]; draw.changed(); } },
    { label: "Send to back", action: () => { draw.snapshot(); draw.items = [d, ...draw.items.filter((q) => q !== d)]; draw.changed(); } },
    "-",
    { label: "Delete", key: "Del", action: () => draw.remove(d) },
  ]);
}
function chartMenu(x, y) {
  window.ReplayUI.contextMenu(x, y, [
    { label: "Chart settings…", action: () => openChartSettings() },
    { label: "Reset the chart view", action: () => { const n = S.bars.length; motion.fit();
                                                     chart.timeScale().setVisibleLogicalRange({ from: Math.max(0, n - 150), to: n + 10 }); } },
    ...motion.menu(),
    { label: draw.hidden ? "Show drawings" : "Hide drawings", action: () => { draw.hidden = !draw.hidden; buildTools(); draw.refresh(); } },
    "-",
    { label: "Remove all drawings", disabled: !draw.items.length, action: () => { if (confirm("Remove every drawing on this day?")) draw.clearAll(); } },
  ]);
}
function openChartSettings() { window.ReplayUI.chartSettings({ palette, motion, apply: (p) => applyChartPrefs(p) }); }
$("chartSettings").onclick = () => openChartSettings();

// ── replay controls ───────────────────────────────────────────────────────
function buildReplay() {
  SPEEDS.forEach((s, i) => { const o = document.createElement("option"); o.value = i; o.textContent = s.label; $("speed").appendChild(o); });
  $("speed").value = S.speed;
  $("speed").onchange = () => { S.speed = Number($("speed").value); Prefs.set("speed", S.speed); };
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
    S.state && S.state.status === "REVEALED" ? "Day revealed." : "Inside a minute the path is simulated (open, extremes, close).";
}
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
  draw.refresh(); sessionsUpdate();
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
          <select id="atf">${[...ALL_TFS].reverse().map((t) => `<option ${t === "H4" ? "selected" : ""}>${t}</option>`).join("")}</select>
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
      await api("/api/drawings", { drawings: draw.items.map(({ status, ...d }) => d) });   // the read keeps the chart as it is now
      onState(await api("/api/read", body));
    });
  } else if (s.status === "INTRADAY") {
    p.innerHTML = readCard() + `
      <h2>Trades</h2>
      <div class="hint">Draw a long or short, then "Place trade" in its panel below. Or type one:</div>
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

// ── the selected drawing: quick settings; the rest in its dialog ──────────
function renderProps(d) {
  const box = $("props");
  if (!d) { box.innerHTML = ""; return; }
  let html = `<h2>${window.DRAWING_NAMES[d.type]}${d.locked ? " · locked" : ""}</h2>`;
  if (d.type === "rect") {
    html += `<div class="row"><label>Side</label><span class="seg" id="pdir"><button data-v="bullish">Bullish</button>
               <button data-v="bearish">Bearish</button><button data-v="neutral">Other</button></span></div>
             <div class="row"><label>Array</label><select id="pkind"><option value="">—</option>${KINDS.map((k) => `<option ${d.kind === k ? "selected" : ""}>${k}</option>`).join("")}</select>
               <select id="ptf"><option value="">TF</option>${ALL_TFS.map((x) => `<option ${d.tf === x ? "selected" : ""}>${x}</option>`).join("")}</select></div>`;
  }
  if (d.type === "long" || d.type === "short") {
    const placed = S.state.trades.some((t) => t.drawing === d.id);
    const [e, st, tg] = d.points.map((q) => q.p);
    html += `<div class="row"><label>Entry</label><span>${fmt(e)}</span></div>
             <div class="row"><label>Stop</label><span>${fmt(st)}</span></div>
             <div class="row"><label>Target</label><span>${fmt(tg)} · R:R ${(Math.abs(tg - e) / Math.abs(e - st)).toFixed(2)}</span></div>
             <div class="row">${placed ? '<span class="good">Placed as a trade</span>' :
               `<button class="primary" id="placeTrade" ${S.state.status === "INTRADAY" ? "" : "disabled"}>Place trade at ${S.state.revealed_until_ny}</button>`}</div>`;
  }
  html += `<div class="row"><button class="boxed" id="psettings">Settings… (double-click)</button>
             <button class="boxed" id="pclone">Clone</button><button class="boxed" id="plock">${d.locked ? "Unlock" : "Lock"}</button>
             <button class="boxed danger" id="pdel">Delete</button></div>`;
  box.innerHTML = html;
  if (d.type === "rect") {
    seg("pdir", (v) => { draw.update(d, { direction: v }); if (d.style) draw.setStyle(d, { color: "", fill: "" }); }, d.direction || "neutral");
    $("pkind").onchange = () => draw.update(d, { kind: $("pkind").value || undefined });
    $("ptf").onchange = () => draw.update(d, { tf: $("ptf").value || undefined });
  }
  $("psettings").onclick = () => editDrawing(d);
  $("pclone").onclick = () => draw.clone(d);
  $("plock").onclick = () => { draw.toggle(d, "locked"); renderProps(d); };
  $("pdel").onclick = () => draw.remove(d);
  if ($("placeTrade")) {
    $("placeTrade").onclick = () => act(async () => {
      const [entry, stop, target] = d.points.map((q) => q.p);
      onState(await api("/api/trade", { direction: d.type === "long" ? "LONG" : "SHORT", entry, stop, target, drawing: d.id }));
      renderProps(d);
    });
  }
}
function renderObjects() {
  $("objCount").textContent = draw.items.length ? `(${draw.items.length})` : "";
  window.ReplayUI.objectTree($("objects"), draw, { refresh: () => renderObjects() });
}

// ── keys ──────────────────────────────────────────────────────────────────
document.addEventListener("keydown", (e) => {
  const typing = /INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName);
  if (e.key === "Escape") { S.pick = null; document.body.classList.remove("picking"); draw.use(null); draw.select(null);
                            draw.measure = null; window.ReplayUI.closeMenu(); markTool(); draw.refresh(); return; }
  if (typing) return;
  if ((e.key === "Delete" || e.key === "Backspace") && draw.selected) { e.preventDefault(); draw.remove(draw.selected); return; }
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "z") { e.preventDefault(); draw.undo(); return; }
  if (e.altKey) {
    const tool = TOOLS.find((t) => t !== "-" && t.key === e.key.toLowerCase());
    if (tool) { e.preventDefault(); S.pick = null; draw.use(tool.type); markTool(); }
    return;
  }
  if (S.state && S.state.status === "INTRADAY") {
    if (e.key === " ") { e.preventDefault(); togglePlay(); }
    else if (e.key === "ArrowRight") { e.preventDefault(); act(async () => { stop(); await advance({ step: e.shiftKey ? "H1" : SPEEDS[S.speed].step }, 0); }); }
  }
});

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
