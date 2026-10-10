"""
Kafka producer for market data topics.

This module provides a KafkaProducer class for publishing tick and candle data
to Kafka topics using aiokafka.

Topics:
- market.ticks: Real-time tick data (key=instrument)
- market.candles: Completed OHLCV candles (key=instrument:timeframe)
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict

from aiokafka import AIOKafkaProducer
from aiokafka.errors import KafkaError


# Topic constants
TOPIC_TICKS = "market.ticks"
TOPIC_CANDLES = "market.candles"


@dataclass
class TickMessage:
    """Tick message schema."""
    instrument: str
    bid: float
    ask: float
    time: str
    source: str


@dataclass
class CandleMessage:
    """Candle message schema."""
    instrument: str
    timeframe: str
    time: str
    open: float
    high: float
    low: float
    close: float
    volume: int
    complete: bool
    source: str


class KafkaProducer:
    """
    Kafka producer for market data topics.
    
    Publishes tick and candle data to Kafka topics with proper serialization
    and error handling.
    
    Example:
        >>> producer = KafkaProducer("localhost:9092")
        >>> await producer.start()
        >>> await producer.publish_tick({
        ...     "instrument": "EURUSD",
        ...     "bid": 1.0850,
        ...     "ask": 1.0851,
        ...     "time": "2024-01-15T10:30:00Z",
        ...     "source": "oanda"
        ... })
        >>> await producer.close()
    """
    
    def __init__(self, bootstrap_servers: str):
        """
        Initialize the Kafka producer.
        
        Args:
            bootstrap_servers: Kafka bootstrap servers (e.g., "localhost:9092")
        """
        self.bootstrap_servers = bootstrap_servers
        self._producer: AIOKafkaProducer | None = None
        self._closed = False
    
    async def start(self) -> None:
        """Start the Kafka producer connection."""
        if self._producer is None:
            self._producer = AIOKafkaProducer(
                bootstrap_servers=self.bootstrap_servers,
            )
            await self._producer.start()
    
    async def _ensure_started(self) -> None:
        """Ensure the producer is started before publishing."""
        if self._producer is None:
            await self.start()
    
    def _serialize_message(self, data: Dict[str, Any]) -> bytes:
        """
        Serialize a message to JSON bytes.
        
        Args:
            data: Message data dictionary
            
        Returns:
            JSON-encoded bytes
        """
        return json.dumps(data).encode('utf-8')
    
    async def publish_tick(self, tick: Dict[str, Any]) -> None:
        """
        Publish a tick to the market.ticks topic.
        
        Args:
            tick: Tick data dictionary with keys: instrument, bid, ask, time, source
            
        Raises:
            KafkaError: If publishing fails
        """
        await self._ensure_started()
        
        key = tick["instrument"].encode('utf-8')
        value = self._serialize_message(tick)
        
        await self._producer.send(TOPIC_TICKS, key=key, value=value)
    
    async def publish_candle(self, candle: Dict[str, Any]) -> None:
        """
        Publish a candle to the market.candles topic.
        
        Args:
            candle: Candle data dictionary with keys: instrument, timeframe, time,
                   open, high, low, close, volume, complete, source
            
        Raises:
            KafkaError: If publishing fails
        """
        await self._ensure_started()
        
        key = f"{candle['instrument']}:{candle['timeframe']}".encode('utf-8')
        value = self._serialize_message(candle)
        
        await self._producer.send(TOPIC_CANDLES, key=key, value=value)
    
    async def health_check(self) -> Dict[str, Any]:
        """
        Check the health of the Kafka producer.
        
        Returns:
            Dictionary with keys:
            - healthy (bool): Whether the producer is healthy
            - status (str): Connection status
            - broker_count (int): Number of connected brokers
        """
        if self._producer is None:
            return {
                "healthy": False,
                "status": "not_started",
                "broker_count": 0
            }
        
        try:
            brokers = self._producer.client.cluster.brokers()
            broker_count = len(brokers)
            
            return {
                "healthy": broker_count > 0,
                "status": "connected" if broker_count > 0 else "disconnected",
                "broker_count": broker_count
            }
        except Exception:
            return {
                "healthy": False,
                "status": "error",
                "broker_count": 0
            }
    
    async def close(self) -> None:
        """
        Close the Kafka producer gracefully.
        
        Flushes all pending messages before stopping the producer.
        This method is idempotent and can be called multiple times safely.
        """
        if self._closed:
            return
        
        if self._producer is not None:
            try:
                await self._producer.flush()
                await self._producer.stop()
            except Exception:
                pass  # Ignore errors during shutdown
            finally:
                self._closed = True
    
    async def __aenter__(self):
        """Async context manager entry."""
        await self.start()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()

