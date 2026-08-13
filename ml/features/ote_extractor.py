"""ml/features/ote_extractor.py — Optimal Trade Entry (OTE) feature extractor.

Computes Fibonacci-based OTE levels from swing high/low anchor points.

TTrades OTE specification:
  - Fibonacci levels: 0, 0.5, 0.62, 0.705, 0.79, 1
  - Anchor: swing high → swing low (bearish) or swing low → swing high (bullish)
  - OTE zone: 0.62–0.79 retracement
  - Golden pocket (optimal entry): 0.705 level
  - Valid OTE: price is currently inside [0.62, 0.79] retracement zone

The OTE extractor is stateless — no fit() required.
Follows the same @dataclass + class pattern as ZoneFeatureExtractor and HTFProjectionExtractor.

Integration:
  - Called from FeaturePipeline.transform() after ZoneFeatureExtractor
  - Swing high/low come from ZoneFeatureExtractor._find_last_swing_high/low()
  - OTE features feed the confluence scorer as additional confluence signals
  - When ote_in_zone=True, InferenceEngine uses ote_level_705 as entry price

Example usage:
    >>> from ml.features.ote_extractor import OTEExtractor
    >>> extractor = OTEExtractor()
    >>> # Bullish setup: price retraced from swing low to swing high, now pulling back
    >>> features = extractor.extract(
    ...     swing_high=1.5100,
    ...     swing_low=1.4900,
    ...     current_price=1.5041,   # ~70.5% retracement into zone
    ...     direction="LONG",
    ... )
    >>> features.ote_in_zone
    True
    >>> round(features.ote_level_705, 4)
    1.4959  # for a SHORT; for LONG: 1.5100 - 0.705 * (1.5100 - 1.4900) = 1.4959... 
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


# ---------------------------------------------------------------------------
# OTE Fibonacci constants (TTrades specification)
# ---------------------------------------------------------------------------
_FIB_0_5 = 0.5
_FIB_0_62 = 0.62
_FIB_0_705 = 0.705   # Golden pocket — primary entry level
_FIB_0_79 = 0.79


@dataclass
class OTEFeatures:
    """OTE (Optimal Trade Entry) features derived from Fibonacci retracement.

    Attributes:
        ote_in_zone: True when current price is inside the 0.62–0.79 OTE zone.
        ote_level_705: The 0.705 golden pocket price level for the current swing.
        ote_level_62: The 0.62 Fibonacci level price.
        ote_level_79: The 0.79 Fibonacci level price.
        ote_distance_pct: Distance of current price from the 0.705 level,
            expressed as a percentage of the swing range. 0.0 when at the
            golden pocket exactly. Negative when below 0.705 (for LONG),
            positive when above.
        ote_valid: True when a valid swing exists (swing_high > swing_low)
            and direction is provided. False when inputs are degenerate.
    """

    ote_in_zone: bool
    ote_level_705: float
    ote_level_62: float
    ote_level_79: float
    ote_distance_pct: float
    ote_valid: bool


class OTEExtractor:
    """Optimal Trade Entry (OTE) Fibonacci extractor.

    Computes OTE levels and determines whether current price is inside the
    0.62–0.79 retracement zone relative to the most recent swing.

    For a LONG setup:
        - Swing move: swing_low → swing_high (price ran up)
        - Retracement: price pulls back toward swing_low
        - OTE zone: 0.62–0.79 retracement FROM swing_high BACK TOWARD swing_low
        - Level formula: swing_high - fib * (swing_high - swing_low)

    For a SHORT setup:
        - Swing move: swing_high → swing_low (price ran down)
        - Retracement: price retraces toward swing_high
        - OTE zone: 0.62–0.79 retracement FROM swing_low BACK TOWARD swing_high
        - Level formula: swing_low + fib * (swing_high - swing_low)
    """

    def extract(
        self,
        swing_high: float,
        swing_low: float,
        current_price: float,
        direction: str = "LONG",
    ) -> OTEFeatures:
        """Compute OTE features for the current price relative to the swing.

        Args:
            swing_high: Most recent swing high price.
            swing_low: Most recent swing low price.
            current_price: Current market price (latest candle close).
            direction: Trade direction — "LONG" or "SHORT". Determines which
                       end of the swing the Fibonacci anchors from.

        Returns:
            OTEFeatures with zone status, price levels, and distance metrics.
        """
        swing_range = swing_high - swing_low

        # Degenerate input guard
        if swing_range <= 0 or not direction:
            return OTEFeatures(
                ote_in_zone=False,
                ote_level_705=current_price,
                ote_level_62=current_price,
                ote_level_79=current_price,
                ote_distance_pct=0.0,
                ote_valid=False,
            )

        if direction == "LONG":
            # Retracement levels measured downward from swing_high
            level_62 = swing_high - _FIB_0_62 * swing_range
            level_705 = swing_high - _FIB_0_705 * swing_range
            level_79 = swing_high - _FIB_0_79 * swing_range

            # Price is in OTE zone when it has pulled back into [level_79, level_62]
            # (level_79 < level_62 since we subtract more for 0.79)
            in_zone = level_79 <= current_price <= level_62

            # Distance from golden pocket: positive means price is above 0.705 (not yet there)
            distance_pct = ((current_price - level_705) / swing_range) * 100.0

        else:  # SHORT
            # Retracement levels measured upward from swing_low
            level_62 = swing_low + _FIB_0_62 * swing_range
            level_705 = swing_low + _FIB_0_705 * swing_range
            level_79 = swing_low + _FIB_0_79 * swing_range

            # Price is in OTE zone when it has retraced into [level_62, level_79]
            # (level_62 < level_79 since we add more for 0.79)
            in_zone = level_62 <= current_price <= level_79

            # Distance from golden pocket: negative means price is below 0.705 (not yet there)
            distance_pct = ((current_price - level_705) / swing_range) * 100.0

        return OTEFeatures(
            ote_in_zone=in_zone,
            ote_level_705=level_705,
            ote_level_62=level_62,
            ote_level_79=level_79,
            ote_distance_pct=distance_pct,
            ote_valid=True,
        )
