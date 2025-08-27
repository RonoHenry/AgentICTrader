import pytest
import numpy as np
from backend.trader.agents.power_of_3 import PowerOfThreeAnalyzer

class TestPowerOfThreeAnalyzer:
    @pytest.fixture
    def analyzer(self):
        return PowerOfThreeAnalyzer()

    def test_detect_bullish_po3_accumulation(self):
        # Mock data for bullish accumulation (consolidation above lows)
        candles = np.array([
            # OHLC data showing tight range, forming lows under open
            [100, 101, 98, 100],  # Ranging, testing lows
            [100, 102, 98, 101],  # Ranging, testing lows
            [101, 102, 99, 101],  # Ranging, holding above lows
            [101, 103, 99, 102],  # Ranging, holding above lows
        ])
        
        analyzer = PowerOfThreeAnalyzer()
        phase = analyzer.detect_phase(candles)
        assert phase == "accumulation"
        assert analyzer.get_phase_characteristics()["volatility"] == "low"
        assert analyzer.get_phase_characteristics()["bias"] == "bullish"

    def test_detect_bearish_po3_accumulation(self):
        # Mock data for bearish accumulation (consolidation below highs)
        candles = np.array([
            # OHLC data showing tight range, forming highs above open
            [100, 102, 99, 100],  # Ranging, testing highs
            [100, 102, 98, 99],   # Ranging, testing highs
            [99, 101, 98, 99],    # Ranging, staying below highs
            [99, 101, 97, 98],    # Ranging, staying below highs
        ])
        
        analyzer = PowerOfThreeAnalyzer()
        phase = analyzer.detect_phase(candles)
        assert phase == "accumulation"
        assert analyzer.get_phase_characteristics()["volatility"] == "low"
        assert analyzer.get_phase_characteristics()["bias"] == "bearish"

    def test_detect_bullish_manipulation(self):
        # Mock data for bullish manipulation (false move down)
        candles = np.array([
            [100, 100, 95, 96],   # Sharp move down
            [96, 97, 94, 95],     # Continuation down
            [95, 96, 93, 94],     # Final push down
        ])
        
        analyzer = PowerOfThreeAnalyzer()
        phase = analyzer.detect_phase(candles)
        assert phase == "manipulation"
        assert analyzer.get_phase_characteristics()["direction"] == "bearish"
        assert analyzer.is_false_move() == True
        assert analyzer.get_phase_characteristics()["true_bias"] == "bullish"

    def test_detect_bearish_manipulation(self):
        # Mock data for bearish manipulation (false move up)
        candles = np.array([
            [100, 105, 99, 104],  # Sharp move up
            [104, 108, 103, 107], # Continuation up
            [107, 110, 106, 109], # Final push up
        ])
        
        analyzer = PowerOfThreeAnalyzer()
        phase = analyzer.detect_phase(candles)
        assert phase == "manipulation"
        assert analyzer.get_phase_characteristics()["direction"] == "bullish"
        assert analyzer.is_false_move() == True
        assert analyzer.get_phase_characteristics()["true_bias"] == "bearish"

    def test_detect_bullish_distribution(self):
        # Mock data for bullish distribution (true move up)
        candles = np.array([
            [94, 98, 94, 97],    # Strong move up from lows
            [97, 101, 96, 100],  # Continuation up
            [100, 104, 99, 103], # Further expansion up
        ])
        
        analyzer = PowerOfThreeAnalyzer()
        phase = analyzer.detect_phase(candles)
        assert phase == "distribution"
        assert analyzer.get_phase_characteristics()["direction"] == "bullish"
        assert analyzer.is_true_move() == True

    def test_detect_bearish_distribution(self):
        # Mock data for bearish distribution (true move down)
        candles = np.array([
            [109, 110, 105, 106], # Initial move down
            [106, 107, 102, 103], # Continuation down
            [103, 104, 98, 99],   # Further expansion down
        ])
        
        analyzer = PowerOfThreeAnalyzer()
        phase = analyzer.detect_phase(candles)
        assert phase == "distribution"
        assert analyzer.get_phase_characteristics()["direction"] == "bearish"
        assert analyzer.is_true_move() == True

    def test_complete_bullish_po3_sequence(self):
        # Test complete bullish PO3 sequence
        candles = np.array([
            # Accumulation (ranging near lows)
            [100, 101, 98, 100],
            [100, 101, 98, 99],
            [99, 100, 97, 98],
            # Manipulation (false move down)
            [98, 98, 95, 96],
            [96, 97, 94, 95],
            # Distribution (true move up)
            [95, 99, 95, 98],
            [98, 102, 97, 101],
        ])
        
        analyzer = PowerOfThreeAnalyzer()
        po3_sequence = analyzer.analyze_sequence(candles)
        
        assert len(po3_sequence) == 3
        assert po3_sequence[0]["phase"] == "accumulation"
        assert po3_sequence[0]["bias"] == "bullish"
        assert po3_sequence[1]["phase"] == "manipulation"
        assert po3_sequence[1]["true_bias"] == "bullish"
        assert po3_sequence[2]["phase"] == "distribution"
        assert po3_sequence[2]["direction"] == "bullish"

    def test_complete_bearish_po3_sequence(self):
        # Test complete bearish PO3 sequence
        candles = np.array([
            # Accumulation (ranging near highs)
            [100, 102, 99, 100],
            [100, 102, 98, 99],
            [99, 101, 98, 99],
            # Manipulation (false move up)
            [99, 103, 99, 102],
            [102, 105, 101, 104],
            # Distribution (true move down)
            [104, 104, 99, 100],
            [100, 101, 96, 97],
        ])
        
        analyzer = PowerOfThreeAnalyzer()
        po3_sequence = analyzer.analyze_sequence(candles)
        
        assert len(po3_sequence) == 3
        assert po3_sequence[0]["phase"] == "accumulation"
        assert po3_sequence[0]["bias"] == "bearish"
        assert po3_sequence[1]["phase"] == "manipulation"
        assert po3_sequence[1]["true_bias"] == "bearish"
        assert po3_sequence[2]["phase"] == "distribution"
        assert po3_sequence[2]["direction"] == "bearish"

    def test_bullish_po3_entry_points(self):
        # Test entry points for bullish PO3
        candles = np.array([
            # Previous bullish PO3 sequence
            [100, 101, 98, 100],  # Accumulation
            [98, 98, 95, 96],     # Manipulation down
            [95, 99, 95, 98],     # Distribution up
            # Current forming candle
            [98, 99, 97, 98]      # Potential entry
        ])
        
        analyzer = PowerOfThreeAnalyzer()
        entry_points = analyzer.calculate_entry_points(candles)
        
        assert entry_points["primary_entry"] > entry_points["stop_loss"]  # Buy setup
        assert entry_points["target"] > entry_points["primary_entry"]     # Profit target above entry

    def test_bearish_po3_entry_points(self):
        # Test entry points for bearish PO3
        candles = np.array([
            # Previous bearish PO3 sequence
            [100, 102, 99, 100],  # Accumulation
            [100, 104, 100, 103], # Manipulation up
            [103, 103, 98, 99],   # Distribution down
            # Current forming candle
            [99, 100, 98, 99]     # Potential entry
        ])
        
        analyzer = PowerOfThreeAnalyzer()
        entry_points = analyzer.calculate_entry_points(candles)
        
        assert entry_points["primary_entry"] < entry_points["stop_loss"]  # Sell setup
        assert entry_points["target"] < entry_points["primary_entry"]     # Profit target below entry
