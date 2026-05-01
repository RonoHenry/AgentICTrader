"""
TimescaleDB writer for candle and tick data.

This module provides async write operations for market data to TimescaleDB,
with batching support for ticks and upsert logic for candles.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
import asyncpg


@dataclass
class CandleData:
    """Represents a single OHLCV candle."""
    time: datetime
    instrument: str
    timeframe: str
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    spread: Optional[Decimal] = None
    complete: bool = True
    source: str = "oanda"


@dataclass
class TickData:
    """Represents a single tick."""
    time: datetime
    instrument: str
    bid: Decimal
    ask: Decimal
    volume: Optional[int] = None
    source: str = "oanda"


class TimescaleDBWriter:
    """
    Async writer for TimescaleDB market data.
    
    Features:
    - Candle upsert with ON CONFLICT DO UPDATE
    - Tick batching (500 records per batch)
    - Auto-flush every 1 second
    - Connection pooling for performance
    """
    
    TICK_BATCH_SIZE = 500
    FLUSH_INTERVAL = 1.0  # seconds
    
    def __init__(
        self,
        host: str,
        port: int,
        database: str,
        user: str,
        password: str,
        min_pool_size: int = 5,
        max_pool_size: int = 20,
    ):
        """
        Initialize the TimescaleDB writer.
        
        Args:
            host: Database host
            port: Database port
            database: Database name
            user: Database user
            password: Database password
            min_pool_size: Minimum connection pool size
            max_pool_size: Maximum connection pool size
        """
        self._host = host
        self._port = port
        self._database = database
        self._user = user
        self._password = password
        self._min_pool_size = min_pool_size
        self._max_pool_size = max_pool_size
        
        self._pool: Optional[asyncpg.Pool] = None
        self._tick_buffer: List[Dict[str, Any]] = []
        self._flush_task: Optional[asyncio.Task] = None
        self._flush_interval = self.FLUSH_INTERVAL
        self._running = False
    
    async def connect(self) -> None:
        """Create the connection pool and start auto-flush task."""
        self._pool = await asyncpg.create_pool(
            host=self._host,
            port=self._port,
            database=self._database,
            user=self._user,
            password=self._password,
            min_size=self._min_pool_size,
            max_size=self._max_pool_size,
        )
        
        # Start auto-flush task
        self._running = True
        self._flush_task = asyncio.create_task(self._auto_flush_loop())
    
    async def close(self) -> None:
        """Flush buffered data and close the connection pool."""
        # Stop auto-flush task
        self._running = False
        if self._flush_task:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass
        
        # Flush any remaining buffered ticks
        if self._tick_buffer:
            await self.flush()
        
        # Close the pool
        if self._pool:
            await self._pool.close()
    
    async def write_candle(self, candle: Dict[str, Any]) -> None:
        """
        Write a candle to the database using upsert logic.
        
        Uses ON CONFLICT (time, instrument, timeframe) DO UPDATE to handle
        updates to incomplete candles.
        
        Args:
            candle: Dictionary containing candle data
        """
        if not self._pool:
            raise RuntimeError("Writer not connected. Call connect() first.")
        
        sql = """
            INSERT INTO candles (
                time, instrument, timeframe, open, high, low, close,
                volume, spread, complete, source, created_at
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, NOW())
            ON CONFLICT (time, instrument, timeframe)
            DO UPDATE SET
                open = EXCLUDED.open,
                high = EXCLUDED.high,
                low = EXCLUDED.low,
                close = EXCLUDED.close,
                volume = EXCLUDED.volume,
                spread = EXCLUDED.spread,
                complete = EXCLUDED.complete,
                source = EXCLUDED.source
        """
        
        async with self._pool.acquire() as conn:
            await conn.execute(
                sql,
                candle["time"],
                candle["instrument"],
                candle["timeframe"],
                candle["open"],
                candle["high"],
                candle["low"],
                candle["close"],
                candle["volume"],
                candle.get("spread"),
                candle.get("complete", True),
                candle.get("source", "oanda"),
            )
    
    async def write_tick(self, tick: Dict[str, Any]) -> None:
        """
        Buffer a tick for batch writing.
        
        Ticks are buffered and written in batches of 500 for performance.
        The buffer is automatically flushed every 1 second.
        
        Args:
            tick: Dictionary containing tick data
        """
        self._tick_buffer.append(tick)
        
        # Flush if batch size reached
        if len(self._tick_buffer) >= self.TICK_BATCH_SIZE:
            await self._flush_ticks()
    
    async def flush(self) -> None:
        """Flush all buffered ticks to the database."""
        if self._tick_buffer:
            await self._flush_ticks()
    
    async def _flush_ticks(self) -> None:
        """Internal method to flush buffered ticks."""
        if not self._tick_buffer:
            return
        
        if not self._pool:
            raise RuntimeError("Writer not connected. Call connect() first.")
        
        sql = """
            INSERT INTO ticks (time, instrument, bid, ask, volume, source)
            VALUES ($1, $2, $3, $4, $5, $6)
        """
        
        # Prepare batch data
        batch_data = [
            (
                tick["time"],
                tick["instrument"],
                tick["bid"],
                tick["ask"],
                tick.get("volume"),
                tick.get("source", "oanda"),
            )
            for tick in self._tick_buffer
        ]
        
        async with self._pool.acquire() as conn:
            await conn.executemany(sql, batch_data)
        
        # Clear buffer
        self._tick_buffer.clear()
    
    async def _auto_flush_loop(self) -> None:
        """Background task that flushes buffered ticks every flush_interval."""
        while self._running:
            try:
                await asyncio.sleep(self._flush_interval)
                if self._tick_buffer:
                    await self._flush_ticks()
            except asyncio.CancelledError:
                break
            except Exception as e:
                # Log error but continue running
                print(f"Error in auto-flush loop: {e}")
    
    @property
    def tick_buffer(self) -> List[Dict[str, Any]]:
        """Get the current tick buffer (for testing)."""
        return self._tick_buffer
    
    @property
    def flush_interval(self) -> float:
        """Get the flush interval in seconds."""
        return self._flush_interval
    
    @property
    def pool(self) -> Optional[asyncpg.Pool]:
        """Get the connection pool (for testing)."""
        return self._pool
