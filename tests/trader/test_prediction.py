import pytest
from backend.trader.agents.prediction import CandlePredictor

def test_candle_predictor_initialization():
    """Test CandlePredictor initialization"""
    predictor = CandlePredictor()
    assert hasattr(predictor, 'timeframes')
    assert 'M1' in predictor.timeframes
    assert 'MN' in predictor.timeframes

def test_next_candle_prediction(sample_candle_data):
    """Test next candle prediction output format"""
    predictor = CandlePredictor()
    prediction = predictor.predict_next_candle(sample_candle_data)
    
    # Check prediction structure
    assert isinstance(prediction, dict)
    assert 'predicted_high' in prediction
    assert 'predicted_low' in prediction
    assert 'predicted_direction' in prediction
    assert 'confidence_score' in prediction
    
    # Check value types
    assert isinstance(prediction['predicted_high'], float)
    assert isinstance(prediction['predicted_low'], float)
    assert isinstance(prediction['predicted_direction'], str)
    assert isinstance(prediction['confidence_score'], float)
    
    # Check value ranges
    assert 0 <= prediction['confidence_score'] <= 1
    assert prediction['predicted_low'] <= prediction['predicted_high']
    assert prediction['predicted_direction'] in ['bullish', 'bearish', 'neutral']

@pytest.mark.asyncio
async def test_real_time_prediction(mock_deriv_client):
    """Test real-time prediction with market data"""
    predictor = CandlePredictor()
    market_data = await mock_deriv_client.get_market_data('EURUSD')
    prediction = predictor.predict_next_candle(market_data)
    
    assert prediction['confidence_score'] > 0
    assert prediction['predicted_high'] > prediction['predicted_low']

def test_multi_timeframe_correlation():
    """Test correlation between different timeframe predictions"""
    predictor = CandlePredictor()
    predictions = {
        timeframe: predictor.predict_next_candle({'timeframe': timeframe})
        for timeframe in ['M1', 'M5', 'M15']
    }
    
    # Check timeframe alignment
    assert len(predictions) == 3
    assert all(pred['confidence_score'] > 0 for pred in predictions.values())
