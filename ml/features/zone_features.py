"""
Zone and structure feature extractor.

This module implements the ZoneFeatureExtractor which extracts zone and structure features
from candle sequences including:
- BOS (Break of Structure) detection
- CHoCH (Change of Character) detection
- FVG (Fair Value Gap) detection
- Liquidity sweep detection
- Swing high/low distance computation
- HTF trend bias derivation from HTF candle direction (not EMA)

**Implements: Requirements FR-3**

Example usage:
    >>> from ml.features.zone_features import ZoneFeatureExtractor
    >>> extractor = ZoneFeatureExtractor()
    >>> candles = [
    ...     {"open": 1.5000, "high": 1.5100, "low": 1.4950, "close": 1.5080},
    ...     {"open": 1.5080, "high": 1.5090, "low": 1.5020, "close": 1.5030},
    ...     {"open": 1.5030, "high": 1.5150, "low": 1.5020, "close": 1.5140},
    ... ]
    >>> htf_candle = {"open": 1.5000, "high": 1.5200, "low": 1.4900, "close": 1.5180}
    >>> features = extractor.extract(candles, htf_candle=htf_candle)
    >>> features.bos_detected
    True
    >>> features.htf_trend_bias
    'BULLISH'
"""

from dataclasses import dataclass
from typing import List, Dict, Any, Optional


@dataclass
class ZoneFeatures:
    """
    Zone and structure features data structure.
    
    Contains all zone and structure features extracted from a candle sequence.
    
    Attributes:
        bos_detected: True if Break of Structure detected, False otherwise
        choch_detected: True if Change of Character detected, False otherwise
        fvg_present: True if Fair Value Gap present, False otherwise
        liquidity_sweep: True if liquidity sweep detected, False otherwise
        swing_high_distance: Distance from current price to last swing high (pips)
        swing_low_distance: Distance from current price to last swing low (pips)
        htf_trend_bias: HTF trend bias derived from HTF candle direction (BULLISH/BEARISH/NEUTRAL)
    """
    bos_detected: bool
    choch_detected: bool
    fvg_present: bool
    liquidity_sweep: bool
    swing_high_distance: float
    swing_low_distance: float
    htf_trend_bias: str


class ZoneFeatureExtractor:
    """
    Zone and structure feature extractor.
    
    Extracts zone and structure features from candle sequences for pattern recognition
    and confluence scoring. Migrates logic from backend/trader/agents/power_of_3.py
    and backend/trader/analysis/pdarray.py.
    
    **Implements: Requirements FR-3**
    """
    
    def __init__(self):
        """Initialize the zone feature extractor."""
        pass
    
    def extract(
        self,
        candles: List[Dict[str, Any]],
        htf_candle: Optional[Dict[str, Any]] = None,
    ) -> ZoneFeatures:
        """
        Extract zone and structure features from candle sequence.
        
        Args:
            candles: List of candle dictionaries with OHLC data (chronological order)
            htf_candle: Optional HTF candle dictionary for trend bias derivation
                
        Returns:
            ZoneFeatures dataclass with all computed features
            
        Raises:
            ValueError: If candles list is empty or invalid
            
        **Validates: Requirements FR-3**
        """
        if not candles:
            raise ValueError("candles list cannot be empty")
        
        # Detect BOS (Break of Structure)
        bos_detected = self._detect_bos(candles)
        
        # Detect CHoCH (Change of Character)
        choch_detected = self._detect_choch(candles)
        
        # Detect FVG (Fair Value Gap)
        fvg_present = self._detect_fvg(candles)
        
        # Detect liquidity sweep
        liquidity_sweep = self._detect_liquidity_sweep(candles)
        
        # Compute swing high/low distances
        swing_high_distance = self._compute_swing_high_distance(candles)
        swing_low_distance = self._compute_swing_low_distance(candles)
        
        # Derive HTF trend bias from HTF candle direction (not EMA)
        htf_trend_bias = self._derive_htf_trend_bias(htf_candle) if htf_candle else "NEUTRAL"
        
        return ZoneFeatures(
            bos_detected=bos_detected,
            choch_detected=choch_detected,
            fvg_present=fvg_present,
            liquidity_sweep=liquidity_sweep,
            swing_high_distance=swing_high_distance,
            swing_low_distance=swing_low_distance,
            htf_trend_bias=htf_trend_bias,
        )
    
    def _detect_bos(self, candles: List[Dict[str, Any]]) -> bool:
        """
        Detect Break of Structure (BOS).
        
        BOS occurs when price closes beyond the last swing high (bullish BOS)
        or below the last swing low (bearish BOS). This indicates a continuation
        of the current trend.
        
        Args:
            candles: List of candle dictionaries
            
        Returns:
            True if BOS detected, False otherwise
        """
        if len(candles) < 3:
            return False
        
        # Find swing highs and lows
        swing_high = self._find_last_swing_high(candles[:-1])
        swing_low = self._find_last_swing_low(candles[:-1])
        
        # Get current candle close
        current_close = float(candles[-1]["close"])
        
        # Check for bullish BOS (close breaks above swing high)
        if swing_high is not None and current_close > swing_high:
            return True
        
        # Check for bearish BOS (close breaks below swing low)
        if swing_low is not None and current_close < swing_low:
            return True
        
        return False
    
    def _detect_choch(self, candles: List[Dict[str, Any]]) -> bool:
        """
        Detect Change of Character (CHoCH).
        
        CHoCH occurs when BOS happens in the opposite direction of the previous BOS.
        
        Args:
            candles: List of candle dictionaries
            
        Returns:
            True if CHoCH detected, False otherwise
        """
        if len(candles) < 6:
            return False
        
        # Track all BOS events
        bos_events = []
        
        # Track the highest high and lowest low seen so far
        highest_high = float(candles[0]["high"])
        lowest_low = float(candles[0]["low"])
        
        for i in range(1, len(candles)):
            current_close = float(candles[i]["close"])
            current_high = float(candles[i]["high"])
            current_low = float(candles[i]["low"])
            
            # Check for bullish BOS (close breaks above previous highest high)
            if current_close > highest_high:
                # Record bullish BOS if it's different from last event
                if not bos_events or bos_events[-1] != "BULLISH":
                    bos_events.append("BULLISH")
            
            # Check for bearish BOS (close breaks below previous lowest low)
            if current_close < lowest_low:
                # Record bearish BOS if it's different from last event
                if not bos_events or bos_events[-1] != "BEARISH":
                    bos_events.append("BEARISH")
            
            # Update highest high and lowest low
            highest_high = max(highest_high, current_high)
            lowest_low = min(lowest_low, current_low)
        
        # CHoCH detected if we have at least 2 BOS events in opposite directions
        if len(bos_events) >= 2:
            for i in range(1, len(bos_events)):
                if bos_events[i] != bos_events[i - 1]:
                    return True
        
        return False
    
    def _detect_fvg(self, candles: List[Dict[str, Any]]) -> bool:
        """
        Detect Fair Value Gap (FVG).
        
        FVG occurs when there's a gap between candle[i-2].high and candle[i].low
        (bullish FVG) or between candle[i-2].low and candle[i].high (bearish FVG).
        This represents an imbalance that price may return to fill.
        
        Args:
            candles: List of candle dictionaries
            
        Returns:
            True if FVG present, False otherwise
        """
        if len(candles) < 3:
            return False
        
        # Check last 3 candles for FVG
        candle_i_minus_2 = candles[-3]
        candle_i = candles[-1]
        
        high_i_minus_2 = float(candle_i_minus_2["high"])
        low_i_minus_2 = float(candle_i_minus_2["low"])
        high_i = float(candle_i["high"])
        low_i = float(candle_i["low"])
        
        # Bullish FVG: gap between candle[i-2].high and candle[i].low
        if low_i > high_i_minus_2:
            return True
        
        # Bearish FVG: gap between candle[i-2].low and candle[i].high
        if high_i < low_i_minus_2:
            return True
        
        return False
    
    def _detect_liquidity_sweep(self, candles: List[Dict[str, Any]]) -> bool:
        """
        Detect liquidity sweep.
        
        Liquidity sweep occurs when wick exceeds swing high/low but close
        is back inside the range (false breakout). This indicates stop-loss
        hunting before the true move.
        
        Args:
            candles: List of candle dictionaries
            
        Returns:
            True if liquidity sweep detected, False otherwise
        """
        if len(candles) < 3:
            return False
        
        # Find swing highs and lows
        swing_high = self._find_last_swing_high(candles[:-1])
        swing_low = self._find_last_swing_low(candles[:-1])
        
        # Get current candle
        current_candle = candles[-1]
        current_high = float(current_candle["high"])
        current_low = float(current_candle["low"])
        current_close = float(current_candle["close"])
        
        # Check for bullish liquidity sweep (wick exceeds swing high, close below)
        if swing_high is not None:
            if current_high > swing_high and current_close < swing_high:
                return True
        
        # Check for bearish liquidity sweep (wick exceeds swing low, close above)
        if swing_low is not None:
            if current_low < swing_low and current_close > swing_low:
                return True
        
        return False
    
    def _compute_swing_high_distance(self, candles: List[Dict[str, Any]]) -> float:
        """
        Compute distance from current price to last swing high.
        
        Args:
            candles: List of candle dictionaries
            
        Returns:
            Distance in price units (pips)
        """
        if len(candles) < 2:
            return 0.0
        
        swing_high = self._find_last_swing_high(candles)
        current_close = float(candles[-1]["close"])
        
        if swing_high is None:
            return 0.0
        
        return swing_high - current_close
    
    def _compute_swing_low_distance(self, candles: List[Dict[str, Any]]) -> float:
        """
        Compute distance from current price to last swing low.
        
        Args:
            candles: List of candle dictionaries
            
        Returns:
            Distance in price units (pips)
        """
        if len(candles) < 2:
            return 0.0
        
        swing_low = self._find_last_swing_low(candles)
        current_close = float(candles[-1]["close"])
        
        if swing_low is None:
            return 0.0
        
        return current_close - swing_low
    
    def _derive_htf_trend_bias(self, htf_candle: Dict[str, Any]) -> str:
        """
        Derive HTF trend bias from HTF candle direction (not EMA).
        
        The HTF trend bias is determined solely by the HTF candle's direction,
        following the principle that trend is defined by candle structure, not indicators.
        
        Args:
            htf_candle: HTF candle dictionary with OHLC data
            
        Returns:
            "BULLISH" if HTF candle is bullish (close > open),
            "BEARISH" if HTF candle is bearish (close < open),
            "NEUTRAL" if HTF candle is doji (close == open)
        """
        htf_open = float(htf_candle["open"])
        htf_close = float(htf_candle["close"])
        
        tolerance = 1e-6
        
        if htf_close > htf_open + tolerance:
            return "BULLISH"
        elif htf_close < htf_open - tolerance:
            return "BEARISH"
        else:
            return "NEUTRAL"
    
    def _find_last_swing_high(self, candles: List[Dict[str, Any]]) -> Optional[float]:
        """
        Find the last swing high in the candle sequence.
        
        A swing high is a candle whose high is higher than the highs of
        the candles immediately before and after it.
        
        Args:
            candles: List of candle dictionaries
            
        Returns:
            Last swing high price, or None if not found
        """
        if len(candles) < 3:
            # Not enough candles to identify swing high
            # Return the highest high as fallback
            if candles:
                return max(float(c["high"]) for c in candles)
            return None
        
        # Search backwards for swing high
        for i in range(len(candles) - 2, 0, -1):
            current_high = float(candles[i]["high"])
            prev_high = float(candles[i - 1]["high"])
            next_high = float(candles[i + 1]["high"])
            
            # Swing high: current high > both neighbors
            if current_high > prev_high and current_high > next_high:
                return current_high
        
        # Fallback: return highest high
        return max(float(c["high"]) for c in candles)
    
    def _find_last_swing_low(self, candles: List[Dict[str, Any]]) -> Optional[float]:
        """
        Find the last swing low in the candle sequence.
        
        A swing low is a candle whose low is lower than the lows of
        the candles immediately before and after it.
        
        Args:
            candles: List of candle dictionaries
            
        Returns:
            Last swing low price, or None if not found
        """
        if len(candles) < 3:
            # Not enough candles to identify swing low
            # Return the lowest low as fallback
            if candles:
                return min(float(c["low"]) for c in candles)
            return None
        
        # Search backwards for swing low
        for i in range(len(candles) - 2, 0, -1):
            current_low = float(candles[i]["low"])
            prev_low = float(candles[i - 1]["low"])
            next_low = float(candles[i + 1]["low"])
            
            # Swing low: current low < both neighbors
            if current_low < prev_low and current_low < next_low:
                return current_low
        
        # Fallback: return lowest low
        return min(float(c["low"]) for c in candles)
