// The context page (context-engine Requirement 32.4): the trader's weekly call per market. Saving a call rewrites
// the engine's thesis file; the engine then trades only that side until the draw trades or a D1 candle closes beyond
// the protected swing.
"use strict";

(function () {
  const $ = (id) => document.getElementById(id);
  const esc = (t) => String(t == null ? "" : t).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const NY = { timeZone: "America/New_York", weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", hour12: false };
  const digits = (x) => (x < 10 ? 5 : x < 500 ? 3 : x < 5000 ? 2 : 1);
  const fmt = (x) => (x == null ? "—" : Number(x).toFixed(digits(Math.abs(x))));
  const shift = (iso, days) => { const d = new Date(iso + "T00:00:00Z"); d.setUTCDate(d.getUTCDate() + days); return d.toISOString().slice(0, 10); };
  const S = { week: null, data: null };

  function weekLabel(iso) {
    const d = new Date(iso + "T12:00:00Z");
    return "Week of " + d.toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
  }

  function until(ms) {
    const h = Math.floor(ms / 3.6e6), d = Math.floor(h / 24);
    return d ? `${d}d ${h % 24}h` : `${h}h ${Math.floor(ms / 6e4) % 60}m`;
  }

  // What the levels say against each other and the last price: an error blocks the save, a warning doesn't.
  function check(side, draw, prot, last) {
    if (side === "NONE" || !side) return null;
    if (!Number.isFinite(draw) || !Number.isFinite(prot)) return { err: "Give the draw and the protected swing." };
    if (side === "BULLISH" ? prot >= draw : prot <= draw)
      return { err: `A ${side.toLowerCase()} call's protected swing is ${side === "BULLISH" ? "below" : "above"} its draw.` };
    if (last != null) {
      if (side === "BULLISH" ? last >= draw : last <= draw) return { warn: "Price is already at or beyond the draw." };
      if (side === "BULLISH" ? last <= prot : last >= prot) return { warn: "Price is already beyond the protected swing." };
      const odds = Math.abs(last - prot) / Math.abs(draw - prot);
      return { info: `A random walk reaches the draw first ${Math.round(odds * 100)}% of the time from here.` };
    }
    return null;
  }

  // The brain's call (Algo Mind): its side, its probability of an up week and the share of its 20 nearest past weeks
  // that went up, with whether it agrees with the trader's saved side.
  function brainCell(b, mine) {
    if (!b) return '<span class="muted">—</span>';
    const s = b.call === "BULLISH" ? '<span class="up">Bullish</span>' : b.call === "BEARISH" ? '<span class="down">Bearish</span>' : '<span class="muted">None</span>';
    const agree = mine && mine !== "NONE" && b.call !== "NONE" ? (mine === b.call ? ' <span class="tag" title="you agree">✓ agree</span>' : ' <span class="tag late" title="you differ">≠</span>') : "";
    const p = b.p == null ? "" : ` <span class="muted">${Math.round(b.p * 100)}%</span>`;
    const mem = b.share_up == null ? "" : `<div class="muted" style="font-size:11px">similar weeks up ${Math.round(b.share_up * 100)}%</div>`;
    const other = Object.entries(b.candidates || {}).map(([v, c]) => `<div class="muted" style="font-size:11px">${esc(v)}: ${c.call === "NONE" ? "none" : c.call.toLowerCase()}${c.p == null ? "" : " " + Math.round(c.p * 100) + "%"}</div>`).join("");
    return s + p + agree + mem + other;
  }

  // The reader (the directional state in shadow, Requirement 35.4): the side the week opened with, how it was
  // reached, the weeks checked for a turn, and each day's read up to its verdict.
  const NYD = { timeZone: "America/New_York", weekday: "short", day: "2-digit", month: "short" };
  const day = (iso) => (iso ? new Date(iso).toLocaleDateString(undefined, NYD) : "—");
  const dateOf = (d, opts) => new Date(d + "T12:00:00Z").toLocaleDateString(undefined, { timeZone: "UTC", ...opts });
  const sideTag = (s) => (s === "BULLISH" ? '<span class="up">Bullish</span>' : s === "BEARISH" ? '<span class="down">Bearish</span>' : '<span class="muted">No side</span>');
  const drawText = (dr) => (dr ? `${esc(dr.name)} ${fmt(Math.min(dr.near, dr.far))}–${fmt(Math.max(dr.near, dr.far))} (CE ${fmt(dr.ce)})` : "none found");

  function readerCell(r) {
    if (!r) return '<span class="muted">—</span>';
    if (r.error) return `<span class="muted" title="${esc(r.error)}">not read</span>`;
    const o = r.open, n = r.now, orders = r.reads.filter((x) => x.order).length;
    const now = n.side !== o.side || n.since !== o.since ? ` <span class="muted">→ now</span> ${sideTag(n.side)}` : "";
    const ord = orders ? `<div class="muted" style="font-size:11px">${orders} order${orders > 1 ? "s" : ""} this week</div>` : "";
    return sideTag(o.side) + now + ord;
  }

  function record(s, label) {
    if (s.state === "ACTIVE") {
      const ignored = s.ignored.length ? ` Turns against it, ignored as manipulation: ${s.ignored.map((x) => `${x.side.toLowerCase()} ${day(x.at)}`).join(", ")}.` : "";
      return `<div><b>${label}:</b> ${sideTag(s.side)} since ${day(s.since)} · draw ${drawText(s.draw)} · protected ${fmt(s.protected)}</div>
        <ul class="ev">${s.evidence.map(([t, at]) => `<li>${esc(t)} <span class="muted">(${day(at)})</span></li>`).join("")}</ul>
        <div class="muted">Proved wrong if ${esc(s.invalidation)}.${ignored}</div>`;
    }
    const e = s.ended;
    return `<div><b>${label}:</b> ${sideTag("NONE")}: ${e ? `the last side was ${esc(e[0])} ${day(e[1])}` : "no turn in the history read"}. It waits for the next turn, and trades nothing until then.</div>`;
  }

  function chain(c) {
    const head = c.turn ? '<b class="ok">turn</b>' : '<span class="muted">no turn</span>';
    return head + `<ol class="chain">${c.steps.map(([n, ok, t]) => `<li class="${ok ? "ok" : "no"}"><span class="mk">${ok ? "✓" : "✗"}</span><b>${esc(n)}</b>: ${esc(t)}</li>`).join("")}</ol>`;
  }

  function dayRead(r) {
    const groups = [];
    for (const [step, text] of r.steps) {
      if (step || !groups.length) groups.push([step, [text]]);
      else groups[groups.length - 1][1].push(text);
    }
    return `<div class="read"><b>${dateOf(r.day, { weekday: "short", day: "2-digit", month: "short" })}</b>
      <span class="verdict ${r.order ? "order" : "none"}">${esc(r.verdict)}</span>${r.so_far ? ' <span class="tag late">so far</span>' : ""}
      <dl>${groups.map(([s, ts]) => `<dt>${esc(s)}</dt><dd>${ts.map(esc).join("<br>")}</dd>`).join("")}</dl></div>`;
  }

  function readerCard(r) {
    if (r.error) return `<details class="rd"><summary><b>${r.market}</b> <span class="msg err">${esc(r.error)}</span></summary></details>`;
    const o = r.open, n = r.now, orders = r.reads.filter((x) => x.order);
    const changed = n.side !== o.side || n.since !== o.since;
    const sum = o.state === "ACTIVE" ? `${sideTag(o.side)} since ${day(o.since)} · draw ${esc(o.draw ? o.draw.name : "none")}`
      : `${sideTag("NONE")}${o.ended ? ` <span class="muted">· the last side ${esc(o.ended[0])} ${day(o.ended[1])}</span>` : ""}`;
    const ord = orders.length ? ` · <span class="verdict order">${orders.map((x) => dateOf(x.day, { weekday: "short" })).join(", ")}: ORDER</span>`
      : r.reads.length ? ' <span class="muted">· no order</span>' : "";
    const spans = r.spans.length ? `<div class="muted spans">Its last sides: ${r.spans.map((sp) => `${sp.side.toLowerCase()} from ${day(sp.since)}, ${sp.reason}${sp.end ? " " + day(sp.end) : ""}`).join(" · ")}</div>` : "";
    return `<details class="rd" ${o.state === "ACTIVE" || n.state === "ACTIVE" || orders.length ? "open" : ""}>
      <summary><b>${r.market}</b> ${sum}${changed ? ` <span class="muted">→ now</span> ${sideTag(n.side)}` : ""}${ord}</summary>
      <div class="rb">
        <h4>1 · The side (W1 and D1, closed candles only)</h4>
        ${record(o, "At the week's open")}
        ${changed ? record(n, `At ${new Date(r.as_of).toLocaleString(undefined, NY)} New York`) : ""}
        ${spans}
        <h4>2 · The last four weeks, checked for a turn</h4>
        <table class="calls wk"><thead><tr><th>Week</th><th>Buy side</th><th>Sell side</th></tr></thead>
          <tbody>${r.weeks.map((c) => `<tr><td>${dateOf(c.week, { day: "2-digit", month: "short" })}</td><td>${chain(c.BULLISH)}</td><td>${chain(c.BEARISH)}</td></tr>`).join("")}</tbody></table>
        <h4>3 · Each day, on the side only: the D1 setup, then C3</h4>
        ${!r.reads.length ? '<span class="muted">No day of this week has opened yet.</span>'
          : r.reads.every((x) => x.side === "NONE")
            ? `<div class="read"><span class="verdict none">${r.reads.map((x) => dateOf(x.day, { weekday: "short" })).join(", ")}: NO TRADE, no live narrative</span> <span class="muted">(no side, so no day is read further)</span></div>`
            : r.reads.map(dayRead).join("")}
      </div></details>`;
  }

  function renderReader(d) {
    const rd = d.reader;
    $("readerState").innerHTML = rd
      ? `reader ${esc(rd.version)} · made ${new Date(rd.made_at).toLocaleString(undefined, NY)} New York`
      : '<span class="muted">the reader hasn’t read this week yet</span>';
    $("reader").innerHTML = rd ? d.rows.map((r) => (r.reader ? readerCard(r.reader) : "")).join("")
      : '<span class="muted">Run the reader to see how it chose: the terminal’s bars, nine markets.</span>';
  }

  function render() {
    const d = S.data;
    renderReader(d);
    $("weekLabel").textContent = weekLabel(d.week);
    const opens = new Date(d.opens), now = new Date(d.now);
    const state = $("weekState");
    if (d.open) { state.className = "pill open"; state.textContent = `opened ${opens.toLocaleString(undefined, NY)} New York · calls now are late`; }
    else { state.className = "pill ahead"; state.textContent = `opens ${opens.toLocaleString(undefined, NY)} New York · in ${until(opens - now)}`; }
    $("weeks").innerHTML = d.weeks.map((w) => `<option value="${w}" ${w === d.week ? "selected" : ""}>${w === d.default ? "next · " : ""}${weekLabel(w)}</option>`).join("");
    const b = d.brain;
    $("brainState").innerHTML = b
      ? `brain ${esc(b.version)}${b.candidates && b.candidates.length ? ` (beside it: ${b.candidates.map(esc).join(", ")})` : ""} · made ${new Date(b.made_at).toLocaleString(undefined, NY)} New York${b.provisional ? ' · <span class="tag late">provisional: rerun after Friday’s close</span>' : ""}`
      : '<span class="muted">no brief for this week yet</span>';
    const notes = [...(b ? b.notes.map((n) => "Brain: " + n) : []), ...d.notes.map((n) => "Your calls: " + n)];
    $("notes").innerHTML = notes.map((n) => `<div class="msg warn">${esc(n)}</div>`).join("");
    $("rows").innerHTML = d.rows.map((r) => {
      const c = r.call || {};
      const saved = r.call ? `${new Date(c.made_at).toLocaleString(undefined, NY)}${c.late ? '<span class="tag late">late</span>' : ""}` : '<span class="muted">—</span>';
      return `<tr data-inst="${r.instrument}">
        <td><b>${r.instrument}</b></td>
        <td class="num">${fmt(r.price)}</td>
        <td class="brain">${brainCell(r.brain, c.side)}</td>
        <td>${readerCell(r.reader)}</td>
        <td><select class="side ${esc(c.side || "")}">${["", "BULLISH", "BEARISH", "NONE"].map((s) => `<option value="${s}" ${s === (c.side || "") ? "selected" : ""}>${s ? s[0] + s.slice(1).toLowerCase() : "—"}</option>`).join("")}</select></td>
        <td class="num"><input type="number" step="any" class="draw" value="${c.draw ?? ""}"></td>
        <td class="num"><input type="number" step="any" class="prot" value="${c.protected ?? ""}"></td>
        <td class="hide-s"><input class="note" value="${esc(c.note || "")}" placeholder="the read, in a line"></td>
        <td><button class="boxed save">Save</button></td>
        <td class="saved">${saved}<div class="msg"></div></td>
      </tr>`;
    }).join("");
    for (const tr of $("rows").querySelectorAll("tr")) wire(tr);
  }

  function wire(tr) {
    const inst = tr.dataset.inst, row = S.data.rows.find((r) => r.instrument === inst);
    const side = tr.querySelector(".side"), draw = tr.querySelector(".draw"), prot = tr.querySelector(".prot");
    const msg = tr.querySelector(".msg");
    const show = () => {
      side.className = "side " + side.value;
      const none = side.value === "NONE" || !side.value;
      draw.disabled = prot.disabled = side.value === "NONE";
      const res = none ? null : check(side.value, parseFloat(draw.value), parseFloat(prot.value), row.price);
      msg.className = "msg " + (res ? (res.err ? "err" : res.warn ? "warn" : "") : "");
      msg.textContent = res ? (res.err || res.warn || res.info) : "";
      return res;
    };
    side.onchange = draw.oninput = prot.oninput = show;
    show();
    tr.querySelector(".save").onclick = async () => {
      const res = show();
      if (!side.value) { msg.className = "msg err"; msg.textContent = "Pick a side, or None."; return; }
      if (res && res.err) return;
      const body = { week: S.week, instrument: inst, side: side.value, draw: draw.value, protected: prot.value, note: tr.querySelector(".note").value };
      const r = await fetch("/api/context/call", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      const out = await r.json();
      if (!r.ok) { msg.className = "msg err"; msg.textContent = out.error || "Not saved."; return; }
      row.call = out.call;
      tr.querySelector(".saved").innerHTML = `${new Date(out.call.made_at).toLocaleString(undefined, NY)}${out.call.late ? '<span class="tag late">late</span>' : ""}<div class="msg ok">saved</div>`;
      tr.querySelector(".brain").innerHTML = brainCell(row.brain, out.call.side);
    };
  }

  async function load(week) {
    const r = await fetch("/api/context" + (week ? `?week=${week}` : ""));
    const d = await r.json();
    if (!r.ok) { $("rows").innerHTML = `<tr><td colspan="9" class="msg err">${esc(d.error)}</td></tr>`; return; }
    S.data = d; S.week = d.week;
    history.replaceState(null, "", `/context?week=${d.week}`);
    render();
    if (window.ContextScore) window.ContextScore.load();
  }

  $("runBrain").onclick = async () => {
    const btn = $("runBrain");
    btn.disabled = true; btn.textContent = "Reading the markets…";
    try {
      const r = await fetch("/api/context/brief", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ week: S.week }) });
      const d = await r.json();
      if (!r.ok) { $("brainState").innerHTML = `<span class="msg err">${esc(d.error)}</span>`; return; }
      S.data = d; render();
    } finally { btn.disabled = false; btn.textContent = "Run the brain"; }
  };
  $("runReader").onclick = async () => {
    const btn = $("runReader");
    btn.disabled = true; btn.textContent = "Reading the terminal…";
    try {
      const r = await fetch("/api/context/reader", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ week: S.week }) });
      const d = await r.json();
      if (!r.ok) { $("readerState").innerHTML = `<span class="msg err">${esc(d.error)}</span>`; return; }
      S.data = d; render();
      if (window.ContextScore) window.ContextScore.load();
    } finally { btn.disabled = false; btn.textContent = "Run the reader"; }
  };
  $("prev").onclick = () => load(shift(S.week, -7));
  $("next").onclick = () => load(shift(S.week, 7));
  $("weeks").onchange = (e) => load(e.target.value);
  load(new URLSearchParams(location.search).get("week"));
})();

// The scorecard (Requirement 32.6): every called week, its close against the call, the context's outcome, and the
// paper agents' R in that market and week: the context agent against the two controls.
(function () {
  const $ = (id) => document.getElementById(id);
  const esc = (t) => String(t == null ? "" : t).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const digits = (x) => (x < 10 ? 5 : x < 500 ? 3 : x < 5000 ? 2 : 1);
  const fmt = (x) => (x == null ? "—" : Number(x).toFixed(digits(Math.abs(x))));
  const r = (a) => (a && a.n ? `<span class="${a.r >= 0 ? "up" : "down"}">${a.r >= 0 ? "+" : ""}${a.r.toFixed(2)}R</span> <span class="muted">(${a.n})</span>` : '<span class="muted">—</span>');
  const when = (iso) => (iso ? new Date(iso).toLocaleString(undefined, { timeZone: "America/New_York", weekday: "short", hour: "2-digit", minute: "2-digit", hour12: false }) : "");
  const side = (s) => (s === "BULLISH" ? '<span class="up">Bullish</span>' : s === "BEARISH" ? '<span class="down">Bearish</span>' : "None");

  async function load() {
    const box = $("score");
    const res = await fetch("/api/context/scorecard");
    const d = await res.json();
    if (!res.ok) { box.innerHTML = `<span class="muted">${esc(d.error)}</span>`; return; }
    if (!d.weeks.length) { box.innerHTML = '<span class="muted">No week with calls has opened yet.</span>'; return; }
    const t = d.totals, be = t.break_even;
    const rate = t.hit_rate == null ? "—" : `${Math.round(t.hit_rate * 100)}%`;
    const pct = (x) => (x.hit_rate == null ? "—" : `${Math.round(x.hit_rate * 100)}%`);
    let html = `<p><b>You: ${t.hits}/${t.final}</b> finished calls closed on their side (${rate}; the costs need ${Math.round(be[0] * 100)}–${Math.round(be[1] * 100)}%).
      Delivered ${t.delivered}, invalidated ${t.invalidated}, of ${t.calls} with a side.<br>
      <b>Brain: ${t.brain.hits}/${t.brain.final}</b> (${pct(t.brain)}) · <b>you and the brain agreeing: ${t.agree.hits}/${t.agree.final}</b> (${pct(t.agree)})
      · <b>reader: ${t.reader.hits}/${t.reader.final}</b> (${pct(t.reader)}; on the side each week opened with).<br>
      Paper R on your called markets: ${Object.entries(t.agents).map(([k, v]) => `${k} ${r(v)}`).join(", ")}.</p>`;
    const agents = Object.keys(t.agents);
    const yes = (h, final) => (h == null ? "—" : `${h ? '<span class="up">yes</span>' : '<span class="down">no</span>'}${final ? "" : ' <span class="muted">(so far)</span>'}`);
    for (const w of d.weeks) {
      html += `<h3 style="margin-top:14px">Week of ${esc(w.week)}</h3><table class="calls"><thead><tr><th>Market</th><th>Your call</th>
        <th class="num">Week open → close</th><th>Closed your way</th><th>Brain</th><th>Closed its way</th><th>Reader</th><th>Closed its way</th><th>Context</th><th class="num">Walk odds</th>
        ${agents.map((a) => `<th>${esc(a[0].toUpperCase() + a.slice(1))}</th>`).join("")}</tr></thead><tbody>`;
      for (const x of w.rows) {
        const c = x.call, b = x.brain, rd = x.reader;
        if (x.error) { html += `<tr><td><b>${x.market}</b></td><td colspan="${9 + agents.length}" class="msg err">${esc(x.error)}</td></tr>`; continue; }
        const ctx = x.outcome ? `${x.outcome} ${when(x.at)}` : "—";
        const mine = c ? `${side(c.side)}${c.side !== "NONE" ? ` <span class="muted">${fmt(c.draw)} / ${fmt(c.protected)}</span>` : ""}${c.late ? '<span class="tag late">late</span>' : ""}` : '<span class="muted">—</span>';
        const brain = b ? `${side(b.call)}${b.p == null ? "" : ` <span class="muted">${Math.round(b.p * 100)}%</span>`}` : '<span class="muted">—</span>';
        html += `<tr><td><b>${x.market}</b></td><td>${mine}</td>
          <td class="num">${fmt(x.week_open)} → ${fmt(x.week_close)}</td><td>${yes(x.hit, x.final)}</td>
          <td>${brain}</td><td>${yes(b ? b.hit : null, x.final)}</td>
          <td>${rd ? side(rd.call) : '<span class="muted">—</span>'}</td><td>${yes(rd ? rd.hit : null, x.final)}</td><td>${esc(ctx)}</td>
          <td class="num">${x.walk == null ? "—" : Math.round(x.walk * 100) + "%"}</td>
          ${agents.map((a) => `<td>${r(x.agents[a])}</td>`).join("")}</tr>`;
      }
      html += "</tbody></table>";
    }
    box.innerHTML = html;
  }
  window.ContextScore = { load };
})();
