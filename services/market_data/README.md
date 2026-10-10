# Market Data Service - Kafka Producer

## Overview

The Kafka Producer module provides a simple, async interface for publishing market data (ticks and candles) to Kafka topics.

## Topics

- **market.ticks**: Real-time tick data (key=instrument)
- **market.candles**: Completed OHLCV candles (key=instrument:timeframe)

## Usage

### Basic Usage

```python
from services.market_data import KafkaProducer

# Initialize producer
producer = KafkaProducer("localhost:9092")
await producer.start()

# Publish a tick
await producer.publish_tick({
    "instrument": "EURUSD",
    "bid": 1.0850,
    "ask": 1.0851,
    "time": "2024-01-15T10:30:00.000000Z",
    "source": "oanda"
})

# Publish a candle
await producer.publish_candle({
    "instrument": "EURUSD",
    "timeframe": "M5",
    "time": "2024-01-15T10:30:00.000000Z",
    "open": 1.0850,
    "high": 1.0860,
    "low": 1.0845,
    "close": 1.0855,
    "volume": 1500,
    "complete": True,
    "source": "oanda"
})

# Check health
health = await producer.health_check()
print(health)  # {"healthy": True, "status": "connected", "broker_count": 3}

# Close gracefully
await producer.close()
```

### Context Manager Usage

```python
from services.market_data import KafkaProducer

async with KafkaProducer("localhost:9092") as producer:
    await producer.publish_tick({
        "instrument": "EURUSD",
        "bid": 1.0850,
        "ask": 1.0851,
        "time": "2024-01-15T10:30:00.000000Z",
        "source": "oanda"
    })
    # Producer automatically closes on exit
```

## Message Schemas

### Tick Message

```python
{
    "instrument": str,  # e.g., "EURUSD"
    "bid": float,       # Bid price
    "ask": float,       # Ask price
    "time": str,        # ISO 8601 timestamp
    "source": str       # Data source (e.g., "oanda")
}
```

### Candle Message

```python
{
    "instrument": str,  # e.g., "EURUSD"
    "timeframe": str,   # e.g., "M5", "H1", "D1"
    "time": str,        # ISO 8601 timestamp (candle open time)
    "open": float,      # Open price
    "high": float,      # High price
    "low": float,       # Low price
    "close": float,     # Close price
    "volume": int,      # Volume
    "complete": bool,   # True if candle is closed
    "source": str       # Data source (e.g., "oanda")
}
```

## Error Handling

The producer raises `KafkaError` exceptions when publishing fails:

```python
from aiokafka.errors import KafkaError

try:
    await producer.publish_tick(tick_data)
except KafkaError as e:
    print(f"Failed to publish tick: {e}")
```

## Health Checks

The `health_check()` method returns connection status:

```python
health = await producer.health_check()

# Returns:
# {
#     "healthy": bool,        # True if connected to at least one broker
#     "status": str,          # "connected", "disconnected", "not_started", or "error"
#     "broker_count": int     # Number of connected brokers
# }
```

## Testing

Run the test suite:

```bash
pytest backend/tests/test_kafka_producer.py -v
```

## Configuration

The producer requires:
- **bootstrap_servers**: Kafka broker addresses (e.g., "localhost:9092")

For production, configure multiple brokers:

```python
producer = KafkaProducer("broker1:9092,broker2:9092,broker3:9092")
```
