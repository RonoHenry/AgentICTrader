"""
Candle structure feature extractor.

This module implements the CandleFeatureExtractor which extracts structural features
from OHLCV candles including:
- Body percentage, wick percentages, close position
- Bullish/bearish classification
- Engulfing pattern detection

**Implements: Requirements FR-3**

Example usage:
    >>> from ml.features.candle_features import CandleFeatureExtractor
    >>> extractor = CandleFeatureExtractor()
    >>> ohlcv = {
    ...     "open": 1.5000,
    ...     "high": 1.5100,
    ...     "low": 1.4900,
    ...     "close": 1.5080,
    ...     "volume": 1000,
    ... }
    >>> features = extractor.extract(ohlcv)
    >>> features.is_bullish
    True
    >>> features.body_pct
    40.0
"""

from dataclasses import dataclass
from typing import Dict, Any


@dataclass
class CandleFeatures:
    """
    Candle structure features data structure.
    
    Contains all structural features extracted from a single OHLCV candle.
    
    Attributes:
        body_pct: Candle body size as percentage of total range (0-100)
        upper_wick_pct: Upper wick size as percentage of total range (0-100)
        lower_wick_pct: Lower wick size as percentage of total range (0-100)
        close_position: Close position within range (0-1, where 0=at low, 1=at high)
        is_bullish: True if close > open, False otherwise
    """
    body_pct: float
    upper_wick_pct: float
    lower_wick_pct: float
    close_position: float
    is_bullish: bool


class CandleFeatureExtractor:
    """
    Candle structure feature extractor.
    
    Extracts structural features from OHLCV candles for pattern recognition
    and confluence scoring.
    
    **Implements: Requirements FR-3**
    """
    
    def __init__(self):
        """Initialize the candle feature extractor."""
        pass
    
    def extract(self, ohlcv: Dict[str, Any]) -> CandleFeatures:
        """
        Extract candle structure features from OHLCV data.
        
        Args:
            ohlcv: Dictionary containing OHLCV data with keys:
                - open: Opening price
                - high: High price
                - low: Low price
                - close: Closing price
                - volume: Trading volume (optional)
                
        Returns:
            CandleFeatures dataclass with all computed features
            
        Raises:
            ValueError: If ohlcv is missing required fields or has invalid OHLC
            
        **Validates: Requirements FR-3**
        """
        # Validate and extract OHLC values
        open_price, high, low, close = self._validate_and_extract_ohlc(ohlcv)
        
        # Compute is_bullish
        is_bullish = close > open_price
        
        # Compute body and wick percentages
        body_pct, upper_wick_pct, lower_wick_pct = self._compute_body_and_wick_percentages(
            open_price, high, low, close
        )
        
        # Compute close position
        close_position = self._compute_close_position(close, high, low)
        
        return CandleFeatures(
            body_pct=body_pct,
            upper_wick_pct=upper_wick_pct,
            lower_wick_pct=lower_wick_pct,
            close_position=close_position,
            is_bullish=is_bullish,
        )
    
    def is_engulfing(
        self, current_ohlcv: Dict[str, Any], previous_ohlcv: Dict[str, Any]
    ) -> bool:
        """
        Detect if current candle engulfs previous candle body.
        
        An engulfing pattern occurs when:
        1. Current and previous candles are opposite directions (bullish/bearish)
        2. Current candle body fully engulfs previous candle body
        
        Args:
            current_ohlcv: Current candle OHLCV data
            previous_ohlcv: Previous candle OHLCV data
            
        Returns:
            True if current candle engulfs previous candle, False otherwise
            
        **Validates: Requirements FR-3**
        """
        # Extract OHLC values
        curr_open = float(current_ohlcv["open"])
        curr_close = float(current_ohlcv["close"])
        prev_open = float(previous_ohlcv["open"])
        prev_close = float(previous_ohlcv["close"])
        
        # Determine candle directions
        curr_is_bullish = curr_close > curr_open
        prev_is_bullish = prev_close > prev_open
        
        # Engulfing requires opposite directions
        if curr_is_bullish == prev_is_bullish:
            return False
        
        # Get body boundaries
        curr_body_top = max(curr_open, curr_close)
        curr_body_bottom = min(curr_open, curr_close)
        prev_body_top = max(prev_open, prev_close)
        prev_body_bottom = min(prev_open, prev_close)
        
        # Check if current body fully engulfs previous body
        engulfs = (
            curr_body_bottom < prev_body_bottom and
            curr_body_top > prev_body_top
        )
        
        return engulfs
    
    def _validate_and_extract_ohlc(
        self, ohlcv: Dict[str, Any]
    ) -> tuple[float, float, float, float]:
        """
        Validate and extract OHLC values from OHLCV dictionary.
        
        Args:
            ohlcv: Dictionary containing OHLCV data
            
        Returns:
            Tuple of (open, high, low, close) as floats
            
        Raises:
            ValueError: If required fields are missing or OHLC relationship is invalid
        """
        # Validate required fields
        required_fields = ["open", "high", "low", "close"]
        for field in required_fields:
            if field not in ohlcv:
                raise ValueError(f"OHLCV missing required field: {field}")
        
        open_price = float(ohlcv["open"])
        high = float(ohlcv["high"])
        low = float(ohlcv["low"])
        close = float(ohlcv["close"])
        
        # Validate OHLC relationship
        if high < low:
            raise ValueError(f"Invalid OHLC: high ({high}) < low ({low})")
        if high < max(open_price, close):
            raise ValueError(f"Invalid OHLC: high ({high}) < max(open, close)")
        if low > min(open_price, close):
            raise ValueError(f"Invalid OHLC: low ({low}) > min(open, close)")
        
        return open_price, high, low, close
    
    def _compute_body_and_wick_percentages(
        self, open_price: float, high: float, low: float, close: float
    ) -> tuple[float, float, float]:
        """
        Compute candle body size and wick percentages.
        
        The body represents the distance between open and close, while wicks
        represent the rejection zones above and below the body.
        
        Args:
            open_price: Candle open price
            high: Candle high price
            low: Candle low price
            close: Candle close price
            
        Returns:
            Tuple of (body_pct, upper_wick_pct, lower_wick_pct)
            
        Note:
            The three percentages always sum to 100.
        """
        candle_range = high - low
        
        if candle_range == 0:
            # Degenerate case: high == low (single price point)
            return 0.0, 0.0, 0.0
        
        # Body size (absolute difference between open and close)
        body_size = abs(close - open_price)
        
        # Upper wick (from max(open, close) to high)
        upper_wick_size = high - max(open_price, close)
        
        # Lower wick (from low to min(open, close))
        lower_wick_size = min(open_price, close) - low
        
        # Convert to percentages
        body_pct = (body_size / candle_range) * 100.0
        upper_wick_pct = (upper_wick_size / candle_range) * 100.0
        lower_wick_pct = (lower_wick_size / candle_range) * 100.0
        
        return body_pct, upper_wick_pct, lower_wick_pct
    
    def _compute_close_position(
        self, close: float, high: float, low: float
    ) -> float:
        """
        Compute close position within range (0-1).
        
        Args:
            close: Candle close price
            high: Candle high price
            low: Candle low price
            
        Returns:
            Close position as decimal (0.0 = at low, 1.0 = at high)
        """
        candle_range = high - low
        
        if candle_range == 0:
            # Degenerate case: high == low (single price point)
            return 0.5
        
        close_position = (close - low) / candle_range
        
        return close_position
