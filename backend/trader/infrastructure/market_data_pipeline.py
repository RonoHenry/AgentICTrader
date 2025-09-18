"""
Market data ingestion pipeline for processing market data.
"""
import logging
import asyncio
from datetime import datetime, UTC
from typing import List, Dict, Optional
from decimal import Decimal

from influxdb_client import Point, WriteOptions
from trader.infrastructure.market_data_types import TickData
from trader.infrastructure.deriv_api import DerivAPIClient
from trader.infrastructure.influxdb_client import InfluxDBClient

logger = logging.getLogger(__name__)

class MarketDataPipeline:
    """Pipeline for ingesting and processing market data."""
    
    def __init__(
        self,
        deriv_client: DerivAPIClient,
        influx_client: InfluxDBClient,
        bucket: str,
        batch_size: int = 1000
    ):
        """Initialize the pipeline."""
        self.deriv_client = deriv_client
        self.influx_client = influx_client
        self.bucket = bucket
        self.batch_size = batch_size
        self.tick_buffer: Dict[str, List[TickData]] = {}
        self.current_candles: Dict[str, Dict[str, any]] = {}
        self._lock = asyncio.Lock()  # Add lock for thread safety
    
    async def validate_tick(self, tick: TickData) -> bool:
        """Validate a tick before processing."""
        if tick.price <= Decimal('0'):
            raise ValueError(f"Invalid price: {tick.price}")
        if not tick.timestamp:
            raise ValueError("Missing timestamp")
        if not tick.symbol:
            raise ValueError("Missing symbol")
        return True
    
    def tick_to_point(self, tick: TickData) -> Point:
        """Convert a tick to InfluxDB point."""
        timestamp = int(tick.timestamp.timestamp())
        # Convert Decimal to float while preserving original precision
        price_float = float(tick.price)
        point = Point("tick") \
            .tag("symbol", tick.symbol) \
            .tag("tick_id", f"{tick.symbol}_{timestamp}") \
            .field("price", price_float) \
            .field("pip_size", tick.pip_size) \
            .time(tick.timestamp)
        return point
    
    async def process_tick(self, tick: TickData):
        """Process a single tick."""
        try:
            # Validate tick
            await self.validate_tick(tick)
            
            # Add to buffer
            if tick.symbol not in self.tick_buffer:
                self.tick_buffer[tick.symbol] = []
            self.tick_buffer[tick.symbol].append(tick)
            logger.debug(f"Added tick to buffer. Buffer size for {tick.symbol}: {len(self.tick_buffer[tick.symbol])}")
            
            # Check if buffer is full
            if len(self.tick_buffer[tick.symbol]) >= self.batch_size:
                await self.write_tick_batch(tick.symbol)  # Will only write if buffer is full
                
            # Update OHLCV
            await self.update_ohlcv(tick)
            
        except Exception as e:
            logger.error(f"Error processing tick: {e}")
            # Re-raise the exception without clearing the buffer
            raise
    
    async def write_tick_batch(self, symbol: str, force: bool = False):
        """Write a batch of ticks to InfluxDB."""
        try:
            if not self.tick_buffer.get(symbol):
                logger.debug(f"No ticks in buffer for {symbol}")
                return
                
            # Only write if there are points or force write is requested
            if not self.tick_buffer[symbol]:
                logger.debug(f"No ticks in buffer for {symbol}")
                return
                
            # Skip if buffer not full and not forced
            if not force and len(self.tick_buffer[symbol]) < self.batch_size:
                logger.debug(f"Buffer not full for {symbol} ({len(self.tick_buffer[symbol])} < {self.batch_size})")
                return
            
            # Make a copy of the current buffer and clear it atomically
            async with self._lock:
                # Only take up to batch_size points if not forced
                if not force and len(self.tick_buffer[symbol]) > self.batch_size:
                    batch = self.tick_buffer[symbol][:self.batch_size]
                    self.tick_buffer[symbol] = self.tick_buffer[symbol][self.batch_size:]
                else:
                    # Take all points if forced or buffer not exceeding batch size
                    batch = self.tick_buffer[symbol][:]
                    self.tick_buffer[symbol] = []
                logger.debug(f"Processing batch of {len(batch)} ticks for {symbol} ({len(self.tick_buffer[symbol])} remaining)")
            
            # Deduplicate points based on tick_id
            seen_ids = set()
            unique_batch = []
            for tick in batch:
                tick_id = f"{tick.symbol}_{int(tick.timestamp.timestamp())}"
                if tick_id not in seen_ids:
                    seen_ids.add(tick_id)
                    unique_batch.append(tick)
            
            logger.debug(f"Processing batch of {len(unique_batch)} unique ticks for {symbol}")
            points = [self.tick_to_point(tick) for tick in unique_batch]
            
            # Write points with retry logic
            max_retries = 3
            retry_delay = 1
            
            for attempt in range(max_retries):
                try:
                    if points:
                        await self.influx_client.write(self.bucket, points)
                        logger.debug(f"Successfully wrote {len(points)} points for {symbol}")
                        break
                except Exception as e:
                    if attempt == max_retries - 1:
                        raise
                    logger.warning(f"Write attempt {attempt + 1} failed, retrying in {retry_delay}s: {e}")
                    await asyncio.sleep(retry_delay)
                    retry_delay *= 2
                
        except Exception as e:
            logger.error(f"Error writing tick batch: {e}")
            raise
    
    async def update_ohlcv(self, tick: TickData):
        """Update OHLCV data with new tick."""
        symbol = tick.symbol
        price = float(tick.price)
        current_time = tick.timestamp
        current_minute = current_time.replace(second=0, microsecond=0)

        try:
            if symbol not in self.current_candles:
                # Initialize first candle
                self.current_candles[symbol] = {
                    'open': price,
                    'high': price,
                    'low': price,
                    'close': price,
                    'volume': 1,
                    'timestamp': current_minute
                }
            else:
                candle = self.current_candles[symbol]
                candle_minute = candle['timestamp'].replace(second=0, microsecond=0)

                if current_minute > candle_minute:
                    # Current tick belongs to a new minute - write the completed candle
                    await self.write_ohlcv(symbol, "1m")

                    # Start new candle with current tick
                    self.current_candles[symbol] = {
                        'open': price,
                        'high': price,
                        'low': price,
                        'close': price,
                        'volume': 1,
                        'timestamp': current_minute
                    }
                else:
                    # Update current candle
                    candle['high'] = max(candle['high'], price)
                    candle['low'] = min(candle['low'], price)
                    candle['close'] = price
                    candle['volume'] += 1

            # If this is the last tick of the current minute, write the candle
            if current_time.second == 59 and current_time.microsecond > 900_000:
                await self.write_ohlcv(symbol, "1m")

        except Exception as e:
            logger.error(f"Error updating OHLCV for {symbol}: {e}")
            raise
    
    async def write_ohlcv(self, symbol: str, timeframe: str):
        """Write OHLCV data to InfluxDB."""
        if symbol not in self.current_candles:
            logger.debug(f"No current candle for symbol {symbol}")
            return
            
        candle = self.current_candles[symbol]
        if not candle or not candle['timestamp']:
            logger.debug(f"Invalid candle data for symbol {symbol}")
            return
        
        timestamp = candle['timestamp'].replace(microsecond=0)  # Remove microseconds for consistency
            
        # Create multiple points, one for each field
        points = []
        fields = ['open', 'high', 'low', 'close', 'volume']
        for field in fields:
            value = candle[field]
            if field == 'volume':
                value = int(value)
            else:
                value = float(value)
                
            point = Point("ohlcv") \
                .tag("symbol", symbol) \
                .tag("timeframe", timeframe) \
                .field(field, value) \
                .field("timestamp", int(timestamp.timestamp())) \
                .time(timestamp)
            points.append(point)
            
        try:
            logger.debug(f"Writing OHLCV for {symbol} at {timestamp}: O={candle['open']}, H={candle['high']}, L={candle['low']}, C={candle['close']}, V={candle['volume']}")
            await self.influx_client.write(self.bucket, points)
            logger.debug(f"Successfully wrote OHLCV data for {symbol}: {len(points)} points")
        except Exception as e:
            logger.error(f"Error writing OHLCV data for {symbol}: {e}")
            raise
            
        # Initialize a new candle with the last tick's close price
        next_candle = {
            'open': candle['close'],
            'high': candle['close'],
            'low': candle['close'],
            'close': candle['close'],
            'volume': 0,
            'timestamp': timestamp  # Use the same timestamp consistency
        }
        self.current_candles[symbol] = next_candle
    
    async def ingest_symbol(self, symbol: str):
        """Start ingesting data for a symbol."""
        try:
            async for tick in self.deriv_client.subscribe_ticks(symbol):
                try:
                    await self.process_tick(tick)
                    
                    # Write batch if buffer is full
                    if len(self.tick_buffer.get(symbol, [])) >= self.batch_size:
                        await self.write_tick_batch(symbol)
                        
                except Exception as e:
                    logger.error(f"Error processing tick for {symbol}: {e}")
                    # Clean up buffer in case of error
                    if symbol in self.tick_buffer:
                        self.tick_buffer[symbol] = []
                    raise
                
        except asyncio.CancelledError:
            # Clean up any remaining ticks
            if symbol in self.tick_buffer and self.tick_buffer[symbol]:
                await self.write_tick_batch(symbol)
            raise
            
        except Exception as e:
            logger.error(f"Error ingesting symbol {symbol}: {e}")
            raise