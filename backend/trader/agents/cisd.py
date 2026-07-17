"""
CISD (Change in State of Delivery) Analyzer.

Timeframe-agnostic detector of the TTrades reversal sequence:
    Turtle Soup sweep → FVG / IFVG imbalance → CISD validating Order Block

The detector is completely stateless — callers pass a candle list and an
optional FVG history buffer and receive a CISDResult back.  The same code
path handles both HTF bias validation (H1/H4/D1) and LTF entry gating
(M1/M5/M15) because price is fractal.

Usage example::

    >>> from backend.trader.agents.cisd import CISDAnalyzer, CISDResult
    >>> analyzer = CISDAnalyzer(max_sequence_candles=20)
    >>> candles = [
    ...     {"open": 1.0900, "high": 1.0950, "low": 1.0880, "close": 1.0920},
    ...     ...
    ... ]
    >>> result = analyzer.scan(candles)
    >>> result.confirmed        # True when full 3-step sequence is met
    >>> result.sequence_step    # 0-3, how far through the sequence
    >>> result.direction        # "BULLISH" | "BEARISH" | "NONE"
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class FVGZone:
    """A Fair Value Gap zone detected in a candle sequence.

    Used as the rolling history buffer for IFVG detection.  Callers are
    responsible for persisting and passing this buffer between scan() calls.

    Attributes:
        high: Upper boundary of the gap (strictly greater than low).
        low: Lower boundary of the gap.
        direction: "BULLISH" or "BEARISH".
        is_filled: True when price has traded back through the entire gap.
        candle_index: Index of the third candle (candles[i]) that formed the gap.
    """

    high: float
    low: float
    direction: str
    is_filled: bool
    candle_index: int

    def __post_init__(self) -> None:
        if self.high <= self.low:
            raise ValueError(
                f"FVGZone.high ({self.high}) must be strictly greater than low ({self.low})"
            )
        if self.direction not in ("BULLISH", "BEARISH"):
            raise ValueError(
                f"FVGZone.direction must be 'BULLISH' or 'BEARISH', got {self.direction!r}"
            )


@dataclass
class CISDResult:
    """Output of a single CISDAnalyzer.scan() call.

    Attributes:
        confirmed: True only when all three steps have been satisfied.
        direction: "BULLISH" | "BEARISH" | "NONE".
        sequence_step: Integer 0-3 encoding how far through the sequence price
            has progressed (0 = nothing, 1 = sweep, 2 = sweep+imbalance,
            3 = full CISD confirmed).
        sweep_level: Price of the swing that was swept (the false breakout level).
        sweep_direction: "BULLISH" (sweep of swing low) | "BEARISH" (sweep of
            swing high) | None when no sweep has been detected.
        imbalance_type: "FVG" | "IFVG" | None.
        imbalance_high: Upper bound of the detected imbalance zone.
        imbalance_low: Lower bound of the detected imbalance zone.
        ob_high: Upper body boundary of the validating Order Block.
        ob_low: Lower body boundary of the validating Order Block.
        candles_elapsed: Candles counted since the sweep candle was detected.
    """

    confirmed: bool = False
    direction: str = "NONE"
    sequence_step: int = 0
    sweep_level: Optional[float] = None
    sweep_direction: Optional[str] = None
    imbalance_type: Optional[str] = None
    imbalance_high: Optional[float] = None
    imbalance_low: Optional[float] = None
    ob_high: Optional[float] = None
    ob_low: Optional[float] = None
    candles_elapsed: int = 0


# ---------------------------------------------------------------------------
# Sentinel for "no result yet"
# ---------------------------------------------------------------------------

_EMPTY = CISDResult()


# ---------------------------------------------------------------------------
# Main analyzer
# ---------------------------------------------------------------------------


class CISDAnalyzer:
    """Timeframe-agnostic CISD sequence detector.

    Detects the TTrades three-step reversal confirmation:
        1. Turtle Soup — a candle whose wick pierces a prior swing high/low
           but whose close is back inside the range (stop hunt / false breakout).
        2. Imbalance — an FVG or IFVG forms in the displacement move away from
           the sweep level.
        3. CISD validating OB — a candle closes back into the Order Block formed
           by the displacement candle (program flip confirmed).

    The analyzer is stateless; callers own any persistent FVG history.

    Args:
        max_sequence_candles: How many candles a partial sequence (step 1 or 2)
            may persist before it is expired and the detector resets.  Default 20.
    """

    def __init__(self, max_sequence_candles: int = 20) -> None:
        self.max_sequence_candles = max_sequence_candles

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def scan(
        self,
        candles: List[Dict[str, Any]],
        fvg_history: Optional[List[FVGZone]] = None,
    ) -> CISDResult:
        """Scan a candle list and return the current reversal sequence state.

        Args:
            candles: OHLC candle dictionaries in chronological order.  Each
                dict must have keys ``open``, ``high``, ``low``, ``close``.
            fvg_history: Optional list of previously detected FVGZone objects
                for IFVG detection.  Pass None or [] to skip IFVG path.

        Returns:
            CISDResult with sequence_step in {0, 1, 2, 3} and confirmed=True
            only when all three steps have been satisfied.
        """
        if not candles:
            return CISDResult(confirmed=False, direction="NONE", sequence_step=0, candles_elapsed=0)

        if len(candles) < 3:
            return CISDResult(confirmed=False, direction="NONE", sequence_step=0, candles_elapsed=0)

        history: List[FVGZone] = fvg_history or []

        # Walk candles sequentially, maintaining sequence state.
        # State variables track progress through the 3-step sequence.
        sweep_direction: Optional[str] = None
        sweep_level: Optional[float] = None
        sweep_candle_idx: Optional[int] = None
        candles_elapsed: int = 0

        imbalance_type: Optional[str] = None
        imbalance_high: Optional[float] = None
        imbalance_low: Optional[float] = None
        displacement_candle_idx: Optional[int] = None

        ob_high: Optional[float] = None
        ob_low: Optional[float] = None

        current_step: int = 0

        # We walk from candle 1 onward (need at least one prior candle for
        # swing detection, and we need i-1, i, i+1 for fractals).
        for i in range(1, len(candles)):

            # ── Check expiry before processing ─────────────────────────────
            if current_step >= 1:
                candles_elapsed += 1
                if candles_elapsed > self.max_sequence_candles:
                    # Reset — partial sequence expired
                    sweep_direction = None
                    sweep_level = None
                    sweep_candle_idx = None
                    candles_elapsed = 0
                    imbalance_type = None
                    imbalance_high = None
                    imbalance_low = None
                    displacement_candle_idx = None
                    ob_high = None
                    ob_low = None
                    current_step = 0

            c = candles[i]
            c_high = float(c["high"])
            c_low = float(c["low"])
            c_close = float(c["close"])

            # ── Step 1 — detect Turtle Soup sweep ──────────────────────────
            if current_step == 0:
                # Look for most recent swing high/low in candles[0..i-1]
                swing_low = self._find_last_swing_low(candles, end_idx=i)
                swing_high = self._find_last_swing_high(candles, end_idx=i)

                # BULLISH sweep: wick pierces swing low, close back above it
                if swing_low is not None and c_low < swing_low and c_close > swing_low:
                    sweep_direction = "BULLISH"
                    sweep_level = swing_low
                    sweep_candle_idx = i
                    candles_elapsed = 0
                    current_step = 1
                    continue

                # BEARISH sweep: wick pierces swing high, close back below it
                if swing_high is not None and c_high > swing_high and c_close < swing_high:
                    sweep_direction = "BEARISH"
                    sweep_level = swing_high
                    sweep_candle_idx = i
                    candles_elapsed = 0
                    current_step = 1
                    continue

            # ── Step 2 — detect FVG / IFVG imbalance ───────────────────────
            elif current_step == 1:
                # Need at least 3 candles (i-2, i-1, i) after the sweep
                if i >= sweep_candle_idx + 2 and i >= 2:
                    # FVG detection (3-candle pattern)
                    c_prev2 = candles[i - 2]
                    prev2_high = float(c_prev2["high"])
                    prev2_low = float(c_prev2["low"])

                    fvg_found = False
                    if sweep_direction == "BULLISH":
                        # Bullish FVG: gap between candles[i-2].high and candles[i].low
                        if c_low > prev2_high:
                            imbalance_type = "FVG"
                            imbalance_low = prev2_high
                            imbalance_high = c_low
                            displacement_candle_idx = i - 1  # middle candle drove the move
                            fvg_found = True
                    elif sweep_direction == "BEARISH":
                        # Bearish FVG: gap between candles[i-2].low and candles[i].high
                        if c_high < prev2_low:
                            imbalance_type = "FVG"
                            imbalance_high = prev2_low
                            imbalance_low = c_high
                            displacement_candle_idx = i - 1
                            fvg_found = True

                    # IFVG detection — only if FVG not already found and history provided
                    if not fvg_found and history:
                        for zone in history:
                            # IFVG: opposing FVG being traded into in displacement move
                            if sweep_direction == "BULLISH" and zone.direction == "BEARISH":
                                # Price trading into a prior bearish FVG from below (inversion)
                                if c_low <= zone.high and c_high >= zone.low:
                                    imbalance_type = "IFVG"
                                    imbalance_high = zone.high
                                    imbalance_low = zone.low
                                    displacement_candle_idx = i
                                    fvg_found = True
                                    break
                            elif sweep_direction == "BEARISH" and zone.direction == "BULLISH":
                                # Price trading into a prior bullish FVG from above (inversion)
                                if c_high >= zone.low and c_low <= zone.high:
                                    imbalance_type = "IFVG"
                                    imbalance_high = zone.high
                                    imbalance_low = zone.low
                                    displacement_candle_idx = i
                                    fvg_found = True
                                    break

                    if fvg_found and imbalance_high is not None and imbalance_low is not None:
                        if imbalance_high > imbalance_low:
                            current_step = 2

            # ── Step 3 — detect CISD validating Order Block ─────────────────
            elif current_step == 2:
                # Find the OB: last opposing candle before displacement
                ob = self._find_order_block(
                    candles,
                    sweep_direction=sweep_direction,
                    before_idx=displacement_candle_idx,
                )
                if ob is not None:
                    ob_high_val, ob_low_val = ob
                    # CISD confirmed when close re-enters OB body
                    if ob_low_val <= c_close <= ob_high_val:
                        ob_high = ob_high_val
                        ob_low = ob_low_val
                        current_step = 3
                        # Full sequence confirmed — return immediately
                        return CISDResult(
                            confirmed=True,
                            direction=sweep_direction,
                            sequence_step=3,
                            sweep_level=sweep_level,
                            sweep_direction=sweep_direction,
                            imbalance_type=imbalance_type,
                            imbalance_high=imbalance_high,
                            imbalance_low=imbalance_low,
                            ob_high=ob_high,
                            ob_low=ob_low,
                            candles_elapsed=candles_elapsed,
                        )

        # Return whatever partial progress we reached
        if current_step == 0:
            return CISDResult(
                confirmed=False,
                direction="NONE",
                sequence_step=0,
                candles_elapsed=0,
            )

        if current_step == 1:
            return CISDResult(
                confirmed=False,
                direction="NONE",
                sequence_step=1,
                sweep_level=sweep_level,
                sweep_direction=sweep_direction,
                candles_elapsed=candles_elapsed,
            )

        # current_step == 2
        return CISDResult(
            confirmed=False,
            direction="NONE",
            sequence_step=2,
            sweep_level=sweep_level,
            sweep_direction=sweep_direction,
            imbalance_type=imbalance_type,
            imbalance_high=imbalance_high,
            imbalance_low=imbalance_low,
            candles_elapsed=candles_elapsed,
        )

    def update_fvg_history(
        self, candles: List[Dict[str, Any]]
    ) -> List[FVGZone]:
        """Scan candles and return all fresh FVG zones detected.

        The caller is responsible for persisting the returned list and passing
        it on the next scan() call to enable IFVG detection.

        Args:
            candles: OHLC candle dictionaries in chronological order.

        Returns:
            List of FVGZone objects, one per imbalance detected.  Empty list
            when no FVGs exist or candles is too short.
        """
        result: List[FVGZone] = []
        if len(candles) < 3:
            return result

        seen: set = set()  # (round(high,8), round(low,8)) deduplication

        for i in range(2, len(candles)):
            c_prev2 = candles[i - 2]
            c_curr = candles[i]
            prev2_high = float(c_prev2["high"])
            prev2_low = float(c_prev2["low"])
            c_high = float(c_curr["high"])
            c_low = float(c_curr["low"])

            # Bullish FVG
            if c_low > prev2_high:
                key = (round(prev2_high, 8), round(c_low, 8))
                if key not in seen:
                    seen.add(key)
                    result.append(
                        FVGZone(
                            high=c_low,
                            low=prev2_high,
                            direction="BULLISH",
                            is_filled=False,
                            candle_index=i,
                        )
                    )

            # Bearish FVG
            if c_high < prev2_low:
                key = (round(c_high, 8), round(prev2_low, 8))
                if key not in seen:
                    seen.add(key)
                    result.append(
                        FVGZone(
                            high=prev2_low,
                            low=c_high,
                            direction="BEARISH",
                            is_filled=False,
                            candle_index=i,
                        )
                    )

        return result

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _find_last_swing_high(
        self,
        candles: List[Dict[str, Any]],
        end_idx: int,
    ) -> Optional[float]:
        """Return the most recent swing high price in candles[0..end_idx-1].

        A swing high is a 1-candle fractal: candles[i].high strictly greater
        than both immediate neighbours.
        """
        # Need at least 3 candles to form a fractal
        if end_idx < 3:
            return None

        for i in range(end_idx - 2, 0, -1):
            h = float(candles[i]["high"])
            h_prev = float(candles[i - 1]["high"])
            h_next = float(candles[i + 1]["high"])
            if h > h_prev and h > h_next:
                return h
        return None

    def _find_last_swing_low(
        self,
        candles: List[Dict[str, Any]],
        end_idx: int,
    ) -> Optional[float]:
        """Return the most recent swing low price in candles[0..end_idx-1].

        A swing low is a 1-candle fractal: candles[i].low strictly less than
        both immediate neighbours.
        """
        if end_idx < 3:
            return None

        for i in range(end_idx - 2, 0, -1):
            lo = float(candles[i]["low"])
            lo_prev = float(candles[i - 1]["low"])
            lo_next = float(candles[i + 1]["low"])
            if lo < lo_prev and lo < lo_next:
                return lo
        return None

    def _find_order_block(
        self,
        candles: List[Dict[str, Any]],
        sweep_direction: Optional[str],
        before_idx: Optional[int],
    ) -> Optional[tuple]:
        """Find the Order Block before the displacement move.

        For a BULLISH sequence the OB is the last down-close (bearish) candle
        before the displacement.  For a BEARISH sequence it is the last
        up-close (bullish) candle before the displacement.

        Returns:
            (ob_high, ob_low) tuple as candle body boundaries, or None.
        """
        if before_idx is None or before_idx <= 0:
            return None

        # Search backwards from just before the displacement candle
        for i in range(before_idx - 1, -1, -1):
            c = candles[i]
            o = float(c["open"])
            cl = float(c["close"])

            if sweep_direction == "BULLISH":
                # OB = last bearish (down-close) candle before displacement
                if cl < o:
                    return (max(o, cl), min(o, cl))
            elif sweep_direction == "BEARISH":
                # OB = last bullish (up-close) candle before displacement
                if cl > o:
                    return (max(o, cl), min(o, cl))

        return None
