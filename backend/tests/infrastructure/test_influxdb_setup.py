"""
Test InfluxDB infrastructure setup and management.
"""
import pytest
from django.conf import settings
from datetime import timedelta
from trader.infrastructure.influxdb_manager import InfluxDBManager
from influxdb_client.client.exceptions import InfluxDBError

class TestInfluxDBSetup:
    @pytest.fixture
    def influx_manager(self):
        """Create a test InfluxDB manager."""
        return InfluxDBManager()

    def test_connection_settings(self, influx_manager):
        """Test that connection settings are properly configured."""
        # Test connection establishment
        assert influx_manager.is_connected() is True
        
        # Test connection parameters
        assert influx_manager.url == settings.INFLUXDB_URL
        assert influx_manager.token == settings.INFLUXDB_TOKEN
        assert influx_manager.org == settings.INFLUXDB_ORG

    def test_bucket_structure(self, influx_manager):
        """Test bucket creation and management."""
        test_bucket = "test_market_data"
        
        # Test bucket creation
        bucket = influx_manager.create_bucket(test_bucket)
        assert bucket is not None
        assert bucket.name == test_bucket
        
        # Test bucket exists
        assert influx_manager.bucket_exists(test_bucket) is True
        
        # Test bucket deletion
        influx_manager.delete_bucket(test_bucket)
        assert influx_manager.bucket_exists(test_bucket) is False

    def test_retention_policy(self, influx_manager):
        """Test retention policy setup and verification."""
        test_bucket = "test_retention"
        retention_hours = 24  # 1 day retention
        
        # Create bucket with retention policy
        bucket = influx_manager.create_bucket(
            name=test_bucket,
            retention_hours=retention_hours
        )
        assert bucket is not None
        
        # Verify retention policy
        retention = influx_manager.get_retention_policy(test_bucket)
        assert retention == timedelta(hours=retention_hours)
        
        # Clean up
        influx_manager.delete_bucket(test_bucket)

    def test_default_bucket_setup(self, influx_manager):
        """Test default market data buckets are properly set up."""
        default_buckets = [
            "market_data_m1",   # 1-minute data
            "market_data_m5",   # 5-minute data
            "market_data_m15",  # 15-minute data
            "market_data_h1",   # 1-hour data
            "market_data_h4",   # 4-hour data
            "market_data_d1"    # Daily data
        ]
        
        # Ensure all default buckets exist
        for bucket_name in default_buckets:
            assert influx_manager.bucket_exists(bucket_name) is True
            
            # Verify appropriate retention policy based on timeframe
            retention = influx_manager.get_retention_policy(bucket_name)
            if "m1" in bucket_name:
                assert retention == timedelta(days=7)  # Keep 1m data for 1 week
            elif "m5" in bucket_name:
                assert retention == timedelta(days=14)  # Keep 5m data for 2 weeks
            elif "m15" in bucket_name:
                assert retention == timedelta(days=30)  # Keep 15m data for 1 month
            elif "h1" in bucket_name:
                assert retention == timedelta(days=90)  # Keep 1h data for 3 months
            elif "h4" in bucket_name:
                assert retention == timedelta(days=180)  # Keep 4h data for 6 months
            elif "d1" in bucket_name:
                assert retention == timedelta(days=365)  # Keep daily data for 1 year

    def test_error_handling(self, influx_manager):
        """Test error handling for invalid operations."""
        # Test creating bucket with invalid name
        with pytest.raises(ValueError):
            influx_manager.create_bucket("")
        
        # Test creating duplicate bucket
        test_bucket = "test_duplicate"
        influx_manager.create_bucket(test_bucket)
        
        with pytest.raises(InfluxDBError):
            influx_manager.create_bucket(test_bucket)
            
        # Clean up
        influx_manager.delete_bucket(test_bucket)
        
        # Test deleting non-existent bucket
        with pytest.raises(InfluxDBError):
            influx_manager.delete_bucket("non_existent_bucket")
