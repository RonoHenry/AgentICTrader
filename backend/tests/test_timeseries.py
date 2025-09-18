"""
Test InfluxDB infrastructure setup and configuration.
"""
import pytest
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch
import time
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS
from django.conf import settings
from trader.infrastructure.timeseries import TimeseriesManager, TimeseriesBucket, OHLCVPoint

class TestInfluxDBSetup:
    def test_read_write_ohlcv(self):
        """Test writing and reading OHLCV data."""
        # Create a test OHLCV point
        test_point = OHLCVPoint(
            symbol="BTCUSD",
            timestamp=datetime(2022, 1, 1, tzinfo=timezone.utc),
            timeframe="1m",
            open=Decimal('100.00'),
            high=Decimal('110.00'),
            low=Decimal('90.00'),
            close=Decimal('105.00'),
            volume=1000
        )

        # Create InfluxDB client first
        client = InfluxDBClient(
            url="http://localhost:8087",
            token="test-token",
            org="agentic"
        )
        
        # Create TimeseriesManager with the client
        manager = TimeseriesManager(client=client)

        try:
            # Write test data
            success = manager.write_ohlcv(test_point)
            assert success, "Writing OHLCV data should succeed"

            # Add a small delay to ensure data is written
            time.sleep(0.1)

            # Read back the data for the same time period
            result = manager.read_ohlcv(
                symbol="BTCUSD",
                timeframe="1m",
                start_time=test_point.timestamp,
                end_time=test_point.timestamp
            )
            
            assert len(result) == 1, "Expected exactly one OHLCV record"
            assert result[0].timestamp == test_point.timestamp, "Timestamps should match exactly"
            assert result[0].open == test_point.open, "Open prices should match"
            assert result[0].high == test_point.high, "High prices should match"
            assert result[0].low == test_point.low, "Low prices should match"
            assert result[0].close == test_point.close, "Close prices should match"
            assert result[0].volume == test_point.volume, "Volumes should match"

        finally:
            # Clean up
            if hasattr(manager, 'client'):
                manager.client.close()

    @pytest.fixture
    def influx_client(self):
        """Create a test InfluxDB client."""
        client = InfluxDBClient(
            url="http://localhost:8087",
            token="test-token",
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
        
        # Delete bucket if it exists
        existing_bucket = buckets_api.find_bucket_by_name(bucket_name)
        if existing_bucket is not None:
            buckets_api.delete_bucket(existing_bucket)
        
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
        
        # Delete bucket if it exists
        existing_bucket = buckets_api.find_bucket_by_name(bucket_name)
        if existing_bucket is not None:
            buckets_api.delete_bucket(existing_bucket)
        
        # Create test bucket
        bucket = buckets_api.create_bucket(bucket_name=bucket_name, org="agentic")
        
        try:
            # Write test data
            write_api = influx_client.write_api(write_options=SYNCHRONOUS)
            current_time = datetime.now(timezone.utc)
            
            point = Point(measurement)\
                .time(current_time)\
                .field("open", 1.1000)\
                .field("high", 1.1100)\
                .field("low", 1.0900)\
                .field("close", 1.1050)\
                .field("volume", 1000)
                
            write_api.write(bucket=bucket_name, record=point)
            
            # Read test data - use specific time range
            start_time = current_time - timedelta(minutes=5)
            end_time = current_time + timedelta(minutes=5)
            query = f'''
                from(bucket:"{bucket_name}")
                    |> range(start: {start_time.isoformat()}, stop: {end_time.isoformat()})
                    |> filter(fn: (r) => r["_measurement"] == "{measurement}")
            '''
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
        
        # Delete bucket if it exists
        existing_bucket = buckets_api.find_bucket_by_name(bucket_name)
        if existing_bucket is not None:
            buckets_api.delete_bucket(existing_bucket)
            
        # Create bucket with short retention
        bucket = buckets_api.create_bucket(
            bucket_name=bucket_name,
            retention_rules=[{"everySeconds": short_retention}],
            org="agentic"
        )
        
        try:
            write_api = influx_client.write_api(write_options=SYNCHRONOUS)
            now = datetime.now(timezone.utc)
            
            # Write data points with different timestamps
            data_points = [
                (now - timedelta(minutes=30), 1.2000),  # Within retention
                (now - timedelta(minutes=45), 1.1500),  # Within retention
                (now - timedelta(minutes=15), 1.2500),  # Within retention
            ]
            
            for timestamp, price in data_points:
                point = Point("EURUSD")\
                    .time(timestamp)\
                    .field("close", price)
                write_api.write(bucket=bucket_name, record=point)
            
            # Wait briefly for writes to complete
            from time import sleep
            sleep(1)
            
            # Query data with explicit time range
            start_time = now - timedelta(minutes=60)
            query = f'''
                from(bucket:"{bucket_name}")
                    |> range(start: {start_time.isoformat()}, stop: {now.isoformat()})
                    |> filter(fn: (r) => r["_measurement"] == "EURUSD")
            '''
            result = influx_client.query_api().query(query=query)
            
            # We should see all three data points
            records = result[0].records if result else []
            assert len(records) == 3
            
            # Verify timestamps are within retention period
            for record in records:
                record_time = record.get_time()
                age = now - record_time
                assert age.total_seconds() < short_retention
            
        finally:
            # Clean up
            buckets_api.delete_bucket(bucket)
