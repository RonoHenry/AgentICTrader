"""
Test InfluxDB infrastructure setup and configuration.
"""
import pytest
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch
from trader.infrastructure.timeseries import TimeseriesManager, TimeseriesBucket, OHLCVPoint

class TestInfluxDBSetup:
    @pytest.fixture
    def influx_client(self):
        """Create a test InfluxDB client."""
        client = InfluxDBClient(
            url=settings.DATABASES['timeseries']['HOST'],
            token=settings.DATABASES['timeseries']['TOKEN'],
            org="agentic"
        )
        yield client
        client.close()

    def test_connection(self, influx_client):
        """Test that we can connect to InfluxDB."""
        health = influx_client.health()
        assert health.status == "pass"
        assert influx_client.ping() is True

    def test_bucket_creation(self, influx_client):
        """Test that we can create and manage buckets."""
        bucket_name = "test_market_data"
        retention = 3600  # 1 hour for testing
        
        # Create bucket API
        buckets_api = influx_client.buckets_api()
        
        # Create new bucket
        bucket = buckets_api.create_bucket(
            bucket_name=bucket_name,
            retention_rules=[{"everySeconds": retention}],
            org="agentic"
        )
        
        # Verify bucket exists
        found = buckets_api.find_bucket_by_name(bucket_name)
        assert found is not None
        assert found.name == bucket_name
        
        # Clean up
        buckets_api.delete_bucket(bucket)

    def test_write_and_read(self, influx_client):
        """Test that we can write and read timeseries data."""
        bucket_name = "test_market_data"
        measurement = "EURUSD"
        
        # Create test bucket
        buckets_api = influx_client.buckets_api()
        bucket = buckets_api.create_bucket(bucket_name=bucket_name, org="agentic")
        
        try:
            # Write test data
            write_api = influx_client.write_api(write_options=SYNCHRONOUS)
            current_time = datetime.utcnow()
            
            point = Point(measurement)\
                .time(current_time)\
                .field("open", 1.1000)\
                .field("high", 1.1100)\
                .field("low", 1.0900)\
                .field("close", 1.1050)\
                .field("volume", 1000)
                
            write_api.write(bucket=bucket_name, record=point)
            
            # Read test data
            query = f'from(bucket:"{bucket_name}") |> range(start: -1h)'
            result = influx_client.query_api().query(query=query)
            
            # Verify data
            assert len(result) > 0
            assert len(result[0].records) > 0
            record = result[0].records[0]
            assert record.get_measurement() == measurement
            assert record.get_value() == 1.1050  # close price
        
        finally:
            # Clean up
            buckets_api.delete_bucket(bucket)

    def test_retention_policy(self, influx_client):
        """Test that retention policies are working."""
        bucket_name = "test_retention"
        short_retention = 3600  # 1 hour
        
        # Create bucket with short retention
        buckets_api = influx_client.buckets_api()
        bucket = buckets_api.create_bucket(
            bucket_name=bucket_name,
            retention_rules=[{"everySeconds": short_retention}],
            org="agentic"
        )
        
        try:
            # Write old data that should be deleted
            write_api = influx_client.write_api(write_options=SYNCHRONOUS)
            old_time = datetime.utcnow() - timedelta(hours=2)
            
            point = Point("EURUSD")\
                .time(old_time)\
                .field("close", 1.1000)
                
            write_api.write(bucket=bucket_name, record=point)
            
            # Write recent data that should be kept
            recent_time = datetime.utcnow()
            point = Point("EURUSD")\
                .time(recent_time)\
                .field("close", 1.2000)
                
            write_api.write(bucket=bucket_name, record=point)
            
            # Query data
            query = f'from(bucket:"{bucket_name}") |> range(start: -3h)'
            result = influx_client.query_api().query(query=query)
            
            # We should only see the recent data
            records = result[0].records if result else []
            assert len(records) == 1
            assert records[0].get_value() == 1.2000
            
        finally:
            # Clean up
            buckets_api.delete_bucket(bucket)
