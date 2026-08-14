"""Tests for liquidity_engine.detectors.external.LiquidityLevelDetector."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from hypothesis import given, settings, strategies as st

from liquidity_engine.detectors.external import LiquidityLevelDetector
from liquidity_engine.models import Candle, LiquiditySource, LiquidityType, Timeframe

_BASE = datetime(2024, 1, 1, tzinfo=timezone.utc)
NY = ZoneInfo("America/New_York")


def ts(n: int) -> datetime:
    return _BASE + timedelta(hours=n)


def mk(open_, high, low, close, n, tf=Timeframe.M15):
    return Candle(
        timestamp=ts(n),
        open=open_,
        high=high,
        low=low,
        close=close,
        timeframe=tf,
        instrument="EURUSD",
    )


def mk_at(open_, high, low, close, dt, tf=Timeframe.M5):
    return Candle(
        timestamp=dt, open=open_, high=high, low=low, close=close, timeframe=tf, instrument="EURUSD"
    )


class TestPreviousHighsLows:
    def test_pwh_detected_as_bsl(self):
        candles = {
            Timeframe.W1: [
                mk(1.0, 1.20, 0.95, 1.10, 0, tf=Timeframe.W1),
                mk(1.0, 1.15, 1.00, 1.05, 1, tf=Timeframe.W1),
            ]
        }
        levels = LiquidityLevelDetector().detect(candles, ts(2))
        pwh = next(l for l in levels if l.source == LiquiditySource.PWH)
        assert pwh.liquidity_type == LiquidityType.BSL
        assert pwh.price == 1.20

    def test_pwl_detected_as_ssl(self):
        candles = {
            Timeframe.W1: [
                mk(1.0, 1.20, 0.95, 1.10, 0, tf=Timeframe.W1),
                mk(1.0, 1.15, 1.00, 1.05, 1, tf=Timeframe.W1),
            ]
        }
        levels = LiquidityLevelDetector().detect(candles, ts(2))
        pwl = next(l for l in levels if l.source == LiquiditySource.PWL)
        assert pwl.liquidity_type == LiquidityType.SSL
        assert pwl.price == 0.95

    def test_pdh_detected_as_bsl(self):
        candles = {
            Timeframe.D1: [
                mk(1.0, 1.30, 0.90, 1.10, 0, tf=Timeframe.D1),
                mk(1.0, 1.20, 1.00, 1.05, 1, tf=Timeframe.D1),
            ]
        }
        levels = LiquidityLevelDetector().detect(candles, ts(2))
        pdh = next(l for l in levels if l.source == LiquiditySource.PDH)
        assert pdh.liquidity_type == LiquidityType.BSL
        assert pdh.price == 1.30

    def test_pdl_detected_as_ssl(self):
        candles = {
            Timeframe.D1: [
                mk(1.0, 1.30, 0.90, 1.10, 0, tf=Timeframe.D1),
                mk(1.0, 1.20, 1.00, 1.05, 1, tf=Timeframe.D1),
            ]
        }
        levels = LiquidityLevelDetector().detect(candles, ts(2))
        pdl = next(l for l in levels if l.source == LiquiditySource.PDL)
        assert pdl.liquidity_type == LiquidityType.SSL
        assert pdl.price == 0.90

    def test_pmh_detected_as_bsl(self):
        candles = {
            Timeframe.MN1: [
                mk(1.0, 1.50, 0.80, 1.10, 0, tf=Timeframe.MN1),
                mk(1.0, 1.30, 1.00, 1.05, 1, tf=Timeframe.MN1),
            ]
        }
        levels = LiquidityLevelDetector().detect(candles, ts(2))
        pmh = next(l for l in levels if l.source == LiquiditySource.PMH)
        assert pmh.liquidity_type == LiquidityType.BSL
        assert pmh.price == 1.50

    def test_pml_detected_as_ssl(self):
        candles = {
            Timeframe.MN1: [
                mk(1.0, 1.50, 0.80, 1.10, 0, tf=Timeframe.MN1),
                mk(1.0, 1.30, 1.00, 1.05, 1, tf=Timeframe.MN1),
            ]
        }
        levels = LiquidityLevelDetector().detect(candles, ts(2))
        pml = next(l for l in levels if l.source == LiquiditySource.PML)
        assert pml.liquidity_type == LiquidityType.SSL
        assert pml.price == 0.80


class TestEqualHighsLows:
    def _highs_candles(self, peak2):
        return [
            mk(99.0, 99.0, 98.0, 99.0, 0),
            mk(99.0, 99.0, 98.0, 99.0, 1),
            mk(99.0, 100.05, 98.0, 99.0, 2),
            mk(99.0, 99.0, 98.0, 99.0, 3),
            mk(99.0, 99.0, 98.0, 99.0, 4),
            mk(99.0, 99.0, 98.0, 99.0, 5),
            mk(99.0, peak2, 98.0, 99.0, 6),
            mk(99.0, 99.0, 98.0, 99.0, 7),
            mk(99.0, 99.0, 98.0, 99.0, 8),
        ]

    def test_equal_highs_within_tolerance(self):
        candles = self._highs_candles(100.10)  # within 0.1% of 100.05
        levels = LiquidityLevelDetector()._detect_equal_highs_lows(candles)
        eqh = [l for l in levels if l.source == LiquiditySource.EQH]
        assert len(eqh) == 1
        assert eqh[0].liquidity_type == LiquidityType.BSL
        assert eqh[0].band_high == 100.10
        assert eqh[0].band_low == 100.05

    def test_equal_highs_outside_tolerance_not_classified(self):
        candles = self._highs_candles(105.0)  # far outside 0.1% of 100.05
        levels = LiquidityLevelDetector()._detect_equal_highs_lows(candles)
        eqh = [l for l in levels if l.source == LiquiditySource.EQH]
        assert eqh == []

    def test_equal_lows_within_tolerance(self):
        candles = [
            mk(1.0, 1.10, 1.00, 1.0, 0),
            mk(1.0, 1.10, 1.00, 1.0, 1),
            mk(1.0, 1.10, 0.9005, 1.0, 2),
            mk(1.0, 1.10, 1.00, 1.0, 3),
            mk(1.0, 1.10, 1.00, 1.0, 4),
            mk(1.0, 1.10, 1.00, 1.0, 5),
            mk(1.0, 1.10, 0.9000, 1.0, 6),
            mk(1.0, 1.10, 1.00, 1.0, 7),
            mk(1.0, 1.10, 1.00, 1.0, 8),
        ]
        levels = LiquidityLevelDetector()._detect_equal_highs_lows(candles)
        eql = [l for l in levels if l.source == LiquiditySource.EQL]
        assert len(eql) == 1
        assert eql[0].liquidity_type == LiquidityType.SSL


class TestSessionHighsLows:
    def _session_candles(self, hours_minutes, base_high=1.10, base_low=0.90):
        return [
            mk_at(1.0, base_high + i * 0.001, base_low - i * 0.001, 1.0, datetime(2024, 1, 15, h, m, tzinfo=NY))
            for i, (h, m) in enumerate(hours_minutes)
        ]

    def test_session_high_london(self):
        candles = self._session_candles([(2, 0), (3, 0), (4, 0)])
        levels = LiquidityLevelDetector()._detect_session_highs_lows(candles, candles[-1].timestamp)
        high = next(l for l in levels if l.source == LiquiditySource.SESSION_HIGH)
        assert high.liquidity_type == LiquidityType.BSL
        assert high.price == max(c.high for c in candles)

    def test_session_low_london(self):
        candles = self._session_candles([(2, 0), (3, 0), (4, 0)])
        levels = LiquidityLevelDetector()._detect_session_highs_lows(candles, candles[-1].timestamp)
        low = next(l for l in levels if l.source == LiquiditySource.SESSION_LOW)
        assert low.liquidity_type == LiquidityType.SSL
        assert low.price == min(c.low for c in candles)

    def test_session_high_ny_am(self):
        candles = self._session_candles([(7, 0), (8, 0), (9, 0)])
        levels = LiquidityLevelDetector()._detect_session_highs_lows(candles, candles[-1].timestamp)
        high = next(l for l in levels if l.source == LiquiditySource.SESSION_HIGH)
        assert high.price == max(c.high for c in candles)

    def test_session_low_ny_pm(self):
        candles = self._session_candles([(13, 30), (14, 30), (15, 30)])
        levels = LiquidityLevelDetector()._detect_session_highs_lows(candles, candles[-1].timestamp)
        low = next(l for l in levels if l.source == LiquiditySource.SESSION_LOW)
        assert low.liquidity_type == LiquidityType.SSL
        assert low.price == min(c.low for c in candles)


class TestLevelIntegrity:
    def _all_levels(self):
        candles = {
            Timeframe.W1: [
                mk(1.0, 1.20, 0.95, 1.10, 0, tf=Timeframe.W1),
                mk(1.0, 1.15, 1.00, 1.05, 1, tf=Timeframe.W1),
            ],
            Timeframe.D1: [
                mk(1.0, 1.30, 0.90, 1.10, 0, tf=Timeframe.D1),
                mk(1.0, 1.20, 1.00, 1.05, 1, tf=Timeframe.D1),
            ],
            Timeframe.M5: TestSessionHighsLows()._session_candles([(2, 0), (3, 0), (4, 0)]),
        }
        return LiquidityLevelDetector().detect(candles, ts(2))

    def test_strength_score_range(self):
        levels = self._all_levels()
        assert levels
        for level in levels:
            assert 0.0 <= level.strength_score <= 1.0

    def test_level_id_is_uuid(self):
        levels = self._all_levels()
        for level in levels:
            uuid.UUID(level.level_id)  # raises ValueError if malformed

    def test_formed_at_is_aware(self):
        levels = self._all_levels()
        for level in levels:
            assert level.formed_at.tzinfo is not None

    def test_touch_count_nonnegative(self):
        levels = self._all_levels()
        for level in levels:
            assert level.touch_count >= 0


@st.composite
def _valid_candle_seq(draw):
    n = draw(st.integers(min_value=5, max_value=15))
    base_price = draw(st.floats(min_value=10.0, max_value=1000.0, allow_nan=False, allow_infinity=False))
    candles = []
    price = base_price
    for i in range(n):
        delta = draw(st.floats(min_value=-5.0, max_value=5.0, allow_nan=False, allow_infinity=False))
        open_ = max(price + delta, 0.01)
        close = max(open_ + draw(st.floats(min_value=-2.0, max_value=2.0, allow_nan=False, allow_infinity=False)), 0.01)
        high = max(open_, close) + abs(draw(st.floats(min_value=0.0, max_value=2.0, allow_nan=False, allow_infinity=False)))
        low = max(min(open_, close) - abs(draw(st.floats(min_value=0.0, max_value=2.0, allow_nan=False, allow_infinity=False))), 0.001)
        candles.append(mk(open_, high, low, close, i))
        price = close
    return candles


class TestPropertyBasedTests:
    @settings(max_examples=100)
    @given(candles=_valid_candle_seq())
    def test_property_equal_highs_tolerance_invariant(self, candles):
        """Property 20: every EQH/EQL level's constituent points satisfy the tolerance."""
        levels = LiquidityLevelDetector()._detect_equal_highs_lows(candles)
        for level in levels:
            if level.source in (LiquiditySource.EQH, LiquiditySource.EQL):
                assert level.band_high is not None and level.band_low is not None
                if level.band_high > 0:
                    assert abs(level.band_high - level.band_low) / level.band_high <= 0.001

    @settings(max_examples=100)
    @given(candles=_valid_candle_seq())
    def test_property_strength_scores_in_range(self, candles):
        """Property 19/21: every LiquidityLevel has strength_score in [0.0, 1.0]."""
        candles_by_tf = {Timeframe.D1: candles, Timeframe.M15: candles}
        levels = LiquidityLevelDetector().detect(candles_by_tf, candles[-1].timestamp)
        for level in levels:
            assert 0.0 <= level.strength_score <= 1.0
