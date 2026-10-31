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


# ── the scorecard (Requirement 32.6, task 381) ──
WEEK_OPEN = datetime(2026, 11, 1, 22, tzinfo=UTC)                          # Sunday 17:00 New York (EST)
DAYS = [(100, 101, 99, 100.5), (100.5, 103, 98, 102), (102, 105.5, 101, 104), (104, 104.5, 102, 103),
        (103, 104, 102.5, 103.5)]                                           # Monday to Friday: open, high, low, close


def week_bars(days=DAYS):
    """Hourly bars from the week's open: each trading day flat at its open, its low at 05:00, its high at 10:00
    (hours from 17:00 New York), and its close in the last hour."""
    import pandas as pd
    from datetime import timedelta

    rows = []
    for d, (o, h, lo, c) in enumerate(days):
        for k in range(24):
            t = WEEK_OPEN + timedelta(days=d, hours=k)
            close = c if k == 23 else o
            rows.append((t, o, h if k == 10 else max(o, close), lo if k == 5 else min(o, close), close))
    return pd.DataFrame(rows, columns=["time", "open", "high", "low", "close"])


def test_a_call_is_scored_on_its_weeks_close_and_its_contexts_first_end():
    from agent.context_calls import score_call

    after = datetime(2026, 11, 7, tzinfo=UTC)
    call = Call("EURUSD", "2026-11-02", "BULLISH", draw=105, protected=95, made_at="2026-10-31T12:00:00+00:00")
    s = score_call(call, week_bars(), after)
    assert (s["week_open"], s["week_close"], s["hit"], s["final"]) == (100, 103.5, True, True)
    assert s["outcome"] == "delivered" and s["at"].startswith("2026-11-04T08:00")      # Wednesday, hour 10
    assert s["walk"] == 0.5
    tight = Call("EURUSD", "2026-11-02", "BULLISH", draw=105, protected=99.5, made_at="2026-10-31T12:00:00+00:00")
    wick = score_call(tight, week_bars(), after)                       # Tuesday's low 98 is a wick: no end
    assert wick["outcome"] == "delivered"
    closed = list(DAYS)
    closed[1] = (100.5, 103, 98, 99)                                   # Tuesday closes at 99, below 99.5
    broken = score_call(tight, week_bars(closed), after)
    assert broken["outcome"] == "invalidated" and broken["at"].startswith("2026-11-03T22:00")   # Tuesday 17:00 EST
    running = score_call(call, week_bars()[:30], datetime(2026, 11, 3, 4, tzinfo=UTC))
    assert running["final"] is False and running["outcome"] == "open" and running["hit"] is True


def test_the_scorecard_sets_the_context_agent_against_the_controls(tmp_path):
    from agent.context_calls import paper_r
    from algo_research.replay.context import BREAK_EVEN, ContextApp

    def trades(*rows):
        return [{"instrument": i, "placed_at": t, "filled_at": t if r is not None else None, "net_r": r}
                for i, t, r in rows]

    (tmp_path / "context.json").write_text(json.dumps(trades(("EURUSD", "2026-11-03T08:00:00+00:00", 2.5))))
    (tmp_path / "control.json").write_text(json.dumps(trades(
        ("EURUSD", "2026-11-02T09:00:00+00:00", -1.0), ("EURUSD", "2026-11-05T14:00:00+00:00", 0.5),
        ("EURUSD", "2026-11-05T15:00:00+00:00", None), ("GBPUSD", "2026-11-05T14:00:00+00:00", -1.0),
        ("EURUSD", "2026-11-09T14:00:00+00:00", -1.0))))
    assert paper_r(tmp_path / "control.json", "EURUSD", WEEK_OPEN, datetime(2026, 11, 6, 22, tzinfo=UTC)) == (2, -0.5)
    app = ContextApp(tmp_path / "calls.json", tmp_path / "theses.json", clock=lambda: datetime(2026, 11, 7, tzinfo=UTC),
                     bars=lambda inst, a, b: week_bars(),
                     paper={"context": tmp_path / "context.json", "partial": tmp_path / "none.json",
                            "control": tmp_path / "control.json"},
                     briefs=tmp_path / "briefs", agree=tmp_path / "agree.json")
    book = app.book()
    book.put(Call("EURUSD", "2026-11-02", "BULLISH", 105, 95, made_at="2026-10-31T12:00:00+00:00"))
    book.put(Call("GBPUSD", "2026-11-02", "NONE", made_at="2026-10-31T12:00:00+00:00"))
    book.put(Call("US500", "2026-11-09", "BEARISH", 7600, 7900, made_at="2026-11-06T12:00:00+00:00"))   # not open
    card = app.scorecard()
    assert [w["week"] for w in card["weeks"]] == ["2026-11-02"]
    assert [r["call"]["instrument"] for r in card["weeks"][0]["rows"]] == ["EURUSD", "GBPUSD"]
    t = card["totals"]
    assert (t["calls"], t["final"], t["hits"], t["hit_rate"], t["delivered"]) == (1, 1, 1, 1.0, 1)
    assert t["agents"] == {"context": {"n": 1, "r": 2.5}, "partial": {"n": 0, "r": 0.0}, "control": {"n": 2, "r": -0.5}}
    assert t["break_even"] == BREAK_EVEN
    with pytest.raises(LookupError):
        ContextApp(tmp_path / "calls.json", tmp_path / "theses.json").scorecard()
