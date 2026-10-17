// Noculus: the trader's own marks on the engine chart (algo-backtester update 2026-10-16, Requirement 18).
//
// A tool is armed, then a candle is clicked. The server reads the array from that candle and the ones its kind
// needs — C1 two before C3 for a gap, the first later close beyond for an inversion — and refuses anything that
// would need a candle closing after the replay clock, so a mark holds only what the trader could see. Nothing
// is computed here: this module arms the tools, sends the click, and draws what comes back as a box with its
// mid line (the CE of a gap, the MT of a block).
//
// A mark may be made on any timeframe while any other is on the chart: the clicked bar's time is floored to the
// marking timeframe's own candle, which the wall-clock buckets make exact.
"use strict";

(function () {
  const TOOLS = [
    ["FVG", "Gap", "Fair value gap: click its third candle"],
    ["IFVG", "Inverted", "Inverted gap: click the gap's third candle, once a close has gone beyond it"],
    ["OB", "Block", "Order block: click the block's own candle"],
    ["BRK", "Breaker", "Breaker: click the block's candle, once a close has gone beyond it"],
  ];
  const CLICK = { FVG: "the gap's third candle", IFVG: "the gap's third candle", OB: "the block's candle", BRK: "the block's candle" };
  const DIRS = [[0, "by its colour"], [1, "bullish"], [-1, "bearish"]];
  const esc = (t) => String(t == null ? "" : t).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

  class Noculus {
    // opts: { box, timeline, palette, seconds(tf), timeframes, tf(), digits(), clock(), status(), api(path, body),
    //         say(text), refresh(), onReveal(status) }
    constructor(chart, series, opts) {
      this.chart = chart; this.series = series; this.opts = opts;
      this.data = null;                                  // the session's journal, as the server keeps it
      this.tool = null; this.tf = null; this.dir = 0;
      this.update = () => {};
      series.attachPrimitive({
        attached: (p) => { this.update = p.requestUpdate; }, detached() {}, updateAllViews() {},
        paneViews: () => [{ zOrder: () => "normal", renderer: () => ({ draw: (target) =>
          target.useMediaCoordinateSpace(({ context, mediaSize }) => this.paint(context, mediaSize)) }) }],
      });
    }

    // ── state ─────────────────────────────────────────────────────────────
    get marks() { return (this.data && this.data.marks || []).filter((m) => m.deleted_at == null); }
    get revealed() { const st = this.opts.status(); return st ? st.revealed_at : null; }
    get blind() { const st = this.opts.status(); return !!(st && st.blind); }
    get marking() { return this.blind && this.revealed == null; }
    armed() { return this.marking && !!this.tool; }

    /** The session's journal, or nothing when the session is not blind. */
    async sync() {
      this.data = null;
      if (this.blind) { try { this.data = await this.opts.api("/api/watch/noculus"); } catch (e) { this.opts.say(e.message); } }
      this.tool = null;
      this.render();
    }

    arm(tool) {
      this.tool = this.tool === tool ? null : tool;
      document.body.classList.toggle("picking", this.armed());
      this.opts.say(this.armed() ? `Click ${CLICK[this.tool]} on the chart (${this.markTf()}).` : "");
      this.render();
    }

    markTf() { return this.tf || this.opts.tf(); }

    /** A click on the chart while a tool is armed: the bar it landed on, floored to the marking timeframe. */
    async pick(at) {
      const tool = this.tool, tf = this.markTf();
      const bar = this.opts.timeline.barAt(at.index);
      if (!bar) return;
      const size = this.opts.seconds(tf) || 900;
      const candle = Math.floor(bar.time / size) * size;
      const body = { tool, tf, t: this.opts.clock(), candle, note: "" };
      if (tool === "OB" || tool === "BRK") body.direction = this.dir;
      const fmt = (p) => Number(p).toFixed(this.opts.digits());
      let message;
      try {
        const mark = await this.opts.api("/api/watch/noculus/mark", body);
        this.data.marks.push(mark);
        message = `${tf} ${tool} marked: ${fmt(mark.low)} to ${fmt(mark.high)}, mid ${fmt(mark.mid)}.`;
      } catch (e) {
        message = e.message;                             // the refusal, in the server's words
      }
      this.arm(null);
      this.opts.say(message);                            // said last: putting the tool down clears the line
      this.opts.refresh();
    }

    async unmark(id) {
      try {
        const gone = await this.opts.api("/api/watch/noculus/unmark", { id, t: this.opts.clock() });
        const row = (this.data.marks || []).find((m) => m.id === gone.id);
        if (row) row.deleted_at = gone.deleted_at;
      } catch (e) { this.opts.say(e.message); }
      this.render();
      this.opts.refresh();
    }

    async reveal() {
      if (!confirm("Reveal the engine's arrays, setups and trades up to the clock? This cannot be undone, and the "
                   + "marking stops here.")) return;
      try {
        const status = await this.opts.api("/api/watch/reveal", { t: this.opts.clock() });
        this.tool = null;
        document.body.classList.remove("picking");
        await this.opts.onReveal(status);
      } catch (e) { this.opts.say(e.message); }
    }

    // ── the panel ─────────────────────────────────────────────────────────
    render() {
      const box = this.opts.box;
      if (!this.blind) { box.innerHTML = ""; return; }
      const fmt = (p) => Number(p).toFixed(this.opts.digits());
      const when = (t) => this.opts.timeLabel(t);
      const rows = this.marks.map((m) => `<div class="nmark">
        <b>${esc(m.tf)} ${esc(m.tool)}</b> ${m.direction > 0 ? "▲" : "▼"}
        <span class="muted">${fmt(m.low)}–${fmt(m.high)} · mid ${fmt(m.mid)} · formed ${esc(when(m.formed_at))}</span>
        <button class="boxed" data-unmark="${esc(m.id)}" title="Delete this mark">×</button></div>`).join("");
      box.innerHTML = `<h2>Noculus</h2>
        <div class="hint">${this.marking
          ? "The engine is hidden. Mark the arrays you see and place your trades, then reveal."
          : `Revealed at ${esc(when(this.revealed))}. The marking is done; the engine is on the chart.`}</div>
        ${this.marking ? `<div class="row ntools">${TOOLS.map(([t, label, title]) =>
            `<button class="boxed${this.tool === t ? " on" : ""}" data-arm="${t}" title="${esc(title)}">${esc(label)}</button>`).join("")}</div>
          <div class="row"><label>On</label><select id="nTf">${this.opts.timeframes.map((tf) =>
            `<option ${tf === this.markTf() ? "selected" : ""}>${tf}</option>`).join("")}</select>
            <label>Block</label><select id="nDir">${DIRS.map(([v, label]) =>
            `<option value="${v}" ${v === this.dir ? "selected" : ""}>${label}</option>`).join("")}</select></div>` : ""}
        <div class="nmarks">${rows || `<div class="muted">No marks yet.</div>`}</div>
        ${this.marking ? `<div class="row"><button class="boxed" id="nReveal">Reveal the engine</button></div>` : ""}`;
      for (const b of box.querySelectorAll("[data-arm]")) b.onclick = () => this.arm(b.dataset.arm);
      for (const b of box.querySelectorAll("[data-unmark]")) b.onclick = () => this.unmark(b.dataset.unmark);
      const tf = box.querySelector("#nTf"), dir = box.querySelector("#nDir"), rev = box.querySelector("#nReveal");
      if (tf) tf.onchange = () => { this.tf = tf.value; this.render(); };
      if (dir) dir.onchange = () => { this.dir = Number(dir.value); };
      if (rev) rev.onclick = () => this.reveal();
    }

    // ── the chart ─────────────────────────────────────────────────────────
    paint(ctx, size) {
      const marks = this.marks;
      if (!marks.length) return;
      const pal = this.opts.palette(), W = size.width;
      const X = (t) => this.opts.X(t), Y = (p) => this.opts.Y(p);
      ctx.save();
      ctx.font = "10px system-ui, sans-serif"; ctx.textBaseline = "bottom";
      for (const m of marks) {
        const y1 = Y(m.high), y2 = Y(m.low), x1 = Math.max(X(m.candles[0]), -10);
        if (!isFinite(y1) || !isFinite(y2) || !isFinite(x1)) continue;
        const c = m.direction > 0 ? pal.good : pal.warn;   // the trader's own colours, not the engine's
        const top = Math.min(y1, y2), height = Math.max(1, Math.abs(y2 - y1));
        ctx.fillStyle = rgba(c, 0.1); ctx.fillRect(x1, top, W - x1, height);
        ctx.strokeStyle = rgba(c, 0.9); ctx.lineWidth = 1.5; ctx.setLineDash([]);
        ctx.strokeRect(x1, top, W - x1, height);
        const ym = Y(m.mid);
        if (isFinite(ym)) {
          ctx.strokeStyle = rgba(c, 0.8); ctx.lineWidth = 1; ctx.setLineDash([3, 3]);
          ctx.beginPath(); ctx.moveTo(x1, ym); ctx.lineTo(W, ym); ctx.stroke(); ctx.setLineDash([]);
        }
        ctx.fillStyle = c; ctx.textAlign = "left";
        ctx.fillText(`mine: ${m.tf} ${m.tool}`, Math.max(x1, 0) + 3, top - 1);
      }
      ctx.restore();
    }
  }

  function rgba(c, a) {
    const m = /^#([0-9a-f]{6})$/i.exec(String(c).trim());
    if (!m) return c;
    const n = parseInt(m[1], 16);
    return `rgba(${n >> 16},${(n >> 8) & 255},${n & 255},${a})`;
  }

  window.Noculus = Noculus;
})();
