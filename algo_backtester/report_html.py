"""The HTML run report (Req 11): report.html, one file that opens offline.

    write_report_inputs(run_dir, result.journal, candles, cfg.strategy.entry_tf)   # context.json, candles.json
    write_html_report(run_dir)                                                     # run_dir/report.html
    html = render(build_forward_test(trades, candles, Timeframe.M15, source="paper_trades.json"))

A report is drawn only from what the run recorded, never by re-running the
engine (Req 11.6):
- journal.csv: every row, trades and skipped intents (Req 11.4);
- context.json: the TradeContext of each order intent (entry array, draw on
  liquidity, swept level, killzone);
- candles.json: the entry-timeframe candles, cut from the run's own data
  around its decisions, with the chart window lengths;
- manifest.json and summary.json: the header and the summary (Req 11.2, 11.3).

Everything is embedded: the data as JSON, and the charts drawn as SVG by a
small inline script. No library, server or network is needed (Req 11.1).

Each row with a setup gets a chart window (Req 11.5). It runs from
``bars_before`` bars before the decision bar to ``bars_after`` bars after the
bar of its close, or of the decision when it never closed. The chart marks:
- the decision, entry, stop and target, and the fill and exit;
- the entry array, the draw on liquidity and the swept level, where recorded;
- the killzones, shaded.

The same page renders a paper forward test's trades file (Req 11.7). Its
trades become rows, with candles from the store, and no context: the paper
broker doesn't record it.

Validates: Requirements 11.1-11.7 (.kiro/specs/algo-backtester/requirements.md)
"""
from __future__ import annotations

import csv
import html
import json
from bisect import bisect_left, bisect_right
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence
from zoneinfo import ZoneInfo

from algo_backtester.metrics import Stats
from algo_backtester.report import stats_cells, stats_from_json
from algo_backtester.simulation import JournalRow
from liquidity_engine.models import KillzoneWindow, Timeframe
from liquidity_engine.utils.time_utils import KILLZONE_WINDOWS, get_killzone

__all__ = ["build_forward_test", "build_from_run_dir", "render", "write_html_report", "write_report_inputs"]

UTC = timezone.utc
_NY = ZoneInfo("America/New_York")
_MINUTES = {Timeframe.M1: 1, Timeframe.M3: 3, Timeframe.M5: 5, Timeframe.M15: 15}   # entry timeframes
_FILTERS = ("outcome", "decision", "instrument", "grade", "killzone")


# ── what a run records for its report ──────────────────────────────────────

def write_report_inputs(run_dir: Path, journal: Sequence[JournalRow], candles: Mapping[str, Sequence[Any]],
                        entry_tf: Timeframe, bars_before: int = 60, bars_after: int = 20) -> None:
    """context.json and candles.json: the recorded context of each order
    intent, and the entry-timeframe candles its charts need (``candles``:
    each instrument's bars, with timestamp/open/high/low/close, oldest first)."""
    run_dir = Path(run_dir)
    context = [{"t": _iso(r.t), "instrument": r.instrument, "setup_id": r.setup_id, "context": asdict(r.context)}
               for r in sorted(journal, key=lambda r: (r.t, r.instrument)) if r.context is not None]
    (run_dir / "context.json").write_text(json.dumps(context, indent=1) + "\n", encoding="utf-8", newline="\n")

    step = timedelta(minutes=_MINUTES[entry_tf])
    spans: dict[str, tuple[datetime, datetime]] = {}
    for row in journal:
        if row.intent is None:
            continue
        end = row.trade.closed_at if row.trade is not None else row.t
        lo, hi = spans.get(row.instrument, (row.t, end))
        spans[row.instrument] = (min(lo, row.t), max(hi, end))
    cut = {}
    for instrument, (first, last) in sorted(spans.items()):
        lo, hi = first - (bars_before + 2) * step, last + (bars_after + 2) * step
        cut[instrument] = [[_iso(b.timestamp), b.open, b.high, b.low, b.close]
                           for b in candles.get(instrument, ()) if lo <= b.timestamp <= hi]
    body = {"timeframe": entry_tf.value, "bars_before": bars_before, "bars_after": bars_after, "instruments": cut}
    (run_dir / "candles.json").write_text(json.dumps(body) + "\n", encoding="utf-8", newline="\n")


def write_html_report(run_dir: Path) -> Path:
    path = Path(run_dir) / "report.html"
    path.write_text(render(build_from_run_dir(run_dir)), encoding="utf-8", newline="\n")
    return path


# ── the model the page renders ─────────────────────────────────────────────

def build_from_run_dir(run_dir: Path) -> dict:
    run_dir = Path(run_dir)

    def read(name: str) -> Any:
        return json.loads((run_dir / name).read_text(encoding="utf-8"))

    manifest, summary, candles = read("manifest.json"), read("summary.json"), read("candles.json")
    contexts = {(c["t"], c["instrument"]): c["context"] for c in read("context.json")}
    with (run_dir / "journal.csv").open(encoding="utf-8", newline="") as fh:
        journal = list(csv.DictReader(fh))

    data = next(iter(manifest["data"].values()), {})
    header = [
        ("Run", manifest["run_id"][:12]),
        ("Broker profile", manifest["broker_profile"]),
        ("Costs from", manifest["instrument_spec_source"] or "unknown"),
        ("Variant", manifest["variant"] or "base"),
        ("Data", f"{data.get('start', '?')[:10]} to {data.get('end', '?')[:10]} (UTC, end exclusive)"),
        ("Instruments", ", ".join(manifest["data"])),
        ("Study", f"{manifest['study']}, hold-out from {manifest['holdout_start']}"
                  + (", FINAL VALIDATION" if manifest["final_validation"] else "")),
        ("Code", f"{manifest['git_commit'][:12]} ({'dirty' if manifest['git_dirty'] else 'clean'})"),
        ("Engine", manifest["engine_code_fingerprint"][:12]),
        ("AI modifiers", manifest["ai_modifiers"]),
        ("News filter", manifest["news_filter"]),
    ]
    charts = _Charts(candles)
    rows = [_journal_row(n, r, contexts.get((r["t"], r["instrument"])), charts) for n, r in enumerate(journal)]
    return _model(f"Backtest {manifest['run_id'][:12]}", header, rows, charts,
                  summary={**summary, "min_trades": manifest["run_config"]["report"]["min_trades"]})


def build_forward_test(trades: Sequence[Mapping[str, Any]], candles: Mapping[str, Sequence[Any]],
                       entry_tf: Timeframe, source: str, bars_before: int = 60, bars_after: int = 20) -> dict:
    """The paper broker's trades (its state file) as report rows."""
    charts = _Charts({"timeframe": entry_tf.value, "bars_before": bars_before, "bars_after": bars_after,
                      "instruments": {i: [[_iso(b.timestamp), b.open, b.high, b.low, b.close] for b in bars]
                                      for i, bars in candles.items()}})
    rows = []
    for n, trade in enumerate(sorted(trades, key=lambda t: t["placed_at"])):
        placed = datetime.fromisoformat(trade["placed_at"]).astimezone(UTC)
        closed = _dt(trade.get("closed_at"))
        rows.append(_row(
            n, t=placed, instrument=trade["instrument"], setup_id=trade.get("setup_id"), grade=None,
            decision="EXECUTE", reason="", killzone=None, time_window=None, direction=trade["direction"],
            entry=trade.get("entry"), stop=trade.get("stop_loss"), target=trade.get("take_profit"),
            order_id=trade["trade_id"], kind=trade.get("kind"),
            outcome=trade.get("exit_reason") or ("OPEN" if trade.get("status") != "CLOSED" else None),
            fill=(_dt(trade.get("filled_at")), trade.get("fill_price")), exit=(closed, trade.get("exit_price")),
            gross_r=trade.get("gross_r"), net_r=trade.get("net_r"), cost_r=None, context=None, charts=charts,
            has_setup=True,
        ))
    header = [("Source", f"paper forward test: {source}"), ("Trades", str(len(rows))),
              ("Instruments", ", ".join(sorted({r["instrument"] for r in rows}))),
              ("Note", "R as the paper broker recorded it; no engine context is recorded live")]
    return _model(f"Forward test: {source}", header, rows, charts, summary=None)


def _journal_row(n: int, r: Mapping[str, str], context: Optional[dict], charts: "_Charts") -> dict:
    t = datetime.fromisoformat(r["t"])
    costs = [_f(r[k]) for k in ("cost_r_spread", "cost_r_slippage", "cost_r_commission")]
    return _row(
        n, t=t, instrument=r["instrument"], setup_id=r["setup_id"] or None, grade=r["grade"] or None,
        decision=r["decision"], reason=r["reason"], killzone=r["killzone"] or None,
        time_window=r["time_window"] or None, direction=r["direction"] or None, entry=_f(r["entry"]),
        stop=_f(r["stop"]), target=_f(r["target"]), order_id=r["order_id"] or None, kind=r["order_kind"] or None,
        outcome=r["exit_reason"] or None, fill=(_dt(r["filled_at"]), _f(r["fill"])),
        exit=(_dt(r["closed_at"]), _f(r["exit"])), gross_r=_f(r["gross_r"]), net_r=_f(r["net_r"]),
        cost_r=sum(costs) if None not in costs else None, context=context, charts=charts,
        has_setup=bool(r["direction"]),
    )


def _row(n: int, *, t: datetime, instrument: str, setup_id, grade, decision: str, reason: str, killzone,
         time_window, direction, entry, stop, target, order_id, kind, outcome, fill: tuple, exit: tuple,
         gross_r, net_r, cost_r, context, charts: "_Charts", has_setup: bool) -> dict:
    if killzone is None:
        window_name = get_killzone(t)
        killzone = None if window_name == KillzoneWindow.NONE else window_name.value
    row = {
        "id": n, "t": _iso(t), "instrument": instrument, "setup_id": setup_id, "grade": grade,
        "decision": decision, "reason": reason, "killzone": killzone, "time_window": time_window,
        "direction": direction, "entry": entry, "stop": stop, "target": target, "order_id": order_id,
        "kind": kind, "outcome": outcome, "gross_r": gross_r, "net_r": net_r, "cost_r": cost_r,
        "context": context, "window": None, "bands": [], "markers": None,
    }
    if not has_setup:
        return row
    fill_at, fill_price = fill
    exit_at, exit_price = exit
    row["markers"] = {
        "decision": _iso(t), "entry": entry, "stop": stop, "target": target,
        "fill": [_iso(fill_at), fill_price] if fill_at is not None and fill_price is not None else None,
        "exit": [_iso(exit_at), exit_price] if exit_at is not None and exit_price is not None else None,
        "closed": _iso(exit_at) if exit_at is not None else None,
    }
    row["window"] = charts.window(instrument, t, exit_at)
    row["bands"] = charts.killzones(row["window"]) if row["window"] else []
    return row


class _Charts:
    """Chart windows over the recorded candles."""

    def __init__(self, candles: Mapping[str, Any]) -> None:
        self.timeframe = Timeframe(candles["timeframe"])
        self.step = timedelta(minutes=_MINUTES[self.timeframe])
        self.before, self.after = candles["bars_before"], candles["bars_after"]
        self.bars = candles["instruments"]
        self._times = {i: [datetime.fromisoformat(b[0]) for b in bars] for i, bars in self.bars.items()}

    def window(self, instrument: str, decision: datetime, closed: Optional[datetime]) -> Optional[list[str]]:
        times = self._times.get(instrument)
        if not times:
            return None
        decided = max(0, bisect_left(times, decision) - 1)              # the bar closing at the decision
        ended = bisect_right(times, closed) - 1 if closed is not None else decided
        lo, hi = max(0, decided - self.before), min(len(times) - 1, max(decided, ended) + self.after)
        return [_iso(times[lo]), _iso(times[hi])]

    def killzones(self, window: Sequence[str]) -> list[list[str]]:
        start, end = datetime.fromisoformat(window[0]), datetime.fromisoformat(window[1]) + self.step
        bands, day = [], start.astimezone(_NY).date() - timedelta(days=1)
        while day <= end.astimezone(_NY).date():
            for name, (opens, closes) in KILLZONE_WINDOWS.items():
                a = datetime.combine(day, opens, tzinfo=_NY).astimezone(UTC)
                b = datetime.combine(day, closes, tzinfo=_NY).astimezone(UTC)
                if a < end and b > start:
                    bands.append([_iso(max(a, start)), _iso(min(b, end)), name.value])
            day += timedelta(days=1)
        return sorted(bands)


def _model(title: str, header: list, rows: list[dict], charts: _Charts, summary: Optional[dict]) -> dict:
    used = {r["instrument"] for r in rows if r["window"]}
    filters = {name: sorted({str(r[name]) for r in rows if r[name] is not None}) for name in _FILTERS}
    return {"title": title, "header": header, "rows": rows, "filters": filters, "summary": summary,
            "timeframe": charts.timeframe.value,
            "candles": {i: bars for i, bars in sorted(charts.bars.items()) if i in used}}


# ── the page ───────────────────────────────────────────────────────────────

def render(model: Mapping[str, Any]) -> str:
    """The whole page: header, summary, trade explorer and chart, one file."""
    payload = json.dumps(_compact(model), separators=(",", ":"), sort_keys=True).replace("</", "<\\/")
    header = "".join(f"<tr><th>{html.escape(k)}</th><td>{html.escape(v)}</td></tr>" for k, v in model["header"])
    return (_PAGE
            .replace("%TITLE%", html.escape(model["title"]))
            .replace("%HEADER%", header)
            .replace("%SUMMARY%", _summary_html(model))
            .replace("%DATA%", payload))


def _compact(model: Mapping[str, Any]) -> dict:
    """The embedded form of the model. A year's journal is ~100k rows: nearly
    all no-trade rows with a few repeated grader reasons, and runs of IN_TRADE
    rows repeating one setup's context. So rows drop their empty fields
    (``fields`` lists them all), and each distinct reason and context is stored
    once, in ``reasons`` and ``contexts``; a row holds its index there."""
    def key(context: Any) -> str:
        return json.dumps(context, sort_keys=True)

    reasons = sorted({r["reason"] for r in model["rows"]})
    contexts = sorted({key(r["context"]) for r in model["rows"] if r["context"] is not None})
    reason_at = {reason: n for n, reason in enumerate(reasons)}
    context_at = {context: n for n, context in enumerate(contexts)}

    def compact(row: Mapping[str, Any]) -> dict:
        out = {k: v for k, v in row.items() if v not in (None, [])}
        out["reason"] = reason_at[row["reason"]]
        if row["context"] is not None:
            out["context"] = context_at[key(row["context"])]
        return out

    return {**model, "rows": [compact(r) for r in model["rows"]], "reasons": reasons,
            "contexts": [json.loads(c) for c in contexts], "fields": sorted({k for r in model["rows"] for k in r})}


def _summary_html(model: Mapping[str, Any]) -> str:
    closed = sorted((r for r in model["rows"] if r["net_r"] is not None),
                    key=lambda r: (r["markers"] or {}).get("closed") or r["t"])
    net = [r["net_r"] for r in closed]
    parts = ['<div class="charts">', _equity_svg(net), _histogram_svg(net), "</div>"]
    summary = model["summary"]
    if summary is None:
        total = sum(net)
        parts.append(f"<p>{len(net)} closed trades, {total:+.2f}R net in total. "
                     "Breakdowns need a backtest run's summary.</p>")
        return "".join(parts)

    min_trades = summary["min_trades"]
    overall = stats_from_json(summary["overall"])
    parts.append(f'<p class="legend"><span class="insufficient">Insufficient evidence</span>: buckets with '
                 f"n &lt; {min_trades} trades are greyed and labelled; they are not findings (Req 8.4).</p>")
    parts.append(_stats_html([("all trades", overall)], "", wide=True))
    if overall.cost_share is not None:
        parts.append(f"<p>Costs took {overall.cost_share:.0%} of gross R (cost share).</p>")
    else:
        parts.append("<p>Cost share: none to report (gross R was not positive).</p>")
    counts = summary["counts"]
    decisions = ", ".join(f"{html.escape(k)} {v}" for k, v in counts["decisions"].items())
    parts.append(f"<p>Journal rows {counts['rows']}; orders {counts['orders']}: {counts['filled']} filled, "
                 f"{counts['unfilled']} never filled, {counts['open_at_end']} open at the end. "
                 f"Decisions: {decisions}.</p>")
    for name, buckets in summary["breakdowns"].items():
        parts.append(f"<h3>By {html.escape(name.replace('_', ' '))}</h3>")
        parts.append(_stats_html([(k, stats_from_json(v)) for k, v in buckets.items()], name))
    return "".join(parts)


_SHORT = ("trades", "win rate", "avg net R", "expectancy R (95% CI)", "profit factor", "max DD R", "cost share")
_WIDE = ("trades", "win rate", "avg gross R", "avg net R", "expectancy R (95% CI)", "profit factor", "max DD R",
         "max DD %", "losing streak", "avg hold (min)", "avg cost R", "cost share")


def _stats_html(rows: Sequence[tuple[str, Stats]], first: str, wide: bool = False) -> str:
    columns = _WIDE if wide else _SHORT
    head = "".join(f"<th>{html.escape(c)}</th>" for c in (first, *columns, "evidence"))
    body = []
    for label, s in rows:
        cells = stats_cells(s)
        cls = ' class="insufficient"' if s.evidence == "insufficient" else ""
        tds = "".join(f"<td>{html.escape(cells[c])}</td>" for c in columns)
        body.append(f"<tr{cls}><th>{html.escape(label)}</th>{tds}<td>{html.escape(s.evidence)}</td></tr>")
    return f'<table class="stats"><tr>{head}</tr>{"".join(body)}</table>'


def _equity_svg(net: Sequence[float]) -> str:
    """Cumulative net R by closing order, and the drawdown from its peak."""
    w, h, pad = 460, 200, 28
    if not net:
        return '<figure id="equity-curve"><figcaption>Equity curve (R): no closed trades</figcaption></figure>'
    curve, peak, dd = [0.0], 0.0, [0.0]
    for r in net:
        curve.append(curve[-1] + r)
        peak = max(peak, curve[-1])
        dd.append(curve[-1] - peak)
    lo, hi = min(min(curve), min(dd)), max(max(curve), 0.0)
    span = (hi - lo) or 1.0

    def pts(series):
        return " ".join(f"{pad + i * (w - 2 * pad) / max(1, len(series) - 1):.1f},"
                        f"{pad + (hi - v) / span * (h - 2 * pad):.1f}" for i, v in enumerate(series))

    zero = pad + hi / span * (h - 2 * pad)
    return (f'<figure id="equity-curve"><figcaption>Equity curve and drawdown (net R, {len(net)} trades; '
            f"end {curve[-1]:+.2f}R, max drawdown {-min(dd):.2f}R)</figcaption>"
            f'<svg viewBox="0 0 {w} {h}" role="img">'
            f'<line class="axis" x1="{pad}" x2="{w - pad}" y1="{zero:.1f}" y2="{zero:.1f}"/>'
            f'<polyline class="dd" points="{pts(dd)}"/><polyline class="eq" points="{pts(curve)}"/>'
            f'<text x="{pad}" y="{pad - 8}">{hi:+.1f}R</text><text x="{pad}" y="{h - 6}">{lo:+.1f}R</text>'
            "</svg></figure>")


def _histogram_svg(net: Sequence[float]) -> str:
    """Trades per half-R bucket of net R."""
    w, h, pad = 460, 200, 28
    if not net:
        return '<figure id="r-distribution"><figcaption>Net R distribution: no closed trades</figcaption></figure>'
    lo, hi = int(min(net) // 0.5), int(max(net) // 0.5)
    counts = {k: 0 for k in range(lo, hi + 1)}
    for r in net:
        counts[int(r // 0.5)] += 1
    top, n = max(counts.values()), len(counts)
    bw = (w - 2 * pad) / n
    bars = "".join(
        f'<rect class="{"win" if k >= 0 else "loss"}" x="{pad + i * bw + 1:.1f}" '
        f'y="{h - pad - c / top * (h - 2 * pad):.1f}" width="{max(1.0, bw - 2):.1f}" '
        f'height="{c / top * (h - 2 * pad):.1f}"><title>{k * 0.5:+.1f}R to {(k + 1) * 0.5:+.1f}R: {c}</title></rect>'
        for i, (k, c) in enumerate(sorted(counts.items())))
    return (f'<figure id="r-distribution"><figcaption>Net R distribution (half-R buckets)</figcaption>'
            f'<svg viewBox="0 0 {w} {h}" role="img">{bars}'
            f'<text x="{pad}" y="{h - 6}">{lo * 0.5:+.1f}R</text>'
            f'<text x="{w - pad}" y="{h - 6}" text-anchor="end">{(hi + 1) * 0.5:+.1f}R</text></svg></figure>')


def _f(value: str) -> Optional[float]:
    return float(value) if value not in ("", None) else None


def _dt(value: Optional[str]) -> Optional[datetime]:
    return datetime.fromisoformat(value).astimezone(UTC) if value else None


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()


_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>%TITLE%</title>
<style>
:root { --bg:#fff; --fg:#1d2329; --muted:#6b7480; --line:#d9dee4; --panel:#f5f7f9; --up:#1a7f5a; --down:#c23b3b;
  --entry:#2563eb; --stop:#c23b3b; --target:#1a7f5a; --band:rgba(250,190,40,.13); --array:rgba(37,99,235,.13);
  --dol:#8b5cf6; --sel:#e8eefc; }
@media (prefers-color-scheme: dark) { :root { --bg:#14181c; --fg:#e3e7eb; --muted:#9aa4ae; --line:#2c333a;
  --panel:#1b2026; --up:#3fbf8a; --down:#ef6b6b; --entry:#6c9cff; --stop:#ef6b6b; --target:#3fbf8a;
  --band:rgba(250,190,40,.10); --array:rgba(108,156,255,.16); --dol:#b794f6; --sel:#243049; } }
body { margin:0; padding:16px; background:var(--bg); color:var(--fg);
  font:14px/1.45 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif; }
h1 { font-size:20px; margin:0 0 12px; } h2 { font-size:16px; margin:28px 0 8px; } h3 { font-size:14px; margin:18px 0 6px; }
table { border-collapse:collapse; font-variant-numeric:tabular-nums; }
th, td { padding:3px 8px; border-bottom:1px solid var(--line); text-align:left; white-space:nowrap; }
.header th { color:var(--muted); font-weight:500; }
.stats td { text-align:right; } .stats tr.insufficient td, .stats tr.insufficient th { color:var(--muted); font-style:italic; }
span.insufficient { color:var(--muted); font-style:italic; }
.charts { display:flex; flex-wrap:wrap; gap:16px; } figure { margin:0; flex:1 1 380px; max-width:520px; }
figcaption { color:var(--muted); font-size:12px; } svg { width:100%; height:auto; display:block; }
svg text { fill:var(--muted); font-size:11px; }
.axis { stroke:var(--line); } .eq { fill:none; stroke:var(--entry); stroke-width:1.6; }
.dd { fill:none; stroke:var(--down); stroke-width:1; opacity:.7; }
rect.win { fill:var(--up); } rect.loss { fill:var(--down); }
.scroll { overflow-x:auto; max-width:100%; }
.filters { display:flex; flex-wrap:wrap; gap:8px; margin:8px 0; align-items:center; }
.filters label { color:var(--muted); font-size:12px; display:flex; flex-direction:column; }
select, button { font:inherit; background:var(--panel); color:var(--fg); border:1px solid var(--line); border-radius:4px; padding:2px 6px; }
#explorer tr.row { cursor:pointer; } #explorer tr.row:hover, #explorer tr.sel { background:var(--sel); }
#explorer td.num { text-align:right; } .pos { color:var(--up); } .neg { color:var(--down); }
#detail { background:var(--panel); border:1px solid var(--line); border-radius:6px; padding:10px; margin-top:10px; }
#detail dl { display:grid; grid-template-columns:max-content 1fr; gap:2px 12px; margin:6px 0 0; }
#detail dt { color:var(--muted); }
.candle-up { stroke:var(--up); fill:var(--up); } .candle-down { stroke:var(--down); fill:var(--down); }
.lvl-entry { stroke:var(--entry); } .lvl-stop { stroke:var(--stop); } .lvl-target { stroke:var(--target); }
.lbl-entry { fill:var(--entry); } .lbl-stop { fill:var(--stop); } .lbl-target { fill:var(--target); }
.band { fill:var(--band); } .array { fill:var(--array); stroke:var(--entry); stroke-dasharray:3 3; }
.dol { stroke:var(--dol); stroke-dasharray:6 4; } .lbl-dol { fill:var(--dol); }
.decision { stroke:var(--fg); stroke-dasharray:2 3; opacity:.6; }
.fill { fill:var(--entry); } .exit { stroke:var(--fg); stroke-width:2; }
</style>
</head>
<body>
<h1>%TITLE%</h1>
<table class="header">%HEADER%</table>
<h2>Summary</h2>
%SUMMARY%
<h2>Trade explorer</h2>
<div class="filters" id="filters"></div>
<div class="scroll"><table id="explorer"></table></div>
<div class="filters"><button id="prev">&larr; previous</button><span id="page"></span><button id="next">next &rarr;</button></div>
<div id="detail"><div id="chart"><p>Pick a row to draw its chart.</p></div><div id="info"></div></div>
<script type="application/json" id="report-data">%DATA%</script>
<script>
(function () {
  const data = JSON.parse(document.getElementById("report-data").textContent);
  const rows = data.rows, PAGE = 200;
  const why = r => data.reasons[r.reason];   // reasons and contexts are stored once (see _compact)
  const ctx = r => r.context == null ? {} : data.contexts[r.context];
  let shown = [], page = 0, selected = null;
  const esc = s => String(s == null ? "" : s).replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
  const num = (v, d) => v == null ? "" : Number(v).toFixed(d);
  const filters = document.getElementById("filters");
  const labels = {outcome: "Outcome", decision: "Decision / skip reason", instrument: "Instrument", grade: "Grade", killzone: "Killzone"};
  for (const name of Object.keys(labels)) {
    const opts = (name === "decision" ? ['<option value="__setups">all but no-trade</option>', '<option value="">all</option>']
                                      : ['<option value="">all</option>'])
      .concat(data.filters[name].map(v => `<option>${esc(v)}</option>`));
    filters.insertAdjacentHTML("beforeend", `<label>${labels[name]}<select data-f="${name}">${opts.join("")}</select></label>`);
  }
  filters.addEventListener("change", apply);
  document.getElementById("prev").onclick = () => { if (page > 0) { page--; table(); } };
  document.getElementById("next").onclick = () => { if ((page + 1) * PAGE < shown.length) { page++; table(); } };

  function apply() {
    const f = {};
    filters.querySelectorAll("select").forEach(s => f[s.dataset.f] = s.value);
    shown = rows.filter(r => Object.entries(f).every(([k, v]) =>
      v === "" || (v === "__setups" ? !["NO_TRADE", "ENGINE_ERROR"].includes(r.decision) : String(r[k]) === v)));
    page = 0; table();
  }
  function table() {
    const head = "<tr><th>time (UTC)</th><th>instrument</th><th>decision</th><th>outcome</th><th>grade</th>" +
      "<th>killzone</th><th>dir</th><th>entry</th><th>stop</th><th>target</th><th>net R</th><th>reason</th></tr>";
    const body = shown.slice(page * PAGE, (page + 1) * PAGE).map(r =>
      `<tr class="row${r.id === selected ? " sel" : ""}" data-id="${r.id}"><td>${esc(r.t.slice(0, 16).replace("T", " "))}</td>` +
      `<td>${esc(r.instrument)}</td><td>${esc(r.decision)}</td><td>${esc(r.outcome)}</td><td>${esc(r.grade)}</td>` +
      `<td>${esc(r.killzone)}</td><td>${esc(r.direction)}</td><td class="num">${esc(r.entry)}</td>` +
      `<td class="num">${esc(r.stop)}</td><td class="num">${esc(r.target)}</td>` +
      `<td class="num ${r.net_r > 0 ? "pos" : r.net_r < 0 ? "neg" : ""}">${num(r.net_r, 2)}</td><td>${esc(why(r))}</td></tr>`).join("");
    document.getElementById("explorer").innerHTML = head + body;
    document.getElementById("page").textContent =
      shown.length ? `rows ${page * PAGE + 1}-${Math.min(shown.length, (page + 1) * PAGE)} of ${shown.length}` : "no rows";
  }
  document.getElementById("explorer").addEventListener("click", e => {
    const tr = e.target.closest("tr.row"); if (!tr) return;
    selected = Number(tr.dataset.id); table(); show(rows[selected]);
  });

  function show(r) {
    const chart = document.getElementById("chart");
    chart.innerHTML = r.window ? svg(r) : "<p>No setup to draw for this row.</p>";
    const m = r.markers || {}, c = ctx(r);
    const items = [["setup", r.setup_id], ["decision", `${r.decision} ${why(r)}`], ["grade", r.grade],
      ["time window", r.time_window], ["order", r.order_id ? `${r.order_id} ${r.kind || ""}` : ""],
      ["fill", m.fill ? `${m.fill[1]} at ${m.fill[0]}` : ""], ["exit", m.exit ? `${m.exit[1]} at ${m.exit[0]} (${r.outcome})` : r.outcome],
      ["R", r.net_r == null ? "" : `gross ${num(r.gross_r, 2)}, net ${num(r.net_r, 2)}, costs ${num(r.cost_r, 2)}`],
      ["entry array", c.entry_array ? `${c.entry_array.type} ${c.entry_array.direction} ${c.entry_array.timeframe} ${c.entry_array.low}-${c.entry_array.high}, formed ${c.entry_array.formed_at}` : ""],
      ["draw on liquidity", c.draw_on_liquidity ? `${c.draw_on_liquidity.type} ${c.draw_on_liquidity.source} ${c.draw_on_liquidity.price}` : ""],
      ["swept level", c.swept_level ? JSON.stringify(c.swept_level) : ""]];
    document.getElementById("info").innerHTML = "<dl>" + items.filter(([, v]) => v)
      .map(([k, v]) => `<dt>${k}</dt><dd>${esc(v)}</dd>`).join("") + "</dl>";
  }

  function svg(r) {
    const all = data.candles[r.instrument] || [];
    const index = t => { let lo = 0, hi = all.length - 1, ans = 0; while (lo <= hi) { const mid = (lo + hi) >> 1;
      if (all[mid][0] <= t) { ans = mid; lo = mid + 1; } else hi = mid - 1; } return ans; };
    const i0 = index(r.window[0]), i1 = index(r.window[1]), bars = all.slice(i0, i1 + 1), n = bars.length;
    if (!n) return "<p>No candles recorded for this window.</p>";
    const W = 960, H = 380, L = 8, R = 84, T = 10, B = 22, pw = W - L - R, ph = H - T - B, step = pw / n;
    const m = r.markers, c = ctx(r);
    const levels = [m.entry, m.stop, m.target].filter(v => v != null);
    if (c.entry_array) levels.push(c.entry_array.high, c.entry_array.low);
    let lo = Math.min(...bars.map(b => b[3]), ...levels), hi = Math.max(...bars.map(b => b[2]), ...levels);
    const dol = c.draw_on_liquidity && c.draw_on_liquidity.price;
    if (dol != null && dol > lo - (hi - lo) && dol < hi + (hi - lo)) { lo = Math.min(lo, dol); hi = Math.max(hi, dol); }
    const pad = (hi - lo) * 0.04 || 1e-6; lo -= pad; hi += pad;
    const y = p => T + (hi - p) / (hi - lo) * ph;
    const x = t => L + (index(t) - i0 + 0.5) * step;
    const clampX = t => t < r.window[0] ? L : (t > r.window[1] ? L + pw : x(t));
    const out = [`<svg viewBox="0 0 ${W} ${H}" role="img">`];
    for (const [s, e, name] of r.bands || []) {
      const a = clampX(s) - step / 2, b = clampX(e) - step / 2;
      out.push(`<rect class="band" x="${a}" y="${T}" width="${Math.max(0, b - a)}" height="${ph}"/><text x="${a + 2}" y="${T + 11}">${name}</text>`);
    }
    if (c.entry_array) {
      const a = clampX(c.entry_array.formed_at) - step / 2;
      out.push(`<rect class="array" x="${a}" y="${y(c.entry_array.high)}" width="${L + pw - a}" height="${Math.max(1, y(c.entry_array.low) - y(c.entry_array.high))}"/>`);
    }
    if (dol != null && dol >= lo && dol <= hi) {
      out.push(`<line class="dol" x1="${L}" x2="${L + pw}" y1="${y(dol)}" y2="${y(dol)}"/><text class="lbl-dol" x="${L + pw + 4}" y="${y(dol) + 4}">DOL ${esc(c.draw_on_liquidity.source)}</text>`);
    }
    bars.forEach((b, i) => {
      const cx = L + (i + 0.5) * step, cls = b[4] >= b[1] ? "candle-up" : "candle-down";
      const top = y(Math.max(b[1], b[4])), h = Math.max(1, Math.abs(y(b[1]) - y(b[4])));
      out.push(`<line class="${cls}" x1="${cx}" x2="${cx}" y1="${y(b[2])}" y2="${y(b[3])}"/><rect class="${cls}" x="${cx - step * 0.35}" y="${top}" width="${step * 0.7}" height="${h}"/>`);
    });
    const d = x(m.decision) + step / 2, end = m.closed ? x(m.closed) + step / 2 : L + pw;
    out.push(`<line class="decision" x1="${d}" x2="${d}" y1="${T}" y2="${T + ph}"/>`);
    for (const [name, v] of [["entry", m.entry], ["stop", m.stop], ["target", m.target]]) {
      if (v == null) continue;
      out.push(`<line class="lvl-${name}" x1="${d}" x2="${Math.max(end, d + step)}" y1="${y(v)}" y2="${y(v)}"/><text class="lbl-${name}" x="${L + pw + 4}" y="${y(v) + 4}">${name} ${v}</text>`);
    }
    if (m.fill) out.push(`<circle class="fill" cx="${x(m.fill[0])}" cy="${y(m.fill[1])}" r="4"><title>fill ${m.fill[1]}</title></circle>`);
    if (m.exit) { const ex = x(m.exit[0]), ey = y(m.exit[1]);
      out.push(`<path class="exit" d="M${ex - 4},${ey - 4}L${ex + 4},${ey + 4}M${ex - 4},${ey + 4}L${ex + 4},${ey - 4}"><title>exit ${m.exit[1]}</title></path>`); }
    for (let k = 0; k <= 4; k++) { const p = lo + (hi - lo) * k / 4;
      out.push(`<text x="${L + pw + 4}" y="${y(p) + 4}" opacity=".5">${p.toPrecision(6)}</text>`); }
    for (const k of [0, Math.floor(n / 2), n - 1])
      out.push(`<text x="${L + (k + 0.5) * step}" y="${H - 6}" text-anchor="middle">${bars[k][0].slice(5, 16).replace("T", " ")}</text>`);
    out.push(`<text x="${L}" y="${H - 6}">${esc(r.instrument)} ${data.timeframe}</text></svg>`);
    return out.join("");
  }
  apply();
})();
</script>
</body>
</html>
"""
