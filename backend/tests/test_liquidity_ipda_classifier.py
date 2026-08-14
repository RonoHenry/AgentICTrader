"""Tests for liquidity_engine.ipda.classifier.IPDAClassifier."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from hypothesis import given, settings, strategies as st

from liquidity_engine.ipda.classifier import IPDAClassifier
from liquidity_engine.ipda.cisd import CISDDetector
from liquidity_engine.models import BiasDirection, Candle, CRTPhase, Timeframe

_BASE = datetime(2024, 1, 1, tzinfo=timezone.utc)


def ts(n: int) -> datetime:
    return _BASE + timedelta(hours=n)


def mk(open_, high, low, close, n, tf=Timeframe.M5):
    return Candle(
        timestamp=ts(n), open=open_, high=high, low=low, close=close, timeframe=tf, instrument="EURUSD"
    )


_TIGHT_BASELINE = [
    mk(100.000, 100.005, 99.998, 100.002, 0),
    mk(100.002, 100.006, 99.999, 100.003, 1),
    mk(100.003, 100.007, 100.000, 100.004, 2),
    mk(100.004, 100.008, 100.001, 100.003, 3),
    mk(100.003, 100.006, 99.999, 100.001, 4),
    mk(100.001, 100.005, 99.998, 100.000, 5),
    mk(100.000, 100.004, 99.997, 99.999, 6),
    # bullish close on the last baseline candle cleanly breaks any bearish
    # run before it, so a following down-close sequence starts exactly here
    mk(99.998, 100.006, 99.996, 100.005, 7),
]


class TestCRTPhaseClassification:
    def test_c1_accumulation_tight_range(self):
        candles = _TIGHT_BASELINE + [mk(99.997, 100.006, 99.995, 100.002, 8)]
        result = IPDAClassifier().classify_crt_phase(candles, Timeframe.M5)
        assert result.phase == CRTPhase.C1_ACCUMULATION

    def _c2_candles(self):
        # baseline (C1) + a down-close run whose violator closes back within the C1 range,
        # satisfying the CISD confirmation check.
        down_run = [
            mk(100.00, 100.01, 99.85, 99.90, 8),
            mk(99.90, 99.92, 99.75, 99.80, 9),
            mk(99.80, 99.82, 99.60, 99.65, 10),
        ]
        violator = mk(99.65, 100.005, 99.65, 100.002, 11)  # closes back above first open (100.00)
        return _TIGHT_BASELINE + down_run + [violator]

    def test_c2_manipulation_within_c1_range(self):
        result = IPDAClassifier().classify_crt_phase(self._c2_candles(), Timeframe.M5)
        assert result.phase == CRTPhase.C2_MANIPULATION

    def test_c2_within_c1_field_true(self):
        result = IPDAClassifier().classify_crt_phase(self._c2_candles(), Timeframe.M5)
        assert result.c2_within_c1 is True

    def test_c2_confirmation_tf_cisd_true(self):
        result = IPDAClassifier().classify_crt_phase(self._c2_candles(), Timeframe.M5)
        assert result.confirmation_tf_cisd is True

    def test_c3_distribution_strong_directional_candle(self):
        candles = _TIGHT_BASELINE + [mk(99.998, 100.30, 99.990, 100.28, 8)]
        result = IPDAClassifier().classify_crt_phase(candles, Timeframe.M5)
        assert result.phase == CRTPhase.C3_DISTRIBUTION

    def test_c4_continuation_follow_through(self):
        candles = _TIGHT_BASELINE + [
            mk(99.998, 100.30, 99.990, 100.28, 8),
            mk(100.28, 100.45, 100.25, 100.40, 9),
        ]
        result = IPDAClassifier().classify_crt_phase(candles, Timeframe.M5)
        assert result.phase == CRTPhase.C4_CONTINUATION

    def test_unknown_when_no_conditions_met(self):
        candles = [
            mk(100.00, 100.10, 99.95, 100.05, 0),
            mk(100.05, 100.15, 100.00, 100.10, 1),
            mk(100.10, 100.20, 100.05, 100.15, 2),
            mk(100.15, 100.25, 100.10, 100.20, 3),
            mk(100.20, 100.30, 100.15, 100.25, 4),
            mk(100.25, 100.35, 100.20, 100.30, 5),
        ]
        result = IPDAClassifier().classify_crt_phase(candles, Timeframe.M5)
        assert result.phase == CRTPhase.UNKNOWN

    def test_confidence_in_range(self):
        for candles in (
            _TIGHT_BASELINE + [mk(99.997, 100.006, 99.995, 100.002, 8)],
            _TIGHT_BASELINE + [mk(99.998, 100.30, 99.990, 100.28, 8)],
            [mk(100.00, 100.10, 99.95, 100.05, n) for n in range(4)],
        ):
            result = IPDAClassifier().classify_crt_phase(candles, Timeframe.M5)
            assert 0.0 <= result.confidence <= 1.0

    def test_c1_range_populated(self):
        candles = _TIGHT_BASELINE + [mk(99.997, 100.006, 99.995, 100.002, 8)]
        result = IPDAClassifier().classify_crt_phase(candles, Timeframe.M5)
        assert result.c1_range_high is not None
        assert result.c1_range_low is not None
        assert result.c1_range_high > result.c1_range_low


class TestCISDCascadeMapping:
    def test_cisd_cascade_mn1_maps_to_d1(self):
        assert IPDAClassifier.CISD_CASCADE[Timeframe.MN1] == Timeframe.D1

    def test_cisd_cascade_w1_maps_to_h4(self):
        assert IPDAClassifier.CISD_CASCADE[Timeframe.W1] == Timeframe.H4

    def test_cisd_cascade_d1_maps_to_h1(self):
        assert IPDAClassifier.CISD_CASCADE[Timeframe.D1] == Timeframe.H1

    def test_cisd_cascade_h4_maps_to_m15(self):
        assert IPDAClassifier.CISD_CASCADE[Timeframe.H4] == Timeframe.M15

    def test_cisd_cascade_m30_maps_to_m3(self):
        assert IPDAClassifier.CISD_CASCADE[Timeframe.M30] == Timeframe.M3

    def test_cisd_cascade_m15_maps_to_m1(self):
        assert IPDAClassifier.CISD_CASCADE[Timeframe.M15] == Timeframe.M1


class TestCISDCascadeValidation:
    def _bearish_cisd_candles(self, tf):
        return [
            mk(1.00, 1.02, 0.99, 1.01, 0, tf=tf),
            mk(1.01, 1.04, 1.00, 1.03, 1, tf=tf),
            mk(1.03, 1.06, 1.02, 1.05, 2, tf=tf),
            mk(1.05, 1.05, 0.90, 0.95, 3, tf=tf),
        ]

    def test_cascade_valid_when_both_cisds_confirmed(self):
        candles_by_tf = {
            Timeframe.D1: self._bearish_cisd_candles(Timeframe.D1),
            Timeframe.H1: self._bearish_cisd_candles(Timeframe.H1),
        }
        status = IPDAClassifier().validate_cisd_cascade(candles_by_tf, Timeframe.D1)
        assert status.cascade_valid is True
        assert len(status.cascade_chain) == 2

    def test_cascade_invalid_when_trigger_unconfirmed(self):
        unconfirmed = [
            mk(1.00, 1.01, 0.99, 1.005, 0, tf=Timeframe.D1),
            mk(1.005, 1.02, 1.00, 1.015, 1, tf=Timeframe.D1),
            mk(1.015, 1.03, 1.01, 1.025, 2, tf=Timeframe.D1),
            mk(1.03, 1.04, 0.90, 0.95, 3, tf=Timeframe.D1),  # monotonic run -> no swing prerequisite
        ]
        candles_by_tf = {
            Timeframe.D1: unconfirmed,
            Timeframe.H1: self._bearish_cisd_candles(Timeframe.H1),
        }
        status = IPDAClassifier().validate_cisd_cascade(candles_by_tf, Timeframe.D1)
        assert status.cascade_valid is False

    def test_cascade_invalid_when_confirmation_unconfirmed(self):
        unconfirmed = [
            mk(1.00, 1.01, 0.99, 1.005, 0, tf=Timeframe.H1),
            mk(1.005, 1.02, 1.00, 1.015, 1, tf=Timeframe.H1),
            mk(1.015, 1.03, 1.01, 1.025, 2, tf=Timeframe.H1),
            mk(1.03, 1.04, 0.90, 0.95, 3, tf=Timeframe.H1),
        ]
        candles_by_tf = {
            Timeframe.D1: self._bearish_cisd_candles(Timeframe.D1),
            Timeframe.H1: unconfirmed,
        }
        status = IPDAClassifier().validate_cisd_cascade(candles_by_tf, Timeframe.D1)
        assert status.cascade_valid is False

    def test_cascade_invalid_when_timeframe_absent(self):
        candles_by_tf = {Timeframe.D1: self._bearish_cisd_candles(Timeframe.D1)}
        status = IPDAClassifier().validate_cisd_cascade(candles_by_tf, Timeframe.D1)
        assert status.cascade_valid is False
        assert status.cascade_chain == []

    def test_crt_phases_keyed_by_timeframe_value(self):
        candles_by_tf = {
            Timeframe.M5: _TIGHT_BASELINE + [mk(99.997, 100.006, 99.995, 100.002, 8)],
            Timeframe.H1: _TIGHT_BASELINE + [mk(99.997, 100.006, 99.995, 100.002, 8, tf=Timeframe.H1)],
        }
        classifier = IPDAClassifier()
        crt_phases = {tf.value: classifier.classify_crt_phase(candles, tf) for tf, candles in candles_by_tf.items()}
        assert set(crt_phases.keys()) == {"M5", "H1"}


@st.composite
def _cisd_result_pair(draw):
    trigger_confirmed = draw(st.booleans())
    confirmation_confirmed = draw(st.booleans())
    trigger = CISDDetector().detect(
        [
            mk(1.00, 1.02, 0.99, 1.01, 0),
            mk(1.01, 1.04, 1.00, 1.03, 1),
            mk(1.03, 1.06, 1.02, 1.05, 2),
            mk(1.05, 1.05, 0.90, 0.95, 3),
        ]
    )
    confirmation = trigger.model_copy(update={"confirmed": confirmation_confirmed})
    trigger = trigger.model_copy(update={"confirmed": trigger_confirmed})
    return trigger, confirmation


class TestPropertyBasedTests:
    @settings(max_examples=100)
    @given(pair=_cisd_result_pair())
    def test_property_cisd_cascade_valid_iff_both_confirmed(self, pair):
        """Property 17/19: cascade_valid iff both trigger and confirmation are confirmed."""
        trigger, confirmation = pair
        cascade_valid = IPDAClassifier()._cascade_valid(trigger, confirmation)
        assert cascade_valid == (trigger.confirmed and confirmation.confirmed)
