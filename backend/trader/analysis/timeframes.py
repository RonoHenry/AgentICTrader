"""
Timeframe analysis module.
Handles multi-timeframe data organization and analysis.
"""
import numpy as np
from typing import Dict, List, Union, Any, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass

@dataclass
class TimeframeConfig:
    """Configuration for a timeframe."""
    name: str
    minutes: int
    candles_to_keep: int
    typical_volume: float
    typical_volatility: float

class TimeframeAnalyzer:
    """Analyzes and organizes multiple timeframes for market structure."""
    
    def __init__(self):
        # Define timeframe configurations with retention and characteristics
        self.timeframe_configs = {
            'M1': TimeframeConfig('M1', 1, 10080, 100, 0.0001),      # 1 week of M1 data
            'M5': TimeframeConfig('M5', 5, 4032, 500, 0.0002),       # 2 weeks of M5 data
            'M15': TimeframeConfig('M15', 15, 2880, 1500, 0.0003),   # 1 month of M15 data
            'H1': TimeframeConfig('H1', 60, 2160, 6000, 0.0005),     # 3 months of H1 data
            'H4': TimeframeConfig('H4', 240, 1080, 24000, 0.0008),   # 6 months of H4 data
            'D1': TimeframeConfig('D1', 1440, 365, 100000, 0.0012)   # 1 year of D1 data
        }
        
        self.timeframes = list(self.timeframe_configs.keys())
        self.timeframe_minutes = {tf: cfg.minutes for tf, cfg in self.timeframe_configs.items()}
        
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
            
        # Ensure data is a numpy array and has the right shape
        data = np.array(data)
        if len(data.shape) != 2:
            data = data.reshape(-1, 6)  # timestamp, open, high, low, close, volume
            
        # Process data in chunks of the target timeframe size
        result = []
        remaining = len(data)
        start_idx = 0
        
        while remaining >= ratio:  # Need at least one complete candle worth of data
            chunk = data[start_idx:start_idx + ratio]
            
            if len(chunk) >= ratio:  # Only create candle if we have enough data
                try:
                    new_candle = [
                        chunk[0, 0],  # First timestamp
                        chunk[0, 1],  # Open price
                        np.max(chunk[:, 2]),  # High price
                        np.min(chunk[:, 3]),  # Low price
                        chunk[-1, 4],  # Close price
                        np.sum(chunk[:, 5])  # Volume
                    ]
                    result.append(new_candle)
                except Exception as e:
                    print(f"Error processing chunk: {e}")
                    print(f"Chunk shape: {chunk.shape}, data:\n{chunk}")
                    break
                    
            start_idx += ratio
            remaining = len(data) - start_idx
            
        if not result:
            # Create at least one candle from available data if possible
            if len(data) > 0:
                try:
                    new_candle = [
                        data[0, 0],  # First timestamp
                        data[0, 1],  # Open price
                        np.max(data[:, 2]),  # High price
                        np.min(data[:, 3]),  # Low price
                        data[-1, 4],  # Close price
                        np.sum(data[:, 5])  # Volume
                    ]
                    result.append(new_candle)
                except Exception as e:
                    print(f"Error processing partial data: {e}")
                    raise ValueError("Could not create candle from available data")
            else:
                raise ValueError("No data available to create candles")
            
        return np.array(result, dtype=object)
        
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
        
        # Convert input to numpy array if it isn't already
        data = np.array(data)
        
        # If data is 1D, reshape it to 2D
        if len(data.shape) == 1:
            data = data.reshape(1, -1)
            
        # Get OHLC columns
        base_ohlc = data[:, 1:5]  # Columns 1-4 are OHLC
        base_ohlc = base_ohlc.astype(float)
        
        # Calculate base timeframe volatility
        base_vol = np.std(base_ohlc[:, 3] - base_ohlc[:, 0])  # Close - Open volatility
        
        # Calculate volatilities for different timeframes
        for tf in self.timeframes:
            if tf == 'M1':
                volatilities[tf] = base_vol
            else:
                try:
                    converted = self.convert_timeframe(data, 'M1', tf)
                    if len(converted) > 0:
                        converted_ohlc = np.array(converted)[:, 1:5].astype(float)
                        volatilities[tf] = np.std(converted_ohlc[:, 3] - converted_ohlc[:, 0])
                    else:
                        volatilities[tf] = 0
                except Exception as e:
                    print(f"Error calculating volatility for {tf}: {e}")
                    volatilities[tf] = 0
                
        # Find timeframe with highest relative volatility
        max_tf = max(volatilities.items(), key=lambda x: x[1])[0]
        total_vol = sum(volatilities.values())
        strength = volatilities[max_tf] / total_vol if total_vol > 0 else 0
        
        return {
            "timeframe": max_tf,
            "strength": strength,
            "volatilities": volatilities
        }
