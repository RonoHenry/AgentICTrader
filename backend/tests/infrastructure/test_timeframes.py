"""
Tests for timeframe analysis and organization.
"""
import pytest
import numpy as np
from datetime import datetime, timedelta
from trader.analysis.timeframes import TimeframeAnalyzer, TimeframeConfig

@pytest.fixture
def analyzer():
    """Create a test timeframe analyzer."""
    return TimeframeAnalyzer()

@pytest.fixture
def sample_m1_data():
    """Create sample M1 candle data."""
    now = datetime.now()
    data = []
    for i in range(100):
        timestamp = now + timedelta(minutes=i)
        data.append([
            timestamp.timestamp(),
            1.1000 + i * 0.0001,  # Open
            1.1000 + i * 0.0002,  # High
            1.1000 + i * 0.0001,  # Low
            1.1000 + i * 0.0002,  # Close
            100.0  # Volume
        ])
    return np.array(data)

def test_timeframe_config(analyzer):
    """Test timeframe configuration."""
    # Check all timeframes are configured
    assert all(tf in analyzer.timeframe_configs for tf in ['M1', 'M5', 'M15', 'H1', 'H4', 'D1'])
    
    # Check M1 configuration
    m1_config = analyzer.timeframe_configs['M1']
    assert isinstance(m1_config, TimeframeConfig)
    assert m1_config.minutes == 1
    assert m1_config.candles_to_keep == 10080  # 1 week
    
    # Check H4 configuration
    h4_config = analyzer.timeframe_configs['H4']
    assert h4_config.minutes == 240
    assert h4_config.candles_to_keep == 1080  # 6 months

def test_timeframe_conversion(analyzer, sample_m1_data):
    """Test converting between timeframes."""
    # Convert M1 to M5
    m5_data = analyzer.convert_timeframe(sample_m1_data, 'M1', 'M5')
    assert len(m5_data) == len(sample_m1_data) // 5
    
    # Convert M1 to H1
    h1_data = analyzer.convert_timeframe(sample_m1_data, 'M1', 'H1')
    assert len(h1_data) == len(sample_m1_data) // 60
    
    # Check data integrity
    assert h1_data[0][0] == sample_m1_data[0][0]  # First timestamp matches
    assert h1_data[0][1] == sample_m1_data[0][1]  # Open price matches
    assert h1_data[0][4] > sample_m1_data[0][4]   # Close price should be higher due to uptrend

def test_timeframe_alignment(analyzer, sample_m1_data):
    """Test aligning data across timeframes."""
    timeframes = ['M1', 'M5', 'M15', 'H1']
    aligned = analyzer.align_timeframes(sample_m1_data, timeframes)
    
    # Check all timeframes are present
    assert all(tf in aligned for tf in timeframes)
    
    # Check relative lengths
    assert len(aligned['M1']) == len(sample_m1_data)
    assert len(aligned['M5']) == len(sample_m1_data) // 5
    assert len(aligned['M15']) == len(sample_m1_data) // 15
    assert len(aligned['H1']) == len(sample_m1_data) // 60

def test_dominant_timeframe(analyzer, sample_m1_data):
    """Test finding dominant timeframe."""
    result = analyzer.find_dominant_timeframe(sample_m1_data)
    
    assert 'timeframe' in result
    assert 'strength' in result
    assert 'volatilities' in result
    assert result['timeframe'] in analyzer.timeframes
    assert 0 <= result['strength'] <= 1
    assert all(tf in result['volatilities'] for tf in analyzer.timeframes)
