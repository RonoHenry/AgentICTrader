// Drawing tools for the blind replay chart (updates 2026-10-14b and 2026-10-14c).
//
// One series primitive paints every drawing on the price pane. A drawing is plain data,
// saved with the day: { id, type, points: [{t, p}], style: {...}, ...metadata }, where t is
// New York wall seconds (the chart's time) and p a price. Its look is the type's defaults,
// then the trader's saved template for the type, then the drawing's own style.
"use strict";

(function () {
  // The x of a logical bar position. The chart maps whole bars only (a fraction comes back as 0),
  // so a time between two bar opens, such as an M1 fill on an M15 chart, sits between them.
  function logicalX(ts, logical) {
    const i = Math.floor(logical), f = logical - i;
    const a = ts.logicalToCoordinate(i);
    if (a === null) return NaN;
    if (!f) return a;
    const b = ts.logicalToCoordinate(i + 1);
    return b === null ? a : a + f * (b - a);
  }

  // Points per type; 0 is a freehand path (any number, drawn by dragging).
  const POINTS = { hline: 1, hray: 1, vline: 1, text: 1, trend: 2, ray: 2, extended: 2, arrow: 2, rect: 2, range: 2,
                   fib: 2, channel: 3, fibext: 3, long: 3, short: 3, path: 0 };
  const NAMES = { hline: "Horizontal line", hray: "Horizontal ray", vline: "Vertical line", text: "Text",
                  trend: "Trend line", ray: "Ray", extended: "Extended line", arrow: "Arrow", rect: "Box (PD array)",
                  range: "Date & price range", fib: "Fib / SD projection", channel: "Parallel channel",
                  fibext: "Trend-based fib extension", long: "Long position", short: "Short position", path: "Brush" };
  const FIB = [1, 0.786, 0.705, 0.618, 0.5, 0, -0.5, -1, -1.5, -2, -2.5, -4];
  const FIBEXT = [0, 0.618, 1, 1.272, 1.618, 2, 2.618, 3.618, 4.236];
  const BASE = { color: "", width: 1, dash: "solid", textColor: "", fontSize: 12, extendLeft: false, extendRight: false,
                 priceLabels: true, fill: "", opacity: 0.14, showMid: true, midDash: "dashed", showLabels: true,
                 showPrices: true, profit: "", loss: "", background: "" };
  const TYPE_LOOK = {
    hline: {}, hray: {}, vline: {}, text: { fontSize: 13 }, trend: {}, ray: { extendRight: true },
    extended: { extendLeft: true, extendRight: true }, arrow: { width: 2 }, rect: { extendRight: true },
    range: { opacity: 0.12 }, fib: { extendRight: true }, fibext: { extendRight: true }, channel: { opacity: 0.08 },
    long: { opacity: 0.18 }, short: { opacity: 0.18 }, path: { width: 2 },
  };
  const DASH = { solid: [], dashed: [6, 4], dotted: [2, 3] };
  const HANDLE = 5, NEAR = 6;

  const newId = () => Date.now().toString(36) + Math.random().toString(36).slice(2, 7);
  const copy = (x) => JSON.parse(JSON.stringify(x));

  function segDist(px, py, x1, y1, x2, y2) {
    const dx = x2 - x1, dy = y2 - y1, len = dx * dx + dy * dy;
    let u = len ? ((px - x1) * dx + (py - y1) * dy) / len : 0;
    u = Math.max(0, Math.min(1, u));
    return Math.hypot(px - (x1 + u * dx), py - (y1 + u * dy));
  }
  function rgba(color, a) {
    if (/^#[0-9a-f]{6}$/i.test(color)) {
      const n = parseInt(color.slice(1), 16);
      return `rgba(${n >> 16}, ${(n >> 8) & 255}, ${n & 255}, ${a})`;
    }
    return color;
  }
  // The line through (x0, y0) and (x1, y1), stretched to the pane's edges on the sides asked for.
  function stretch(x0, y0, x1, y1, left, right, width) {
    const dx = x1 - x0, dy = y1 - y0;
    if (Math.abs(dx) < 1e-9) return [x0, left ? -1e4 : y0, x1, right ? 1e4 : y1];
    const k = dy / dx;
    let a = [x0, y0], b = [x1, y1];
    const forward = dx > 0;
    if (right) b = forward ? [width, y0 + k * (width - x0)] : [0, y0 + k * (0 - x0)];
    if (left) a = forward ? [0, y0 + k * (0 - x0)] : [width, y0 + k * (width - x0)];
    return [a[0], a[1], b[0], b[1]];
  }
  function duration(seconds) {
    const s = Math.abs(seconds), d = Math.floor(s / 86400), h = Math.floor((s % 86400) / 3600), m = Math.floor((s % 3600) / 60);
    return (d ? d + "d " : "") + (h ? h + "h " : "") + (m || (!d && !h) ? m + "m" : "");
  }

  class Drawings {
    // opts: { container, timeline: {toLogical, toTime, barAt}, digits(), palette(), template(type),
    //         onChange(items), onSelect(item), onEdit(item), onContext(item, x, y), onPick(at), picking(), onError(text) }
    constructor(chart, series, opts) {
      this.chart = chart; this.series = series; this.opts = opts;
      this.items = []; this.selected = null; this.tool = null; this.pending = null; this.mouse = null;
      this.drag = null; this.measure = null; this.magnet = true; this.hidden = false; this.keepTool = false;
      this.history = [];
      this.requestUpdate = () => {};
      const owner = this;
      series.attachPrimitive({
        attached(param) { owner.requestUpdate = param.requestUpdate; },
        detached() {},
        updateAllViews() {},
        paneViews() {
          return [{ zOrder: () => "top", renderer: () => ({
            draw: (target) => target.useMediaCoordinateSpace(({ context, mediaSize }) => owner.paint(context, mediaSize)),
          }) }];
        },
        priceAxisViews() { return owner.axisViews(); },
      });
      this.bind(opts.container);
    }

    // ── data ──────────────────────────────────────────────────────────────
    load(items) {
      this.items = copy(items || []);
      this.selected = null; this.history = []; this.measure = null;
      this.cancel();
    }
    snapshot() { this.history.push(JSON.stringify(this.items)); if (this.history.length > 200) this.history.shift(); }
    changed() { this.refresh(); this.opts.onChange(copy(this.items.map(({ status, ...d }) => d))); }
    undo() {
      const last = this.history.pop();
      if (last === undefined) return;
      const id = this.selected && this.selected.id;
      this.items = JSON.parse(last);
      this.selected = this.items.find((d) => d.id === id) || null;
      this.opts.onSelect(this.selected);
      this.changed();
    }
    find(id) { return this.items.find((d) => d.id === id) || null; }
    update(item, change, snapshot = true) { if (snapshot) this.snapshot(); Object.assign(item, change); this.changed(); }
    setStyle(item, patch) { item.style = { ...(item.style || {}), ...patch }; this.changed(); }
    remove(item) {
      if (!item) return;
      this.snapshot();
      this.items = this.items.filter((d) => d !== item);
      if (this.selected === item) { this.selected = null; this.opts.onSelect(null); }
      this.changed();
    }
    clone(item) {
      const d = { ...copy(item), id: newId() };
      delete d.status;
      this.snapshot(); this.items.push(d); this.select(d); this.changed();
      return d;
    }
    toggle(item, key) { this.update(item, { [key]: !item[key] }); if (key === "hidden" && item.hidden && this.selected === item) this.select(null); }
    clearAll() {
      if (!this.items.length) return;
      this.snapshot(); this.items = []; this.selected = null; this.opts.onSelect(null); this.changed();
    }
    refresh() { this.requestUpdate(); }

    // ── tools ─────────────────────────────────────────────────────────────
    use(type) {
      this.tool = type || null;
      this.pending = type ? { type, points: [] } : null;
      if (type) this.select(null);
      this.opts.container.style.cursor = type ? "crosshair" : "";
      this.refresh();
    }
    cancel() { this.use(null); }
    select(item) { this.selected = item; this.opts.onSelect(item); this.refresh(); }
    create(type, points) {
      const d = { id: newId(), type, points };
      if (type === "rect") d.direction = "neutral";
      return d;
    }
    look(d) {
      const legacy = {};
      if (d.color) legacy.color = d.color;
      if (d.extend !== undefined) legacy.extendRight = !!d.extend;
      if (d.mid !== undefined) legacy.showMid = !!d.mid;
      return { ...BASE, ...TYPE_LOOK[d.type], ...(this.opts.template(d.type) || {}), ...legacy, ...(d.style || {}) };
    }
    levelsOf(d) {
      const t = this.opts.template(d.type) || {};
      const raw = d.levels && d.levels.length ? d.levels : t.levels && t.levels.length ? t.levels : d.type === "fibext" ? FIBEXT : FIB;
      return raw.map((l) => (typeof l === "number" ? { value: l } : l));
    }
    colorOf(d, look, pal) {
      if (look.color) return look.color;
      if (d.type === "rect") return d.direction === "bullish" ? pal.up : d.direction === "bearish" ? pal.bad : pal.accent;
      if (d.type === "fib" || d.type === "fibext") return pal.muted;
      if (d.type === "hline" || d.type === "hray" || d.type === "range") return pal.accent;
      return pal.ink;
    }

    // ── coordinates ───────────────────────────────────────────────────────
    X(t) { return logicalX(this.chart.timeScale(), this.opts.timeline.toLogical(t)); }
    Y(p) { const y = this.series.priceToCoordinate(p); return y === null ? NaN : y; }
    round(p) { const f = Math.pow(10, this.opts.digits()); return Math.round(p * f) / f; }
    at(x, y, snap) {
      const logical = this.chart.timeScale().coordinateToLogical(x);
      if (logical === null) return null;
      const index = Math.round(logical);
      let p = this.series.coordinateToPrice(y);
      if (p === null) return null;
      if (snap && this.magnet) {
        const bar = this.opts.timeline.barAt(index);
        if (bar) {
          let best = null;
          for (const v of [bar.open, bar.high, bar.low, bar.close]) {
            const dist = Math.abs(this.Y(v) - y);
            if (dist < 14 && (!best || dist < best.dist)) best = { v, dist };
          }
          if (best) p = best.v;
        }
      }
      return { t: this.opts.timeline.toTime(index), p: this.round(p), x, y, index };
    }

    // ── geometry, shared by painting and hit tests ────────────────────────
    shape(d, width) {
      const L = this.look(d);
      const pts = d.points.map((q) => ({ x: this.X(q.t), y: this.Y(q.p) }));
      const p = pts[0];
      switch (d.type) {
        case "hline": return { lines: [[0, p.y, width, p.y]], handles: [{ x: 40, y: p.y }] };
        case "hray": return { lines: [[p.x, p.y, width, p.y]], handles: [p] };
        case "vline": return { lines: [[p.x, -1e4, p.x, 1e4]], handles: [{ x: p.x, y: 40 }] };
        case "text": return { text: p, handles: [p] };
        case "trend": case "ray": case "extended": case "arrow":
          return { lines: [stretch(p.x, p.y, pts[1].x, pts[1].y, L.extendLeft && d.type !== "arrow", L.extendRight && d.type !== "arrow", width)],
                   handles: pts };
        case "path": return { path: pts, handles: [pts[0], pts[pts.length - 1]] };
        case "rect": case "range": {
          const x1 = L.extendLeft ? 0 : Math.min(pts[0].x, pts[1].x);
          const x2 = d.type === "rect" && L.extendRight ? width : Math.max(pts[0].x, pts[1].x);
          return { box: [x1, Math.min(pts[0].y, pts[1].y), x2, Math.max(pts[0].y, pts[1].y)], handles: pts };
        }
        case "channel": {
          const [a, b, c] = pts;
          const k = Math.abs(b.x - a.x) < 1e-9 ? 0 : (b.y - a.y) / (b.x - a.x);
          const shift = c.y - (a.y + k * (c.x - a.x));
          const base = stretch(a.x, a.y, b.x, b.y, L.extendLeft, L.extendRight, width);
          const other = [base[0], base[1] + shift, base[2], base[3] + shift];
          return { lines: [base, other], poly: [[base[0], base[1]], [base[2], base[3]], [other[2], other[3]], [other[0], other[1]]],
                   handles: [a, b, { x: c.x, y: a.y + k * (c.x - a.x) + shift }] };
        }
        case "fib": case "fibext": {
          const levels = this.levelsOf(d).filter((l) => l.visible !== false);
          let price, x1, x2;
          if (d.type === "fib") {
            const [a, b] = d.points;
            price = (v) => b.p + (a.p - b.p) * v;
            x1 = Math.min(pts[0].x, pts[1].x); x2 = Math.max(pts[0].x, pts[1].x);
          } else {
            const [a, b, c] = d.points;
            price = (v) => c.p + (b.p - a.p) * v;
            x1 = pts[2].x; x2 = pts[2].x + Math.max(40, Math.abs(pts[1].x - pts[0].x));
          }
          if (L.extendRight) x2 = width;
          if (L.extendLeft) x1 = 0;
          const rows = levels.map((l) => ({ ...l, p: price(l.value), y: this.Y(price(l.value)) }));
          return { levels: rows, x1, x2, lines: rows.map((r) => [x1, r.y, x2, r.y]), handles: pts };
        }
        case "long": case "short": {
          const x1 = pts[0].x;
          let x2 = Math.max(pts[1].x, pts[2].x);
          if (!(x2 > x1 + 4)) x2 = x1 + 160;
          if (L.extendRight) x2 = width;
          return { entry: pts[0].y, stop: pts[1].y, target: pts[2].y, x1, x2,
                   handles: [{ x: x1, y: pts[0].y }, { x: x1, y: pts[1].y }, { x: x2, y: pts[2].y }] };
        }
      }
      return { handles: [] };
    }

    hit(x, y, width) {
      for (let i = this.items.length - 1; i >= 0; i--) {
        const d = this.items[i];
        if (d.hidden) continue;
        const s = this.shape(d, width);
        if (d === this.selected && !d.locked) {
          const h = s.handles.findIndex((q) => Math.hypot(q.x - x, q.y - y) <= HANDLE + 3);
          if (h >= 0) return { item: d, handle: h };
        }
        if (s.lines && s.lines.some(([x1, y1, x2, y2]) => segDist(x, y, x1, y1, x2, y2) <= NEAR)) return { item: d, handle: -1 };
        if (s.path && s.path.some((q, k) => k && segDist(x, y, s.path[k - 1].x, s.path[k - 1].y, q.x, q.y) <= NEAR)) return { item: d, handle: -1 };
        if (s.box) {
          const [x1, y1, x2, y2] = s.box;
          if (x >= x1 - NEAR && x <= x2 + NEAR && y >= y1 - NEAR && y <= y2 + NEAR) return { item: d, handle: -1 };
        }
        if (s.poly) {
          const ys = s.poly.map((q) => q[1]), xs = s.poly.map((q) => q[0]);
          if (x >= Math.min(...xs) && x <= Math.max(...xs)) {
            const t = (x - s.lines[0][0]) / ((s.lines[0][2] - s.lines[0][0]) || 1);
            const y1 = s.lines[0][1] + t * (s.lines[0][3] - s.lines[0][1]), y2 = s.lines[1][1] + t * (s.lines[1][3] - s.lines[1][1]);
            if (y >= Math.min(y1, y2) && y <= Math.max(y1, y2)) return { item: d, handle: -1 };
            void ys;
          }
        }
        if (s.entry !== undefined) {
          const top = Math.min(s.stop, s.target, s.entry), bottom = Math.max(s.stop, s.target, s.entry);
          if (x >= s.x1 && x <= s.x2 && y >= top && y <= bottom) return { item: d, handle: -1 };
        }
        if (s.text) {
          const w = 8 * Math.max(4, (d.text || "").length);
          if (x >= s.text.x - 4 && x <= s.text.x + w && y >= s.text.y - 18 && y <= s.text.y + 4) return { item: d, handle: -1 };
        }
      }
      return null;
    }

    // ── painting ──────────────────────────────────────────────────────────
    paint(ctx, size) {
      const pal = this.opts.palette();
      if (!this.hidden) {
        const preview = this.previewItem();
        for (const d of preview ? [...this.items, preview] : this.items) {
          if (!d.hidden) this.paintOne(ctx, size, d, pal, d === this.selected);
        }
      }
      if (this.measure) this.paintMeasure(ctx, pal);
    }
    previewItem() {
      if (!this.pending || !this.mouse) return null;
      const points = [...this.pending.points, { t: this.mouse.t, p: this.mouse.p }];
      if (this.pending.type === "path") return points.length > 1 ? { ...this.create("path", this.pending.points), id: "preview" } : null;
      while (points.length < POINTS[this.pending.type]) points.push(points[points.length - 1]);
      return { ...this.create(this.pending.type, points), id: "preview" };
    }

    paintOne(ctx, size, d, pal, selected) {
      const L = this.look(d);
      const s = this.shape(d, size.width);
      const color = this.colorOf(d, L, pal);
      const fmt = (p) => p.toFixed(this.opts.digits());
      ctx.save();
      ctx.lineWidth = L.width + (selected ? 1 : 0);
      ctx.strokeStyle = color; ctx.fillStyle = color;
      ctx.font = `${L.fontSize}px system-ui, sans-serif`;
      ctx.textBaseline = "bottom";
      const dash = DASH[L.dash] || [];
      const line = (x1, y1, x2, y2, pattern) => {
        ctx.setLineDash(pattern || dash); ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke(); ctx.setLineDash([]);
      };
      const label = (text, x, y, align, tint) => {
        if (!text || !L.showLabels) return;
        ctx.textAlign = align || "left"; ctx.fillStyle = tint || L.textColor || color; ctx.fillText(text, x, y);
      };
      switch (d.type) {
        case "hline": case "hray": case "vline": case "trend": case "ray": case "extended": {
          for (const l of s.lines) line(...l);
          if (d.label) {
            const [x1, y1] = s.lines[0];
            if (d.type === "vline") label(d.label, x1 + 4, 16);
            else label(d.label, Math.max(Math.min(x1, s.lines[0][2]), 0) + 6, (d.type === "hline" || d.type === "hray" ? y1 : Math.min(y1, s.lines[0][3])) - 3);
          }
          break;
        }
        case "arrow": {
          const [x1, y1, x2, y2] = s.lines[0];
          line(x1, y1, x2, y2);
          const a = Math.atan2(y2 - y1, x2 - x1), head = 8 + 2 * L.width;
          ctx.beginPath(); ctx.moveTo(x2, y2);
          ctx.lineTo(x2 - head * Math.cos(a - 0.45), y2 - head * Math.sin(a - 0.45));
          ctx.lineTo(x2 - head * Math.cos(a + 0.45), y2 - head * Math.sin(a + 0.45));
          ctx.closePath(); ctx.fill();
          label(d.label, x1 + 4, y1 - 3);
          break;
        }
        case "path": {
          ctx.setLineDash(dash); ctx.lineJoin = "round"; ctx.lineCap = "round";
          ctx.beginPath(); s.path.forEach((q, k) => (k ? ctx.lineTo(q.x, q.y) : ctx.moveTo(q.x, q.y))); ctx.stroke();
          ctx.setLineDash([]);
          break;
        }
        case "rect": {
          const [x1, y1, x2, y2] = s.box;
          ctx.fillStyle = rgba(L.fill || color, L.opacity);
          ctx.fillRect(x1, y1, x2 - x1, y2 - y1);
          ctx.setLineDash(dash); ctx.strokeRect(x1, y1, x2 - x1, y2 - y1); ctx.setLineDash([]);
          if (L.showMid) line(x1, (y1 + y2) / 2, x2, (y1 + y2) / 2, DASH[L.midDash] || DASH.dashed);
          label([d.tf, d.kind, d.label].filter(Boolean).join(" "), Math.max(x1, 0) + 4, y1 - 3);
          break;
        }
        case "range": {
          const [x1, y1, x2, y2] = s.box;
          ctx.fillStyle = rgba(L.fill || color, L.opacity); ctx.fillRect(x1, y1, x2 - x1, y2 - y1);
          const [a, b] = d.points;
          const dp = b.p - a.p, bars = Math.round(this.opts.timeline.toLogical(b.t) - this.opts.timeline.toLogical(a.t));
          line((x1 + x2) / 2, y1, (x1 + x2) / 2, y2); line(x1, (y1 + y2) / 2, x2, (y1 + y2) / 2);
          ctx.font = "12px system-ui, sans-serif";
          label(`${dp >= 0 ? "+" : ""}${fmt(dp)} (${((dp / a.p) * 100).toFixed(2)}%)  ${bars} bars, ${duration(b.t - a.t)}`,
                (x1 + x2) / 2, (dp >= 0 ? y1 : y2 + 16) - 3, "center");
          break;
        }
        case "channel": {
          ctx.fillStyle = rgba(L.fill || color, L.opacity);
          ctx.beginPath(); s.poly.forEach((q, k) => (k ? ctx.lineTo(q[0], q[1]) : ctx.moveTo(q[0], q[1]))); ctx.closePath(); ctx.fill();
          for (const l of s.lines) line(...l);
          label(d.label, Math.max(s.lines[0][0], 0) + 6, s.lines[0][1] - 3);
          break;
        }
        case "fib": case "fibext": {
          for (const r of s.levels) {
            const tint = r.color || color;
            ctx.strokeStyle = tint;
            line(s.x1, r.y, s.x2, r.y, r.value === 0 || r.value === 1 ? [] : dash.length ? dash : [4, 3]);
            const text = [L.showLabels ? String(r.value) : "", L.showPrices ? fmt(r.p) : ""].filter(Boolean).join("  ");
            if (text) { ctx.textAlign = "left"; ctx.fillStyle = r.color || L.textColor || color; ctx.fillText(text, Math.max(s.x1, 0) + 4, r.y - 2); }
          }
          ctx.strokeStyle = color;
          const anchors = d.points.map((q) => [this.X(q.t), this.Y(q.p)]);
          for (let k = 1; k < anchors.length; k++) line(...anchors[k - 1], ...anchors[k], [2, 3]);
          break;
        }
        case "long": case "short": {
          const { x1, x2, entry, stop, target } = s;
          ctx.fillStyle = rgba(L.profit || pal.up, L.opacity);
          ctx.fillRect(x1, Math.min(entry, target), x2 - x1, Math.abs(target - entry));
          ctx.fillStyle = rgba(L.loss || pal.bad, L.opacity);
          ctx.fillRect(x1, Math.min(entry, stop), x2 - x1, Math.abs(stop - entry));
          ctx.strokeStyle = L.color || pal.ink;
          line(x1, entry, x2, entry, []);
          const [e, st, tg] = d.points.map((q) => q.p);
          const risk = Math.abs(e - st), rr = risk ? Math.abs(tg - e) / risk : 0;
          label(`${d.type === "long" ? "Long" : "Short"} ${fmt(e)}  R:R ${rr.toFixed(2)}${d.status ? "  · " + d.status : ""}`, x1 + 4, entry - 3, "left", pal.ink);
          label(`Target ${fmt(tg)} (${fmt(Math.abs(tg - e))})`, x1 + 4, d.type === "long" ? target - 3 : target + 15, "left", L.profit || pal.up);
          label(`Stop ${fmt(st)} (${fmt(risk)})`, x1 + 4, d.type === "long" ? stop + 15 : stop - 3, "left", L.loss || pal.bad);
          break;
        }
        case "text": {
          const text = d.text || "";
          const w = ctx.measureText(text).width + 8;
          ctx.fillStyle = L.background || rgba(pal.panel, 0.85);
          ctx.fillRect(s.text.x - 4, s.text.y - L.fontSize - 5, w, L.fontSize + 7);
          ctx.textAlign = "left"; ctx.fillStyle = L.textColor || color; ctx.fillText(text, s.text.x, s.text.y - 2);
          break;
        }
      }
      if (selected) {
        ctx.fillStyle = pal.panel; ctx.strokeStyle = d.locked ? pal.muted : pal.accent; ctx.lineWidth = 1.5; ctx.setLineDash([]);
        for (const q of s.handles) { ctx.beginPath(); ctx.rect(q.x - HANDLE, q.y - HANDLE, HANDLE * 2, HANDLE * 2); ctx.fill(); ctx.stroke(); }
      }
      ctx.restore();
    }

    paintMeasure(ctx, pal) {
      const { a, b } = this.measure;
      const x1 = this.X(a.t), y1 = this.Y(a.p), x2 = this.X(b.t), y2 = this.Y(b.p);
      const up = b.p >= a.p, tint = up ? pal.accent : pal.bad;
      ctx.save();
      ctx.fillStyle = rgba(tint, 0.15); ctx.strokeStyle = tint;
      ctx.fillRect(Math.min(x1, x2), Math.min(y1, y2), Math.abs(x2 - x1), Math.abs(y2 - y1));
      const dp = b.p - a.p, bars = Math.round(this.opts.timeline.toLogical(b.t) - this.opts.timeline.toLogical(a.t));
      const text = `${dp >= 0 ? "+" : ""}${dp.toFixed(this.opts.digits())} (${((dp / a.p) * 100).toFixed(2)}%)  ${bars} bars, ${duration(b.t - a.t)}`;
      ctx.font = "12px system-ui, sans-serif";
      const w = ctx.measureText(text).width + 12, bx = (x1 + x2) / 2 - w / 2, by = up ? Math.min(y1, y2) - 26 : Math.max(y1, y2) + 6;
      ctx.fillStyle = tint; ctx.fillRect(bx, by, w, 20);
      ctx.fillStyle = "#ffffff"; ctx.textAlign = "center"; ctx.textBaseline = "middle"; ctx.fillText(text, bx + w / 2, by + 10);
      ctx.restore();
    }

    axisViews() {
      const views = [], pal = this.opts.palette();
      const add = (p, color) => views.push({
        coordinate: () => this.Y(p), text: () => p.toFixed(this.opts.digits()), textColor: () => "#ffffff",
        backColor: () => color, visible: () => Number.isFinite(this.Y(p)), tickVisible: () => true,
      });
      if (this.hidden) return views;
      for (const d of this.items) {
        if (d.hidden) continue;
        const L = this.look(d);
        if ((d.type === "hline" || d.type === "hray") && L.priceLabels) add(d.points[0].p, this.colorOf(d, L, pal));
      }
      const s = this.selected;
      if (s && !s.hidden && this.look(s).priceLabels) {
        if (s.type === "long" || s.type === "short") { add(s.points[0].p, pal.ink); add(s.points[1].p, pal.bad); add(s.points[2].p, pal.up); }
        if (s.type === "rect" || s.type === "range") { const c = this.colorOf(s, this.look(s), pal); add(s.points[0].p, c); add(s.points[1].p, c); }
      }
      return views;
    }

    // ── the pointer ───────────────────────────────────────────────────────
    bind(el) {
      const local = (e) => { const r = el.getBoundingClientRect(); return { x: e.clientX - r.left, y: e.clientY - r.top }; };
      const paneWidth = () => this.chart.timeScale().width();
      const freeze = (on) => this.chart.applyOptions({ handleScroll: !on, handleScale: !on });
      el.addEventListener("mousedown", (e) => {
        if (e.button !== 0) return;
        const { x, y } = local(e);
        if (x > paneWidth()) return;                                   // the price scale
        if (this.measure && this.measure.done) { this.measure = null; this.refresh(); }
        const stop = () => { e.stopPropagation(); e.preventDefault(); };
        if (this.opts.picking && this.opts.picking()) {
          const at = this.at(x, y, true); if (at) this.opts.onPick(at); stop(); return;
        }
        if (e.shiftKey && !this.pending) {                             // measure, as TradingView: Shift and drag
          const at = this.at(x, y, false);
          if (at) { this.measure = { a: at, b: at, done: false }; freeze(true); stop(); this.refresh(); }
          return;
        }
        if (this.pending) {
          const at = this.at(x, y, true);
          if (!at) return;
          stop();
          if (this.pending.type === "path") { this.pending.points = [{ t: at.t, p: at.p }]; this.pending.drawing = true; freeze(true); return; }
          this.pending.points.push({ t: at.t, p: at.p });
          if (this.pending.points.length === POINTS[this.pending.type]) this.finish();
          this.refresh();
          return;
        }
        const hit = this.hit(x, y, paneWidth());
        if (!hit) { if (this.selected) this.select(null); return; }
        if (hit.item !== this.selected) this.select(hit.item);
        stop();
        if (hit.item.locked) return;
        this.snapshot();
        this.drag = { item: hit.item, handle: hit.handle, start: this.at(x, y, false), points: copy(hit.item.points), moved: false };
        freeze(true);
      }, true);
      el.addEventListener("mousemove", (e) => {
        const { x, y } = local(e);
        if (this.measure && !this.measure.done) { const at = this.at(x, y, false); if (at) this.measure.b = at; this.refresh(); return; }
        if (this.pending && this.pending.drawing) {
          const at = this.at(x, y, false), last = this.pending.points[this.pending.points.length - 1];
          if (at && Math.hypot(this.X(last.t) - x, this.Y(last.p) - y) >= 3 && this.pending.points.length < 400) {
            this.pending.points.push({ t: at.t, p: at.p }); this.refresh();
          }
          return;
        }
        const at = this.at(x, y, !!this.pending || (this.drag && this.drag.handle >= 0));
        this.mouse = at;
        if (this.drag && at) { this.dragTo(at, x); return; }
        if (this.pending) { this.refresh(); return; }
        if (!(this.opts.picking && this.opts.picking())) el.style.cursor = this.hit(x, y, paneWidth()) ? "pointer" : "";
      }, true);
      window.addEventListener("mouseup", () => {
        if (this.measure && !this.measure.done) { this.measure.done = true; freeze(false); this.refresh(); return; }
        if (this.pending && this.pending.drawing) {
          freeze(false); this.pending.drawing = false;
          if (this.pending.points.length > 1) this.finish(); else this.pending.points = [];
          return;
        }
        if (!this.drag) return;
        const moved = this.drag.moved;
        this.drag = null; freeze(false);
        if (moved) this.changed(); else this.history.pop();
      });
      el.addEventListener("dblclick", (e) => {
        const { x, y } = local(e);
        const hit = this.hit(x, y, paneWidth());
        if (hit) { e.preventDefault(); e.stopPropagation(); this.opts.onEdit(hit.item); }
      }, true);
      el.addEventListener("contextmenu", (e) => {
        const { x, y } = local(e);
        e.preventDefault();
        if (this.pending) { this.cancel(); return; }
        const hit = this.hit(x, y, paneWidth());
        if (hit) this.select(hit.item);
        this.opts.onContext(hit ? hit.item : null, e.clientX, e.clientY);
      }, true);
      el.addEventListener("mouseleave", () => { this.mouse = null; if (this.pending) this.refresh(); });
    }

    dragTo(at, x) {
      const { item, handle, start, points } = this.drag;
      this.drag.moved = true;
      if (handle >= 0) {
        const q = item.points[handle];
        if (item.type === "hline") q.p = at.p;
        else if ((item.type === "long" || item.type === "short") && handle < 2) q.p = at.p;
        else if (item.type === "channel" && handle === 2) { q.t = at.t; q.p = at.p; }
        else if (item.type === "path") { const dt = at.t - q.t, dp = at.p - q.p; item.points = item.points.map((r) => ({ t: r.t + dt, p: this.round(r.p + dp) })); }
        else { q.t = at.t; q.p = at.p; }
      } else {
        const ts = this.chart.timeScale(), tl = this.opts.timeline;
        const shift = Math.round(ts.coordinateToLogical(x) - ts.coordinateToLogical(this.X(start.t)));
        const dp = at.p - start.p;
        item.points = points.map((q) => ({ t: tl.toTime(Math.round(tl.toLogical(q.t)) + shift), p: this.round(q.p + dp) }));
      }
      this.refresh();
    }

    finish() {
      const p = this.pending;
      const d = this.create(p.type, p.points);
      if (d.type === "text") d.text = "Text";                       // edited in its settings, opened below
      if (d.type === "long" || d.type === "short") {
        const [e, s, t] = d.points.map((q) => q.p);
        const ok = d.type === "long" ? s < e && t > e : s > e && t < e;
        if (!ok) { this.rearm(); this.opts.onError(`A ${d.type}: the stop ${d.type === "long" ? "below" : "above"} the entry, the target beyond it.`); return; }
      }
      this.snapshot();
      this.items.push(d);
      this.rearm();
      if (!this.keepTool || d.type === "text") this.select(d);
      this.changed();
      if (d.type === "text") setTimeout(() => this.opts.onEdit(d, "Text"), 0);
    }
    rearm() { if (this.keepTool && this.tool) this.pending = { type: this.tool, points: [] }; else this.cancel(); this.refresh(); }
  }

  window.Drawings = Drawings;
  window.logicalX = logicalX;
  window.DRAWING_POINTS = POINTS;
  window.DRAWING_NAMES = NAMES;
  window.FIB_LEVELS = FIB;
  window.FIBEXT_LEVELS = FIBEXT;
})();
