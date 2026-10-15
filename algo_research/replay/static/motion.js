// A chart that moves freely (market-narrative Requirement 13, update 2026-10-15), shared by the replay and the watch.
//
// TradingView's behaviour on Lightweight Charts: drag the pane in any direction; a vertical drag turns the price
// scale from auto-fit to manual; drag the price axis to stretch or squeeze it; double-click it, or press A, to fit
// again; lock the price to bar ratio so zooming time zooms price too. The manual range is served through the
// series' autoscale provider, so the price scale stays in "auto" mode underneath and every redraw keeps it.
// The bar countdown under the last price runs on the replay's clock.
"use strict";

(function () {
  const DAY = 86400, DAY_OPEN = 61200;                        // trading days open at 17:00 New York wall time

  class Motion {
    // opts: { container, draw, prefs: {get, set}, now() -> wall seconds or null, tfSeconds(), bars(), palette(), onChange() }
    constructor(chart, series, opts) {
      this.chart = chart; this.series = series; this.opts = opts;
      this.view = null;                                       // null: fit the data; {lo, hi}: the pane's price range
      this.lock = !!opts.prefs.get("motion.lock", false);
      this.width = null;                                      // the visible logical width, for the locked ratio
      this.press = null;
      this.scale = { mouseWheel: true, pinch: true, axisPressedMouseMove: { time: true, price: false },
                     axisDoubleClickReset: { time: true, price: false } };
      chart.applyOptions({ handleScale: this.scale, rightPriceScale: { autoScale: true } });
      if (opts.draw) opts.draw.restore = { handleScroll: true, handleScale: this.scale };
      series.applyOptions({ autoscaleInfoProvider: this.provider() });
      chart.timeScale().subscribeVisibleLogicalRangeChange((r) => this.zoomed(r));
      this.countdown(series);
      this.corner();
      this.bind(opts.container);
    }

    // ── the price range ───────────────────────────────────────────────────
    mode() { return this.chart.priceScale("right").options().mode || 0; }
    log() { return this.mode() === 1; }
    to(p) { return this.log() ? Math.log10(Math.max(p, 1e-12)) : p; }
    from(v) { return this.log() ? Math.pow(10, v) : v; }
    height() { return this.chart.paneSize().height; }
    visible() {                                               // the pane's range now, in scale units (log10 on a log scale)
      const h = this.height(), hi = this.series.coordinateToPrice(0), lo = this.series.coordinateToPrice(h);
      return hi === null || lo === null ? null : { lo: this.to(lo), hi: this.to(hi) };
    }
    provider() {
      return (base) => {
        if (!this.view) return base();
        const m = this.series.priceScale().options().scaleMargins || { top: 0.2, bottom: 0.1 };
        const span = this.view.hi - this.view.lo;              // the provider's range is padded by the margins: undo them
        return { priceRange: { minValue: this.from(this.view.lo + m.bottom * span), maxValue: this.from(this.view.hi - m.top * span) } };
      };
    }
    apply() {
      this.series.applyOptions({ autoscaleInfoProvider: this.provider() });   // a new provider makes the scale ask again
      this.mark();
      if (this.opts.onChange) this.opts.onChange();
    }
    isAuto() { return !this.view; }
    fit() { this.view = null; if (this.lock) this.setLock(false); this.apply(); }
    freeze() { if (!this.view) { const v = this.visible(); if (v) { this.view = v; this.apply(); } } }
    setLock(on) {
      this.lock = !!on; this.opts.prefs.set("motion.lock", this.lock);
      if (this.lock) this.freeze();                           // a locked ratio needs a manual range, as in TradingView
      this.mark();
    }
    setView(lo, hi) { if (hi - lo > 0 && isFinite(lo) && isFinite(hi)) { this.view = { lo, hi }; this.apply(); } }
    zoomed(r) {
      if (!r) return;
      const width = r.to - r.from, before = this.width;
      this.width = width;
      if (!this.lock || !before || this.press || Math.abs(width / before - 1) < 1e-6) return;
      const v = this.view || this.visible();
      if (!v) return;
      const c = (v.lo + v.hi) / 2, half = ((v.hi - v.lo) / 2) * (width / before);
      this.setView(c - half, c + half);
    }

    // ── the pointer: pan the pane, stretch the axis ───────────────────────
    bind(el) {
      const local = (e) => { const r = el.getBoundingClientRect(); return { x: e.clientX - r.left, y: e.clientY - r.top }; };
      el.addEventListener("mousedown", (e) => {
        if (e.button !== 0 || e.defaultPrevented) return;      // the drawings took it
        const { x, y } = local(e), pane = this.chart.timeScale().width(), h = this.height();
        if (y > h || this.mode() >= 2) return;                 // the time axis; a percent scale keeps fitting
        const v = this.view || this.visible();
        if (!v) return;
        const axis = x > pane && x <= pane + this.chart.priceScale("right").width();
        this.press = { axis, y0: y, v, h, moved: false };
      }, true);
      window.addEventListener("mousemove", (e) => {
        const p = this.press;
        if (!p) return;
        const dy = local(e).y - p.y0, span = p.v.hi - p.v.lo;
        if (!p.moved && Math.abs(dy) < 4) return;
        p.moved = true;
        if (p.axis) {                                          // drag down squeezes, up stretches, about the middle
          const c = (p.v.lo + p.v.hi) / 2, half = (span / 2) * Math.exp((dy / p.h) * 2.5);
          this.setView(c - half, c + half);
        } else {
          const shift = (dy / p.h) * span;                     // drag down: see higher prices
          this.setView(p.v.lo + shift, p.v.hi + shift);
        }
      });
      window.addEventListener("mouseup", () => { this.press = null; });
      el.addEventListener("dblclick", (e) => {
        const { x, y } = local(e), pane = this.chart.timeScale().width();
        if (x > pane && y <= this.height()) { e.preventDefault(); this.fit(); }
      }, true);
    }

    // ── the corner: A and the lock ────────────────────────────────────────
    corner() {
      const host = this.opts.container.parentElement;
      const box = document.createElement("div");
      box.className = "motion-corner";
      this.lockBtn = Object.assign(document.createElement("button"), { textContent: "🔒", title: "Lock price to bar ratio" });
      this.autoBtn = Object.assign(document.createElement("button"), { textContent: "A", title: "Auto: fit the data to the screen (or double-click the price scale)" });
      this.lockBtn.onclick = () => this.setLock(!this.lock);
      this.autoBtn.onclick = () => { if (this.view) this.fit(); else this.freeze(); };
      box.append(this.lockBtn, this.autoBtn);
      host.append(box);
      this.box = box;
      const place = () => {
        const w = this.chart.priceScale("right").width(), h = this.chart.timeScale().height();
        Object.assign(box.style, { width: Math.max(w, 52) + "px", height: Math.max(h, 24) + "px" });
      };
      new ResizeObserver(place).observe(host);
      this.chart.timeScale().subscribeVisibleLogicalRangeChange(place);
      this.mark();
    }
    mark() {
      if (!this.autoBtn) return;
      this.autoBtn.classList.toggle("on", !this.view);
      this.lockBtn.classList.toggle("on", this.lock);
    }
    menu() {                                                  // entries for the chart's right-click menu
      return [
        { label: (this.view ? "" : "✓ ") + "Auto (fit the data to the screen)", action: () => (this.view ? this.fit() : this.freeze()) },
        { label: (this.lock ? "✓ " : "") + "Lock price to bar ratio", action: () => this.setLock(!this.lock) },
      ];
    }

    // ── the bar countdown, on the replay's clock ──────────────────────────
    countdown(series) {
      const owner = this;
      let update = () => {};
      this.redraw = () => update();
      series.attachPrimitive({
        attached(p) { update = p.requestUpdate; }, detached() {}, updateAllViews() {}, paneViews() { return []; },
        priceAxisViews() {
          const left = owner.remaining();
          if (left == null) return [];
          const bars = owner.opts.bars(), last = bars[bars.length - 1];
          const pal = owner.opts.palette();
          const color = last.close >= last.open ? pal.up : pal.down;
          return [{
            coordinate: () => { const y = series.priceToCoordinate(last.close); return y === null ? -100 : y + 19; },
            text: () => clock(left), textColor: () => "#ffffff", backColor: () => color,
            visible: () => true, tickVisible: () => false,
          }];
        },
      });
    }
    remaining() {
      const now = this.opts.now(), sec = this.opts.tfSeconds(), bars = this.opts.bars();
      if (now == null || !bars.length || !sec || sec > 7 * DAY) return null;
      const t = bars[bars.length - 1].time;
      let end = t + sec;
      if (sec < DAY) end = Math.min(end, t + (DAY - ((((t - DAY_OPEN) % DAY) + DAY) % DAY)));   // bars restart at 17:00
      const left = end - now;
      return left > 0 && now >= t ? left : null;
    }
  }

  function clock(s) {
    const p = (n) => String(n).padStart(2, "0");
    if (s >= DAY) return `${Math.floor(s / DAY)}d ${p(Math.floor((s % DAY) / 3600))}h`;
    const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = Math.floor(s % 60);
    return h ? `${h}:${p(m)}:${p(sec)}` : `${p(m)}:${p(sec)}`;
  }

  window.Motion = Motion;
})();
