"""
HTF OHLC computation and projection feature extractor.

This module implements the HTF Candle Projections feature extractor which computes:
- HTF OHLC values for current and last N HTF candles (regular OHLC only, no Heikin Ashi)
- HTF Open bias (price above = bullish, price below = bearish)
- Distance from current price to HTF High and HTF Low as range proximity percentages
- HTF candle body size, wick percentages, and close position within range

**Implements: Requirements FR-2**

Example usage:
    >>> from ml.features.htf_projections import HTFProjectionExtractor
    >>> extractor = HTFProjectionExtractor()
    >>> projection = extractor.compute_projections(
    ...     current_price=1.5050,
    ...     htf_candles=[{
    ...         "time": "2024-01-01T00:00:00Z",
    ...         "open": 1.5000,
    ...         "high": 1.5100,
    ...         "low": 1.4900,
    ...         "close": 1.5080,
    ...         "volume": 1000,
    ...     }],
    ...     htf_timeframe="H1",
    ... )
    >>> projection.htf_open_bias
    'BULLISH'
"""

from dataclasses import dataclass
from typing import List, Dict, Any, Optional


@dataclass
class HTFProjection:
    """
    HTF Candle Projection data structure.
    
    Contains all HTF projection levels and computed features for a single candle.
    
    Attributes:
        htf_timeframe: Higher timeframe identifier (e.g., "H1", "H4", "D1")
        htf_open: HTF candle open price (bias anchor)
        htf_high: HTF candle high price (upper range boundary)
        htf_low: HTF candle low price (lower range boundary)
        htf_open_bias: Directional bias relative to HTF open (BULLISH/BEARISH/NEUTRAL)
        htf_high_proximity_pct: Distance from current price to HTF high as percentage
        htf_low_proximity_pct: Distance from current price to HTF low as percentage
        htf_body_pct: HTF candle body size as percentage of total range
        htf_upper_wick_pct: HTF upper wick size as percentage of total range
        htf_lower_wick_pct: HTF lower wick size as percentage of total range
        htf_close_position: HTF close position within range (0-100)
    """
    htf_timeframe: str
    htf_open: float
    htf_high: float
    htf_low: float
    htf_open_bias: str
    htf_high_proximity_pct: float
    htf_low_proximity_pct: float
    htf_body_pct: float
    htf_upper_wick_pct: float
    htf_lower_wick_pct: float
    htf_close_position: float


class HTFProjectionExtractor:
    """
    HTF Candle Projection feature extractor.
    
    Computes HTF projection features from HTF candle data and current price.
    This is the SOLE technical indicator in the system (no ATR, RSI, ADX, EMA).
    
    **Implements: Requirements FR-2**
    """
    
    def __init__(self):
        """Initialize the HTF projection extractor."""
        pass
    
    def fetch_htf_candles(
        self,
        instrument: str,
        htf_timeframe: str,
        n_candles: int = 1,
    ) -> List[Dict[str, Any]]:
        """
        Fetch HTF candles from TimescaleDB.
        
        Args:
            instrument: Trading instrument (e.g., "EURUSD", "US500")
            htf_timeframe: Higher timeframe identifier (e.g., "H1", "H4", "D1")
            n_candles: Number of HTF candles to fetch (default: 1)
            
        Returns:
            List of HTF candle dictionaries with OHLCV data
            
        Note:
            This is a placeholder implementation. In production, this would
            query TimescaleDB for the most recent N HTF candles.
        """
        # Placeholder implementation
        # In production, this would query TimescaleDB:
        # SELECT time, open, high, low, close, volume
        # FROM candles
        # WHERE instrument = %s AND timeframe = %s
        # ORDER BY time DESC
        # LIMIT %s
        return []
    
    def compute_projections(
        self,
        current_price: float,
        htf_candles: List[Dict[str, Any]],
        htf_timeframe: str,
    ) -> HTFProjection:
        """
        Compute HTF projection features from HTF candle data.
        
        Args:
            current_price: Current market price
            htf_candles: List of HTF candle dictionaries (most recent first)
            htf_timeframe: Higher timeframe identifier
            
        Returns:
            HTFProjection dataclass with all computed features
            
        Raises:
            ValueError: If htf_candles is empty or invalid
            
        **Validates: Requirements FR-2**
        """
        if not htf_candles:
            raise ValueError("htf_candles cannot be empty")
        
        # Use the most recent HTF candle
        htf_candle = htf_candles[0]
        
        # Validate candle has required fields
        required_fields = ["open", "high", "low", "close"]
        for field in required_fields:
            if field not in htf_candle:
                raise ValueError(f"HTF candle missing required field: {field}")
        
        htf_open = float(htf_candle["open"])
        htf_high = float(htf_candle["high"])
        htf_low = float(htf_candle["low"])
        htf_close = float(htf_candle["close"])
        
        # Validate OHLC relationship
        if htf_high < htf_low:
            raise ValueError(f"Invalid OHLC: high ({htf_high}) < low ({htf_low})")
        if htf_high < max(htf_open, htf_close):
            raise ValueError(f"Invalid OHLC: high ({htf_high}) < max(open, close)")
        if htf_low > min(htf_open, htf_close):
            raise ValueError(f"Invalid OHLC: low ({htf_low}) > min(open, close)")
        
        # Compute HTF open bias
        htf_open_bias = self._compute_open_bias(current_price, htf_open)
        
        # Compute proximity percentages
        htf_high_proximity_pct, htf_low_proximity_pct = self._compute_proximity_percentages(
            current_price, htf_high, htf_low
        )
        
        # Compute body and wick percentages
        htf_body_pct, htf_upper_wick_pct, htf_lower_wick_pct = self._compute_body_and_wick_percentages(
            htf_open, htf_high, htf_low, htf_close
        )
        
        # Compute close position within range
        htf_close_position = self._compute_close_position(htf_close, htf_high, htf_low)
        
        return HTFProjection(
            htf_timeframe=htf_timeframe,
            htf_open=htf_open,
            htf_high=htf_high,
            htf_low=htf_low,
            htf_open_bias=htf_open_bias,
            htf_high_proximity_pct=htf_high_proximity_pct,
            htf_low_proximity_pct=htf_low_proximity_pct,
            htf_body_pct=htf_body_pct,
            htf_upper_wick_pct=htf_upper_wick_pct,
            htf_lower_wick_pct=htf_lower_wick_pct,
            htf_close_position=htf_close_position,
        )
    
    def _compute_open_bias(self, current_price: float, htf_open: float) -> str:
        """
        Compute directional bias relative to HTF open.
        
        Args:
            current_price: Current market price
            htf_open: HTF candle open price
            
        Returns:
            "BULLISH" if price > htf_open, "BEARISH" if price < htf_open, "NEUTRAL" if equal
        """
        tolerance = 1e-6
        
        if current_price > htf_open + tolerance:
            return "BULLISH"
        elif current_price < htf_open - tolerance:
            return "BEARISH"
        else:
            return "NEUTRAL"
    
    def _compute_proximity_percentages(
        self, current_price: float, htf_high: float, htf_low: float
    ) -> tuple[float, float]:
        """
        Compute distance from current price to HTF high and low as percentages.
        
        The proximity percentages indicate how close the current price is to the
        HTF high and low boundaries. When price is within the HTF range, the two
        percentages sum to 100.
        
        Args:
            current_price: Current market price
            htf_high: HTF candle high price
            htf_low: HTF candle low price
            
        Returns:
            Tuple of (htf_high_proximity_pct, htf_low_proximity_pct)
            
        Example:
            If HTF range is 1.4900-1.5100 (200 pips) and current price is 1.5050:
            - htf_low_proximity_pct = 75% (150 pips from low)
            - htf_high_proximity_pct = 25% (50 pips from high)
            
        Note:
            When price is outside range, percentages may exceed 100 or be negative.
        """
        htf_range = htf_high - htf_low
        
        if htf_range == 0:
            # Degenerate case: high == low (single price point)
            return 50.0, 50.0
        
        # Distance from low to current price as percentage of range
        htf_low_proximity_pct = ((current_price - htf_low) / htf_range) * 100.0
        
        # Distance from current price to high as percentage of range
        htf_high_proximity_pct = ((htf_high - current_price) / htf_range) * 100.0
        
        return htf_high_proximity_pct, htf_low_proximity_pct
    
    def _compute_body_and_wick_percentages(
        self, htf_open: float, htf_high: float, htf_low: float, htf_close: float
    ) -> tuple[float, float, float]:
        """
        Compute HTF candle body size and wick percentages.
        
        The body represents the distance between open and close, while wicks
        represent the rejection zones above and below the body.
        
        Args:
            htf_open: HTF candle open price
            htf_high: HTF candle high price
            htf_low: HTF candle low price
            htf_close: HTF candle close price
            
        Returns:
            Tuple of (htf_body_pct, htf_upper_wick_pct, htf_lower_wick_pct)
            
        Example:
            For a bullish candle: open=1.5000, high=1.5100, low=1.4900, close=1.5080
            - Range = 200 pips
            - Body = 80 pips (40%)
            - Upper wick = 20 pips (10%)
            - Lower wick = 100 pips (50%)
            
        Note:
            The three percentages always sum to 100.
        """
        htf_range = htf_high - htf_low
        
        if htf_range == 0:
            # Degenerate case: high == low (single price point)
            return 0.0, 0.0, 0.0
        
        # Body size (absolute difference between open and close)
        body_size = abs(htf_close - htf_open)
        
        # Upper wick (from max(open, close) to high)
        upper_wick_size = htf_high - max(htf_open, htf_close)
        
        # Lower wick (from low to min(open, close))
        lower_wick_size = min(htf_open, htf_close) - htf_low
        
        # Convert to percentages
        htf_body_pct = (body_size / htf_range) * 100.0
        htf_upper_wick_pct = (upper_wick_size / htf_range) * 100.0
        htf_lower_wick_pct = (lower_wick_size / htf_range) * 100.0
        
        return htf_body_pct, htf_upper_wick_pct, htf_lower_wick_pct
    
    def _compute_close_position(
        self, htf_close: float, htf_high: float, htf_low: float
    ) -> float:
        """
        Compute HTF close position within range (0-100).
        
        Args:
            htf_close: HTF candle close price
            htf_high: HTF candle high price
            htf_low: HTF candle low price
            
        Returns:
            Close position as percentage (0 = at low, 100 = at high)
        """
        htf_range = htf_high - htf_low
        
        if htf_range == 0:
            # Degenerate case: high == low (single price point)
            return 50.0
        
        close_position = ((htf_close - htf_low) / htf_range) * 100.0
        
        return close_position
