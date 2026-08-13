"""Tests for liquidity_engine.ipda.cisd.CISDDetector."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from liquidity_engine.ipda.cisd import CISDDetector
from liquidity_engine.models import BiasDirection, Candle, Timeframe

_BASE = datetime(2024, 1, 1, tzinfo=timezone.utc)


def ts(n: int) -> datetime:
    return _BASE + timedelta(hours=n)


def mk(open_, high, low, close, n, tf=Timeframe.M5):
    return Candle(
        timestamp=ts(n), open=open_, high=high, low=low, close=close, timeframe=tf, instrument="EURUSD"
    )


class TestCISDDetection:
    def _bearish_cisd_candles(self):
        return [
            mk(1.00, 1.02, 0.99, 1.01, 0),
            mk(1.01, 1.04, 1.00, 1.03, 1),
            mk(1.03, 1.06, 1.02, 1.05, 2),
            mk(1.05, 1.05, 0.90, 0.95, 3),  # close 0.95 < first open 1.00
        ]

    def _bullish_cisd_candles(self):
        return [
            mk(1.05, 1.06, 1.00, 1.01, 0),
            mk(1.01, 1.02, 0.97, 0.98, 1),
            mk(0.98, 0.99, 0.94, 0.95, 2),
            mk(0.95, 1.10, 0.95, 1.08, 3),  # close 1.08 > first open 1.05
        ]

    def test_bearish_cisd_detected(self):
        result = CISDDetector().detect(self._bearish_cisd_candles())
        assert result is not None
        assert result.direction == BiasDirection.BEARISH
        assert result.confirmed is True

    def test_bullish_cisd_detected(self):
        result = CISDDetector().detect(self._bullish_cisd_candles())
        assert result is not None
        assert result.direction == BiasDirection.BULLISH
        assert result.confirmed is True

    def test_cisd_not_confirmed_without_swing_prerequisite(self):
        candles = [
            mk(1.00, 1.01, 0.99, 1.005, 0),
            mk(1.005, 1.02, 1.00, 1.015, 1),
            mk(1.015, 1.03, 1.01, 1.025, 2),
            mk(1.03, 1.04, 0.90, 0.95, 3),  # monotonic run, no interior swing point
        ]
        result = CISDDetector().detect(candles)
        assert result is not None
        assert result.has_swing_prerequisite is False
        assert result.confirmed is False

    def test_cisd_level_equals_first_candle_open(self):
        result = CISDDetector().detect(self._bearish_cisd_candles())
        assert result.level == 1.00

    def test_cisd_sequence_start_time_populated(self):
        candles = self._bearish_cisd_candles()
        result = CISDDetector().detect(candles)
        assert result.sequence_start_time == candles[0].timestamp

    def test_cisd_violation_candle_time_populated(self):
        candles = self._bearish_cisd_candles()
        result = CISDDetector().detect(candles)
        assert result.violation_candle_time == candles[-1].timestamp

    def test_cisd_direction_bearish_for_bearish_cisd(self):
        result = CISDDetector().detect(self._bearish_cisd_candles())
        assert result.direction == BiasDirection.BEARISH

    def test_cisd_direction_bullish_for_bullish_cisd(self):
        result = CISDDetector().detect(self._bullish_cisd_candles())
        assert result.direction == BiasDirection.BULLISH

    def test_swing_prerequisite_3_candle_check(self):
        detector = CISDDetector()
        assert detector._has_swing_point_prerequisite(self._bearish_cisd_candles()) is True
        too_short = self._bearish_cisd_candles()[:2]
        assert detector._has_swing_point_prerequisite(too_short) is False
        monotonic = [
            mk(1.00, 1.01, 0.99, 1.005, 0),
            mk(1.005, 1.02, 1.00, 1.015, 1),
            mk(1.015, 1.03, 1.01, 1.025, 2),
        ]
        assert detector._has_swing_point_prerequisite(monotonic) is False

    def test_no_cisd_on_single_candle(self):
        result = CISDDetector().detect([mk(1.00, 1.01, 0.99, 1.00, 0)])
        assert result is None
