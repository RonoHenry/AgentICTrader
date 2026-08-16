"""
Candle Range Theory (CRT) phase classification and CISD cascade validation.

CRT models a single delivery window as four phases — C1 Accumulation (tight,
ATR-relative range), C2 Manipulation (a close back inside that range,
confirmed by a CISD), C3 Distribution (a strong break away from the range),
C4 Continuation (follow-through in the break direction) — checked most
specific to least specific so the richest description wins.

Note: `classify_crt_phase(candles, tf)` only receives a single timeframe's
candles (per the design), so "lower-timeframe CISD confirmation" (Requirement
5.2) and "direction consistent with HTF bias" (Requirement 5.3) can't be
checked against genuinely separate data. Both are approximated using the
given candles themselves — see `_check_c2`/`_check_c3` below.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from pd_array_engine.ipda.cisd import CISDDetector
from pd_array_engine.models import (
    Candle,
    CISDCascadeStatus,
    CISDResult,
    CRTPhase,
    CRTPhaseResult,
    Timeframe,
)
from pd_array_engine.utils.candle_utils import calculate_atr

_ATR_PERIOD = 14
# Number of candles forming the C1 accumulation baseline window. Fixed-size
# and always taken immediately before the candle(s) under test — using
# "everything before the last candle" instead would pull the manipulation/
# distribution candles themselves into the baseline and mask the tight range
# they departed from.
_C1_LOOKBACK = 8
# C1 compares an *aggregate* multi-candle range to a *single-candle* ATR, so
# the tight-range threshold is expressed as a multiple (not a fraction) of
# ATR — a genuinely tight consolidation still spans a couple of candles' worth
# of noise, it doesn't shrink below one candle's average true range.
_C1_TIGHT_RATIO = 2.0
_C3_EXPANSION_RATIO = 1.5


class IPDAClassifier:
    """Classifies CRT phase per timeframe and validates the CISD cascade."""

    CISD_CASCADE: Dict[Timeframe, Timeframe] = {
        Timeframe.MN1: Timeframe.D1,
        Timeframe.W1: Timeframe.H4,
        Timeframe.D1: Timeframe.H1,
        Timeframe.H4: Timeframe.M15,
        Timeframe.M30: Timeframe.M3,
        Timeframe.M15: Timeframe.M1,
    }

    def classify_crt_phase(self, candles: List[Candle], tf: Timeframe) -> CRTPhaseResult:
        return self._classify_phase(candles)

    def validate_cisd_cascade(
        self, candles_by_tf: Dict[Timeframe, List[Candle]], trigger_tf: Timeframe
    ) -> CISDCascadeStatus:
        confirmation_tf = self.CISD_CASCADE.get(trigger_tf)
        if confirmation_tf is None:
            return CISDCascadeStatus(cascade_valid=False, cascade_chain=[])

        trigger_candles = candles_by_tf.get(trigger_tf)
        confirmation_candles = candles_by_tf.get(confirmation_tf)
        if not trigger_candles or not confirmation_candles:
            return CISDCascadeStatus(cascade_valid=False, cascade_chain=[])

        detector = CISDDetector()
        trigger_result = detector.detect(trigger_candles)
        confirmation_result = detector.detect(confirmation_candles)

        chain = [r for r in (trigger_result, confirmation_result) if r is not None]
        return CISDCascadeStatus(
            cascade_valid=self._cascade_valid(trigger_result, confirmation_result),
            cascade_chain=chain,
        )

    def _cascade_valid(
        self, trigger: Optional[CISDResult], confirmation: Optional[CISDResult]
    ) -> bool:
        return bool(trigger and trigger.confirmed and confirmation and confirmation.confirmed)

    def _classify_phase(self, candles: List[Candle]) -> CRTPhaseResult:
        if len(candles) < 4:
            return CRTPhaseResult(phase=CRTPhase.UNKNOWN, confidence=0.0)

        for check in (self._check_c4, self._check_c3, self._check_c2, self._check_c1):
            result = check(candles)
            if result is not None:
                return result
        return CRTPhaseResult(phase=CRTPhase.UNKNOWN, confidence=0.0)

    def _range_stats(self, window: List[Candle]) -> tuple[float, float, float]:
        high = max(c.high for c in window)
        low = min(c.low for c in window)
        atr = calculate_atr(window, period=min(_ATR_PERIOD, max(len(window) - 1, 1)))
        return high, low, atr

    def _baseline_window(self, candles: List[Candle], tail_excluded: int) -> List[Candle]:
        """The `_C1_LOOKBACK` candles immediately preceding the last `tail_excluded` candles."""
        end = len(candles) - tail_excluded
        start = max(0, end - _C1_LOOKBACK)
        return candles[start:end]

    def _check_c1(self, candles: List[Candle]) -> Optional[CRTPhaseResult]:
        window = self._baseline_window(candles, tail_excluded=0)
        if len(window) < 3:
            return None
        high, low, atr = self._range_stats(window)
        rng = high - low
        if atr <= 0 or rng > _C1_TIGHT_RATIO * atr:
            return None
        confidence = max(0.0, min(1.0, 1.0 - (rng / (_C1_TIGHT_RATIO * atr))))
        return CRTPhaseResult(
            phase=CRTPhase.C1_ACCUMULATION, confidence=confidence, c1_range_high=high, c1_range_low=low
        )

    def _check_c2(self, candles: List[Candle]) -> Optional[CRTPhaseResult]:
        if len(candles) < 4:
            return None
        # "Lower-timeframe CISD" approximated by a self-contained CISD check
        # over the same candles (see module docstring). Its `sequence_start_time`
        # also tells us where the manipulation run began, so the C1 baseline can
        # be measured *before* that run — not a naive trailing window, which the
        # run itself (being a departure from the tight range) would contaminate.
        cisd_result = CISDDetector().detect(candles)
        if not (cisd_result and cisd_result.confirmed):
            return None
        run_start = next(
            (i for i, c in enumerate(candles) if c.timestamp == cisd_result.sequence_start_time), None
        )
        if run_start is None:
            return None
        baseline = candles[max(0, run_start - _C1_LOOKBACK):run_start]
        if len(baseline) < 3:
            return None
        high, low, atr = self._range_stats(baseline)
        rng = high - low
        if atr <= 0 or rng > _C1_TIGHT_RATIO * atr:
            return None
        last = candles[-1]
        if not (low <= last.close <= high):
            return None
        return CRTPhaseResult(
            phase=CRTPhase.C2_MANIPULATION,
            confidence=0.7,
            c1_range_high=high,
            c1_range_low=low,
            c2_within_c1=True,
            confirmation_tf_cisd=True,
        )

    def _check_c3(self, candles: List[Candle]) -> Optional[CRTPhaseResult]:
        if len(candles) < 4:
            return None
        baseline = self._baseline_window(candles, tail_excluded=1)
        if len(baseline) < 3:
            return None
        high, low, atr = self._range_stats(baseline)
        if atr <= 0:
            return None
        last = candles[-1]
        if last.total_range < _C3_EXPANSION_RATIO * atr:
            return None
        if not (last.close > high or last.close < low):
            return None
        confidence = max(0.0, min(1.0, 0.6 + last.total_range / (_C3_EXPANSION_RATIO * atr) - 1.0))
        return CRTPhaseResult(
            phase=CRTPhase.C3_DISTRIBUTION, confidence=confidence, c1_range_high=high, c1_range_low=low
        )

    def _check_c4(self, candles: List[Candle]) -> Optional[CRTPhaseResult]:
        if len(candles) < 5:
            return None
        baseline = self._baseline_window(candles, tail_excluded=2)
        if len(baseline) < 3:
            return None
        high, low, atr = self._range_stats(baseline)
        if atr <= 0:
            return None
        c3_candle, c4_candle = candles[-2], candles[-1]
        if c3_candle.total_range < _C3_EXPANSION_RATIO * atr:
            return None
        continues_up = c3_candle.close > high and c4_candle.close > c3_candle.close
        continues_down = c3_candle.close < low and c4_candle.close < c3_candle.close
        if not (continues_up or continues_down):
            return None
        return CRTPhaseResult(
            phase=CRTPhase.C4_CONTINUATION, confidence=0.75, c1_range_high=high, c1_range_low=low
        )
