"""
HTF 3-tier timeframe correlation logic (TTrades methodology).

This module implements the 3-tier timeframe correlation system:
- Higher TF (Bias Layer): Determines market direction
- Mid TF (Structure Layer): Confirms alignment via CISD
- Lower TF (Entry Layer): Precision timing for entry

**Implements: Requirements FR-2.1**

Example usage:
    >>> from ml.features.htf_selector import TradingStyle, get_htf_correlation
    >>> get_htf_correlation("M1", TradingStyle.SCALPING)
    ('H1', 'M15', 'M1')
    
    >>> get_bias_timeframe("M5", TradingStyle.INTRADAY_STANDARD)
    'D1'
"""

from enum import Enum
from typing import Tuple


class TradingStyle(Enum):
    """
    Trading style enum for 3-tier timeframe correlation.
    
    Each trading style has a specific 3-tier timeframe correlation:
    - SCALPING: H1 → M15 → M1
    - INTRADAY_STANDARD: D1 → H1 → M5
    - INTRADAY_SIMPLE: D1 → H4 → M15
    - SWING: W1 → D1 → H1
    - POSITION: MN1 → W1 → H4
    """
    SCALPING = "SCALPING"
    INTRADAY_STANDARD = "INTRADAY_STANDARD"
    INTRADAY_SIMPLE = "INTRADAY_SIMPLE"
    SWING = "SWING"
    POSITION = "POSITION"


# Supported timeframes constant (all valid timeframes in the system)
SUPPORTED_TIMEFRAMES = frozenset({
    "M1",   # 1 minute
    "M3",   # 3 minutes
    "M5",   # 5 minutes
    "M15",  # 15 minutes
    "M30",  # 30 minutes
    "H1",   # 1 hour
    "H4",   # 4 hours
    "D1",   # 1 day
    "W1",   # 1 week
    "MN1",  # 1 month
})


# Trading style to 3-tier correlation mapping
# Format: (Higher TF - Bias, Mid TF - Structure, Lower TF - Entry)
_TRADING_STYLE_CORRELATIONS = {
    TradingStyle.SCALPING: ("H1", "M15", "M1"),
    TradingStyle.INTRADAY_STANDARD: ("D1", "H1", "M5"),
    TradingStyle.INTRADAY_SIMPLE: ("D1", "H4", "M15"),
    TradingStyle.SWING: ("W1", "D1", "H1"),
    TradingStyle.POSITION: ("MN1", "W1", "H4"),
}


def _validate_inputs(current_tf: str, trading_style: TradingStyle) -> None:
    """
    Validate timeframe and trading style inputs.
    
    Args:
        current_tf: Current timeframe to validate
        trading_style: Trading style to validate
        
    Raises:
        ValueError: If inputs are invalid
    """
    if current_tf is None:
        raise ValueError("current_tf cannot be None")
    
    if trading_style is None:
        raise ValueError("trading_style cannot be None")
    
    if current_tf not in SUPPORTED_TIMEFRAMES:
        raise ValueError(
            f"Unsupported timeframe: {current_tf}. "
            f"Supported: {sorted(SUPPORTED_TIMEFRAMES)}"
        )
    
    if not isinstance(trading_style, TradingStyle):
        raise ValueError(
            f"Invalid trading_style: {trading_style}. "
            f"Must be a TradingStyle enum value."
        )


def get_htf_correlation(
    current_tf: str, trading_style: TradingStyle
) -> Tuple[str, str, str]:
    """
    Get 3-tier timeframe correlation for a given trading style.
    
    Args:
        current_tf: Current timeframe (e.g., "M1", "H1", "D1")
        trading_style: Trading style enum value
        
    Returns:
        Tuple of (higher_tf, mid_tf, lower_tf) where:
        - higher_tf: Bias layer timeframe
        - mid_tf: Structure layer timeframe
        - lower_tf: Entry layer timeframe
        
    Raises:
        ValueError: If timeframe or trading style is invalid
        
    Example:
        >>> get_htf_correlation("M1", TradingStyle.SCALPING)
        ('H1', 'M15', 'M1')
        
    **Validates: Requirements FR-2.1**
    """
    _validate_inputs(current_tf, trading_style)
    return _TRADING_STYLE_CORRELATIONS[trading_style]


def get_bias_timeframe(current_tf: str, trading_style: TradingStyle) -> str:
    """
    Get the Higher TF (Bias Layer) for a given trading style.
    
    The bias layer determines market direction via Candle 2 closures
    and Candle 3 expansions.
    
    Args:
        current_tf: Current timeframe
        trading_style: Trading style enum value
        
    Returns:
        Higher timeframe for bias determination
        
    Example:
        >>> get_bias_timeframe("M1", TradingStyle.SCALPING)
        'H1'
        
    **Validates: Requirements FR-2.1**
    """
    higher_tf, _, _ = get_htf_correlation(current_tf, trading_style)
    return higher_tf


def get_structure_timeframe(current_tf: str, trading_style: TradingStyle) -> str:
    """
    Get the Mid TF (Structure Layer) for a given trading style.
    
    The structure layer confirms alignment via CISD (Change in State
    of Delivery) or market structure shift.
    
    Args:
        current_tf: Current timeframe
        trading_style: Trading style enum value
        
    Returns:
        Mid timeframe for structure confirmation
        
    Example:
        >>> get_structure_timeframe("M1", TradingStyle.SCALPING)
        'M15'
        
    **Validates: Requirements FR-2.1**
    """
    _, mid_tf, _ = get_htf_correlation(current_tf, trading_style)
    return mid_tf


def get_entry_timeframe(current_tf: str, trading_style: TradingStyle) -> str:
    """
    Get the Lower TF (Entry Layer) for a given trading style.
    
    The entry layer provides precision timing for entry (wait for wick
    completion, enter on body expansion).
    
    Args:
        current_tf: Current timeframe
        trading_style: Trading style enum value
        
    Returns:
        Lower timeframe for entry precision
        
    Example:
        >>> get_entry_timeframe("M1", TradingStyle.SCALPING)
        'M1'
        
    **Validates: Requirements FR-2.1**
    """
    _, _, lower_tf = get_htf_correlation(current_tf, trading_style)
    return lower_tf
