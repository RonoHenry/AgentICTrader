"""
PD Array analysis module for identifying Bullish and Bearish PD Arrays.

PD Arrays (Premium/Discount Arrays) are the correct ICT terminology:
  - Bearish Arrays at Premium of Dealing Range: Bearish OB, FVG, Breaker, IFVG
    (commonly and incorrectly called "supply zones")
  - Bullish Arrays at Discount of Dealing Range: Bullish OB, FVG, Breaker, IFVG
    (commonly and incorrectly called "demand zones")

Supply and Demand zones do not exist as concepts in ICT methodology.
"""
import numpy as np
from typing import Dict, Any, Union

class PDArrayAnalyzer:
    """
    Bullish and Bearish PD Array detection using premium/discount analysis.

    Bearish Arrays (at Premium) = what is commonly called "supply zones"
    Bullish Arrays (at Discount) = what is commonly called "demand zones"
    """
    
    def __init__(self):
        self.cache = {}
        
    def detect_premium_zone(self, candles: np.ndarray) -> Dict[str, Any]:
        """
        Detect premium zone formation.
        
        Args:
            candles: numpy array of shape (n, 4) with columns [open, high, low, close]
            
        Returns:
            dict: Premium zone information
        """
        if len(candles) >= 3:
            highs = candles[:, 1]
            higher_highs = all(highs[i] > highs[i-1] for i in range(1, len(highs)))
            
            if higher_highs:
                return {
                    "present": True,
                    "strength": 0.85,
                    "upper_bound": np.max(highs),
                    "lower_bound": np.min(highs[-2:])  # Last two highs
                }
                
        return {
            "present": False,
            "strength": 0.0,
            "upper_bound": 0,
            "lower_bound": 0
        }
        
    def detect_discount_zone(self, candles: np.ndarray) -> Dict[str, Any]:
        """
        Detect discount zone formation.
        
        Args:
            candles: numpy array of shape (n, 4) with columns [open, high, low, close]
            
        Returns:
            dict: Discount zone information
        """
        if len(candles) >= 3:
            lows = candles[:, 2]
            lower_lows = all(lows[i] < lows[i-1] for i in range(1, len(lows)))
            
            if lower_lows:
                return {
                    "present": True,
                    "strength": 0.85,
                    "upper_bound": np.max(lows[-2:]),  # Last two lows
                    "lower_bound": np.min(lows)
                }
                
        return {
            "present": False,
            "strength": 0.0,
            "upper_bound": 0,
            "lower_bound": 0
        }
        
    def calculate_zone_strength(self, zone: Dict[str, Any], candles: np.ndarray) -> float:
        """
        Calculate the strength of a given PD Array (Bullish or Bearish).

        Args:
            zone: Zone information including type ("premium" for Bearish Array,
                  "discount" for Bullish Array) and boundaries
            candles: Historical candle data

        Returns:
            float: Zone strength value between 0 and 1
        """
        touches = 0
        total_reactions = 0
        
        for candle in candles:
            high, low = candle[1], candle[2]
            
            # Check if price interacts with the zone
            if zone["lower_bound"] <= high <= zone["upper_bound"] or \
               zone["lower_bound"] <= low <= zone["upper_bound"]:
                touches += 1
                # Check if price respects the zone boundaries
                if (zone["type"] == "premium" and low < zone["lower_bound"]) or \
                   (zone["type"] == "discount" and high > zone["upper_bound"]):
                    total_reactions += 1
                    
        return total_reactions / max(touches, 1)
        
    def correlate_timeframes(self, timeframe_data: Dict[str, np.ndarray]) -> Dict[str, Any]:
        """
        Analyze correlation between different timeframe analyses.
        
        Args:
            timeframe_data: Dict mapping timeframe names to candle data
            
        Returns:
            dict: Correlation analysis results
        """
        zones = {}
        for tf, candles in timeframe_data.items():
            prem = self.detect_premium_zone(candles)
            disc = self.detect_discount_zone(candles)
            zones[tf] = {"premium": prem, "discount": disc}
            
        # Calculate alignment score
        alignments = []
        for tf1 in timeframe_data.keys():
            for tf2 in timeframe_data.keys():
                if tf1 < tf2:  # Compare each pair once
                    if zones[tf1]["premium"]["present"] and zones[tf2]["premium"]["present"]:
                        overlap = min(
                            abs(zones[tf1]["premium"]["upper_bound"] - zones[tf2]["premium"]["upper_bound"]),
                            abs(zones[tf1]["premium"]["lower_bound"] - zones[tf2]["premium"]["lower_bound"])
                        )
                        alignments.append(1 - (overlap / max(
                            zones[tf1]["premium"]["upper_bound"] - zones[tf1]["premium"]["lower_bound"],
                            1e-6
                        )))
                        
        correlation_score = np.mean(alignments) if alignments else 0.0
        
        return {
            "correlation_score": correlation_score,
            "aligned_zones": zones
        }
