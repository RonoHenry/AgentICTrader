"""Tests for liquidity_engine.utils (time_utils, candle_utils)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
from hypothesis import given, strategies as st

from liquidity_engine.models import Candle, CandleType, KillzoneWindow, Timeframe
from liquidity_engine.utils.time_utils import (
    KILLZONE_WINDOWS,
    get_killzone,
    is_in_killzone,
    to_est,
    to_utc,
)
from liquidity_engine.utils.candle_utils import (
    EXPANSION_WICK_RATIO_MAX,
    REVERSAL_WICK_RATIO_MIN,
    calculate_atr,
    classify_candle_type,
    find_swing_highs,
    find_swing_lows,
)

NY = ZoneInfo("America/New_York")


def make_candle(open_, high, low, close, ts=None):
    return Candle(
        timestamp=ts or datetime.now(timezone.utc),
        open=open_,
        high=high,
        low=low,
        close=close,
        timeframe=Timeframe.M5,
        instrument="EURUSD",
    )


class TestTimeUtils:
    def test_to_est_from_utc(self):
        """UTC datetime correctly offset to EST (UTC-5) / EDT (UTC-4)."""
        winter_utc = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        est = to_est(winter_utc)
        assert est.utcoffset() == timedelta(hours=-5)
        assert est.hour == 7

        summer_utc = datetime(2024, 7, 15, 12, 0, 0, tzinfo=timezone.utc)
        edt = to_est(summer_utc)
        assert edt.utcoffset() == timedelta(hours=-4)
        assert edt.hour == 8

    def test_to_utc_from_est(self):
        """EST/EDT correctly converted back to UTC."""
        est_dt = datetime(2024, 1, 15, 7, 0, 0, tzinfo=NY)
        utc_dt = to_utc(est_dt)
        assert utc_dt.tzinfo is not None
        assert utc_dt.utcoffset() == timedelta(0)
        assert utc_dt.hour == 12

    def test_killzone_london_start_end(self):
        """02:00-05:00 EST correctly identified."""
        assert get_killzone(datetime(2024, 1, 15, 2, 0, 0, tzinfo=NY)) == KillzoneWindow.LONDON
        assert get_killzone(datetime(2024, 1, 15, 5, 0, 0, tzinfo=NY)) == KillzoneWindow.LONDON
        assert get_killzone(datetime(2024, 1, 15, 3, 30, 0, tzinfo=NY)) == KillzoneWindow.LONDON
        assert get_killzone(datetime(2024, 1, 15, 1, 59, 59, tzinfo=NY)) != KillzoneWindow.LONDON

    def test_killzone_ny_am_start_end(self):
        """07:00-10:00 EST correctly identified."""
        assert get_killzone(datetime(2024, 1, 15, 7, 0, 0, tzinfo=NY)) == KillzoneWindow.NY_AM
        assert get_killzone(datetime(2024, 1, 15, 10, 0, 0, tzinfo=NY)) == KillzoneWindow.NY_AM
        assert get_killzone(datetime(2024, 1, 15, 8, 30, 0, tzinfo=NY)) == KillzoneWindow.NY_AM

    def test_killzone_ny_pm_start_end(self):
        """13:30-16:00 EST correctly identified."""
        assert get_killzone(datetime(2024, 1, 15, 13, 30, 0, tzinfo=NY)) == KillzoneWindow.NY_PM
        assert get_killzone(datetime(2024, 1, 15, 16, 0, 0, tzinfo=NY)) == KillzoneWindow.NY_PM
        assert get_killzone(datetime(2024, 1, 15, 14, 45, 0, tzinfo=NY)) == KillzoneWindow.NY_PM

    def test_get_killzone_returns_correct_window(self):
        """All three killzone windows + NONE."""
        assert get_killzone(datetime(2024, 1, 15, 3, 0, 0, tzinfo=NY)) == KillzoneWindow.LONDON
        assert get_killzone(datetime(2024, 1, 15, 9, 0, 0, tzinfo=NY)) == KillzoneWindow.NY_AM
        assert get_killzone(datetime(2024, 1, 15, 15, 0, 0, tzinfo=NY)) == KillzoneWindow.NY_PM
        assert get_killzone(datetime(2024, 1, 15, 12, 0, 0, tzinfo=NY)) == KillzoneWindow.NONE
        assert get_killzone(datetime(2024, 1, 15, 20, 0, 0, tzinfo=NY)) == KillzoneWindow.NONE

    def test_is_in_killzone_true_false(self):
        """Boundary timestamps tested."""
        assert is_in_killzone(datetime(2024, 1, 15, 2, 0, 0, tzinfo=NY)) is True
        assert is_in_killzone(datetime(2024, 1, 15, 5, 0, 0, tzinfo=NY)) is True
        assert is_in_killzone(datetime(2024, 1, 15, 1, 59, 59, tzinfo=NY)) is False
        assert is_in_killzone(datetime(2024, 1, 15, 5, 0, 1, tzinfo=NY)) is False
        assert is_in_killzone(datetime(2024, 1, 15, 12, 0, 0, tzinfo=NY)) is False

    def test_dst_transition_march(self):
        """Spring-forward handled correctly (UTC-4)."""
        after_spring_forward = datetime(2024, 3, 15, 12, 0, 0, tzinfo=timezone.utc)
        assert to_est(after_spring_forward).utcoffset() == timedelta(hours=-4)

    def test_dst_transition_november(self):
        """Fall-back handled correctly (UTC-5)."""
        after_fall_back = datetime(2024, 11, 15, 12, 0, 0, tzinfo=timezone.utc)
        assert to_est(after_fall_back).utcoffset() == timedelta(hours=-5)

    def test_killzone_windows_constant_defined(self):
        """KILLZONE_WINDOWS maps each non-NONE window to a (start, end) time pair."""
        assert KillzoneWindow.LONDON in KILLZONE_WINDOWS
        assert KillzoneWindow.NY_AM in KILLZONE_WINDOWS
        assert KillzoneWindow.NY_PM in KILLZONE_WINDOWS


class TestCandleUtils:
    def test_swing_high_detected(self):
        """Local maximum identified after n-candle confirmation."""
        candles = [
            make_candle(1.0, 1.00, 0.99, 1.0),
            make_candle(1.0, 1.05, 0.99, 1.0),
            make_candle(1.0, 1.10, 0.99, 1.0),
            make_candle(1.0, 1.05, 0.99, 1.0),
            make_candle(1.0, 1.00, 0.99, 1.0),
        ]
        assert find_swing_highs(candles, lookback=2) == [2]

    def test_swing_low_detected(self):
        """Local minimum identified."""
        candles = [
            make_candle(1.0, 1.15, 1.10, 1.0),
            make_candle(1.0, 1.15, 1.05, 1.0),
            make_candle(1.0, 1.15, 1.00, 1.0),
            make_candle(1.0, 1.15, 1.05, 1.0),
            make_candle(1.0, 1.15, 1.10, 1.0),
        ]
        assert find_swing_lows(candles, lookback=2) == [2]

    def test_no_swing_flat_candles(self):
        """Flat sequence returns no swings."""
        candles = [make_candle(1.0, 1.0, 1.0, 1.0) for _ in range(6)]
        assert find_swing_highs(candles, lookback=2) == []
        assert find_swing_lows(candles, lookback=2) == []

    def test_atr_calculation(self):
        """ATR over n periods matches manual calculation."""
        candles = [
            make_candle(100, 100, 100, 100),
            make_candle(100, 105, 95, 100),
            make_candle(100, 110, 90, 100),
            make_candle(100, 108, 98, 103),
        ]
        # TR1 = max(105-95, |105-100|, |95-100|) = 10
        # TR2 = max(110-90, |110-100|, |90-100|) = 20
        # TR3 = max(108-98, |108-100|, |98-100|) = 10
        expected = (10 + 20 + 10) / 3
        assert calculate_atr(candles, period=3) == pytest.approx(expected)

    def test_classify_candle_type_expansion(self):
        """wick_ratio <= 0.25 -> CandleType.EXPANSION."""
        candle = make_candle(100, 110, 100, 109)  # upper_wick=1, lower_wick=0, ratio=0.1
        assert classify_candle_type(candle) == CandleType.EXPANSION

    def test_classify_candle_type_reversal(self):
        """wick_ratio >= 0.5 -> CandleType.REVERSAL."""
        candle = make_candle(105, 110, 100, 104)  # upper_wick=5, lower_wick=4, ratio=0.5
        assert classify_candle_type(candle) == CandleType.REVERSAL

    def test_classify_candle_type_reversal_expansion(self):
        """0.25 < wick_ratio < 0.5 -> CandleType.REVERSAL_EXPANSION."""
        candle = make_candle(100, 110, 100, 106.5)  # upper_wick=3.5, ratio=0.35
        assert classify_candle_type(candle) == CandleType.REVERSAL_EXPANSION

    def test_classify_candle_type_zero_range_is_expansion(self):
        """total_range == 0 -> CandleType.EXPANSION."""
        candle = make_candle(100, 100, 100, 100)
        assert classify_candle_type(candle) == CandleType.EXPANSION

    def test_classify_candle_type_thresholds_are_named_constants(self):
        """EXPANSION_WICK_RATIO_MAX and REVERSAL_WICK_RATIO_MIN are module-level constants."""
        assert EXPANSION_WICK_RATIO_MAX == 0.25
        assert REVERSAL_WICK_RATIO_MIN == 0.5


@st.composite
def _valid_candle(draw):
    open_ = draw(st.floats(min_value=1.0, max_value=1000.0, allow_nan=False, allow_infinity=False))
    low = draw(st.floats(min_value=1.0, max_value=1000.0, allow_nan=False, allow_infinity=False))
    close = draw(st.floats(min_value=1.0, max_value=1000.0, allow_nan=False, allow_infinity=False))
    extra = draw(st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False))
    high = max(open_, low, close) + extra
    return make_candle(open_, high, low, close)


class TestPropertyBasedTests:
    @given(candle=_valid_candle())
    def test_property_candle_type_classification_total(self, candle):
        """Property 26: classify_candle_type is total and exclusive."""
        result = classify_candle_type(candle)
        assert result in (CandleType.EXPANSION, CandleType.REVERSAL, CandleType.REVERSAL_EXPANSION)
