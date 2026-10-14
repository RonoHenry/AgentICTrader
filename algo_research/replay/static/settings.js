// Settings for the blind replay chart (update 2026-10-14c): preferences kept in this browser,
// the drawing settings dialog, the chart settings dialog, context menus and the object tree.
"use strict";

(function () {
  // ── preferences (this browser only; the chart works without them) ────────
  const Prefs = {
    get(key, fallback) {
      try { const v = localStorage.getItem("replay." + key); return v == null ? fallback : JSON.parse(v); } catch (e) { return fallback; }
    },
    set(key, value) { try { localStorage.setItem("replay." + key, JSON.stringify(value)); } catch (e) { /* private window */ } },
  };

  const CHART_DEFAULTS = {
    theme: "auto", upColor: "", downColor: "", wicksLikeBody: true, upWick: "", downWick: "", borders: false,
    background: "", gridV: true, gridH: true, crosshair: "normal", scaleMode: "normal", autoScale: true, watermark: false,
    separators: true, dayOpen: true, midnightOpen: true,
    kzAsia: false, kzLondon: false, kzNyAm: false, kzNyPm: false,
    kzAsiaColor: "#94a3b8", kzLondonColor: "#3b82f6", kzNyAmColor: "#22c55e", kzNyPmColor: "#f59e0b", kzOpacity: 0.07,
  };

  // ── small DOM helpers ─────────────────────────────────────────────────────
  const el = (tag, attrs, ...kids) => {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (k === "class") n.className = v; else if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
      else if (v !== undefined && v !== null && v !== false) n.setAttribute(k, v === true ? "" : v);
    }
    for (const kid of kids.flat()) if (kid !== null && kid !== undefined && kid !== false) n.append(kid.nodeType ? kid : String(kid));
    return n;
  };
  const row = (label, ...controls) => el("div", { class: "row" }, el("label", {}, label), ...controls);
  const hex = (c, fallback) => (/^#[0-9a-f]{6}$/i.test(c || "") ? c : fallback);
  const color = (value, fallback, onInput) => { const i = el("input", { type: "color", value: hex(value, fallback) }); i.oninput = () => onInput(i.value); return i; };
  const check = (text, value, onChange) => {
    const i = el("input", { type: "checkbox" }); i.checked = !!value; i.onchange = () => onChange(i.checked);
    return el("label", { class: "check" }, i, " " + text);
  };
  const choose = (value, options, onChange) => {
    const s = el("select", {}, options.map(([v, t]) => el("option", { value: v, selected: String(v) === String(value) }, t)));
    s.onchange = () => onChange(s.value); return s;
  };
  const numberIn = (value, attrs, onChange) => { const i = el("input", { type: "number", step: "any", ...attrs }); i.value = value; i.onchange = () => onChange(Number(i.value)); return i; };
  const textIn = (value, placeholder, onChange) => { const i = el("input", { type: "text", placeholder }); i.value = value || ""; i.oninput = () => onChange(i.value); return i; };
  const range = (value, onInput) => { const i = el("input", { type: "range", min: 0, max: 0.6, step: 0.02 }); i.value = value; i.oninput = () => onInput(Number(i.value)); return i; };

  // ── a movable dialog ──────────────────────────────────────────────────────
  let open = null;
  function dialog(title, tabs, footer, start) {
    if (open) open.close();
    const body = el("div", { class: "dialog-body" });
    const tabBar = el("div", { class: "dialog-tabs" });
    const box = el("div", { class: "dialog", role: "dialog", "aria-label": title },
      el("div", { class: "dialog-head" }, el("b", {}, title), el("span", { class: "spacer" }),
         el("button", { class: "x", title: "Close (Esc)", onclick: () => api.close() }, "✕")),
      tabs.length > 1 ? tabBar : null, body, footer ? el("div", { class: "dialog-foot" }, footer) : null);
    const show = (i) => {
      [...tabBar.children].forEach((b, k) => b.classList.toggle("on", k === i));
      body.replaceChildren(); tabs[i].build(body);
    };
    tabs.forEach((t, i) => tabBar.append(el("button", { onclick: () => show(i) }, t.name)));
    const api = { close() { box.remove(); document.removeEventListener("keydown", esc, true); if (open === api) open = null; }, box };
    const esc = (e) => { if (e.key === "Escape") { e.stopPropagation(); api.close(); } };
    document.addEventListener("keydown", esc, true);
    // drag by the head
    const head = box.firstChild;
    head.addEventListener("mousedown", (e) => {
      if (e.target.closest("button")) return;
      const r = box.getBoundingClientRect(), dx = e.clientX - r.left, dy = e.clientY - r.top;
      const move = (m) => { box.style.left = Math.max(0, m.clientX - dx) + "px"; box.style.top = Math.max(0, m.clientY - dy) + "px"; box.style.transform = "none"; };
      const up = () => { window.removeEventListener("mousemove", move); window.removeEventListener("mouseup", up); };
      window.addEventListener("mousemove", move); window.addEventListener("mouseup", up);
    });
    document.body.append(box);
    show(Math.max(0, tabs.findIndex((t) => t.name === start)));
    open = api;
    return api;
  }

  // ── the drawing settings dialog ───────────────────────────────────────────
  const LINE_TYPES = ["hline", "hray", "vline", "trend", "ray", "extended", "arrow", "path", "channel", "fib", "fibext", "rect", "range"];
  const EXTENDS = ["trend", "ray", "extended", "rect", "fib", "fibext", "channel", "long", "short"];
  const FILLS = ["rect", "range", "channel"];
  const AXIS = ["hline", "hray", "rect", "range", "long", "short"];

  function toolSettings(draw, item, ctx, start) {
    draw.snapshot();
    const look = () => draw.look(item);
    const set = (patch) => { draw.setStyle(item, patch); };
    const meta = (patch) => { Object.assign(item, patch); draw.changed(); };
    const pal = ctx.palette();
    const t = item.type;
    const tabs = [{ name: "Style", build(b) {
      const L = look();
      if (t === "rect") {
        b.append(row("Side", choose(item.direction || "neutral", [["bullish", "Bullish"], ["bearish", "Bearish"], ["neutral", "Other"]],
                                    (v) => { meta({ direction: v }); set({ color: "" }); })),
                 row("Array", choose(item.kind || "", [["", "—"], ...ctx.kinds.map((k) => [k, k])], (v) => meta({ kind: v || undefined })),
                     choose(item.tf || "", [["", "TF"], ...ctx.timeframes.map((x) => [x, x])], (v) => meta({ tf: v || undefined }))));
      }
      if (LINE_TYPES.includes(t) || t === "long" || t === "short") {
        b.append(row(t === "long" || t === "short" ? "Entry line" : "Line", color(L.color, draw.colorOf(item, L, pal), (v) => set({ color: v })),
                     choose(L.width, [[1, "1px"], [2, "2px"], [3, "3px"], [4, "4px"]], (v) => set({ width: Number(v) })),
                     choose(L.dash, [["solid", "Solid"], ["dashed", "Dashed"], ["dotted", "Dotted"]], (v) => set({ dash: v }))));
      }
      if (FILLS.includes(t)) b.append(row("Fill", color(L.fill, draw.colorOf(item, L, pal), (v) => set({ fill: v })), range(L.opacity, (v) => set({ opacity: v }))));
      if (t === "rect") b.append(row("50% line", check("show (CE / MT)", L.showMid, (v) => set({ showMid: v })),
                                     choose(L.midDash, [["solid", "Solid"], ["dashed", "Dashed"], ["dotted", "Dotted"]], (v) => set({ midDash: v }))));
      if (t === "long" || t === "short") {
        b.append(row("Target zone", color(L.profit, pal.up, (v) => set({ profit: v }))), row("Stop zone", color(L.loss, pal.bad, (v) => set({ loss: v }))),
                 row("Opacity", range(L.opacity, (v) => set({ opacity: v }))));
      }
      if (EXTENDS.includes(t)) {
        const left = t === "long" || t === "short" ? null : check("left", L.extendLeft, (v) => set({ extendLeft: v }));
        b.append(row("Extend", left, check("right", L.extendRight, (v) => set({ extendRight: v }))));
      }
      if (AXIS.includes(t)) b.append(row("Price labels", check("on the price scale", L.priceLabels, (v) => set({ priceLabels: v }))));
      b.append(row("", check("Lock (no moving)", item.locked, (v) => meta({ locked: v })), check("Hide", item.hidden, (v) => meta({ hidden: v }))));
    } }];
    tabs.push({ name: "Text", build(b) {
      const L = look();
      if (t === "text") b.append(row("Text", textIn(item.text, "", (v) => meta({ text: v }))),
                                 row("Background", color(L.background, pal.panel, (v) => set({ background: v }))));
      else b.append(row("Label", textIn(item.label, "e.g. PDH, NWOG, Asia low, C2 high", (v) => meta({ label: v || undefined }))));
      b.append(row("Text colour", color(L.textColor, draw.colorOf(item, L, pal), (v) => set({ textColor: v }))),
               row("Size", choose(L.fontSize, [[10, "10"], [11, "11"], [12, "12"], [13, "13"], [14, "14"], [16, "16"], [20, "20"]], (v) => set({ fontSize: Number(v) }))));
      if (t === "fib" || t === "fibext") b.append(row("Show", check("levels", L.showLabels, (v) => set({ showLabels: v })), check("prices", L.showPrices, (v) => set({ showPrices: v }))));
      else b.append(row("", check("Show the label", L.showLabels, (v) => set({ showLabels: v }))));
    } });
    if (t === "fib" || t === "fibext") tabs.push({ name: "Levels", build(b) {
      const render = () => {
        b.replaceChildren();
        const levels = draw.levelsOf(item).map((l) => ({ ...l }));
        const save = () => meta({ levels: levels.map((l) => ({ value: l.value, ...(l.color ? { color: l.color } : {}), ...(l.visible === false ? { visible: false } : {}) })) });
        levels.forEach((l, i) => {
          const vis = el("input", { type: "checkbox" }); vis.checked = l.visible !== false; vis.onchange = () => { l.visible = vis.checked; save(); };
          b.append(el("div", { class: "row level" }, vis, numberIn(l.value, { style: "width:90px" }, (v) => { if (Number.isFinite(v)) { l.value = v; save(); } }),
                      color(l.color, draw.colorOf(item, look(), pal), (v) => { l.color = v; save(); }),
                      el("button", { class: "boxed", title: "Remove", onclick: () => { levels.splice(i, 1); save(); render(); } }, "✕")));
        });
        b.append(el("div", { class: "row" },
          el("button", { class: "boxed", onclick: () => { levels.push({ value: 0 }); save(); render(); } }, "+ Level"),
          el("button", { class: "boxed", onclick: () => { meta({ levels: undefined }); delete item.levels; draw.changed(); render(); } }, "Default levels")));
      };
      render();
    } });
    tabs.push({ name: "Coordinates", build(b) {
      const names = t === "long" || t === "short" ? ["Entry", "Stop", "Target"] : t === "fib" ? ["Level 1", "Level 0"] :
        t === "fibext" ? ["A", "B", "C"] : t === "channel" ? ["Start", "End", "Width"] : ["Point 1", "Point 2", "Point 3"];
      if (t === "path") { b.append(el("div", { class: "hint" }, `${item.points.length} points, drawn freehand.`)); return; }
      item.points.forEach((q, i) => {
        b.append(row(names[i], numberIn(q.p.toFixed(ctx.digits()), { style: "width:120px" }, (v) => {
          if (!Number.isFinite(v)) return;
          const pts = item.points.map((r) => ({ ...r })); pts[i].p = v; meta({ points: pts });
        }), el("span", { class: "muted" }, ctx.timeLabel(q.t))));
      });
    } });
    const footer = [
      el("button", { class: "boxed", title: "New drawings of this kind will look like this one", onclick: () => {
        const L = look(); const keep = {};
        for (const k of ["color", "width", "dash", "fill", "opacity", "showMid", "midDash", "extendLeft", "extendRight", "priceLabels",
                         "textColor", "fontSize", "showLabels", "showPrices", "profit", "loss", "background"]) keep[k] = L[k];
        if (t === "rect") keep.color = item.style && item.style.color ? item.style.color : "";
        if (t === "fib" || t === "fibext") keep.levels = draw.levelsOf(item);
        ctx.saveTemplate(t, keep); ctx.say(`Saved as the default ${window.DRAWING_NAMES[t].toLowerCase()}.`);
      } }, "Save as default"),
      el("button", { class: "boxed", title: "Back to the default look", onclick: () => { delete item.style; draw.changed(); dlg.close(); toolSettings(draw, item, ctx); } }, "Reset look"),
      el("span", { class: "spacer" }),
      el("button", { class: "primary", onclick: () => dlg.close() }, "OK"),
    ];
    const dlg = dialog(window.DRAWING_NAMES[t], tabs, footer, start);
    if (start === "Text") setTimeout(() => { const i = dlg.box.querySelector(".dialog-body input[type=text]"); if (i) { i.focus(); i.select(); } }, 0);
    return dlg;
  }

  // ── the chart settings dialog ─────────────────────────────────────────────
  function chartSettings(ctx) {
    const p = { ...CHART_DEFAULTS, ...Prefs.get("chart", {}) };
    const set = (patch) => { Object.assign(p, patch); Prefs.set("chart", p); ctx.apply(p); };
    const pal = ctx.palette();
    const tabs = [
      { name: "Candles", build(b) {
        b.append(row("Up", color(p.upColor, pal.up, (v) => set({ upColor: v }))), row("Down", color(p.downColor, pal.down, (v) => set({ downColor: v }))),
                 row("Wicks", check("same as the body", p.wicksLikeBody, (v) => set({ wicksLikeBody: v })),
                     color(p.upWick, pal.up, (v) => set({ upWick: v })), color(p.downWick, pal.down, (v) => set({ downWick: v }))),
                 row("Borders", check("show", p.borders, (v) => set({ borders: v }))),
                 row("", el("button", { class: "boxed", onclick: () => set({ upColor: "", downColor: "", upWick: "", downWick: "" }) }, "Theme colours")));
      } },
      { name: "Canvas", build(b) {
        b.append(row("Theme", choose(p.theme, [["auto", "Follow the system"], ["light", "Light"], ["dark", "Dark"]], (v) => set({ theme: v }))),
                 row("Background", color(p.background, pal.background, (v) => set({ background: v })),
                     el("button", { class: "boxed", onclick: () => set({ background: "" }) }, "Theme")),
                 row("Grid", check("vertical", p.gridV, (v) => set({ gridV: v })), check("horizontal", p.gridH, (v) => set({ gridH: v }))),
                 row("Crosshair", choose(p.crosshair, [["normal", "Free"], ["magnet", "Magnet to the close"]], (v) => set({ crosshair: v }))),
                 row("Watermark", check("instrument and timeframe", p.watermark, (v) => set({ watermark: v }))));
      } },
      { name: "Scales", build(b) {
        b.append(row("Price scale", choose(p.scaleMode, [["normal", "Regular"], ["log", "Logarithmic"], ["percent", "Percent"]], (v) => set({ scaleMode: v }))),
                 row("", check("Auto-scale", p.autoScale, (v) => set({ autoScale: v }))));
      } },
      { name: "Sessions", build(b) {
        b.append(row("Days", check("separators at 17:00 New York", p.separators, (v) => set({ separators: v }))),
                 row("Opens", check("day open (17:00)", p.dayOpen, (v) => set({ dayOpen: v })), check("midnight open (00:00)", p.midnightOpen, (v) => set({ midnightOpen: v }))),
                 el("div", { class: "hint" }, "Killzones (the engine's windows, New York time):"),
                 row("Asia 20–00", check("shade", p.kzAsia, (v) => set({ kzAsia: v })), color(p.kzAsiaColor, "#94a3b8", (v) => set({ kzAsiaColor: v }))),
                 row("London 02–05", check("shade", p.kzLondon, (v) => set({ kzLondon: v })), color(p.kzLondonColor, "#3b82f6", (v) => set({ kzLondonColor: v }))),
                 row("NY AM 07–10", check("shade", p.kzNyAm, (v) => set({ kzNyAm: v })), color(p.kzNyAmColor, "#22c55e", (v) => set({ kzNyAmColor: v }))),
                 row("NY PM 13:30–16", check("shade", p.kzNyPm, (v) => set({ kzNyPm: v })), color(p.kzNyPmColor, "#f59e0b", (v) => set({ kzNyPmColor: v }))),
                 row("Shade", range(p.kzOpacity, (v) => set({ kzOpacity: v }))));
      } },
    ];
    const footer = [el("button", { class: "boxed", onclick: () => { Prefs.set("chart", {}); ctx.apply({ ...CHART_DEFAULTS }); dlg.close(); chartSettings(ctx); } }, "Reset all"),
                    el("span", { class: "spacer" }), el("button", { class: "primary", onclick: () => dlg.close() }, "OK")];
    const dlg = dialog("Chart settings", tabs, footer);
    return dlg;
  }

  // ── context menus ─────────────────────────────────────────────────────────
  let menu = null;
  function contextMenu(x, y, entries) {
    if (menu) menu.remove();
    menu = el("div", { class: "menu", role: "menu" }, entries.map((e) => e === "-" ? el("div", { class: "menu-sep" }) :
      el("button", { disabled: e.disabled, onclick: () => { closeMenu(); e.action(); } }, e.label, e.key ? el("span", { class: "muted key" }, e.key) : null)));
    document.body.append(menu);
    const r = menu.getBoundingClientRect();
    menu.style.left = Math.min(x, window.innerWidth - r.width - 6) + "px";
    menu.style.top = Math.min(y, window.innerHeight - r.height - 6) + "px";
    setTimeout(() => window.addEventListener("mousedown", outside, true), 0);
  }
  function outside(e) { if (menu && !menu.contains(e.target)) closeMenu(); }
  function closeMenu() { if (menu) menu.remove(); menu = null; window.removeEventListener("mousedown", outside, true); }

  // ── the object tree ───────────────────────────────────────────────────────
  function objectTree(box, draw, ctx) {
    box.replaceChildren();
    if (!draw.items.length) { box.append(el("div", { class: "muted" }, "No drawings.")); return; }
    for (const d of [...draw.items].reverse()) {
      const name = [window.DRAWING_NAMES[d.type], d.tf, d.kind, d.label || d.text].filter(Boolean).join(" · ");
      box.append(el("div", { class: "obj" + (d === draw.selected ? " on" : "") },
        el("button", { class: "name", title: "Select", onclick: () => { draw.select(d); ctx.refresh(); } }, name),
        el("button", { title: d.hidden ? "Show" : "Hide", onclick: () => { draw.toggle(d, "hidden"); ctx.refresh(); } }, d.hidden ? "◌" : "👁"),
        el("button", { title: d.locked ? "Unlock" : "Lock", onclick: () => { draw.toggle(d, "locked"); ctx.refresh(); } }, d.locked ? "🔒" : "🔓"),
        el("button", { title: "Delete", onclick: () => { draw.remove(d); ctx.refresh(); } }, "✕")));
    }
  }

  window.ReplayUI = { Prefs, CHART_DEFAULTS, toolSettings, chartSettings, contextMenu, closeMenu, objectTree, el };
})();
