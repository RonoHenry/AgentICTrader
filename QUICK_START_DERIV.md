# Quick Start with Deriv API 🚀

## ✅ What's Ready

1. ✅ Python dependencies installed (`aiohttp`, `asyncpg`, `websockets`)
2. ✅ `.env` file configured with Deriv API key
3. ✅ Deriv historical data loader script ready
4. ⏳ Need to start TimescaleDB database

## 🐳 Option 1: Docker (Recommended)

### Try pulling the image again:

```bash
# Pull the TimescaleDB image
docker pull timescale/timescaledb:latest-pg15

# If successful, start the database
cd docker
docker compose up -d timescaledb

# Check if it's running
docker compose ps
```

### If Docker pull keeps failing:

Your network might be blocking Docker Hub. Try:
- Using a VPN
- Using mobile hotspot
- Trying at a different time
- Using a different network

## 💻 Option 2: Local PostgreSQL (Alternative)

If you have PostgreSQL installed locally:

### 1. Create the database:

```bash
# Connect to PostgreSQL
psql -U postgres

# Create database and user
CREATE DATABASE agentictrader;
CREATE USER agentictrader WITH PASSWORD 'changeme';
GRANT ALL PRIVILEGES ON DATABASE agentictrader TO agentictrader;
\q
```

### 2. Install TimescaleDB extension:

```bash
# Connect to the database
psql -U agentictrader -d agentictrader

# Enable TimescaleDB
CREATE EXTENSION IF NOT EXISTS timescaledb;
\q
```

### 3. Run the schema script:

```bash
psql -U agentictrader -d agentictrader -f docker/init/timescaledb/001_schema.sql
```

### 4. Update `.env` file:

```bash
# Change this line in .env:
TIMESCALE_URL=postgresql+asyncpg://agentictrader:changeme@localhost:5432/agentictrader
```

## 🎯 Once Database is Running

### Test with a small dataset first:

```bash
# Load EURUSD daily data (fast - ~10 seconds, ~1000 candles)
python scripts/load_historical_data_deriv.py --instrument EURUSD --timeframe D1
```

### If successful, load more data:

```bash
# Load EURUSD hourly data (~2 minutes, ~26,000 candles)
python scripts/load_historical_data_deriv.py --instrument EURUSD --timeframe H1

# Load all EURUSD timeframes (~20 minutes)
python scripts/load_historical_data_deriv.py --instrument EURUSD

# Load ALL Deriv data (~1-2 hours)
python scripts/load_historical_data_deriv.py
```

## 📊 View Your Data

### Option A: Using psql

```bash
# Connect to database
docker compose exec timescaledb psql -U agentictrader -d agentictrader

# Or if using local PostgreSQL:
psql -U agentictrader -d agentictrader
```

Then run queries:

```sql
-- Count total candles
SELECT COUNT(*) FROM candles;

-- Count by instrument
SELECT instrument, COUNT(*) as count 
FROM candles 
GROUP BY instrument 
ORDER BY count DESC;

-- View latest EURUSD H1 candles
SELECT time, instrument, timeframe, open, high, low, close
FROM candles
WHERE instrument = 'EURUSD' AND timeframe = 'H1'
ORDER BY time DESC
LIMIT 10;

-- Date range summary
SELECT 
    instrument,
    timeframe,
    MIN(time) as first_candle,
    MAX(time) as last_candle,
    COUNT(*) as total_candles
FROM candles
GROUP BY instrument, timeframe
ORDER BY instrument, timeframe;
```

### Option B: Using Python

Create a file `view_data.py`:

```python
import asyncio
import asyncpg

async def view_data():
    conn = await asyncpg.connect(
        'postgresql://agentictrader:changeme@localhost:5432/agentictrader'
    )
    
    # Get summary
    rows = await conn.fetch("""
        SELECT instrument, timeframe, COUNT(*) as count,
               MIN(time) as first_candle, MAX(time) as last_candle
        FROM candles
        GROUP BY instrument, timeframe
        ORDER BY instrument, timeframe
    """)
    
    print(f"\n{'Instrument':<10} {'TF':<4} | {'Count':>8} | Date Range")
    print("-" * 70)
    for row in rows:
        print(f"{row['instrument']:<10} {row['timeframe']:<4} | "
              f"{row['count']:>8} | "
              f"{row['first_candle'].strftime('%Y-%m-%d')} → "
              f"{row['last_candle'].strftime('%Y-%m-%d')}")
    
    await conn.close()

asyncio.run(view_data())
```

Run it:
```bash
python view_data.py
```

## 🎉 What You'll Get

### Deriv Data (3 years):

| Instrument | Type | Timeframes |
|------------|------|------------|
| EURUSD | Forex | M1, M5, M15, H1, H4, D1 |
| GBPUSD | Forex | M1, M5, M15, H1, H4, D1 |
| XAUUSD | Gold | M1, M5, M15, H1, H4, D1 |
| R_100 | Synthetic | M1, M5, M15, H1, H4, D1 |
| R_50 | Synthetic | M1, M5, M15, H1, H4, D1 |

**Total:** ~10 million candles, ~800 MB

### Expected Load Times:

- **D1 (Daily):** ~10 seconds per instrument
- **H1 (Hourly):** ~2 minutes per instrument
- **M1 (1-minute):** ~20 minutes per instrument
- **All timeframes, all instruments:** 1-2 hours

## 🔧 Troubleshooting

### "TIMESCALE_URL environment variable not set"

Make sure `.env` file exists and has:
```bash
TIMESCALE_URL=postgresql+asyncpg://agentictrader:changeme@localhost:5432/agentictrader
```

### "Database not connected" or "Connection refused"

- Check if TimescaleDB is running: `docker compose ps`
- Or check local PostgreSQL: `pg_isready`

### "Failed to connect to Deriv API"

- Check your internet connection
- Verify DERIV_APP_ID in `.env` is set
- Try again (might be temporary network issue)

### Script runs but no data loaded

Check the log file:
```bash
cat load_historical_data_deriv.log
```

## 📝 Next Steps

Once you have data loaded:

1. ✅ **Task 7 Complete** - Historical data loaded
2. 🔄 **Task 8** - Implement economic calendar ingestion
3. 🔄 **Task 9** - Implement HTF auto-timeframe selection
4. 🔄 **Task 10** - Implement HTF OHLC computation

## 💡 Pro Tips

1. **Start small:** Test with D1 timeframe first (fastest)
2. **Use resume:** If interrupted, use `--resume` flag to continue
3. **Monitor progress:** Watch the log file in real-time:
   ```bash
   tail -f load_historical_data_deriv.log
   ```
4. **Check data quality:** After loading, run validation queries to check for gaps

## 🆘 Need Help?

If you're stuck:
1. Check `load_historical_data_deriv.log` for errors
2. Verify database is running
3. Test database connection manually
4. Check if Deriv API is accessible: https://api.deriv.com/

---

**Ready to load data?** Just need to get TimescaleDB running! 🚀
