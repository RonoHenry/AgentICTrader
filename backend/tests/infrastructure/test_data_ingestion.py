"""
Tests for data ingestion pipeline.
"""
import pytest
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from trader.infrastructure.data_ingestion import MarketDataIngestionPipeline
from trader.infrastructure.market_data_types import TickData, TickHistoryResponse

@pytest.fixture
def ingestion_pipeline():
    """Create a test ingestion pipeline."""
    return MarketDataIngestionPipeline()

@pytest.fixture
def sample_tick():
    """Create a sample tick."""
    return TickData(
        symbol="EURUSD",
        timestamp=datetime.now(timezone.utc),
        price=Decimal("1.1234"),
        pip_size=4
    )

@pytest.fixture
def sample_history():
    """Create sample historical data."""
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    ticks = []
    
    # Create test data: multiple ticks per minute
    for minute in range(60):  # 1 hour of data
        base_price = Decimal("1.1234") + Decimal(str(minute * 0.0001))
        # Add multiple ticks per minute
        for tick in range(5):  # 5 ticks per minute
            tick_price = base_price + Decimal(str(tick * 0.00001))
            ticks.append(
                TickData(
                    symbol="EURUSD",
                    timestamp=now - timedelta(minutes=minute),
                    price=tick_price,
                    pip_size=4
                )
            )
            
    return TickHistoryResponse(
        symbol="EURUSD",
        ticks=sorted(ticks, key=lambda x: x.timestamp),  # Ensure ticks are sorted
        pip_size=4
    )

@pytest.mark.asyncio
async def test_tick_ingestion(ingestion_pipeline, sample_tick):
    """Test ingesting a single tick."""
    await ingestion_pipeline.ingest_tick(sample_tick)
    assert len(ingestion_pipeline.buffer[sample_tick.symbol]) == 1
    assert ingestion_pipeline.buffer[sample_tick.symbol][0] == sample_tick

@pytest.mark.asyncio
async def test_buffer_processing(ingestion_pipeline, sample_tick):
    """Test processing buffered ticks."""
    # Fill buffer with data for multiple minutes
    symbol = sample_tick.symbol
    base_time = sample_tick.timestamp.replace(second=0, microsecond=0)
    ticks_per_minute = 5
    minutes = 10
    
    for minute in range(minutes):
        base_price = sample_tick.price + Decimal(str(minute * 0.0001))
        current_time = base_time + timedelta(minutes=minute)
        
        # Add multiple ticks for each minute
        for tick_num in range(ticks_per_minute):
            tick = TickData(
                symbol=symbol,
                timestamp=current_time,
                price=base_price + Decimal(str(tick_num * 0.00001)),
                pip_size=4
            )
            await ingestion_pipeline.ingest_tick(tick)
    
    # Explicitly process buffer
    await ingestion_pipeline.process_buffer(symbol)
    
    # Buffer should be empty after processing
    assert len(ingestion_pipeline.buffer.get(symbol, [])) == 0
    
    # Check that data was written to InfluxDB
    latest_m1 = ingestion_pipeline.get_latest_candle(symbol, "M1")
    assert latest_m1 is not None
    assert latest_m1["symbol"] == symbol
    assert "open" in latest_m1
    assert "high" in latest_m1
    assert "low" in latest_m1
    assert "close" in latest_m1
    assert "volume" in latest_m1
    
    # Verify candle values
    assert float(latest_m1["volume"]) == ticks_per_minute  # Should be number of ticks in last minute
    assert float(latest_m1["high"]) > float(latest_m1["open"])  # High should be higher than open due to price increments

@pytest.mark.asyncio
async def test_history_ingestion(ingestion_pipeline, sample_history):
    """Test ingesting historical data."""
    await ingestion_pipeline.ingest_history(sample_history)
    
    # Check that data was written to InfluxDB
    latest_m1 = ingestion_pipeline.get_latest_candle(sample_history.symbol, "M1")
    assert latest_m1 is not None
    assert latest_m1["symbol"] == sample_history.symbol

def test_get_latest_candle(ingestion_pipeline, sample_tick):
    """Test retrieving latest candle."""
    symbol = sample_tick.symbol
    
    # Try getting latest candle for different timeframes
    for tf in ["M1", "M5", "M15", "H1", "H4", "D1"]:
        candle = ingestion_pipeline.get_latest_candle(symbol, tf)
        # May be None if no data exists yet
        if candle:
            assert candle["symbol"] == symbol
            assert "open" in candle
            assert "high" in candle
            assert "low" in candle
            assert "close" in candle
            assert "volume" in candle
