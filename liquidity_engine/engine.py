"""
LiquidityMappingEngine — top-level orchestrator.

Wires every detector/analytics component into a single deterministic
`analyze()` call, per Requirement 1.5:

    HTFBiasClassifier -> LiquidityLevelDetector -> SwingStructureClassifier ->
    PDArrayDetector -> FractalModelTracker -> IPDAClassifier -> OTECalculator ->
    UnicornDetector -> SetupSequenceDetector -> SetupGrader

SetupSequenceDetector (Requirement 18, update 2026-10) runs before grading:
the grader reads the setup sequence it records.

A few cross-component values (draw_on_liquidity, sweep_detected, the OTE
displacement leg, the Fractal Model's key_level) are engine-level derivations,
not one of the named components above — they're computed inline, between
component calls, wherever their inputs become available, without disturbing
the required call order of the components themselves.
"""
from __future__ import annotations

from bisect import bisect_right
from datetime import datetime
from typing import Dict, List, Optional

from liquidity_engine.detectors.bias import HTFBiasClassifier
from liquidity_engine.detectors.external import LiquidityLevelDetector
from liquidity_engine.detectors.internal import PDArrayDetector
from liquidity_engine.detectors.structure import SwingStructureClassifier
from liquidity_engine.fractal.candle_model import FractalModelTracker
from liquidity_engine.grader.sequence import SetupSequenceDetector
from liquidity_engine.grader.setup_grader import SetupGrader
from liquidity_engine.ipda.classifier import IPDAClassifier
from liquidity_engine.models import (
    BiasDirection,
    Candle,
    CISDCascadeStatus,
    HTFBias,
    LiquidityLevel,
    LiquidityMap,
    LiquidityType,
    SetupSequence,
    Timeframe,
)
from liquidity_engine.ote.calculator import OTECalculator
from liquidity_engine.projections.standard_deviation import StandardDeviationCalculator
from liquidity_engine.unicorn.detector import UnicornDetector

# Finest-to-coarsest, used to pick a single "live price" source and to
# supply the Fractal Model / OTE displacement leg with intraday resolution.
_TIMEFRAME_PRIORITY: List[Timeframe] = [
    Timeframe.M1,
    Timeframe.M3,
    Timeframe.M5,
    Timeframe.M15,
    Timeframe.M30,
    Timeframe.H1,
    Timeframe.H3,
    Timeframe.H4,
    Timeframe.H6,
    Timeframe.H8,
    Timeframe.H12,
    Timeframe.D1,
    Timeframe.W1,
    Timeframe.MN1,
]

# Senior-to-junior, used to pick which timeframe pair triggers CISD cascade
# validation — the highest-timeframe pair with both legs present wins.
_CASCADE_TRIGGER_PRIORITY: List[Timeframe] = [
    Timeframe.MN1,
    Timeframe.W1,
    Timeframe.D1,
    Timeframe.H4,
    Timeframe.M30,
    Timeframe.M15,
]

_REQUIRED_TIMEFRAMES: List[Timeframe] = [Timeframe.D1, Timeframe.W1]


class LiquidityMappingEngine:
    """Main orchestrator class for liquidity analysis. Stateless; safe to reuse across calls."""

    def analyze(
        self,
        candles_by_tf: Dict[Timeframe, List[Candle]],
        instrument: str,
        timestamp: datetime,
    ) -> LiquidityMap:
        for required in _REQUIRED_TIMEFRAMES:
            if not candles_by_tf.get(required):
                raise ValueError(f"analyze() requires non-empty {required.value} candles")

        finest_candles = self._finest_candles(candles_by_tf)
        current_price = finest_candles[-1].close

        htf_bias = HTFBiasClassifier().classify(candles_by_tf, current_price)
        liquidity_levels = self._mark_swept_levels(
            candles_by_tf, LiquidityLevelDetector().detect(candles_by_tf, timestamp)
        )
        draw_on_liquidity = self._find_draw_on_liquidity(htf_bias, liquidity_levels)

        swing_structure = SwingStructureClassifier().classify(candles_by_tf)
        pd_arrays = PDArrayDetector().detect(candles_by_tf, swing_structure)

        key_level = self._fractal_key_level(draw_on_liquidity, htf_bias)
        fractal_model = FractalModelTracker().track(finest_candles, key_level)

        ipda = IPDAClassifier()
        crt_phases = {
            tf.value: ipda.classify_crt_phase(candles, tf) for tf, candles in candles_by_tf.items()
        }
        cisd_cascade = self._validate_cisd_cascade(ipda, candles_by_tf)

        ote_zone = self._calculate_ote_zone(finest_candles, htf_bias, current_price)
        unicorn = UnicornDetector().detect(pd_arrays)
        setup_sequence = SetupSequenceDetector().detect(candles_by_tf, pd_arrays)

        liquidity_map = LiquidityMap(
            analyzed_at=timestamp,
            instrument=instrument,
            htf_bias={tf.value: bias for tf, bias in htf_bias.items()},
            liquidity_levels=liquidity_levels,
            pd_arrays=pd_arrays,
            crt_phases=crt_phases,
            cisd_cascade=cisd_cascade,
            draw_on_liquidity=draw_on_liquidity,
            sweep_detected=setup_sequence is not None,          # Requirement 13.4 (2026-10)
            ote_zone=ote_zone,
            unicorn=unicorn,
            setup_grade=None,
            swing_structure={tf.value: result for tf, result in swing_structure.items()},
            fractal_model=fractal_model,
            sd_projection=None,
            setup_sequence=setup_sequence,
        )
        liquidity_map.setup_grade = SetupGrader().grade(liquidity_map, timestamp)
        liquidity_map.sd_projection = self._calculate_sd_projection(setup_sequence)
        return liquidity_map

    def _finest_candles(self, candles_by_tf: Dict[Timeframe, List[Candle]]) -> List[Candle]:
        for tf in _TIMEFRAME_PRIORITY:
            candles = candles_by_tf.get(tf)
            if candles:
                return candles
        raise ValueError("analyze() requires at least one non-empty timeframe")

    def _mark_swept_levels(
        self, candles_by_tf: Dict[Timeframe, List[Candle]], levels: List[LiquidityLevel]
    ) -> List[LiquidityLevel]:
        """Requirement 13.5: a level is swept once a bar of any timeframe,
        opening after the level formed, trades beyond it (strictly: a bar that
        only reaches it hasn't taken it). ``swept_at`` is the earliest such bar.
        Runs before _find_draw_on_liquidity, so the draw is an untouched pool."""
        opens = {tf: [c.timestamp for c in candles] for tf, candles in candles_by_tf.items()}
        marked: List[LiquidityLevel] = []
        for level in levels:
            is_bsl = level.liquidity_type == LiquidityType.BSL
            swept_at: Optional[datetime] = None
            for tf, candles in candles_by_tf.items():
                for candle in candles[bisect_right(opens[tf], level.formed_at):]:   # oldest first
                    if swept_at is not None and candle.timestamp >= swept_at:
                        break
                    if (candle.high > level.price) if is_bsl else (candle.low < level.price):
                        swept_at = candle.timestamp
                        break
            marked.append(level if swept_at is None else level.model_copy(update={"swept": True, "swept_at": swept_at}))
        return marked

    def _find_draw_on_liquidity(
        self, htf_bias: Dict[Timeframe, HTFBias], levels: List[LiquidityLevel]
    ) -> Optional[LiquidityLevel]:
        d1_bias = htf_bias.get(Timeframe.D1)
        if d1_bias is None or d1_bias.direction == BiasDirection.NEUTRAL:
            return None
        target_type = (
            LiquidityType.BSL if d1_bias.direction == BiasDirection.BULLISH else LiquidityType.SSL
        )
        candidates = [lvl for lvl in levels if lvl.liquidity_type == target_type and not lvl.swept]
        if not candidates:
            return None
        return max(candidates, key=lambda lvl: lvl.strength_score)

    def _fractal_key_level(
        self, draw_on_liquidity: Optional[LiquidityLevel], htf_bias: Dict[Timeframe, HTFBias]
    ) -> Optional[float]:
        if draw_on_liquidity is not None:
            return draw_on_liquidity.price
        d1_bias = htf_bias.get(Timeframe.D1)
        return d1_bias.reference_open if d1_bias is not None else None

    def _validate_cisd_cascade(
        self, ipda: IPDAClassifier, candles_by_tf: Dict[Timeframe, List[Candle]]
    ) -> CISDCascadeStatus:
        for trigger_tf in _CASCADE_TRIGGER_PRIORITY:
            confirmation_candidates = ipda.CISD_CASCADE.get(trigger_tf, [])
            if trigger_tf in candles_by_tf and any(tf in candles_by_tf for tf in confirmation_candidates):
                return ipda.validate_cisd_cascade(candles_by_tf, trigger_tf)
        return CISDCascadeStatus(cascade_valid=False, cascade_chain=[])

    def _calculate_ote_zone(
        self, finest_candles: List[Candle], htf_bias: Dict[Timeframe, HTFBias], current_price: float
    ):
        d1_bias = htf_bias.get(Timeframe.D1)
        direction = d1_bias.direction if d1_bias is not None else BiasDirection.NEUTRAL
        if direction == BiasDirection.NEUTRAL:
            return None

        calculator = OTECalculator()
        leg = calculator.find_displacement_leg(finest_candles, direction)
        if leg is None:
            return None
        swing_high, swing_low = leg
        zone = calculator.calculate(swing_high, swing_low, direction)
        zone.price_in_ote = calculator.price_in_ote(current_price, zone)
        return zone

    def _calculate_sd_projection(self, sequence: Optional[SetupSequence]):
        # Requirement 18.15: anchored on the setup leg, from the protected
        # swing's wick to the leg's far extreme, in the sequence's direction:
        # the same direction the stop was placed for. (It was the entry
        # array's own range, which fixed R:R at 5.0 for every midpoint entry.)
        if sequence is None:
            return None
        wick = sequence.protected_swing.wick
        if sequence.direction == BiasDirection.BULLISH:
            return StandardDeviationCalculator().project(sequence.leg_extreme, wick, BiasDirection.BULLISH)
        return StandardDeviationCalculator().project(wick, sequence.leg_extreme, BiasDirection.BEARISH)


__all__ = ["LiquidityMappingEngine"]
