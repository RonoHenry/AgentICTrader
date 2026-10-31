// The charts' shell (market-narrative Requirement 15, update 2026-10-15), shared by the You and Engine pages:
// the mode switch, the instrument tabs and the watchlist, laid out as TradingView's. The watchlist is read as of
// the page's own clock: the You mode names its instrument (the server reads that day's revealed time), the
// Engine mode names the session's time.
"use strict";

(function () {
  const $ = (id) => document.getElementById(id);
  const esc = (t) => String(t == null ? "" : t).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const signed = (x, d) => (x == null ? "" : (x >= 0 ? "+" : "−") + Math.abs(x).toFixed(d));

  const Shell = {
    mode: null, inst: null, instruments: [], rows: {}, onPick: null, query: null, timer: null,

    async init({ mode, inst, onPick }) {
      this.mode = mode; this.inst = inst; this.onPick = onPick;
      try { this.instruments = (await (await fetch("/api/instruments")).json()).instruments || []; } catch (e) { this.instruments = []; }
      if (!this.inst && this.instruments.length) this.inst = this.instruments[0];
      this.render();
    },
    setInstrument(inst) { this.inst = inst; this.render(); },
    // The watchlist, coalesced: "inst=XAUUSD" (You) or "t=<wall seconds>" (Engine).
    refresh(query) {
      this.query = query;
      if (this.timer) return;
      this.timer = setTimeout(async () => {
        this.timer = null;
        try {
          const r = await (await fetch("/api/watchlist?" + this.query)).json();
          if (r.rows) { this.rows = Object.fromEntries(r.rows.map((x) => [x.instrument, x])); this.render(); }
        } catch (e) { /* the chart works without it */ }
      }, 200);
    },
    render() {
      const bar = $("shell");
      if (bar) {
        const q = this.inst ? `?inst=${encodeURIComponent(this.inst)}` : "";
        bar.innerHTML = `<span class="modes" title="Who is reading the chart">
            <a href="/${q}" class="${this.mode === "you" ? "on" : ""}">You</a><a href="/engine${q}" class="${this.mode === "engine" ? "on" : ""}">Engine</a><a href="/context">Context</a></span>` +
          this.instruments.map((i) => {
            const r = this.rows[i] || {};
            const cls = r.change == null ? "" : r.change >= 0 ? "up" : "down";
            return `<button class="itab${i === this.inst ? " on" : ""}" data-inst="${esc(i)}"><b>${esc(i)}</b>` +
                   `<span class="${cls}">${r.change_pct == null ? "" : signed(r.change_pct, 2) + "%"}</span></button>`;
          }).join("");
        for (const b of bar.querySelectorAll(".itab")) b.onclick = () => this.pick(b.dataset.inst);
      }
      const box = $("watchlist");
      if (box) {
        box.innerHTML = `<table class="wl"><tr><th>Symbol</th><th>Last</th><th>Chg</th><th>Chg%</th></tr>` +
          this.instruments.map((i) => {
            const r = this.rows[i] || {}, d = r.digits || 5, cls = r.change == null ? "" : r.change >= 0 ? "up" : "down";
            return `<tr class="${i === this.inst ? "on" : ""}" data-inst="${esc(i)}"><td>${esc(i)}</td>` +
                   `<td>${r.last == null ? "—" : r.last.toFixed(d)}</td><td class="${cls}">${signed(r.change, d)}</td>` +
                   `<td class="${cls}">${r.change_pct == null ? "" : signed(r.change_pct, 2) + "%"}</td></tr>`;
          }).join("") + `</table>`;
        for (const tr of box.querySelectorAll("tr[data-inst]")) tr.onclick = () => this.pick(tr.dataset.inst);
      }
    },
    pick(inst) { if (inst !== this.inst && this.onPick) this.onPick(inst); },
  };

  window.Shell = Shell;
})();
