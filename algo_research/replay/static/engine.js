// Engine watch (algo-backtester update 2026-10-14d): play a backtested window and see, at every 15-minute
// close, what the engine saw and what it did. Times are New York wall seconds; nothing here is blind.
"use strict";

const { Prefs } = window.ReplayUI;
const $ = (id) => document.getElementById(id);
const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
const pad = (n) => String(n).padStart(2, "0");
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const WD = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const GROUPS = [["M1", "M2", "M3", "M4", "M5", "M10", "M15", "M20", "M30", "M45"], ["H1", "H3", "H4", "H6", "H7", "H8", "H12"], ["D1", "W1"]];
const SECONDS = { M1: 60, M2: 120, M3: 180, M4: 240, M5: 300, M10: 600, M15: 900, M20: 1200, M30: 1800, M45: 2700, H1: 3600,
                  H3: 10800, H4: 14400, H6: 21600, H7: 25200, H8: 28800, H12: 43200, D1: 86400, W1: 604800 };
const SPEEDS = [{ label: "1m per 0.1 s", step: 60, ms: 100 }, { label: "1m per 0.25 s", step: 60, ms: 250 },
                { label: "5m per 0.25 s", step: 300, ms: 250 }, { label: "15m per 0.5 s", step: 900, ms: 500 },
                { label: "1h per 0.5 s", step: 3600, ms: 500 }];
const TOOLS = [
  { type: null, icon: "↖", title: "Cursor (Esc)" }, { type: "trend", icon: "╱", title: "Trend line (Alt+T)", key: "t" },
  { type: "hline", icon: "―", title: "Horizontal line (Alt+H)", key: "h" }, { type: "hray", icon: "⟶", title: "Horizontal ray (Alt+J)", key: "j" },
  { type: "vline", icon: "│", title: "Vertical line (Alt+V)", key: "v" }, { type: "rect", icon: "▭", title: "Box (Alt+R)", key: "r" },
  { type: "fib", icon: "≣", title: "Fib / SD (Alt+F)", key: "f" }, { type: "range", icon: "⇕", title: "Range (or Shift + drag)", key: "m" },
  { type: "text", icon: "T", title: "Text (Alt+N)", key: "n" },
];
const LAYERS = [["arrays", "Arrays"], ["pools", "Pools"], ["profile", "Day bias & draw"], ["sequence", "Setup"], ["orders", "Orders & trades"]];
const S = { meta: null, status: null, tf: "M15", bars: [], t: 0, state: null, journal: [], playing: false, busy: false,
            speed: 1, digits: 5, layers: Prefs.get("watch.layers", { arrays: true, pools: true, profile: true, sequence: true, orders: true }),
            arrayTfs: Prefs.get("watch.arrayTfs", "M15") };

// ── the chart ─────────────────────────────────────────────────────────────
const chart = LightweightCharts.createChart($("chart"), {
  autoSize: true, layout: { background: { color: "transparent" }, textColor: css("--muted"), fontSize: 12 },
  grid: { vertLines: { color: css("--grid") }, horzLines: { color: css("--grid") } },
  crosshair: { mode: LightweightCharts.CrosshairMode.Normal }, rightPriceScale: { borderColor: css("--line") },
  timeScale: { borderColor: css("--line"), timeVisible: true, secondsVisible: false, rightOffset: 14, shiftVisibleRangeOnNewBar: true,
               tickMarkFormatter: (t) => label(t, false) },
  localization: { timeFormatter: (t) => label(t, true) },
});
const series = chart.addCandlestickSeries({ borderVisible: false });
function palette() {
  return { ink: css("--ink"), muted: css("--muted"), accent: css("--accent"), up: css("--up"), down: css("--down"), bad: css("--bad"),
           panel: css("--panel"), warn: css("--warn"), good: css("--good") };
}
function paintTheme() {
  const up = css("--up"), down = css("--down");
  series.applyOptions({ upColor: up, downColor: down, wickUpColor: up, wickDownColor: down });
  chart.applyOptions({ layout: { textColor: css("--muted") }, grid: { vertLines: { color: css("--grid") }, horzLines: { color: css("--grid") } } });
}
paintTheme();
matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => { paintTheme(); refresh(); });
function label(t, long) {
  const d = new Date(t * 1000), hm = pad(d.getUTCHours()) + ":" + pad(d.getUTCMinutes());
  if (SECONDS[S.tf] >= 86400) return `${WD[new Date((t + 7 * 3600) * 1000).getUTCDay()]} ${new Date((t + 7 * 3600) * 1000).getUTCDate()}`;
  return long ? `${WD[d.getUTCDay()]} ${d.getUTCDate()} ${MON[d.getUTCMonth()]} ${hm}` : `${WD[d.getUTCDay()]} ${hm}`;
}
const fmtTime = (t) => (t == null ? "—" : label(t, true));
const fmt = (x) => (x == null ? "—" : Number(x).toFixed(S.digits));
function rgba(c, a) { const m = /^#([0-9a-f]{6})$/i.exec(c); if (!m) return c; const n = parseInt(m[1], 16); return `rgba(${n >> 16},${(n >> 8) & 255},${n & 255},${a})`; }

const timeline = {
  index(t) { const b = S.bars; let lo = 0, hi = b.length - 1, a = -1; while (lo <= hi) { const m = (lo + hi) >> 1; if (b[m].time <= t) { a = m; lo = m + 1; } else hi = m - 1; } return a; },
  toLogical(t) {
    const b = S.bars, sec = SECONDS[S.tf];
    if (!b.length) return 0;
    const i = this.index(t);
    if (i < 0) return (t - b[0].time) / sec;
    const f = (t - b[i].time) / sec;
    return i + (i === b.length - 1 ? f : Math.min(f, 0.999));
  },
  toTime(l) {
    const b = S.bars, sec = SECONDS[S.tf];
    if (!b.length) return 0;
    const i = Math.floor(l);
    if (i < 0) return b[0].time + Math.round(l * sec);
    if (i >= b.length) return b[b.length - 1].time + Math.round((l - (b.length - 1)) * sec);
    return b[i].time + Math.round((l - i) * sec);
  },
  barAt(l) { const b = S.bars; return b.length ? b[Math.max(0, Math.min(b.length - 1, Math.round(l)))] : null; },
};

// ── the trader's own drawings, kept in this browser per session ──────────
const templates = Prefs.get("templates", {});
const drawKey = () => S.status ? `watch.drawings.${S.status.instrument}.${S.status.first_day}` : "watch.drawings";
const draw = new Drawings(chart, series, {
  container: $("chart"), timeline, palette, digits: () => S.digits, template: (type) => templates[type],
  onChange: (items) => Prefs.set(drawKey(), items), onSelect: () => {}, onEdit: (item, start) => window.ReplayUI.toolSettings(draw, item, uiCtx, start),
  onContext: (item, x, y) => { if (item) window.ReplayUI.contextMenu(x, y, [{ label: "Settings…", action: () => window.ReplayUI.toolSettings(draw, item, uiCtx) },
    { label: "Delete", action: () => draw.remove(item) }]); },
  picking: () => false, onPick: () => {}, onError: (t) => say(t),
});
const uiCtx = { palette, kinds: ["OB", "FVG", "BREAKER", "IFVG", "BPR", "LIQUIDITY", "OTHER"], timeframes: Object.keys(SECONDS),
                digits: () => S.digits, timeLabel: (t) => fmtTime(t), say: (t) => say(t),
                saveTemplate: (type, look) => { templates[type] = look; Prefs.set("templates", templates); draw.refresh(); } };

// ── the engine's layer ────────────────────────────────────────────────────
let engineUpdate = () => {};
series.attachPrimitive({
  attached(p) { engineUpdate = p.requestUpdate; }, detached() {}, updateAllViews() {},
  paneViews() { return [{ zOrder: () => "normal", renderer: () => ({ draw: (target) => target.useMediaCoordinateSpace(({ context, mediaSize }) => paintEngine(context, mediaSize)) }) }]; },
});
function X(t) { return logicalX(chart.timeScale(), timeline.toLogical(t)); }
function Y(p) { const y = series.priceToCoordinate(p); return y === null ? NaN : y; }
const TF_RANK = { M1: 1, M3: 2, M5: 3, M15: 4, M30: 5, H1: 6, H3: 7, H4: 8, H6: 9, H8: 10, H12: 11, D1: 12, W1: 13, MN1: 14 };
function showArray(a) {
  const min = { all: 0, M15: 4, H1: 6, H4: 8 }[S.arrayTfs] || 0;
  return a.entry || (TF_RANK[a.tf] || 0) >= min;
}
function paintEngine(ctx, size) {
  const st = S.state, pal = palette(), W = size.width;
  ctx.save();
  ctx.font = "10px system-ui, sans-serif"; ctx.textBaseline = "bottom";
  const text = (s, x, y, color, align) => { ctx.fillStyle = color; ctx.textAlign = align || "left"; ctx.fillText(s, x, y); };
  const line = (x1, y1, x2, y2, color, dash, width) => { ctx.strokeStyle = color; ctx.lineWidth = width || 1; ctx.setLineDash(dash || []); ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke(); ctx.setLineDash([]); };
  if (st && !st.error) {
    if (S.layers.arrays) {
      for (const a of st.arrays.filter(showArray)) {
        const x1 = Math.max(X(a.formed), -10), y1 = Y(a.high), y2 = Y(a.low);
        if (!isFinite(y1) || !isFinite(y2)) continue;
        const c = a.dir === "BULLISH" ? pal.up : a.dir === "BEARISH" ? pal.bad : pal.muted;
        ctx.fillStyle = rgba(c.startsWith("#") ? c : "#888888", a.entry ? 0.22 : 0.06);
        ctx.fillRect(x1, Math.min(y1, y2), W - x1, Math.abs(y2 - y1));
        ctx.strokeStyle = rgba(c.startsWith("#") ? c : "#888888", a.entry ? 0.95 : 0.35); ctx.lineWidth = a.entry ? 2 : 1;
        ctx.strokeRect(x1, Math.min(y1, y2), W - x1, Math.abs(y2 - y1));
        if (a.mt != null) line(x1, Y(a.mt), W, Y(a.mt), rgba(c.startsWith("#") ? c : "#888888", 0.7), [2, 3]);
        text(`${a.tf} ${a.type}${a.entry ? "  ← entry array" : ""}`, Math.max(x1, 0) + 3, Math.min(y1, y2) - 1, c);
      }
    }
    if (S.layers.pools) {
      for (const p of st.pools) {
        const y = Y(p.price), x1 = Math.max(X(p.known), 0);
        if (!isFinite(y)) continue;
        const c = p.side === "BSL" ? pal.warn : pal.accent;
        line(x1, y, W, y, c, [6, 4]);
        text(`${p.source.replace("_", " ")} ${p.tf}`, W - 4, y - 1, c, "right");
      }
    }
    if (S.layers.profile && st.profile) {
      const pr = st.profile, x0 = Math.max(X(pr.open_time), 0);
      line(x0, Y(pr.open), W, Y(pr.open), pal.ink, [1, 3]); text("day open", x0 + 3, Y(pr.open) - 1, pal.ink);
      if (pr.midnight != null) { line(x0, Y(pr.midnight), W, Y(pr.midnight), pal.muted, [6, 3]); text("00:00 open", x0 + 3, Y(pr.midnight) - 1, pal.muted); }
      if (pr.draw) {
        const y = Y(pr.draw.price);
        line(x0, y, W, y, pal.accent, [], 2.5);
        text(`DRAW ${pr.direction === "BULLISH" ? "▲" : "▼"} ${pr.draw.source} ${pr.draw.tf} ${fmt(pr.draw.price)}`, x0 + 3, y - 2, pal.accent);
      }
    }
    if (S.layers.sequence && st.sequence) {
      const sq = st.sequence, c = sq.direction === "BULLISH" ? pal.up : pal.bad;
      const rx = X(sq.raided), ry = Y(sq.pool.price);
      ctx.strokeStyle = c; ctx.lineWidth = 2; ctx.beginPath(); ctx.arc(rx, ry, 6, 0, 2 * Math.PI); ctx.stroke();
      text(`raid of ${sq.pool.source.replace("_", " ")} ${sq.pool.tf}`, rx + 8, ry - 4, c);
      const cx = X(sq.cisd);
      line(cx, 0, cx, size.height, rgba(c.startsWith("#") ? c : "#888888", 0.6), [3, 3]); text("CISD", cx + 3, 24, c);
      const px = X(sq.protected.at), py = Y(sq.protected.wick);
      ctx.fillStyle = c; ctx.beginPath();
      if (sq.direction === "BULLISH") { ctx.moveTo(px, py + 2); ctx.lineTo(px - 6, py + 12); ctx.lineTo(px + 6, py + 12); }
      else { ctx.moveTo(px, py - 2); ctx.lineTo(px - 6, py - 12); ctx.lineTo(px + 6, py - 12); }
      ctx.fill(); text("protected swing", px + 8, sq.direction === "BULLISH" ? py + 14 : py - 6, c);
    }
  }
  if (S.layers.orders) {
    for (const r of S.journal) {
      if (r.decision !== "EXECUTE" || r.placed_at == null || r.placed_at > S.t) continue;
      const long = r.direction === "LONG", c = long ? pal.up : pal.bad;
      const filled = r.filled_at != null && r.filled_at <= S.t;
      const closed = r.closed_at != null && r.closed_at <= S.t;
      if (!filled) {
        const until = Math.min(S.t, r.expires_at || S.t);
        if (r.expires_at != null && r.expires_at < S.t && r.filled_at == null) continue;   // expired unfilled
        const x1 = X(r.placed_at), x2 = Math.max(X(until), x1 + 30);
        line(x1, Y(r.entry), x2, Y(r.entry), c, [5, 3], 1.5); line(x1, Y(r.stop), x2, Y(r.stop), pal.bad, [2, 2]);
        line(x1, Y(r.target), x2, Y(r.target), pal.good, [2, 2]);
        text(`${r.order_kind || ""} ${r.direction} @ ${fmt(r.entry)}  (R:R ${r.r_ratio ? r.r_ratio.toFixed(1) : "—"})`, x1 + 3, Y(r.entry) - 2, c);
        continue;
      }
      const x1 = X(r.filled_at), x2 = closed ? Math.max(X(r.closed_at), x1 + 6) : Math.max(X(S.t), x1 + 40);
      const fy = Y(r.fill), sy = Y(r.stop), ty = Y(r.target);
      const shade = (col, a) => rgba(col.startsWith("#") ? col : "#888888", a);
      ctx.fillStyle = shade(pal.bad, 0.12); ctx.fillRect(x1, Math.min(fy, sy), x2 - x1, Math.abs(sy - fy));     // risk
      ctx.fillStyle = shade(pal.good, 0.12); ctx.fillRect(x1, Math.min(fy, ty), x2 - x1, Math.abs(ty - fy));    // reward
      line(x1, fy, x2, fy, c, [], 1.5);
      line(x1, Y(r.stop), x2, Y(r.stop), pal.bad, [], 1.2); line(x1, Y(r.target), x2, Y(r.target), pal.good, [], 1.2);
      ctx.fillStyle = c; ctx.beginPath();
      if (long) { ctx.moveTo(x1, fy); ctx.lineTo(x1 - 6, fy + 10); ctx.lineTo(x1 + 6, fy + 10); } else { ctx.moveTo(x1, fy); ctx.lineTo(x1 - 6, fy - 10); ctx.lineTo(x1 + 6, fy - 10); }
      ctx.fill();
      if (!closed) {                                    // the open trade, marked to the last close
        const last = S.bars[S.bars.length - 1], risk = Math.abs(r.stop - r.fill);
        const openR = last && risk ? (long ? last.close - r.fill : r.fill - last.close) / risk : null;
        const s = `${r.direction} @ ${fmt(r.fill)} · stop ${fmt(r.stop)} · target ${fmt(r.target)}` +
                  (openR == null ? "" : ` · open ${openR >= 0 ? "+" : ""}${openR.toFixed(2)}R`);
        const right = x1 + 8 + ctx.measureText(s).width > W - 4;          // no room to the right: read leftwards
        text(s, right ? x1 - 8 : x1 + 8, long ? fy + 22 : fy - 12, c, right ? "right" : "left");
      }
      if (closed) {
        const ey = Y(r.exit), win = (r.net_r || 0) > 0;
        ctx.strokeStyle = win ? pal.good : pal.bad; ctx.lineWidth = 2;
        ctx.beginPath(); ctx.moveTo(x2 - 5, ey - 5); ctx.lineTo(x2 + 5, ey + 5); ctx.moveTo(x2 + 5, ey - 5); ctx.lineTo(x2 - 5, ey + 5); ctx.stroke();
        ctx.font = "11px system-ui, sans-serif";
        text(`${r.exit_reason || "exit"} ${r.net_r != null ? (r.net_r >= 0 ? "+" : "") + r.net_r.toFixed(2) + "R" : ""}`, x2 + 7, ey - 3, win ? pal.good : pal.bad);
        ctx.font = "10px system-ui, sans-serif";
      }
    }
  }
  ctx.restore();
}
function refresh() { engineUpdate(); draw.refresh(); }

// ── API ───────────────────────────────────────────────────────────────────
async function api(path, body) {
  const r = await fetch(path, body === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const j = await r.json();
  if (!r.ok) throw new Error(j.error || r.statusText);
  return j;
}
function say(t) { $("msg").textContent = t || ""; }
async function act(fn) { say(""); try { await fn(); } catch (e) { say(e.message); } }

// ── session ───────────────────────────────────────────────────────────────
async function boot() {
  S.meta = await api("/api/watch/meta");
  $("sInst").innerHTML = S.meta.instruments.map((i) => `<option ${i === "XAUUSD" ? "selected" : ""}>${i}</option>`).join("");
  $("sVariant").innerHTML = S.meta.variants.map((v) => `<option>${v}</option>`).join("");
  $("sDays").innerHTML = Array.from({ length: S.meta.max_days }, (_, i) => `<option ${i === 2 ? "selected" : ""}>${i + 1}</option>`).join("");
  Object.assign($("sDay"), { min: S.meta.first, max: S.meta.last, value: Prefs.get("watch.day", "2025-01-27") });
  $("sStart").onclick = () => act(startSession);
  buildTfs(); buildTools(); buildLayers(); buildControls();
  const st = await api("/api/watch/status");
  if (st.state === "ready") await openSession(st); else if (st.state === "preparing") await waitReady();
  else overlay("No session yet", "Pick an instrument, a first day and how many days on the right, then Start session.");
}
async function startSession() {
  Prefs.set("watch.day", $("sDay").value);
  stop();
  await api("/api/watch/start", { instrument: $("sInst").value, first_day: $("sDay").value, days: Number($("sDays").value), variant: $("sVariant").value });
  await waitReady();
}
function overlay(title, text, progress) {
  $("overlay").style.display = title ? "" : "none";
  if (!title) return;
  $("ovTitle").textContent = title; $("ovText").textContent = text || "";
  $("ovProg").parentElement.style.display = progress == null ? "none" : "";
  $("ovProg").style.width = Math.round((progress || 0) * 100) + "%";
}
async function waitReady() {
  $("status").textContent = "preparing"; $("status").className = "pill READING";
  const started = Date.now();
  for (;;) {
    const st = await api("/api/watch/status");
    const pct = Math.round((st.progress || 0) * 100);
    $("prog").style.width = pct + "%";
    $("sMsg").textContent = st.message || "";
    const secs = Math.round((Date.now() - started) / 1000);
    overlay(`Preparing ${st.instrument}, ${st.days} day(s) from ${st.first_day}`,
            `${st.message || "starting"} — ${pct}% (${secs} s). The backtest runs for real; about 20-30 s a day.`, st.progress || 0);
    if (st.state === "ready") { overlay(null); await openSession(st); return; }
    if (st.state === "error") { $("status").textContent = "error"; overlay("The session failed", st.message); throw new Error(st.message); }
    await sleep(700);
  }
}
async function openSession(st) {
  overlay(null);
  S.status = st; S.digits = st.digits;
  $("inst").textContent = `${st.instrument} · ${st.variant}`;
  $("status").textContent = "ready"; $("status").className = "pill REVEALED";
  $("summaryTop").textContent = `${st.days} day(s) from ${st.first_day}: ${st.summary.orders} orders, ${st.summary.trades} trades, ${st.summary.total_r >= 0 ? "+" : ""}${st.summary.total_r}R`;
  $("sMsg").textContent = "Play, step, or jump to the next order. Your own drawings are kept in this browser for this session.";
  $("prog").style.width = "100%";
  S.journal = (await api("/api/watch/journal")).rows;
  draw.load(Prefs.get(drawKey(), []));
  await jumpTo(st.start + 3600);
}

// ── time ──────────────────────────────────────────────────────────────────
async function loadBars(fit) {
  const range = chart.timeScale().getVisibleLogicalRange();
  S.bars = (await api(`/api/watch/bars?tf=${S.tf}&until=${S.t}`)).bars;
  series.applyOptions({ priceFormat: { type: "price", precision: S.digits, minMove: Math.pow(10, -S.digits) } });
  series.setData(S.bars);
  const n = S.bars.length;
  if (fit || !range) chart.timeScale().setVisibleLogicalRange({ from: Math.max(0, n - 140), to: n + 12 });
}
async function loadState() {
  S.state = (await api(`/api/watch/state?t=${S.t}`)).state;
  renderEngine(); renderLog(); refresh();
}
async function jumpTo(t) {
  S.t = Math.max(S.status.start, Math.min(t, S.status.end));
  await loadBars(true); await loadState(); renderHeader();
}
function put(bar) {
  const n = S.bars.length, last = S.bars[n - 1];
  if (last && last.time === bar.time) S.bars[n - 1] = bar; else if (!last || bar.time > last.time) S.bars.push(bar); else return;
  series.update(bar);
}
async function advance(dt) {
  if (S.busy || !S.status) return;
  S.busy = true;
  try {
    const before = S.t;
    S.t = Math.min(S.t + dt, S.status.end);
    if (S.t === before) { stop(); return; }
    const last = S.bars[S.bars.length - 1];
    const got = (await api(`/api/watch/bars?tf=${S.tf}&until=${S.t}&since=${last ? last.time : S.t - 86400}`)).bars;
    try { for (const b of got) put(b); } catch (e) { await loadBars(false); }
    if (Math.floor(S.t / 900) !== Math.floor(before / 900)) await loadState(); else refresh();
    renderHeader();
  } finally { S.busy = false; }
}
function stop() { S.playing = false; $("play").textContent = "▶ Play"; }
function togglePlay() {
  if (S.playing) { stop(); return; }
  S.playing = true; $("play").textContent = "⏸ Pause";
  (async () => {
    while (S.playing) {
      const sp = SPEEDS[S.speed], t0 = performance.now();
      try { await advance(sp.step); } catch (e) { say(e.message); break; }
      if (S.t >= S.status.end) break;
      const wait = sp.ms - (performance.now() - t0);
      if (wait > 0) await sleep(wait);
    }
    stop();
  })();
}
function nextTime(pick) {
  let best = null;
  for (const r of S.journal) for (const t of pick(r)) if (t != null && t > S.t && (best == null || t < best)) best = t;
  return best;
}

// ── controls ──────────────────────────────────────────────────────────────
function tfLabel(tf) { return tf === "W1" ? "W" : tf === "D1" ? "D" : tf[0] === "M" ? tf.slice(1) + "m" : tf.slice(1) + "H"; }
function buildTfs() {
  const box = $("tfs"); box.replaceChildren();
  GROUPS.forEach((g, gi) => {
    if (gi) box.append(Object.assign(document.createElement("span"), { className: "sep" }));
    for (const tf of g) {
      const b = document.createElement("button"); b.textContent = tfLabel(tf); b.dataset.tf = tf; b.classList.toggle("on", tf === S.tf);
      b.onclick = () => act(async () => { S.tf = tf; buildTfs(); if (S.status) { await loadBars(true); refresh(); } });
      box.append(b);
    }
  });
}
function buildTools() {
  const nav = $("tools");
  for (const tool of TOOLS) {
    const b = document.createElement("button"); b.textContent = tool.icon; b.title = tool.title; b.dataset.type = tool.type || "";
    b.onclick = () => { draw.use(tool.type); markTool(); };
    nav.append(b);
  }
  const clear = document.createElement("button"); clear.textContent = "🗑"; clear.title = "Remove my drawings";
  clear.onclick = () => { if (confirm("Remove your drawings in this session?")) draw.clearAll(); };
  nav.append(clear);
}
function markTool() { for (const b of document.querySelectorAll("#tools button[data-type]")) b.classList.toggle("on", (b.dataset.type || null) === draw.tool); }
new MutationObserver(markTool).observe($("chart"), { attributes: true, attributeFilter: ["style"] });
function buildLayers() {
  const box = $("layers");
  for (const [key, name] of LAYERS) {
    const l = document.createElement("label"), c = document.createElement("input");
    c.type = "checkbox"; c.checked = !!S.layers[key];
    c.onchange = () => { S.layers[key] = c.checked; Prefs.set("watch.layers", S.layers); refresh(); };
    l.append(c, " " + name); box.append(l);
  }
  const sel = document.createElement("select");
  sel.innerHTML = [["all", "arrays: every TF"], ["M15", "arrays: M15 and up"], ["H1", "arrays: H1 and up"], ["H4", "arrays: H4 and up"]]
    .map(([v, t]) => `<option value="${v}" ${S.arrayTfs === v ? "selected" : ""}>${t}</option>`).join("");
  sel.onchange = () => { S.arrayTfs = sel.value; Prefs.set("watch.arrayTfs", sel.value); refresh(); };
  box.append(sel);
}
function buildControls() {
  $("speed").innerHTML = SPEEDS.map((s, i) => `<option value="${i}" ${i === S.speed ? "selected" : ""}>${s.label}</option>`).join("");
  $("speed").onchange = () => { S.speed = Number($("speed").value); };
  $("play").onclick = () => togglePlay();
  $("stepBtn").onclick = () => act(async () => { stop(); await advance(900 - (S.t % 900 || 0) || 900); });
  $("nextSetup").onclick = () => act(async () => { stop(); const t = nextTime((r) => (r.decision === "EXECUTE" ? [r.t] : [])); if (t) await jumpTo(t); else say("No more orders in this session."); });
  $("nextEvent").onclick = () => act(async () => { stop(); const t = nextTime((r) => (r.decision === "EXECUTE" ? [r.t, r.filled_at, r.closed_at] : [])); if (t) await jumpTo(t); else say("No more events in this session."); });
  document.addEventListener("keydown", (e) => {
    const typing = /INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName);
    if (e.key === "Escape") { draw.use(null); draw.select(null); draw.measure = null; markTool(); draw.refresh(); return; }
    if (typing || !S.status) return;
    if ((e.key === "Delete" || e.key === "Backspace") && draw.selected) { e.preventDefault(); draw.remove(draw.selected); return; }
    if (e.altKey) { const tool = TOOLS.find((t) => t.key === e.key.toLowerCase()); if (tool) { e.preventDefault(); draw.use(tool.type); markTool(); } return; }
    if (e.key === " ") { e.preventDefault(); togglePlay(); }
    else if (e.key === "ArrowRight") { e.preventDefault(); act(async () => { stop(); await advance(e.shiftKey ? 3600 : 900 - (S.t % 900 || 0) || 900); }); }
  });
}

// ── panels ────────────────────────────────────────────────────────────────
function renderHeader() {
  $("when").textContent = fmtTime(S.t) + " New York";
  const last = S.bars[S.bars.length - 1];
  $("price").textContent = last ? fmt(last.close) : "";
}
const esc = (t) => String(t == null ? "" : t).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
function renderEngine() {
  const st = S.state, box = $("engine");
  if (!st) { box.innerHTML = `<h2>The engine</h2><div class="muted">Before the first close of the session.</div>`; return; }
  if (st.error) { box.innerHTML = `<h2>The engine at ${fmtTime(st.t)}</h2><div class="bad">${esc(st.error)}</div>`; return; }
  const d = st.decision || {}, g = st.grade, pr = st.profile, sq = st.sequence;
  const cls = d.decision === "EXECUTE" ? "good" : d.decision === "NO_TRADE" || d.decision === "IN_TRADE" ? "muted" : "neutral";
  let html = `<h2>The engine at ${fmtTime(st.t)}</h2>
    <div class="card"><div class="decision ${cls}">${esc(d.decision || "no record")}</div><div class="muted">${esc(d.reason || "")}</div>
    ${d.decision === "EXECUTE" ? `<div>${esc(d.order_kind)} ${esc(d.direction)} @ ${fmt(d.entry)} · stop ${fmt(d.stop)} · target ${fmt(d.target)} · R:R ${d.r_ratio ? d.r_ratio.toFixed(1) : "—"}</div>` : ""}</div>`;
  if (g) {
    html += `<div class="card cond"><b>Grade ${esc(g.grade)}</b> (${g.met}/8)${g.counter_trend ? ", counter-trend (capped at B)" : ""}<br>` +
      Object.entries(g.conditions).map(([k, v]) => `<span class="${v ? "y" : "n"}">${v ? "✓" : "✗"}</span> ${esc(k)}`).join("<br>") + `</div>`;
  }
  if (pr) {
    html += `<div class="card"><b>Day profile</b>: ${esc(pr.direction)} (trend ${esc(pr.trend)})<br>
      Draw: ${pr.draw ? `${esc(pr.draw.source)} ${esc(pr.draw.tf)} ${fmt(pr.draw.price)}` : "none"} · open ${fmt(pr.open)} · 00:00 ${fmt(pr.midnight)}<br>
      False move taken: ${pr.false_move ? "yes" : "no"} · Asia raided: ${pr.asia_raided ? "yes" : "no"} · raid in 01:00–13:00: ${pr.raid_in_window ? "yes" : "no"}</div>`;
  }
  if (sq) {
    html += `<div class="card"><b>Setup</b>: ${esc(sq.direction)} after a raid of ${esc(sq.pool.source)} ${esc(sq.pool.tf)} ${fmt(sq.pool.price)} at ${fmtTime(sq.raided)}<br>
      CISD at ${fmtTime(sq.cisd)} · protected swing ${fmt(sq.protected.wick)} (${fmtTime(sq.protected.at)})</div>`;
  }
  const bias = Object.entries(st.bias || {}).map(([tf, b]) => `${tf} ${b.direction === "BULLISH" ? "▲" : b.direction === "BEARISH" ? "▼" : "–"}`).join(" · ");
  html += `<div class="hint">Price against each open: ${bias}. Showing ${st.arrays.length} unfilled arrays and ${st.pools.length} untaken pools near price.</div>`;
  box.innerHTML = html;
}
function renderLog() {
  const items = [];
  for (const r of S.journal) {
    if (r.decision !== "EXECUTE") continue;
    if (r.t <= S.t) items.push({ t: r.t, text: `${r.order_kind || ""} ${r.direction} placed @ ${fmt(r.entry)} (R:R ${r.r_ratio ? r.r_ratio.toFixed(1) : "—"})`, cls: "" });
    if (r.filled_at != null && r.filled_at <= S.t) items.push({ t: r.filled_at, text: `${r.direction} filled @ ${fmt(r.fill)}`, cls: "" });
    if (r.closed_at != null && r.closed_at <= S.t) items.push({ t: r.closed_at, text: `${r.exit_reason || "closed"} ${r.net_r != null ? (r.net_r >= 0 ? "+" : "") + r.net_r.toFixed(2) + "R" : ""}`,
                                                               cls: (r.net_r || 0) > 0 ? "good" : "bad" });
    else if (r.filled_at == null && r.expires_at != null && r.expires_at <= S.t) items.push({ t: r.expires_at, text: "order expired unfilled", cls: "muted" });
  }
  items.sort((a, b) => b.t - a.t);
  $("log").innerHTML = items.length ? items.map((i) => `<div data-t="${i.t}" class="${i.cls}">${fmtTime(i.t)} · ${esc(i.text)}</div>`).join("")
    : `<div class="muted">No orders yet.</div>`;
  for (const div of $("log").children) if (div.dataset.t) div.onclick = () => act(() => jumpTo(Number(div.dataset.t)));
}

boot().catch((e) => say(e.message));
