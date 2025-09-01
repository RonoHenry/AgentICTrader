import pytest
import numpy as np
from datetime import datetime, timedelta
from trader.analysis.timeframes import TimeframeAnalyzer

class TestTimeframeAnalyzer:
    @pytest.fixture
    def analyzer(self):
        return TimeframeAnalyzer()

    @pytest.fixture
    def sample_data(self):
        # Create sample OHLCV data for multiple timeframes
        now = datetime.now()
        m1_data = [
            # timestamp, open, high, low, close, volume
            (now - timedelta(minutes=i), 
             100 + i + np.random.normal(0, 0.5),  # Add some noise to make it more realistic
             102 + i + np.random.normal(0, 0.5),
             99 + i + np.random.normal(0, 0.5),
             101 + i + np.random.normal(0, 0.5),
             1000 + np.random.randint(-100, 100))
            for i in range(480)  # 8 hours worth of M1 data
        ]
        return np.array(m1_data, dtype=object)

    def test_timeframe_conversion(self, analyzer, sample_data):
        """Test converting M1 data to higher timeframes"""
        m5_data = analyzer.convert_timeframe(sample_data, "M1", "M5")
        m15_data = analyzer.convert_timeframe(sample_data, "M1", "M15")
        
        assert len(m5_data) == len(sample_data) // 5
        assert len(m15_data) == len(sample_data) // 15

    def test_timeframe_alignment(self, analyzer, sample_data):
        """Test alignment of different timeframes"""
        timeframes = ["M1", "M5", "M15", "H1"]
        aligned_data = analyzer.align_timeframes(sample_data, timeframes)
        
        assert all(tf in aligned_data for tf in timeframes)
        assert all(len(aligned_data[tf]) > 0 for tf in timeframes)

    def test_dominant_timeframe(self, analyzer, sample_data):
        """Test detection of dominant timeframe"""
        dominant_info = analyzer.find_dominant_timeframe(sample_data)
        assert isinstance(dominant_info, dict)
        assert "timeframe" in dominant_info
        assert "strength" in dominant_info
        assert "volatilities" in dominant_info
        assert dominant_info["timeframe"] in ["M1", "M5", "M15", "H1", "H4", "D1"]
        assert 0 <= dominant_info["strength"] <= 1  # Confidence score should be between 0 and 1
