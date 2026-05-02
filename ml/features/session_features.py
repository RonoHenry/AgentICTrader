"""
Session and time feature extractor.

This module implements the TimeWindowClassifier which classifies timestamps into
time windows and extracts session-based features including:
- Time window classification (ASIAN_RANGE, TRUE_DAY_OPEN, LONDON_KILLZONE, etc.)
- Narrative phase derivation (ACCUMULATION, MANIPULATION, EXPANSION, etc.)
- Time window probability weights
- Price position relative to reference opens (daily, weekly, true day)
- Narrative context generation for trade reasoning

**Validates: Requirements FR-3A**
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo


@dataclass
class TimeFeatures:
    """Time-based features for a candle."""
    
    time_window: str
    narrative_phase: str
    time_window_weight: float
    is_killzone: bool
    is_high_probability_window: bool
    price_vs_daily_open: Optional[str] = None
    price_vs_weekly_open: Optional[str] = None
    price_vs_true_day_open: Optional[str] = None


class TimeWindowClassifier:
    """
    Classifies timestamps into time windows and extracts session features.
    
    Based on ICT Killzone methodology - all times in NY/EST timezone (DST-aware):
    - ASIAN_RANGE: 20:00-22:00 NY (EST) — Liquidity building, creates Asian Range
    - TRUE_DAY_OPEN: 00:00-01:00 NY — NY midnight reference
    - LONDON_KILLZONE: 02:00-05:00 NY (EST) — "Engine Room", creates high/low of day
    - LONDON_SILVER_BULLET: 03:00-04:00 NY (EST) — Highest probability London window
    - NY_AM_KILLZONE: 07:00-10:00 NY (EST) — "Decisive Mover", correlates with US data
    - NY_AM_SILVER_BULLET: 10:00-11:00 NY (EST) — Highest probability NY AM window
    - LONDON_CLOSE: 10:00-12:00 NY (EST) — Retracements/reversals as EU squares positions
    - NY_PM_KILLZONE: 13:30-16:00 NY (EST) — Best for indices, secondary expansion
    - NY_PM_SILVER_BULLET: 14:00-15:00 NY (EST) — Highest probability NY PM window
    - NEWS_WINDOW: 08:00-09:00 NY (EST) — US economic data releases (8:30 AM)
    - DAILY_CLOSE: 17:00-18:00 NY — Position squaring before daily candle transition
    - OFF_HOURS: all other times
    """
    
    # Time window weights (probability multipliers)
    WEIGHTS = {
        "LONDON_SILVER_BULLET": 1.0,
        "NY_AM_SILVER_BULLET": 1.0,
        "NY_PM_SILVER_BULLET": 1.0,
        "LONDON_KILLZONE": 0.9,
        "NY_AM_KILLZONE": 0.9,
        "NY_PM_KILLZONE": 0.9,
        "NEWS_WINDOW": 0.8,
        "TRUE_DAY_OPEN": 0.7,
        "LONDON_CLOSE": 0.5,
        "ASIAN_RANGE": 0.3,
        "DAILY_CLOSE": 0.2,
        "OFF_HOURS": 0.1,
    }
    
    # Narrative phase mapping
    NARRATIVE_PHASES = {
        "ASIAN_RANGE": "ACCUMULATION",
        "TRUE_DAY_OPEN": "TRANSITION",
        "LONDON_KILLZONE": "MANIPULATION",
        "LONDON_SILVER_BULLET": "MANIPULATION",
        "NEWS_WINDOW": "EXPANSION",
        "NY_AM_KILLZONE": "EXPANSION",
        "NY_AM_SILVER_BULLET": "EXPANSION",
        "LONDON_CLOSE": "DISTRIBUTION",
        "NY_PM_KILLZONE": "EXPANSION",
        "NY_PM_SILVER_BULLET": "EXPANSION",
        "DAILY_CLOSE": "DISTRIBUTION",
        "OFF_HOURS": "OFF",
    }
    
    def __init__(self):
        """Initialize the TimeWindowClassifier."""
        self.ny_tz = ZoneInfo("America/New_York")
    
    def classify(
        self,
        timestamp_utc: datetime,
        instrument: str,
        current_price: Optional[float] = None,
        daily_open: Optional[float] = None,
        weekly_open: Optional[float] = None,
        true_day_open: Optional[float] = None,
    ) -> TimeFeatures:
        """
        Classify a timestamp into a time window and extract session features.
        
        Args:
            timestamp_utc: UTC timestamp to classify
            instrument: Trading instrument (e.g., "EURUSD", "US500")
            current_price: Current price (optional, for price position features)
            daily_open: Daily open price at 18:00 NY (optional)
            weekly_open: Weekly open price at Sunday 18:00 NY (optional)
            true_day_open: True day open price at 00:00 NY (optional)
        
        Returns:
            TimeFeatures dataclass with all time-based features
        """
        # Convert to NY timezone
        ny_time = timestamp_utc.astimezone(self.ny_tz)
        hour = ny_time.hour
        minute = ny_time.minute
        
        # Determine time window
        time_window = self._classify_time_window(hour, minute, instrument)
        
        # Derive narrative phase
        narrative_phase = self.NARRATIVE_PHASES.get(time_window, "OFF")
        
        # Get time window weight
        time_window_weight = self.WEIGHTS.get(time_window, 0.1)
        
        # Determine if killzone (Silver Bullets are the highest probability killzone windows)
        is_killzone = time_window in {
            "LONDON_KILLZONE", "LONDON_SILVER_BULLET",
            "NY_AM_KILLZONE", "NY_AM_SILVER_BULLET",
            "NY_PM_KILLZONE", "NY_PM_SILVER_BULLET"
        }
        
        # Determine if high probability window (weight >= 0.7)
        is_high_probability_window = time_window_weight >= 0.7
        
        # Compute price positions
        price_vs_daily_open = self._compute_price_position(current_price, daily_open)
        price_vs_weekly_open = self._compute_price_position(current_price, weekly_open)
        price_vs_true_day_open = self._compute_price_position(current_price, true_day_open)
        
        return TimeFeatures(
            time_window=time_window,
            narrative_phase=narrative_phase,
            time_window_weight=time_window_weight,
            is_killzone=is_killzone,
            is_high_probability_window=is_high_probability_window,
            price_vs_daily_open=price_vs_daily_open,
            price_vs_weekly_open=price_vs_weekly_open,
            price_vs_true_day_open=price_vs_true_day_open,
        )
    
    def _classify_time_window(self, hour: int, minute: int, instrument: str) -> str:
        """
        Classify hour and minute into a time window based on ICT killzone methodology.
        
        Args:
            hour: Hour in NY timezone (0-23)
            minute: Minute (0-59)
            instrument: Trading instrument
        
        Returns:
            Time window name
        """
        time_decimal = hour + minute / 60.0
        
        # ASIAN_RANGE: 20:00-22:00 NY (20.0-22.0)
        if 20.0 <= time_decimal < 22.0:
            return "ASIAN_RANGE"
        
        # TRUE_DAY_OPEN: 00:00-01:00 NY (0.0-1.0)
        if 0.0 <= time_decimal < 1.0:
            return "TRUE_DAY_OPEN"
        
        # LONDON_KILLZONE: 02:00-05:00 NY (2.0-5.0)
        if 2.0 <= time_decimal < 5.0:
            # LONDON_SILVER_BULLET: 03:00-04:00 NY (3.0-4.0) - highest probability
            if 3.0 <= time_decimal < 4.0:
                return "LONDON_SILVER_BULLET"
            return "LONDON_KILLZONE"
        
        # NY_AM_KILLZONE: 07:00-10:00 NY (7.0-10.0)
        if 7.0 <= time_decimal < 10.0:
            # NEWS_WINDOW: 08:00-09:00 NY (8.0-9.0) - prioritize over killzone
            if 8.0 <= time_decimal < 9.0:
                return "NEWS_WINDOW"
            return "NY_AM_KILLZONE"
        
        # LONDON_CLOSE / NY_AM_SILVER_BULLET: 10:00-12:00 NY (10.0-12.0)
        if 10.0 <= time_decimal < 12.0:
            # NY_AM_SILVER_BULLET: 10:00-11:00 NY (10.0-11.0) - highest probability
            if time_decimal < 11.0:
                return "NY_AM_SILVER_BULLET"
            return "LONDON_CLOSE"
        
        # NY_PM_KILLZONE: 13:30-16:00 NY (13.5-16.0)
        if 13.5 <= time_decimal < 16.0:
            # NY_PM_SILVER_BULLET: 14:00-15:00 NY (14.0-15.0) - highest probability
            if 14.0 <= time_decimal < 15.0:
                return "NY_PM_SILVER_BULLET"
            return "NY_PM_KILLZONE"
        
        # DAILY_CLOSE: 17:00-18:00 NY (17.0-18.0)
        if 17.0 <= time_decimal < 18.0:
            return "DAILY_CLOSE"
        
        # OFF_HOURS: all other times
        return "OFF_HOURS"
    
    def _compute_price_position(
        self,
        current_price: Optional[float],
        reference_price: Optional[float],
    ) -> Optional[str]:
        """
        Compute price position relative to a reference price.
        
        Args:
            current_price: Current price
            reference_price: Reference price (daily/weekly/true day open)
        
        Returns:
            "ABOVE", "BELOW", "AT", or None if prices not provided
        """
        if current_price is None or reference_price is None:
            return None
        
        if abs(current_price - reference_price) < 1e-6:
            return "AT"
        elif current_price > reference_price:
            return "ABOVE"
        else:
            return "BELOW"


def get_narrative_context(
    time_features: TimeFeatures,
    htf_features: dict,
    zone_features: dict,
) -> str:
    """
    Generate narrative context for trade reasoning.
    
    This function answers the 3-question framework:
    1. Where has price come from? (HTF context, previous session range, PD arrays)
    2. Where is it now? (current time window phase, price vs reference opens)
    3. Where is it likely to go? (nearest liquidity pool or imbalance to rebalance)
    
    Args:
        time_features: TimeFeatures from TimeWindowClassifier
        htf_features: HTF projection features (htf_open, htf_high, htf_low, htf_open_bias)
        zone_features: Zone features (swing_high, swing_low, fvg_present, etc.)
    
    Returns:
        Narrative context string
    """
    # Question 1: Where has price come from?
    htf_bias = htf_features.get("htf_open_bias", "NEUTRAL")
    htf_open = htf_features.get("htf_open", 0.0)
    htf_high = htf_features.get("htf_high", 0.0)
    htf_low = htf_features.get("htf_low", 0.0)
    
    context_parts = []
    
    # HTF context
    context_parts.append(
        f"HTF bias is {htf_bias} (HTF open: {htf_open:.5f}, high: {htf_high:.5f}, low: {htf_low:.5f})."
    )
    
    # Question 2: Where is it now?
    context_parts.append(
        f"Current time window: {time_features.time_window} ({time_features.narrative_phase} phase)."
    )
    
    if time_features.price_vs_daily_open:
        context_parts.append(f"Price is {time_features.price_vs_daily_open} daily open.")
    
    if time_features.price_vs_true_day_open:
        context_parts.append(f"Price is {time_features.price_vs_true_day_open} true day open.")
    
    # Question 3: Where is it likely to go?
    swing_high = zone_features.get("swing_high")
    swing_low = zone_features.get("swing_low")
    fvg_present = zone_features.get("fvg_present", False)
    
    if htf_bias == "BULLISH":
        if swing_high:
            context_parts.append(f"Expecting expansion toward swing high at {swing_high:.5f}.")
        elif htf_high:
            context_parts.append(f"Expecting expansion toward HTF high at {htf_high:.5f}.")
    elif htf_bias == "BEARISH":
        if swing_low:
            context_parts.append(f"Expecting expansion toward swing low at {swing_low:.5f}.")
        elif htf_low:
            context_parts.append(f"Expecting expansion toward HTF low at {htf_low:.5f}.")
    
    if fvg_present:
        context_parts.append("FVG present — potential imbalance to rebalance.")
    
    return " ".join(context_parts)
