"""
Tests for the tick normaliser and OHLCV candle builder.

TDD Phase: RED → GREEN → REFACTOR.
Run with:  cd backend && python -m pytest tests/test_candle_builder.py -v

All tests in this file must FAIL before any implementation is written.

**Validates: Requirements FR-1, FR-2**
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone, timedelta

import pytest
from hypothesis import given, settings as h_settings, assume
from hypothesis import strategies as st

# ---------------------------------------------------------------------------
# Path setup — add workspace root so `services` package is importable
# ---------------------------------------------------------------------------
_WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, _WORKSPACE_ROOT)

# ---------------------------------------------------------------------------
# Import targets — these will raise ImportError until 4b is implemented
# ---------------------------------------------------------------------------
from services.market_data.normaliser import Candle, TickNormaliser  # noqa: E402


# ===========================================================================
# Hypothesis strategies
# ===========================================================================

TIMEFRAMES = ["M1", "M5", "M15", "H1", "H4", "D1", "W1"]

# A strategy that generates a UTC-aware datetime within a reasonable range
utc_datetimes = st.datetimes(
    min_value=datetime(2020, 1, 1),
    max_value=datetime(2030, 12, 31),
    timezones=st.just(timezone.utc),
)

# A strategy for positive prices (realistic FX/index range)
prices = st.floats(min_value=0.0001, max_value=100_000.0, allow_nan=False, allow_infinity=False)

# A strategy for a sequence of at least 2 ticks (price, timestamp offset in seconds)
tick_sequences = st.lists(
    st.tuples(
        st.floats(min_value=0.0001, max_value=100_000.0, allow_nan=False, allow_infinity=False),
        st.integers(min_value=0, max_value=3600),  # offset in seconds from base
    ),
    min_size=2,
    max_size=20,
)


# ===========================================================================
# Helper: build a TickNormaliser and feed it a sequence of ticks
# ===========================================================================

def _feed_ticks(
    normaliser: TickNormaliser,
    instrument: str,
    base_time: datetime,
    tick_data: list[tuple[float, int]],
) -> list[Candle]:
    """Feed (price, offset_seconds) pairs into the normaliser and collect all candles."""
    all_candles: list[Candle] = []
    for price, offset in tick_data:
        ts = base_time + timedelta(seconds=offset)
        candles = normaliser.process_tick(instrument, price, ts)
        all_candles.extend(candles)
    return all_candles


# ===========================================================================
# Property 1: high >= open, high >= close, high >= low
# ===========================================================================

class TestHighIsMaximum:
    """Property: high must be >= open, close, and low for every candle."""

    @given(
        base_time=utc_datetimes,
        tick_data=tick_sequences,
    )
    @h_settings(max_examples=100)
    def test_high_gte_open(self, base_time: datetime, tick_data: list[tuple[float, int]]):
        """**Validates: Requirements FR-1** — high >= open for all candles."""
        normaliser = TickNormaliser(timeframes=["M1"])
        candles = _feed_ticks(normaliser, "EURUSD", base_time, tick_data)
        for candle in candles:
            assert candle.high >= candle.open, (
                f"high={candle.high} < open={candle.open} in candle {candle}"
            )

    @given(
        base_time=utc_datetimes,
        tick_data=tick_sequences,
    )
    @h_settings(max_examples=100)
    def test_high_gte_close(self, base_time: datetime, tick_data: list[tuple[float, int]]):
        """**Validates: Requirements FR-1** — high >= close for all candles."""
        normaliser = TickNormaliser(timeframes=["M1"])
        candles = _feed_ticks(normaliser, "EURUSD", base_time, tick_data)
        for candle in candles:
            assert candle.high >= candle.close, (
                f"high={candle.high} < close={candle.close} in candle {candle}"
            )

    @given(
        base_time=utc_datetimes,
        tick_data=tick_sequences,
    )
    @h_settings(max_examples=100)
    def test_high_gte_low(self, base_time: datetime, tick_data: list[tuple[float, int]]):
        """**Validates: Requirements FR-1** — high >= low for all candles."""
        normaliser = TickNormaliser(timeframes=["M1"])
        candles = _feed_ticks(normaliser, "EURUSD", base_time, tick_data)
        for candle in candles:
            assert candle.high >= candle.low, (
                f"high={candle.high} < low={candle.low} in candle {candle}"
            )


# ===========================================================================
# Property 2: low <= open, low <= close, low <= high
# ===========================================================================

class TestLowIsMinimum:
    """Property: low must be <= open, close, and high for every candle."""

    @given(
        base_time=utc_datetimes,
        tick_data=tick_sequences,
    )
    @h_settings(max_examples=100)
    def test_low_lte_open(self, base_time: datetime, tick_data: list[tuple[float, int]]):
        """**Validates: Requirements FR-1** — low <= open for all candles."""
        normaliser = TickNormaliser(timeframes=["M1"])
        candles = _feed_ticks(normaliser, "EURUSD", base_time, tick_data)
        for candle in candles:
            assert candle.low <= candle.open, (
                f"low={candle.low} > open={candle.open} in candle {candle}"
            )

    @given(
        base_time=utc_datetimes,
        tick_data=tick_sequences,
    )
    @h_settings(max_examples=100)
    def test_low_lte_close(self, base_time: datetime, tick_data: list[tuple[float, int]]):
        """**Validates: Requirements FR-1** — low <= close for all candles."""
        normaliser = TickNormaliser(timeframes=["M1"])
        candles = _feed_ticks(normaliser, "EURUSD", base_time, tick_data)
        for candle in candles:
            assert candle.low <= candle.close, (
                f"low={candle.low} > close={candle.close} in candle {candle}"
            )

    @given(
        base_time=utc_datetimes,
        tick_data=tick_sequences,
    )
    @h_settings(max_examples=100)
    def test_low_lte_high(self, base_time: datetime, tick_data: list[tuple[float, int]]):
        """**Validates: Requirements FR-1** — low <= high for all candles."""
        normaliser = TickNormaliser(timeframes=["M1"])
        candles = _feed_ticks(normaliser, "EURUSD", base_time, tick_data)
        for candle in candles:
            assert candle.low <= candle.high, (
                f"low={candle.low} > high={candle.high} in candle {candle}"
            )


# ===========================================================================
# Property 3: candle time is always aligned to the timeframe boundary
# ===========================================================================

class TestCandleTimeAlignment:
    """Property: candle.time must be aligned to the timeframe boundary."""

    @given(
        base_time=utc_datetimes,
        tick_data=tick_sequences,
    )
    @h_settings(max_examples=100)
    def test_m1_time_aligned_to_minute(self, base_time: datetime, tick_data: list[tuple[float, int]]):
        """**Validates: Requirements FR-1** — M1 candle time has seconds=0."""
        normaliser = TickNormaliser(timeframes=["M1"])
        candles = _feed_ticks(normaliser, "EURUSD", base_time, tick_data)
        for candle in candles:
            assert candle.time.second == 0, f"M1 candle time not aligned: {candle.time}"
            assert candle.time.microsecond == 0, f"M1 candle time has microseconds: {candle.time}"

    @given(
        base_time=utc_datetimes,
        tick_data=tick_sequences,
    )
    @h_settings(max_examples=100)
    def test_m5_time_aligned_to_5_minute_boundary(self, base_time: datetime, tick_data: list[tuple[float, int]]):
        """**Validates: Requirements FR-1** — M5 candle time is on a 5-minute boundary."""
        normaliser = TickNormaliser(timeframes=["M5"])
        candles = _feed_ticks(normaliser, "EURUSD", base_time, tick_data)
        for candle in candles:
            assert candle.time.minute % 5 == 0, f"M5 candle time not aligned: {candle.time}"
            assert candle.time.second == 0, f"M5 candle time has seconds: {candle.time}"

    @given(
        base_time=utc_datetimes,
        tick_data=tick_sequences,
    )
    @h_settings(max_examples=100)
    def test_m15_time_aligned_to_15_minute_boundary(self, base_time: datetime, tick_data: list[tuple[float, int]]):
        """**Validates: Requirements FR-1** — M15 candle time is on a 15-minute boundary."""
        normaliser = TickNormaliser(timeframes=["M15"])
        candles = _feed_ticks(normaliser, "EURUSD", base_time, tick_data)
        for candle in candles:
            assert candle.time.minute % 15 == 0, f"M15 candle time not aligned: {candle.time}"
            assert candle.time.second == 0, f"M15 candle time has seconds: {candle.time}"

    @given(
        base_time=utc_datetimes,
        tick_data=tick_sequences,
    )
    @h_settings(max_examples=100)
    def test_h1_time_aligned_to_hour(self, base_time: datetime, tick_data: list[tuple[float, int]]):
        """**Validates: Requirements FR-1** — H1 candle time has minute=0, second=0."""
        normaliser = TickNormaliser(timeframes=["H1"])
        candles = _feed_ticks(normaliser, "EURUSD", base_time, tick_data)
        for candle in candles:
            assert candle.time.minute == 0, f"H1 candle time not aligned: {candle.time}"
            assert candle.time.second == 0, f"H1 candle time has seconds: {candle.time}"

    @given(
        base_time=utc_datetimes,
        tick_data=tick_sequences,
    )
    @h_settings(max_examples=100)
    def test_h4_time_aligned_to_4_hour_boundary(self, base_time: datetime, tick_data: list[tuple[float, int]]):
        """**Validates: Requirements FR-1** — H4 candle time is on a 4-hour boundary (0,4,8,12,16,20)."""
        normaliser = TickNormaliser(timeframes=["H4"])
        candles = _feed_ticks(normaliser, "EURUSD", base_time, tick_data)
        for candle in candles:
            assert candle.time.hour % 4 == 0, f"H4 candle time not aligned: {candle.time}"
            assert candle.time.minute == 0, f"H4 candle time has minutes: {candle.time}"
            assert candle.time.second == 0, f"H4 candle time has seconds: {candle.time}"

    @given(
        base_time=utc_datetimes,
        tick_data=tick_sequences,
    )
    @h_settings(max_examples=100)
    def test_d1_time_aligned_to_day(self, base_time: datetime, tick_data: list[tuple[float, int]]):
        """**Validates: Requirements FR-1** — D1 candle time is at 00:00:00 UTC."""
        normaliser = TickNormaliser(timeframes=["D1"])
        candles = _feed_ticks(normaliser, "EURUSD", base_time, tick_data)
        for candle in candles:
            assert candle.time.hour == 0, f"D1 candle time not aligned: {candle.time}"
            assert candle.time.minute == 0, f"D1 candle time has minutes: {candle.time}"
            assert candle.time.second == 0, f"D1 candle time has seconds: {candle.time}"

    @given(
        base_time=utc_datetimes,
        tick_data=tick_sequences,
    )
    @h_settings(max_examples=100)
    def test_w1_time_aligned_to_monday(self, base_time: datetime, tick_data: list[tuple[float, int]]):
        """**Validates: Requirements FR-1** — W1 candle time is Monday 00:00:00 UTC."""
        normaliser = TickNormaliser(timeframes=["W1"])
        candles = _feed_ticks(normaliser, "EURUSD", base_time, tick_data)
        for candle in candles:
            # weekday() == 0 means Monday
            assert candle.time.weekday() == 0, (
                f"W1 candle time is not Monday: {candle.time} (weekday={candle.time.weekday()})"
            )
            assert candle.time.hour == 0, f"W1 candle time not at midnight: {candle.time}"
            assert candle.time.minute == 0, f"W1 candle time has minutes: {candle.time}"
            assert candle.time.second == 0, f"W1 candle time has seconds: {candle.time}"


# ===========================================================================
# Test: complete=True emitted exactly on timeframe boundary close
# ===========================================================================

class TestCandleCompletion:
    """complete=True must be emitted exactly when a tick crosses the timeframe boundary."""

    def test_complete_true_emitted_on_boundary_cross(self):
        """
        Feed two ticks in the same M1 candle, then one tick in the next minute.
        The third tick should trigger complete=True for the first candle.
        """
        normaliser = TickNormaliser(timeframes=["M1"])

        # Tick 1: 10:00:00 UTC — opens M1 candle at 10:00
        t1 = datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
        candles1 = normaliser.process_tick("EURUSD", 1.0850, t1)
        assert len(candles1) == 1
        assert candles1[0].complete is False, "First tick should produce incomplete candle"

        # Tick 2: 10:00:30 UTC — still in same M1 candle
        t2 = datetime(2024, 1, 15, 10, 0, 30, tzinfo=timezone.utc)
        candles2 = normaliser.process_tick("EURUSD", 1.0860, t2)
        assert len(candles2) == 1
        assert candles2[0].complete is False, "Intra-candle tick should produce incomplete candle"

        # Tick 3: 10:01:00 UTC — crosses into next M1 candle
        t3 = datetime(2024, 1, 15, 10, 1, 0, tzinfo=timezone.utc)
        candles3 = normaliser.process_tick("EURUSD", 1.0855, t3)
        # Should emit the completed previous candle AND the new incomplete candle
        complete_candles = [c for c in candles3 if c.complete is True]
        assert len(complete_candles) >= 1, (
            "Crossing the boundary should emit at least one complete=True candle"
        )
        # The completed candle should be for the 10:00 period
        completed = complete_candles[0]
        assert completed.time == datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)

    def test_complete_true_on_m5_boundary(self):
        """M5 candle completes when a tick arrives at or after the 5-minute boundary."""
        normaliser = TickNormaliser(timeframes=["M5"])

        # Tick in 10:00–10:05 window
        t1 = datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
        normaliser.process_tick("EURUSD", 1.0850, t1)

        t2 = datetime(2024, 1, 15, 10, 3, 0, tzinfo=timezone.utc)
        normaliser.process_tick("EURUSD", 1.0860, t2)

        # Tick at 10:05:00 — crosses boundary
        t3 = datetime(2024, 1, 15, 10, 5, 0, tzinfo=timezone.utc)
        candles3 = normaliser.process_tick("EURUSD", 1.0855, t3)

        complete_candles = [c for c in candles3 if c.complete is True]
        assert len(complete_candles) >= 1
        assert complete_candles[0].time == datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)

    def test_complete_true_on_h4_boundary(self):
        """H4 candle completes when a tick arrives at or after the 4-hour boundary."""
        normaliser = TickNormaliser(timeframes=["H4"])

        # Tick in 08:00–12:00 window
        t1 = datetime(2024, 1, 15, 8, 0, 0, tzinfo=timezone.utc)
        normaliser.process_tick("XAUUSD", 2000.0, t1)

        t2 = datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
        normaliser.process_tick("XAUUSD", 2010.0, t2)

        # Tick at 12:00:00 — crosses H4 boundary
        t3 = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        candles3 = normaliser.process_tick("XAUUSD", 2005.0, t3)

        complete_candles = [c for c in candles3 if c.complete is True]
        assert len(complete_candles) >= 1
        assert complete_candles[0].time == datetime(2024, 1, 15, 8, 0, 0, tzinfo=timezone.utc)


# ===========================================================================
# Test: complete=False emitted on intra-candle tick updates
# ===========================================================================

class TestIntraCandleUpdates:
    """complete=False must be emitted for all ticks within the same timeframe period."""

    def test_intra_candle_ticks_are_incomplete(self):
        """All ticks within the same M1 period must produce complete=False."""
        normaliser = TickNormaliser(timeframes=["M1"])

        base = datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
        for offset in [0, 10, 20, 30, 40, 50]:
            ts = base + timedelta(seconds=offset)
            candles = normaliser.process_tick("EURUSD", 1.0850 + offset * 0.0001, ts)
            for candle in candles:
                assert candle.complete is False, (
                    f"Intra-candle tick at offset {offset}s should be incomplete, got {candle}"
                )

    def test_multiple_timeframes_all_incomplete_intra_candle(self):
        """All timeframes should emit incomplete candles for intra-period ticks."""
        normaliser = TickNormaliser(timeframes=["M1", "M5", "H1"])

        # All ticks within the first minute — all timeframes should be incomplete
        base = datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
        for offset in [0, 15, 30, 45]:
            ts = base + timedelta(seconds=offset)
            candles = normaliser.process_tick("EURUSD", 1.0850, ts)
            for candle in candles:
                assert candle.complete is False, (
                    f"Candle {candle.timeframe} at offset {offset}s should be incomplete"
                )

    def test_ohlcv_updates_correctly_intra_candle(self):
        """OHLCV values must update correctly as ticks arrive within the same candle."""
        normaliser = TickNormaliser(timeframes=["M1"])

        base = datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)

        # Tick 1: open = 1.0850
        c1 = normaliser.process_tick("EURUSD", 1.0850, base)
        assert c1[0].open == pytest.approx(1.0850)
        assert c1[0].high == pytest.approx(1.0850)
        assert c1[0].low == pytest.approx(1.0850)
        assert c1[0].close == pytest.approx(1.0850)

        # Tick 2: price goes up to 1.0870 — high should update
        c2 = normaliser.process_tick("EURUSD", 1.0870, base + timedelta(seconds=10))
        assert c2[0].open == pytest.approx(1.0850)  # open unchanged
        assert c2[0].high == pytest.approx(1.0870)  # high updated
        assert c2[0].low == pytest.approx(1.0850)   # low unchanged
        assert c2[0].close == pytest.approx(1.0870)  # close updated

        # Tick 3: price drops to 1.0830 — low should update
        c3 = normaliser.process_tick("EURUSD", 1.0830, base + timedelta(seconds=20))
        assert c3[0].open == pytest.approx(1.0850)  # open unchanged
        assert c3[0].high == pytest.approx(1.0870)  # high unchanged
        assert c3[0].low == pytest.approx(1.0830)   # low updated
        assert c3[0].close == pytest.approx(1.0830)  # close updated


# ===========================================================================
# Test: UTC timestamps used throughout
# ===========================================================================

class TestUTCTimestamps:
    """All datetime objects in Candle must be timezone-aware with tzinfo=timezone.utc."""

    def test_candle_time_is_utc_aware(self):
        """candle.time must be timezone-aware with UTC tzinfo."""
        normaliser = TickNormaliser(timeframes=["M1"])
        ts = datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
        candles = normaliser.process_tick("EURUSD", 1.0850, ts)
        for candle in candles:
            assert candle.time.tzinfo is not None, "candle.time must be timezone-aware"
            assert candle.time.utcoffset() == timedelta(0), (
                f"candle.time must be UTC, got offset={candle.time.utcoffset()}"
            )

    def test_candle_time_utc_across_all_timeframes(self):
        """All timeframes must produce UTC-aware candle times."""
        normaliser = TickNormaliser(timeframes=TIMEFRAMES)
        ts = datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
        candles = normaliser.process_tick("EURUSD", 1.0850, ts)
        assert len(candles) == len(TIMEFRAMES), (
            f"Expected {len(TIMEFRAMES)} candles, got {len(candles)}"
        )
        for candle in candles:
            assert candle.time.tzinfo is not None, (
                f"candle.time for {candle.timeframe} must be timezone-aware"
            )
            assert candle.time.utcoffset() == timedelta(0), (
                f"candle.time for {candle.timeframe} must be UTC"
            )

    def test_naive_datetime_raises_or_is_handled(self):
        """Passing a naive datetime should raise ValueError."""
        normaliser = TickNormaliser(timeframes=["M1"])
        naive_ts = datetime(2024, 1, 15, 10, 0, 0)  # no tzinfo
        with pytest.raises((ValueError, TypeError)):
            normaliser.process_tick("EURUSD", 1.0850, naive_ts)

    def test_candle_dataclass_fields(self):
        """Candle must have all required fields: instrument, timeframe, time, open, high, low, close, volume, complete."""
        normaliser = TickNormaliser(timeframes=["M1"])
        ts = datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
        candles = normaliser.process_tick("EURUSD", 1.0850, ts)
        assert len(candles) == 1
        candle = candles[0]
        assert hasattr(candle, "instrument")
        assert hasattr(candle, "timeframe")
        assert hasattr(candle, "time")
        assert hasattr(candle, "open")
        assert hasattr(candle, "high")
        assert hasattr(candle, "low")
        assert hasattr(candle, "close")
        assert hasattr(candle, "volume")
        assert hasattr(candle, "complete")

    def test_candle_instrument_and_timeframe_values(self):
        """Candle must carry the correct instrument and timeframe labels."""
        normaliser = TickNormaliser(timeframes=["M1", "H1"])
        ts = datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
        candles = normaliser.process_tick("XAUUSD", 2000.0, ts)
        timeframes_seen = {c.timeframe for c in candles}
        assert "M1" in timeframes_seen
        assert "H1" in timeframes_seen
        for candle in candles:
            assert candle.instrument == "XAUUSD"

    def test_volume_accumulates_across_ticks(self):
        """Volume should accumulate (count of ticks) within a candle period."""
        normaliser = TickNormaliser(timeframes=["M1"])
        base = datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
        for i in range(5):
            candles = normaliser.process_tick("EURUSD", 1.0850, base + timedelta(seconds=i * 10))
        # After 5 ticks, volume should be 5
        assert candles[0].volume == pytest.approx(5.0)

    def test_multiple_instruments_tracked_independently(self):
        """Different instruments must have independent candle state."""
        normaliser = TickNormaliser(timeframes=["M1"])
        base = datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)

        normaliser.process_tick("EURUSD", 1.0850, base)
        normaliser.process_tick("XAUUSD", 2000.0, base + timedelta(seconds=5))

        # EURUSD tick
        eu_candles = normaliser.process_tick("EURUSD", 1.0860, base + timedelta(seconds=10))
        xau_candles = normaliser.process_tick("XAUUSD", 2010.0, base + timedelta(seconds=15))

        eu_candle = eu_candles[0]
        xau_candle = xau_candles[0]

        assert eu_candle.instrument == "EURUSD"
        assert xau_candle.instrument == "XAUUSD"
        assert eu_candle.open == pytest.approx(1.0850)
        assert xau_candle.open == pytest.approx(2000.0)
