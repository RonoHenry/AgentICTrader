"""
Aggregated bars must equal a venue's own native bars wherever the venue's
bars follow the strategy calendar.

Task 186 (.kiro/specs/algo-backtester/tasks.md). The fixtures are real venue
data exported by scripts/export_aggregation_fixture.py:
  - MetaQuotes-Demo (New York-close server): every timeframe lines up, so its
    native H4/D1/W1 bars check the calendar itself. One week of M1, plus 52
    weeks of H1 spanning both US DST changes (Nov 2025, Mar 2026).
  - Exness (UTC+0) and Binance (UTC): H1 lines up; H4/D1/W1 do not.
A mismatch means the calendar is wrong: fix the calendar, never the tolerance.
Validates: Requirements 3.4 (.kiro/specs/algo-backtester/requirements.md)
"""
from __future__ import annotations

import gzip
import json
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Optional

import pytest

from liquidity_engine.models import Candle, Timeframe
from services.market_data.as_of_view import aggregate
from services.market_data.mt5_clock import MT5ServerClock
from services.market_data.strategy_calendar import StrategyCalendar

FIXTURES = Path(__file__).parent / "fixtures" / "backtester" / "aggregation"
FIXTURE_FILES = sorted(FIXTURES.glob("*.json.gz"))
CALENDAR = StrategyCalendar()


@lru_cache(maxsize=None)
def _load(path: Path):
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        record = json.load(fh)
    instrument = record["instrument"]
    bars = {
        Timeframe(tf): [
            Candle(timestamp=datetime.fromisoformat(ts), open=o, high=h, low=lo, close=c, volume=v,
                   timeframe=Timeframe(tf), instrument=instrument)
            for ts, o, h, lo, c, v in rows
        ]
        for tf, rows in record["bars"].items()
    }
    return record, bars


def _clock(record) -> Optional[MT5ServerClock]:
    return MT5ServerClock(record["server_clock"]) if record["venue"] == "mt5" else None


def _cases():
    for path in FIXTURE_FILES:
        record, bars = _load(path)
        base = Timeframe(record["base_tf"])
        for tf in bars:
            if tf != base and CALENDAR.matches_native(_clock(record), tf):
                yield pytest.param(path, tf, id=f"{path.name.split('.')[0]}-{tf.value}")


def test_fixtures_present_and_cover_the_calendar():
    assert {p.name for p in FIXTURE_FILES} == {
        "binance_BTCUSDT_M1_20260926.json.gz",
        "exness-standard_EURUSD_M1_20260926.json.gz",
        "exness-standard_XAUUSD_M1_20260926.json.gz",
        "metaquotes-demo_EURUSD_M1_20260926.json.gz",
        "metaquotes-demo_EURUSD_H1_20251004.json.gz",
        "metaquotes-demo_XAUUSD_M1_20260926.json.gz",
        "metaquotes-demo_XAUUSD_H1_20251004.json.gz",
    }
    checked = {(param.values[0].name.split("_")[0], param.values[1]) for param in _cases()}
    # The point of the task: H4, D1 and W1 are checked against a New York-close server.
    for tf in (Timeframe.H1, Timeframe.H4, Timeframe.D1, Timeframe.W1):
        assert ("metaquotes-demo", tf) in checked
    assert ("exness-standard", Timeframe.H1) in checked and ("binance", Timeframe.H1) in checked


@pytest.mark.parametrize("path, tf", list(_cases()))
def test_aggregated_bars_match_native_within_one_tick(path, tf):
    record, bars = _load(path)
    base = Timeframe(record["base_tf"])
    start, end = datetime.fromisoformat(record["start"]), datetime.fromisoformat(record["end"])
    tick = record["tick_size"]

    native = {b.timestamp: b for b in bars[tf] if CALENDAR.period_end(b.timestamp, tf) <= end}
    aggregated = {b.timestamp: b for b in aggregate(bars[base], tf, CALENDAR, as_of=end)}

    assert native, "no native bars inside the window"
    assert sorted(aggregated) == sorted(native), (
        f"calendar periods differ: only aggregated {sorted(set(aggregated) - set(native))[:3]}, "
        f"only native {sorted(set(native) - set(aggregated))[:3]}"
    )
    assert min(native) >= start
    mismatches = [
        (ts, field, getattr(aggregated[ts], field), getattr(bar, field))
        for ts, bar in sorted(native.items())
        for field in ("open", "high", "low", "close")
        if abs(getattr(aggregated[ts], field) - getattr(bar, field)) > tick * (1 + 1e-9)
    ]
    assert not mismatches, f"{len(mismatches)} prices off by more than one tick ({tick}), e.g. {mismatches[:5]}"


def test_parity_check_detects_a_different_calendar():
    # Negative control: Exness's native D1 bars start at 00:00 UTC, not at
    # 17:00 New York, so they must NOT line up with the strategy calendar.
    # If this passed by matching, the parity test above would prove nothing.
    record, bars = _load(FIXTURES / "exness-standard_EURUSD_M1_20260926.json.gz")
    assert not CALENDAR.matches_native(_clock(record), Timeframe.D1)
    end = datetime.fromisoformat(record["end"])

    aggregated = aggregate(bars[Timeframe.M1], Timeframe.D1, CALENDAR, as_of=end)

    assert aggregated and bars[Timeframe.D1]
    assert {b.timestamp for b in aggregated}.isdisjoint(b.timestamp for b in bars[Timeframe.D1])
