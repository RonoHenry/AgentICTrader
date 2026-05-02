"""
Test suite for HTF 3-tier timeframe correlation logic (TTrades methodology).

This module tests the 3-tier timeframe correlation system:
- Higher TF (Bias Layer): Determines market direction
- Mid TF (Structure Layer): Confirms alignment via CISD
- Lower TF (Entry Layer): Precision timing for entry

**Validates: Requirements FR-2.1**
"""

import os
import sys

import pytest
from hypothesis import given, strategies as st

# ---------------------------------------------------------------------------
# Path setup — add workspace root so `ml` package is importable
# ---------------------------------------------------------------------------
_WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, _WORKSPACE_ROOT)

from ml.features.htf_selector import (  # noqa: E402
    TradingStyle,
    get_htf_correlation,
    get_bias_timeframe,
    get_structure_timeframe,
    get_entry_timeframe,
    SUPPORTED_TIMEFRAMES,
)


class TestTradingStyleCorrelations:
    """Test that all trading styles return correct 3-tier tuples."""

    def test_scalping_correlation(self):
        """Scalping: H1 → M15 → M1"""
        result = get_htf_correlation("M1", TradingStyle.SCALPING)
        assert result == ("H1", "M15", "M1")

    def test_intraday_standard_correlation(self):
        """Intraday Standard: D1 → H1 → M5"""
        result = get_htf_correlation("M5", TradingStyle.INTRADAY_STANDARD)
        assert result == ("D1", "H1", "M5")

    def test_intraday_simple_correlation(self):
        """Intraday Simple: D1 → H4 → M15"""
        result = get_htf_correlation("M15", TradingStyle.INTRADAY_SIMPLE)
        assert result == ("D1", "H4", "M15")

    def test_swing_correlation(self):
        """Swing: W1 → D1 → H1 (or H4)"""
        result = get_htf_correlation("H1", TradingStyle.SWING)
        assert result == ("W1", "D1", "H1")

    def test_position_correlation(self):
        """Position/Crypto: MN1 → W1 → H4"""
        result = get_htf_correlation("H4", TradingStyle.POSITION)
        assert result == ("MN1", "W1", "H4")


class TestIndividualLayerExtraction:
    """Test individual layer extraction functions."""

    def test_get_bias_timeframe_scalping(self):
        """Bias timeframe for scalping should be H1."""
        result = get_bias_timeframe("M1", TradingStyle.SCALPING)
        assert result == "H1"

    def test_get_structure_timeframe_scalping(self):
        """Structure timeframe for scalping should be M15."""
        result = get_structure_timeframe("M1", TradingStyle.SCALPING)
        assert result == "M15"

    def test_get_entry_timeframe_scalping(self):
        """Entry timeframe for scalping should be M1."""
        result = get_entry_timeframe("M1", TradingStyle.SCALPING)
        assert result == "M1"

    def test_get_bias_timeframe_intraday_standard(self):
        """Bias timeframe for intraday standard should be D1."""
        result = get_bias_timeframe("M5", TradingStyle.INTRADAY_STANDARD)
        assert result == "D1"

    def test_get_structure_timeframe_intraday_standard(self):
        """Structure timeframe for intraday standard should be H1."""
        result = get_structure_timeframe("M5", TradingStyle.INTRADAY_STANDARD)
        assert result == "H1"

    def test_get_entry_timeframe_intraday_standard(self):
        """Entry timeframe for intraday standard should be M5."""
        result = get_entry_timeframe("M5", TradingStyle.INTRADAY_STANDARD)
        assert result == "M5"

    def test_get_bias_timeframe_position(self):
        """Bias timeframe for position should be MN1."""
        result = get_bias_timeframe("H4", TradingStyle.POSITION)
        assert result == "MN1"

    def test_get_structure_timeframe_position(self):
        """Structure timeframe for position should be W1."""
        result = get_structure_timeframe("H4", TradingStyle.POSITION)
        assert result == "W1"

    def test_get_entry_timeframe_position(self):
        """Entry timeframe for position should be H4."""
        result = get_entry_timeframe("H4", TradingStyle.POSITION)
        assert result == "H4"


class TestSupportedTimeframes:
    """Test all supported timeframes are recognized."""

    def test_supported_timeframes_constant(self):
        """All required timeframes should be in SUPPORTED_TIMEFRAMES."""
        expected = {"M1", "M3", "M5", "M15", "M30", "H1", "H4", "D1", "W1", "MN1"}
        assert SUPPORTED_TIMEFRAMES == expected

    @pytest.mark.parametrize(
        "timeframe",
        ["M1", "M3", "M5", "M15", "M30", "H1", "H4", "D1", "W1", "MN1"],
    )
    def test_all_timeframes_supported(self, timeframe):
        """Each timeframe should be in SUPPORTED_TIMEFRAMES."""
        assert timeframe in SUPPORTED_TIMEFRAMES


class TestInvalidInputs:
    """Test that invalid inputs raise appropriate errors."""

    def test_invalid_timeframe_raises_error(self):
        """Invalid timeframe should raise ValueError."""
        with pytest.raises(ValueError, match="Unsupported timeframe"):
            get_htf_correlation("M2", TradingStyle.SCALPING)

    def test_invalid_trading_style_raises_error(self):
        """Invalid trading style should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid trading_style"):
            get_htf_correlation("M1", "INVALID_STYLE")

    def test_none_timeframe_raises_error(self):
        """None timeframe should raise ValueError."""
        with pytest.raises(ValueError):
            get_htf_correlation(None, TradingStyle.SCALPING)

    def test_none_trading_style_raises_error(self):
        """None trading style should raise ValueError."""
        with pytest.raises(ValueError):
            get_htf_correlation("M1", None)


class TestTimeframeHierarchyProperty:
    """Property-based test: bias_tf > structure_tf > entry_tf (strict hierarchy)."""

    # Timeframe duration mapping in minutes
    TIMEFRAME_MINUTES = {
        "M1": 1,
        "M3": 3,
        "M5": 5,
        "M15": 15,
        "M30": 30,
        "H1": 60,
        "H4": 240,
        "D1": 1440,
        "W1": 10080,
        "MN1": 43200,  # Approximate 30 days
    }

    @pytest.mark.parametrize(
        "trading_style",
        [
            TradingStyle.SCALPING,
            TradingStyle.INTRADAY_STANDARD,
            TradingStyle.INTRADAY_SIMPLE,
            TradingStyle.SWING,
            TradingStyle.POSITION,
        ],
    )
    def test_strict_timeframe_hierarchy(self, trading_style):
        """
        Property: bias_tf duration > structure_tf duration > entry_tf duration.
        
        **Validates: Requirements FR-2.1**
        """
        # Use a representative timeframe for each style
        timeframe_map = {
            TradingStyle.SCALPING: "M1",
            TradingStyle.INTRADAY_STANDARD: "M5",
            TradingStyle.INTRADAY_SIMPLE: "M15",
            TradingStyle.SWING: "H1",
            TradingStyle.POSITION: "H4",
        }
        
        current_tf = timeframe_map[trading_style]
        bias_tf, structure_tf, entry_tf = get_htf_correlation(current_tf, trading_style)
        
        bias_duration = self.TIMEFRAME_MINUTES[bias_tf]
        structure_duration = self.TIMEFRAME_MINUTES[structure_tf]
        entry_duration = self.TIMEFRAME_MINUTES[entry_tf]
        
        assert bias_duration > structure_duration, (
            f"{trading_style.value}: Bias TF ({bias_tf}={bias_duration}min) "
            f"must be > Structure TF ({structure_tf}={structure_duration}min)"
        )
        assert structure_duration > entry_duration, (
            f"{trading_style.value}: Structure TF ({structure_tf}={structure_duration}min) "
            f"must be > Entry TF ({entry_tf}={entry_duration}min)"
        )


class TestAllTradingStylesWithAllTimeframes:
    """Comprehensive test: all trading styles work with their designated timeframes."""

    @pytest.mark.parametrize(
        "current_tf,trading_style,expected",
        [
            # Scalping
            ("M1", TradingStyle.SCALPING, ("H1", "M15", "M1")),
            ("M5", TradingStyle.SCALPING, ("H1", "M15", "M1")),
            # Intraday Standard
            ("M5", TradingStyle.INTRADAY_STANDARD, ("D1", "H1", "M5")),
            ("M15", TradingStyle.INTRADAY_STANDARD, ("D1", "H1", "M5")),
            # Intraday Simple
            ("M15", TradingStyle.INTRADAY_SIMPLE, ("D1", "H4", "M15")),
            ("M30", TradingStyle.INTRADAY_SIMPLE, ("D1", "H4", "M15")),
            # Swing
            ("H1", TradingStyle.SWING, ("W1", "D1", "H1")),
            ("H4", TradingStyle.SWING, ("W1", "D1", "H1")),
            # Position
            ("H4", TradingStyle.POSITION, ("MN1", "W1", "H4")),
            ("D1", TradingStyle.POSITION, ("MN1", "W1", "H4")),
        ],
    )
    def test_correlation_for_all_styles(self, current_tf, trading_style, expected):
        """Test correlation returns expected tuple for all trading styles."""
        result = get_htf_correlation(current_tf, trading_style)
        assert result == expected
