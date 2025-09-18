"""
Tests for market data ingestion pipeline and InfluxDB storage.
"""
import pytest
import asyncio
import logging
from decimal import Decimal
from datetime import datetime, UTC, timedelta
from unittest.mock import AsyncMock
from influxdb_client import Point, WriteOptions

from .docker_setup import docker_setup  # Import the Docker setup

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

from trader.infrastructure.market_data_types import TickData
from trader.infrastructure.market_data_pipeline import MarketDataPipeline
from trader.infrastructure.influxdb_client import InfluxDBClient
from trader.infrastructure.deriv_api import DerivAPIClient

@pytest.fixture
async def influx_client(docker_setup):
    """Create test InfluxDB client with robust cleanup."""
    async def verify_bucket_empty(client, max_attempts=5, base_sleep=2):
        """Helper to verify bucket is empty with exponential backoff."""
        query = '''
        from(bucket: "market_data")
            |> range(start: -100y)
        '''
        
        for attempt in range(max_attempts):
            try:
                result = await client.query(query)
                if not result:
                    logger.info("Bucket verified empty")
                    return True
                    
                logger.warning(f"Attempt {attempt + 1}: {len(result)} records remain")
                # More detailed logging about remaining records
                if result:
                    measurements = set(r.get('_measurement') for r in result if r.get('_measurement'))
                    logger.warning(f"Remaining measurements: {measurements}")
                
                sleep_time = base_sleep * (2 ** attempt)
                logger.info(f"Waiting {sleep_time}s before next check...")
                await asyncio.sleep(sleep_time)
            except Exception as e:
                logger.error(f"Error checking bucket contents (attempt {attempt + 1}): {e}")
                await asyncio.sleep(base_sleep)
                
        return False

    async def clean_bucket(client, retries=3):
        """Helper to clean bucket with multiple attempts."""
        for attempt in range(retries):
            try:
                logger.info(f"Cleaning attempt {attempt + 1}/{retries}")
                
                # Delete each measurement separately to ensure thorough cleanup
                # First get list of measurements
                query = '''
                from(bucket: "market_data")
                    |> range(start: -100y)
                    |> distinct(column: "_measurement")
                '''
                measurements = await client.query(query)
                for measurement in measurements:
                    measurement_name = measurement.get("_value")
                    if measurement_name:
                        logger.info(f"Deleting measurement: {measurement_name}")
                        await client.delete_data(
                            bucket="market_data",
                            start="1970-01-01T00:00:00Z",
                            stop="2030-12-31T23:59:59Z",
                            measurement=measurement_name
                        )

                # Verify the deletion worked
                if await verify_bucket_empty(client):
                    logger.info("Bucket successfully cleaned")
                    return True

            except Exception as e:
                logger.error(f"Error during cleanup attempt {attempt + 1}: {e}")
                await asyncio.sleep(2 * (attempt + 1))
                
        return False

    # Create and configure client
    client = InfluxDBClient(
        url="http://localhost:8087",
        token="test-token",
        org="agentic",
        debug=True
    )
    
    # Verify connection with retries
    max_ping_attempts = 3
    for attempt in range(max_ping_attempts):
        try:
            if client.ping():
                logger.info("Successfully connected to InfluxDB")
                break
            else:
                logger.warning(f"Ping attempt {attempt + 1} failed")
                await asyncio.sleep(2)
        except Exception as e:
            if attempt == max_ping_attempts - 1:
                pytest.fail(f"Could not connect to InfluxDB after {max_ping_attempts} attempts: {e}")
            logger.warning(f"Connection attempt {attempt + 1} failed: {e}")
            await asyncio.sleep(2)
    
    # Initialize and clean bucket
    try:
        logger.info("Starting bucket cleanup")
        if not await clean_bucket(client):
            pytest.fail("Failed to clean bucket after all attempts")
        
        logger.info("Bucket initialization complete")
    except Exception as e:
        pytest.fail(f"Failed to initialize bucket: {e}")
    
    yield client
    
    # Teardown cleanup
    logger.info("Starting teardown cleanup")
    try:
        if not await clean_bucket(client):
            logger.error("Failed to fully clean bucket during teardown")
        
        client.close()
        logger.info("Client closed successfully")
    except Exception as e:
        logger.error(f"Error during teardown: {e}")
        # Don't raise here as it's teardown

@pytest.fixture
def mock_deriv_client(mocker):
    """Create mock Deriv API client."""
    client = mocker.MagicMock(spec=DerivAPIClient)
    
    async def mock_subscribe_ticks(symbol):
        # Simulate tick stream
        ticks = [
            TickData(
                symbol="frxEURUSD",
                price=Decimal("1.23456"),
                timestamp=datetime.now(UTC),
                pip_size=5
            ),
            TickData(
                symbol="frxEURUSD",
                price=Decimal("1.23458"),
                timestamp=datetime.now(UTC),
                pip_size=5
            )
        ]
        for tick in ticks:
            yield tick
    
    client.subscribe_ticks = mock_subscribe_ticks
    return client

@pytest.fixture
async def pipeline(influx_client, mock_deriv_client):
    """Create test data pipeline."""
    # Use a small batch size for testing to ensure writes happen quickly
    pipeline = MarketDataPipeline(
        deriv_client=mock_deriv_client,
        influx_client=influx_client,
        bucket="market_data",
        batch_size=2  # Small batch size for testing
    )
    
    # Clean up any existing data
    pipeline.tick_buffer = {}
    pipeline.current_candles = {}
    
    return pipeline

@pytest.mark.asyncio
async def test_tick_ingestion(pipeline, influx_client):
    """Test ingestion of tick data into InfluxDB."""
    # Process some ticks directly to ensure they get written
    symbol = "frxEURUSD"
    pipeline.batch_size = 2  # Small batch size for testing
    
    # Generate some ticks with different timestamps
    base_time = datetime.now(UTC)
    ticks = []
    from datetime import timedelta
    for i in range(5):
        tick = TickData(
            symbol=symbol,
            price=Decimal(f"1.2345{i}"),
            timestamp=base_time + timedelta(seconds=i),
            pip_size=5
        )
        ticks.append(tick)
        
        # Process tick and track buffer size
        await pipeline.process_tick(tick)
        buffer_size = len(pipeline.tick_buffer.get(symbol, []))
        logger.info(f"Buffer size after tick {i+1}: {buffer_size}")
        
        # Write batch if we've reached batch size
        if buffer_size >= pipeline.batch_size:
            logger.info(f"Writing batch of {buffer_size} ticks")
            await pipeline.write_tick_batch(symbol)
            
    # Force write any remaining ticks
    logger.info(f"Remaining ticks in buffer: {len(pipeline.tick_buffer.get(symbol, []))}")
    if pipeline.tick_buffer.get(symbol):
        logger.info("Forcing write of remaining ticks")
        await pipeline.write_tick_batch(symbol, force=True)

        # Give InfluxDB more time to process all writes
        logger.info("Waiting for InfluxDB to process writes...")
        await asyncio.sleep(5)  # Increased sleep time
        
        # Query with a larger time window
        query = f'''
            from(bucket: "market_data")
                |> range(start: -15m)
                |> filter(fn: (r) => r.symbol == "{symbol}")
                |> filter(fn: (r) => r._measurement == "tick")
                |> filter(fn: (r) => r._field == "price")
                |> sort(columns: ["_time"])
                |> limit(n: 100)
            '''
        result = await influx_client.query(query)
        
        if len(result) != len(ticks):
            # Log detailed information about what we got
            actual_ticks = [f"{point['_time']}: {point['_value']}" for point in result]
            logger.error(f"Found {len(result)} ticks: {actual_ticks}")
            logger.error(f"Expected {len(ticks)} ticks: {[str(t.price) for t in ticks]}")
            
        assert len(result) == len(ticks), f"Expected {len(ticks)} points but got {len(result)}"    # Convert expected prices to strings for comparison
    # Convert expected prices to strings with normalized format
    expected_prices = [f"{float(tick.price):.4f}" for tick in ticks]
    actual_prices = [f"{float(point['_value']):.4f}" for point in result]

    # Verify all expected prices are present, ignoring trailing zeros
    for i, price in enumerate(expected_prices):
        assert actual_prices[i] == price, f"Price mismatch at position {i}: expected {price} but got {actual_prices[i]}"@pytest.mark.asyncio
async def test_ohlcv_transformation(pipeline, influx_client):
    """Test transformation of ticks to OHLCV and storage."""
    symbol = "frxEURUSD"
    timeframe = "1m"
    
    # Create ticks that will force a minute candle to complete
    base_time = datetime.now(UTC).replace(second=0, microsecond=0)
    prices = [1.23450, 1.23460, 1.23440, 1.23455]  # Ensure clear OHLCV values
    
    # Send ticks in the same minute
    for i, price in enumerate(prices):
        tick = TickData(
            symbol=symbol,
            price=Decimal(str(price)),
            timestamp=base_time.replace(second=i*15),  # Space them out within the minute
            pip_size=5
        )
        await pipeline.process_tick(tick)
    
    # Force OHLCV write by sending a tick in the next minute
    next_minute = base_time.replace(minute=base_time.minute + 1)
    final_tick = TickData(
        symbol=symbol,
        price=Decimal("1.23457"),
        timestamp=next_minute,
        pip_size=5
    )
    await pipeline.process_tick(final_tick)
    
    # Give InfluxDB a moment to process the write
    await asyncio.sleep(0.5)
    
    # Query OHLCV data with pivot to get all fields in one record
    query = f'''
    from(bucket: "market_data")
        |> range(start: -2h)
        |> filter(fn: (r) => r._measurement == "ohlcv")
        |> filter(fn: (r) => r.symbol == "{symbol}")
        |> filter(fn: (r) => r.timeframe == "{timeframe}")
        |> pivot(rowKey: ["_time", "symbol", "timeframe"], columnKey: ["_field"], valueColumn: "_value")
    '''
    result = await influx_client.query(query)
    assert len(result) > 0
    
    candle = result[0]
    for field in ["open", "high", "low", "close", "volume"]:
        assert field in candle, f"Missing {field} field in candle data"
    
    # Verify OHLCV values are logical
    assert float(candle["high"]) >= float(candle["low"])
    assert float(candle["open"]) >= float(candle["low"]) and float(candle["open"]) <= float(candle["high"])
    assert float(candle["close"]) >= float(candle["low"]) and float(candle["close"]) <= float(candle["high"])

@pytest.mark.asyncio
async def test_data_validation(pipeline):
    """Test data validation in the pipeline."""
    # Test with invalid tick data
    invalid_tick = TickData(
        symbol="INVALID",
        price=Decimal("-1.0"),  # Invalid negative price
        timestamp=datetime.now(UTC),
        pip_size=5
    )
    
    with pytest.raises(ValueError):
        await pipeline.validate_tick(invalid_tick)

@pytest.mark.asyncio
async def test_error_handling(pipeline, caplog):
    """Test error handling in the pipeline."""
    # Make batch size 1 to trigger immediate write
    pipeline.batch_size = 1
    
    # Simulate network error for write operations
    pipeline.influx_client.write = AsyncMock(side_effect=Exception("Network error"))
    
    # Try to process a tick which should trigger the write error
    tick = TickData(
        symbol="frxEURUSD",
        price=Decimal("1.23456"),
        timestamp=datetime.now(UTC),
        pip_size=5
    )
    
    # Error should be raised when processing the tick
    with pytest.raises(Exception) as exc_info:
        await pipeline.process_tick(tick)
    
    # Verify error was logged
    assert "Network error" in str(exc_info.value)
    assert any("Error" in record.message for record in caplog.records)

@pytest.mark.asyncio
async def test_batch_writing(pipeline, influx_client):
    """Test batch writing of ticks to InfluxDB."""
    symbol = "frxEURUSD"
    
    # Configure small batch size for testing
    pipeline.batch_size = 2
    
    # Reset any existing data
    pipeline.tick_buffer = {}
    
    # Create ticks with different timestamps and prices
    base_time = datetime.now(UTC)
    prices = ["1.23450", "1.23451", "1.23452", "1.23453", "1.23454"]
    ticks = [
        TickData(
            symbol=symbol,
            price=Decimal(price),
            timestamp=base_time + timedelta(seconds=i),
            pip_size=5
        ) for i, price in enumerate(prices)
    ]
    
    # Process ticks in batch
    for tick in ticks:
        await pipeline.process_tick(tick)
        if len(pipeline.tick_buffer.get(symbol, [])) >= pipeline.batch_size:
            await pipeline.write_tick_batch(symbol)
    
        # Force write all remaining ticks regardless of batch size
        if pipeline.tick_buffer.get(symbol):
            while pipeline.tick_buffer.get(symbol):
                await pipeline.write_tick_batch(symbol, force=True)
            
        # Give InfluxDB more time to process all writes and replicate
        await asyncio.sleep(5)    # Query ticks written in the last minute
    query = f'''
    from(bucket: "market_data")
        |> range(start: -1m)
        |> filter(fn: (r) => r.symbol == "{symbol}")
        |> filter(fn: (r) => r._measurement == "tick")
        |> filter(fn: (r) => r._field == "price")
        |> sort(columns: ["_time"])
    '''
    
    result = await influx_client.query(query)
    
    # Verify we got all ticks
    assert len(result) == len(prices), f"Expected {len(prices)} ticks but got {len(result)}"
    
    # Convert values for consistent comparison while preserving precision
    actual_prices = [float(point['_value']) for point in result]
    expected_prices = [float(price) for price in prices]
    
    # Verify each price matches at its original precision
    for expected, actual in zip(expected_prices, actual_prices):
        # Convert back to string with enough precision and compare
        assert f"{actual:.5f}" == f"{expected:.5f}", f"Price mismatch: expected {expected:.5f} but got {actual:.5f}"
        
    # Verify we got prices in the expected order
    assert len(actual_prices) == len(expected_prices), f"Got wrong number of prices: {actual_prices}"