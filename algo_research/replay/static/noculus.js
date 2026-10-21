// Noculus: the trader's own marks and trades on the engine chart (algo-backtester update 2026-10-16,
// Requirements 18 and 19).
//
// A tool is armed, then a candle is clicked. The server reads the array from that candle and the ones its kind
// needs — C1 two before C3 for a gap, the first later close beyond for an inversion — and refuses anything that
// would need a candle closing after the replay clock, so a mark holds only what the trader could see. Nothing
// is computed here: this module arms the tools, sends the click, and draws what comes back as a box with its
// mid line (the CE of a gap, the MT of a block).
//
// A mark may be made on any timeframe while any other is on the chart: the clicked bar's time is floored to the
// marking timeframe's own candle, which the wall-clock buckets make exact.
//
// A trade is a ticket at the clock: long or short, market or limit, with a stop and a target, optionally tied to
// one of the marks. The server prices it by the race rules and settles it as the clock advances; the page draws
// each one's entry, stop and target, and its exit once it has one.
//
// A position (update 2026-10-21, Requirements 25-26) is TradingView's Long or Short Position drawn on the chart,
// in any session: selected, it is placed at the clock, and the server makes it a market order or a limit by where
// its entry sits. The drawing then carries its trade's state, and the panel sets each position beside the
// engine's trade at that moment, measured in the market's own average range. While a blind session is unrevealed,
// the engine's side stays hidden.
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
  const LIVE = { PENDING: "waiting", OPEN: "open", CLOSED: "closed", EXPIRED: "expired", REJECTED: "refused" };
  const esc = (t) => String(t == null ? "" : t).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

  class Noculus {
    // opts: { box, timeline, palette, seconds(tf), timeframes, tf(), digits(), clock(), status(), api(path, body),
    //         say(text), refresh(), timeLabel(t), X(t), Y(p), onReveal(status) }
    constructor(chart, series, opts) {
      this.chart = chart; this.series = series; this.opts = opts;
      this.data = null;                                  // the session's journal, as the server keeps it
      this.trades = []; this.diff = null;                // the comparison, once the engine is revealed
      this.pairs = null; this.position = null;           // the positions beside the engine's; the selected drawing
      this.tool = null; this.field = null; this.tf = null; this.dir = 0; this.side = "LONG"; this.builtKey = null;
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
    armed() { return !!(this.blind && (this.tool || this.field)); }

    /** The session's journal, its trades and its positions beside the engine's. Every session keeps one. */
    async sync() {
      this.data = null; this.trades = []; this.pairs = null; this.builtKey = null;
      if (this.opts.status()) {
        try {
          this.data = await this.opts.api("/api/watch/noculus");
          this.trades = this.data.trades || [];
          if (this.blind && this.revealed != null) this.diff = await this.opts.api("/api/watch/noculus/comparison");
          await this.loadPairs();
        } catch (e) { this.data = null; this.opts.say(e.message); }
      }
      this.tool = this.field = null;
      this.render();
      this.link();
    }

    /** The clock moved: the server settles every trade up to it, and sets the positions beside the engine's. */
    async tick() {
      if (!this.data) return;
      try {
        this.trades = (await this.opts.api(`/api/watch/noculus/trades?t=${this.opts.clock()}`)).trades;
        await this.loadPairs();
        this.fillTrades(); this.fillPosition(); this.fillPairs(); this.link();
      } catch (e) { /* the session may be between states; the next tick will catch up */ }
    }

    async loadPairs() {
      this.pairs = this.trades.length ? await this.opts.api(`/api/watch/noculus/positions?t=${this.opts.clock()}`) : null;
    }

    // ── positions (Requirements 25-26) ────────────────────────────────────
    /** The drawing selected on the chart: a long or short position is offered for placing. */
    select(d) {
      this.position = d && (d.type === "long" || d.type === "short") ? d : null;
      this.fillPosition();
    }

    /** Place a drawn position at the clock; the server picks market or limit from where its entry sits. */
    async placePosition(d) {
      d = d || this.position;
      if (!d || !this.data) return;
      const [entry, stop, target] = d.points.map((q) => q.p);
      try {
        const trade = await this.opts.api("/api/watch/noculus/position", {
          direction: d.type === "long" ? "LONG" : "SHORT", entry, stop, target, t: this.opts.clock(), drawing: d.id });
        this.trades.push(trade);
        await this.loadPairs();
        this.opts.say(`${trade.id}: ${trade.direction} ${trade.kind === "LIMIT" ? `limit at ${this.price(trade.price)}` : "at market"} placed.`);
      } catch (e) { this.opts.say(e.message); }
      this.fillTrades(); this.fillPosition(); this.fillPairs(); this.link();
      this.opts.refresh();
    }

    /** Each position drawing carries its trade's state, as TradingView's tool shows its P&L. */
    link() {
      const items = this.opts.drawings ? this.opts.drawings() : [];
      const by = {};
      for (const x of this.trades) if (x.drawing) by[x.drawing] = x;
      for (const d of items) {
        if (d.type !== "long" && d.type !== "short") continue;
        const x = by[d.id];
        if (!x) { delete d.status; continue; }
        d.status = x.state === "OPEN" ? `open ${this.r(x.live_r)}` : x.state === "CLOSED" ? `${x.outcome} ${this.r(x.net_r)}`
          : LIVE[x.state] || x.state;
      }
      if (this.opts.redraw) this.opts.redraw();
    }

    arm(tool) {
      this.tool = this.tool === tool ? null : tool;
      this.field = null;
      this.cursor(this.tool ? `Click ${CLICK[this.tool]} on the chart (${this.markTf()}).` : "");
      this.fillTools();
    }

    armField(id, what) {
      this.tool = null;
      this.field = this.field === id ? null : id;
      this.cursor(this.field ? `Click the chart to set the ${what}.` : "");
      this.fillTools();
    }

    cursor(message) {
      document.body.classList.toggle("picking", this.armed());
      this.opts.say(message);
    }

    markTf() { return this.tf || this.opts.tf(); }

    /** A click on the chart: a price for the ticket, or the candle of a new mark. */
    async pick(at) {
      if (this.field) {
        const el = this.opts.box.querySelector("#" + this.field);
        if (el) el.value = Number(at.p).toFixed(this.opts.digits());
        this.field = null;
        this.cursor("");
        this.fillTools();
        return;
      }
      const tool = this.tool, tf = this.markTf();
      const bar = this.opts.timeline.barAt(at.index);
      if (!bar || !tool) return;
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
      this.fillMarks();
      this.opts.refresh();
    }

    async unmark(id) {
      try {
        const gone = await this.opts.api("/api/watch/noculus/unmark", { id, t: this.opts.clock() });
        const row = (this.data.marks || []).find((m) => m.id === gone.id);
        if (row) row.deleted_at = gone.deleted_at;
      } catch (e) { this.opts.say(e.message); }
      this.fillMarks();
      this.opts.refresh();
    }

    // ── the ticket ────────────────────────────────────────────────────────
    async place() {
      const box = this.opts.box, num = (id) => {
        const el = box.querySelector("#" + id);
        return el && el.value !== "" ? Number(el.value) : null;
      };
      const kind = box.querySelector("#nKind").value;
      const body = { direction: this.side, kind, t: this.opts.clock(), stop: num("nStop"), target: num("nTarget"),
                     note: box.querySelector("#nNote").value, mark: box.querySelector("#nMark").value || null };
      if (kind === "LIMIT") body.price = num("nPrice");
      if (body.stop == null || body.target == null) { this.opts.say("A stop and a target, please."); return; }
      try {
        const trade = await this.opts.api("/api/watch/noculus/place", body);
        this.trades.push(trade);
        this.opts.say(`${trade.id}: ${trade.direction} ${trade.kind.toLowerCase()} placed.`);
        for (const id of ["nPrice", "nStop", "nTarget", "nNote"]) box.querySelector("#" + id).value = "";
      } catch (e) { this.opts.say(e.message); }
      this.fillTrades();
      this.opts.refresh();
    }

    async closeTrade(id) {
      try {
        const done = await this.opts.api("/api/watch/noculus/close", { id, t: this.opts.clock() });
        const i = this.trades.findIndex((x) => x.id === done.id);
        if (i >= 0) this.trades[i] = done;
        this.opts.say(`${done.id}: closed by hand, ${this.r(done.net_r)}.`);
      } catch (e) { this.opts.say(e.message); }
      this.fillTrades();
      this.opts.refresh();
    }

    async reveal() {
      if (!confirm("Reveal the engine's arrays, setups and trades up to the clock? This cannot be undone, and the "
                   + "marking stops here.")) return;
      try {
        const status = await this.opts.api("/api/watch/reveal", { t: this.opts.clock() });
        this.tool = this.field = null;
        document.body.classList.remove("picking");
        await this.opts.onReveal(status);
        this.diff = await this.opts.api("/api/watch/noculus/comparison");
        await this.loadPairs();                          // the engine's side of each position, now in sight
        this.builtKey = null;                            // the panel becomes the comparison
        this.render();
      } catch (e) { this.opts.say(e.message); }
    }

    // ── the panel ─────────────────────────────────────────────────────────
    r(value) { return value == null ? "—" : `${value >= 0 ? "+" : ""}${Number(value).toFixed(2)}R`; }
    price(p) { return p == null ? "—" : Number(p).toFixed(this.opts.digits()); }

    render() {
      const key = `${!!this.data}|${this.blind}|${this.marking}`;
      if (this.builtKey !== key) { this.build(); this.builtKey = key; }
      if (!this.data) return;
      this.fillTools(); this.fillMarks(); this.fillTrades(); this.fillDiff(); this.fillPosition(); this.fillPairs();
    }

    build() {
      const box = this.opts.box;
      if (!this.data) { box.innerHTML = ""; return; }
      if (!this.blind) {
        box.innerHTML = `<h2>Your positions</h2>
          <div class="hint">Draw a Long or Short position (▲ ▼ or Alt+L, Alt+S), select it and place it at the clock.
            Each is set beside the engine's trade at that moment.</div>
          <div id="nPosition"></div><div class="ntrades" id="nTrades"></div><div id="nPairs"></div>`;
        return;
      }
      const tools = this.marking ? `
        <div class="row ntools" id="nTools"></div>
        <div class="row"><label>On</label><select id="nTf">${this.opts.timeframes.map((tf) =>
          `<option ${tf === this.markTf() ? "selected" : ""}>${tf}</option>`).join("")}</select>
          <label>Block</label><select id="nDir">${DIRS.map(([v, label]) =>
          `<option value="${v}">${label}</option>`).join("")}</select></div>` : "";
      const ticket = this.marking ? `
        <h2>Your trade</h2>
        <div class="row" id="nSides"></div>
        <div class="row"><label>Order</label><select id="nKind"><option>MARKET</option><option>LIMIT</option></select>
          <label>Limit</label><input type="number" step="any" id="nPrice">
          <button class="boxed" data-field="nPrice" title="Pick from the chart">◎</button></div>
        <div class="row"><label>Stop</label><input type="number" step="any" id="nStop">
          <button class="boxed" data-field="nStop" title="Pick from the chart">◎</button>
          <label>Target</label><input type="number" step="any" id="nTarget">
          <button class="boxed" data-field="nTarget" title="Pick from the chart">◎</button></div>
        <div class="row"><label>From</label><select id="nMark"></select>
          <input type="text" id="nNote" placeholder="why"></div>
        <div class="row"><button class="primary" id="nPlace">Place the trade</button></div>` : "";
      box.innerHTML = `<h2>Noculus</h2>
        <div class="hint">${this.marking
          ? "The engine is hidden. Mark the arrays you see and place your trades, then reveal."
          : `Revealed at ${esc(this.opts.timeLabel(this.revealed))}. The marking is done; the engine is on the chart.`}</div>
        ${tools}
        <div class="nmarks" id="nMarks"></div>
        <div id="nPosition"></div>
        ${ticket}
        <div class="ntrades" id="nTrades"></div>
        <div id="nPairs"></div>
        ${this.marking ? `<div class="row"><button class="boxed" id="nReveal">Reveal the engine</button></div>`
                       : `<div id="nDiff"></div>`}`;
      const tf = box.querySelector("#nTf"), dir = box.querySelector("#nDir"), rev = box.querySelector("#nReveal");
      if (tf) tf.onchange = () => { this.tf = tf.value; this.fillTools(); };
      if (dir) dir.onchange = () => { this.dir = Number(dir.value); };
      if (rev) rev.onclick = () => this.reveal();
      const place = box.querySelector("#nPlace");
      if (place) place.onclick = () => this.place();
      for (const b of box.querySelectorAll("[data-field]")) {
        b.onclick = () => this.armField(b.dataset.field, { nPrice: "limit price", nStop: "stop", nTarget: "target" }[b.dataset.field]);
      }
      const kind = box.querySelector("#nKind");
      if (kind) kind.onchange = () => { box.querySelector("#nPrice").disabled = kind.value !== "LIMIT"; };
      if (kind) box.querySelector("#nPrice").disabled = true;
    }

    fillTools() {
      const box = this.opts.box, tools = box.querySelector("#nTools"), sides = box.querySelector("#nSides");
      if (tools) {
        tools.innerHTML = TOOLS.map(([t, label, title]) =>
          `<button class="boxed${this.tool === t ? " on" : ""}" data-arm="${t}" title="${esc(title)}">${esc(label)}</button>`).join("");
        for (const b of tools.querySelectorAll("[data-arm]")) b.onclick = () => this.arm(b.dataset.arm);
      }
      if (sides) {
        sides.innerHTML = ["LONG", "SHORT"].map((s) =>
          `<button class="boxed${this.side === s ? " on" : ""}" data-side="${s}">${s === "LONG" ? "Long" : "Short"}</button>`).join("");
        for (const b of sides.querySelectorAll("[data-side]")) {
          b.onclick = () => { this.side = b.dataset.side; this.fillTools(); };
        }
      }
      for (const b of box.querySelectorAll("[data-field]")) b.classList.toggle("on", this.field === b.dataset.field);
    }

    fillMarks() {
      const box = this.opts.box, list = box.querySelector("#nMarks");
      if (!list) return;
      list.innerHTML = this.marks.map((m) => `<div class="nmark">
        <b>${esc(m.tf)} ${esc(m.tool)}</b> ${m.direction > 0 ? "▲" : "▼"}
        <span class="muted">${this.price(m.low)}–${this.price(m.high)} · mid ${this.price(m.mid)} ·
          formed ${esc(this.opts.timeLabel(m.formed_at))}</span>
        ${this.marking ? `<button class="boxed" data-unmark="${esc(m.id)}" title="Delete this mark">×</button>` : ""}</div>`).join("")
        || `<div class="muted">No marks yet.</div>`;
      for (const b of list.querySelectorAll("[data-unmark]")) b.onclick = () => this.unmark(b.dataset.unmark);
      const pick = box.querySelector("#nMark");
      if (pick) {
        const was = pick.value;
        pick.innerHTML = `<option value="">no mark</option>` + this.marks.map((m) =>
          `<option value="${esc(m.id)}">${esc(m.tf)} ${esc(m.tool)} ${this.price(m.mid)}</option>`).join("");
        pick.value = was;
      }
    }

    fillTrades() {
      const list = this.opts.box.querySelector("#nTrades");
      if (!list) return;
      const rows = this.trades.map((x) => {
        const live = x.state === "OPEN" ? `${this.r(x.live_r)} now` : x.state === "CLOSED" ? `${esc(x.outcome)} ${this.r(x.net_r)}` : LIVE[x.state] || x.state;
        return `<div class="nmark"><b>${esc(x.direction)}</b> <span class="muted">${esc(x.kind.toLowerCase())}
          ${x.fill == null ? `at ${this.price(x.price)}` : `from ${this.price(x.fill)}`} ·
          stop ${this.price(x.stop)} · target ${this.price(x.target)}</span>
          <b class="${x.state === "CLOSED" ? (x.net_r >= 0 ? "good" : "bad") : "muted"}">${live}</b>
          ${x.state === "OPEN" ? `<button class="boxed" data-close="${esc(x.id)}" title="Close it here">close</button>` : ""}</div>`;
      }).join("");
      const done = this.trades.filter((x) => x.state === "CLOSED");
      const total = done.reduce((s, x) => s + (x.net_r || 0), 0);
      list.innerHTML = (rows || `<div class="muted">No trades yet.</div>`)
        + (done.length ? `<div class="hint">${done.length} closed: <b>${this.r(total)}</b></div>` : "");
      for (const b of list.querySelectorAll("[data-close]")) b.onclick = () => this.closeTrade(b.dataset.close);
    }

    /** The selected position drawing, with its place button until it is placed. */
    fillPosition() {
      const el = this.opts.box.querySelector("#nPosition");
      if (!el) return;
      const d = this.position;
      if (!d) { el.innerHTML = ""; return; }
      const placed = this.trades.find((x) => x.drawing === d.id);
      const [e, s, tg] = d.points.map((q) => q.p);
      const rr = Math.abs(e - s) ? (Math.abs(tg - e) / Math.abs(e - s)).toFixed(2) : "—";
      el.innerHTML = `<div class="card"><b>${d.type === "long" ? "Long" : "Short"} position</b>
        <span class="muted">entry ${this.price(e)} · stop ${this.price(s)} · target ${this.price(tg)} · R:R ${rr}</span>
        <div class="row">${placed ? `<span class="good">Placed as ${esc(placed.id)}</span>`
          : `<button class="primary" id="nPlacePos">Place it at ${esc(this.opts.timeLabel(this.opts.clock()))}</button>`}</div>
        ${placed ? "" : `<div class="hint">Within two spreads of the price it is a market order; on the pullback side, a limit at its entry.</div>`}</div>`;
      const b = this.opts.box.querySelector("#nPlacePos");
      if (b) b.onclick = () => this.placePosition(d);
    }

    /** Each position beside the engine's trade at its clock, measured in the M15 average range. */
    fillPairs() {
      const el = this.opts.box.querySelector("#nPairs");
      if (!el) return;
      const p = this.pairs;
      if (!p || !p.pairs || !p.pairs.length) { el.innerHTML = ""; return; }
      const atr = (m) => (m && m.M15 != null ? Number(m.M15).toFixed(1) : "—");
      const num = (v) => (v == null ? "—" : String(v));
      const one = (x) => `${esc(x.direction)}${x.kind === "SKIPPED" ? " (refused by its limits)" : ""} ${this.price(x.entry)}
        <span class="muted">· stop ${atr(x.stop_atr)} / target ${atr(x.target_atr)} M15 ATR · R:R ${x.rr == null ? "—" : Number(x.rr).toFixed(1)}
        · ${esc(x.outcome || "")} ${this.r(x.net_r)}</span>`;
      const rows = p.pairs.map((q) => `<div class="nmark"><b>you</b> ${one(q.mine)}</div>` + (p.hidden
        ? `<div class="cond muted">the engine: hidden until you reveal</div>`
        : q.engine ? `<div class="cond"><b>engine</b> ${one(q.engine)} <span class="muted">${esc(q.when)}, ${q.minutes_apart} min apart</span>
            ${q.engine.kind === "SKIPPED" && q.engine.reason ? `<div class="muted">${esc(q.engine.reason)}</div>` : ""}</div>
            <div class="cond">parted on: <b class="${q.label === "agree" ? "good" : "warn"}">${esc(q.label)}</b></div>`
          : `<div class="cond muted">the engine had no trade then, nor later that day</div>`)).join("");
      const s = p.summary;
      const tail = s ? `<div class="hint">${s.pairs} position(s): ${Object.entries(s.labels).map(([k, v]) => `${esc(k)} ${v}`).join(", ")}.
        Median stop in M15 ATR: yours ${num(s.median_stop_atr.mine)}, the engine's ${num(s.median_stop_atr.engine)};
        median target: yours ${num(s.median_target_atr.mine)}, the engine's ${num(s.median_target_atr.engine)}.</div>` : "";
      el.innerHTML = `<h2>You beside the engine</h2>${rows}${tail}`;
    }

    /** The comparison, once the engine is out: where the marks agreed, and the days side by side. */
    fillDiff() {
      const box = this.opts.box.querySelector("#nDiff");
      if (!box) return;
      const d = this.diff;
      if (!d) { box.innerHTML = `<div class="muted">No comparison yet.</div>`; return; }
      const a = d.arrays, c = a.counts;
      const rate = (row) => (row.mine ? `${row.matched}/${row.mine} (${Math.round(100 * row.matched / row.mine)}%)` : "—");
      const kinds = Object.entries(a.by_kind || {}).map(([k, row]) => `${esc(k)} ${rate(row)}`).join(" · ");
      const frames = Object.entries(a.by_tf || {}).map(([k, row]) => `${esc(k)} ${rate(row)}`).join(" · ");
      const one = (x) => (x ? `${esc(x.direction)} ${this.price(x.entry)} → ${esc(x.outcome)} ${this.r(x.net_r)}` : "—");
      const days = (d.trades.days || []).map((day) => `<div class="nmark">
        <b>${esc(day.day)}</b> <span class="muted">you ${this.r(day.mine_r)} · engine ${this.r(day.engine_r)}</span>
        ${day.disagreed ? `<b class="warn">read differently</b>` : ""}</div>` +
        day.pairs.map((p) => `<div class="cond">${one(p.mine)} <span class="muted">vs</span> ${one(p.engine)}
          <span class="muted">${p.same_side ? "same side" : "the other side"}, ${p.apart_minutes} min apart</span></div>`).join("") +
        day.mine_only.map((x) => `<div class="cond">${one(x)} <span class="muted">— the engine didn't</span></div>`).join("") +
        day.engine_only.map((x) => `<div class="cond"><span class="muted">you didn't —</span> ${one(x)}</div>`).join("")).join("");
      box.innerHTML = `<h2>You against the engine</h2>
        <div class="card"><b>Arrays</b>: ${c.matched} of your ${c.mine} marks are also the engine's;
          ${c.mine_only} only yours; ${c.engine_only} of its own, on the timeframes you marked, you didn't mark.
          <div class="muted">${kinds || "—"}</div><div class="muted">${frames || "—"}</div></div>
        <div class="card"><b>Trades</b>: you ${this.r(d.trades.totals.mine_r)} in ${d.trades.totals.mine},
          the engine ${this.r(d.trades.totals.engine_r)} in ${d.trades.totals.engine};
          ${d.trades.totals.days_apart} day(s) read differently.${days}</div>`;
    }

    // ── the chart ─────────────────────────────────────────────────────────
    paint(ctx, size) {
      if (!this.data) return;
      const pal = this.opts.palette(), W = size.width;
      const X = (t) => this.opts.X(t), Y = (p) => this.opts.Y(p);
      ctx.save();
      ctx.font = "10px system-ui, sans-serif"; ctx.textBaseline = "bottom";
      const line = (x1, y, x2, color, dash) => {
        if (!isFinite(y) || !isFinite(x1)) return;
        ctx.strokeStyle = color; ctx.lineWidth = 1; ctx.setLineDash(dash || []);
        ctx.beginPath(); ctx.moveTo(x1, y); ctx.lineTo(x2, y); ctx.stroke(); ctx.setLineDash([]);
      };
      const text = (s, x, y, color) => { ctx.fillStyle = color; ctx.textAlign = "left"; ctx.fillText(s, x, y); };
      for (const m of this.blind ? this.marks : []) {
        const y1 = Y(m.high), y2 = Y(m.low), x1 = Math.max(X(m.candles[0]), -10);
        if (!isFinite(y1) || !isFinite(y2) || !isFinite(x1)) continue;
        const c = m.direction > 0 ? pal.good : pal.warn;   // the trader's own colours, not the engine's
        const top = Math.min(y1, y2), height = Math.max(1, Math.abs(y2 - y1));
        ctx.fillStyle = rgba(c, 0.1); ctx.fillRect(x1, top, W - x1, height);
        ctx.strokeStyle = rgba(c, 0.9); ctx.lineWidth = 1.5; ctx.setLineDash([]);
        ctx.strokeRect(x1, top, W - x1, height);
        line(x1, Y(m.mid), W, rgba(c, 0.8), [3, 3]);
        text(`mine: ${m.tf} ${m.tool}`, Math.max(x1, 0) + 3, top - 1, c);
      }
      for (const x of this.trades) {
        if (x.state === "REJECTED" || x.state === "EXPIRED" || x.drawing) continue;   // a drawn position shows itself
        const from = Math.max(X(x.filled_at != null ? x.filled_at : x.placed_at), -10);
        const to = x.exit_at != null ? X(x.exit_at) : W;
        if (!isFinite(from)) continue;
        if (x.fill == null) {                              // a limit still waiting at its price
          line(from, Y(x.price), x.expiry ? Math.min(X(x.expiry), W) : W, rgba(pal.accent, 0.9), [5, 4]);
          text(`${x.direction} limit`, Math.max(from, 0) + 3, Y(x.price) - 1, pal.accent);
          continue;
        }
        line(from, Y(x.fill), to, pal.accent, []);
        line(from, Y(x.stop), to, rgba(pal.bad, 0.8), [4, 3]);
        line(from, Y(x.target), to, rgba(pal.good, 0.8), [4, 3]);
        const label = x.state === "CLOSED" ? `${x.direction} ${x.outcome} ${this.r(x.net_r)}` : `${x.direction} ${this.r(x.live_r)}`;
        text(`mine: ${label}`, Math.max(from, 0) + 3, Y(x.fill) - 1, pal.accent);
        if (x.exit_at != null && isFinite(to)) {
          const y = Y(x.exit);
          if (isFinite(y)) { ctx.fillStyle = x.net_r >= 0 ? pal.good : pal.bad; ctx.fillRect(to - 2, y - 2, 5, 5); }
        }
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
