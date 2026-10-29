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

  function render() {
    const d = S.data;
    $("weekLabel").textContent = weekLabel(d.week);
    const opens = new Date(d.opens), now = new Date(d.now);
    const state = $("weekState");
    if (d.open) { state.className = "pill open"; state.textContent = `opened ${opens.toLocaleString(undefined, NY)} New York · calls now are late`; }
    else { state.className = "pill ahead"; state.textContent = `opens ${opens.toLocaleString(undefined, NY)} New York · in ${until(opens - now)}`; }
    $("weeks").innerHTML = d.weeks.map((w) => `<option value="${w}" ${w === d.week ? "selected" : ""}>${w === d.default ? "next · " : ""}${weekLabel(w)}</option>`).join("");
    $("rows").innerHTML = d.rows.map((r) => {
      const c = r.call || {};
      const saved = r.call ? `${new Date(c.made_at).toLocaleString(undefined, NY)}${c.late ? '<span class="tag late">late</span>' : ""}` : '<span class="muted">—</span>';
      return `<tr data-inst="${r.instrument}">
        <td><b>${r.instrument}</b></td>
        <td class="num">${fmt(r.price)}</td>
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
    };
  }

  async function load(week) {
    const r = await fetch("/api/context" + (week ? `?week=${week}` : ""));
    const d = await r.json();
    if (!r.ok) { $("rows").innerHTML = `<tr><td colspan="8" class="msg err">${esc(d.error)}</td></tr>`; return; }
    S.data = d; S.week = d.week;
    history.replaceState(null, "", `/context?week=${d.week}`);
    render();
    if (window.ContextScore) window.ContextScore.load();
  }

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
    let html = `<p><b>${t.hits}/${t.final}</b> finished calls closed on their side (${rate}; the costs need ${Math.round(be[0] * 100)}–${Math.round(be[1] * 100)}%).
      Delivered ${t.delivered}, invalidated ${t.invalidated}, of ${t.calls} with a side.
      Paper R on the called markets: context ${r(t.agents.context)}, partial ${r(t.agents.partial)}, control ${r(t.agents.control)}.</p>`;
    for (const w of d.weeks) {
      html += `<h3 style="margin-top:14px">Week of ${esc(w.week)}</h3><table class="calls"><thead><tr><th>Market</th><th>Call</th>
        <th class="num">Week open → close</th><th>Closed its way</th><th>Context</th><th class="num">Walk odds</th>
        <th>Context agent</th><th>Partial</th><th>Control</th></tr></thead><tbody>`;
      for (const x of w.rows) {
        const c = x.call;
        if (x.error) { html += `<tr><td><b>${c.instrument}</b></td><td colspan="8" class="msg err">${esc(x.error)}</td></tr>`; continue; }
        const hit = x.hit == null ? "—" : `${x.hit ? '<span class="up">yes</span>' : '<span class="down">no</span>'}${x.final ? "" : ' <span class="muted">(so far)</span>'}`;
        const ctx = x.outcome ? `${x.outcome} ${when(x.at)}` : "—";
        html += `<tr><td><b>${c.instrument}</b></td><td>${side(c.side)}${c.side !== "NONE" ? ` <span class="muted">${fmt(c.draw)} / ${fmt(c.protected)}</span>` : ""}${c.late ? '<span class="tag late">late</span>' : ""}</td>
          <td class="num">${fmt(x.week_open)} → ${fmt(x.week_close)}</td><td>${hit}</td><td>${esc(ctx)}</td>
          <td class="num">${x.walk == null ? "—" : Math.round(x.walk * 100) + "%"}</td>
          <td>${r(x.agents.context)}</td><td>${r(x.agents.partial)}</td><td>${r(x.agents.control)}</td></tr>`;
      }
      html += "</tbody></table>";
    }
    box.innerHTML = html;
  }
  window.ContextScore = { load };
})();
