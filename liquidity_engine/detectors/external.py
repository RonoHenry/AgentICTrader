"""
External liquidity pool detection.

Identifies where resting stop orders are likely to sit: previous period
highs/lows, equal highs/lows, and session highs/lows. Pure and stateless.
"""
from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Tuple

from liquidity_engine.models import (
    Candle,
    KillzoneWindow,
    LiquidityLevel,
    LiquiditySource,
    LiquidityType,
    Timeframe,
)
from liquidity_engine.utils.candle_utils import find_swing_highs, find_swing_lows
from liquidity_engine.utils.id_utils import deterministic_id
from liquidity_engine.utils.time_utils import get_killzone

# Previous-period high/low sources, keyed by the timeframe they're derived from.
_PREV_HIGH_LOW_SOURCES: Dict[Timeframe, Tuple[LiquiditySource, LiquiditySource]] = {
    Timeframe.W1: (LiquiditySource.PWH, LiquiditySource.PWL),
    Timeframe.D1: (LiquiditySource.PDH, LiquiditySource.PDL),
    Timeframe.MN1: (LiquiditySource.PMH, LiquiditySource.PML),
}

# Preferred timeframe to source session (intraday killzone) highs/lows from.
_INTRADAY_PRIORITY: List[Timeframe] = [
    Timeframe.M1,
    Timeframe.M3,
    Timeframe.M5,
    Timeframe.M15,
    Timeframe.M30,
    Timeframe.H1,
    Timeframe.H4,
]

# Relative weight [0.0, 1.0] of each timeframe when scoring level significance.
_TIMEFRAME_WEIGHT: Dict[Timeframe, float] = {
    Timeframe.MN1: 1.0,
    Timeframe.W1: 0.9,
    Timeframe.D1: 0.8,
    Timeframe.H12: 0.75,
    Timeframe.H8: 0.7,
    Timeframe.H6: 0.65,
    Timeframe.H4: 0.6,
    Timeframe.H3: 0.55,
    Timeframe.H1: 0.5,
    Timeframe.M30: 0.4,
    Timeframe.M15: 0.3,
    Timeframe.M5: 0.2,
    Timeframe.M3: 0.15,
    Timeframe.M1: 0.1,
}

_KILLZONES: Tuple[KillzoneWindow, ...] = (
    KillzoneWindow.LONDON,
    KillzoneWindow.NY_AM,
    KillzoneWindow.NY_PM,
)


class LiquidityLevelDetector:
    """Detects external liquidity pools (PWH/PWL, PDH/PDL, PMH/PML, EQH/EQL, sessions)."""

    def detect(
        self, candles_by_tf: Dict[Timeframe, List[Candle]], timestamp: datetime
    ) -> List[LiquidityLevel]:
        levels: List[LiquidityLevel] = list(self._detect_previous_highs_lows(candles_by_tf))
        for candles in candles_by_tf.values():
            levels += self._detect_equal_highs_lows(candles)

        intraday_tf = next((tf for tf in _INTRADAY_PRIORITY if tf in candles_by_tf), None)
        if intraday_tf is not None:
            levels += self._detect_session_highs_lows(candles_by_tf[intraday_tf], timestamp)
        return levels

    def _detect_previous_highs_lows(
        self, candles_by_tf: Dict[Timeframe, List[Candle]]
    ) -> List[LiquidityLevel]:
        levels: List[LiquidityLevel] = []
        for tf, (high_source, low_source) in _PREV_HIGH_LOW_SOURCES.items():
            candles = candles_by_tf.get(tf)
            if not candles or len(candles) < 2:
                continue
            prev_candle = candles[-2]
            levels.append(
                self._build_level(
                    LiquidityType.BSL, high_source, prev_candle.high, tf, prev_candle.timestamp, candles
                )
            )
            levels.append(
                self._build_level(
                    LiquidityType.SSL, low_source, prev_candle.low, tf, prev_candle.timestamp, candles
                )
            )
        return levels

    def _detect_equal_highs_lows(
        self, candles: List[Candle], tolerance_pct: float = 0.001
    ) -> List[LiquidityLevel]:
        if not candles:
            return []
        levels = self._cluster_equal(candles, find_swing_highs(candles), is_high=True, tolerance_pct=tolerance_pct)
        levels += self._cluster_equal(candles, find_swing_lows(candles), is_high=False, tolerance_pct=tolerance_pct)
        return levels

    def _cluster_equal(
        self, candles: List[Candle], indices: List[int], is_high: bool, tolerance_pct: float
    ) -> List[LiquidityLevel]:
        if len(indices) < 2:
            return []
        points = sorted(
            ((candles[i].high if is_high else candles[i].low, candles[i].timestamp) for i in indices),
            key=lambda p: p[0],
        )
        levels: List[LiquidityLevel] = []
        i = 0
        while i < len(points) - 1:
            price_a, ts_a = points[i]
            price_b, ts_b = points[i + 1]
            if price_a > 0 and abs(price_b - price_a) / price_a <= tolerance_pct:
                avg_price = (price_a + price_b) / 2
                latest_ts = max(ts_a, ts_b)
                level = LiquidityLevel(
                    level_id=deterministic_id("eq", is_high, price_a, price_b, latest_ts),
                    liquidity_type=LiquidityType.BSL if is_high else LiquidityType.SSL,
                    source=LiquiditySource.EQH if is_high else LiquiditySource.EQL,
                    price=avg_price,
                    timeframe=candles[0].timeframe,
                    formed_at=latest_ts,
                    strength_score=0.0,
                    touch_count=2,
                    band_high=max(price_a, price_b),
                    band_low=min(price_a, price_b),
                )
                level.strength_score = self._score_level(level, candles)
                levels.append(level)
                i += 2
            else:
                i += 1
        return levels

    def _detect_session_highs_lows(
        self, candles: List[Candle], timestamp: datetime
    ) -> List[LiquidityLevel]:
        if not candles:
            return []
        levels: List[LiquidityLevel] = []
        for window in _KILLZONES:
            session_candles = [c for c in candles if get_killzone(c.timestamp) == window]
            if not session_candles:
                continue
            high_candle = max(session_candles, key=lambda c: c.high)
            low_candle = min(session_candles, key=lambda c: c.low)

            high_level = LiquidityLevel(
                level_id=deterministic_id("session_high", window.value, high_candle.timestamp, high_candle.high),
                liquidity_type=LiquidityType.BSL,
                source=LiquiditySource.SESSION_HIGH,
                price=high_candle.high,
                timeframe=high_candle.timeframe,
                formed_at=timestamp,
                strength_score=0.0,
                touch_count=len(session_candles),
            )
            high_level.strength_score = self._score_level(high_level, candles)
            levels.append(high_level)

            low_level = LiquidityLevel(
                level_id=deterministic_id("session_low", window.value, low_candle.timestamp, low_candle.low),
                liquidity_type=LiquidityType.SSL,
                source=LiquiditySource.SESSION_LOW,
                price=low_candle.low,
                timeframe=low_candle.timeframe,
                formed_at=timestamp,
                strength_score=0.0,
                touch_count=len(session_candles),
            )
            low_level.strength_score = self._score_level(low_level, candles)
            levels.append(low_level)
        return levels

    def _score_level(self, level: LiquidityLevel, candles: List[Candle]) -> float:
        touch_component = min(level.touch_count / 5.0, 1.0) * 0.3
        tf_component = _TIMEFRAME_WEIGHT.get(level.timeframe, 0.5) * 0.4
        recency_component = self._recency_factor(level, candles) * 0.3
        return max(0.0, min(1.0, touch_component + tf_component + recency_component))

    def _recency_factor(self, level: LiquidityLevel, candles: List[Candle]) -> float:
        if not candles:
            return 0.5
        matching = [i for i, c in enumerate(candles) if c.timestamp == level.formed_at]
        if not matching:
            return 0.5
        idx = matching[-1]
        return (idx + 1) / len(candles)

    def _build_level(
        self,
        liquidity_type: LiquidityType,
        source: LiquiditySource,
        price: float,
        timeframe: Timeframe,
        formed_at: datetime,
        candles: List[Candle],
    ) -> LiquidityLevel:
        is_high = liquidity_type == LiquidityType.BSL
        touch_count = self._count_touches(price, candles, is_high)
        level = LiquidityLevel(
            level_id=deterministic_id("prev", source.value, price, formed_at),
            liquidity_type=liquidity_type,
            source=source,
            price=price,
            timeframe=timeframe,
            formed_at=formed_at,
            strength_score=0.0,
            touch_count=touch_count,
        )
        level.strength_score = self._score_level(level, candles)
        return level

    def _count_touches(
        self, price: float, candles: List[Candle], is_high: bool, tolerance_pct: float = 0.001
    ) -> int:
        if price == 0:
            return 0
        count = 0
        for candle in candles:
            reference = candle.high if is_high else candle.low
            if abs(reference - price) / price <= tolerance_pct:
                count += 1
        return count
