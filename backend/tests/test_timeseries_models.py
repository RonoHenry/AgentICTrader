"""
Test timeseries data models and utilities.
"""
import pytest
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch
from influxdb_client import Bucket, BucketsApi, InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS
from influxdb_client.service.buckets_service import BucketsService
from trader.infrastructure.timeseries import TimeseriesManager, TimeseriesBucket, OHLCVPoint

@pytest.fixture
def mock_bucket():
    """Create a mock InfluxDB bucket."""
    bucket = MagicMock(spec=Bucket)
    bucket.name = "test_bucket"
    bucket.retention_rules = [MagicMock(every_seconds=7 * 86400)]
    return bucket

@pytest.fixture
def mock_buckets_api():
    """Create a mock InfluxDB buckets API."""
    api = MagicMock(spec=BucketsApi)
    return api

@pytest.fixture
def mock_influx_client(mock_buckets_api, mock_bucket):
    """Create a mock InfluxDB client."""
    client = MagicMock(spec=InfluxDBClient)
    client.org = "test_org"
    client.buckets_api.return_value = mock_buckets_api
    mock_buckets_api.find_bucket_by_name.return_value = mock_bucket
    mock_buckets_api.create_bucket.return_value = mock_bucket
    client.write_api.return_value = MagicMock()
    client.query_api.return_value = MagicMock()
    return client

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

def test_ohlcv_point_creation():
    """Test creating an OHLCV data point."""
    timestamp = datetime.now(timezone.utc)
    point = OHLCVPoint(
        symbol="EURUSD",
        timestamp=timestamp,
        timeframe="1H",
        open=Decimal("1.10000"),
        high=Decimal("1.10500"),
        low=Decimal("1.09500"),
        close=Decimal("1.10250"),
        volume=1000
    )
    
    assert point.symbol == "EURUSD"
    assert point.timestamp == timestamp
    assert point.timeframe == "1H"
    assert point.open == Decimal("1.10000")
    assert point.high == Decimal("1.10500")
    assert point.low == Decimal("1.09500")
    assert point.close == Decimal("1.10250")
    assert point.volume == 1000

def test_ohlcv_point_validation():
    """Test validation of OHLCV data."""
    timestamp = datetime.now(timezone.utc)
    
    # Test high price less than low price
    with pytest.raises(ValueError):
        OHLCVPoint(
            symbol="EURUSD",
            timestamp=timestamp,
            timeframe="1H",
            open=Decimal("1.10000"),
            high=Decimal("1.09000"),  # Less than low
            low=Decimal("1.09500"),
            close=Decimal("1.10250"),
            volume=1000
        )
    
    # Test open price outside high-low range
    with pytest.raises(ValueError):
        OHLCVPoint(
            symbol="EURUSD",
            timestamp=timestamp,
            timeframe="1H",
            open=Decimal("1.11000"),  # Above high
            high=Decimal("1.10500"),
            low=Decimal("1.09500"),
            close=Decimal("1.10250"),
            volume=1000
        )
    
    # Test close price outside high-low range
    with pytest.raises(ValueError):
        OHLCVPoint(
            symbol="EURUSD",
            timestamp=timestamp,
            timeframe="1H",
            open=Decimal("1.10000"),
            high=Decimal("1.10500"),
            low=Decimal("1.09500"),
            close=Decimal("1.09000"),  # Below low
            volume=1000
        )
    
    # Test negative volume
    with pytest.raises(ValueError):
        OHLCVPoint(
            symbol="EURUSD",
            timestamp=timestamp,
            timeframe="1H", 
            open=Decimal("1.10000"),
            high=Decimal("1.10500"),
            low=Decimal("1.09500"),
            close=Decimal("1.10250"),
            volume=-1000
        )

def test_timeseries_bucket_config(mock_influx_client):
    """Test timeseries bucket configuration."""
    bucket = TimeseriesBucket.create(
        client=mock_influx_client,
        name="market_data_m1",
        retention_days=7
    )
    
    assert bucket.name == "market_data_m1"
    assert bucket.get_retention_period() == "7d"
    
    # Test bucket creation without retention rules
    no_retention_bucket = MagicMock(spec=Bucket)
    no_retention_bucket.retention_rules = None
    mock_influx_client.buckets_api.return_value.find_bucket_by_name.return_value = no_retention_bucket
    
    bucket2 = TimeseriesBucket(
        client=mock_influx_client,
        name="no_retention"
    )
    assert bucket2.get_retention_period() == "infinite"

@pytest.mark.django_db
def test_timeseries_manager(mock_influx_client):
    """Test timeseries manager functionality."""
    manager = TimeseriesManager(mock_influx_client)
    
    # Test bucket creation and retrieval
    bucket = TimeseriesBucket.create(
        client=mock_influx_client,
        name="test_bucket",
        retention_days=7
    )
    assert bucket.name == "test_bucket"
    assert bucket.get_retention_period() == "7d"
    
    retrieved_bucket = manager.get_bucket("test_bucket")
    assert retrieved_bucket.name == "test_bucket"
    assert retrieved_bucket.exists() is True
    
    # Test write point
    timestamp = datetime.now(timezone.utc)
    point = OHLCVPoint(
        symbol="EURUSD",
        timestamp=timestamp,
        timeframe="1H",
        open=Decimal("1.10000"),
        high=Decimal("1.10500"),
        low=Decimal("1.09500"),
        close=Decimal("1.10250"),
        volume=1000
    )
    
    success = manager.write_ohlcv(point)
    assert success is True
    
    # Verify the write API call
    write_api = mock_influx_client.write_api.return_value
    write_api.write.assert_called_once()
    
    # Test retrieving read OHLCV data
    query_api = mock_influx_client.query_api.return_value
    # Setup mock response for read query
    mock_record = MagicMock()
    mock_record.values = {
        "symbol": "EURUSD",
        "_time": timestamp,
        "timeframe": "1H",
        "open": "1.10000",
        "high": "1.10500", 
        "low": "1.09500",
        "close": "1.10250",
        "volume": "1000"
    }
    mock_table = MagicMock()
    mock_table.records = [mock_record]
    query_api.query.return_value = [mock_table]
    
    records = manager.read_ohlcv(
        symbol="EURUSD",
        timeframe="1H",
        start_time=datetime.now(timezone.utc),
        end_time=datetime.now(timezone.utc)
    )
    assert isinstance(records, list)
    assert query_api.query.call_count == 1