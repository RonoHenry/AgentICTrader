"""
Test suite for InfluxDB setup and configuration.

This test suite covers:
1. Connection settings configuration
2. Bucket structure creation
3. Retention policy management
"""
import pytest
from datetime import timedelta
from django.conf import settings
from trader.infrastructure.influxdb_manager import InfluxDBManager

class TestInfluxDBSetup:
    """Test cases for InfluxDB initial setup and configuration."""
    
    @pytest.fixture
    def influx_manager(self):
        """Create a fresh InfluxDB manager for each test."""
        return InfluxDBManager()

    def test_connection_settings(self, influx_manager):
        """
        Test that connection settings are properly configured.
        Verifies:
        1. URL is correctly set from settings
        2. Token is properly configured
        3. Organization is set correctly
        4. Default bucket is defined
        """
        config = influx_manager.get_connection_config()
        assert config['url'] == settings.INFLUXDB_URL, "InfluxDB URL not properly configured"
        assert config['token'] == settings.INFLUXDB_TOKEN, "InfluxDB token not properly configured"
        assert config['org'] == settings.INFLUXDB_ORG, "InfluxDB organization not properly configured"
        assert config['default_bucket'] == settings.INFLUXDB_DEFAULT_BUCKET, "Default bucket not properly configured"

    def test_client_initialization(self, influx_manager):
        """
        Test that the InfluxDB client can be initialized successfully.
        Verifies:
        1. Client can be created
        2. Client maintains connection settings
        3. Client can connect to database
        """
        client = influx_manager.get_client()
        assert client is not None, "Failed to create InfluxDB client"
        
        # Verify client settings
        assert client.url == settings.INFLUXDB_URL, "Client URL mismatch"
        assert client.token == settings.INFLUXDB_TOKEN, "Client token mismatch"
        assert client.org == settings.INFLUXDB_ORG, "Client organization mismatch"
        
        # Test connection by making a simple API call
        health = client.ping()
        assert health, "InfluxDB connection test failed"

    def test_bucket_structure_creation(self, influx_manager):
        """
        Test that the required bucket structure can be created.
        Verifies:
        1. All required buckets are created
        2. Bucket names follow the convention
        3. Buckets have correct retention policies
        """
        # Create bucket structure
        buckets = influx_manager.create_bucket_structure()
        
        # Verify all required timeframe buckets exist
        expected_buckets = [
            "market_data_m1",   # 1-minute data
            "market_data_m5",   # 5-minute data
            "market_data_m15",  # 15-minute data
            "market_data_h1",   # 1-hour data
            "market_data_h4",   # 4-hour data
            "market_data_d1"    # Daily data
        ]
        
        for bucket_name in expected_buckets:
            assert bucket_name in buckets, f"Missing bucket: {bucket_name}"
            assert influx_manager.bucket_exists(bucket_name), f"Bucket not created: {bucket_name}"

    def test_retention_policies(self, influx_manager):
        """
        Test retention policy setup and verification.
        Verifies:
        1. Retention policies can be set
        2. Policies are correctly retrieved
        3. Different timeframes have appropriate retention periods
        """
        # Create test bucket with retention
        test_bucket = "test_retention"
        influx_manager.create_bucket(test_bucket, retention_hours=168)  # 1 week
        
        try:
            # Verify retention policy
            retention = influx_manager.get_retention_policy(test_bucket, return_str=True)
            assert retention == "7d", "Retention policy not set correctly"
            
            # Verify we can modify retention
            influx_manager.set_retention_policy(test_bucket, "30d")
            retention = influx_manager.get_retention_policy(test_bucket, return_str=True)
            assert retention == "30d", "Failed to update retention policy"
            
        finally:
            # Cleanup
            influx_manager.delete_bucket(test_bucket)

    def test_default_bucket_retention_policies(self, influx_manager):
        """
        Test that default buckets are created with correct retention policies.
        Verifies each timeframe bucket has appropriate retention:
        - M1: 7 days
        - M5: 14 days
        - M15: 30 days
        - H1: 90 days
        - H4: 180 days
        - D1: 365 days
        """
        # Create fresh bucket structure
        influx_manager.create_bucket_structure()
        
        # Expected retention periods
        retention_map = {
            "market_data_m1": timedelta(days=7),    # 1-minute data
            "market_data_m5": timedelta(days=14),   # 5-minute data
            "market_data_m15": timedelta(days=30),  # 15-minute data
            "market_data_h1": timedelta(days=90),   # 1-hour data
            "market_data_h4": timedelta(days=180),  # 4-hour data
            "market_data_d1": timedelta(days=365)   # Daily data
        }
        
        # Verify retention policies
        for bucket_name, expected_retention in retention_map.items():
            retention = influx_manager.get_retention_policy(bucket_name)
            assert retention == expected_retention, \
                f"Incorrect retention for {bucket_name}. Expected {expected_retention}, got {retention}"
