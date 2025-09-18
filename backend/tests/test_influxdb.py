"""
Test InfluxDB connection and data writing.
"""
import pytest
import asyncio
from datetime import datetime, timezone, UTC, timedelta
from influxdb_client import Point
from influxdb_client import InfluxDBClient as BaseInfluxDBClient
from trader.infrastructure.influxdb_client import InfluxDBClient

@pytest.fixture(scope="function")
def influx_client():
    """Create an InfluxDB client for testing."""
    # First create raw client to set up bucket
    raw_client = BaseInfluxDBClient(
        url="http://localhost:8087",
        token="test-token",
        org="agentic"
    )
    
    # Create bucket if it doesn't exist
    buckets_api = raw_client.buckets_api()
    bucket = buckets_api.find_bucket_by_name("market_data")
    if not bucket:
        buckets_api.create_bucket(
            bucket_name="market_data",
            org="agentic",
            retention_rules=[],
        )
    
    # Clean up old data
    delete_api = raw_client.delete_api()
    start = "1970-01-01T00:00:00Z"  # Beginning of time
    stop = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    
    # Delete each measurement type separately since OR operator is not supported
    measurements = ['tick', 'ohlcv', 'test_measurement']
    for measurement in measurements:
        delete_api.delete(
            start=start,
            stop=stop,
            predicate=f'_measurement="{measurement}"',
            bucket="market_data",
            org="agentic"
        )
    
    # Create our wrapper client for testing
    client = InfluxDBClient(
        url="http://localhost:8087",
        token="test-token",
        org="agentic",
        debug=True
    )
    
    yield client
    
    # Clean up again after test
    stop = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    measurements = ['tick', 'ohlcv', 'test_measurement']
    for measurement in measurements:
        delete_api.delete(
            start=start,
            stop=stop,
            predicate=f'_measurement="{measurement}"',
            bucket="market_data",
            org="agentic"
        )
    client.close()
    raw_client.close()

def test_influxdb_connection(influx_client):
    """Test that we can connect to InfluxDB."""
    # Basic connectivity test - just check that the client's raw client is accessible
    assert influx_client.client is not None
    assert influx_client.write_api is not None
    assert influx_client.query_api is not None

@pytest.mark.asyncio
async def test_influxdb_write_and_query(influx_client):
    """Test writing and querying data from InfluxDB."""
    # Prepare test data using Point
    # Write point with current timestamp
    now = datetime.now(UTC)
    point = (Point("test_measurement")
            .tag("test_tag", "test_value")
            .field("test_field", 123.45)
            .time(now))
    
    # Write data
    try:
        await influx_client.write("market_data", [point])
        
        # Give InfluxDB a moment to process the write
        await asyncio.sleep(0.5)
        
        # Query with precise filtering including tag value
        query = '''
        from(bucket: "market_data")
            |> range(start: -1h)
            |> filter(fn: (r) => r._measurement == "test_measurement")
            |> filter(fn: (r) => r._field == "test_field")
            |> filter(fn: (r) => r.test_tag == "test_value")
            |> filter(fn: (r) => r._value == 123.45)
        '''
        result = await influx_client.query(query)
        assert len(result) > 0
        for record in result:
            assert record["_field"] == "test_field"
            assert record["_value"] == 123.45
            assert record["test_tag"] == "test_value"

    finally:
        influx_client.close()  # Just close the client, cleanup is handled by the fixture
