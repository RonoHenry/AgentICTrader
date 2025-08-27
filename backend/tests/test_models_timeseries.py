"""
Test timeseries models and their integration with InfluxDB.
"""
import pytest
from datetime import datetime, timezone
from decimal import Decimal
from trader.models_timeseries import CandlePoint, PDArrayPoint

def test_candle_point_creation():
    """Test creating a new candle point."""
    timestamp = datetime.now(timezone.utc)
    candle = CandlePoint(
        symbol="EURUSD",
        timeframe="1H",
        timestamp=timestamp,
        open=Decimal("1.10000"),
        high=Decimal("1.10500"),
        low=Decimal("1.09500"),
        close=Decimal("1.10250"),
        volume=1000
    )
    
    # Test point creation
    point_dict = candle.to_dict()
    assert point_dict["measurement"] == "candles"
    assert point_dict["tags"]["symbol"] == "EURUSD"
    assert point_dict["tags"]["timeframe"] == "1H"
    assert point_dict["fields"]["open"] == float(Decimal("1.10000"))
    assert point_dict["fields"]["high"] == float(Decimal("1.10500"))
    assert point_dict["fields"]["low"] == float(Decimal("1.09500"))
    assert point_dict["fields"]["close"] == float(Decimal("1.10250"))
    assert point_dict["fields"]["volume"] == 1000
    assert point_dict["time"] == timestamp

def test_pdarray_point_creation():
    """Test creating a new PDArray point."""
    timestamp = datetime.now(timezone.utc)
    pdarray = PDArrayPoint(
        symbol="EURUSD",
        timeframe="1H",
        timestamp=timestamp,
        zone_type="demand",
        high=Decimal("1.10500"),
        low=Decimal("1.10000"),
        strength=Decimal("0.85")
    )
    
    # Test point creation
    point_dict = pdarray.to_dict()
    assert point_dict["measurement"] == "pd_arrays"
    assert point_dict["tags"]["symbol"] == "EURUSD"
    assert point_dict["tags"]["timeframe"] == "1H"
    assert point_dict["tags"]["zone_type"] == "demand"
    assert point_dict["fields"]["high"] == float(Decimal("1.10500"))
    assert point_dict["fields"]["low"] == float(Decimal("1.10000"))
    assert point_dict["fields"]["strength"] == float(Decimal("0.85"))
    assert point_dict["time"] == timestamp

def test_candle_point_validation():
    """Test validation for candle point creation."""
    timestamp = datetime.now(timezone.utc)
    
    # Test with invalid symbol
    with pytest.raises(ValueError):
        CandlePoint(
            symbol="",  # Empty symbol
            timeframe="1H",
            timestamp=timestamp,
            open=Decimal("1.10000"),
            high=Decimal("1.10500"),
            low=Decimal("1.09500"),
            close=Decimal("1.10250"),
            volume=1000
        )
    
    # Test with invalid timeframe
    with pytest.raises(ValueError):
        CandlePoint(
            symbol="EURUSD",
            timeframe="",  # Empty timeframe
            timestamp=timestamp,
            open=Decimal("1.10000"),
            high=Decimal("1.10500"),
            low=Decimal("1.09500"),
            close=Decimal("1.10250"),
            volume=1000
        )
    
    # Test with invalid price order (high < low)
    with pytest.raises(ValueError):
        CandlePoint(
            symbol="EURUSD",
            timeframe="1H",
            timestamp=timestamp,
            open=Decimal("1.10000"),
            high=Decimal("1.09000"),  # High less than low
            low=Decimal("1.09500"),
            close=Decimal("1.10250"),
            volume=1000
        )
        
    # Test with non-decimal price
    with pytest.raises(ValueError):
        CandlePoint(
            symbol="EURUSD",
            timeframe="1H",
            timestamp=timestamp,
            open=1.10000,  # float instead of Decimal
            high=Decimal("1.10500"),
            low=Decimal("1.09500"),
            close=Decimal("1.10250"),
            volume=1000
        )

    # Test with non-integer volume
    with pytest.raises(ValueError):
        CandlePoint(
            symbol="EURUSD",
            timeframe="1H",
            timestamp=timestamp,
            open=Decimal("1.10000"),
            high=Decimal("1.10500"),
            low=Decimal("1.09500"),
            close=Decimal("1.10250"),
            volume=1000.0  # float instead of int
        )

def test_pdarray_point_validation():
    """Test validation for PDArray point creation."""
    timestamp = datetime.now(timezone.utc)
    
    # Test with invalid zone type
    with pytest.raises(ValueError):
        PDArrayPoint(
            symbol="EURUSD",
            timeframe="1H",
            timestamp=timestamp,
            zone_type="invalid",  # Invalid zone type
            high=Decimal("1.10500"),
            low=Decimal("1.10000"),
            strength=Decimal("0.85")
        )
    
    # Test with invalid strength range
    with pytest.raises(ValueError):
        PDArrayPoint(
            symbol="EURUSD",
            timeframe="1H",
            timestamp=timestamp,
            zone_type="demand",
            high=Decimal("1.10500"),
            low=Decimal("1.10000"),
            strength=Decimal("1.5")  # Strength should be between 0 and 1
        )
    
    # Test with invalid price levels (high < low)
    with pytest.raises(ValueError):
        PDArrayPoint(
            symbol="EURUSD",
            timeframe="1H",
            timestamp=timestamp,
            zone_type="demand",
            high=Decimal("1.09500"),  # High less than low
            low=Decimal("1.10000"),
            strength=Decimal("0.85")
        )
        
    # Test with non-decimal values
    with pytest.raises(ValueError):
        PDArrayPoint(
            symbol="EURUSD",
            timeframe="1H",
            timestamp=timestamp,
            zone_type="demand",
            high=1.10500,  # float instead of Decimal
            low=Decimal("1.10000"),
            strength=Decimal("0.85")
        )
