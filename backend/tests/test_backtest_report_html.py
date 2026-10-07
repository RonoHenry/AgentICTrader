"""
Tests for algo_backtester/report_html.py — the self-contained HTML run report.

Task 218 (.kiro/specs/algo-backtester/tasks.md). A synthetic run directory:
the scripted run of test_backtest_report.py (every kind of journal row), one
setup with a recorded TradeContext, and M15 candles around it. The report is
one offline file: the data is embedded as JSON and the charts are drawn by
inline script, from the run's own recorded files only.
Validates: Requirements 11.1-11.7 (.kiro/specs/algo-backtester/requirements.md)
"""
from __future__ import annotations

import json
import re
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from algo_backtester.report import write_run
from algo_backtester.report_html import build_forward_test, render, write_html_report, write_report_inputs
from algo_backtester.run import RunResult, WindowResult
from algo_backtester.signals import TradeContext
from liquidity_engine import LiquidityMappingEngine
from liquidity_engine.models import Timeframe
from tests.test_backtest_report import cfg, manifest, scripted
from tests.test_backtest_simulation import PRICES

UTC = timezone.utc
T0 = datetime(2026, 9, 30, 13, 0, tzinfo=UTC)
M15 = timedelta(minutes=15)
CONTEXT = TradeContext(
    entry_array={"type": "FVG", "direction": "BULLISH", "timeframe": "M15", "high": 1.1003, "low": 1.0999,
                 "formed_at": "2026-09-30T12:15:00+00:00"},
    draw_on_liquidity={"type": "BSL", "source": "PDH", "price": 1.1060, "formed_at": "2026-09-29T21:00:00+00:00"},
    swept_level=None,
    killzone="NY_AM",
)


def m15_candles(instrument: str) -> list:
    price, out, t = PRICES[instrument], [], datetime(2026, 9, 29, 0, 0, tzinfo=UTC)
    while t < datetime(2026, 10, 1, 0, 0, tzinfo=UTC):
        low = price - (0.0016 if instrument == "EURUSD" and t == T0 + M15 else 0.0)   # the stop-out bar
        out.append(SimpleNamespace(timestamp=t, open=price, high=price, low=low, close=price))
        t += M15
    return out


def with_context(result: RunResult) -> RunResult:
    window = result.windows[0]
    journal = [replace(row, context=CONTEXT) if row.setup_id == "EURUSD-1" else row for row in window.result.journal]
    return replace(result, windows=[WindowResult(window.start, window.end, replace(window.result, journal=journal))])


@pytest.fixture
def run_dir(tmp_path) -> Path:
    result = with_context(scripted())
    directory = write_run(tmp_path, cfg(), manifest(), result)
    write_report_inputs(directory, result.journal, {i: m15_candles(i) for i in PRICES}, Timeframe.M15)
    return directory


def data_of(html: str) -> dict:
    """The embedded data, rows expanded as the page script reads them: missing
    fields are empty, and a reason or context is an index into ``reasons`` or
    ``contexts``."""
    match = re.search(r'<script type="application/json" id="report-data">(.*?)</script>', html, re.S)
    data = json.loads(match.group(1))
    data["rows"] = [{**{k: None for k in data["fields"]}, "bands": [], **row, "reason": data["reasons"][row["reason"]],
                     "context": data["contexts"][row["context"]] if "context" in row else None}
                    for row in data["rows"]]
    return data


def test_rows_are_compacted_for_size(run_dir):
    raw = re.search(r'id="report-data">(.*?)</script>',
                    write_html_report(run_dir).read_text(encoding="utf-8"), re.S).group(1)
    data = json.loads(raw)
    no_trade = next(r for r in data["rows"] if r["decision"] == "NO_TRADE")
    assert set(no_trade) == {"id", "t", "instrument", "decision", "reason", "grade", "killzone"}
    assert None not in no_trade.values()                                             # no empty fields
    assert data["reasons"][no_trade["reason"]] == "5/8" and len(set(data["reasons"])) == len(data["reasons"])


def row_of(data: dict, setup_id: str) -> dict:
    return next(r for r in data["rows"] if r.get("setup_id") == setup_id)


# ── the file ───────────────────────────────────────────────────────────────

def test_report_is_single_offline_file(run_dir):
    path = write_html_report(run_dir)
    assert path == run_dir / "report.html"
    html = path.read_text(encoding="utf-8")
    assert html.startswith("<!doctype html>")
    # nothing is fetched: no external script, stylesheet or image, and no web addresses at all
    assert not re.search(r"<(script|link|img)\b[^>]*\b(src|href)\s*=", html, re.I)
    assert "http://" not in html and "https://" not in html
    assert write_html_report(run_dir).read_text(encoding="utf-8") == html      # deterministic


def test_report_header_shows_manifest_essentials(run_dir):
    html = write_html_report(run_dir).read_text(encoding="utf-8")
    header = {k: v for k, v in data_of(html)["header"]}
    m = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert header["Broker profile"] == "exness-standard"
    assert header["Costs from"].startswith("Exness (KE) Limited")
    assert header["Variant"] == "base"
    assert header["Data"] == "2026-09-30 to 2026-10-01 (UTC, end exclusive)"
    assert header["Code"] == f"{m['git_commit'][:12]} (clean)"
    assert header["AI modifiers"] == "disabled" and header["News filter"] == "not_applied"
    assert header["Run"] == m["run_id"][:12]


def test_every_journal_row_present_including_skipped(run_dir):
    data = data_of(write_html_report(run_dir).read_text(encoding="utf-8"))
    journal_lines = (run_dir / "journal.csv").read_text(encoding="utf-8").strip().splitlines()
    assert len(data["rows"]) == len(journal_lines) - 1 == 8
    decisions = sorted(r["decision"] for r in data["rows"])
    assert decisions == sorted(["EXECUTE", "EXECUTE", "EXECUTE", "SKIP", "IN_TRADE", "NO_TRADE", "RR_BELOW_MIN",
                                "ENGINE_ERROR"])
    skipped = next(r for r in data["rows"] if r["decision"] == "SKIP")
    assert "concurrent trades" in skipped["reason"] and skipped["window"]          # skipped intents get a chart
    no_trade = next(r for r in data["rows"] if r["decision"] == "NO_TRADE")
    assert no_trade["window"] is None                                             # no setup to draw
    # the explorer's filters (Req 11.4)
    assert {"outcome", "decision", "instrument", "grade", "killzone"} <= set(data["filters"])


def test_chart_window_spans_bars_before_decision_to_bars_after_close(run_dir):
    data = data_of(write_html_report(run_dir).read_text(encoding="utf-8"))
    stopped = row_of(data, "EURUSD-1")
    # the decision bar opened 12:45 and closed at t; the exit (13:29) is in the bar opening 13:15
    assert stopped["window"] == [(T0 - M15 - 60 * M15).isoformat(), (T0 + M15 + 20 * M15).isoformat()]
    in_trade = next(r for r in data["rows"] if r["decision"] == "IN_TRADE")      # decided 13:15, never closed
    assert in_trade["window"] == [(T0 - 60 * M15).isoformat(), (T0 + 20 * M15).isoformat()]
    # the candles cover the windows, and are the only ones embedded
    eur = data["candles"]["EURUSD"]
    assert eur[0][0] <= stopped["window"][0] and eur[-1][0] >= stopped["window"][1]


def test_chart_window_lengths_configurable(tmp_path):
    # The CLI passes [report] chart_bars_before / chart_bars_after (defaults 60 and 20, Req 11.5).
    assert (cfg().report.chart_bars_before, cfg().report.chart_bars_after) == (60, 20)
    result = with_context(scripted())
    directory = write_run(tmp_path, cfg(), manifest(), result)
    write_report_inputs(directory, result.journal, {i: m15_candles(i) for i in PRICES}, Timeframe.M15,
                        bars_before=4, bars_after=2)
    data = data_of(write_html_report(directory).read_text(encoding="utf-8"))
    assert row_of(data, "EURUSD-1")["window"] == [(T0 - M15 - 4 * M15).isoformat(), (T0 + M15 + 2 * M15).isoformat()]


def test_markers_for_decision_entry_stop_target_fill_exit(run_dir):
    data = data_of(write_html_report(run_dir).read_text(encoding="utf-8"))
    markers = row_of(data, "EURUSD-1")["markers"]
    assert markers["decision"] == T0.isoformat()
    assert (markers["entry"], markers["stop"], markers["target"]) == pytest.approx((1.1001, 1.0991, 1.1051))
    assert markers["fill"][0] == T0.isoformat() and markers["fill"][1] == pytest.approx(1.1001)
    assert markers["exit"][0] == (T0 + 29 * timedelta(minutes=1)).isoformat()
    assert markers["exit"][1] == pytest.approx(1.0991)
    assert row_of(data, "EURUSD-1")["outcome"] == "SL"
    # killzone shading: New York AM on 2026-09-30 is 11:00-14:00 UTC (EDT)
    assert ["2026-09-30T11:00:00+00:00", "2026-09-30T14:00:00+00:00", "NY_AM"] in row_of(data, "EURUSD-1")["bands"]
    still_open = row_of(data, "GBPUSD-1")
    assert still_open["markers"]["fill"] and still_open["markers"]["exit"] is None
    assert still_open["outcome"] == "OPEN_AT_END"


def test_context_drawn_only_from_recorded_signal_records(run_dir, monkeypatch):
    def no_analysis(*args, **kwargs):
        raise AssertionError("the report must not re-run the engine (Req 11.6)")

    monkeypatch.setattr(LiquidityMappingEngine, "analyze", no_analysis)
    data = data_of(write_html_report(run_dir).read_text(encoding="utf-8"))
    assert row_of(data, "EURUSD-1")["context"] == {
        "entry_array": CONTEXT.entry_array, "draw_on_liquidity": CONTEXT.draw_on_liquidity,
        "swept_level": None, "killzone": "NY_AM"}
    assert row_of(data, "GBPUSD-1")["context"] is None           # none was recorded for it
    recorded = json.loads((run_dir / "context.json").read_text(encoding="utf-8"))
    assert len(recorded) == 1 and recorded[0]["setup_id"] == "EURUSD-1"


def test_insufficient_evidence_buckets_marked(run_dir):
    html = write_html_report(run_dir).read_text(encoding="utf-8")
    data = data_of(html)
    eur = data["summary"]["breakdowns"]["instrument"]["EURUSD"]
    assert eur["evidence"] == "insufficient"
    assert 'class="insufficient"' in html and "Insufficient evidence" in html
    # the summary section: equity curve, net R distribution, cost share (Req 11.3)
    assert 'id="equity-curve"' in html and 'id="r-distribution"' in html and "cost share" in html.lower()


def test_forward_test_trades_file_renders_same_explorer():
    trades = [
        {"trade_id": "paper-1", "setup_id": "s1", "instrument": "EURUSD", "direction": "LONG", "kind": "LIMIT",
         "entry": 1.1001, "stop_loss": 1.0991, "take_profit": 1.1051, "status": "CLOSED",
         "placed_at": T0.isoformat(), "expires_at": (T0 + timedelta(hours=1)).isoformat(),
         "filled_at": T0.isoformat(), "fill_price": 1.1001, "closed_at": (T0 + 29 * timedelta(minutes=1)).isoformat(),
         "exit_price": 1.0991, "exit_reason": "SL", "gross_r": -0.9, "net_r": -1.0},
        {"trade_id": "paper-2", "setup_id": "s2", "instrument": "EURUSD", "direction": "SHORT", "kind": "LIMIT",
         "entry": 1.1020, "stop_loss": 1.1030, "take_profit": 1.0970, "status": "CLOSED",
         "placed_at": (T0 + 2 * M15).isoformat(), "expires_at": (T0 + 4 * M15).isoformat(), "filled_at": None,
         "fill_price": None, "closed_at": (T0 + 4 * M15).isoformat(), "exit_price": None, "exit_reason": "EXPIRED",
         "gross_r": None, "net_r": None},
    ]
    model = build_forward_test(trades, {"EURUSD": m15_candles("EURUSD")}, Timeframe.M15, source="paper_trades.json")
    html = render(model)
    data = data_of(html)
    assert [r["order_id"] for r in data["rows"]] == ["paper-1", "paper-2"]
    first = data["rows"][0]
    assert first["outcome"] == "SL" and first["net_r"] == -1.0 and first["killzone"] == "NY_AM"
    assert first["window"] == [(T0 - M15 - 60 * M15).isoformat(), (T0 + M15 + 20 * M15).isoformat()]
    assert first["markers"]["fill"] == [T0.isoformat(), 1.1001] and first["context"] is None
    assert data["rows"][1]["outcome"] == "EXPIRED" and data["rows"][1]["markers"]["fill"] is None
    assert dict(data["header"])["Source"] == "paper forward test: paper_trades.json"
    # one explorer for both: the same row fields and the same page structure
    with_run = set(row_of(data_of(render(model)), "s1"))
    assert {"window", "markers", "bands", "context", "outcome", "decision", "killzone"} <= with_run
    assert 'id="explorer"' in html and 'id="chart"' in html
