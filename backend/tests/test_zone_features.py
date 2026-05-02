"""
Test suite for zone and structure feature extractor.

This module tests the ZoneFeatureExtractor which extracts zone and structure features
from candle sequences including:
- BOS (Break of Structure) detection
- CHoCH (Change of Character) detection
- FVG (Fair Value Gap) detection
- Liquidity sweep detection
- Swing high/low distance computation
- HTF trend bias derivation

**Validates: Requirements FR-3**
"""

import os
import sys

import pytest

# ---------------------------------------------------------------------------
# Path setup — add workspace root so `ml` package is importable
# ---------------------------------------------------------------------------
_WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, _WORKSPACE_ROOT)

from ml.features.zone_features import (  # noqa: E402
    ZoneFeatures,
    ZoneFeatureExtractor,
)


class TestZoneFeaturesDataclass:
    """Test ZoneFeatures dataclass has all required fields."""

    def test_zone_features_has_all_required_fields(self):
        """ZoneFeatures dataclass should have all required fields."""
        # Create a ZoneFeatures instance with all required fields
        features = ZoneFeatures(
            bos_detected=True,
            choch_detected=False,
            fvg_present=True,
            liquidity_sweep=False,
            swing_high_distance=50.0,
            swing_low_distance=30.0,
            htf_trend_bias="BULLISH",
        )
        
        # Verify all fields are accessible
        assert hasattr(features, "bos_detected")
        assert hasattr(features, "choch_detected")
        assert hasattr(features, "fvg_present")
        assert hasattr(features, "liquidity_sweep")
        assert hasattr(features, "swing_high_distance")
        assert hasattr(features, "swing_low_distance")
        assert hasattr(features, "htf_trend_bias")
        
        # Verify values
        assert features.bos_detected is True
        assert features.choch_detected is False
        assert features.fvg_present is True
        assert features.liquidity_sweep is False
        assert features.swing_high_distance == 50.0
        assert features.swing_low_distance == 30.0
        assert features.htf_trend_bias == "BULLISH"


class TestBOSDetection:
    """Test BOS (Break of Structure) detection."""

    def test_bos_detected_when_close_breaks_beyond_last_swing_high(self):
        """BOS should be detected when close breaks beyond last swing high."""
        extractor = ZoneFeatureExtractor()
        
        # Known candle sequence with BOS:
        # Candle 1: swing high at 1.5100
        # Candle 2: pullback
        # Candle 3: close breaks above swing high (BOS)
        candles = [
            {"open": 1.5000, "high": 1.5100, "low": 1.4950, "close": 1.5080},  # Swing high
            {"open": 1.5080, "high": 1.5090, "low": 1.5020, "close": 1.5030},  # Pullback
            {"open": 1.5030, "high": 1.5150, "low": 1.5020, "close": 1.5140},  # BOS: close > 1.5100
        ]
        
        features = extractor.extract(candles)
        
        assert features.bos_detected is True

    def test_bos_detected_when_close_breaks_below_last_swing_low(self):
        """BOS should be detected when close breaks below last swing low."""
        extractor = ZoneFeatureExtractor()
        
        # Known candle sequence with BOS:
        # Candle 1: swing low at 1.4900
        # Candle 2: pullback
        # Candle 3: close breaks below swing low (BOS)
        candles = [
            {"open": 1.5000, "high": 1.5050, "low": 1.4900, "close": 1.4920},  # Swing low
            {"open": 1.4920, "high": 1.4980, "low": 1.4910, "close": 1.4970},  # Pullback
            {"open": 1.4970, "high": 1.4980, "low": 1.4850, "close": 1.4860},  # BOS: close < 1.4900
        ]
        
        features = extractor.extract(candles)
        
        assert features.bos_detected is True

    def test_bos_not_detected_when_close_does_not_break_swing(self):
        """BOS should not be detected when close does not break swing high/low."""
        extractor = ZoneFeatureExtractor()
        
        # Candle sequence without BOS
        candles = [
            {"open": 1.5000, "high": 1.5100, "low": 1.4950, "close": 1.5080},
            {"open": 1.5080, "high": 1.5090, "low": 1.5020, "close": 1.5030},
            {"open": 1.5030, "high": 1.5095, "low": 1.5020, "close": 1.5090},  # No BOS: close < 1.5100
        ]
        
        features = extractor.extract(candles)
        
        assert features.bos_detected is False


class TestCHoCHDetection:
    """Test CHoCH (Change of Character) detection."""

    def test_choch_detected_when_bos_occurs_in_opposite_direction(self):
        """CHoCH should be detected when BOS occurs in opposite direction."""
        extractor = ZoneFeatureExtractor()
        
        # Known candle sequence with CHoCH:
        # Candles 0-2: bullish BOS (break above initial high)
        # Candles 3-5: bearish BOS (break below initial low) → CHoCH
        candles = [
            {"open": 1.5000, "high": 1.5100, "low": 1.4950, "close": 1.5080},  # Initial range
            {"open": 1.5080, "high": 1.5090, "low": 1.5020, "close": 1.5030},  # Pullback
            {"open": 1.5030, "high": 1.5150, "low": 1.5020, "close": 1.5140},  # Bullish BOS (close > 1.5100)
            {"open": 1.5140, "high": 1.5150, "low": 1.5080, "close": 1.5090},  # Pullback
            {"open": 1.5090, "high": 1.5110, "low": 1.5070, "close": 1.5100},  # Pullback
            {"open": 1.5100, "high": 1.5110, "low": 1.4900, "close": 1.4920},  # Bearish BOS (close < 1.4950) → CHoCH
        ]
        
        features = extractor.extract(candles)
        
        assert features.choch_detected is True

    def test_choch_not_detected_when_bos_same_direction(self):
        """CHoCH should not be detected when BOS continues in same direction."""
        extractor = ZoneFeatureExtractor()
        
        # Candle sequence with multiple bullish BOS (no CHoCH)
        candles = [
            {"open": 1.5000, "high": 1.5100, "low": 1.4950, "close": 1.5080},
            {"open": 1.5080, "high": 1.5090, "low": 1.5020, "close": 1.5030},
            {"open": 1.5030, "high": 1.5150, "low": 1.5020, "close": 1.5140},  # Bullish BOS
            {"open": 1.5140, "high": 1.5160, "low": 1.5120, "close": 1.5130},
            {"open": 1.5130, "high": 1.5200, "low": 1.5120, "close": 1.5190},  # Another bullish BOS
        ]
        
        features = extractor.extract(candles)
        
        assert features.choch_detected is False


class TestFVGDetection:
    """Test FVG (Fair Value Gap) detection."""

    def test_fvg_detected_when_gap_exists_between_candles(self):
        """FVG should be detected when gap exists between candle[i-2].high and candle[i].low."""
        extractor = ZoneFeatureExtractor()
        
        # Known candle sequence with FVG:
        # Candle 0: high at 1.5000
        # Candle 1: large move (creates gap)
        # Candle 2: low at 1.5050 (gap between 1.5000 and 1.5050)
        candles = [
            {"open": 1.4950, "high": 1.5000, "low": 1.4940, "close": 1.4990},  # Candle i-2
            {"open": 1.4990, "high": 1.5100, "low": 1.4980, "close": 1.5090},  # Candle i-1 (large move)
            {"open": 1.5090, "high": 1.5150, "low": 1.5050, "close": 1.5140},  # Candle i: FVG (1.5000 < 1.5050)
        ]
        
        features = extractor.extract(candles)
        
        assert features.fvg_present is True

    def test_fvg_not_detected_when_no_gap(self):
        """FVG should not be detected when no gap exists."""
        extractor = ZoneFeatureExtractor()
        
        # Candle sequence without FVG (no gap)
        candles = [
            {"open": 1.4950, "high": 1.5000, "low": 1.4940, "close": 1.4990},
            {"open": 1.4990, "high": 1.5050, "low": 1.4980, "close": 1.5040},
            {"open": 1.5040, "high": 1.5100, "low": 1.4995, "close": 1.5090},  # No FVG: low overlaps
        ]
        
        features = extractor.extract(candles)
        
        assert features.fvg_present is False


class TestLiquiditySweepDetection:
    """Test liquidity sweep detection."""

    def test_liquidity_sweep_detected_when_wick_exceeds_swing_but_close_inside(self):
        """Liquidity sweep should be detected when wick exceeds swing high/low but close is back inside."""
        extractor = ZoneFeatureExtractor()
        
        # Known candle sequence with liquidity sweep:
        # Candle 1: swing high at 1.5100
        # Candle 2: wick exceeds 1.5100 but close is below (liquidity sweep)
        candles = [
            {"open": 1.5000, "high": 1.5100, "low": 1.4950, "close": 1.5080},  # Swing high
            {"open": 1.5080, "high": 1.5090, "low": 1.5020, "close": 1.5030},  # Pullback
            {"open": 1.5030, "high": 1.5120, "low": 1.5020, "close": 1.5040},  # Liquidity sweep: high > 1.5100, close < 1.5100
        ]
        
        features = extractor.extract(candles)
        
        assert features.liquidity_sweep is True

    def test_liquidity_sweep_not_detected_when_close_breaks_swing(self):
        """Liquidity sweep should not be detected when close also breaks swing (that's BOS)."""
        extractor = ZoneFeatureExtractor()
        
        # Candle sequence with BOS (not liquidity sweep)
        candles = [
            {"open": 1.5000, "high": 1.5100, "low": 1.4950, "close": 1.5080},
            {"open": 1.5080, "high": 1.5090, "low": 1.5020, "close": 1.5030},
            {"open": 1.5030, "high": 1.5150, "low": 1.5020, "close": 1.5140},  # BOS: close > 1.5100
        ]
        
        features = extractor.extract(candles)
        
        assert features.liquidity_sweep is False


class TestSwingDistanceComputation:
    """Test swing high/low distance computation."""

    def test_swing_high_distance_computed_correctly(self):
        """swing_high_distance should be computed as distance from current price to last swing high."""
        extractor = ZoneFeatureExtractor()
        
        # Candle sequence with known swing high
        candles = [
            {"open": 1.5000, "high": 1.5100, "low": 1.4950, "close": 1.5080},  # Swing high at 1.5100
            {"open": 1.5080, "high": 1.5090, "low": 1.5020, "close": 1.5030},  # Current price: 1.5030
        ]
        
        features = extractor.extract(candles)
        
        # Distance from 1.5030 to 1.5100 = 70 pips
        expected_distance = 1.5100 - 1.5030
        assert features.swing_high_distance == pytest.approx(expected_distance, abs=0.0001)

    def test_swing_low_distance_computed_correctly(self):
        """swing_low_distance should be computed as distance from current price to last swing low."""
        extractor = ZoneFeatureExtractor()
        
        # Candle sequence with known swing low
        candles = [
            {"open": 1.5000, "high": 1.5050, "low": 1.4900, "close": 1.4920},  # Swing low at 1.4900
            {"open": 1.4920, "high": 1.4980, "low": 1.4910, "close": 1.4970},  # Current price: 1.4970
        ]
        
        features = extractor.extract(candles)
        
        # Distance from 1.4970 to 1.4900 = 70 pips
        expected_distance = 1.4970 - 1.4900
        assert features.swing_low_distance == pytest.approx(expected_distance, abs=0.0001)


class TestHTFTrendBias:
    """Test HTF trend bias derivation from HTF candle direction."""

    def test_htf_trend_bias_bullish_when_htf_candle_bullish(self):
        """htf_trend_bias should be BULLISH when HTF candle is bullish (close > open)."""
        extractor = ZoneFeatureExtractor()
        
        # Candle sequence with bullish HTF candle
        candles = [
            {"open": 1.5000, "high": 1.5100, "low": 1.4950, "close": 1.5080},  # Bullish HTF candle
        ]
        
        # Pass HTF candle data
        htf_candle = {"open": 1.5000, "high": 1.5100, "low": 1.4950, "close": 1.5080}
        
        features = extractor.extract(candles, htf_candle=htf_candle)
        
        assert features.htf_trend_bias == "BULLISH"

    def test_htf_trend_bias_bearish_when_htf_candle_bearish(self):
        """htf_trend_bias should be BEARISH when HTF candle is bearish (close < open)."""
        extractor = ZoneFeatureExtractor()
        
        # Candle sequence with bearish HTF candle
        candles = [
            {"open": 1.5080, "high": 1.5100, "low": 1.4950, "close": 1.5000},  # Bearish HTF candle
        ]
        
        # Pass HTF candle data
        htf_candle = {"open": 1.5080, "high": 1.5100, "low": 1.4950, "close": 1.5000}
        
        features = extractor.extract(candles, htf_candle=htf_candle)
        
        assert features.htf_trend_bias == "BEARISH"

    def test_htf_trend_bias_neutral_when_htf_candle_doji(self):
        """htf_trend_bias should be NEUTRAL when HTF candle is doji (close == open)."""
        extractor = ZoneFeatureExtractor()
        
        # Candle sequence with doji HTF candle
        candles = [
            {"open": 1.5000, "high": 1.5100, "low": 1.4950, "close": 1.5000},  # Doji HTF candle
        ]
        
        # Pass HTF candle data
        htf_candle = {"open": 1.5000, "high": 1.5100, "low": 1.4950, "close": 1.5000}
        
        features = extractor.extract(candles, htf_candle=htf_candle)
        
        assert features.htf_trend_bias == "NEUTRAL"
