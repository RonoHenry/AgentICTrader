"""
Test InfluxDB manager configuration and operations.
"""
import pytest
from datetime import datetime, timezone
from decimal import Decimal
from django.conf import settings
from trader.infrastructure.influxdb_manager import InfluxDBManager
from influxdb_client.client.exceptions import InfluxDBError

@pytest.fixture
def influx_manager():
    """Create an InfluxDB manager for testing."""
    return InfluxDBManager()

def test_connection_config(influx_manager):
    """Test that connection configuration is properly loaded."""
    config = influx_manager.get_connection_config()
    assert config['url'] == settings.INFLUXDB_URL
    assert config['token'] == settings.INFLUXDB_TOKEN
    assert config['org'] == settings.INFLUXDB_ORG
    assert config['default_bucket'] == settings.INFLUXDB_DEFAULT_BUCKET

def test_client_initialization(influx_manager):
    """Test that client is properly initialized."""
    client = influx_manager.get_client()
    assert client is not None
    health = client.health()
    assert health.status == "pass"

def test_bucket_management(influx_manager):
    """Test bucket creation and verification."""
    test_bucket = "test_market_data"
    
    # Test bucket creation
    buckets = influx_manager.create_bucket_structure()
    assert isinstance(buckets, list)
    assert "market_data_m1" in buckets
    
    # Test bucket existence
    assert influx_manager.bucket_exists("market_data_m1") is True
    assert influx_manager.bucket_exists("non_existent_bucket") is False

def test_retention_policy_management(influx_manager):
    """Test setting and getting retention policies."""
    bucket = "market_data_m1"
    
    # Set retention policy
    influx_manager.set_retention_policy(bucket, "7d")
    
    # Get retention policy
    retention = influx_manager.get_retention_policy(bucket)
    assert retention == "7d"

def test_data_point_operations(influx_manager):
    """Test writing and querying data points."""
    bucket = settings.INFLUXDB_DEFAULT_BUCKET
    test_data = {
        "symbol": "EURUSD",
        "open": 1.1000,
        "high": 1.1100,
        "low": 1.0900,
        "close": 1.1050,
        "volume": 1000.0,
        "timestamp": datetime.now(timezone.utc)
    }
    
    # Write point
    influx_manager.write_point(bucket, test_data)
    
    # Query last point
    point = influx_manager.query_last_point(bucket, "EURUSD")
    assert point is not None
    assert point["symbol"] == "EURUSD"
    assert Decimal(str(point["close"])) == Decimal("1.1050")

def test_duration_parsing(influx_manager):
    """Test duration string parsing and formatting."""
    # Test parsing
    assert influx_manager._parse_duration("7d") == 7 * 24 * 60 * 60
    assert influx_manager._parse_duration("24h") == 24 * 60 * 60
    assert influx_manager._parse_duration("60m") == 60 * 60
    assert influx_manager._parse_duration("3600s") == 3600
    
    # Test formatting
    assert influx_manager._format_duration(7 * 24 * 60 * 60) == "7d"
    assert influx_manager._format_duration(24 * 60 * 60) == "24h"
    assert influx_manager._format_duration(60 * 60) == "60m"
    assert influx_manager._format_duration(30) == "30s"

def test_error_handling(influx_manager):
    """Test error handling for various operations."""
    # Test invalid bucket name
    with pytest.raises(ValueError):
        influx_manager.write_point("", {"symbol": "EURUSD"})
    
    # Test invalid data format
    with pytest.raises(KeyError):
        influx_manager.write_point("market_data_m1", {})  # Missing symbol
    
    # Test invalid retention policy
    with pytest.raises(ValueError):
        influx_manager.set_retention_policy("market_data_m1", "invalid")
