"""
Timeframe analysis module.
"""
import numpy as np
from typing import Dict, List, Union, Any
from datetime import datetime, timedelta

class TimeframeAnalyzer:
    """Analyzes multiple timeframes for market structure."""
    
    def __init__(self):
        self.timeframes = ['M1', 'M5', 'M15', 'H1', 'H4', 'D1']
        self.timeframe_minutes = {
            'M1': 1,
            'M5': 5,
            'M15': 15,
            'H1': 60,
            'H4': 240,
            'D1': 1440
        }
        
    def convert_timeframe(self, data: np.ndarray, from_tf: str, to_tf: str) -> np.ndarray:
        """
        Convert candle data from one timeframe to another.
        
        Args:
            data: Array of [timestamp, open, high, low, close, volume] data
            from_tf: Source timeframe (e.g., 'M1')
            to_tf: Target timeframe (e.g., 'M5')
        
        Returns:
            array: Converted candle data
        """
        if from_tf not in self.timeframe_minutes or to_tf not in self.timeframe_minutes:
            raise ValueError(f"Invalid timeframe: {from_tf} or {to_tf}")
            
        ratio = self.timeframe_minutes[to_tf] // self.timeframe_minutes[from_tf]
        if ratio <= 0:
            raise ValueError(f"Cannot convert from {from_tf} to {to_tf}")
            
        # Calculate number of output candles
        n_candles = len(data) // ratio
        result = []
        
        for i in range(n_candles):
            idx = i * ratio
            chunk = data[idx:idx + ratio]
            
            # Create new candle
            new_candle = [
                chunk[0, 0],  # First timestamp
                chunk[0, 1],  # Open price
                np.max(chunk[:, 2]),  # High price
                np.min(chunk[:, 3]),  # Low price
                chunk[-1, 4],  # Close price
                np.sum(chunk[:, 5])  # Volume
            ]
            result.append(new_candle)
            
        return np.array(result, dtype=object)

            
        return result
        
    def align_timeframes(self, data: np.ndarray, timeframes: List[str]) -> Dict[str, np.ndarray]:
        """
        Align candle data across multiple timeframes.
        
        Args:
            data: Base timeframe candle data
            timeframes: List of timeframes to align
            
        Returns:
            dict: Aligned candle data for each timeframe
        """
        result = {}
        base_tf = 'M1'  # Assume input data is M1
        
        for tf in timeframes:
            if tf == base_tf:
                result[tf] = data
            else:
                result[tf] = self.convert_timeframe(data, base_tf, tf)
                
        return result
        
    def find_dominant_timeframe(self, data: np.ndarray) -> Dict[str, Any]:
        """
        Find the dominant timeframe based on price action.
        
        Args:
            data: Candle data to analyze
            
        Returns:
            dict: Dominant timeframe information
        """
        volatilities = {}
        base_data = np.array([d[1:] for d in data])  # Remove datetime column
        base_vol = np.std(base_data[:, 3] - base_data[:, 0])  # Close - Open volatility
        
        # Check volatility ratio in different timeframes
        for tf in self.timeframes:
            if tf == 'M1':
                volatilities[tf] = base_vol
            else:
                converted = self.convert_timeframe(data, 'M1', tf)
                conv_data = np.array([d[1:] for d in converted])  # Remove datetime column
                volatilities[tf] = np.std(conv_data[:, 3] - conv_data[:, 0])
                
        # Find timeframe with highest relative volatility
        max_tf = max(volatilities.items(), key=lambda x: x[1])[0]
        strength = volatilities[max_tf] / sum(volatilities.values())
        
        return {
            "timeframe": max_tf,
            "strength": strength,
            "volatilities": volatilities
        }
