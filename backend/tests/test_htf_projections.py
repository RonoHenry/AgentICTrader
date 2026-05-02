"""
Test suite for HTF OHLC computation and projection feature extractor.

This module tests the HTF Candle Projections feature extractor which computes:
- HTF OHLC values for current and last N HTF candles
- HTF Open bias (price above = bullish, price below = bearish)
- Distance from current price to HTF High and HTF Low as range proximity percentages
- HTF candle body size, wick percentages, and close position within range

**Validates: Requirements FR-2**
"""

import os
import sys
from dataclasses import dataclass
from typing import Optional

import pytest
from hypothesis import given, strategies as st, assume

# ---------------------------------------------------------------------------
# Path setup — add workspace root so `ml` package is importable
# ---------------------------------------------------------------------------
_WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, _WORKSPACE_ROOT)

from ml.features.htf_projections import (  # noqa: E402
    HTFProjection,
    HTFProjectionExtractor,
)


# ---------------------------------------------------------------------------
# Test Data Helpers
# ---------------------------------------------------------------------------

def create_sample_candle(
    open_price: float,
    high: float,
    low: float,
    close: float,
    timestamp: str = "2024-01-01T00:00:00Z",
) -> dict:
    """Create a sample candle dictionary."""
    return {
        "time": timestamp,
        "open": open_price,
        "high": high,
        "low": low,
        "close": close,
        "volume": 1000,
    }


# ---------------------------------------------------------------------------
# Property-Based Tests
# ---------------------------------------------------------------------------

class TestHTFProjectionProperties:
    """Property-based tests for HTF projection computations."""

    @given(
        htf_high=st.floats(min_value=1.1, max_value=2.0),
        htf_low=st.floats(min_value=1.0, max_value=1.09),
        current_price=st.floats(min_value=1.0, max_value=2.0),
    )
    def test_proximity_percentages_sum_to_100_when_price_in_range(
        self, htf_high: float, htf_low: float, current_price: float
    ):
        """
        Property: htf_high_proximity_pct + htf_low_proximity_pct = 100
        when price is within HTF range.
        
        **Validates: Requirements FR-2**
        """
        assume(htf_low < htf_high)
        assume(htf_low <= current_price <= htf_high)
        
        extractor = HTFProjectionExtractor()
        projection = extractor.compute_projections(
            current_price=current_price,
            htf_candles=[
                create_sample_candle(
                    open_price=(htf_high + htf_low) / 2,
                    high=htf_high,
                    low=htf_low,
                    close=current_price,
                )
            ],
            htf_timeframe="H1",
        )
        
        total = projection.htf_high_proximity_pct + projection.htf_low_proximity_pct
        assert abs(total - 100.0) < 0.01, (
            f"Proximity percentages must sum to 100 when price is in range. "
            f"Got: {projection.htf_high_proximity_pct} + {projection.htf_low_proximity_pct} = {total}"
        )

    @given(
        htf_open=st.floats(min_value=1.0, max_value=2.0),
        current_price=st.floats(min_value=1.0, max_value=2.0),
    )
    def test_open_bias_is_bullish_iff_price_above_htf_open(
        self, htf_open: float, current_price: float
    ):
        """
        Property: open_bias is BULLISH iff current_price > htf_open.
        
        **Validates: Requirements FR-2**
        """
        assume(abs(current_price - htf_open) > 0.0001)  # Avoid neutral case
        
        extractor = HTFProjectionExtractor()
        projection = extractor.compute_projections(
            current_price=current_price,
            htf_candles=[
                create_sample_candle(
                    open_price=htf_open,
                    high=max(htf_open, current_price) + 0.1,
                    low=min(htf_open, current_price) - 0.1,
                    close=current_price,
                )
            ],
            htf_timeframe="H1",
        )
        
        if current_price > htf_open:
            assert projection.htf_open_bias == "BULLISH", (
                f"Expected BULLISH bias when price ({current_price}) > htf_open ({htf_open}), "
                f"got {projection.htf_open_bias}"
            )
        else:
            assert projection.htf_open_bias == "BEARISH", (
                f"Expected BEARISH bias when price ({current_price}) < htf_open ({htf_open}), "
                f"got {projection.htf_open_bias}"
            )

    @given(
        htf_high=st.floats(min_value=1.1, max_value=2.0),
        htf_low=st.floats(min_value=1.0, max_value=1.09),
        current_price=st.floats(min_value=1.0, max_value=2.0),
    )
    def test_all_percentage_values_in_valid_range(
        self, htf_high: float, htf_low: float, current_price: float
    ):
        """
        Property: all percentage values are in [0, 100] when price is within HTF range.
        
        **Validates: Requirements FR-2**
        """
        assume(htf_low < htf_high)
        assume(htf_low <= current_price <= htf_high)
        
        extractor = HTFProjectionExtractor()
        projection = extractor.compute_projections(
            current_price=current_price,
            htf_candles=[
                create_sample_candle(
                    open_price=(htf_high + htf_low) / 2,
                    high=htf_high,
                    low=htf_low,
                    close=current_price,
                )
            ],
            htf_timeframe="H1",
        )
        
        assert 0 <= projection.htf_high_proximity_pct <= 100, (
            f"htf_high_proximity_pct must be in [0, 100], got {projection.htf_high_proximity_pct}"
        )
        assert 0 <= projection.htf_low_proximity_pct <= 100, (
            f"htf_low_proximity_pct must be in [0, 100], got {projection.htf_low_proximity_pct}"
        )

    @given(
        base_price=st.floats(min_value=1.0, max_value=2.0),
        body_size=st.floats(min_value=0.0, max_value=0.1),
        upper_wick=st.floats(min_value=0.0, max_value=0.05),
        lower_wick=st.floats(min_value=0.0, max_value=0.05),
        is_bullish=st.booleans(),
    )
    def test_body_and_wick_percentages_sum_to_100(
        self, base_price: float, body_size: float, upper_wick: float, lower_wick: float, is_bullish: bool
    ):
        """
        Property: htf_body_pct + htf_upper_wick_pct + htf_lower_wick_pct = 100.
        
        **Validates: Requirements FR-2**
        """
        # Construct valid OHLC from components
        if is_bullish:
            open_price = base_price
            close = base_price + body_size
        else:
            open_price = base_price + body_size
            close = base_price
        
        high = max(open_price, close) + upper_wick
        low = min(open_price, close) - lower_wick
        
        # Ensure valid range
        assume(low < high)
        
        extractor = HTFProjectionExtractor()
        projection = extractor.compute_projections(
            current_price=close,
            htf_candles=[
                create_sample_candle(
                    open_price=open_price,
                    high=high,
                    low=low,
                    close=close,
                )
            ],
            htf_timeframe="H1",
        )
        
        total = (
            projection.htf_body_pct
            + projection.htf_upper_wick_pct
            + projection.htf_lower_wick_pct
        )
        assert abs(total - 100.0) < 0.01, (
            f"Body and wick percentages must sum to 100. "
            f"Got: {projection.htf_body_pct} + {projection.htf_upper_wick_pct} + "
            f"{projection.htf_lower_wick_pct} = {total}"
        )


# ---------------------------------------------------------------------------
# Example-Based Tests
# ---------------------------------------------------------------------------

class TestHTFProjectionExamples:
    """Example-based tests for specific HTF projection scenarios."""

    def test_open_bias_is_neutral_when_price_equals_htf_open(self):
        """
        Test: open_bias is NEUTRAL when current_price == htf_open.
        
        **Validates: Requirements FR-2**
        """
        htf_open = 1.5000
        current_price = 1.5000
        
        extractor = HTFProjectionExtractor()
        projection = extractor.compute_projections(
            current_price=current_price,
            htf_candles=[
                create_sample_candle(
                    open_price=htf_open,
                    high=1.5100,
                    low=1.4900,
                    close=current_price,
                )
            ],
            htf_timeframe="H1",
        )
        
        assert projection.htf_open_bias == "NEUTRAL", (
            f"Expected NEUTRAL bias when price equals htf_open, got {projection.htf_open_bias}"
        )

    def test_htf_projection_dataclass_has_all_required_fields(self):
        """
        Test: HTFProjection dataclass has all required fields.
        
        **Validates: Requirements FR-2**
        """
        extractor = HTFProjectionExtractor()
        projection = extractor.compute_projections(
            current_price=1.5000,
            htf_candles=[
                create_sample_candle(
                    open_price=1.4950,
                    high=1.5100,
                    low=1.4900,
                    close=1.5000,
                )
            ],
            htf_timeframe="H1",
        )
        
        # Check all required fields exist
        assert hasattr(projection, "htf_timeframe")
        assert hasattr(projection, "htf_open")
        assert hasattr(projection, "htf_high")
        assert hasattr(projection, "htf_low")
        assert hasattr(projection, "htf_open_bias")
        assert hasattr(projection, "htf_high_proximity_pct")
        assert hasattr(projection, "htf_low_proximity_pct")
        assert hasattr(projection, "htf_body_pct")
        assert hasattr(projection, "htf_upper_wick_pct")
        assert hasattr(projection, "htf_lower_wick_pct")
        assert hasattr(projection, "htf_close_position")
        
        # Check field types
        assert isinstance(projection.htf_timeframe, str)
        assert isinstance(projection.htf_open, float)
        assert isinstance(projection.htf_high, float)
        assert isinstance(projection.htf_low, float)
        assert isinstance(projection.htf_open_bias, str)
        assert isinstance(projection.htf_high_proximity_pct, float)
        assert isinstance(projection.htf_low_proximity_pct, float)
        assert isinstance(projection.htf_body_pct, float)
        assert isinstance(projection.htf_upper_wick_pct, float)
        assert isinstance(projection.htf_lower_wick_pct, float)
        assert isinstance(projection.htf_close_position, float)

    def test_bullish_candle_projection_computation(self):
        """
        Test: Bullish candle projection computation is correct.
        
        **Validates: Requirements FR-2**
        """
        extractor = HTFProjectionExtractor()
        projection = extractor.compute_projections(
            current_price=1.5050,
            htf_candles=[
                create_sample_candle(
                    open_price=1.5000,  # Bullish candle (close > open)
                    high=1.5100,
                    low=1.4900,
                    close=1.5080,
                )
            ],
            htf_timeframe="H1",
        )
        
        # Price above HTF open → BULLISH bias
        assert projection.htf_open_bias == "BULLISH"
        
        # HTF OHLC values should match
        assert projection.htf_open == 1.5000
        assert projection.htf_high == 1.5100
        assert projection.htf_low == 1.4900
        
        # Proximity percentages should be valid
        assert 0 <= projection.htf_high_proximity_pct <= 100
        assert 0 <= projection.htf_low_proximity_pct <= 100

    def test_bearish_candle_projection_computation(self):
        """
        Test: Bearish candle projection computation is correct.
        
        **Validates: Requirements FR-2**
        """
        extractor = HTFProjectionExtractor()
        projection = extractor.compute_projections(
            current_price=1.4950,
            htf_candles=[
                create_sample_candle(
                    open_price=1.5000,  # Bearish candle (close < open)
                    high=1.5100,
                    low=1.4900,
                    close=1.4920,
                )
            ],
            htf_timeframe="H1",
        )
        
        # Price below HTF open → BEARISH bias
        assert projection.htf_open_bias == "BEARISH"
        
        # HTF OHLC values should match
        assert projection.htf_open == 1.5000
        assert projection.htf_high == 1.5100
        assert projection.htf_low == 1.4900
        
        # Proximity percentages should be valid
        assert 0 <= projection.htf_high_proximity_pct <= 100
        assert 0 <= projection.htf_low_proximity_pct <= 100
