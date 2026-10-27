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
  // TradingView's position tools (Requirement 25): select one and place it at the clock, beside the engine's trade
  { type: "long", icon: "▲", title: "Long position: entry, stop, target (Alt+L)", key: "l" },
  { type: "short", icon: "▼", title: "Short position: entry, stop, target (Alt+S)", key: "s" },
];
const LAYERS = [["fractal", "Fractal + POI"], ["modelA", "Model A"], ["modelAFramed", "Model A: unswept C1s"], ["arrays", "Arrays"], ["pools", "Pools"],
                ["profile", "Day bias & draw"], ["trend", "Trend"], ["chain", "Chain & stack"], ["sequence", "Setup"], ["candidates", "Candidates"],
                ["orders", "Orders & trades"]];
// The trader's trend (context-engine Requirement 23): the frames it is read on.
const TREND_TFS = ["H1", "H4", "D1"];
// Model A (context-engine Requirement 17): the trader's frame sets.
const MA_SETS = [["model_d1", "Model A: D1 / H1 / M5"], ["model_h4", "Model A: H4 / M15 / M1"]];
// A C1 is shown once C2 has run it, as the trader's indicator draws one (2026-10-24). Model A frames a candidate C1
// at every C close in premium (or discount) with a POI; most die unswept a candle later, behind "unswept C1s".
const maSwept = (y) => y.events.some((e) => e[0] === "MANIPULATED");
const maShown = () => S.ma.filter((y) => S.layers.modelAFramed || maSwept(y));
const S = { meta: null, status: null, tf: "M15", bars: [], t: 0, state: null, journal: [], ideas: [], playing: false, busy: false, picks: {}, hl: null,
            ma: [], maSet: Prefs.get("watch.maSet", "model_d1"), maAt: null,
            trendTf: Prefs.get("watch.trendTf", "H1"), trend: { rows: [], withheld: false, at: null },
            chain: { rows: [], withheld: false, at: null, smt: "" },
            speed: 1, digits: 5, layers: Prefs.get("watch.layers", { arrays: true, pools: true, profile: true, sequence: true, orders: true }),
            arrayMode: Prefs.get("watch.arrayMode", "interval"), arrayVis: Prefs.get("watch.arrayVis", {}) };
// The chart timeframes each array timeframe shows on by default (Requirement 14.3); the trader can change them.
const ARRAY_SHOWS = { M1: ["M1", "M5"], M3: ["M1", "M10"], M5: ["M1", "M15"], M15: ["M1", "H1"], M30: ["M5", "H3"],
                      H1: ["M5", "H4"], H3: ["M15", "H8"], H4: ["M15", "D1"], H6: ["M30", "D1"], H8: ["M30", "D1"],
                      H12: ["H1", "W1"], D1: ["H1", "W1"], W1: ["H4", "W1"] };
const arrayInterval = (tf) => S.arrayVis[tf] || ARRAY_SHOWS[tf] || null;
if (S.layers.modelA === undefined) S.layers.modelA = true;      // new in 2026-10-15: on until switched off
if (S.layers.fractal === undefined) S.layers.fractal = true;    // new in 2026-10-19: the trader's indicator
if (S.layers.chain === undefined) S.layers.chain = true;        // new in 2026-10-24: the chain and the stack

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
function hexOf(c) { const m = /rgba?\((\d+),\s*(\d+),\s*(\d+)/.exec(c); return m ? "#" + [m[1], m[2], m[3]].map((x) => Number(x).toString(16).padStart(2, "0")).join("") : c; }
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
  container: $("chart"), timeline, palette, tf: () => S.tf, digits: () => S.digits, template: (type) => templates[type],
  onChange: (items) => Prefs.set(drawKey(), items.map(({ status, ...d }) => d)), onSelect: (item) => noculus.select(item),
  onEdit: (item, start) => window.ReplayUI.toolSettings(draw, item, uiCtx, start),
  onContext: (item, x, y) => { if (item) window.ReplayUI.contextMenu(x, y, [{ label: "Settings…", action: () => window.ReplayUI.toolSettings(draw, item, uiCtx) },
    ...(item.type === "long" || item.type === "short" ? [{ label: `Place it as my trade at ${fmtTime(S.t)}`, action: () => act(() => noculus.placePosition(item)) }] : []),
    { label: "Delete", action: () => draw.remove(item) }]);
    else window.ReplayUI.contextMenu(x, y, [{ label: "Reset the chart view", action: () => { const n = S.bars.length; motion.fit();
      chart.timeScale().setVisibleLogicalRange({ from: Math.max(0, n - 140), to: n + 12 }); } }, ...motion.menu()]); },
  picking: () => noculus.armed(), onPick: (at) => act(() => noculus.pick(at)), onError: (t) => say(t),
});
const motion = new Motion(chart, series, {
  container: $("chart"), draw, prefs: Prefs, palette, bars: () => S.bars, tfSeconds: () => SECONDS[S.tf],
  now: () => (S.status ? S.t : null), onChange: () => refresh(),
});
// ── Fractal + POI: the trader's own indicator, read at the clock (Requirement 23); blind sessions show it too ──
const fractal = new FractalPOI(chart, series, {
  X, Y, palette, api: (path) => api(path), tf: () => S.tf, clock: () => S.t, status: () => S.status,
  instruments: () => (S.meta ? S.meta.instruments : []), prefs: Prefs, say: (t) => say(t),
  refresh: () => { renderFractal(); renderLog(); refresh(); }, onView: () => renderFractal(),
});
fractal.setOn(S.layers.fractal);
// ── Noculus: the trader's marks, blind until they reveal the engine (Requirements 17-18) ──
const MARK_TFS = ["M1", "M5", "M15", "M30", "H1", "H4", "D1", "W1"];
const noculus = new Noculus(chart, series, {
  box: $("noculus"), timeline, palette, seconds: (tf) => SECONDS[tf], timeframes: MARK_TFS, tf: () => S.tf,
  digits: () => S.digits, clock: () => S.t, status: () => S.status, api: (path, body) => api(path, body),
  say: (t) => say(t), refresh: () => refresh(), timeLabel: (t) => fmtTime(t), X, Y,
  drawings: () => draw.items, redraw: () => draw.refresh(),
  onReveal: async (status) => {                         // the clock stays where it is; the engine joins it
    S.status = status;
    await loadJournal();
    summaryLine(); await loadState(); noculus.render();
  },
});
const uiCtx = { palette, kinds: ["OB", "FVG", "BREAKER", "IFVG", "BPR", "LIQUIDITY", "OTHER"], timeframes: Object.keys(SECONDS), tf: () => S.tf,
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
  if (a.entry || S.arrayMode === "all") return true;
  if (S.arrayMode === "interval") { const iv = arrayInterval(a.tf); return !iv || Visibility.shows(Visibility.between(iv[0], iv[1]), S.tf); }
  return (TF_RANK[a.tf] || 0) >= ({ M15: 4, H1: 6, H4: 8 }[S.arrayMode] || 0);
}
function paintEngine(ctx, size) {
  const st = S.state, pal = palette(), W = size.width;
  ctx.save();
  ctx.font = "10px system-ui, sans-serif"; ctx.textBaseline = "bottom";
  const text = (s, x, y, color, align) => { ctx.fillStyle = color; ctx.textAlign = align || "left"; ctx.fillText(s, x, y); };
  const line = (x1, y1, x2, y2, color, dash, width) => { ctx.strokeStyle = color; ctx.lineWidth = width || 1; ctx.setLineDash(dash || []); ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke(); ctx.setLineDash([]); };
  // The CISD's level, from its run's first candle to the close through it, as the indicator draws it (Req 30.5).
  const cisdLevel = (s, cx, color) => {
    if (s.cisd_level == null || s.cisd_from == null) return;
    const lx = X(s.cisd_from), ly = Y(s.cisd_level);
    if (!isFinite(lx) || !isFinite(ly)) return;
    line(lx, ly, Math.max(cx, lx + 20), ly, color, [], 2); text(`CISD ${fmt(s.cisd_level)}`, lx + 3, ly - 3, color);
  };
  if (st && !st.error && !st.withheld) {
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
      cisdLevel(sq, cx, c);
      const px = X(sq.protected.at), py = Y(sq.protected.wick);
      ctx.fillStyle = c; ctx.beginPath();
      if (sq.direction === "BULLISH") { ctx.moveTo(px, py + 2); ctx.lineTo(px - 6, py + 12); ctx.lineTo(px + 6, py + 12); }
      else { ctx.moveTo(px, py - 2); ctx.lineTo(px - 6, py - 12); ctx.lineTo(px + 6, py - 12); }
      ctx.fill(); text("protected swing", px + 8, sq.direction === "BULLISH" ? py + 14 : py - 6, c);
    }
  }
  if (S.layers.modelA) paintModelA(ctx, size, pal, text, line);
  if (st && !st.error && st.candidates) {               // what the sequence detector ranked; the hovered one always
    for (const c of [...st.candidates.ranked].reverse()) {
      if (!S.layers.candidates && c.id !== S.hl) continue;
      const x1 = Math.max(X(c.formed), -10), y1 = Y(c.high), y2 = Y(c.low);
      if (!isFinite(y1) || !isFinite(y2)) continue;
      const col = c.dir === "BULLISH" ? pal.up : pal.bad, hex = col.startsWith("#") ? col : "#888888", hot = c.id === S.hl;
      if (hot) { ctx.fillStyle = rgba(hex, 0.18); ctx.fillRect(x1, Math.min(y1, y2), W - x1, Math.abs(y2 - y1)); }
      ctx.strokeStyle = rgba(hex, c.chosen || hot ? 1 : 0.6); ctx.lineWidth = c.chosen || hot ? 2 : 1; ctx.setLineDash(c.chosen ? [] : [4, 3]);
      ctx.strokeRect(x1, Math.min(y1, y2), W - x1, Math.abs(y2 - y1)); ctx.setLineDash([]);
      text(`#${c.rank} ${c.tf} ${c.type}${c.chosen ? " (engine)" : ""}`, Math.max(x1, 0) + 3, Math.max(y1, y2) + 11, col);
      if (hot) {
        const rx = X(c.raid.at), ry = Y(c.raid.price), cx = X(c.cisd);
        ctx.strokeStyle = col; ctx.lineWidth = 2; ctx.beginPath(); ctx.arc(rx, ry, 6, 0, 2 * Math.PI); ctx.stroke();
        text(`raid ${c.raid.source.replace("_", " ")} ${c.raid.tf}, ${c.raid.age_h} h before`, rx + 8, ry - 4, col);
        line(cx, 0, cx, size.height, rgba(hex, 0.6), [3, 3]); text("CISD", cx + 3, 36, col);
        cisdLevel(c, cx, col);
      }
    }
  }
  if (S.layers.orders) {
    for (const i of S.ideas) {                           // a trade the engine wanted but its limits refused (Req 26.1)
      if (i.kind !== "SKIPPED" || i.from > S.t || i.until <= S.t) continue;
      const long = i.direction === "LONG", c = long ? pal.up : pal.bad;
      const x1 = X(i.from), x2 = Math.max(X(S.t), x1 + 40), ey = Y(i.entry), sy = Y(i.stop), ty = Y(i.target);
      if (!isFinite(ey) || !isFinite(x1)) continue;
      const shade = (col, a) => rgba(col.startsWith("#") ? col : "#888888", a);
      ctx.fillStyle = shade(pal.bad, 0.07); ctx.fillRect(x1, Math.min(ey, sy), x2 - x1, Math.abs(sy - ey));
      ctx.fillStyle = shade(pal.good, 0.07); ctx.fillRect(x1, Math.min(ey, ty), x2 - x1, Math.abs(ty - ey));
      ctx.strokeStyle = c; ctx.lineWidth = 1; ctx.setLineDash([4, 3]);
      ctx.strokeRect(x1, Math.min(sy, ty), x2 - x1, Math.abs(ty - sy)); ctx.setLineDash([]);
      line(x1, ey, x2, ey, c, [4, 3], 1.5);
      text(`engine wanted ${i.direction} @ ${fmt(i.entry)} · stop ${fmt(i.stop)} · target ${fmt(i.target)} (R:R ${i.r_ratio ? i.r_ratio.toFixed(1) : "—"}${i.grade ? ", " + i.grade : ""})`,
           x1 + 3, ey - 2, c);
      text(`refused: ${i.reason}`, x1 + 3, long ? ey + 12 : ey - 13, pal.muted);
    }
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
      // After a partial (Requirement 28) the stop is the fill: the risk ends where the partial came off.
      const xs = r.partial_at != null && r.partial_at <= S.t ? Math.min(Math.max(X(r.partial_at), x1), x2) : x2;
      ctx.fillStyle = shade(pal.bad, 0.12); ctx.fillRect(x1, Math.min(fy, sy), xs - x1, Math.abs(sy - fy));     // risk
      ctx.fillStyle = shade(pal.good, 0.12); ctx.fillRect(x1, Math.min(fy, ty), x2 - x1, Math.abs(ty - fy));    // reward
      line(x1, fy, x2, fy, c, [], 1.5);
      line(x1, Y(r.stop), xs, Y(r.stop), pal.bad, [], 1.2); line(x1, Y(r.target), x2, Y(r.target), pal.good, [], 1.2);
      ctx.fillStyle = c; ctx.beginPath();
      if (long) { ctx.moveTo(x1, fy); ctx.lineTo(x1 - 6, fy + 10); ctx.lineTo(x1 + 6, fy + 10); } else { ctx.moveTo(x1, fy); ctx.lineTo(x1 - 6, fy - 10); ctx.lineTo(x1 + 6, fy - 10); }
      ctx.fill();
      const oneR = r.fill + (long ? 1 : -1) * Math.abs(r.fill - r.stop);   // where a break-even would arm
      line(x1, Y(oneR), x2, Y(oneR), rgba(hexOf(pal.muted), 0.8), [1, 3]); text("+1R", x2 + 3, Y(oneR) + 4, pal.muted);
      const mark = (t, p, label, color, up) => {
        const mx = X(t), my = Y(p);
        if (!isFinite(mx) || !isFinite(my)) return;
        ctx.fillStyle = color; ctx.beginPath(); ctx.arc(mx, my, 3.5, 0, 2 * Math.PI); ctx.fill();
        text(label, mx + 6, up ? my - 5 : my + 13, color);
      };
      if (r.partial_at != null && r.partial_at <= S.t) {  // the partial (Requirement 28), once taken
        const partialR = (long ? r.partial_exit - r.fill : r.fill - r.partial_exit) / Math.abs(r.fill - r.stop);
        mark(r.partial_at, r.partial_exit, `${Math.round(100 * r.partial_fraction)}% off +${partialR.toFixed(1)}R, rest to BE`, pal.good, long);
      }
      if (closed && r.path) {                           // the path, once it is all in the past
        mark(r.path.best_at, r.path.best, `best +${r.path.best_r.toFixed(2)}R`, pal.good, long);
        mark(r.path.worst_at, r.path.worst, `worst ${r.path.worst_r.toFixed(2)}R`, pal.bad, !long);
      } else if (!closed) {                             // the best so far, from the chart's own bars
        const i0 = Math.max(0, timeline.index(r.filled_at));
        let best = r.fill, at = r.filled_at;
        for (let i = i0; i < S.bars.length; i++) {
          const b = S.bars[i], p = long ? b.high : b.low;
          if (long ? p > best : p < best) { best = p; at = Math.max(b.time, r.filled_at); }
        }
        const bestR = (long ? best - r.fill : r.fill - best) / Math.abs(r.fill - r.stop);
        if (bestR > 0.05) mark(at, best, `best so far +${bestR.toFixed(2)}R`, pal.good, long);
      }
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
        text(`${exitLabel(r)} ${r.net_r != null ? (r.net_r >= 0 ? "+" : "") + r.net_r.toFixed(2) + "R" : ""}`, x2 + 7, ey - 3, win ? pal.good : pal.bad);
        ctx.font = "10px system-ui, sans-serif";
      }
    }
  }
  if (S.layers.trend) paintTrend(ctx, size, pal, text);
  if (S.layers.chain) paintChain(ctx, size, pal, text, line);
  ctx.restore();
}
// The trader's trend (context-engine Requirement 23): a strip along the chart's foot, one cell per closed candle of
// the trend's frame (red bearish, green bullish, grey neither), and the last one's five signals spelled out.
function paintTrend(ctx, size, pal, text) {
  const H = size.height, W = size.width, sec = SECONDS[S.trendTf] || 3600, y = H - 9;
  const arrow = (v) => (v < 0 ? "▼" : v > 0 ? "▲" : "·");
  if (S.trend.withheld) { text(`Trend ${S.trendTf}: hidden until you reveal`, 6, y - 3, pal.muted); return; }
  for (const r of S.trend.rows) {
    const x0 = X(r.time), x1 = X(r.time + sec);
    if (!isFinite(x0) || !isFinite(x1) || x1 < 0 || x0 > W) continue;
    ctx.fillStyle = r.trend < 0 ? rgba(hexOf(pal.bad), 0.85) : r.trend > 0 ? rgba(hexOf(pal.good), 0.85) : rgba(hexOf(pal.muted), 0.25);
    ctx.fillRect(Math.max(x0, 0) + 0.5, y, Math.max(1, Math.min(x1, W) - Math.max(x0, 0) - 1), 6);
  }
  const last = S.trend.rows[S.trend.rows.length - 1];
  if (!last) return;
  const parts = [["structure", "structure"], ["closes", "closes"], ["liquidity", "sweeps"], ["arrays", "arrays"], ["po3", "PO3"]]
    .map(([k, name]) => `${name} ${arrow(last[k])}`).join("  ");
  text(`Trend ${S.trendTf} ${arrow(last.trend)} ${last.score > 0 ? "+" : ""}${last.score}   ${parts}`, 6, y - 3,
       last.trend < 0 ? pal.bad : last.trend > 0 ? pal.good : pal.muted);
}
// The context chain and the confluence stack (2026-10-24): what H-K and H-M read at each D1 close, on the candles.
// A strip along the chart's top, one cell per closed D1 candle: the stack's call (green up, red down, grey none)
// with its score and, once the next candle has closed, a tick or a cross; under it a thin bar for the chain alone.
// The latest close's frames are drawn to the right of it: the W1 and D1 dealing ranges with their 50% (the MN1
// range faint), each frame's POIs (dashed once reached), and the chain's draw.
function paintChain(ctx, size, pal, text, line) {
  const W = size.width;
  if (S.chain.withheld) { text("Chain & stack: hidden until you reveal", 6, 14, pal.muted); return; }
  const rows = S.chain.rows;
  if (!rows.length) return;
  for (const r of rows) {
    const x1 = X(r.open), x2 = X(r.close);
    if (!isFinite(x1) || !isFinite(x2) || x2 < 0 || x1 > W) continue;
    const c = r.call > 0 ? pal.good : r.call < 0 ? pal.bad : pal.muted;
    ctx.fillStyle = rgba(hexOf(c), r.call ? 0.85 : 0.25); ctx.fillRect(x1 + 1, 2, Math.max(x2 - x1 - 2, 2), 8);
    const k = r.chain_call > 0 ? pal.good : r.chain_call < 0 ? pal.bad : pal.muted;
    ctx.fillStyle = rgba(hexOf(k), r.chain_call ? 0.6 : 0.15); ctx.fillRect(x1 + 1, 11, Math.max(x2 - x1 - 2, 2), 3);
    let s = `${r.score > 0 ? "+" : ""}${r.score}`;
    if (r.next != null && r.call) s += r.next === r.call ? " ✓" : " ✗";
    text(s, (x1 + x2) / 2, 26, c, "center");
  }
  const last = rows[rows.length - 1], x0 = Math.max(X(last.close), -10);
  const frames = Object.fromEntries((last.frames || []).map((f) => [f.tf, f]));
  const range = (f, color, dash, alpha) => {
    if (!f || !f.range) return;
    const [lo, hi] = f.range, mid = (lo + hi) / 2, col = rgba(hexOf(color), alpha);
    line(x0, Y(hi), W, Y(hi), col, dash, 1); line(x0, Y(lo), W, Y(lo), col, dash, 1); line(x0, Y(mid), W, Y(mid), col, [8, 4], 1);
    text(`${f.tf} high ${fmt(hi)}`, W - 4, Y(hi) - 2, col, "right"); text(`${f.tf} low ${fmt(lo)}`, W - 4, Y(lo) + 11, col, "right");
    text(`${f.tf} 50% · ${f.zone || "unranged"}${f.position != null ? " " + Math.round(100 * f.position) + "%" : ""}`, W - 4, Y(mid) - 2, col, "right");
  };
  range(frames.MN1, pal.muted, [1, 3], 0.6); range(frames.W1, pal.accent, [], 0.9); range(frames.D1, pal.ink, [4, 3], 0.6);
  for (const f of last.frames || []) {
    for (const [key, color] of [["poi_bull", pal.up], ["poi_bear", pal.bad]]) {
      const p = f[key];
      if (!p) continue;
      const px = Math.max(X(p.formed), -10), a = Y(p.high), b = Y(p.low);
      if (!isFinite(a) || !isFinite(b)) continue;
      ctx.fillStyle = rgba(hexOf(color), p.reached != null ? 0.06 : 0.14); ctx.fillRect(px, Math.min(a, b), W - px, Math.abs(b - a));
      ctx.strokeStyle = rgba(hexOf(color), 0.7); ctx.lineWidth = 1; ctx.setLineDash(p.reached != null ? [3, 3] : []);
      ctx.strokeRect(px, Math.min(a, b), W - px, Math.abs(b - a)); ctx.setLineDash([]);
      text(`${f.tf} POI · ${p.kind} ${p.reached != null ? "reached" : "unreached"}`, Math.max(px, 0) + 3, Math.min(a, b) - 2, color);
    }
  }
  const links = last.links || [], bias = links[links.length - 1];
  if (bias && bias.draw) {
    const c = bias.context === "BULLISH" ? pal.good : pal.bad, y = Y(bias.draw.price);
    line(x0, y, W, y, c, [6, 3], 2);
    text(`draw → ${bias.draw.tf} ${bias.draw.source} ${fmt(bias.draw.price)}`, Math.max(x0, 0) + 3, y - 3, c);
  }
  const read = bias ? `${bias.context} (${bias.case.replace(/_/g, " ").toLowerCase()})` : "no chain yet";
  text(`Chain: D1 ${read} · stack ${last.score > 0 ? "+" : ""}${last.score} of 13 · ${last.call ? (last.call > 0 ? "call up" : "call down") : "no call (needs ±7)"}`,
       6, 40, last.call > 0 ? pal.good : last.call < 0 ? pal.bad : pal.muted);
}
async function loadChain() {
  if (!S.status || !S.layers.chain) { S.chain = { rows: [], withheld: false, at: null, smt: "" }; return; }
  const key = `${Math.floor((S.t + 7 * 3600) / 86400)}|${!!(S.state && S.state.withheld)}`;   // D1 closes at 17:00 New York
  if (S.chain.at === key) return;
  const got = await api(`/api/watch/chain?t=${S.t}`);
  S.chain = { rows: got.rows || [], withheld: !!got.withheld, at: key, smt: got.smt || "" };
}
// The chain and the stack at the latest D1 close, in words: each frame's read, the links and the thirteen votes.
const VOTE_NAMES = { "own-MN1": "MN1 own", "own-W1": "W1 own", "own-D1": "D1 own", "H-K": "chain", profile: "candle profile",
                     "zone-W1": "W1 P/D", "zone-D1": "D1 P/D", structure: "structure", closes: "closes", liquidity: "failed sweep",
                     arrays: "arrays", po3: "PO3", smt: "SMT" };
function chainCard() {
  if (S.chain.withheld) return `<div class="card"><b>Chain & stack</b><div class="muted">Hidden: this session is blind.</div></div>`;
  const rows = S.chain.rows, last = rows[rows.length - 1];
  if (!last) return `<div class="card"><b>Chain & stack</b><div class="muted">No D1 candle has closed in view yet.</div></div>`;
  const arrow = (v) => (v > 0 ? "▲" : v < 0 ? "▼" : "–");
  const frames = (last.frames || []).map((f) => `<div><b>${esc(f.tf)}</b> own ${esc(f.own)} · ${esc(f.zone || "unranged")}${f.position != null ? ` (${Math.round(100 * f.position)}%)` : ""} · trend ${esc(f.trend)}
      <div class="muted">${esc(f.reasons.range)}; ${esc(f.reasons.own)}; POI ▲ ${esc(f.reasons.poi_bullish)}; POI ▼ ${esc(f.reasons.poi_bearish)}</div></div>`).join("");
  const links = (last.links || []).map((x) => `<div>${esc(x.reason)}</div>`).join("");
  const votes = Object.entries(last.votes).map(([k, v]) => `<span class="${v > 0 ? "good" : v < 0 ? "bad" : "muted"}">${esc(VOTE_NAMES[k] || k)} ${arrow(v)}</span>`).join(" · ");
  const res = last.next == null ? "the next candle hasn't closed" : `next candle ${arrow(last.next)}${last.call ? (last.next === last.call ? ": right" : ": wrong") : ""}`;
  const called = rows.filter((r) => r.call && r.next != null), right = called.filter((r) => r.next === r.call).length;
  return `<div class="card"><b>Chain & stack</b> at the D1 close ${fmtTime(last.close)}
    <div>Stack <b>${last.score > 0 ? "+" : ""}${last.score}</b> of 13: ${last.call ? `<b>${last.call > 0 ? "up" : "down"}</b>` : "no call (needs ±7)"} · the chain alone ${arrow(last.chain_call)} · ${esc(res)}</div>
    <div class="muted">${votes}</div>${frames ? `<div class="hint">Frames</div>${frames}<div class="hint">Links (PD_POI)</div>${links}`
      : `<div class="muted">The monthly frame has no range yet: the chain needs more closed months of history.</div>`}
    <div class="hint">SMT ${esc(S.chain.smt)}. In view: ${called.length} stack call(s) resolved, ${right} right.</div></div>`;
}
function paintModelA(ctx, size, pal, text, line) {
  const W = size.width;
  for (const y of maShown()) {
    const short = y.side === "SHORT", col = short ? pal.bad : pal.up, hex = col.startsWith("#") ? col : "#888888";
    const alpha = y.ended ? 0.35 : 1, c = (a) => rgba(hex, a * alpha);
    const x0 = Math.max(X(y.c1_open), -10), xr = y.end_at ? X(y.end_at) : W, cSec = SECONDS[y.c] || 900;
    if (y.f_range) {                                  // F's equilibrium: premium above it for shorts, discount below for longs
      const mid = (y.f_range[0] + y.f_range[1]) / 2;
      line(x0, Y(mid), xr, Y(mid), rgba(hexOf(pal.muted), 0.6 * alpha), [8, 4]); text(`${y.f} 50%`, x0 + 3, Y(mid) - 2, pal.muted);
    }
    const p1 = Y(y.poi_near), p2 = Y(isFinite(y.poi_far) ? y.poi_far : y.poi_near);
    ctx.fillStyle = c(0.12); ctx.fillRect(x0, Math.min(p1, p2), xr - x0, Math.abs(p2 - p1));
    ctx.strokeStyle = c(0.8); ctx.lineWidth = 1; ctx.setLineDash([]); ctx.strokeRect(x0, Math.min(p1, p2), xr - x0, Math.abs(p2 - p1));
    text(`POI · ${y.poi_label}`, x0 + 3, (short ? Math.min(p1, p2) : Math.max(p1, p2) + 11) - 1, col);
    const c1x2 = X(y.c1_open + cSec);
    line(x0, Y(y.c1_extreme), Math.max(c1x2, x0 + 12), Y(y.c1_extreme), c(1), [], 2);
    line(x0, Y(y.c1_opposite), xr, Y(y.c1_opposite), c(0.7), [4, 3]);
    text(`C1 ${short ? "high" : "low"}`, x0 + 3, Y(y.c1_extreme) + (short ? 11 : -2), col);
    text(`C1 ${short ? "low" : "high"}: TP1`, x0 + 3, Y(y.c1_opposite) + (short ? 11 : -2), col);
    const manip = y.events.find((e) => e[0] === "MANIPULATED");
    if (manip) { const mx = X(manip[1]); line(mx, Y(y.poi_near) + (short ? -14 : 14), mx, Y(y.poi_near), col, [], 2); }
    if (y.c2_extreme != null) {
      line(c1x2, Y(y.c2_extreme), xr, Y(y.c2_extreme), c(0.9), [], 1.5);
      text(`C2 ${short ? "high" : "low"}`, Math.max(c1x2, 0) + 3, Y(y.c2_extreme) + (short ? -2 : 11), col);
    }
    if (y.entry != null) {
      const ox = Math.max(X(y.order_at), x0);
      const a = Y(y.ote_near), b = Y(y.ote_far);
      ctx.fillStyle = c(0.18); ctx.fillRect(ox, Math.min(a, b), xr - ox, Math.abs(b - a));
      text("OTE 0.62-0.79", ox + 3, Math.min(a, b) - 2, col);
      line(ox, Y(y.entry), xr, Y(y.entry), c(1), [], 2); text(`0.705 entry ${fmt(y.entry)}`, ox + 3, Y(y.entry) - 2, col);
      line(ox, Y(y.stop), xr, Y(y.stop), rgba(hexOf(pal.bad), alpha), [2, 2]); text("stop", ox + 3, Y(y.stop) - 2, pal.bad);
      line(ox, Y(y.range_end), xr, Y(y.range_end), c(0.6), [1, 3]);
      for (const [k, name] of [["sd1", "-1 SD"], ["sd2", "-2 SD"], ["sd25", "-2.5 SD"]]) {
        line(ox, Y(y[k]), xr, Y(y[k]), rgba(hexOf(pal.good), 0.7 * alpha), [6, 3]); text(name, ox + 3, Y(y[k]) - 2, pal.good);
      }
    }
    if (y.fill != null) {
      const ent = y.events.find((e) => e[0] === "ENTERED");
      if (ent) { ctx.fillStyle = col; ctx.beginPath(); ctx.arc(X(ent[1]), Y(y.fill), 4, 0, 2 * Math.PI); ctx.fill(); }
    }
    ctx.font = "11px system-ui, sans-serif";
    const badge = `${y.side} · ${y.ended || y.state}`;
    text(badge, Math.max(x0, 0) + 3, (short ? Math.min(p1, p2) : Math.max(p1, p2)) + (short ? -14 : 25), col);
    ctx.font = "10px system-ui, sans-serif";
  }
}
async function loadTrend() {
  if (!S.status || !S.layers.trend) { S.trend = { rows: [], withheld: false, at: null }; return; }
  const key = `${S.trendTf}@${S.t}`;
  if (S.trend.at === key) return;
  const got = await api(`/api/watch/trend?tf=${S.trendTf}&t=${S.t}`);
  S.trend = { rows: got.rows || [], withheld: !!got.withheld, at: key };
}
async function loadModelA() {
  if (!S.status || !S.layers.modelA) { S.ma = []; return; }
  const key = `${S.maSet}@${S.t}`;
  if (S.maAt === key) return;
  S.maAt = key;
  S.ma = (await api(`/api/watch/model-a?set=${S.maSet}&t=${S.t}`)).instances;
}
function refresh() { engineUpdate(); fractal.update(); noculus.update(); draw.refresh(); }
function renderFractal() {
  const box = $("fractal");
  box.innerHTML = fractal.panel();
  const b = box.querySelector("[data-fractal]");
  if (b) b.onclick = () => act(() => fractal.dialog());
}

// ── API ───────────────────────────────────────────────────────────────────
async function api(path, body, retried = false) {
  const r = await fetch(path, body === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const j = await r.json();
  if (!r.ok) {
    // The server restarted under the page: start the same session again and carry on from the same clock. A
    // blind session's marks and trades are on disk and come back with it; a revealed one stays revealed.
    if (r.status === 409 && /no session/.test(j.error || "") && S.status && !S.recovering && !retried) {
      await recover();
      return api(path, body, true);
    }
    throw new Error(j.error || r.statusText);
  }
  return j;
}
async function recover() {
  const st = S.status, t = S.t;
  S.recovering = true;
  stop();
  try {
    say("The server restarted: starting your session again where you were…");
    await api("/api/watch/start", { instrument: st.instrument, first_day: st.first_day, days: st.days,
                                   variant: st.variant, blind: !!st.blind, live: !!st.live }, true);
    await waitReady(t);
    say("Your session is back.");
  } finally { S.recovering = false; }
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
  const want = (new URLSearchParams(location.search).get("inst") || "").toUpperCase();
  if (S.meta.instruments.includes(want)) $("sInst").value = want;
  await Shell.init({ mode: "engine", inst: $("sInst").value, onPick: (i) => act(async () => {
    $("sInst").value = i; Shell.setInstrument(i);
    if (S.status) await startSession();            // TradingView's tabs: the same days, the other instrument
    else overlay("No session yet", `Start a session for ${i} on the right.`);
  }) });
  for (const id of ["sInst", "sDay", "sDays"]) $(id).addEventListener("change", () => { Shell.setInstrument($("sInst").value); blindCheck(); });
  $("sLiveRow").style.display = S.meta.live ? "" : "none";       // the broker's terminal, now (Requirement 27)
  $("sLive").checked = !!S.meta.live && Prefs.get("watch.live", false);
  const liveForm = () => { $("sDay").disabled = $("sLive").checked; };
  $("sLive").addEventListener("change", () => { Prefs.set("watch.live", $("sLive").checked); liveForm(); blindCheck(); });
  liveForm();
  blindCheck();
  $("sStart").onclick = () => act(startSession);
  buildTfs(); buildTools(); buildLayers(); buildControls();
  const st = await api("/api/watch/status");
  if (st.state === "ready") await openSession(st); else if (st.state === "preparing") await waitReady();
  else overlay("No session yet", "Pick an instrument, a first day and how many days on the right, then Start session.");
}
async function blindCheck() {                         // days still unread in the blind replay
  if ($("sLive").checked) { S.unread = 0; $("blindWarn").textContent = ""; return; }   // live days are not in it
  try {
    const b = await api(`/api/blind?inst=${$("sInst").value}&first_day=${$("sDay").value}&days=${$("sDays").value}`);
    S.unread = b.unread;
    $("blindWarn").textContent = b.unread ? `${b.unread} of these ${b.days} day(s) are still unread in your blind replay: `
      + "watching the engine on them spoils them for a blind read." : "";
  } catch (e) { S.unread = 0; $("blindWarn").textContent = ""; }
}
async function startSession() {
  const blind = $("sBlind").checked;                    // a blind session spoils nothing: the engine stays hidden
  const live = $("sLive").checked;
  await blindCheck();
  if (!blind && S.unread && !confirm(`${S.unread} of these days are still unread in your blind replay. Watching the engine on them spoils `
                                     + "them for a blind read. Start anyway?")) return;
  if (!live) Prefs.set("watch.day", $("sDay").value);
  stop();
  await api("/api/watch/start", { instrument: $("sInst").value, first_day: $("sDay").value, days: Number($("sDays").value),
                                 variant: $("sVariant").value, blind, live });
  await waitReady();
}
function overlay(title, text, progress) {
  $("overlay").style.display = title ? "" : "none";
  if (!title) return;
  $("ovTitle").textContent = title; $("ovText").textContent = text || "";
  $("ovProg").parentElement.style.display = progress == null ? "none" : "";
  $("ovProg").style.width = Math.round((progress || 0) * 100) + "%";
}
async function waitReady(resumeAt) {
  $("status").textContent = "preparing"; $("status").className = "pill READING";
  const started = Date.now();
  for (;;) {
    const st = await api("/api/watch/status");
    const pct = Math.round((st.progress || 0) * 100);
    $("prog").style.width = pct + "%";
    $("sMsg").textContent = st.message || "";
    const secs = Math.round((Date.now() - started) / 1000);
    overlay(`Preparing ${st.instrument}, ${st.live ? "live: " : ""}${st.days} day(s) from ${st.first_day}`,
            st.live ? `${st.message || "starting"} — ${pct}% (${secs} s). The engine is read at every close since the first day's open, `
                      + "then the chart follows the market live." :
            `${st.message || "starting"} — ${pct}% (${secs} s). The backtest runs for real; about 20-30 s a day.`, st.progress || 0);
    if (st.state === "ready") { overlay(null); await openSession(st, resumeAt); return; }
    if (st.state === "error") { $("status").textContent = "error"; overlay("The session failed", st.message); throw new Error(st.message); }
    await sleep(700);
  }
}
async function openSession(st, resumeAt) {
  overlay(null);
  S.status = st; S.digits = st.digits;
  $("sInst").value = st.instrument; Shell.setInstrument(st.instrument);
  $("inst").textContent = `${st.instrument} · ${st.variant}`;
  $("status").textContent = st.blind && st.revealed_at == null ? "blind" : st.live ? "● live" : "ready";
  $("status").className = "pill REVEALED";
  summaryLine();
  $("sMsg").textContent = st.blind && st.revealed_at == null
    ? "The engine is hidden. Mark what you see and place your trades, then reveal it (Noculus, on the right)."
    : st.live ? "Live: the price moves as the market does; the engine reads each 15-minute close as it closes, as the "
                + "paper runner does. Step back to look; Back to live returns to now."
    : "Play, step, or jump to the next order. Your own drawings are kept in this browser for this session.";
  $("prog").style.width = "100%";
  await loadJournal();
  S.picks = Object.fromEntries((await api("/api/watch/picks")).picks.map((p) => [p.t, p]));
  draw.load(Prefs.get(drawKey(), []));
  await noculus.sync();
  await jumpTo(resumeAt != null ? resumeAt : st.live ? st.end : st.start + 3600);
  if (st.live) follow();
}

// A live session (Requirement 27): every second the page asks for the market now, the forming candle of its
// chart and the last bid and ask, and draws them; the price moves through what the engine drew at its last close.
// The server reads the terminal again while asked; when a minute has closed and been read (the session's version
// moves), the engine's orders are read again and the clock steps to the new end, which reads the engine at a new
// 15-minute close. Stepped back, the clock stays where the trader put it and the chart shows that time.
const LIVE_TICK_MS = 1000;
const liveKey = (st) => (st && st.live ? [st.instrument, st.first_day, st.days, st.variant, !!st.blind].join("|") : null);
const atLive = () => !!(S.status && S.status.live && S.t >= S.status.end);
async function follow() {
  const key = liveKey(S.status);
  if (!key || S.follow === key) return;
  S.follow = key;
  while (S.follow === key && liveKey(S.status) === key) {
    await sleep(LIVE_TICK_MS);
    if (liveKey(S.status) !== key) break;
    try {
      const now = await api(`/api/watch/live?tf=${S.tf}`);
      if (liveKey(S.status) !== key) break;
      say(now.message || "");
      const was = S.status;
      if (now.state === "ready" && (now.version !== was.version || now.end !== was.end)) {
        const st = await api("/api/watch/status");
        if (liveKey(st) !== key) break;                // another session took the server
        const following = S.t >= was.end;
        S.status = { ...was, ...st };
        summaryLine();
        await loadJournal();
        if (following && !S.busy) await advance(st.end - S.t);
        else { renderLog(); refresh(); }
      }
      S.now = now;
      if (atLive() && !S.busy) { for (const b of now.bars) put(b); refresh(); }
      renderHeader();
    } catch (e) { say(e.message); }
  }
  if (S.follow === key) S.follow = null;
}

async function loadJournal() {                          // the engine's orders and the trades it wanted (none while blind)
  const j = await api("/api/watch/journal");
  S.journal = j.rows; S.ideas = j.ideas || [];
}

function summaryLine() {
  const st = S.status, s = st.summary || {};
  const days = `${st.live ? "live, " : ""}${st.days} day(s) from ${st.first_day}`;
  $("summaryTop").textContent = st.blind && st.revealed_at == null
    ? `${days}: blind — the engine's side is hidden`
    : `${days}: ${s.orders} orders, ${s.trades} trades, ${s.total_r >= 0 ? "+" : ""}${s.total_r}R`;
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
  await loadModelA(); await loadTrend(); await loadChain();
  await fractal.tick();
  renderFractal();
  Shell.refresh("t=" + S.t);
  renderEngine(); renderLog(); refresh();
}
async function jumpTo(t) {
  S.t = Math.max(S.status.start, Math.min(t, S.status.end));
  await loadBars(true); await loadState(); await noculus.tick(); renderHeader();
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
    if (Math.floor(S.t / 900) !== Math.floor(before / 900)) await loadState();
    else { await loadModelA(); await loadTrend(); await loadChain(); await fractal.tick(); renderFractal(); renderEngine(); renderLog(); refresh(); }
    await noculus.tick();                               // the trader's own trades settle to the clock too
    renderHeader();
  } finally { S.busy = false; }
}
// A live session has no replay to play: the button says Live at the end, and takes a stepped-back clock back to it.
const playLabel = () => (S.status && S.status.live ? (atLive() ? "● Live" : "⏭ Back to live") : S.playing ? "⏸ Pause" : "▶ Play");
function stop() { S.playing = false; $("play").textContent = playLabel(); }
function togglePlay() {
  if (S.status && S.status.live) { stop(); act(async () => { await jumpTo(S.status.end); stop(); }); return; }
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
      b.onclick = () => act(async () => { S.tf = tf; buildTfs(); if (S.status) { await loadBars(true); await fractal.tick(); renderFractal(); refresh(); } });
      box.append(b);
    }
  });
}
// The magnet (as TradingView's): off, weak (snaps to a bar's open, high, low or close when near one), strong
// (always the nearest of the four). Shift straightens a line while it is drawn.
const MAGNETS = [[false, "🧲", "Magnet off (click: weak)"],
                 ["weak", "🧲", "Magnet: snaps to the open, high, low or close when you are near one (click: strong)"],
                 ["strong", "🧲⁺", "Strong magnet: always snaps to the nearest open, high, low or close (click: off)"]];
draw.magnet = (() => { const m = Prefs.get("watch.magnet", "weak"); return m === true ? "weak" : m; })();
function buildTools() {
  const nav = $("tools");
  for (const tool of TOOLS) {
    const b = document.createElement("button"); b.textContent = tool.icon; b.title = tool.title; b.dataset.type = tool.type || "";
    b.onclick = () => { draw.use(tool.type); markTool(); };
    nav.append(b);
  }
  const magnet = document.createElement("button");
  const showMagnet = () => {
    const [, icon, title] = MAGNETS.find(([v]) => v === draw.magnet) || MAGNETS[1];
    magnet.textContent = icon; magnet.title = title + ". Hold Shift while drawing a line to keep it level.";
    magnet.classList.toggle("on", !!draw.magnet);
  };
  magnet.onclick = () => {
    const i = MAGNETS.findIndex(([v]) => v === draw.magnet);
    draw.magnet = MAGNETS[(i + 1) % MAGNETS.length][0];
    Prefs.set("watch.magnet", draw.magnet);
    showMagnet();
  };
  showMagnet(); nav.append(magnet);
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
    c.onchange = () => act(async () => { S.layers[key] = c.checked; Prefs.set("watch.layers", S.layers); S.maAt = null;
                                         fractal.setOn(S.layers.fractal); await fractal.tick(); renderFractal();
                                         await loadModelA(); await loadTrend(); await loadChain(); renderEngine(); renderLog(); refresh(); });
    l.append(c, " " + name); box.append(l);
    if (key === "fractal") {
      const gear = document.createElement("button");
      gear.className = "boxed"; gear.id = "fractalSettings"; gear.textContent = "⚙"; gear.title = "Fractal + POI settings";
      gear.onclick = () => act(() => fractal.dialog());
      box.append(gear);
    }
  }
  const ma = document.createElement("select");
  ma.id = "maSet"; ma.title = "Which of your frame sets Model A reads";
  ma.innerHTML = MA_SETS.map(([v, t]) => `<option value="${v}" ${S.maSet === v ? "selected" : ""}>${t}</option>`).join("");
  ma.onchange = () => act(async () => { S.maSet = ma.value; Prefs.set("watch.maSet", ma.value); S.maAt = null; await loadModelA(); await loadTrend(); await loadChain(); renderEngine(); renderLog(); refresh(); });
  box.append(ma);
  const tr = document.createElement("select");
  tr.id = "trendTf"; tr.title = "The frame your trend is read on (the Trend layer)";
  tr.innerHTML = TREND_TFS.map((v) => `<option value="${v}" ${S.trendTf === v ? "selected" : ""}>trend: ${v}</option>`).join("");
  tr.onchange = () => act(async () => { S.trendTf = tr.value; Prefs.set("watch.trendTf", tr.value); S.trend.at = null;
                                        await loadTrend(); await loadChain(); refresh(); });
  box.append(tr);
  const sel = document.createElement("select");
  sel.title = "Which of the engine's arrays to draw";
  sel.innerHTML = [["interval", "arrays: by visibility interval"], ["all", "arrays: every one"], ["M15", "arrays: M15 and up"],
                   ["H1", "arrays: H1 and up"], ["H4", "arrays: H4 and up"]]
    .map(([v, t]) => `<option value="${v}" ${S.arrayMode === v ? "selected" : ""}>${t}</option>`).join("");
  sel.onchange = () => { S.arrayMode = sel.value; Prefs.set("watch.arrayMode", sel.value); refresh(); };
  const iv = document.createElement("button");
  iv.className = "boxed"; iv.id = "arrayIntervals"; iv.textContent = "Intervals…";
  iv.title = "The chart timeframes each array timeframe shows on";
  iv.onclick = () => arrayIntervalsDialog();
  box.append(sel, iv);
}
function arrayIntervalsDialog() {
  const { el, dialog, row, choose } = window.ReplayUI;
  const tfs = Object.keys(SECONDS);
  const tabs = [{ name: "Intervals", build(b) {
    b.append(el("div", { class: "hint" }, "Each kind of array shows only on the chart timeframes from–to. The entry array always shows."));
    for (const tf of Object.keys(ARRAY_SHOWS)) {
      const [lo, hi] = arrayInterval(tf);
      const put = (i, v) => {
        const cur = [...arrayInterval(tf)]; cur[i] = v;
        if (tfs.indexOf(cur[0]) > tfs.indexOf(cur[1])) cur[1 - i] = v;
        S.arrayVis = { ...S.arrayVis, [tf]: cur }; Prefs.set("watch.arrayVis", S.arrayVis); refresh(); dlg.close(); arrayIntervalsDialog();
      };
      b.append(row(`${tf} arrays`, choose(lo, tfs.map((x) => [x, x]), (v) => put(0, v)), el("span", { class: "muted" }, "to"),
                   choose(hi, tfs.map((x) => [x, x]), (v) => put(1, v))));
    }
  } }];
  const footer = [el("button", { class: "boxed", onclick: () => { S.arrayVis = {}; Prefs.set("watch.arrayVis", {}); refresh(); dlg.close(); arrayIntervalsDialog(); } }, "Defaults"),
                  el("span", { class: "spacer" }), el("button", { class: "primary", onclick: () => dlg.close() }, "OK")];
  const dlg = dialog("Array visibility", tabs, footer);
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
    if (e.key === "Escape") { if (noculus.armed()) noculus.arm(null);
                              draw.use(null); draw.select(null); draw.measure = null; markTool(); draw.refresh(); return; }
    if (typing || !S.status) return;
    if ((e.key === "Delete" || e.key === "Backspace") && draw.selected) { e.preventDefault(); draw.remove(draw.selected); return; }
    if (e.altKey) { const tool = TOOLS.find((t) => t.key === e.key.toLowerCase()); if (tool) { e.preventDefault(); draw.use(tool.type); markTool(); } return; }
    if (e.key === " ") { e.preventDefault(); togglePlay(); }
    else if (e.key === "ArrowRight") { e.preventDefault(); act(async () => { stop(); await advance(e.shiftKey ? 3600 : 900 - (S.t % 900 || 0) || 900); }); }
  });
}

// ── panels ────────────────────────────────────────────────────────────────
function renderHeader() {
  const live = atLive() && S.now;
  $("when").textContent = live ? `LIVE · ${fmtTime(S.now.time)} New York` : fmtTime(S.t) + " New York";
  const last = S.bars[S.bars.length - 1];
  $("price").textContent = live && S.now.bid != null ? `${fmt(S.now.bid)} / ${fmt(S.now.ask)}` : last ? fmt(last.close) : "";
  if (!S.playing) $("play").textContent = playLabel();
  $("speed").style.display = S.status && S.status.live ? "none" : "";
}
const esc = (t) => String(t == null ? "" : t).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
function renderEngine() {
  const st = S.state, box = $("engine");
  if (!st) { box.innerHTML = `<h2>The engine</h2><div class="muted">Before the first close of the session.</div>`; return; }
  if (st.error) { box.innerHTML = `<h2>The engine at ${fmtTime(st.t)}</h2><div class="bad">${esc(st.error)}</div>`; return; }
  if (st.withheld) {
    box.innerHTML = `<h2>The engine at ${fmtTime(st.t)}</h2><div class="muted">Hidden: this session is blind. Your marks and
      trades come first, then reveal it and compare.</div>`;
    return;
  }
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
      CISD at ${fmtTime(sq.cisd)}${sq.cisd_level != null ? ` through ${fmt(sq.cisd_level)}` : ""} · protected swing ${fmt(sq.protected.wick)} (${fmtTime(sq.protected.at)})</div>`;
  }
  if (S.layers.modelA) {
    const label = (MA_SETS.find(([v]) => v === S.maSet) || ["", S.maSet])[1];
    const lv = (y) => y.entry != null ? `<div class="muted">0.705 entry ${fmt(y.entry)} · stop ${fmt(y.stop)} · TP1 ${fmt(y.tp1)} · -1 SD ${fmt(y.sd1)} · -2 SD ${fmt(y.sd2)}</div>` : "";
    const shown = maShown(), unswept = S.ma.length - shown.length;
    html += `<div class="card"><b>${esc(label)}</b>` + (shown.length ? shown.map((y) => `<div class="ma ${y.ended ? "muted" : ""}">
        <b>${esc(y.side)} · ${esc(y.ended || y.state)}</b> <span class="muted">POI ${esc(y.poi_label)} ${fmt(y.poi_near)}–${fmt(y.poi_far)}</span>
        <div>${esc(y.reason)}</div><div class="muted">C2's phase: ${esc(y.phase || "—")}${y.time_sync != null ? `; ${y.time_sync ? "in" : "outside"} your time window` : ""}${y.inducement ? `; inducement: ${esc(y.inducement)}` : ""}</div>${y.adr_used != null ? `<div class="muted">At C2's close: ${Math.round(100 * y.adr_used)}% of the ADR used; the setup ${y.size_adr.toFixed(2)} ADR; TP1 ${y.target_reach.toFixed(2)} ADR from the day's extreme</div>` : ""}${lv(y)}</div>`).join("")
      : unswept ? `<div class="muted">${unswept} C1 candidate(s) framed, none run by C2 yet ("Model A: unswept C1s" shows them).</div>`
      : `<div class="muted">Nothing framed: price isn't in premium with a POI above (or discount with one below) on ${esc(label.split(": ")[1] || "")}, or C2 would open outside the early phases (20:00-07:00 New York).</div>`) + `</div>`;
  }
  if (S.layers.chain) html += chainCard();
  const open = S.journal.find((r) => r.filled_at != null && r.filled_at <= S.t && (r.closed_at == null || r.closed_at > S.t));
  if (open) {
    const m = (S.status && S.status.management) || {}, partialDone = open.partial_at != null && open.partial_at <= S.t;
    html += `<div class="card"><b>Open trade</b>: ${esc(open.direction)} from ${fmt(open.fill)}, stop ${fmt(partialDone ? open.fill : open.stop)}, target ${fmt(open.target)}.
      <div class="muted">${m.partial_r ? `Managed: ${Math.round(100 * m.partial_fraction)}% off at ${m.partial_r}R, the rest's stop to the fill (break-even). ${partialDone ? "The partial is taken." : "No partial yet."} No trailing.`
        : `The engine doesn't manage trades: no break-even, trailing or partial close. It waits for the stop or the target;
      the dotted +1R line is where a break-even would arm.`}</div></div>`;
  }
  const cd = st.candidates;
  if (cd) {
    const without = Object.entries(cd.without || {}).map(([tf, n]) => `${n} ${tf}`).join(", ");
    const mine = S.picks[st.t];
    const tag = (v) => (mine && mine.pick === v ? "✓ " : "");
    html += `<div class="card cands"><b>Candidates</b>: ${cd.ranked.length} array(s) with a raid, CISD and intact swing behind them${without ? `; none behind ${esc(without)}` : ""}.
      <div class="hint">Ranked as the engine ranks them: the latest raid first, then the raided pool's timeframe, then the array's type. Hover to see one; mark the one you would take.</div>
      ${cd.ranked.map((c) => `<div class="cand${c.chosen ? " chosen" : ""}${mine && mine.pick === c.id ? " mine" : ""}" data-id="${esc(c.id)}">
        <span class="rk">#${c.rank}</span> ${esc(c.tf)} ${esc(c.type)} ${c.dir === "BULLISH" ? "▲" : "▼"} ${fmt(c.low)}–${fmt(c.high)}${c.chosen ? " · <b>the engine's choice</b>" : ""}
        <div class="muted">raid of ${esc(c.raid.source.replace("_", " "))} ${esc(c.raid.tf)} ${fmt(c.raid.price)}, ${c.raid.age_h} h before · CISD ${fmtTime(c.cisd)}${c.cisd_level != null ? ` through ${fmt(c.cisd_level)}` : ""}</div>
        <button class="boxed pick" data-pick="${esc(c.id)}">${tag(c.id)}Mine</button></div>`).join("")}
      <div class="row"><button class="boxed pick" data-pick="none">${tag("none")}None: no trade here</button>
        <button class="boxed pick" data-pick="other">${tag("other")}Another array</button></div>
      <textarea id="pickNote" placeholder="Why (optional): the POI you would use, the step the engine skipped">${esc(mine ? mine.note : "")}</textarea>
      ${mine ? `<div class="hint">Saved: ${esc(mine.pick === "none" ? "no trade" : mine.pick === "other" ? "another array" : "#" + (mine.picked ? mine.picked.rank : "?"))}.</div>` : ""}</div>`;
  }
  const bias = Object.entries(st.bias || {}).map(([tf, b]) => `${tf} ${b.direction === "BULLISH" ? "▲" : b.direction === "BEARISH" ? "▼" : "–"}`).join(" · ");
  html += `<div class="hint">Price against each open: ${bias}. Showing ${st.arrays.length} unfilled arrays and ${st.pools.length} untaken pools near price.</div>`;
  box.innerHTML = html;
  for (const div of box.querySelectorAll(".cand")) {
    div.onmouseenter = () => { S.hl = div.dataset.id; refresh(); };
    div.onmouseleave = () => { S.hl = null; refresh(); };
  }
  for (const b of box.querySelectorAll("button.pick")) {
    b.onclick = () => act(async () => {
      const saved = await api("/api/watch/pick", { t: st.t, pick: b.dataset.pick, note: $("pickNote").value });
      S.picks[st.t] = saved; renderEngine();
    });
  }
}
// A rest stopped at its own fill after the partial is a break-even, not a loss (Requirement 28.5).
function exitLabel(r) { return r.partial_at != null && r.exit_reason === "SL" ? "BE" : (r.exit_reason || "exit"); }
function renderLog() {
  const items = [];
  for (const r of S.journal) {
    if (r.decision !== "EXECUTE") continue;
    if (r.t <= S.t) items.push({ t: r.t, text: `${r.order_kind || ""} ${r.direction} placed @ ${fmt(r.entry)} (R:R ${r.r_ratio ? r.r_ratio.toFixed(1) : "—"})`, cls: "" });
    if (r.filled_at != null && r.filled_at <= S.t) items.push({ t: r.filled_at, text: `${r.direction} filled @ ${fmt(r.fill)}`, cls: "" });
    if (r.partial_at != null && r.partial_at <= S.t) items.push({ t: r.partial_at, text: `${Math.round(100 * r.partial_fraction)}% closed @ ${fmt(r.partial_exit)}, stop to break-even ${fmt(r.fill)}`, cls: "good" });
    if (r.closed_at != null && r.closed_at <= S.t) items.push({ t: r.closed_at, text: `${r.exit_reason ? exitLabel(r) : "closed"} ${r.net_r != null ? (r.net_r >= 0 ? "+" : "") + r.net_r.toFixed(2) + "R" : ""}`
                                                               + (r.path ? ` (best +${r.path.best_r.toFixed(2)}R at ${fmtTime(r.path.best_at)})` : ""),
                                                               cls: (r.net_r || 0) > 0 ? "good" : "bad" });
    else if (r.filled_at == null && r.expires_at != null && r.expires_at <= S.t) items.push({ t: r.expires_at, text: "order expired unfilled", cls: "muted" });
  }
  if (S.layers.fractal) {
    for (const e of fractal.events()) items.push({ t: e.t, text: `Fractal + POI: ${e.text}`, cls: e.dir === "bull" ? "good" : "bad" });
  }
  if (S.layers.modelA) {
    for (const y of maShown()) for (const [state, t, why] of y.events) {
      if (state === "FRAMED" || state === "ARMED") continue;
      items.push({ t, text: `Model A ${y.side.toLowerCase()} ${state}: ${why}`, cls: /STOPPED|MISSED|INVALID|FAILED|NO_/.test(state) ? "bad" : /TP1|SD_/.test(state) ? "good" : "" });
    }
  }
  items.sort((a, b) => b.t - a.t);
  $("log").innerHTML = items.length ? items.map((i) => `<div data-t="${i.t}" class="${i.cls}">${fmtTime(i.t)} · ${esc(i.text)}</div>`).join("")
    : `<div class="muted">No orders yet.</div>`;
  for (const div of $("log").children) if (div.dataset.t) div.onclick = () => act(() => jumpTo(Number(div.dataset.t)));
}

boot().catch((e) => say(e.message));
