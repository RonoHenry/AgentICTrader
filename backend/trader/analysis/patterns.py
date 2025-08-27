"""
Candle pattern analysis module.
"""
import numpy as np
from typing import Dict, Any, List, Union

class CandlePatternAnalyzer:
    """Analyzes candlestick patterns for trading signals."""
    
    def __init__(self):
        self.patterns = {}
        
    def detect_pattern(self, candles: np.ndarray) -> Dict[str, Any]:
        """
        Detect patterns in a series of candles.
        
        Args:
            candles: numpy array of shape (n, 4) with columns [open, high, low, close]
            
        Returns:
            dict: Pattern information including type and confidence
        """
        if len(candles) >= 3:
            # Check for manipulation first
            moves = candles[1:, 3] - candles[:-1, 3]  # Close price changes
            mean_range = np.mean(candles[:, 1] - candles[:, 2])  # Average candle range
            
            if len(moves) >= 2 and all(x > 0 for x in moves) and np.mean(moves) > mean_range * 0.5:
                return {
                    "type": "manipulation",
                    "direction": "bullish",
                    "confidence": 0.85,
                    "details": "Strong directional moves"
                }
            
            # Check for accumulation
            price_range = candles[:, 1] - candles[:, 2]  # high - low
            if all(abs(x - mean_range) < mean_range * 0.3 for x in price_range):
                return {
                    "type": "accumulation",
                    "confidence": 0.75,
                    "details": "Price ranging with consistent volatility"
                }
                
        return {
            "type": "unknown",
            "confidence": 0.0,
            "details": "No clear pattern detected"
        }
        
    def detect_fvg(self, candles: np.ndarray) -> Dict[str, Union[bool, float]]:
        """
        Detect Fair Value Gaps in price action.
        
        Args:
            candles: numpy array of shape (n, 4) with columns [open, high, low, close]
            
        Returns:
            dict: FVG information including presence and levels
        """
        if len(candles) >= 2:
            current_low = candles[-1, 2]  # Current candle low
            prev_high = candles[-2, 1]    # Previous candle high
            
            if current_low > prev_high:
                return {
                    "present": True,
                    "high": current_low,
                    "low": prev_high,
                    "size": current_low - prev_high
                }
        
        return {
            "present": False,
            "high": 0,
            "low": 0,
            "size": 0
        }
        
    def detect_liquidity_pool(self, candles: np.ndarray) -> Dict[str, Any]:
        """
        Detect areas of liquidity pool formation.
        
        Args:
            candles: numpy array of shape (n, 4) with columns [open, high, low, close]
            
        Returns:
            dict: Liquidity pool information
        """
        if len(candles) >= 3:
            lows = candles[:, 2]  # All lows
            min_level = np.min(lows)
            touches = sum(abs(low - min_level) < (np.mean(candles[:, 1] - candles[:, 2]) * 0.2) for low in lows)
            
            if touches >= 2:
                return {
                    "present": True,
                    "type": "buy",
                    "price_level": min_level,
                    "strength": touches / len(candles)
                }
                
        return {
            "present": False,
            "type": None,
            "price_level": 0,
            "strength": 0
        }
