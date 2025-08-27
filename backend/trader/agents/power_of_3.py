from dataclasses import dataclass
from datetime import datetime
from typing import List, Dict, Union, Optional, Tuple
import numpy as np

@dataclass
class Candle:
    """Represents a single candlestick with PO3 context"""
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    
    @property
    def is_bullish(self) -> bool:
        """Check if candle is bullish (closed above open)"""
        return self.close > self.open
    
    @property
    def is_bearish(self) -> bool:
        """Check if candle is bearish (closed below open)"""
        return self.close < self.open
    
    @property
    def body_size(self) -> float:
        """Calculate the size of candle body"""
        return abs(self.close - self.open)
    
    @property
    def upper_wick(self) -> float:
        """Calculate upper wick length"""
        return self.high - (self.close if self.is_bullish else self.open)
    
    @property
    def lower_wick(self) -> float:
        """Calculate lower wick length"""
        return (self.open if self.is_bullish else self.close) - self.low
    
    @property
    def total_range(self) -> float:
        """Calculate total candle range"""
        return self.high - self.low
    
    def relationship_to_open(self) -> str:
        """Determine candle's relationship to its opening price"""
        if self.low < self.open and self.high > self.open:
            return "straddling"
        elif self.low >= self.open:
            return "above_open"
        else:
            return "below_open"

class PowerOfThreeAnalyzer:
    def __init__(self):
        self.current_phase = None
        self.phase_characteristics = {
            "direction": None,
            "volatility": None,
            "strength": 0.0
        }
    
    def _convert_to_candles(self, np_candles: np.ndarray) -> List[Candle]:
        """Convert numpy array of OHLC data to list of Candle objects"""
        candles = []
        for i in range(len(np_candles)):
            candle = Candle(
                timestamp=datetime.fromtimestamp(np_candles[i][0]) if np_candles.shape[1] > 4 else None,
                open=float(np_candles[i][0] if np_candles.shape[1] == 4 else np_candles[i][1]),
                high=float(np_candles[i][1] if np_candles.shape[1] == 4 else np_candles[i][2]),
                low=float(np_candles[i][2] if np_candles.shape[1] == 4 else np_candles[i][3]),
                close=float(np_candles[i][3] if np_candles.shape[1] == 4 else np_candles[i][4])
            )
            candles.append(candle)
        return candles
        
    def detect_phase(self, np_candles: np.ndarray) -> str:
        """Detect current market phase based on PO3 pattern"""
        candles = self._convert_to_candles(np_candles)
        if len(candles) < 3:
            return None
            
        # Use last 5 candles for analysis
        recent_candles = candles[-5:] if len(candles) >= 5 else candles
        initial_open = recent_candles[0].open
        
        # Calculate price relationships
        above_open = [c.close > initial_open for c in recent_candles]
        below_open = [c.close < initial_open for c in recent_candles]
        range_sizes = [c.total_range for c in recent_candles]
        avg_range = sum(range_sizes) / len(range_sizes)
        
        # Detect Accumulation
        if all(c.total_range < avg_range * 1.2 for c in recent_candles[-3:]):
            self.current_phase = "accumulation"
            self.phase_characteristics["volatility"] = "low"
            # Determine bias based on position relative to open
            if sum(below_open) > sum(above_open):
                self.phase_characteristics["bias"] = "bullish"  # Accumulating below open
            else:
                self.phase_characteristics["bias"] = "bearish"  # Accumulating above open
                
        # Detect Manipulation
        elif max(range_sizes[-2:]) > avg_range * 1.5:
            self.current_phase = "manipulation"
            if all(c.close < initial_open for c in recent_candles[-2:]):
                self.phase_characteristics["direction"] = "bearish"  # Moving down
                self.phase_characteristics["true_bias"] = "bullish"  # Will reverse up
            else:
                self.phase_characteristics["direction"] = "bullish"  # Moving up
                self.phase_characteristics["true_bias"] = "bearish"  # Will reverse down
                
        # Detect Distribution
        elif len(recent_candles) >= 3:
            last_candles = recent_candles[-3:]
            if self.phase_characteristics.get("true_bias") == "bullish" and all(c.close > c.open for c in last_candles):
                self.current_phase = "distribution"
                self.phase_characteristics["direction"] = "bullish"
            elif self.phase_characteristics.get("true_bias") == "bearish" and all(c.close < c.open for c in last_candles):
                self.current_phase = "distribution"
                self.phase_characteristics["direction"] = "bearish"
            
        return self.current_phase
    
    def get_phase_characteristics(self) -> Dict[str, Union[str, float]]:
        """Return characteristics of current phase"""
        return self.phase_characteristics
    
    def is_false_move(self) -> bool:
        """Check if current phase is manipulation (false move)"""
        return self.current_phase == "manipulation"
    
    def is_true_move(self) -> bool:
        """Check if current phase is distribution (true move)"""
        return self.current_phase == "distribution"
    
    def analyze_sequence(self, np_candles: np.ndarray) -> List[Dict[str, Union[str, int, float, bool]]]:
        """Analyze complete PO3 sequence"""
        candles = self._convert_to_candles(np_candles)
        sequence = []
        
        # Minimum 3 candles needed for each phase
        if len(candles) < 9:  # 3 candles × 3 phases
            return sequence
            
        # TODO: Implement sequence analysis logic
        return sequence
    
    def calculate_entry_points(self, np_candles: np.ndarray) -> Dict[str, float]:
        """Calculate entry points based on PO3 analysis"""
        candles = self._convert_to_candles(np_candles)
        if len(candles) < 5:
            return {
                "primary_entry": None,
                "secondary_entry": None,
                "stop_loss": None,
                "target": None
            }
            
        # Get recent price action
        recent_candles = candles[-5:]
        initial_open = recent_candles[0].open
        
        # Identify pattern bias
        pattern_bias = self.phase_characteristics.get("true_bias")
        if not pattern_bias:
            pattern_bias = self.phase_characteristics.get("bias")
            
        entry_points = {}
        
        if pattern_bias == "bullish":
            # For bullish setups
            lowest_low = min(c.low for c in recent_candles)
            manipulation_low = recent_candles[-2].low  # Assuming last manipulation low
            
            entry_points = {
                "primary_entry": manipulation_low + (initial_open - manipulation_low) * 0.382,  # First entry above manipulation
                "secondary_entry": manipulation_low + (initial_open - manipulation_low) * 0.618,  # Second entry if first missed
                "stop_loss": lowest_low - (recent_candles[-1].high - recent_candles[-1].low) * 0.1,  # Below manipulation low
                "target": initial_open + (initial_open - lowest_low)  # Projection of range
            }
            
        elif pattern_bias == "bearish":
            # For bearish setups
            highest_high = max(c.high for c in recent_candles)
            manipulation_high = recent_candles[-2].high  # Assuming last manipulation high
            
            entry_points = {
                "primary_entry": manipulation_high - (manipulation_high - initial_open) * 0.382,  # First entry below manipulation
                "secondary_entry": manipulation_high - (manipulation_high - initial_open) * 0.618,  # Second entry if first missed
                "stop_loss": highest_high + (recent_candles[-1].high - recent_candles[-1].low) * 0.1,  # Above manipulation high
                "target": initial_open - (highest_high - initial_open)  # Projection of range
            }
            
        return entry_points
