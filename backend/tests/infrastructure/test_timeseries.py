"""
Test InfluxDB infrastructure and time series data handling.
"""
import pytest
from datetime import datetime, timezone
from decimal import Decimal
from trader.infrastructure.timeseries import (
    InfluxDBClient,
    TimeseriesManager,
    OHLCVPoint,
    TimeseriesBucket
)

@pytest.fixture
def influx_client():
    """Create a test InfluxDB client."""
    return InfluxDBClient(
        url="http://localhost:8086",
        token="test-token",
        org="agentic"
    )

@pytest.fixture
def timeseries_manager(influx_client):
    """Create a test timeseries manager."""
    return TimeseriesManager(client=influx_client)

@pytest.fixture
def sample_ohlcv_data():
    """Create sample OHLCV data."""
    return OHLCVPoint(
        symbol="EUR/USD",
        timestamp=datetime.now(timezone.utc),
        timeframe="M1",
        open=Decimal("1.2000"),
        high=Decimal("1.2010"),
        low=Decimal("1.1990"),
        close=Decimal("1.2005"),
        volume=1000
    )

class TestInfluxDBInfrastructure:
    def test_client_connection(self, influx_client):
        """Test that we can connect to InfluxDB."""
        health = influx_client.health()
        assert health.status == "pass"
        
    def test_bucket_creation(self, influx_client):
        """Test bucket creation and management."""
        bucket = TimeseriesBucket.create(
            client=influx_client,
            name="test_market_data",
            retention_days=30
        )
        assert bucket.exists()
        assert bucket.get_retention_period() == "30d"
        
    def test_write_ohlcv_data(self, timeseries_manager, sample_ohlcv_data):
        """Test writing OHLCV data points."""
        result = timeseries_manager.write_ohlcv(sample_ohlcv_data)
        assert result is True
        
    def test_read_ohlcv_data(self, timeseries_manager, sample_ohlcv_data):
        """Test reading back written OHLCV data."""
        # Write test data
        timeseries_manager.write_ohlcv(sample_ohlcv_data)
        
        # Read back data
        data = timeseries_manager.read_ohlcv(
            symbol=sample_ohlcv_data.symbol,
            timeframe=sample_ohlcv_data.timeframe,
            start_time=sample_ohlcv_data.timestamp,
            end_time=sample_ohlcv_data.timestamp
        )
        
        assert len(data) == 1
        point = data[0]
        assert point.symbol == sample_ohlcv_data.symbol
        assert point.open == sample_ohlcv_data.open
        assert point.high == sample_ohlcv_data.high
        assert point.low == sample_ohlcv_data.low
        assert point.close == sample_ohlcv_data.close
        assert point.volume == sample_ohlcv_data.volume
        
    def test_data_retention(self, timeseries_manager):
        """Test that data retention policies are working."""
        bucket = timeseries_manager.get_bucket("test_market_data")
        retention = bucket.get_retention_period()
        assert retention == "30d"
        
    def test_multiple_timeframe_storage(self, timeseries_manager):
        """Test storing data for multiple timeframes."""
        timeframes = ["M1", "M5", "M15", "H1"]
        base_price = Decimal("1.2000")
        
        # Write data for each timeframe
        for tf in timeframes:
            data = OHLCVPoint(
                symbol="EUR/USD",
                timestamp=datetime.now(timezone.utc),
                timeframe=tf,
                open=base_price,
                high=base_price + Decimal("0.0010"),
                low=base_price - Decimal("0.0010"),
                close=base_price + Decimal("0.0005"),
                volume=1000
            )
            result = timeseries_manager.write_ohlcv(data)
            assert result is True
            
        # Verify data for each timeframe
        for tf in timeframes:
            data = timeseries_manager.read_ohlcv(
                symbol="EUR/USD",
                timeframe=tf,
                start_time=datetime.now(timezone.utc).replace(hour=0, minute=0),
                end_time=datetime.now(timezone.utc)
            )
            assert len(data) > 0
            assert data[0].timeframe == tf
