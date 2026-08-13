"""
Swing structure hierarchy classification and BOS/CHoCH detection.

Encodes the "Basic/Advanced Market Structure" nesting: every local extremum is
seeded as a Short-Term swing; a swing is promoted one tier (SHORT_TERM ->
INTERMEDIATE_TERM -> LONG_TERM) once the opposite-type swing immediately
preceding it is broken by a subsequent candle close. Promotion always creates a
*new* SwingPoint at the higher tier rather than mutating the source swing in
place — the lower-tier object must keep its own tier stable forever, otherwise
a chain of same-pass promotions (Requirement 15.4 / Property 24: a promoted
point's `derived_from_swing_id` must reference an object one tier below) could
end up pointing at an object that itself gets promoted again before the caller
ever sees it. Pure and stateless: the classifier never mutates its inputs.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from liquidity_engine.models import (
    BiasDirection,
    Candle,
    StructureEvent,
    StructureEventType,
    SwingPoint,
    SwingStructureResult,
    SwingTier,
    Timeframe,
)
from liquidity_engine.utils.candle_utils import find_swing_highs, find_swing_lows
from liquidity_engine.utils.id_utils import deterministic_id

_NEXT_TIER: Dict[SwingTier, SwingTier] = {
    SwingTier.SHORT_TERM: SwingTier.INTERMEDIATE_TERM,
    SwingTier.INTERMEDIATE_TERM: SwingTier.LONG_TERM,
}


class SwingStructureClassifier:
    """Classifies swing points into a tiered hierarchy and emits BOS/CHoCH events."""

    def classify(
        self, candles_by_tf: Dict[Timeframe, List[Candle]]
    ) -> Dict[Timeframe, SwingStructureResult]:
        return {tf: self._classify_single(tf, candles) for tf, candles in candles_by_tf.items()}

    def _classify_single(self, tf: Timeframe, candles: List[Candle]) -> SwingStructureResult:
        short_term = self._seed_short_term(candles)
        self._mark_broken(short_term, candles)

        intermediate = self._promote_tier(short_term, candles)
        long_term = self._promote_tier(intermediate, candles)

        events = sorted(
            self._classify_structure_events(short_term, candles, tf)
            + self._classify_structure_events(intermediate, candles, tf)
            + self._classify_structure_events(long_term, candles, tf),
            key=lambda e: e.confirmed_at,
        )

        return SwingStructureResult(
            short_term_highs=[s for s in short_term if s.is_high],
            short_term_lows=[s for s in short_term if not s.is_high],
            intermediate_term_highs=[s for s in intermediate if s.is_high],
            intermediate_term_lows=[s for s in intermediate if not s.is_high],
            long_term_highs=[s for s in long_term if s.is_high],
            long_term_lows=[s for s in long_term if not s.is_high],
            events=events,
            latest_event=events[-1] if events else None,
        )

    def _seed_short_term(self, candles: List[Candle]) -> List[SwingPoint]:
        highs = [
            SwingPoint(
                swing_id=deterministic_id("swing", True, candles[i].high, candles[i].timestamp),
                tier=SwingTier.SHORT_TERM,
                is_high=True,
                price=candles[i].high,
                formed_at=candles[i].timestamp,
            )
            for i in find_swing_highs(candles)
        ]
        lows = [
            SwingPoint(
                swing_id=deterministic_id("swing", False, candles[i].low, candles[i].timestamp),
                tier=SwingTier.SHORT_TERM,
                is_high=False,
                price=candles[i].low,
                formed_at=candles[i].timestamp,
            )
            for i in find_swing_lows(candles)
        ]
        return sorted(highs + lows, key=lambda s: s.formed_at)

    def _break_confirmed(self, swing: Optional[SwingPoint], candles: List[Candle]) -> Optional[Candle]:
        """Return the first candle after `swing.formed_at` whose close breaks the swing level."""
        if swing is None:
            return None
        for candle in candles:
            if candle.timestamp <= swing.formed_at:
                continue
            if swing.is_high and candle.close > swing.price:
                return candle
            if not swing.is_high and candle.close < swing.price:
                return candle
        return None

    def _mark_broken(self, swings: List[SwingPoint], candles: List[Candle]) -> None:
        for swing in swings:
            breaking_candle = self._break_confirmed(swing, candles)
            if breaking_candle is not None:
                swing.broken = True
                swing.broken_at = breaking_candle.timestamp

    def _promote_tier(self, swings: List[SwingPoint], candles: List[Candle]) -> List[SwingPoint]:
        """Return brand-new SwingPoints one tier above `swings`, for every entry whose
        immediately preceding opposite-type swing (within `swings`) is broken.
        `swings` itself is never mutated — see module docstring.
        """
        if not swings:
            return []
        next_tier = _NEXT_TIER.get(swings[0].tier)
        if next_tier is None:
            return []

        ordered = sorted(swings, key=lambda s: s.formed_at)
        promoted: List[SwingPoint] = []
        for i, swing in enumerate(ordered):
            preceding_opposite = next(
                (prior for prior in reversed(ordered[:i]) if prior.is_high != swing.is_high),
                None,
            )
            if self._break_confirmed(preceding_opposite, candles) is not None:
                promoted.append(
                    SwingPoint(
                        swing_id=deterministic_id(
                            "promoted", next_tier.value, swing.is_high, swing.price, swing.formed_at
                        ),
                        tier=next_tier,
                        is_high=swing.is_high,
                        price=swing.price,
                        formed_at=swing.formed_at,
                        derived_from_swing_id=preceding_opposite.swing_id,
                    )
                )

        self._mark_broken(promoted, candles)
        return promoted

    def _classify_structure_events(
        self, swings: List[SwingPoint], candles: List[Candle], timeframe: Timeframe
    ) -> List[StructureEvent]:
        if not swings:
            return []
        tier = swings[0].tier
        ordered = sorted(swings, key=lambda s: s.formed_at)
        events: List[StructureEvent] = []
        trend: Optional[BiasDirection] = None
        for swing in ordered:
            breaking_candle = self._break_confirmed(swing, candles)
            if breaking_candle is None:
                continue
            break_direction = BiasDirection.BULLISH if swing.is_high else BiasDirection.BEARISH
            event_type = (
                StructureEventType.BOS
                if trend is None or break_direction == trend
                else StructureEventType.CHOCH
            )
            trend = break_direction
            events.append(
                StructureEvent(
                    event_type=event_type,
                    tier=tier,
                    timeframe=timeframe,
                    direction=break_direction,
                    broken_swing_id=swing.swing_id,
                    confirmed_at=breaking_candle.timestamp,
                )
            )
        return events
