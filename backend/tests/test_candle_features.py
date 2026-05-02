"""
Test suite for candle structure feature extractor.

This module tests the CandleFeatureExtractor which extracts structural features
from OHLCV candles including:
- Body percentage, wick percentages, close position
- Bullish/bearish classification
- Engulfing pattern detection

**Validates: Requirements FR-3**
"""

import os
import sys

import pytest
from hypothesis import given, strategies as st

# ---------------------------------------------------------------------------
# Path setup — add workspace root so `ml` package is importable
# ---------------------------------------------------------------------------
_WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, _WORKSPACE_ROOT)

from ml.features.candle_features import (  # noqa: E402
    CandleFeatures,
    CandleFeatureExtractor,
)


class TestCandleFeaturesDataclass:
    """Test CandleFeatures dataclass has all required fields."""

    def test_candle_features_has_all_required_fields(self):
        """CandleFeatures dataclass should have all required fields."""
        # Create a CandleFeatures instance with all required fields
        features = CandleFeatures(
            body_pct=50.0,
            upper_wick_pct=25.0,
            lower_wick_pct=25.0,
            close_position=0.75,
            is_bullish=True,
        )
        
        # Verify all fields are accessible
        assert hasattr(features, "body_pct")
        assert hasattr(features, "upper_wick_pct")
        assert hasattr(features, "lower_wick_pct")
        assert hasattr(features, "close_position")
        assert hasattr(features, "is_bullish")
        
        # Verify values
        assert features.body_pct == 50.0
        assert features.upper_wick_pct == 25.0
        assert features.lower_wick_pct == 25.0
        assert features.close_position == 0.75
        assert features.is_bullish is True


class TestCandleFeatureExtractor:
    """Test CandleFeatureExtractor.extract() method."""

    def test_extract_bullish_candle(self):
        """Test extraction of bullish candle features."""
        extractor = CandleFeatureExtractor()
        
        ohlcv = {
            "open": 1.5000,
            "high": 1.5100,
            "low": 1.4900,
            "close": 1.5080,
            "volume": 1000,
        }
        
        features = extractor.extract(ohlcv)
        
        # Bullish candle: close > open
        assert features.is_bullish is True
        
        # Body = 80 pips, Range = 200 pips → 40%
        assert features.body_pct == pytest.approx(40.0, abs=0.1)
        
        # Upper wick = 20 pips → 10%
        assert features.upper_wick_pct == pytest.approx(10.0, abs=0.1)
        
        # Lower wick = 100 pips → 50%
        assert features.lower_wick_pct == pytest.approx(50.0, abs=0.1)
        
        # Close position: (1.5080 - 1.4900) / (1.5100 - 1.4900) = 0.9
        assert features.close_position == pytest.approx(0.9, abs=0.01)

    def test_extract_bearish_candle(self):
        """Test extraction of bearish candle features."""
        extractor = CandleFeatureExtractor()
        
        ohlcv = {
            "open": 1.5080,
            "high": 1.5100,
            "low": 1.4900,
            "close": 1.5000,
            "volume": 1000,
        }
        
        features = extractor.extract(ohlcv)
        
        # Bearish candle: close < open
        assert features.is_bullish is False
        
        # Body = 80 pips, Range = 200 pips → 40%
        assert features.body_pct == pytest.approx(40.0, abs=0.1)
        
        # Upper wick = 20 pips → 10%
        assert features.upper_wick_pct == pytest.approx(10.0, abs=0.1)
        
        # Lower wick = 100 pips → 50%
        assert features.lower_wick_pct == pytest.approx(50.0, abs=0.1)
        
        # Close position: (1.5000 - 1.4900) / (1.5100 - 1.4900) = 0.5
        assert features.close_position == pytest.approx(0.5, abs=0.01)


class TestIsBullishProperty:
    """Test is_bullish property: True iff close > open."""

    def test_is_bullish_true_when_close_greater_than_open(self):
        """is_bullish should be True when close > open."""
        extractor = CandleFeatureExtractor()
        
        ohlcv = {
            "open": 1.5000,
            "high": 1.5100,
            "low": 1.4900,
            "close": 1.5050,
            "volume": 1000,
        }
        
        features = extractor.extract(ohlcv)
        assert features.is_bullish is True

    def test_is_bullish_false_when_close_less_than_open(self):
        """is_bullish should be False when close < open."""
        extractor = CandleFeatureExtractor()
        
        ohlcv = {
            "open": 1.5050,
            "high": 1.5100,
            "low": 1.4900,
            "close": 1.5000,
            "volume": 1000,
        }
        
        features = extractor.extract(ohlcv)
        assert features.is_bullish is False

    def test_is_bullish_false_when_close_equals_open(self):
        """is_bullish should be False when close == open (doji)."""
        extractor = CandleFeatureExtractor()
        
        ohlcv = {
            "open": 1.5000,
            "high": 1.5100,
            "low": 1.4900,
            "close": 1.5000,
            "volume": 1000,
        }
        
        features = extractor.extract(ohlcv)
        assert features.is_bullish is False


class TestEngulfingPattern:
    """Test engulfing pattern detection."""

    def test_is_engulfing_bullish_engulfing(self):
        """is_engulfing should return True for bullish engulfing pattern."""
        extractor = CandleFeatureExtractor()
        
        # Previous candle: bearish (open=1.5050, close=1.5000)
        previous_ohlcv = {
            "open": 1.5050,
            "high": 1.5060,
            "low": 1.4990,
            "close": 1.5000,
            "volume": 1000,
        }
        
        # Current candle: bullish (open=1.4980, close=1.5070)
        # Body fully engulfs previous candle body
        current_ohlcv = {
            "open": 1.4980,
            "high": 1.5100,
            "low": 1.4970,
            "close": 1.5070,
            "volume": 1000,
        }
        
        result = extractor.is_engulfing(current_ohlcv, previous_ohlcv)
        assert result is True

    def test_is_engulfing_bearish_engulfing(self):
        """is_engulfing should return True for bearish engulfing pattern."""
        extractor = CandleFeatureExtractor()
        
        # Previous candle: bullish (open=1.5000, close=1.5050)
        previous_ohlcv = {
            "open": 1.5000,
            "high": 1.5060,
            "low": 1.4990,
            "close": 1.5050,
            "volume": 1000,
        }
        
        # Current candle: bearish (open=1.5070, close=1.4980)
        # Body fully engulfs previous candle body
        current_ohlcv = {
            "open": 1.5070,
            "high": 1.5100,
            "low": 1.4970,
            "close": 1.4980,
            "volume": 1000,
        }
        
        result = extractor.is_engulfing(current_ohlcv, previous_ohlcv)
        assert result is True

    def test_is_engulfing_false_when_body_does_not_engulf(self):
        """is_engulfing should return False when body does not fully engulf."""
        extractor = CandleFeatureExtractor()
        
        # Previous candle: bearish (open=1.5050, close=1.5000)
        previous_ohlcv = {
            "open": 1.5050,
            "high": 1.5060,
            "low": 1.4990,
            "close": 1.5000,
            "volume": 1000,
        }
        
        # Current candle: bullish but doesn't fully engulf
        # (open=1.5010, close=1.5060) - doesn't go below previous close
        current_ohlcv = {
            "open": 1.5010,
            "high": 1.5100,
            "low": 1.5000,
            "close": 1.5060,
            "volume": 1000,
        }
        
        result = extractor.is_engulfing(current_ohlcv, previous_ohlcv)
        assert result is False

    def test_is_engulfing_false_when_same_direction(self):
        """is_engulfing should return False when both candles same direction."""
        extractor = CandleFeatureExtractor()
        
        # Previous candle: bullish
        previous_ohlcv = {
            "open": 1.5000,
            "high": 1.5060,
            "low": 1.4990,
            "close": 1.5050,
            "volume": 1000,
        }
        
        # Current candle: also bullish (not engulfing pattern)
        current_ohlcv = {
            "open": 1.4980,
            "high": 1.5100,
            "low": 1.4970,
            "close": 1.5070,
            "volume": 1000,
        }
        
        result = extractor.is_engulfing(current_ohlcv, previous_ohlcv)
        assert result is False


class TestPercentageSumProperty:
    """
    Property-based test: body_pct + upper_wick_pct + lower_wick_pct = 100 for all valid candles.
    
    **Validates: Requirements FR-3**
    """

    @given(
        open_price=st.floats(min_value=1.0, max_value=2.0),
        high_offset=st.floats(min_value=0.0, max_value=0.1),
        low_offset=st.floats(min_value=0.0, max_value=0.1),
        close_offset=st.floats(min_value=-0.1, max_value=0.1),
    )
    def test_percentages_sum_to_100(self, open_price, high_offset, low_offset, close_offset):
        """
        Property: body_pct + upper_wick_pct + lower_wick_pct = 100 for all valid candles.
        
        **Validates: Requirements FR-3**
        """
        extractor = CandleFeatureExtractor()
        
        # Construct valid OHLC
        low = open_price - low_offset
        high = open_price + high_offset
        close = open_price + close_offset
        
        # Ensure close is within [low, high]
        close = max(low, min(high, close))
        
        # Skip degenerate cases where high == low
        if abs(high - low) < 1e-6:
            return
        
        ohlcv = {
            "open": open_price,
            "high": high,
            "low": low,
            "close": close,
            "volume": 1000,
        }
        
        features = extractor.extract(ohlcv)
        
        total_pct = features.body_pct + features.upper_wick_pct + features.lower_wick_pct
        
        assert total_pct == pytest.approx(100.0, abs=0.01), (
            f"Percentages must sum to 100. Got: body={features.body_pct}, "
            f"upper_wick={features.upper_wick_pct}, lower_wick={features.lower_wick_pct}, "
            f"total={total_pct}"
        )


class TestClosePositionProperty:
    """
    Property-based test: close_position is always in [0, 1].
    
    **Validates: Requirements FR-3**
    """

    @given(
        open_price=st.floats(min_value=1.0, max_value=2.0),
        high_offset=st.floats(min_value=0.0, max_value=0.1),
        low_offset=st.floats(min_value=0.0, max_value=0.1),
        close_offset=st.floats(min_value=-0.1, max_value=0.1),
    )
    def test_close_position_in_range(self, open_price, high_offset, low_offset, close_offset):
        """
        Property: close_position is always in [0, 1].
        
        **Validates: Requirements FR-3**
        """
        extractor = CandleFeatureExtractor()
        
        # Construct valid OHLC
        low = open_price - low_offset
        high = open_price + high_offset
        close = open_price + close_offset
        
        # Ensure close is within [low, high]
        close = max(low, min(high, close))
        
        # Skip degenerate cases where high == low
        if abs(high - low) < 1e-6:
            return
        
        ohlcv = {
            "open": open_price,
            "high": high,
            "low": low,
            "close": close,
            "volume": 1000,
        }
        
        features = extractor.extract(ohlcv)
        
        assert 0.0 <= features.close_position <= 1.0, (
            f"close_position must be in [0, 1]. Got: {features.close_position}"
        )
