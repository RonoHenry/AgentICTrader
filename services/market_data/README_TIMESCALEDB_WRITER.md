# TimescaleDB Writer

Async writer for TimescaleDB market data with batching and connection pooling.

## Features

- **Candle Upsert**: Uses `ON CONFLICT (time, instrument, timeframe) DO UPDATE` to handle updates to incomplete candles
- **Tick Batching**: Buffers ticks and writes in batches of 500 for optimal performance
- **Auto-Flush**: Automatically flushes buffered ticks every 1 second
- **Connection Pooling**: Uses asyncpg connection pool (5-20 connections) for high throughput
- **Low Latency**: Write latency < 2s from candle close

## Usage

```python
from services.market_data.timescaledb_writer import TimescaleDBWriter
from datetime import datetime, timezone
from decimal import Decimal

# Initialize writer
writer = TimescaleDBWriter(
    host="localhost",
    port=5432,
    database="agentictrader",
    user="agentictrader",
    password="changeme",
)

# Connect
await writer.connect()

# Write a candle
candle = {
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
await writer.write_candle(candle)

# Write ticks (buffered automatically)
tick = {
    "time": datetime(2024, 1, 15, 10, 30, 0, 123456, tzinfo=timezone.utc),
    "instrument": "EURUSD",
    "bid": Decimal("1.08500"),
    "ask": Decimal("1.08510"),
    "volume": 100,
    "source": "oanda",
}
await writer.write_tick(tick)

# Manual flush (if needed)
await writer.flush()

# Close (flushes automatically)
await writer.close()
```

## Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `host` | - | Database host |
| `port` | - | Database port |
| `database` | - | Database name |
| `user` | - | Database user |
| `password` | - | Database password |
| `min_pool_size` | 5 | Minimum connection pool size |
| `max_pool_size` | 20 | Maximum connection pool size |

## Performance

- **Tick Batch Size**: 500 records per batch
- **Flush Interval**: 1 second
- **Write Latency**: < 2 seconds from candle close
- **Connection Pool**: 5-20 connections for concurrency

## Testing

Run tests with:
```bash
pytest backend/tests/test_timescaledb_writer.py -v
```

Integration tests (require running TimescaleDB):
```bash
pytest backend/tests/test_timescaledb_writer.py -v -m integration
```

## Database Schema

### Candles Table
```sql
CREATE TABLE candles (
    time            TIMESTAMPTZ     NOT NULL,
    instrument      VARCHAR(20)     NOT NULL,
    timeframe       VARCHAR(5)      NOT NULL,
    open            NUMERIC(18, 5)  NOT NULL,
    high            NUMERIC(18, 5)  NOT NULL,
    low             NUMERIC(18, 5)  NOT NULL,
    close           NUMERIC(18, 5)  NOT NULL,
    volume          BIGINT,
    spread          NUMERIC(10, 5),
    complete        BOOLEAN         DEFAULT TRUE,
    source          VARCHAR(20),
    created_at      TIMESTAMPTZ     DEFAULT NOW(),
    PRIMARY KEY (time, instrument, timeframe)
);
```

### Ticks Table
```sql
CREATE TABLE ticks (
    time        TIMESTAMPTZ     NOT NULL,
    instrument  VARCHAR(20)     NOT NULL,
    bid         NUMERIC(18, 5)  NOT NULL,
    ask         NUMERIC(18, 5)  NOT NULL,
    volume      INTEGER,
    source      VARCHAR(20)
);
```

## Error Handling

- Database errors are propagated to the caller
- Connection pool handles transient connection errors automatically
- Auto-flush loop continues running even if individual flushes fail
