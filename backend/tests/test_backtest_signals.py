"""
Tests for algo_backtester/signals.py — Phase A: the engine's decision at
every entry-timeframe close.

Tasks 199 and 217 (.kiro/specs/algo-backtester/tasks.md). Real data: the
task 186 MetaQuotes-Demo fixtures (New York-close server), one week of M1
plus a year of native H1/H4/D1/W1 for the warm-up. Small windows keep the
engine quick.
Validates: Requirements 1.1, 9.2, 11.5, 11.6 (.kiro/specs/algo-backtester/requirements.md)
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
from algo_backtester.signals import (
    EngineError,
    SignalRecord,
    TradeContext,
    generate_all,
    generate_signals,
    signal_at,
    trade_context,
)
from liquidity_engine import LiquidityMappingEngine
from liquidity_engine.models import Timeframe as TF
from liquidity_engine.utils.time_utils import get_killzone
from services.market_data.as_of_view import compose_as_of_view
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


def test_minimum_stop_rule_gets_the_spread():
    # Without the spread the rule can't be applied, and every record says so (Req 25.2).
    tight = CFG.model_copy(update={"min_stop_spreads": 2.0})
    start, end = datetime(2026, 9, 30, 13, 0, tzinfo=UTC), datetime(2026, 9, 30, 14, 0, tzinfo=UTC)
    without = list(generate_signals(data_for(), tight, start, end))
    assert {type(r.result) for r in without} == {EngineError}
    given = list(generate_signals(data_for(), tight, start, end, typical_spread=0.0001))
    assert given and not any(isinstance(r.result, EngineError) for r in given)
    assert generate_all([data_for()], tight, start, end, workers=1, spreads={"EURUSD": 0.0001}) == {"EURUSD": given}


def test_parallel_per_instrument_equals_sequential():
    datas = [data_for("EURUSD"), data_for("XAUUSD")]
    start, end = datetime(2026, 9, 30, 13, 0, tzinfo=UTC), datetime(2026, 9, 30, 14, 30, tzinfo=UTC)
    sequential = generate_all(datas, CFG, start, end, workers=1)
    parallel = generate_all(datas, CFG, start, end, workers=2)
    assert parallel == sequential
    assert set(parallel) == {"EURUSD", "XAUUSD"} and all(parallel.values())


# ── TradeContext (task 217, Req 11.5) ──────────────────────────────────────
# 12:00-14:00 UTC on 2026-09-30 holds both order intents and no-trades.
CONTEXT_START, CONTEXT_END = datetime(2026, 9, 30, 12, 0, tzinfo=UTC), datetime(2026, 9, 30, 14, 0, tzinfo=UTC)


@lru_cache(maxsize=None)
def context_records() -> tuple[SignalRecord, ...]:
    records = tuple(generate_signals(data_for(), CFG, CONTEXT_START, CONTEXT_END))
    assert {type(r.result) for r in records} == {OrderIntent, NoTrade}
    return records


def liquidity_map_at(t: datetime):
    data = data_for()
    view = compose_as_of_view(data.closed, data.m1, t, CFG.entry_tf, CFG.candle_counts, CAL)
    return LiquidityMappingEngine().analyze(view, data.instrument, t)


def test_order_intent_records_carry_trade_context():
    intents = [r for r in context_records() if isinstance(r.result, OrderIntent)]
    for record in intents:
        liquidity_map = liquidity_map_at(record.t)
        context, grade, draw = record.context, liquidity_map.setup_grade, liquidity_map.draw_on_liquidity
        # the array the grader chose, as the grader itself describes it
        assert (context.entry_array["high"], context.entry_array["low"]) == (grade.entry_array_high,
                                                                             grade.entry_array_low)
        assert context.entry_array["direction"] == grade.entry_array_direction.value
        assert context.entry_array["timeframe"] == "M15"           # entries come from the entry timeframe
        assert context.entry_array["type"] and datetime.fromisoformat(context.entry_array["formed_at"]) < record.t
        assert context.draw_on_liquidity == {"type": draw.liquidity_type.value, "source": draw.source.value,
                                             "price": draw.price, "formed_at": draw.formed_at.isoformat()}
        assert context.swept_level is not None and context.protected_swing is not None
        assert context.killzone == get_killzone(record.t).value != "NONE"
        json.dumps(vars(context))                                   # ready for the report as it is


def test_trade_context_records_raid_and_protected_swing():
    # liquidity-engine Requirement 19.5: the raid and the protected swing, as the report draws them.
    intents = [r for r in context_records() if isinstance(r.result, OrderIntent)]
    assert intents
    for record in intents:
        sequence = liquidity_map_at(record.t).setup_sequence
        pool, swing = sequence.raid.pool, sequence.protected_swing
        assert record.context.swept_level == {
            "side": pool.side.value, "source": pool.source.value, "timeframe": pool.timeframe.value,
            "price": pool.price, "formed_at": pool.formed_at.isoformat(),
            "raided_at": sequence.raid.raided_at.isoformat(),
        }
        assert record.context.protected_swing == {
            "wick": swing.wick, "body": swing.body, "candle_at": swing.candle_at.isoformat(),
        }
        # the raid comes before the array the order trades, which comes before t
        raided_at = datetime.fromisoformat(record.context.swept_level["raided_at"])
        assert raided_at <= datetime.fromisoformat(record.context.entry_array["formed_at"]) < record.t
        # the pool is on the side opposite the trade: sell stops below a LONG, buy stops above a SHORT
        assert record.context.swept_level["side"] == ("SSL" if record.result.direction == "LONG" else "BSL")


def test_no_trade_records_carry_no_context():
    no_trades = [r for r in context_records() if isinstance(r.result, NoTrade)]
    fail_at = datetime(2026, 9, 30, 13, 30, tzinfo=UTC)
    failed = signal_at(data_for(), CFG, fail_at, engine=FakeEngine(fail_at=fail_at))
    for record in [*no_trades, failed]:
        assert record.context is None
        assert "context" not in record.to_json()                    # keeps the cache small


def test_killzone_none_outside_killzones():
    t = datetime(2026, 9, 30, 13, 0, tzinfo=UTC)
    noon_new_york = datetime(2026, 9, 30, 16, 0, tzinfo=UTC)        # between NY AM and NY PM
    assert trade_context(liquidity_map_at(t), noon_new_york).killzone is None


def test_trade_context_round_trips_through_cache(tmp_path):
    from algo_backtester.cache import SignalCache

    cache = SignalCache(tmp_path, "e" * 64)
    stored = cache.store("k" * 64, context_records())
    loaded = cache.load("k" * 64)
    assert loaded == stored == list(context_records())
    assert all(type(r.context) is TradeContext for r in loaded if isinstance(r.result, OrderIntent))
