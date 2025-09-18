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
    def influx_manager(self, docker_services):
        """Create a test InfluxDB manager."""
        return InfluxDBManager()

    def test_connection_settings(self, influx_manager):
        """Test that connection settings are properly configured."""
        # Test connection configuration
        config = influx_manager.get_connection_config()
        assert config['url'] == settings.INFLUXDB_URL
        assert config['token'] == settings.INFLUXDB_TOKEN
        assert config['org'] == settings.INFLUXDB_ORG
        
        # Test client creation
        client = influx_manager.get_client()
        assert client is not None

    def test_bucket_structure(self, influx_manager):
        """Test bucket creation and management."""
        # Test creating bucket structure
        buckets = influx_manager.create_bucket_structure()
        assert len(buckets) > 0
        
        # Test bucket existence
        for bucket in buckets:
            assert influx_manager.bucket_exists(bucket) is True

    def test_retention_policy(self, influx_manager):
        """Test retention policy setup and verification."""
        # Create test bucket with initial retention policy
        test_bucket = "test_retention"
        influx_manager.create_bucket(test_bucket)
        
        # Set retention policy
        influx_manager.set_retention_policy(test_bucket, "7d")  # 7 days retention
        
        # Verify retention policy
        retention = influx_manager.get_retention_policy(test_bucket, return_str=True)
        assert retention == "7d"
        
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
        
        # Create fresh bucket structure
        influx_manager.create_bucket_structure()
        
        # Ensure all default buckets exist and have correct retention policies
        for bucket_name in default_buckets:
            assert influx_manager.bucket_exists(bucket_name) is True
            
            # Verify appropriate retention policy based on timeframe
            retention = influx_manager.get_retention_policy(bucket_name)
            print(f"\nTesting {bucket_name}:")
            print(f"Got retention: {retention} ({retention.days} days)")
            expected = None
            print(f"\nChecking '{bucket_name}':")
            print(f"  Contains '_m1': {'_m1' in bucket_name}")
            print(f"  Contains '_m5': {'_m5' in bucket_name}")
            print(f"  Contains '_m15': {'_m15' in bucket_name}")
            print(f"  Contains '_h1': {'_h1' in bucket_name}")
            print(f"  Contains '_h4': {'_h4' in bucket_name}")
            print(f"  Contains '_d1': {'_d1' in bucket_name}")
            
            if "_m1" in bucket_name and not "_m15" in bucket_name:
                expected = timedelta(days=7)  # Keep 1m data for 1 week
            elif "_m5" in bucket_name:
                expected = timedelta(days=14)  # Keep 5m data for 2 weeks
            elif "_m15" in bucket_name:
                expected = timedelta(days=30)  # Keep 15m data for 1 month
            elif "_h1" in bucket_name:
                expected = timedelta(days=90)  # Keep 1h data for 3 months
            elif "_h4" in bucket_name:
                expected = timedelta(days=180)  # Keep 4h data for 6 months
            elif "_d1" in bucket_name:
                expected = timedelta(days=365)  # Keep daily data for 1 year
            print(f"Expected: {expected} ({expected.days} days)")
            assert retention == expected

    def test_error_handling(self, influx_manager):
        """Test error handling for invalid operations."""
        # Test creating bucket with invalid name
        with pytest.raises(ValueError):
            influx_manager.create_bucket("")

        # Test creating duplicate bucket
        test_bucket = "test_duplicate"
        try:
            # First creation should succeed
            influx_manager.create_bucket(test_bucket)

            # Second creation should fail
            with pytest.raises(InfluxDBError) as exc_info:
                influx_manager.create_bucket(test_bucket)
            assert "already exists" in str(exc_info.value)
        finally:
            # Clean up
            try:
                influx_manager.delete_bucket(test_bucket)
            except:
                pass  # Ignore errors in cleanup
        
        # Test deleting non-existent bucket
        with pytest.raises(InfluxDBError) as exc_info:
            influx_manager.delete_bucket("non_existent_bucket")
        assert "not found" in str(exc_info.value)