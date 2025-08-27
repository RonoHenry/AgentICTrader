import pytest
import numpy as np
from trader.analysis.patterns import CandlePatternAnalyzer

class TestCandlePatternAnalyzer:
    @pytest.fixture
    def analyzer(self):
        return CandlePatternAnalyzer()

    def test_detect_accumulation_pattern(self, analyzer):
        """Test detection of accumulation pattern"""
        candles = np.array([
            [100, 101, 99, 100],  # Ranging candle
            [100, 102, 99, 101],  # Ranging candle
            [101, 102, 100, 101], # Ranging candle
        ])
        pattern = analyzer.detect_pattern(candles)
        assert pattern["type"] == "accumulation"
        assert pattern["confidence"] > 0.7

    def test_detect_manipulation_pattern(self, analyzer):
        """Test detection of manipulation pattern"""
        candles = np.array([
            [100, 105, 99, 104],  # Large move
            [104, 108, 103, 107], # Continuation
            [107, 110, 106, 109], # Final push
        ])
        pattern = analyzer.detect_pattern(candles)
        assert pattern["type"] == "manipulation"
        assert pattern["direction"] == "bullish"

    def test_detect_fvg(self, analyzer):
        """Test Fair Value Gap detection"""
        candles = np.array([
            [100, 102, 98, 101],   # Base candle
            [110, 115, 108, 113],  # Gap candle (FVG between 108 and 102)
        ])
        fvg = analyzer.detect_fvg(candles)
        assert fvg["present"] == True
        assert fvg["high"] == 108
        assert fvg["low"] == 102

    def test_detect_liquidity_pool(self, analyzer):
        """Test liquidity pool detection"""
        candles = np.array([
            [100, 102, 98, 101],
            [101, 103, 97, 102],
            [102, 104, 96, 103],  # Accumulation of orders at 96-97
        ])
        pool = analyzer.detect_liquidity_pool(candles)
        assert pool["present"] == True
        assert pool["type"] == "buy"  # Buy orders accumulated below
        assert 96 <= pool["price_level"] <= 97
