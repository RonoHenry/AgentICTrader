import pytest
import numpy as np
from trader.analysis.pdarray import PDArrayAnalyzer

class TestPDArrayAnalyzer:
    @pytest.fixture
    def analyzer(self):
        return PDArrayAnalyzer()

    def test_detect_premium_zone(self, analyzer):
        """Test premium zone detection"""
        candles = np.array([
            [100, 102, 98, 101],
            [101, 105, 100, 104],
            [104, 108, 103, 107]  # Premium zone forming above
        ])
        premium = analyzer.detect_premium_zone(candles)
        assert premium["present"] == True
        assert premium["strength"] > 0.7
        assert premium["upper_bound"] > premium["lower_bound"]

    def test_detect_discount_zone(self, analyzer):
        """Test discount zone detection"""
        candles = np.array([
            [100, 102, 98, 99],
            [99, 100, 95, 96],
            [96, 97, 93, 94]  # Discount zone forming below
        ])
        discount = analyzer.detect_discount_zone(candles)
        assert discount["present"] == True
        assert discount["strength"] > 0.7
        assert discount["upper_bound"] > discount["lower_bound"]

    def test_zone_strength_calculation(self, analyzer):
        """Test zone strength calculator"""
        candles = np.array([
            [100, 102, 98, 101],
            [101, 105, 100, 104],
            [104, 108, 103, 107]
        ])
        zone = {
            "type": "premium",
            "upper_bound": 108,
            "lower_bound": 105
        }
        strength = analyzer.calculate_zone_strength(zone, candles)
        assert 0 <= strength <= 1

    def test_multi_timeframe_correlation(self, analyzer):
        """Test correlation across timeframes"""
        m5_candles = np.array([[100, 102, 98, 101]])
        m15_candles = np.array([[99, 103, 97, 102]])
        h1_candles = np.array([[98, 104, 96, 103]])
        
        correlation = analyzer.correlate_timeframes({
            "M5": m5_candles,
            "M15": m15_candles,
            "H1": h1_candles
        })
        
        assert "correlation_score" in correlation
        assert 0 <= correlation["correlation_score"] <= 1
        assert "aligned_zones" in correlation
