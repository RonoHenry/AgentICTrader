// Fractal + POI on Noculus (algo-backtester update 2026-10-19, Requirement 23): the trader's own TradingView
// indicator, read by the server at the replay clock (algo_research.fractal_poi) and painted here.
//
// Nothing is computed on the page. The server sends what the indicator would show on its last bar, from the
// candles closed by the clock: Pine's boxes, lines and labels, each placed in time. The page asks again only when
// something can have changed (a chart candle closed, the chart timeframe or a setting changed, or the clock went
// back), and paints them in the chart's theme: the indicator's black is the theme's ink, so it reads on dark
// charts too.
//
// The settings dialog has the indicator's own inputs and defaults. Changing an input that only chooses what is
// drawn redraws at once; one that changes what is read (the Fractal mode, how many HTF candles) rereads the
// window, which takes a second. The choices are kept in this browser.
"use strict";

(function () {
  const DASH = { solid: [], dashed: [6, 4], dotted: [1.5, 3] };
  const SIZE = { tiny: 9, small: 10, normal: 12, large: 14, huge: 18 };
  const esc = (t) => String(t == null ? "" : t).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const pad = (n) => String(n).padStart(2, "0");

  // A colour as the server writes it: "#rrggbb@alpha", or "ink@alpha" for the indicator's black.
  function paintColor(spec, ink) {
    const [base, a] = String(spec || "ink@1").split("@");
    const alpha = a == null ? 1 : Number(a);
    const hex = base === "ink" ? ink : base;
    let m = /^#([0-9a-f]{6})$/i.exec(hex);
    if (m) { const n = parseInt(m[1], 16); return `rgba(${n >> 16},${(n >> 8) & 255},${n & 255},${alpha})`; }
    m = /rgba?\((\d+),\s*(\d+),\s*(\d+)/.exec(hex || "");
    return m ? `rgba(${m[1]},${m[2]},${m[3]},${alpha})` : `rgba(128,128,128,${alpha})`;
  }

  // The indicator's timer: "45", "12:05", "01:12:05", "2D 01:12:05".
  function timer(left) {
    left = Math.max(0, Math.floor(left));
    const d = Math.floor(left / 86400), h = Math.floor((left % 86400) / 3600), m = Math.floor((left % 3600) / 60), s = left % 60;
    let out = pad(s);
    if (m || h || d) out = pad(m) + ":" + out;
    if (h || d) out = pad(h) + ":" + out;
    return d ? `${d}D ${out}` : out;
  }

  // The inputs in the dialog, by tab: [key, label, kind, options]. Kinds: bool, int, float, text, choice.
  const TABS = [
    ["Inputs", [
      ["fractal_mode", "Fractal", "choice", "modes"], ["custom_htf", "Custom HTF (when Fractal is Custom)", "text"],
      ["bias", "Bias", "choice", ["Neutral", "Bullish", "Bearish"]], ["sweep_history", "History", "int"],
      ["sweep_visible_only", "Setups on visible HTF candles always shown", "bool"],
      ["max_display", "HTF candles", "int"], ["candle_size", "Size", "choice", ["Small", "Normal", "Big"]],
      ["offset", "Offset (candles right of price)", "int"], ["hide_candles", "Hide projection", "bool"],
      ["hide_setups", "Hide setups", "bool"], ["events_show", "Alerts in the event log", "bool"],
      ["dash_show", "Dashboard", "bool"]]],
    ["Model", [
      ["sweep_show", "Sweeps", "bool"], ["sweep_live", "Live setup", "bool"], ["show_c2_lbl", "C2 label", "bool"],
      ["show_c3_lbl", "C3 label", "bool"], ["show_c4_lbl", "C4 label", "bool"], ["cisd_show", "CISD", "bool"],
      ["ic_cisd_show", "IC-CISD", "bool"], ["early_cisd_show", "Early CISD", "bool"], ["entry_zone_show", "Entry zones", "bool"],
      ["proj_show", "SD projections", "bool"], ["proj_type", "SD type", "choice", ["Wick", "Body"]],
      ["proj_deviations", "SD levels", "text"], ["proj_label_show", "SD labels", "bool"],
      ["liq_show", "Formation liquidity", "bool"], ["prev_eq_show", "Previous EQ", "bool"],
      ["drawings_type", "EQ drawn", "choice", ["Both", "On Chart", "HTF candle"]]]],
    ["HTF", [
      ["vt_show", "Vertical lines", "bool"], ["hl_show", "L/H lines", "bool"], ["trace_show", "HTF open", "bool"],
      ["htf_label_show", "HTF label", "bool"], ["label_position", "Label position", "choice", ["Top", "Bottom", "Both"]],
      ["htf_timer_show", "Remaining time", "bool"], ["daily_name", "Interval value", "bool"],
      ["dow_position", "Interval position", "choice", ["Bottom", "Top", "Both"]], ["htf2_show", "HTF2 candles", "bool"],
      ["htf2_count", "HTF2 candles", "int"], ["htf2_gap", "Gap from HTF1", "int"],
      ["htf2_mode", "HTF2 mode", "choice", ["Automatic", "Custom"]], ["htf2_custom", "Custom HTF2", "text"],
      ["htf2_label_show", "HTF2 label", "bool"], ["htf2_timer_show", "HTF2 remaining time", "bool"]]],
    ["Liquidity", [
      ["lq_show_sessions", "Sessions", "bool"], ["lq_draw_style", "Style", "choice", ["Both", "Box", "Lines"]],
      ["lq_box_transp", "Box transparency", "int"], ["lq_max_sessions", "Past sessions shown", "int"],
      ["lq_use_asia", "Asia", "bool"], ["lq_asia_session", "Asia (New York)", "text"],
      ["lq_use_london", "London", "bool"], ["lq_london_session", "London (New York)", "text"],
      ["lq_use_ny", "New York", "bool"], ["lq_ny_session", "New York (New York)", "text"],
      ["lq_session_labels", "Session labels", "bool"], ["lq_hide_above_tf", "Hide sessions from (minutes)", "text"],
      ["lq_use_true_open", "True day open", "bool"], ["lq_tdo_show_label", "TDO label", "bool"],
      ["lq_show_pd", "PDH / PDL", "bool"], ["lq_show_pw", "PWH / PWL", "bool"], ["lq_show_pm", "PMH / PML", "bool"],
      ["lq_show_htf1", "HTF1 BSL / SSL", "bool"], ["lq_htf1_mode", "HTF1 mode", "choice", ["Auto", "Manual"]],
      ["lq_htf1_manual", "HTF1 timeframe", "text"], ["lq_show_htf2", "HTF2 BSL / SSL", "bool"],
      ["lq_htf2_manual", "HTF2 timeframe", "text"], ["lq_show_htf3", "HTF3 BSL / SSL", "bool"],
      ["lq_htf3_manual", "HTF3 timeframe", "text"], ["lq_max_bsl_lines", "Lines per level", "int"],
      ["lq_del_purged", "Delete purged levels", "bool"], ["lq_purge_cross", "✕ on purge", "bool"],
      ["lq_max_purged", "Purged levels kept", "int"], ["lq_show_swings", "Relevant swings", "bool"],
      ["lq_swing_window", "Swing window (HTF candles)", "int"], ["lq_swing_len", "Pivot length", "int"],
      ["lq_swing_max_levels", "Max levels per side", "int"], ["lq_mark_relevant", "Show only relevant levels", "bool"],
      ["lq_atr_len", "ATR length", "int"], ["lq_atr_mult", "Proximity (x ATR)", "float"]]],
    ["FVG & SMT", [
      ["fvg_show", "Fair value gaps", "bool"], ["fvg_auto_mode", "Auto timeframe", "bool"],
      ["fvg_manual_htf", "Manual timeframe", "text"], ["fvg_show_bull", "Bullish", "bool"], ["fvg_show_bear", "Bearish", "bool"],
      ["fvg_show_boxes", "Boxes", "bool"], ["fvg_show_labels", "Labels", "bool"], ["fvg_show_midline", "Midline", "bool"],
      ["fvg_max_fvgs", "Kept", "int"], ["smt_show", "SMT", "bool"], ["smt_label_show", "SMT label", "bool"],
      ["smt_mode", "SMT mode", "choice", ["Automatic", "Manual"]], ["smt_sym2_enable", "Second SMT", "bool"],
      ["smt_sym1", "Symbol 1 (Manual)", "choice", "instruments"], ["smt_sym1_inverse", "Symbol 1 inverse", "bool"],
      ["smt_sym2", "Symbol 2 (Manual)", "choice", "instruments"], ["smt_sym2_inverse", "Symbol 2 inverse", "bool"]]],
  ];

  class FractalPOI {
    // opts: { X(t), Y(p), palette(), api(path), tf(), clock(), status(), instruments(), prefs, say(text),
    //         refresh(), seconds(tf), onView() }
    constructor(chart, series, opts) {
      this.chart = chart; this.series = series; this.opts = opts;
      this.view = null; this.key = null; this.defaults = null; this.on = true; this.busy = null;
      this.mine = opts.prefs.get("watch.fractal", {});           // only the inputs the trader changed
      this.update = () => {};
      series.attachPrimitive({
        attached: (p) => { this.update = p.requestUpdate; }, detached() {}, updateAllViews() {},
        paneViews: () => [{ zOrder: () => "normal", renderer: () => ({ draw: (target) =>
          target.useMediaCoordinateSpace(({ context, mediaSize }) => this.paint(context, mediaSize)) }) }],
      });
    }

    get settings() { return { ...(this.defaults || {}), ...this.mine }; }
    setOn(on) { this.on = !!on; if (!this.on) { this.view = null; this.update(); } }

    async loadDefaults() {
      if (this.defaults) return;
      const got = await this.opts.api("/api/watch/fractal-defaults");
      this.defaults = got.settings || {}; this.modes = got.modes || []; this.drawOnly = new Set(got.draw_only || []);
      for (const k of Object.keys(this.mine)) if (!(k in this.defaults)) delete this.mine[k];   // dropped inputs
    }

    /** Ask the server again if the view can have changed: another timeframe or setting, a candle closed, or
     *  the clock went back. ``force`` asks regardless. */
    async tick(force) {
      const st = this.opts.status();
      if (!this.on || !st) { if (this.view) { this.view = null; this.update(); } return; }
      const tf = this.opts.tf(), t = this.opts.clock(), key = `${tf}|${JSON.stringify(this.mine)}`;
      const v = this.view;
      if (!force && v && v.key === key && t >= v.clock && t < v.refresh_at) { this.update(); return; }
      if (this.busy) return this.busy;
      this.busy = (async () => {
        try {
          await this.loadDefaults();
          const q = `/api/watch/fractal?tf=${tf}&t=${t}&s=${encodeURIComponent(JSON.stringify(this.mine))}`;
          const got = await this.opts.api(q);
          got.key = key;
          this.view = got;
          if (this.opts.onView) this.opts.onView(got);
        } catch (e) {                                     // a bad input: say so, keep playing, keep the last view
          this.opts.say(`Fractal + POI: ${e.message}`);
        } finally { this.busy = null; this.update(); }
      })();
      return this.busy;
    }

    events() { return this.on && this.view ? this.view.events || [] : []; }

    // ── painting ──────────────────────────────────────────────────────────
    paint(ctx, size) {
      const v = this.view;
      if (!this.on || !v) return;
      const { X, Y } = this.opts, pal = this.opts.palette(), ink = pal.ink || "#888888";
      const t = this.opts.clock(), end = v.dashboard && v.dashboard.htf_end;
      ctx.save();
      for (const it of v.items || []) {
        if (it.k === "box") {
          const x1 = X(it.x1), x2 = X(it.x2), y1 = Y(it.y1), y2 = Y(it.y2);
          if (![x1, x2, y1, y2].every(isFinite)) continue;
          ctx.fillStyle = paintColor(it.fill, ink);
          ctx.fillRect(Math.min(x1, x2), Math.min(y1, y2), Math.max(1, Math.abs(x2 - x1)), Math.max(1, Math.abs(y2 - y1)));
          if (it.border) {
            ctx.strokeStyle = paintColor(it.border, ink); ctx.lineWidth = 1; ctx.setLineDash([]);
            ctx.strokeRect(Math.min(x1, x2), Math.min(y1, y2), Math.abs(x2 - x1), Math.abs(y2 - y1));
          }
        } else if (it.k === "line") {
          ctx.strokeStyle = paintColor(it.c, ink); ctx.lineWidth = it.w || 1; ctx.setLineDash(DASH[it.s] || []);
          ctx.beginPath();
          if (it.ext === "both") {
            const x = X(it.x1);
            if (!isFinite(x)) continue;
            ctx.moveTo(x, 0); ctx.lineTo(x, size.height);
          } else {
            const x1 = X(it.x1), x2 = X(it.x2), y1 = Y(it.y1), y2 = Y(it.y2);
            if (![x1, x2, y1, y2].every(isFinite)) continue;
            ctx.moveTo(x1, y1); ctx.lineTo(x2, y2);
          }
          ctx.stroke();
        } else if (it.k === "label") {
          const x = X(it.x), y = Y(it.y);
          if (!isFinite(x) || !isFinite(y)) continue;
          let text = it.t;
          if (it.l === "htf_label" && end != null) text = text.replace(/\(([^)]*)\)\s*$/, `(${timer(end - t)})`);
          this.label(ctx, text, x, y, it.st, SIZE[it.sz] || 10, paintColor(it.c, ink));
        }
      }
      ctx.setLineDash([]);
      ctx.restore();
    }

    label(ctx, text, x, y, style, px, color) {
      const lines = String(text).split("\n");
      ctx.font = `${px}px system-ui, sans-serif`; ctx.fillStyle = color;
      const lh = px + 2, n = lines.length;
      if (style === "left" || style === "right") {
        ctx.textAlign = style === "left" ? "left" : "right"; ctx.textBaseline = "middle";
        lines.forEach((s, i) => ctx.fillText(s, x + (style === "left" ? 5 : -5), y + (i - (n - 1) / 2) * lh));
      } else if (style === "up") {
        ctx.textAlign = "center"; ctx.textBaseline = "top";
        lines.forEach((s, i) => ctx.fillText(s, x, y + 3 + i * lh));
      } else {
        ctx.textAlign = "center"; ctx.textBaseline = "bottom";
        lines.forEach((s, i) => ctx.fillText(s, x, y - 3 - (n - 1 - i) * lh));
      }
    }

    // ── the panel: the indicator's dashboard ─────────────────────────────
    panel() {
      const v = this.view;
      if (!this.on) return "";
      if (!v) return `<h2>Fractal + POI</h2><div class="muted">Reading the indicator…</div>`;
      const d = v.dashboard || {};
      if (!this.settings.dash_show) return `<h2>Fractal + POI <button class="boxed" data-fractal="settings">Settings…</button></h2>`;
      const left = d.htf_end != null ? timer(d.htf_end - this.opts.clock()) : "n/a";
      return `<h2>Fractal + POI <button class="boxed" data-fractal="settings">Settings…</button></h2>
        <div class="card">${esc(d.asset)} · ${esc(d.ltf)} / ${esc(d.htf1)} / ${esc(d.htf2)} · Bias ${esc(d.bias)}<br>
        <span class="muted">${esc(d.htf1)} closes in ${esc(left)} · FVG ${esc(d.fvg)} · SMT ${d.smt && d.smt.length ? esc(d.smt.join(", ")) : "none"}
        · read to the ${esc(this.opts.tf())} candle closed at the clock</span>
        ${d.warning ? `<div class="bad">${esc(d.warning)}</div>` : ""}</div>`;
    }

    // ── the settings dialog ───────────────────────────────────────────────
    async dialog(start) {
      await this.loadDefaults();
      const { el, dialog } = window.ReplayUI;
      const s = this.settings;
      const set = (key, value) => {
        if (value === this.defaults[key]) delete this.mine[key]; else this.mine[key] = value;
        this.opts.prefs.set("watch.fractal", this.mine);
        const slow = !this.drawOnly.has(key);
        this.opts.say(slow ? "Rereading the indicator with the new input…" : "");
        this.tick(true).then(() => { if (slow) this.opts.say(""); this.opts.refresh(); }).catch((e) => this.opts.say(e.message));
      };
      const control = ([key, , kind, options]) => {
        const value = s[key];
        if (kind === "bool") {
          const i = el("input", { type: "checkbox" }); i.checked = !!value; i.onchange = () => set(key, i.checked); return i;
        }
        if (kind === "choice") {
          const list = options === "modes" ? this.modes : options === "instruments" ? ["", ...this.opts.instruments()] : options;
          const sel = el("select", {}, list.map((o) => el("option", { value: o, selected: String(o) === String(value) }, o || "—")));
          sel.onchange = () => set(key, sel.value); return sel;
        }
        const i = el("input", { type: kind === "text" ? "text" : "number", step: kind === "float" ? "0.05" : "1" });
        i.value = value;
        i.onchange = () => set(key, kind === "int" ? Math.round(Number(i.value)) : kind === "float" ? Number(i.value) : i.value);
        return i;
      };
      const tabs = TABS.map(([name, inputs]) => ({ name, build: (b) => {
        if (name === "Inputs") b.append(el("div", { class: "hint" }, "The indicator's own inputs and defaults. It reads closed candles only (Calculate on Close)."));
        for (const input of inputs) b.append(el("div", { class: "row" }, el("label", {}, input[1]), control(input)));
      } }));
      const footer = [el("button", { class: "boxed", onclick: () => { this.mine = {}; this.opts.prefs.set("watch.fractal", {}); dlg.close();
                                                                       this.tick(true).then(() => this.opts.refresh()); } }, "Defaults"),
                      el("span", { class: "spacer" }), el("button", { class: "primary", onclick: () => dlg.close() }, "OK")];
      const dlg = dialog("Fractal + POI", tabs, footer, start);
      return dlg;
    }
  }

  window.FractalPOI = FractalPOI;
  window.FractalPOI.paintColor = paintColor;
  window.FractalPOI.timer = timer;
})();
