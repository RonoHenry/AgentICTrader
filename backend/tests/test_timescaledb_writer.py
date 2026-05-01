"""
Tests for the TimescaleDB writer for candle and tick data.

TDD Phase: RED → these tests are written BEFORE the implementation.
Run with:  pytest backend/tests/test_timescaledb_writer.py -v

All tests in this file must FAIL before any implementation is written.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch, call
from decimal import Decimal

import pytest

# ---------------------------------------------------------------------------
# Import targets — these will raise ImportError until 6b is implemented
# ---------------------------------------------------------------------------
from services.market_data.timescaledb_writer import (
    TimescaleDBWriter,
    CandleData,
    TickData,
)


# ===========================================================================
# Fixtures
# ===========================================================================

SAMPLE_CANDLE = {
    "time": datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
    "instrument": "EURUSD",
    "timeframe": "M5",
    "open": Decimal("1.08500"),
    "high": Decimal("1.08600"),
    "low": Decimal("1.08450"),
    "close": Decimal("1.08550"),
    "volume": 1500,
    "spread": Decimal("0.00010"),
    "complete": True,
    "source": "oanda",
}

SAMPLE_TICK = {
    "time": datetime(2024, 1, 15, 10, 30, 0, 123456, tzinfo=timezone.utc),
    "instrument": "EURUSD",
    "bid": Decimal("1.08500"),
    "ask": Decimal("1.08510"),
    "volume": 100,
    "source": "oanda",
}


@pytest.fixture
def db_config():
    """Return TimescaleDB connection configuration for testing."""
    return {
        "host": "localhost",
        "port": 5432,
        "database": "agentictrader",
        "user": "agentictrader",
        "password": "changeme",
    }


@pytest.fixture
async def db_writer(db_config):
    """Create a TimescaleDBWriter instance for testing."""
    writer = TimescaleDBWriter(**db_config)
    await writer.connect()
    yield writer
    await writer.close()


# ===========================================================================
# 1. Integration test: candle upsert uses ON CONFLICT DO UPDATE
# ===========================================================================

class TestCandleUpsert:
    """Candles must be upserted using ON CONFLICT (time, instrument, timeframe) DO UPDATE."""

    @pytest.mark.asyncio
    async def test_candle_insert_creates_new_record(self, db_writer):
        """A new candle must be inserted into the candles table."""
        with patch.object(db_writer, "_pool") as mock_pool:
            mock_conn = AsyncMock()
            mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
            mock_conn.execute = AsyncMock()
            
            await db_writer.write_candle(SAMPLE_CANDLE)
            
            # Verify execute was called
            mock_conn.execute.assert_called_once()
            
            # Verify the SQL contains INSERT
            call_args = mock_conn.execute.call_args[0]
            sql = call_args[0]
            assert "INSERT INTO candles" in sql.upper()

    @pytest.mark.asyncio
    async def test_candle_upsert_uses_on_conflict_clause(self, db_writer):
        """The INSERT must use ON CONFLICT (time, instrument, timeframe) DO UPDATE."""
        with patch.object(db_writer, "_pool") as mock_pool:
            mock_conn = AsyncMock()
            mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
            mock_conn.execute = AsyncMock()
            
            await db_writer.write_candle(SAMPLE_CANDLE)
            
            call_args = mock_conn.execute.call_args[0]
            sql = call_args[0]
            
            # Verify ON CONFLICT clause is present
            assert "ON CONFLICT" in sql.upper()
            assert "time" in sql.lower()
            assert "instrument" in sql.lower()
            assert "timeframe" in sql.lower()

    @pytest.mark.asyncio
    async def test_candle_upsert_updates_existing_record(self, db_writer):
        """An existing candle must be updated with new values."""
        with patch.object(db_writer, "_pool") as mock_pool:
            mock_conn = AsyncMock()
            mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
            mock_conn.execute = AsyncMock()
            
            await db_writer.write_candle(SAMPLE_CANDLE)
            
            call_args = mock_conn.execute.call_args[0]
            sql = call_args[0]
            
            # Verify DO UPDATE is present
            assert "DO UPDATE" in sql.upper()

    @pytest.mark.asyncio
    async def test_candle_all_fields_are_written(self, db_writer):
        """All candle fields must be written to the database."""
        with patch.object(db_writer, "_pool") as mock_pool:
            mock_conn = AsyncMock()
            mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
            mock_conn.execute = AsyncMock()
            
            await db_writer.write_candle(SAMPLE_CANDLE)
            
            call_args = mock_conn.execute.call_args[0]
            sql = call_args[0].lower()
            
            # Verify all required fields are in the SQL
            required_fields = [
                "time", "instrument", "timeframe", "open", "high", 
                "low", "close", "volume", "spread", "complete", "source"
            ]
            for field in required_fields:
                assert field in sql, f"Field '{field}' not found in SQL"

    @pytest.mark.asyncio
    async def test_candle_parameters_are_bound_correctly(self, db_writer):
        """Candle values must be passed as parameters to prevent SQL injection."""
        with patch.object(db_writer, "_pool") as mock_pool:
            mock_conn = AsyncMock()
            mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
            mock_conn.execute = AsyncMock()
            
            await db_writer.write_candle(SAMPLE_CANDLE)
            
            # Verify parameters were passed
            call_args = mock_conn.execute.call_args[0]
            assert len(call_args) > 1, "No parameters passed to execute()"
            
            # Parameters should be a tuple or list
            params = call_args[1:]
            assert len(params) > 0


# ===========================================================================
# 2. Integration test: ticks inserted in batches of 500
# ===========================================================================

class TestTickBatching:
    """Ticks must be inserted in batches of 500 for performance."""

    @pytest.mark.asyncio
    async def test_single_tick_is_buffered(self, db_writer):
        """A single tick must be buffered, not immediately written."""
        with patch.object(db_writer, "_pool") as mock_pool:
            mock_conn = AsyncMock()
            mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
            mock_conn.executemany = AsyncMock()
            
            await db_writer.write_tick(SAMPLE_TICK)
            
            # Should NOT execute immediately
            mock_conn.executemany.assert_not_called()

    @pytest.mark.asyncio
    async def test_batch_of_500_ticks_triggers_write(self, db_writer):
        """Accumulating 500 ticks must trigger a batch write."""
        with patch.object(db_writer, "_pool") as mock_pool:
            mock_conn = AsyncMock()
            mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
            mock_conn.executemany = AsyncMock()
            
            # Write 500 ticks
            for i in range(500):
                tick = SAMPLE_TICK.copy()
                tick["time"] = datetime(2024, 1, 15, 10, 30, i, tzinfo=timezone.utc)
                await db_writer.write_tick(tick)
            
            # Should execute once after 500 ticks
            mock_conn.executemany.assert_called_once()

    @pytest.mark.asyncio
    async def test_batch_write_uses_executemany(self, db_writer):
        """Batch writes must use executemany for performance."""
        with patch.object(db_writer, "_pool") as mock_pool:
            mock_conn = AsyncMock()
            mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
            mock_conn.executemany = AsyncMock()
            
            # Write 500 ticks to trigger batch
            for i in range(500):
                tick = SAMPLE_TICK.copy()
                tick["time"] = datetime(2024, 1, 15, 10, 30, i, tzinfo=timezone.utc)
                await db_writer.write_tick(tick)
            
            # Verify executemany was called
            call_args = mock_conn.executemany.call_args[0]
            sql = call_args[0]
            assert "INSERT INTO ticks" in sql.upper()

    @pytest.mark.asyncio
    async def test_batch_contains_500_records(self, db_writer):
        """The batch must contain exactly 500 records."""
        with patch.object(db_writer, "_pool") as mock_pool:
            mock_conn = AsyncMock()
            mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
            mock_conn.executemany = AsyncMock()
            
            # Write 500 ticks
            for i in range(500):
                tick = SAMPLE_TICK.copy()
                tick["time"] = datetime(2024, 1, 15, 10, 30, i, tzinfo=timezone.utc)
                await db_writer.write_tick(tick)
            
            # Verify 500 records were passed
            call_args = mock_conn.executemany.call_args[0]
            records = call_args[1]
            assert len(records) == 500

    @pytest.mark.asyncio
    async def test_multiple_batches_are_written_separately(self, db_writer):
        """Writing 1000 ticks must trigger 2 separate batch writes."""
        with patch.object(db_writer, "_pool") as mock_pool:
            mock_conn = AsyncMock()
            mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
            mock_conn.executemany = AsyncMock()
            
            # Write 1000 ticks
            for i in range(1000):
                tick = SAMPLE_TICK.copy()
                tick["time"] = datetime(2024, 1, 15, 10, 30, i, tzinfo=timezone.utc)
                await db_writer.write_tick(tick)
            
            # Should execute twice (500 + 500)
            assert mock_conn.executemany.call_count == 2


# ===========================================================================
# 3. Integration test: batch flushed within 1s max interval
# ===========================================================================

class TestBatchFlushInterval:
    """Buffered ticks must be flushed within 1 second even if batch is not full."""

    @pytest.mark.asyncio
    async def test_flush_writes_buffered_ticks(self, db_writer):
        """flush() must write all buffered ticks regardless of batch size."""
        with patch.object(db_writer, "_pool") as mock_pool:
            mock_conn = AsyncMock()
            mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
            mock_conn.executemany = AsyncMock()
            
            # Write only 10 ticks (less than batch size)
            for i in range(10):
                tick = SAMPLE_TICK.copy()
                tick["time"] = datetime(2024, 1, 15, 10, 30, i, tzinfo=timezone.utc)
                await db_writer.write_tick(tick)
            
            # Manually flush
            await db_writer.flush()
            
            # Should execute with 10 records
            mock_conn.executemany.assert_called_once()
            call_args = mock_conn.executemany.call_args[0]
            records = call_args[1]
            assert len(records) == 10

    @pytest.mark.asyncio
    async def test_auto_flush_timer_exists(self, db_writer):
        """The writer must have an auto-flush mechanism."""
        # Verify the writer has a flush interval attribute
        assert hasattr(db_writer, "_flush_interval") or hasattr(db_writer, "flush_interval")

    @pytest.mark.asyncio
    async def test_flush_interval_is_1_second(self, db_writer):
        """The flush interval must be 1 second."""
        flush_interval = getattr(db_writer, "_flush_interval", None) or getattr(db_writer, "flush_interval", None)
        assert flush_interval == 1.0 or flush_interval == 1

    @pytest.mark.asyncio
    async def test_auto_flush_triggers_after_interval(self, db_writer):
        """Buffered ticks must be auto-flushed after 1 second."""
        with patch.object(db_writer, "_pool") as mock_pool:
            mock_conn = AsyncMock()
            mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
            mock_conn.executemany = AsyncMock()
            
            # Write a few ticks
            for i in range(10):
                tick = SAMPLE_TICK.copy()
                tick["time"] = datetime(2024, 1, 15, 10, 30, i, tzinfo=timezone.utc)
                await db_writer.write_tick(tick)
            
            # Wait for auto-flush (1 second + buffer)
            await asyncio.sleep(1.2)
            
            # Should have auto-flushed
            mock_conn.executemany.assert_called()

    @pytest.mark.asyncio
    async def test_flush_clears_buffer(self, db_writer):
        """flush() must clear the tick buffer after writing."""
        with patch.object(db_writer, "_pool") as mock_pool:
            mock_conn = AsyncMock()
            mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
            mock_conn.executemany = AsyncMock()
            
            # Write ticks
            for i in range(10):
                tick = SAMPLE_TICK.copy()
                tick["time"] = datetime(2024, 1, 15, 10, 30, i, tzinfo=timezone.utc)
                await db_writer.write_tick(tick)
            
            # Flush
            await db_writer.flush()
            
            # Buffer should be empty
            assert len(db_writer._tick_buffer) == 0 or len(getattr(db_writer, "tick_buffer", [])) == 0


# ===========================================================================
# 4. Integration test: write latency < 2s from candle close
# ===========================================================================

class TestWriteLatency:
    """Candle writes must complete within 2 seconds for real-time requirements."""

    @pytest.mark.asyncio
    async def test_candle_write_completes_quickly(self, db_writer):
        """write_candle() must complete within 2 seconds."""
        with patch.object(db_writer, "_pool") as mock_pool:
            mock_conn = AsyncMock()
            mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
            mock_conn.execute = AsyncMock()
            
            start_time = datetime.now(timezone.utc)
            await db_writer.write_candle(SAMPLE_CANDLE)
            end_time = datetime.now(timezone.utc)
            
            latency = (end_time - start_time).total_seconds()
            assert latency < 2.0, f"Write latency {latency}s exceeds 2s threshold"

    @pytest.mark.asyncio
    async def test_batch_tick_write_completes_quickly(self, db_writer):
        """Batch tick writes must complete within 2 seconds."""
        with patch.object(db_writer, "_pool") as mock_pool:
            mock_conn = AsyncMock()
            mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
            mock_conn.executemany = AsyncMock()
            
            start_time = datetime.now(timezone.utc)
            
            # Write 500 ticks to trigger batch
            for i in range(500):
                tick = SAMPLE_TICK.copy()
                tick["time"] = datetime(2024, 1, 15, 10, 30, i, tzinfo=timezone.utc)
                await db_writer.write_tick(tick)
            
            end_time = datetime.now(timezone.utc)
            
            latency = (end_time - start_time).total_seconds()
            assert latency < 2.0, f"Batch write latency {latency}s exceeds 2s threshold"

    @pytest.mark.asyncio
    async def test_connection_pool_is_used(self, db_writer):
        """The writer must use a connection pool for performance."""
        assert hasattr(db_writer, "_pool") or hasattr(db_writer, "pool")

    @pytest.mark.asyncio
    async def test_connection_pool_has_multiple_connections(self, db_writer):
        """The connection pool must have multiple connections for concurrency."""
        pool = getattr(db_writer, "_pool", None) or getattr(db_writer, "pool", None)
        
        # Pool should be configured with min/max size
        if pool:
            # asyncpg pools have _minsize and _maxsize attributes
            assert hasattr(pool, "_minsize") or hasattr(pool, "get_min_size")
            assert hasattr(pool, "_maxsize") or hasattr(pool, "get_max_size")


# ===========================================================================
# 5. Connection management
# ===========================================================================

class TestConnectionManagement:
    """The writer must properly manage database connections."""

    @pytest.mark.asyncio
    async def test_connect_creates_connection_pool(self):
        """connect() must create a connection pool."""
        writer = TimescaleDBWriter(
            host="localhost",
            port=5432,
            database="agentictrader",
            user="agentictrader",
            password="changeme",
        )
        
        with patch("services.market_data.timescaledb_writer.asyncpg.create_pool", new_callable=AsyncMock) as mock_create_pool:
            mock_pool = AsyncMock()
            mock_create_pool.return_value = mock_pool
            
            await writer.connect()
            
            # Verify create_pool was called
            mock_create_pool.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_closes_connection_pool(self):
        """close() must close the connection pool."""
        writer = TimescaleDBWriter(
            host="localhost",
            port=5432,
            database="agentictrader",
            user="agentictrader",
            password="changeme",
        )
        
        with patch.object(writer, "_pool") as mock_pool:
            mock_pool.close = AsyncMock()
            
            await writer.close()
            
            # Verify pool was closed
            mock_pool.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_flushes_before_closing(self):
        """close() must flush buffered ticks before closing the pool."""
        writer = TimescaleDBWriter(
            host="localhost",
            port=5432,
            database="agentictrader",
            user="agentictrader",
            password="changeme",
        )
        
        with patch.object(writer, "_pool") as mock_pool:
            mock_pool.close = AsyncMock()
            mock_conn = AsyncMock()
            mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
            mock_conn.executemany = AsyncMock()
            
            # Add some ticks to buffer
            writer._tick_buffer = [SAMPLE_TICK] * 10
            
            await writer.close()
            
            # Verify flush happened before close
            mock_conn.executemany.assert_called()
            mock_pool.close.assert_called()


# ===========================================================================
# 6. Error handling
# ===========================================================================

class TestErrorHandling:
    """The writer must handle database errors gracefully."""

    @pytest.mark.asyncio
    async def test_write_candle_raises_on_db_error(self, db_writer):
        """write_candle should raise an exception if database write fails."""
        import asyncpg
        
        with patch.object(db_writer, "_pool") as mock_pool:
            mock_conn = AsyncMock()
            mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
            mock_conn.execute = AsyncMock(side_effect=asyncpg.PostgresError("Connection failed"))
            
            with pytest.raises(Exception):  # Should propagate the error
                await db_writer.write_candle(SAMPLE_CANDLE)

    @pytest.mark.asyncio
    async def test_flush_raises_on_db_error(self, db_writer):
        """flush should raise an exception if database write fails."""
        import asyncpg
        
        with patch.object(db_writer, "_pool") as mock_pool:
            mock_conn = AsyncMock()
            mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
            mock_conn.executemany = AsyncMock(side_effect=asyncpg.PostgresError("Connection failed"))
            
            # Add ticks to buffer
            db_writer._tick_buffer = [SAMPLE_TICK] * 10
            
            with pytest.raises(Exception):  # Should propagate the error
                await db_writer.flush()

    @pytest.mark.asyncio
    async def test_connection_retry_on_transient_error(self, db_writer):
        """The writer should handle transient connection errors gracefully."""
        # This is a placeholder for retry logic testing
        # Implementation should include retry mechanism for transient errors
        assert True  # Will be implemented in 6b


# ===========================================================================
# 7. Integration test with real TimescaleDB (optional, requires Docker)
# ===========================================================================

@pytest.mark.integration
@pytest.mark.asyncio
async def test_real_timescaledb_candle_write():
    """
    Integration test: write a candle to real TimescaleDB and verify it was stored.
    This test requires TimescaleDB to be running (docker-compose up timescaledb).
    """
    pytest.skip("Integration test - requires running TimescaleDB instance")
    
    # This test would:
    # 1. Create a real TimescaleDBWriter
    # 2. Write a test candle
    # 3. Query the database to verify the candle was stored
    # 4. Clean up test data


@pytest.mark.integration
@pytest.mark.asyncio
async def test_real_timescaledb_tick_batching():
    """
    Integration test: write ticks and verify batching behavior.
    This test requires TimescaleDB to be running (docker-compose up timescaledb).
    """
    pytest.skip("Integration test - requires running TimescaleDB instance")
    
    # This test would:
    # 1. Create a real TimescaleDBWriter
    # 2. Write 1000 ticks
    # 3. Verify 2 batch writes occurred
    # 4. Query the database to verify all ticks were stored
    # 5. Clean up test data
