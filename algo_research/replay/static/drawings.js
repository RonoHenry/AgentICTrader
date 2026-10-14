// Drawing tools for the blind replay chart (update 2026-10-14b).
//
// One series primitive paints every drawing on the price pane. A drawing is plain data,
// saved with the day: { id, type, points: [{t, p}], ...options }, where t is New York wall
// seconds (the chart's time) and p a price. Tools: horizontal line and ray, vertical line,
// trend line, box (a PD array, with its 50% line), fib/SD projection, long and short
// position, text. Select a drawing to edit it; drag its handles or its body to move it.
"use strict";

(function () {
  const POINTS = { hline: 1, hray: 1, vline: 1, text: 1, trend: 2, rect: 2, fib: 2, long: 3, short: 3 };
  const FIB_LEVELS = [1, 0.786, 0.705, 0.618, 0.5, 0, -0.5, -1, -1.5, -2, -2.5, -4];
  const HANDLE = 5;
  const NEAR = 6;

  function newId() {
    return Date.now().toString(36) + Math.random().toString(36).slice(2, 7);
  }

  function segDist(px, py, x1, y1, x2, y2) {
    const dx = x2 - x1, dy = y2 - y1;
    const len = dx * dx + dy * dy;
    let u = len ? ((px - x1) * dx + (py - y1) * dy) / len : 0;
    u = Math.max(0, Math.min(1, u));
    return Math.hypot(px - (x1 + u * dx), py - (y1 + u * dy));
  }

  function alpha(color, a) {
    if (/^#[0-9a-f]{6}$/i.test(color)) {
      const n = parseInt(color.slice(1), 16);
      return `rgba(${n >> 16}, ${(n >> 8) & 255}, ${n & 255}, ${a})`;
    }
    return color;
  }

  class Drawings {
    // opts: { container, timeline: {toLogical(t), toTime(l), barAt(l)}, digits(), palette(),
    //         onChange(items), onSelect(item), onPick(point) }
    constructor(chart, series, opts) {
      this.chart = chart;
      this.series = series;
      this.opts = opts;
      this.items = [];
      this.selected = null;
      this.tool = null;
      this.pending = null;     // the drawing being placed: its points so far
      this.mouse = null;       // the last pointer position on the chart, as {t, p, x, y}
      this.drag = null;
      this.magnet = true;
      this.hidden = false;
      this.history = [];
      this.requestUpdate = () => {};
      const owner = this;
      this.primitive = {
        attached(param) { owner.requestUpdate = param.requestUpdate; },
        detached() {},
        updateAllViews() {},
        paneViews() {
          return [{
            zOrder: () => "top",
            renderer: () => ({
              draw: (target) => target.useMediaCoordinateSpace(({ context, mediaSize }) => owner.paint(context, mediaSize)),
            }),
          }];
        },
        priceAxisViews() { return owner.axisViews(); },
      };
      series.attachPrimitive(this.primitive);
      this.bind(opts.container);
    }

    // ── data ──────────────────────────────────────────────────────────────
    load(items) {
      this.items = (items || []).map((d) => JSON.parse(JSON.stringify(d)));
      this.selected = null;
      this.history = [];
      this.cancel();
      this.refresh();
    }
    snapshot() {
      this.history.push(JSON.stringify(this.items));
      if (this.history.length > 100) this.history.shift();
    }
    changed() {
      this.refresh();
      this.opts.onChange(this.items.map((d) => JSON.parse(JSON.stringify(d))));
    }
    undo() {
      const last = this.history.pop();
      if (last === undefined) return;
      const selectedId = this.selected && this.selected.id;
      this.items = JSON.parse(last);
      this.selected = this.items.find((d) => d.id === selectedId) || null;
      this.opts.onSelect(this.selected);
      this.changed();
    }
    remove(item) {
      if (!item) return;
      this.snapshot();
      this.items = this.items.filter((d) => d !== item);
      if (this.selected === item) { this.selected = null; this.opts.onSelect(null); }
      this.changed();
    }
    update(item, change) {
      this.snapshot();
      Object.assign(item, change);
      this.changed();
    }
    clearAll() {
      if (!this.items.length) return;
      this.snapshot();
      this.items = [];
      this.selected = null;
      this.opts.onSelect(null);
      this.changed();
    }
    refresh() { this.requestUpdate(); }

    // ── tools ─────────────────────────────────────────────────────────────
    use(type) {
      this.cancel();
      this.tool = type;
      this.pending = type ? { type, points: [] } : null;
      this.select(null);
      this.opts.container.style.cursor = type ? "crosshair" : "";
    }
    cancel() {
      this.tool = null;
      this.pending = null;
      this.opts.container.style.cursor = "";
      this.refresh();
    }
    select(item) {
      this.selected = item;
      this.opts.onSelect(item);
      this.refresh();
    }
    defaults(type, points) {
      const d = { id: newId(), type, points };
      if (type === "rect") Object.assign(d, { mid: true, extend: true, direction: "neutral" });
      if (type === "fib") Object.assign(d, { levels: FIB_LEVELS.slice(), extend: true });
      if (type === "hline" || type === "hray") d.color = this.opts.palette().accent;
      if (type === "trend" || type === "vline") d.color = this.opts.palette().ink;
      return d;
    }

    // ── coordinates ───────────────────────────────────────────────────────
    X(t) {
      const x = this.chart.timeScale().logicalToCoordinate(this.opts.timeline.toLogical(t));
      return x === null ? NaN : x;
    }
    Y(p) {
      const y = this.series.priceToCoordinate(p);
      return y === null ? NaN : y;
    }
    at(x, y, snap) {
      const ts = this.chart.timeScale();
      const logical = ts.coordinateToLogical(x);
      if (logical === null) return null;
      const index = Math.round(logical);
      const t = this.opts.timeline.toTime(index);
      let p = this.series.coordinateToPrice(y);
      if (p === null) return null;
      if (snap && this.magnet) {
        const bar = this.opts.timeline.barAt(index);
        if (bar) {
          let best = null;
          for (const v of [bar.open, bar.high, bar.low, bar.close]) {
            const d = Math.abs(this.Y(v) - y);
            if (d < 14 && (!best || d < best.d)) best = { v, d };
          }
          if (best) p = best.v;
        }
      }
      const f = Math.pow(10, this.opts.digits());
      return { t, p: Math.round(p * f) / f, x, y };
    }

    // ── geometry, shared by painting and hit tests ────────────────────────
    shape(d, width) {
      const pts = d.points.map((q) => ({ x: this.X(q.t), y: this.Y(q.p) }));
      const right = width;
      switch (d.type) {
        case "hline": return { lines: [[0, pts[0].y, right, pts[0].y]], handles: [{ x: 40, y: pts[0].y }] };
        case "hray": return { lines: [[pts[0].x, pts[0].y, right, pts[0].y]], handles: [pts[0]] };
        case "vline": return { lines: [[pts[0].x, 0, pts[0].x, 10000]], handles: [{ x: pts[0].x, y: 40 }] };
        case "text": return { text: pts[0], handles: [pts[0]] };
        case "trend": return { lines: [[pts[0].x, pts[0].y, pts[1].x, pts[1].y]], handles: pts };
        case "rect": {
          const x1 = Math.min(pts[0].x, pts[1].x);
          const x2 = d.extend ? right : Math.max(pts[0].x, pts[1].x);
          const y1 = Math.min(pts[0].y, pts[1].y), y2 = Math.max(pts[0].y, pts[1].y);
          return { box: [x1, y1, x2, y2], handles: pts };
        }
        case "fib": {
          const [a, b] = d.points;
          const x1 = Math.min(pts[0].x, pts[1].x);
          const x2 = d.extend ? right : Math.max(pts[0].x, pts[1].x);
          const levels = (d.levels && d.levels.length ? d.levels : FIB_LEVELS)
            .map((l) => ({ l, p: b.p + (a.p - b.p) * l })).map((v) => ({ ...v, y: this.Y(v.p) }));
          return { levels, x1, x2, lines: levels.map((v) => [x1, v.y, x2, v.y]), handles: pts };
        }
        case "long": case "short": {
          const x1 = pts[0].x;
          let x2 = Math.max(pts[1].x, pts[2].x);
          if (!(x2 > x1 + 4)) x2 = x1 + 160;
          if (d.extend) x2 = right;
          return { entry: pts[0].y, stop: pts[1].y, target: pts[2].y, x1, x2,
                   handles: [{ x: x1, y: pts[0].y }, { x: x1, y: pts[1].y }, { x: x2, y: pts[2].y }] };
        }
      }
      return { handles: [] };
    }

    hit(x, y, width) {
      for (let i = this.items.length - 1; i >= 0; i--) {
        const d = this.items[i];
        const s = this.shape(d, width);
        if (d === this.selected) {
          const h = s.handles.findIndex((q) => Math.hypot(q.x - x, q.y - y) <= HANDLE + 3);
          if (h >= 0) return { item: d, handle: h };
        }
        if (s.lines && s.lines.some(([x1, y1, x2, y2]) => segDist(x, y, x1, y1, x2, y2) <= NEAR)) return { item: d, handle: -1 };
        if (s.box) {
          const [x1, y1, x2, y2] = s.box;
          if (x >= x1 - NEAR && x <= x2 + NEAR && y >= y1 - NEAR && y <= y2 + NEAR) return { item: d, handle: -1 };
        }
        if (s.entry !== undefined) {
          const top = Math.min(s.stop, s.target, s.entry), bottom = Math.max(s.stop, s.target, s.entry);
          if (x >= s.x1 && x <= s.x2 && y >= top && y <= bottom) return { item: d, handle: -1 };
        }
        if (s.text) {
          const w = 8 * Math.max(4, (d.text || "").length);
          if (x >= s.text.x - 4 && x <= s.text.x + w && y >= s.text.y - 16 && y <= s.text.y + 4) return { item: d, handle: -1 };
        }
      }
      return null;
    }

    // ── painting ──────────────────────────────────────────────────────────
    paint(ctx, size) {
      if (this.hidden) return;
      const pal = this.opts.palette();
      const preview = this.previewItem();
      for (const d of preview ? [...this.items, preview] : this.items) this.paintOne(ctx, size, d, pal, d === this.selected);
    }

    previewItem() {
      if (!this.pending || !this.mouse) return null;
      const points = [...this.pending.points, { t: this.mouse.t, p: this.mouse.p }];
      while (points.length < POINTS[this.pending.type]) points.push(points[points.length - 1]);
      return { ...this.defaults(this.pending.type, points), id: "preview" };
    }

    colorOf(d, pal) {
      if (d.color) return d.color;
      if (d.type === "rect") return d.direction === "bullish" ? pal.up : d.direction === "bearish" ? pal.bad : pal.accent;
      if (d.type === "fib") return pal.muted;
      return pal.ink;
    }

    paintOne(ctx, size, d, pal, selected) {
      const s = this.shape(d, size.width);
      const color = this.colorOf(d, pal);
      const fmt = (p) => p.toFixed(this.opts.digits());
      ctx.save();
      ctx.lineWidth = selected ? 2 : 1;
      ctx.strokeStyle = color;
      ctx.fillStyle = color;
      ctx.font = "12px system-ui, sans-serif";
      ctx.textBaseline = "bottom";
      const line = (x1, y1, x2, y2, dash) => {
        ctx.setLineDash(dash || []);
        ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke();
        ctx.setLineDash([]);
      };
      const label = (text, x, y, align) => {
        if (!text) return;
        ctx.textAlign = align || "left";
        ctx.fillText(text, x, y);
      };
      switch (d.type) {
        case "hline": case "hray": case "trend": case "vline": {
          for (const l of s.lines) line(...l);
          if (d.label) {
            const [x1, y1] = s.lines[0];
            label(d.label, d.type === "vline" ? x1 + 4 : Math.max(x1, 0) + 6, d.type === "vline" ? 16 : y1 - 3);
          }
          break;
        }
        case "rect": {
          const [x1, y1, x2, y2] = s.box;
          ctx.fillStyle = alpha(color, 0.14);
          ctx.fillRect(x1, y1, x2 - x1, y2 - y1);
          ctx.strokeRect(x1, y1, x2 - x1, y2 - y1);
          if (d.mid) line(x1, (y1 + y2) / 2, x2, (y1 + y2) / 2, [5, 4]);
          ctx.fillStyle = color;
          const name = [d.tf, d.kind, d.label].filter(Boolean).join(" ");
          label(name, Math.max(x1, 0) + 4, y1 - 3);         // stays in view when the box starts off-screen
          break;
        }
        case "fib": {
          for (const v of s.levels) {
            const key = v.l === 1 || v.l === 0;
            ctx.globalAlpha = key ? 1 : 0.8;
            line(s.x1, v.y, s.x2, v.y, key ? [] : [4, 3]);
            label(`${v.l}  ${fmt(v.p)}`, Math.max(s.x1, 0) + 4, v.y - 2);
          }
          ctx.globalAlpha = 1;
          line(...d.points.map((q) => [this.X(q.t), this.Y(q.p)]).flat(), [2, 3]);
          break;
        }
        case "long": case "short": {
          const { x1, x2, entry, stop, target } = s;
          ctx.fillStyle = alpha(pal.up, 0.18);
          ctx.fillRect(x1, Math.min(entry, target), x2 - x1, Math.abs(target - entry));
          ctx.fillStyle = alpha(pal.bad, 0.18);
          ctx.fillRect(x1, Math.min(entry, stop), x2 - x1, Math.abs(stop - entry));
          ctx.strokeStyle = pal.ink;
          line(x1, entry, x2, entry);
          const [e, st, tg] = d.points.map((q) => q.p);
          const risk = Math.abs(e - st), rr = risk ? Math.abs(tg - e) / risk : 0;
          ctx.fillStyle = pal.ink;
          label(`${d.type === "long" ? "Long" : "Short"} ${fmt(e)}  R:R ${rr.toFixed(2)}${d.status ? "  · " + d.status : ""}`,
                x1 + 4, entry - 3);
          ctx.fillStyle = pal.up;
          label(`Target ${fmt(tg)}`, x1 + 4, d.type === "long" ? target - 3 : target + 14);
          ctx.fillStyle = pal.bad;
          label(`Stop ${fmt(st)}`, x1 + 4, d.type === "long" ? stop + 14 : stop - 3);
          break;
        }
        case "text": {
          const text = d.text || "";
          const w = ctx.measureText(text).width + 8;
          ctx.fillStyle = alpha(pal.panel, 0.85);
          ctx.fillRect(s.text.x - 4, s.text.y - 16, w, 18);
          ctx.fillStyle = color;
          label(text, s.text.x, s.text.y - 2);
          break;
        }
      }
      if (selected) {
        ctx.fillStyle = pal.panel;
        ctx.strokeStyle = pal.accent;
        ctx.lineWidth = 1.5;
        for (const q of s.handles) {
          ctx.beginPath(); ctx.rect(q.x - HANDLE, q.y - HANDLE, HANDLE * 2, HANDLE * 2); ctx.fill(); ctx.stroke();
        }
      }
      ctx.restore();
    }

    axisViews() {
      const views = [];
      const pal = this.opts.palette();
      const add = (p, color) => views.push({
        coordinate: () => this.Y(p), text: () => p.toFixed(this.opts.digits()), textColor: () => "#ffffff",
        backColor: () => color, visible: () => Number.isFinite(this.Y(p)), tickVisible: () => true,
      });
      if (this.hidden) return views;
      for (const d of this.items) {
        if (d.type === "hline" || d.type === "hray") add(d.points[0].p, this.colorOf(d, pal));
      }
      const s = this.selected;
      if (s && (s.type === "long" || s.type === "short")) {
        add(s.points[0].p, pal.ink); add(s.points[1].p, pal.bad); add(s.points[2].p, pal.up);
      } else if (s && s.type === "rect") {
        add(s.points[0].p, this.colorOf(s, pal)); add(s.points[1].p, this.colorOf(s, pal));
      }
      return views;
    }

    // ── the pointer ───────────────────────────────────────────────────────
    bind(el) {
      const local = (e) => {
        const r = el.getBoundingClientRect();
        return { x: e.clientX - r.left, y: e.clientY - r.top, width: r.width };
      };
      const paneWidth = () => this.chart.timeScale().width();
      el.addEventListener("mousedown", (e) => {
        if (e.button !== 0) return;
        const { x, y } = local(e);
        if (x > paneWidth()) return;                               // the price scale
        if (this.opts.picking && this.opts.picking()) {
          const at = this.at(x, y, true);
          if (at) this.opts.onPick(at);
          e.stopPropagation(); e.preventDefault();
          return;
        }
        if (this.pending) {
          const at = this.at(x, y, true);
          if (!at) return;
          this.pending.points.push({ t: at.t, p: at.p });
          e.stopPropagation(); e.preventDefault();
          if (this.pending.points.length === POINTS[this.pending.type]) this.finish();
          this.refresh();
          return;
        }
        const hit = this.hit(x, y, paneWidth());
        if (!hit) { if (this.selected) this.select(null); return; }
        if (hit.item !== this.selected) this.select(hit.item);
        const start = this.at(x, y, false);
        this.snapshot();
        this.drag = { item: hit.item, handle: hit.handle, start, points: JSON.parse(JSON.stringify(hit.item.points)), moved: false };
        this.chart.applyOptions({ handleScroll: false, handleScale: false });
        e.stopPropagation(); e.preventDefault();
      }, true);
      el.addEventListener("mousemove", (e) => {
        const { x, y } = local(e);
        const at = this.at(x, y, !!this.pending || (this.drag && this.drag.handle >= 0));
        this.mouse = at;
        if (this.drag && at) {
          const { item, handle, start, points } = this.drag;
          this.drag.moved = true;
          if (handle >= 0) {
            const q = item.points[handle];
            if (item.type === "hline") q.p = at.p;
            else if ((item.type === "long" || item.type === "short") && handle < 2) { q.p = at.p; }
            else { q.t = at.t; q.p = at.p; }
          } else {
            const ts = this.chart.timeScale();
            const dl = ts.coordinateToLogical(x) - ts.coordinateToLogical(this.X(start.t));
            const dp = at.p - start.p;
            const shift = Math.round(dl);
            item.points = points.map((q) => ({
              t: this.opts.timeline.toTime(Math.round(this.opts.timeline.toLogical(q.t)) + shift),
              p: Math.round((q.p + dp) * Math.pow(10, this.opts.digits())) / Math.pow(10, this.opts.digits()),
            }));
          }
          this.refresh();
          return;
        }
        if (this.pending) { this.refresh(); return; }
        if (!(this.opts.picking && this.opts.picking())) {
          el.style.cursor = this.hit(x, y, this.chart.timeScale().width()) ? "pointer" : "";
        }
      }, true);
      window.addEventListener("mouseup", () => {
        if (!this.drag) return;
        const moved = this.drag.moved;
        this.drag = null;
        this.chart.applyOptions({ handleScroll: true, handleScale: true });
        if (moved) this.changed(); else this.history.pop();
      });
      el.addEventListener("mouseleave", () => { this.mouse = null; if (this.pending) this.refresh(); });
    }

    finish() {
      const p = this.pending;
      const d = this.defaults(p.type, p.points);
      if (d.type === "text") {
        const text = window.prompt("Text");
        if (!text) { this.cancel(); return; }
        d.text = text;
      }
      if ((d.type === "long" || d.type === "short")) {
        const [e, s, t] = d.points.map((q) => q.p);
        const ok = d.type === "long" ? s < e && t > e : s > e && t < e;
        if (!ok) { this.cancel(); this.opts.onError(`A ${d.type}: stop ${d.type === "long" ? "below" : "above"} the entry, target beyond it.`); return; }
      }
      this.snapshot();
      this.items.push(d);
      this.cancel();
      this.select(d);
      this.changed();
    }
  }

  window.Drawings = Drawings;
  window.DRAWING_POINTS = POINTS;
  window.FIB_LEVELS = FIB_LEVELS;
})();
