# AgentICTrader Setup Guide

## 🚀 Quick Start Guide

### Step 1: Install Python Dependencies ✅ DONE

```bash
pip install aiohttp asyncpg python-dateutil
```

### Step 2: Choose Your Data Source

You have **two options** for loading historical data:

#### Option A: Deriv API (Recommended - No Signup Required!) ⭐

**Advantages:**
- ✅ No signup required - works immediately
- ✅ Free demo data access
- ✅ Already integrated in your codebase
- ✅ Supports EURUSD, GBPUSD, XAUUSD
- ✅ Also has synthetic indices (R_100, R_50)

**Setup:**
```bash
# No credentials needed! Uses default test app ID
# Just make sure TIMESCALE_URL is set in .env (already done)
```

#### Option B: OANDA API (More Instruments)

**Advantages:**
- ✅ More instruments (US500, US30, etc.)
- ✅ Professional-grade data
- ✅ Weekly (W1) timeframe available

**Setup:**
1. Go to [OANDA Demo Account](https://www.oanda.com/demo-account/)
2. Sign up for a demo/practice account
3. Generate API token
4. Update `.env` file:
   ```bash
   OANDA_API_KEY=PASTE_YOUR_API_KEY_HERE
   OANDA_ACCOUNT_ID=PASTE_YOUR_ACCOUNT_ID_HERE
   ```

### Step 3: Configure Environment Variables ✅ DONE

The `.env` file has been created with default settings.

### Step 4: Start TimescaleDB Database 🐳

**Option A: Using Docker Compose (Recommended)**

```bash
cd docker
docker compose up -d timescaledb
```

Wait for the database to be ready (check with):
```bash
docker compose ps
```

**Option B: If Docker pull fails (network issues)**

Try again later or use a different network. The image is: `timescale/timescaledb:latest-pg15`

### Step 5: Verify Database Connection

```bash
# Test connection
docker compose exec timescaledb psql -U agentictrader -d agentictrader -c "\dt"
```

You should see the `candles` table listed.

### Step 6: Load Historical Data 📊

#### Using Deriv API (Recommended - No Signup!) ⭐

**Test with a single instrument first:**

```bash
# Load EURUSD daily data (fast test - ~10 seconds)
python scripts/load_historical_data_deriv.py --instrument EURUSD --timeframe D1
```

**If successful, load more data:**

```bash
# Load EURUSD hourly data (~2 minutes)
python scripts/load_historical_data_deriv.py --instrument EURUSD --timeframe H1

# Load all EURUSD timeframes (~20 minutes)
python scripts/load_historical_data_deriv.py --instrument EURUSD

# Load ALL Deriv data - 3 instruments × 6 timeframes (~1-2 hours)
python scripts/load_historical_data_deriv.py
```

**Available Deriv Instruments:**
- EURUSD (Forex)
- GBPUSD (Forex)
- XAUUSD (Gold)
- R_100 (Volatility 100 Index - synthetic)
- R_50 (Volatility 50 Index - synthetic)

**Available Timeframes:**
- M1, M5, M15, H1, H4, D1

#### Using OANDA API (If you have credentials)

```bash
# Load EURUSD daily data (fast test - ~10 seconds)
python scripts/load_historical_data.py --instrument EURUSD --timeframe D1

# Load all OANDA data - 5 instruments × 7 timeframes (2-4 hours)
python scripts/load_historical_data.py
```

**Available OANDA Instruments:**
- EURUSD, GBPUSD, XAUUSD, US500, US30

**Available Timeframes:**
- M1, M5, M15, H1, H4, D1, W1

### Step 7: View the Data 👀

**Option A: Using psql (Docker)**

```bash
docker compose exec timescaledb psql -U agentictrader -d agentictrader
```

Then run SQL queries:

```sql
-- Count total candles
SELECT COUNT(*) FROM candles;

-- Count by instrument
SELECT instrument, COUNT(*) as count 
FROM candles 
GROUP BY instrument 
ORDER BY count DESC;

-- Count by timeframe
SELECT timeframe, COUNT(*) as count 
FROM candles 
GROUP BY timeframe 
ORDER BY count DESC;

-- View latest EURUSD H1 candles
SELECT time, instrument, timeframe, open, high, low, close, volume
FROM candles
WHERE instrument = 'EURUSD' AND timeframe = 'H1'
ORDER BY time DESC
LIMIT 10;

-- Date range per instrument
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

**Option B: Using Python script**

```python
import asyncpg
import asyncio

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
    
    for row in rows:
        print(f"{row['instrument']:8} {row['timeframe']:4} | "
              f"{row['count']:8} candles | "
              f"{row['first_candle']} → {row['last_candle']}")
    
    await conn.close()

asyncio.run(view_data())
```

## 📋 Troubleshooting

### "ModuleNotFoundError: No module named 'aiohttp'"

```bash
pip install aiohttp asyncpg python-dateutil
```

### "OANDA_API_KEY environment variable not set"

Make sure you:
1. Created the `.env` file
2. Added your actual OANDA credentials
3. The script loads environment variables from `.env`

### "Database not connected" or "Connection refused"

Make sure TimescaleDB is running:

```bash
cd docker
docker compose ps
docker compose up -d timescaledb
```

### Docker pull fails with network errors

This is a temporary network issue. Try:
1. Wait a few minutes and try again
2. Use a different network (mobile hotspot, VPN, etc.)
3. Check Docker Hub status: https://status.docker.com/

### "Failed to fetch candles after 3 attempts"

- Check your internet connection
- Verify OANDA API credentials are correct
- Check if you're rate-limited (wait 5 minutes)
- Verify OANDA API is operational

## 📊 Expected Data Volume

For 3 years of historical data:

| Timeframe | Candles per Instrument | Approx Size |
|-----------|------------------------|-------------|
| M1        | ~1,576,800             | ~150 MB     |
| M5        | ~315,360               | ~30 MB      |
| M15       | ~105,120               | ~10 MB      |
| H1        | ~26,280                | ~3 MB       |
| H4        | ~6,570                 | ~1 MB       |
| D1        | ~1,095                 | ~100 KB     |
| W1        | ~156                   | ~15 KB      |

**Total for all 5 instruments × 7 timeframes:** ~1 GB

## 🎯 Next Steps

Once you have historical data loaded:

1. ✅ **Task 7 Complete** - Historical data loaded
2. 🔄 **Task 8** - Implement economic calendar ingestion
3. 🔄 **Task 9** - Implement HTF auto-timeframe selection
4. 🔄 **Task 10** - Implement HTF OHLC computation

## 📚 Additional Resources

- [OANDA v20 API Documentation](https://developer.oanda.com/rest-live-v20/introduction/)
- [TimescaleDB Documentation](https://docs.timescale.com/)
- [Historical Data Loader README](scripts/README_HISTORICAL_DATA.md)
- [Project Requirements](.kiro/specs/agentictrader-platform/requirements.md)
- [Project Design](.kiro/specs/agentictrader-platform/design.md)

## 🆘 Need Help?

If you encounter issues:
1. Check the logs in `load_historical_data.log`
2. Review the error messages carefully
3. Verify all prerequisites are met
4. Check Docker container logs: `docker compose logs timescaledb`
