"""
Tests for algo_backtester/signals.py — Phase A: the engine's decision at
every entry-timeframe close.

Task 199 (.kiro/specs/algo-backtester/tasks.md). Real data: the task 186
MetaQuotes-Demo fixtures (New York-close server), one week of M1 plus a year
of native H1/H4/D1/W1 for the warm-up. Small windows keep the engine quick.
Validates: Requirements 1.1, 9.2 (.kiro/specs/algo-backtester/requirements.md)
"""
from __future__ import annotations

import gzip
import json
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace
from typing import Optional

import pytest

from agent.order_intent import NoTrade, OrderIntent
from agent.strategy_config import StrategyConfig
from algo_backtester.data import InstrumentData, StoredBar, load_instrument
from algo_backtester.signals import EngineError, SignalRecord, generate_all, generate_signals, signal_at
from liquidity_engine.models import Timeframe as TF
from services.market_data.mt5_clock import MT5ServerClock
from services.market_data.strategy_calendar import StrategyCalendar

FIXTURES = Path(__file__).parent / "fixtures" / "backtester" / "aggregation"
UTC = timezone.utc
MIN = timedelta(minutes=1)
CAL = StrategyCalendar()
CFG = StrategyConfig(entry_tf="M15", context_tfs=("H4",), candle_counts={"M15": 60, "H4": 30, "D1": 20, "W1": 8})
# The fixture week: Sunday 2026-09-27 21:00 UTC (FX open) to Friday 2026-10-02 21:00 UTC.
START, END = datetime(2026, 9, 29, 0, 0, tzinfo=UTC), datetime(2026, 10, 2, 20, 0, tzinfo=UTC)


class FixtureSource:
    """M1 from the one-week file, native H1/H4/D1/W1 from the year file."""

    def __init__(self, instrument: str, m1_until: Optional[datetime] = None):
        self.instrument = instrument
        self.m1_until = m1_until

    @staticmethod
    @lru_cache(maxsize=None)
    def _rows(instrument: str, base: str):
        name = {"M1": "20260926", "H1": "20251004"}[base]
        with gzip.open(FIXTURES / f"metaquotes-demo_{instrument}_{base}_{name}.json.gz", "rt", encoding="utf-8") as fh:
            return json.load(fh)["bars"]

    def bars(self, instrument, tf, start, end):
        rows = self._rows(instrument, "M1" if tf == TF.M1 else "H1").get(tf.value, [])  # fixtures hold H1/H4/D1/W1
        out = []
        for ts, o, h, lo, c, v in rows:
            t = datetime.fromisoformat(ts)
            if start <= t < end and (tf != TF.M1 or self.m1_until is None or t + MIN <= self.m1_until):
                out.append(StoredBar(t, o, h, lo, c, v, None, tf, instrument))
        return out


@lru_cache(maxsize=None)
def data_for(instrument: str = "EURUSD") -> InstrumentData:
    data = load_instrument(FixtureSource(instrument), instrument, START, END, CFG, MT5ServerClock("ny_close"),
                           venue="mt5", max_gap_minutes=30)
    assert data.coverage.ok, data.coverage.problems
    return data


def entry_closes(data: InstrumentData, start: datetime, end: datetime) -> list[datetime]:
    last_close = data.m1[-1].timestamp + MIN
    closes = (CAL.period_end(b.timestamp, TF.M15) for b in data.closed[TF.M15])
    return [t for t in closes if start <= t <= end and t <= last_close]


class FakeEngine:
    """Records what analyze() was given; grades nothing."""

    def __init__(self, fail_at: Optional[datetime] = None):
        self.calls = []
        self.fail_at = fail_at

    def analyze(self, view, instrument, t):
        self.calls.append((t, view[TF.M15][-1].timestamp))
        if t == self.fail_at:
            raise ValueError("engine blew up")
        return SimpleNamespace(setup_grade=None)


def test_one_record_per_entry_tf_close():
    data = data_for()
    start, end = datetime(2026, 9, 30, 13, 0, tzinfo=UTC), datetime(2026, 9, 30, 16, 0, tzinfo=UTC)
    records = list(generate_signals(data, CFG, start, end, engine=FakeEngine()))
    assert [r.t for r in records] == entry_closes(data, start, end)
    assert len(records) == 13  # 13:00, 13:15, ..., 16:00 inclusive
    assert all(r.instrument == "EURUSD" and isinstance(r.result, NoTrade) for r in records)


def test_analyze_called_with_as_of_time():
    data = data_for()
    engine = FakeEngine()
    start, end = datetime(2026, 9, 30, 13, 0, tzinfo=UTC), datetime(2026, 9, 30, 14, 0, tzinfo=UTC)
    records = list(generate_signals(data, CFG, start, end, engine=engine))
    for record, (t, last_entry_open) in zip(records, engine.calls):
        assert t == record.t                          # never the wall clock
        assert last_entry_open + 15 * MIN == t        # the view ends with the bar that closed at t


def test_engine_exception_becomes_engine_error_record():
    data = data_for()
    start, end = datetime(2026, 9, 30, 13, 0, tzinfo=UTC), datetime(2026, 9, 30, 14, 0, tzinfo=UTC)
    fail_at = datetime(2026, 9, 30, 13, 30, tzinfo=UTC)
    records = list(generate_signals(data, CFG, start, end, engine=FakeEngine(fail_at=fail_at)))
    assert len(records) == 5  # generation carries on past the failure
    failed = next(r for r in records if r.t == fail_at)
    assert failed.result == EngineError(exception="ValueError", message="engine blew up")


def test_real_engine_produces_records_on_fixture_week():
    data = data_for()
    start, end = datetime(2026, 9, 30, 12, 0, tzinfo=UTC), datetime(2026, 9, 30, 15, 0, tzinfo=UTC)
    records = list(generate_signals(data, CFG, start, end))
    assert records and all(isinstance(r.result, (OrderIntent, NoTrade)) for r in records)


def test_parallel_per_instrument_equals_sequential():
    datas = [data_for("EURUSD"), data_for("XAUUSD")]
    start, end = datetime(2026, 9, 30, 13, 0, tzinfo=UTC), datetime(2026, 9, 30, 14, 30, tzinfo=UTC)
    sequential = generate_all(datas, CFG, start, end, workers=1)
    parallel = generate_all(datas, CFG, start, end, workers=2)
    assert parallel == sequential
    assert set(parallel) == {"EURUSD", "XAUUSD"} and all(parallel.values())
