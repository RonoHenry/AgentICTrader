"""
Tests for algo_backtester/data.py — candle sources, the coverage check, the
data fingerprint, warm-up and per-bar spreads.

Task 198 (.kiro/specs/algo-backtester/tasks.md). Synthetic CSV fixtures are
written per test. The gap rules were calibrated on real data (task 186
fixtures): FX rollover leaves 4-7 minute gaps at 17:00 New York, gold stops
62 minutes daily at Exness and 120 at MetaQuotes, Binance has none.
Validates: Requirements 3.1, 3.2, 3.6, 3.7, 5.1 (.kiro/specs/algo-backtester/requirements.md)
"""
from __future__ import annotations

import os
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

import pytest

from agent.strategy_config import StrategyConfig
from algo_backtester.data import (
    CoverageError,
    CsvSource,
    StoredBar,
    check_coverage,
    ensure_coverage,
    fill_bars,
    fingerprint,
    load_instrument,
)
from liquidity_engine.models import Timeframe as TF
from services.market_data.mt5_clock import MT5ServerClock
from services.market_data.strategy_calendar import StrategyCalendar

UTC = timezone.utc
NY = ZoneInfo("America/New_York")
MIN = timedelta(minutes=1)
CAL = StrategyCalendar()


def ny(y: int, mo: int, d: int, h: int = 0, mi: int = 0) -> datetime:
    return datetime(y, mo, d, h, mi, tzinfo=NY).astimezone(UTC)


def m1(start: datetime, end: datetime, skip: tuple[tuple[datetime, datetime], ...] = (), price: float = 1.1,
       spread: Optional[float] = 0.0001, instrument: str = "EURUSD") -> list[StoredBar]:
    out, ts = [], start
    while ts < end:
        if not any(a <= ts < b for a, b in skip):
            out.append(StoredBar(timestamp=ts, open=price, high=price + 0.0005, low=price - 0.0005, close=price,
                                 volume=1, spread=spread, timeframe=TF.M1, instrument=instrument))
        ts += MIN
    return out


# ── coverage (Req 3.6) ──────────────────────────────────────────────────────

def test_weekend_gap_allowed_midweek_gap_refused():
    weekend = ((ny(2026, 1, 16, 17), ny(2026, 1, 18, 17)),)
    bars = m1(ny(2026, 1, 15, 10), ny(2026, 1, 19, 10), skip=weekend)
    assert check_coverage("EURUSD", bars, ny(2026, 1, 15, 10), ny(2026, 1, 19, 10), venue="mt5", max_gap_minutes=30).ok

    midweek = weekend + ((ny(2026, 1, 19, 8), ny(2026, 1, 19, 8, 45)),)
    cov = check_coverage("EURUSD", m1(ny(2026, 1, 15, 10), ny(2026, 1, 19, 10), skip=midweek),
                         ny(2026, 1, 15, 10), ny(2026, 1, 19, 10), venue="mt5", max_gap_minutes=30)
    assert not cov.ok
    [problem] = cov.problems
    assert "45 min" in problem and "2026-01-19" in problem

    # Binance trades 24/7: the same weekend gap is an outage there.
    assert not check_coverage("BTCUSDT", bars, ny(2026, 1, 15, 10), ny(2026, 1, 19, 10), venue="binance",
                              max_gap_minutes=30).ok


def test_daily_break_and_holidays_allowed_on_mt5():
    # Gold: no trading 16:57-18:00 New York every day (Exness), 62 minutes.
    gold = m1(ny(2026, 1, 13, 10), ny(2026, 1, 14, 10), skip=((ny(2026, 1, 13, 16, 57), ny(2026, 1, 13, 18)),))
    assert check_coverage("XAUUSD", gold, ny(2026, 1, 13, 10), ny(2026, 1, 14, 10), venue="mt5", max_gap_minutes=30).ok
    # Christmas Day closed.
    xmas = m1(ny(2025, 12, 23, 10), ny(2025, 12, 26, 10), skip=((ny(2025, 12, 24, 13), ny(2025, 12, 25, 17)),))
    assert check_coverage("EURUSD", xmas, ny(2025, 12, 23, 10), ny(2025, 12, 26, 10), venue="mt5", max_gap_minutes=30).ok
    # A long stop around 17:00 isn't a daily break.
    outage = m1(ny(2026, 1, 13, 10), ny(2026, 1, 14, 10), skip=((ny(2026, 1, 13, 15), ny(2026, 1, 13, 20)),))
    assert not check_coverage("EURUSD", outage, ny(2026, 1, 13, 10), ny(2026, 1, 14, 10), venue="mt5", max_gap_minutes=30).ok


def test_late_history_start_refused():
    bars = m1(ny(2026, 1, 14, 0), ny(2026, 1, 15, 0))  # history from Wednesday
    cov = check_coverage("EURUSD", bars, ny(2026, 1, 12, 0), ny(2026, 1, 15, 0), venue="mt5", max_gap_minutes=30)
    assert not cov.ok and any("starts" in p for p in cov.problems)

    # A run starting on Saturday with history from the Sunday open is fine.
    sunday = m1(ny(2026, 1, 18, 17), ny(2026, 1, 19, 17))
    assert check_coverage("EURUSD", sunday, ny(2026, 1, 17, 0), ny(2026, 1, 19, 17), venue="mt5", max_gap_minutes=30).ok

    # Nor may history end early.
    cov = check_coverage("EURUSD", bars, ny(2026, 1, 14, 0), ny(2026, 1, 16, 0), venue="mt5", max_gap_minutes=30)
    assert not cov.ok and any("ends" in p for p in cov.problems)


def test_allow_gaps_flag_permits_and_is_reported():
    cov = check_coverage("EURUSD", m1(ny(2026, 1, 14, 0), ny(2026, 1, 15, 0)), ny(2026, 1, 12, 0), ny(2026, 1, 15, 0),
                         venue="mt5", max_gap_minutes=30)
    with pytest.raises(CoverageError, match="EURUSD"):
        ensure_coverage([cov], allow_gaps=False)
    reported = ensure_coverage([cov], allow_gaps=True)  # allowed, but the problems are kept for the manifest
    assert reported == {"EURUSD": list(cov.problems)}


# ── fingerprint (Req 3.7) ───────────────────────────────────────────────────

def test_fingerprint_changes_when_one_row_changes():
    bars = m1(ny(2026, 1, 14, 9), ny(2026, 1, 14, 10))
    same = m1(ny(2026, 1, 14, 9), ny(2026, 1, 14, 10))
    changed = list(bars)
    changed[17] = replace(changed[17], close=changed[17].close + 0.00001)

    assert fingerprint(bars) == fingerprint(same)
    assert fingerprint(bars).rows == 60
    assert fingerprint(changed).sha256 != fingerprint(bars).sha256


# ── spreads (Req 5.1, D10) ──────────────────────────────────────────────────

def test_bar_spread_floored_at_typical_and_floored_bars_counted():
    recorded = [0.0003, 0.00005, None, 0.0001]  # wider, narrower, none recorded, equal
    bars = [StoredBar(timestamp=ny(2026, 1, 14, 9) + i * MIN, open=1.1, high=1.1, low=1.1, close=1.1, volume=1,
                      spread=s, timeframe=TF.M1, instrument="EURUSD") for i, s in enumerate(recorded)]
    out, floored = fill_bars(bars, default_spread=0.0001)
    assert [b.spread for b in out] == [0.0003, 0.0001, 0.0001, 0.0001]
    assert floored == 2  # the narrower one and the unrecorded one were priced at the typical spread


# ── warm-up (design: As-of view, backtest side) ─────────────────────────────

def _write_csv(path: Path, bars) -> None:
    lines = ["time,open,high,low,close,volume,spread"]
    for b in bars:
        spread = "" if b.spread is None else repr(b.spread)
        lines.append(f"{b.timestamp.isoformat()},{b.open!r},{b.high!r},{b.low!r},{b.close!r},{b.volume},{spread}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _native(tf: TF, start: datetime, end: datetime, instrument: str = "EURUSD") -> list[StoredBar]:
    out, ts = [], CAL.period_start(start, tf)
    while ts < end:
        out.append(StoredBar(timestamp=ts, open=1.2, high=1.21, low=1.19, close=1.2, volume=10, spread=None,
                             timeframe=tf, instrument=instrument))
        ts = CAL.period_end(ts, tf)
    return out


@pytest.mark.parametrize("server_clock, fallback", [("ny_close", "native"), ("+0", "native_h1")])
def test_warmup_falls_back_to_native_htf_and_reports_source(tmp_path, server_clock, fallback):
    # M1 for only the last two weeks; native bars go back a year. Small windows keep it quick.
    cfg = StrategyConfig(entry_tf="M15", context_tfs=("H4",),
                         candle_counts={"M15": 40, "H4": 30, "D1": 20, "W1": 8})
    start, end = ny(2026, 1, 19, 0), ny(2026, 1, 23, 17)
    _write_csv(tmp_path / "EURUSD_M1.csv", m1(ny(2026, 1, 9, 0), end))
    for tf in (TF.M15, TF.H1, TF.H4, TF.D1, TF.W1):
        _write_csv(tmp_path / f"EURUSD_{tf.value}.csv", _native(tf, ny(2025, 1, 1), end))

    data = load_instrument(CsvSource(tmp_path), "EURUSD", start, end, cfg, MT5ServerClock(server_clock),
                           venue="mt5", max_gap_minutes=30)

    # M15 and H4 windows fit inside the M1 history; D1 x 20 and W1 x 8 reach back before it.
    assert data.warmup_source == {"M15": "m1", "H4": "m1", "D1": fallback, "W1": fallback}
    for tf in (TF.D1, TF.W1):
        bars = data.closed[tf]
        before_m1 = [b for b in bars if b.timestamp < data.m1[0].timestamp]
        assert before_m1 and all(b.close == 1.2 for b in before_m1)       # from the native series
        assert len([b for b in bars if CAL.period_end(b.timestamp, tf) <= start]) >= cfg.candle_counts[tf]
        assert all(CAL.period_start(b.timestamp, tf) == b.timestamp for b in bars)  # on the strategy calendar
    assert data.coverage.ok


def test_short_warmup_reported(tmp_path):
    cfg = StrategyConfig(entry_tf="M15", context_tfs=("H4",), candle_counts={"M15": 40, "H4": 30, "D1": 20, "W1": 8})
    start, end = ny(2026, 1, 19, 0), ny(2026, 1, 23, 17)
    _write_csv(tmp_path / "EURUSD_M1.csv", m1(ny(2026, 1, 9, 0), end))  # no native series to fall back on
    data = load_instrument(CsvSource(tmp_path), "EURUSD", start, end, cfg, MT5ServerClock("ny_close"),
                           venue="mt5", max_gap_minutes=30)
    assert not data.coverage.ok
    assert any("W1" in p and "warm-up" in p for p in data.coverage.problems)


# ── TimescaleDB (needs the docker candle store) ─────────────────────────────

@pytest.mark.infrastructure
def test_timescale_source_reads_m1_utc():
    from algo_backtester.data import TimescaleSource

    url = os.environ.get("TIMESCALE_URL") or "postgresql://agentictrader:changeme@localhost:5432/agentictrader"
    end = datetime.now(UTC).replace(second=0, microsecond=0)
    bars = TimescaleSource(url, source="binance").bars("BTCUSDT", TF.M1, end - timedelta(hours=2), end)
    assert bars, "the paper trader stores Binance M1; is the candle store running?"
    assert all(b.timestamp.tzinfo is not None and b.timestamp.utcoffset() == timedelta(0) for b in bars)
    assert [b.timestamp for b in bars] == sorted({b.timestamp for b in bars})
    assert all(b.timeframe == TF.M1 and b.instrument == "BTCUSDT" for b in bars)
