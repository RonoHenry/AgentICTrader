// Blind weekly calls (context-engine Requirement 36): a random market and week, hidden, called and scored at once.
// The page only ever knows a chart by its number; the market and the real dates come back with the reveal.
"use strict";

(function () {
  const $ = (id) => document.getElementById(id);
  const esc = (t) => String(t == null ? "" : t).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const pct = (x) => (x == null ? "—" : (100 * x).toFixed(1) + "%");
  const pts = (x) => (x == null ? "—" : (x >= 0 ? "+" : "−") + Math.abs(100 * x).toFixed(1));
  const px = (x) => (x == null ? "—" : Number(x).toFixed(2));
  const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

  const S = { chart: null, series: null, data: null, tf: "W1", side: null, conf: 2, pick: null, lineMode: false,
              lines: [], marks: {}, started: 0, revealed: null };

  // ── the chart ──────────────────────────────────────────────────────────
  function makeChart() {
    const el = $("chart");
    S.chart = LightweightCharts.createChart(el, {
      autoSize: true,
      layout: { background: { color: css("--panel") }, textColor: css("--ink") },
      grid: { vertLines: { color: css("--grid") }, horzLines: { color: css("--grid") } },
      rightPriceScale: { borderColor: css("--line") }, timeScale: { borderColor: css("--line") },
      crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
    });
    S.series = S.chart.addCandlestickSeries({ upColor: css("--up"), downColor: css("--down"), borderUpColor: css("--up"),
      borderDownColor: css("--down"), wickUpColor: css("--up"), wickDownColor: css("--down"),
      priceFormat: { type: "price", precision: 2, minMove: 0.01 } });
    S.chart.subscribeClick((p) => {
      if (!p.point) return;
      const price = S.series.coordinateToPrice(p.point.y);
      if (price == null) return;
      onPrice(Math.round(price * 100) / 100);
    });
    S.chart.subscribeCrosshairMove((p) => {
      const y = p.point ? S.series.coordinateToPrice(p.point.y) : null;
      $("cursor").textContent = y == null ? "" : px(y);
    });
  }

  function show(tf) {
    S.tf = tf;
    for (const b of document.querySelectorAll("[data-tf]")) b.classList.toggle("on", b.dataset.tf === tf);
    let bars = (S.data && S.data.bars[tf]) || [];
    if (tf === "D1" && S.revealed) {
      const muted = css("--muted");
      bars = bars.concat(S.revealed.bars_after.map((b) => ({ ...b, color: muted, borderColor: muted, wickColor: muted })));
    }
    S.series.setData(bars);
    const n = bars.length, span = tf === "D1" ? (S.revealed ? 160 : 120) : tf === "W1" ? 104 : 120;
    if (n) S.chart.timeScale().setVisibleLogicalRange({ from: n - span, to: n + 3 });
  }

  // ── the levels ─────────────────────────────────────────────────────────
  function mark(key, price, color, title, style) {
    if (S.marks[key]) { S.series.removePriceLine(S.marks[key]); delete S.marks[key]; }
    if (price == null || !Number.isFinite(price)) return;
    S.marks[key] = S.series.createPriceLine({ price, color, lineWidth: 2, lineStyle: style || 0, axisLabelVisible: true, title });
  }

  function onPrice(price) {
    if (S.revealed) return;
    if (S.lineMode) {
      S.lines.push(S.series.createPriceLine({ price, color: css("--accent"), lineWidth: 1, lineStyle: 2, axisLabelVisible: true }));
      return;
    }
    if (!S.pick) return;
    $(S.pick === "draw" ? "draw" : "prot").value = price;
    S.pick = S.pick === "draw" && !$("prot").value ? "prot" : null;
    syncLevels();
  }

  function syncLevels() {
    const draw = parseFloat($("draw").value), prot = parseFloat($("prot").value);
    mark("draw", Number.isFinite(draw) ? draw : null, css("--good"), "draw");
    mark("prot", Number.isFinite(prot) ? prot : null, css("--bad"), "protected");
    $("pickDraw").classList.toggle("on", S.pick === "draw");
    $("pickProt").classList.toggle("on", S.pick === "prot");
    const last = S.data ? S.data.last : null, m = check();
    $("odds").textContent = m && m.info ? m.info : "";
    $("odds").className = "msg " + (m && m.err ? "err" : "info");
    if (m && m.err && Number.isFinite(draw) && Number.isFinite(prot)) $("odds").textContent = m.err;
    return last;
  }

  function check() {
    if (!S.side) return { err: "Choose a side." };
    if (S.side === "NONE") return null;
    const draw = parseFloat($("draw").value), prot = parseFloat($("prot").value), last = S.data.last;
    if (!Number.isFinite(draw) || !Number.isFinite(prot)) return { err: "Give the draw and the protected swing." };
    const up = S.side === "BULLISH";
    if (up ? !(prot < last && last < draw) : !(prot > last && last > draw))
      return { err: `A ${S.side.toLowerCase()} call's protected swing is ${up ? "below" : "above"} the last close (1000) and its draw ${up ? "above" : "below"} it.` };
    return { info: `A random walk reaches the draw first ${Math.round(100 * Math.abs(last - prot) / Math.abs(draw - prot))}% of the time (touch against touch).` };
  }

  function setSide(side) {
    if (S.revealed) return;
    S.side = side;
    for (const b of document.querySelectorAll("[data-side]")) b.classList.toggle("on", b.dataset.side === side);
    $("levels").style.opacity = side === "NONE" ? 0.4 : 1;
    if (side !== "NONE" && !$("draw").value) S.pick = "draw";
    if (side === "NONE") S.pick = null;
    syncLevels();
  }

  function setConf(c) {
    S.conf = c;
    for (const b of document.querySelectorAll("[data-c]")) b.classList.toggle("on", Number(b.dataset.c) === c);
  }

  // ── the flow ───────────────────────────────────────────────────────────
  async function api(path, body) {
    const r = await fetch(path, body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {});
    const j = await r.json();
    if (!r.ok) throw new Error(j.error || r.statusText);
    return j;
  }

  async function load() {
    $("msg").textContent = "Loading…"; $("msg").className = "msg info";
    S.data = await api("/api/weekly/chart");
    S.revealed = null; S.side = null; S.pick = null; S.lineMode = false;
    for (const l of S.lines) S.series.removePriceLine(l);
    S.lines = [];
    for (const k of Object.keys(S.marks)) { S.series.removePriceLine(S.marks[k]); delete S.marks[k]; }
    $("draw").value = ""; $("prot").value = ""; $("note").value = ""; $("recognised").checked = false;
    $("reveal").hidden = true; $("reveal").innerHTML = ""; $("save").disabled = false;
    for (const b of document.querySelectorAll("[data-side]")) b.classList.remove("on");
    $("lineTool").classList.remove("on");
    setConf(2);
    if (S.data.id == null) { $("msg").textContent = "Every chart is called."; return; }
    $("chartNo").textContent = `#${S.data.id + 1}`;
    $("evidence").innerHTML = S.data.evidence.map((e, i) => `<label><input type="checkbox" data-ev="${i}"> ${esc(e)}</label>`).join("");
    $("progress").textContent = `${S.data.done} called · ${S.data.total - S.data.done} left`;
    show(S.tf);
    $("msg").textContent = "";
    S.started = Date.now();
  }

  async function save() {
    if (S.revealed || !S.data || S.data.id == null) return;
    const m = check();
    if (m && m.err) { $("msg").textContent = m.err; $("msg").className = "msg err"; return; }
    const evidence = [...document.querySelectorAll("[data-ev]")].filter((x) => x.checked).map((x) => S.data.evidence[Number(x.dataset.ev)]);
    const body = { id: S.data.id, side: S.side, confidence: S.conf, evidence, note: $("note").value,
                   recognised: $("recognised").checked, ms: Date.now() - S.started };
    if (S.side !== "NONE") { body.draw = parseFloat($("draw").value); body.protected = parseFloat($("prot").value); }
    $("save").disabled = true; $("msg").textContent = "Scoring…"; $("msg").className = "msg info";
    try {
      S.revealed = await api("/api/weekly/call", body);
    } catch (e) {
      $("save").disabled = false; $("msg").textContent = e.message; $("msg").className = "msg err"; return;
    }
    $("msg").textContent = "";
    reveal(S.revealed);
    show("D1");
    totals();
  }

  function reveal(r) {
    const s = r.score, rd = r.reader;
    const side = r.side, sideCls = side === "BULLISH" ? "good" : side === "BEARISH" ? "bad" : "";
    const wk = s.week_hit == null ? `${s.week_up ? "up" : "down"} (no side called)` :
      `<span class="${s.week_hit ? "good" : "bad"}">${s.week_hit ? "on your side" : "against you"}</span> (drift ${pct(s.drift)})`;
    const race = s.race == null ? "—" : `<span class="${s.race === "held" ? "good" : s.race === "failed" ? "bad" : ""}">${
      s.race === "held" ? "draw first" : s.race === "failed" ? "invalidated first" : "still open"}</span>${s.days != null ? ` in ${s.days} days` : ""}`;
    let reader = "—";
    if (rd) {
      reader = rd.side === "NONE" ? "no side" : `<b>${rd.side.toLowerCase()}</b> since ${esc(rd.since)}, draw ${px(rd.draw)}, protected ${px(rd.protected)}`;
      if (rd.side !== "NONE") {
        mark("rdraw", rd.draw, css("--muted"), "reader draw", 2);
        mark("rprot", rd.protected, css("--muted"), "reader protected", 2);
      }
    }
    $("reveal").hidden = false;
    $("reveal").innerHTML = `<dl>
      <dt>Market</dt><dd><b>${esc(r.market)}</b>, week of ${esc(r.monday)} (close Fri ${esc(r.friday)})</dd>
      <dt>Your call</dt><dd class="${sideCls}">${esc(side.toLowerCase())}${r.recognised ? " · recognised" : ""}</dd>
      <dt>Next week</dt><dd>${wk}</dd>
      <dt>The race</dt><dd>${race}</dd>
      <dt>Control</dt><dd>${s.control == null ? "—" : `${pct(s.control)} of ${s.n_control} random starts; a walk ${pct(s.geo)}`}</dd>
      <dt>Reader v0</dt><dd>${reader}</dd></dl>
      <button class="boxed" id="nextBtn" style="margin-top:8px;width:100%">Next chart (→)</button>`;
    $("nextBtn").onclick = load;
    $("progress").textContent = `${S.data.done + 1} called · ${S.data.total - S.data.done - 1} left`;
  }

  async function totals() {
    let t;
    try { t = await api("/api/weekly/summary"); } catch (e) { return; }
    const row = (name, x) => !x || !x.n ? `<tr><td>${name}</td><td colspan="4" class="muted">no calls yet</td></tr>` :
      `<tr><td>${name}</td><td>${x.n}</td><td>${pct(x.hit)}</td><td>${pct(x.base)}</td><td>${pts(x.excess)} [${pts(x.lo)}, ${pts(x.hi)}]</td></tr>`;
    const conf = Object.entries(t.by_confidence || {}).map(([c, x]) => row(`week, confidence ${c}`, x.week) + row(`race, confidence ${c}`, x.race)).join("");
    $("totals").innerHTML = `<b>Your calls</b> · ${t.sided} with a side of ${t.target} for the bar, ${t.none} no side, ${t.recognised} recognised (left out).
      The bar: the week on your side ${pct(t.bar[0])}-${pct(t.bar[1])}.${t.agree ? ` The reader had a side on ${t.agree.n} of your calls and agreed on ${pct(t.agree.share)}.` : ""}
      <table><tr><th></th><th>n</th><th>Yours</th><th>Base</th><th>Excess (pts) [95%]</th></tr>
      ${row("next week on your side (base: drift)", t.week)}${row("draw first (base: random starts)", t.race)}${conf}</table>
      <p class="muted" style="margin:6px 0 0">With fewer than about 300 calls the interval is wider than the edge it looks for; read the totals then.</p>`;
  }

  // ── wiring ─────────────────────────────────────────────────────────────
  makeChart();
  for (const b of document.querySelectorAll("[data-tf]")) b.onclick = () => show(b.dataset.tf);
  for (const b of document.querySelectorAll("[data-side]")) b.onclick = () => setSide(b.dataset.side);
  for (const b of document.querySelectorAll("[data-c]")) b.onclick = () => setConf(Number(b.dataset.c));
  $("pickDraw").onclick = () => { S.pick = "draw"; S.lineMode = false; syncLevels(); };
  $("pickProt").onclick = () => { S.pick = "prot"; S.lineMode = false; syncLevels(); };
  $("draw").oninput = syncLevels; $("prot").oninput = syncLevels;
  $("lineTool").onclick = () => { S.lineMode = !S.lineMode; $("lineTool").classList.toggle("on", S.lineMode); };
  $("clearLines").onclick = () => { for (const l of S.lines) S.series.removePriceLine(l); S.lines = []; };
  $("save").onclick = save;
  document.addEventListener("keydown", (e) => {
    if (e.target.tagName === "INPUT" && e.target.type !== "checkbox" || e.target.tagName === "TEXTAREA") {
      if (e.key === "Enter" && e.target.tagName === "INPUT") save();
      return;
    }
    const k = e.key.toLowerCase();
    if (k === "b") setSide("BULLISH"); else if (k === "s") setSide("BEARISH"); else if (k === "n") setSide("NONE");
    else if (k === "m") show("MN1"); else if (k === "w") show("W1"); else if (k === "d") show("D1");
    else if (k === "l") $("lineTool").click();
    else if (k === "enter") { e.preventDefault(); S.revealed ? load() : save(); }
    else if (k === "arrowright" && S.revealed) load();
  });
  load().then(totals).catch((e) => { $("msg").textContent = e.message; $("msg").className = "msg err"; });
})();
