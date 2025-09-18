"""
Data ingestion pipeline for market data.
Handles ingestion from various sources and stores in appropriate timeframe buckets.
"""
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone
from decimal import Decimal
import asyncio
import logging
import numpy as np
from .market_data_types import TickData, TickHistoryResponse
from .influxdb_manager import InfluxDBManager
from ..analysis.timeframes import TimeframeAnalyzer

logger = logging.getLogger(__name__)

class MarketDataIngestionPipeline:
    """Handles ingestion of market data into appropriate storage buckets."""
    
    def __init__(self):
        """Initialize the data ingestion pipeline."""
        self.influx_manager = InfluxDBManager()
        self.timeframe_analyzer = TimeframeAnalyzer()
        self.buffer: Dict[str, List[TickData]] = {}  # Symbol -> List[TickData]
        self.buffer_size = 1000  # Number of ticks to buffer before processing
        
    async def ingest_tick(self, tick: TickData) -> None:
        """
        Ingest a single tick of market data.
        
        Args:
            tick: The tick data to ingest
        """
        symbol = tick.symbol
        
        # Initialize buffer for symbol if needed
        if symbol not in self.buffer:
            self.buffer[symbol] = []
            
        # Add tick to buffer
        self.buffer[symbol].append(tick)
        
        # Process buffer if it's full
        if len(self.buffer[symbol]) >= self.buffer_size:
            try:
                await self.process_buffer(symbol)
            except Exception as e:
                logger.error(f"Failed to process buffer for {symbol}: {str(e)}")
                # Clear buffer to prevent memory buildup
                self.buffer[symbol] = []
            
    async def process_buffer(self, symbol: str) -> None:
        """
        Process the buffered ticks for a symbol and store in appropriate timeframes.
        
        Args:
            symbol: The symbol to process
        """
        if not self.buffer.get(symbol):
            return
            
        try:
            # Sort ticks by timestamp
            ticks = sorted(self.buffer[symbol], key=lambda x: x.timestamp)
            
            # Convert ticks to numpy array for timeframe conversion
            tick_data = []
            current_minute = ticks[0].timestamp.replace(second=0, microsecond=0)
            current_candle = {
                'open': float(ticks[0].price),
                'high': float(ticks[0].price),
                'low': float(ticks[0].price),
                'close': float(ticks[0].price),
                'volume': 1.0
            }

            for tick in ticks[1:]:
                tick_minute = tick.timestamp.replace(second=0, microsecond=0)
                price = float(tick.price)
                
                if tick_minute == current_minute:
                    # Update current candle
                    current_candle['high'] = max(current_candle['high'], price)
                    current_candle['low'] = min(current_candle['low'], price)
                    current_candle['close'] = price
                    current_candle['volume'] += 1
                else:
                    # Add completed candle to tick_data
                    tick_data.append([
                        current_minute.timestamp(),
                        current_candle['open'],
                        current_candle['high'],
                        current_candle['low'],
                        current_candle['close'],
                        current_candle['volume']
                    ])
                    # Start new candle
                    current_minute = tick_minute
                    current_candle = {
                        'open': price,
                        'high': price,
                        'low': price,
                        'close': price,
                        'volume': 1.0
                    }
            
            # Add the last candle
            tick_data.append([
                current_minute.timestamp(),
                current_candle['open'],
                current_candle['high'],
                current_candle['low'],
                current_candle['close'],
                current_candle['volume']
            ])
            
            # Convert to numpy array
            tick_data = np.array(tick_data)
            
            if len(tick_data) == 0:
                raise ValueError("No valid candles could be created")

                # Process for each timeframe
            # Only convert to timeframes that make sense for the data length
            timeframes = []
            for tf in self.timeframe_analyzer.timeframes:
                tf_minutes = self.timeframe_analyzer.timeframe_minutes[tf]
                if len(tick_data) >= tf_minutes:  # Need at least enough data for one candle
                    timeframes.append(tf)
                    
            aligned_data = self.timeframe_analyzer.align_timeframes(tick_data, timeframes)
            
            # Store in appropriate buckets
            success = True
            for tf, candles in aligned_data.items():
                bucket = f"market_data_{tf.lower()}"
                
                for candle in candles:
                    data_point = {
                        "symbol": symbol,
                        "timestamp": datetime.fromtimestamp(candle[0], tz=timezone.utc),
                        "open": Decimal(str(candle[1])),
                        "high": Decimal(str(candle[2])),
                        "low": Decimal(str(candle[3])),
                        "close": Decimal(str(candle[4])),
                        "volume": Decimal(str(candle[5]))
                    }
                    # Add to InfluxDB
                    if not self.influx_manager.write_point(bucket, data_point):
                        logger.error(f"Failed to write {tf} candle for {symbol}")
                        success = False

            # Clear buffer only if processing was successful
            if success:
                self.buffer[symbol] = []
            
        except Exception as e:
            logger.error(f"Error processing buffer for {symbol}: {str(e)}")
            # Clear buffer even on error to prevent memory buildup
            self.buffer[symbol] = []
            raise
            
    async def ingest_history(self, history: TickHistoryResponse) -> None:
        """
        Ingest historical tick data.
        
        Args:
            history: Historical tick data response
        """
        try:
            # Process historical ticks in chunks
            chunk_size = self.buffer_size
            ticks = history.ticks
            
            for i in range(0, len(ticks), chunk_size):
                chunk = ticks[i:i + chunk_size]
                self.buffer[history.symbol] = chunk
                await self.process_buffer(history.symbol)
                
        except Exception as e:
            logger.error(f"Error ingesting history for {history.symbol}: {str(e)}")
            
    def get_latest_candle(self, symbol: str, timeframe: str) -> Optional[Dict[str, Any]]:
        """
        Get the latest candle for a symbol and timeframe.
        
        Args:
            symbol: The trading symbol
            timeframe: The timeframe (e.g., 'M1', 'M5', etc.)
            
        Returns:
            Optional[Dict]: The latest candle data or None if not found
        """
        bucket = f"market_data_{timeframe.lower()}"
        return self.influx_manager.query_last_point(bucket, symbol)
        
    async def cleanup_old_data(self) -> None:
        """Clean up old data according to retention policies."""
        # Retention policies are already handled by InfluxDB
        # This method exists for any additional cleanup needed
        pass
