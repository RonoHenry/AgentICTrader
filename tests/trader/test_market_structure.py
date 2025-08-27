import pytest
import numpy as np
from backend.trader.agents.market_structure import MarketStructureAnalyzer

class TestMarketStructureAnalyzer:
    @pytest.fixture
    def analyzer(self):
        return MarketStructureAnalyzer()

    def test_detect_accumulation_phase(self):
        # Mock data representing sideways movement with small candles
        candles = np.array([
            # OHLC data showing tight range
            [100, 101, 99, 100],  # Small range candle
            [100, 102, 99, 101],  # Small range candle
            [101, 102, 100, 101], # Small range candle
            [101, 103, 100, 102], # Small range candle
        ])
        
        analyzer = MarketStructureAnalyzer()
        phase = analyzer.detect_phase(candles)
        assert phase == "accumulation"
        assert analyzer.get_phase_strength() > 0.7  # High confidence

    def test_detect_manipulation_phase(self):
        # Mock data representing sharp move in one direction
        candles = np.array([
            [100, 105, 99, 104],  # Large bullish candle
            [104, 108, 103, 107], # Continuation
            [107, 110, 106, 109], # Final push
        ])
        
        analyzer = MarketStructureAnalyzer()
        phase = analyzer.detect_phase(candles)
        assert phase == "manipulation"
        assert analyzer.get_move_direction() == "bullish"

    def test_detect_distribution_phase(self):
        # Mock data representing reversal and true move
        candles = np.array([
            [109, 110, 105, 106], # Reversal candle
            [106, 107, 102, 103], # Follow through
            [103, 104, 98, 99],   # Continuation
        ])
        
        analyzer = MarketStructureAnalyzer()
        phase = analyzer.detect_phase(candles)
        assert phase == "distribution"
        assert analyzer.get_move_direction() == "bearish"

    def test_complete_formation_sequence(self):
        # Test complete AMD sequence
        candles = np.array([
            # Accumulation
            [100, 101, 99, 100],
            [100, 102, 99, 101],
            [101, 102, 100, 101],
            # Manipulation
            [101, 105, 101, 104],
            [104, 108, 103, 107],
            # Distribution
            [107, 108, 103, 104],
            [104, 105, 100, 101],
        ])
        
        analyzer = MarketStructureAnalyzer()
        phases = analyzer.analyze_formation(candles)
        
        assert len(phases) == 3
        assert phases[0]["phase"] == "accumulation"
        assert phases[1]["phase"] == "manipulation"
        assert phases[2]["phase"] == "distribution"
        
        # Verify the sequence timing
        assert phases[1]["start_index"] > phases[0]["start_index"]
        assert phases[2]["start_index"] > phases[1]["start_index"]
