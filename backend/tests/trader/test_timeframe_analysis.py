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
            (now - timedelta(minutes=i), 100+i, 102+i, 99+i, 101+i, 1000)
            for i in range(60)
        ]
        return np.array(m1_data)

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
        dominant_tf = analyzer.find_dominant_timeframe(sample_data)
        assert dominant_tf in ["M1", "M5", "M15", "H1", "H4", "D1"]
        assert hasattr(dominant_tf, "strength")  # Confidence score
