"""
Internal Price Delivery Array (PD Array) detection.

Detects imbalances and institutional footprints: Fair Value Gaps, Order
Blocks, Breaker Blocks, Inverse FVGs, Balanced Price Ranges, and CISD levels.
Pure and stateless — every detection is a function of the candles (and, for
Breakers, the swing structure) passed in.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from pd_array_engine.models import (
    BiasDirection,
    Candle,
    PDArray,
    PDArrayType,
    StructureEvent,
    SwingStructureResult,
    Timeframe,
)
from pd_array_engine.utils.candle_utils import calculate_atr
from pd_array_engine.utils.id_utils import deterministic_id

# Minimum multiple of ATR a candle's range must reach to count as a
# significant expansion move for Order Block detection.
OB_EXPANSION_ATR_MULTIPLE: float = 1.5

# Minimum run length of same-direction candles before a violation counts as a CISD.
CISD_MIN_SEQUENCE_LENGTH: int = 3

# Baseline significance per array type, used by `_assign_strength_score`.
_ARRAY_TYPE_WEIGHT: Dict[PDArrayType, float] = {
    PDArrayType.FVG: 0.5,
    PDArrayType.OB: 0.7,
    PDArrayType.BREAKER: 0.8,
    PDArrayType.IFVG: 0.6,
    PDArrayType.BPR: 0.75,
    PDArrayType.CISD_LEVEL: 0.65,
}


class PDArrayDetector:
    """Detects all Price Delivery Array types across the provided timeframes."""

    def detect(
        self,
        candles_by_tf: Dict[Timeframe, List[Candle]],
        swing_structure: Dict[Timeframe, SwingStructureResult],
    ) -> List[PDArray]:
        arrays: List[PDArray] = []
        for tf, candles in candles_by_tf.items():
            fvgs = self._detect_fvg(candles, tf)
            for fvg in fvgs:
                self._mark_fvg_filled(fvg, candles)

            obs = self._detect_order_blocks(candles, tf)
            structure_result = swing_structure.get(tf)
            events = structure_result.events if structure_result else []
            breakers = self._detect_breaker_blocks(candles, obs, events)
            ifvgs = self._detect_ifvg(candles, fvgs)
            bprs = self._detect_bpr(fvgs)
            cisd_levels = self._detect_cisd_levels(candles, tf)

            arrays += fvgs + obs + breakers + ifvgs + bprs + cisd_levels
        return arrays

    def _detect_fvg(self, candles: List[Candle], tf: Timeframe) -> List[PDArray]:
        arrays: List[PDArray] = []
        for i in range(2, len(candles)):
            c0, c2 = candles[i - 2], candles[i]
            if c2.low > c0.high:
                arrays.append(
                    self._make_pdarray(
                        PDArrayType.FVG, BiasDirection.BULLISH, tf, c2.high, c0.low, c2.timestamp
                    )
                )
            elif c0.low > c2.high:
                arrays.append(
                    self._make_pdarray(
                        PDArrayType.FVG, BiasDirection.BEARISH, tf, c0.high, c2.low, c2.timestamp
                    )
                )
        return arrays

    def _mark_fvg_filled(self, fvg: PDArray, candles: List[Candle]) -> None:
        for candle in candles:
            if candle.timestamp <= fvg.formed_at:
                continue
            if fvg.direction == BiasDirection.BULLISH and candle.low <= fvg.low:
                fvg.is_filled = True
                fvg.filled_at = candle.timestamp
                return
            if fvg.direction == BiasDirection.BEARISH and candle.high >= fvg.high:
                fvg.is_filled = True
                fvg.filled_at = candle.timestamp
                return

    def _detect_order_blocks(self, candles: List[Candle], tf: Timeframe) -> List[PDArray]:
        arrays: List[PDArray] = []
        for i in range(2, len(candles)):
            candle = candles[i]
            atr = calculate_atr(candles[:i], period=min(14, i))
            if atr <= 0:
                continue
            if candle.total_range < OB_EXPANSION_ATR_MULTIPLE * atr:
                continue

            if candle.is_bearish:
                ob_candle = self._last_opposing_candle(candles, i, want_bullish=True)
                if ob_candle is not None and ob_candle.high > ob_candle.low:
                    arrays.append(
                        self._make_pdarray(
                            PDArrayType.OB,
                            BiasDirection.BEARISH,
                            tf,
                            ob_candle.high,
                            ob_candle.low,
                            ob_candle.timestamp,
                            ob_candle_open=ob_candle.open,
                            ob_candle_close=ob_candle.close,
                        )
                    )
            elif candle.is_bullish:
                ob_candle = self._last_opposing_candle(candles, i, want_bullish=False)
                if ob_candle is not None and ob_candle.high > ob_candle.low:
                    arrays.append(
                        self._make_pdarray(
                            PDArrayType.OB,
                            BiasDirection.BULLISH,
                            tf,
                            ob_candle.high,
                            ob_candle.low,
                            ob_candle.timestamp,
                            ob_candle_open=ob_candle.open,
                            ob_candle_close=ob_candle.close,
                        )
                    )
        return arrays

    def _last_opposing_candle(self, candles: List[Candle], i: int, want_bullish: bool) -> Optional[Candle]:
        j = i - 1
        while j >= 0:
            if want_bullish and candles[j].is_bullish:
                return candles[j]
            if not want_bullish and candles[j].is_bearish:
                return candles[j]
            j -= 1
        return None

    def _detect_breaker_blocks(
        self, candles: List[Candle], ob_list: List[PDArray], structure_events: List[StructureEvent]
    ) -> List[PDArray]:
        breakers: List[PDArray] = []
        for ob in ob_list:
            violation_candle = self._find_violation(ob, candles)
            if violation_candle is None:
                continue
            new_direction = (
                BiasDirection.BULLISH if ob.direction == BiasDirection.BEARISH else BiasDirection.BEARISH
            )
            breaker = self._make_pdarray(
                PDArrayType.BREAKER,
                new_direction,
                ob.timeframe,
                ob.high,
                ob.low,
                violation_candle.timestamp,
                source_ob_id=ob.array_id,
            )
            breaker.structure_confirmed = self._structure_confirmed(
                violation_candle, new_direction, structure_events
            )
            breakers.append(breaker)
        return breakers

    def _find_violation(self, ob: PDArray, candles: List[Candle]) -> Optional[Candle]:
        for candle in candles:
            if candle.timestamp <= ob.formed_at:
                continue
            if ob.direction == BiasDirection.BEARISH and candle.close > ob.high:
                return candle
            if ob.direction == BiasDirection.BULLISH and candle.close < ob.low:
                return candle
        return None

    def _structure_confirmed(
        self, violation_candle: Candle, new_direction: BiasDirection, structure_events: List[StructureEvent]
    ) -> bool:
        return any(
            event.direction == new_direction and event.confirmed_at >= violation_candle.timestamp
            for event in structure_events
        )

    def _detect_ifvg(self, candles: List[Candle], fvg_list: List[PDArray]) -> List[PDArray]:
        ifvgs: List[PDArray] = []
        for fvg in fvg_list:
            if not fvg.is_filled:
                continue
            opposing = (
                BiasDirection.BEARISH if fvg.direction == BiasDirection.BULLISH else BiasDirection.BULLISH
            )
            ifvgs.append(
                self._make_pdarray(
                    PDArrayType.IFVG,
                    opposing,
                    fvg.timeframe,
                    fvg.high,
                    fvg.low,
                    fvg.filled_at or fvg.formed_at,
                )
            )
        return ifvgs

    def _detect_bpr(self, fvg_list: List[PDArray]) -> List[PDArray]:
        bprs: List[PDArray] = []
        bullish = [f for f in fvg_list if f.direction == BiasDirection.BULLISH]
        bearish = [f for f in fvg_list if f.direction == BiasDirection.BEARISH]
        for bull in bullish:
            for bear in bearish:
                if bull.timeframe != bear.timeframe:
                    continue
                overlap_low = max(bull.low, bear.low)
                overlap_high = min(bull.high, bear.high)
                if overlap_low >= overlap_high:
                    continue
                bprs.append(
                    self._make_pdarray(
                        PDArrayType.BPR,
                        BiasDirection.NEUTRAL,
                        bull.timeframe,
                        overlap_high,
                        overlap_low,
                        max(bull.formed_at, bear.formed_at),
                        bpr_bullish_fvg_id=bull.array_id,
                        bpr_bearish_fvg_id=bear.array_id,
                    )
                )
        return bprs

    def _detect_cisd_levels(self, candles: List[Candle], tf: Timeframe) -> List[PDArray]:
        arrays: List[PDArray] = []
        n = len(candles)
        i = 0
        while i < n:
            if candles[i].is_bullish:
                bullish_run = True
            elif candles[i].is_bearish:
                bullish_run = False
            else:
                i += 1
                continue

            j = i
            while j + 1 < n and (
                (bullish_run and candles[j + 1].is_bullish)
                or (not bullish_run and candles[j + 1].is_bearish)
            ):
                j += 1

            if j - i + 1 >= CISD_MIN_SEQUENCE_LENGTH and j + 1 < n:
                violator = candles[j + 1]
                first_open = candles[i].open
                if bullish_run and violator.close < first_open:
                    arrays.append(
                        self._make_cisd_level(first_open, BiasDirection.BEARISH, tf, violator.timestamp)
                    )
                elif not bullish_run and violator.close > first_open:
                    arrays.append(
                        self._make_cisd_level(first_open, BiasDirection.BULLISH, tf, violator.timestamp)
                    )
            i = j + 1
        return arrays

    def _make_cisd_level(
        self, open_price: float, direction: BiasDirection, tf: Timeframe, formed_at
    ) -> PDArray:
        epsilon = max(abs(open_price) * 1e-5, 1e-6)
        return self._make_pdarray(
            PDArrayType.CISD_LEVEL,
            direction,
            tf,
            open_price + epsilon,
            open_price - epsilon,
            formed_at,
            cisd_sequence_open=open_price,
        )

    def _make_pdarray(
        self,
        array_type: PDArrayType,
        direction: BiasDirection,
        tf: Timeframe,
        high: float,
        low: float,
        formed_at,
        **kwargs,
    ) -> PDArray:
        array = PDArray(
            array_id=deterministic_id("pdarray", array_type.value, direction.value, tf.value, high, low, formed_at),
            array_type=array_type,
            direction=direction,
            timeframe=tf,
            high=high,
            low=low,
            formed_at=formed_at,
            strength_score=0.0,
            **kwargs,
        )
        array.strength_score = self._assign_strength_score(array)
        return array

    def _assign_strength_score(self, array: PDArray) -> float:
        return _ARRAY_TYPE_WEIGHT.get(array.array_type, 0.5)
