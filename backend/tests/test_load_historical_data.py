"""
Tests for the historical data loading script.

Run with: pytest backend/tests/test_load_historical_data.py -v
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

# Add scripts directory to path
scripts_dir = Path(__file__).parent.parent.parent / "scripts"
sys.path.insert(0, str(scripts_dir))

from load_historical_data import (
    Candle,
    INSTRUMENT_MAPPING,
    TIMEFRAME_MAPPING,
    TIMEFRAME_DURATIONS,
    detect_gaps,
)


class TestCandleValidation:
    """Test OHLC validation logic."""

    def test_valid_candle_passes_validation(self):
        """A valid candle with proper OHLC relationships should pass."""
        candle = Candle(
            time=datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc),
            instrument="EURUSD",
            timeframe="M1",
            open=Decimal("1.0850"),
            high=Decimal("1.0860"),
            low=Decimal("1.0840"),
            close=Decimal("1.0855"),
            volume=1000,
            complete=True,
        )
        assert candle.validate_ohlc() is True

    def test_high_below_open_fails_validation(self):
        """High must be >= open."""
        candle = Candle(
            time=datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc),
            instrument="EURUSD",
            timeframe="M1",
            open=Decimal("1.0850"),
            high=Decimal("1.0840"),  # Invalid: high < open
            low=Decimal("1.0830"),
            close=Decimal("1.0845"),
            volume=1000,
            complete=True,
        )
        assert candle.validate_ohlc() is False

    def test_high_below_close_fails_validation(self):
        """High must be >= close."""
        candle = Candle(
            time=datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc),
            instrument="EURUSD",
            timeframe="M1",
            open=Decimal("1.0840"),
            high=Decimal("1.0850"),
            low=Decimal("1.0830"),
            close=Decimal("1.0860"),  # Invalid: close > high
            volume=1000,
            complete=True,
        )
        assert candle.validate_ohlc() is False

    def test_low_above_open_fails_validation(self):
        """Low must be <= open."""
        candle = Candle(
            time=datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc),
            instrument="EURUSD",
            timeframe="M1",
            open=Decimal("1.0840"),
            high=Decimal("1.0860"),
            low=Decimal("1.0850"),  # Invalid: low > open
            close=Decimal("1.0845"),
            volume=1000,
            complete=True,
        )
        assert candle.validate_ohlc() is False

    def test_low_above_close_fails_validation(self):
        """Low must be <= close."""
        candle = Candle(
            time=datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc),
            instrument="EURUSD",
            timeframe="M1",
            open=Decimal("1.0850"),
            high=Decimal("1.0860"),
            low=Decimal("1.0855"),  # Invalid: low > close
            close=Decimal("1.0840"),
            volume=1000,
            complete=True,
        )
        assert candle.validate_ohlc() is False


class TestGapDetection:
    """Test gap detection logic."""

    def test_no_gaps_in_continuous_data(self):
        """Continuous data with no gaps should return empty list."""
        candles = [
            Candle(
                time=datetime(2024, 1, 15, 10, i, 0, tzinfo=timezone.utc),
                instrument="EURUSD",
                timeframe="M1",
                open=Decimal("1.0850"),
                high=Decimal("1.0860"),
                low=Decimal("1.0840"),
                close=Decimal("1.0855"),
                volume=1000,
                complete=True,
            )
            for i in range(5)
        ]
        gaps = detect_gaps(candles, "M1")
        assert len(gaps) == 0

    def test_gap_detected_when_exceeds_2x_timeframe(self):
        """Gap > 2x timeframe duration should be detected."""
        candles = [
            Candle(
                time=datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc),
                instrument="EURUSD",
                timeframe="M1",
                open=Decimal("1.0850"),
                high=Decimal("1.0860"),
                low=Decimal("1.0840"),
                close=Decimal("1.0855"),
                volume=1000,
                complete=True,
            ),
            Candle(
                time=datetime(2024, 1, 15, 10, 5, 0, tzinfo=timezone.utc),  # 5 min gap
                instrument="EURUSD",
                timeframe="M1",
                open=Decimal("1.0850"),
                high=Decimal("1.0860"),
                low=Decimal("1.0840"),
                close=Decimal("1.0855"),
                volume=1000,
                complete=True,
            ),
        ]
        gaps = detect_gaps(candles, "M1")
        assert len(gaps) == 1
        assert gaps[0][2] > 0  # gap_hours > 0

    def test_empty_candle_list_returns_no_gaps(self):
        """Empty candle list should return no gaps."""
        gaps = detect_gaps([], "M1")
        assert len(gaps) == 0

    def test_single_candle_returns_no_gaps(self):
        """Single candle should return no gaps."""
        candles = [
            Candle(
                time=datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc),
                instrument="EURUSD",
                timeframe="M1",
                open=Decimal("1.0850"),
                high=Decimal("1.0860"),
                low=Decimal("1.0840"),
                close=Decimal("1.0855"),
                volume=1000,
                complete=True,
            )
        ]
        gaps = detect_gaps(candles, "M1")
        assert len(gaps) == 0


class TestConfiguration:
    """Test configuration constants."""

    def test_all_instruments_mapped(self):
        """All 5 required instruments must be mapped."""
        expected_instruments = {"EURUSD", "GBPUSD", "US500", "US30", "XAUUSD"}
        assert set(INSTRUMENT_MAPPING.keys()) == expected_instruments

    def test_all_timeframes_mapped(self):
        """All 7 required timeframes must be mapped."""
        expected_timeframes = {"M1", "M5", "M15", "H1", "H4", "D1", "W1"}
        assert set(TIMEFRAME_MAPPING.keys()) == expected_timeframes

    def test_timeframe_durations_defined(self):
        """All timeframes must have duration definitions."""
        for timeframe in TIMEFRAME_MAPPING.keys():
            assert timeframe in TIMEFRAME_DURATIONS
            assert TIMEFRAME_DURATIONS[timeframe] > 0

    def test_oanda_instrument_mapping_correct(self):
        """OANDA instrument names must follow correct format."""
        assert INSTRUMENT_MAPPING["EURUSD"] == "EUR_USD"
        assert INSTRUMENT_MAPPING["GBPUSD"] == "GBP_USD"
        assert INSTRUMENT_MAPPING["US500"] == "SPX500_USD"
        assert INSTRUMENT_MAPPING["US30"] == "US30_USD"
        assert INSTRUMENT_MAPPING["XAUUSD"] == "XAU_USD"

    def test_oanda_granularity_mapping_correct(self):
        """OANDA granularity must follow correct format."""
        assert TIMEFRAME_MAPPING["M1"] == "M1"
        assert TIMEFRAME_MAPPING["M5"] == "M5"
        assert TIMEFRAME_MAPPING["M15"] == "M15"
        assert TIMEFRAME_MAPPING["H1"] == "H1"
        assert TIMEFRAME_MAPPING["H4"] == "H4"
        assert TIMEFRAME_MAPPING["D1"] == "D"
        assert TIMEFRAME_MAPPING["W1"] == "W"
