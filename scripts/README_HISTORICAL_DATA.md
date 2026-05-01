# Historical Data Loader

## Overview

The `load_historical_data.py` script fetches 3 years of historical OHLCV data from the OANDA v20 REST API and loads it into TimescaleDB. This script is part of Phase 0 (Foundation & Edge Quantification) of the AgentICTrader platform.

## Features

- **Multi-instrument support**: EURUSD, GBPUSD, US500, US30, XAUUSD
- **Multi-timeframe support**: M1, M5, M15, H1, H4, D1, W1
- **Pagination handling**: Automatically handles OANDA's 5000 candle limit per request
- **Data validation**: Validates OHLC integrity (high >= open/close/low, low <= open/close/high)
- **Gap detection**: Identifies gaps > 2x timeframe duration
- **Resume capability**: Can resume from last loaded timestamp if interrupted
- **Batch inserts**: Efficient batch loading (1000 candles per batch)
- **Retry logic**: Automatic retry with exponential backoff for failed requests
- **Rate limiting**: Respects OANDA API rate limits
- **Detailed logging**: Comprehensive logging to console and file

## Prerequisites

1. **OANDA API credentials**: You need an OANDA account and API key
2. **TimescaleDB**: Running TimescaleDB instance with schema initialized
3. **Python dependencies**: All dependencies from `requirements.txt` installed

## Environment Variables

Set the following environment variables before running the script:

```bash
# OANDA API credentials
export OANDA_API_KEY="your_oanda_api_key_here"
export OANDA_ACCOUNT_ID="your_account_id_here"
export OANDA_ENVIRONMENT="practice"  # or "live"

# TimescaleDB connection
export TIMESCALE_URL="postgresql+asyncpg://agentictrader:changeme@localhost:5432/agentictrader"
```

Or create a `.env` file in the project root (see `.env.example`).

## Usage

### Load all instruments and timeframes (default)

```bash
python scripts/load_historical_data.py
```

This will load 3 years of data for:
- **Instruments**: EURUSD, GBPUSD, US500, US30, XAUUSD
- **Timeframes**: M1, M5, M15, H1, H4, D1, W1
- **Total combinations**: 5 instruments × 7 timeframes = 35 datasets

### Load a specific instrument

```bash
python scripts/load_historical_data.py --instrument EURUSD
```

### Load a specific timeframe

```bash
python scripts/load_historical_data.py --timeframe H1
```

### Load a specific instrument-timeframe combination

```bash
python scripts/load_historical_data.py --instrument EURUSD --timeframe H1
```

### Resume from last loaded timestamp

If the script is interrupted, you can resume from where it left off:

```bash
python scripts/load_historical_data.py --resume
```

This will check the database for the last loaded timestamp for each instrument-timeframe pair and continue from there.

## Output

### Console Output

The script provides real-time progress updates:

```
2024-01-15 10:30:00 [INFO] ================================================================================
2024-01-15 10:30:00 [INFO] AgentICTrader Historical Data Loader
2024-01-15 10:30:00 [INFO] ================================================================================
2024-01-15 10:30:00 [INFO] Instruments: EURUSD, GBPUSD, US500, US30, XAUUSD
2024-01-15 10:30:00 [INFO] Timeframes: M1, M5, M15, H1, H4, D1, W1
2024-01-15 10:30:00 [INFO] Historical period: 3 years
2024-01-15 10:30:00 [INFO] OANDA environment: practice
2024-01-15 10:30:00 [INFO] Resume mode: False
2024-01-15 10:30:00 [INFO] ================================================================================
2024-01-15 10:30:01 [INFO] Connected to TimescaleDB
2024-01-15 10:30:01 [INFO] Fetching EUR_USD M1 from 2021-01-15 10:30:00+00:00 to 2024-01-15 10:30:00+00:00
2024-01-15 10:30:05 [INFO] Fetched 5000 candles. Total: 5000. Last: 2021-01-18 15:30:00+00:00
2024-01-15 10:30:10 [INFO] Fetched 5000 candles. Total: 10000. Last: 2021-01-21 20:30:00+00:00
...
```

### Summary Report

At the end, a summary report is displayed:

```
================================================================================
LOAD SUMMARY REPORT
================================================================================
Instrument Timeframe  Rows       Date Range                               Gaps   Errors   Duration
------------------------------------------------------------------------------------
EURUSD     M1         1576800    2021-01-15 → 2024-01-15                  12     0        1234.56s
EURUSD     M5         315360     2021-01-15 → 2024-01-15                  8      0        456.78s
EURUSD     M15        105120     2021-01-15 → 2024-01-15                  5      0        234.56s
...
------------------------------------------------------------------------------------
TOTAL                 2500000                                             45     0        5678.90s
================================================================================
```

### Log File

All output is also written to `load_historical_data.log` in the current directory.

## Data Validation

The script performs the following validations:

### OHLC Integrity

Each candle is validated to ensure:
- `high >= open`
- `high >= close`
- `high >= low`
- `low <= open`
- `low <= close`
- `low <= high`

Invalid candles are logged and skipped.

### Gap Detection

Gaps are detected when the time between consecutive candles exceeds 2× the timeframe duration:

- **M1**: Gap if > 2 minutes
- **M5**: Gap if > 10 minutes
- **M15**: Gap if > 30 minutes
- **H1**: Gap if > 2 hours
- **H4**: Gap if > 8 hours
- **D1**: Gap if > 2 days
- **W1**: Gap if > 2 weeks

Gaps are logged with start time, end time, and duration in hours.

## Database Schema

Data is loaded into the `candles` table:

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

The script uses `ON CONFLICT DO UPDATE` to handle duplicate timestamps, allowing for safe re-runs and updates.

## Instrument and Timeframe Mapping

### Instruments

| Platform Name | OANDA API Name |
|---------------|----------------|
| EURUSD        | EUR_USD        |
| GBPUSD        | GBP_USD        |
| US500         | SPX500_USD     |
| US30          | US30_USD       |
| XAUUSD        | XAU_USD        |

### Timeframes

| Platform Name | OANDA Granularity |
|---------------|-------------------|
| M1            | M1                |
| M5            | M5                |
| M15           | M15               |
| H1            | H1                |
| H4            | H4                |
| D1            | D                 |
| W1            | W                 |

## Error Handling

The script includes robust error handling:

- **Network errors**: Automatic retry with exponential backoff (max 3 attempts)
- **Rate limiting**: Respects `Retry-After` header from OANDA API
- **API errors**: Logs error details and continues with next dataset
- **Database errors**: Logs error and exits gracefully
- **Validation errors**: Logs invalid candles and continues

## Performance Considerations

### Expected Load Times

Approximate load times for 3 years of data (varies by network speed and API rate limits):

- **M1**: ~20-30 minutes per instrument
- **M5**: ~5-10 minutes per instrument
- **M15**: ~2-5 minutes per instrument
- **H1**: ~1-2 minutes per instrument
- **H4**: ~30-60 seconds per instrument
- **D1**: ~10-20 seconds per instrument
- **W1**: ~5-10 seconds per instrument

**Total estimated time**: 2-4 hours for all 35 combinations

### Optimization Tips

1. **Load higher timeframes first**: Start with D1 and W1 for quick validation
2. **Use resume mode**: If interrupted, resume to avoid re-fetching data
3. **Load specific instruments**: Focus on instruments you need first
4. **Run during off-peak hours**: Better API response times

## Troubleshooting

### "OANDA_API_KEY environment variable not set"

Set the required environment variables:

```bash
export OANDA_API_KEY="your_key_here"
export TIMESCALE_URL="postgresql+asyncpg://user:pass@host:port/db"
```

### "Failed to fetch candles after 3 attempts"

- Check your internet connection
- Verify OANDA API credentials are valid
- Check if OANDA API is experiencing issues
- Try again later (may be rate limited)

### "Database not connected"

- Ensure TimescaleDB is running
- Verify connection string is correct
- Check database credentials
- Ensure database schema is initialized

### High validation error count

- Check OANDA API data quality
- Review validation logic in logs
- Report issues to OANDA support if persistent

### Gaps in data

Some gaps are expected:
- **Weekends**: Forex markets closed
- **Holidays**: Market holidays
- **Low liquidity periods**: Some instruments may have gaps during off-hours

Excessive gaps may indicate:
- Data quality issues from OANDA
- Network interruptions during historical period
- Instrument-specific trading hours

## Testing

Run the test suite to verify the script:

```bash
pytest backend/tests/test_load_historical_data.py -v
```

Tests cover:
- OHLC validation logic
- Gap detection algorithm
- Configuration constants
- Instrument and timeframe mappings

## Integration with AgentICTrader

This script is part of the AgentICTrader platform's data pipeline:

1. **Phase 0**: Historical data loading (this script)
2. **Phase 1**: Real-time data ingestion (market-data service)
3. **Phase 2**: Feature engineering (HTF projections)
4. **Phase 3**: ML pattern detection
5. **Phase 4**: Agentic execution loop

After loading historical data, you can:
- Train ML models on historical patterns
- Backtest trading strategies
- Validate HTF projection calculations
- Analyze market structure across timeframes

## References

- [OANDA v20 REST API Documentation](https://developer.oanda.com/rest-live-v20/introduction/)
- [TimescaleDB Documentation](https://docs.timescale.com/)
- [AgentICTrader Design Document](../docs/design.md)
- [AgentICTrader Requirements](../.kiro/specs/agentictrader-platform/requirements.md)
