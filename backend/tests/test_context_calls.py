"""
Tests for agent/context_calls.py — the trader's weekly context (context-engine Requirement 32.1-32.2, task 378).
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone

import pytest

from agent.context_calls import Call, ContextBook, thesis_table, trading_dates, week_monday, week_open

UTC = timezone.utc


def test_a_week_opens_on_sunday_at_five_in_new_york_and_a_weekend_belongs_to_the_next():
    assert week_monday(datetime(2026, 10, 29, 12, tzinfo=UTC)) == date(2026, 10, 26)       # a Thursday
    assert week_monday(datetime(2026, 10, 30, 20, 59, tzinfo=UTC)) == date(2026, 10, 26)   # Friday 16:59 New York
    assert week_monday(datetime(2026, 10, 30, 21, 0, tzinfo=UTC)) == date(2026, 11, 2)     # Friday 17:00: closed
    assert week_monday(datetime(2026, 10, 31, 12, tzinfo=UTC)) == date(2026, 11, 2)        # Saturday
    assert week_monday(datetime(2026, 11, 1, 22, 0, tzinfo=UTC)) == date(2026, 11, 2)      # Sunday 17:00 EST
    assert week_open(date(2026, 10, 26)) == datetime(2026, 10, 25, 21, tzinfo=UTC)         # EDT
    assert week_open(date(2026, 11, 2)) == datetime(2026, 11, 1, 22, tzinfo=UTC)           # EST from 1 November
    assert trading_dates(date(2026, 11, 2)) == ["2026-11-02", "2026-11-03", "2026-11-04", "2026-11-05",
                                                "2026-11-06"]


def test_a_call_checks_its_levels():
    Call("EURUSD", "2026-11-02", "BULLISH", draw=1.12, protected=1.10)
    Call("EURUSD", "2026-11-02", "NONE")
    with pytest.raises(ValueError, match="protected"):
        Call("EURUSD", "2026-11-02", "BULLISH", draw=1.10, protected=1.12)
    with pytest.raises(ValueError, match="protected"):
        Call("EURUSD", "2026-11-02", "BEARISH", draw=1.12, protected=1.10)
    with pytest.raises(ValueError, match="draw"):
        Call("EURUSD", "2026-11-02", "BEARISH", protected=1.12)
    with pytest.raises(ValueError, match="side"):
        Call("EURUSD", "2026-11-02", "LONG", draw=1.12, protected=1.10)
    with pytest.raises(ValueError, match="Monday"):
        Call("EURUSD", "2026-11-03", "NONE")


def test_a_late_call_counts_from_its_own_time():
    on_time = Call("US500", "2026-11-02", "BULLISH", 7850, 7600, made_at="2026-11-01T12:00:00+00:00")
    late = Call("US500", "2026-11-02", "BULLISH", 7850, 7600, made_at="2026-11-03T15:30:00+00:00")
    assert not on_time.late and on_time.since == "2026-11-01T22:00:00+00:00"
    assert late.late and late.since == "2026-11-03T15:30:00+00:00"


def test_the_thesis_file_holds_each_trading_date_of_a_called_week(tmp_path):
    book = ContextBook(tmp_path / "calls.json", tmp_path / "theses.json")
    book.put(Call("EURUSD", "2026-11-02", "BEARISH", 1.10, 1.13, made_at="2026-10-31T09:00:00+00:00"))
    book.put(Call("EURUSD", "2026-11-02", "BULLISH", 1.13, 1.10, made_at="2026-11-01T09:00:00+00:00"))  # replaces
    book.put(Call("GBPUSD", "2026-11-02", "NONE", made_at="2026-11-01T09:00:00+00:00"))
    theses = json.loads((tmp_path / "theses.json").read_text(encoding="utf-8"))
    assert list(theses) == ["EURUSD"] and sorted(theses["EURUSD"]) == trading_dates(date(2026, 11, 2))
    assert theses["EURUSD"]["2026-11-04"] == {"side": "BULLISH", "draw": 1.13, "protected": 1.10,
                                              "since": "2026-11-01T22:00:00+00:00"}
    assert [c.side for c in book.history("EURUSD", "2026-11-02")] == ["BEARISH", "BULLISH"]
    assert set(book.week(date(2026, 11, 2))) == {"EURUSD", "GBPUSD"}
    assert thesis_table([]) == {}
    reopened = ContextBook(tmp_path / "calls.json", tmp_path / "theses.json")
    assert reopened.week(date(2026, 11, 2))["EURUSD"].side == "BULLISH"


def test_the_context_variant_trades_only_inside_the_calls():
    from pathlib import Path

    from agent.context_calls import THESIS_FILE, REPO
    from agent.strategy_config import BiasMode
    from algo_backtester.config import load_run_config

    focus = load_run_config(REPO / "config" / "backtests" / "focus.toml", "fresh_near_gap_context")
    partial = load_run_config(REPO / "config" / "backtests" / "focus.toml", "fresh_near_gap_partial")
    assert focus.strategy.bias_mode == BiasMode.THESIS and focus.strategy.min_stop_spreads == 10
    assert (REPO / focus.strategy.thesis_file).resolve() == Path(THESIS_FILE).resolve()
    assert focus.management == partial.management
    same = {"bias_mode", "thesis_file", "min_stop_spreads"}
    assert {k: v for k, v in focus.strategy.model_dump().items() if k not in same} == \
           {k: v for k, v in partial.strategy.model_dump().items() if k not in same}
