# Data Source Comparison: Deriv vs OANDA

## Quick Recommendation

**Use Deriv API** for immediate testing and development. It requires no signup and works out of the box!

## Detailed Comparison

| Feature | Deriv API ⭐ | OANDA API |
|---------|-------------|-----------|
| **Signup Required** | ❌ No | ✅ Yes |
| **API Key Required** | ❌ No (uses test app ID) | ✅ Yes |
| **Setup Time** | < 1 minute | ~10-15 minutes |
| **Cost** | 🆓 Free | 🆓 Free (demo) |
| **Data Quality** | ✅ Good | ✅ Excellent |
| **Rate Limit** | ~2 req/sec | ~5 req/sec |
| **Max Candles/Request** | 5000 | 5000 |
| **Historical Data** | 3+ years | 3+ years |

## Instruments Available

### Deriv API
- **Forex (3):** EURUSD, GBPUSD, XAUUSD
- **Synthetic Indices (2):** R_100, R_50
- **Total:** 5 instruments

### OANDA API
- **Forex (2):** EURUSD, GBPUSD
- **Commodities (1):** XAUUSD (Gold)
- **US Indices (2):** US500 (S&P 500), US30 (Dow Jones)
- **Total:** 5 instruments

## Timeframes Available

### Deriv API
- M1 (1 minute)
- M5 (5 minutes)
- M15 (15 minutes)
- H1 (1 hour)
- H4 (4 hours)
- D1 (Daily)
- **Total:** 6 timeframes

### OANDA API
- M1, M5, M15, H1, H4, D1
- **W1 (Weekly)** ← Extra timeframe
- **Total:** 7 timeframes

## Data Volume Estimates

### Deriv (3 years)
- **Per instrument:** ~2M candles (all timeframes)
- **Total (5 instruments):** ~10M candles
- **Database size:** ~800 MB
- **Load time:** 1-2 hours

### OANDA (3 years)
- **Per instrument:** ~2M candles (all timeframes)
- **Total (5 instruments):** ~10M candles
- **Database size:** ~1 GB
- **Load time:** 2-4 hours

## Use Cases

### When to Use Deriv
✅ Quick testing and development  
✅ No signup hassle  
✅ Immediate start  
✅ Synthetic indices for testing  
✅ Good enough for ML training  

### When to Use OANDA
✅ Need US indices (US500, US30)  
✅ Need weekly (W1) timeframe  
✅ Production-grade data quality  
✅ Professional trading platform integration  
✅ More comprehensive documentation  

## Scripts Available

### Deriv Loader
```bash
python scripts/load_historical_data_deriv.py
```

**Features:**
- No credentials needed
- Uses default test app ID (1089)
- Loads: EURUSD, GBPUSD, XAUUSD, R_100, R_50
- Timeframes: M1, M5, M15, H1, H4, D1

### OANDA Loader
```bash
python scripts/load_historical_data.py
```

**Features:**
- Requires API key and account ID
- Loads: EURUSD, GBPUSD, XAUUSD, US500, US30
- Timeframes: M1, M5, M15, H1, H4, D1, W1

## Data Quality Comparison

### Deriv
- ✅ Clean OHLC data
- ✅ No gaps during trading hours
- ✅ Accurate timestamps
- ❌ No volume data for forex
- ✅ Synthetic indices have volume

### OANDA
- ✅ Professional-grade data
- ✅ Clean OHLC data
- ✅ Accurate timestamps
- ❌ No volume data for forex
- ✅ Volume data for indices

## API Reliability

### Deriv
- ✅ Stable WebSocket API
- ✅ Good uptime
- ⚠️ Rate limiting (2 req/sec)
- ✅ Automatic reconnection

### OANDA
- ✅ Enterprise-grade reliability
- ✅ Excellent uptime
- ✅ Higher rate limits
- ✅ Professional support

## Recommendation by Use Case

| Use Case | Recommended Source |
|----------|-------------------|
| Quick testing | **Deriv** ⭐ |
| Development | **Deriv** ⭐ |
| ML model training | **Either** (Deriv is faster to set up) |
| Backtesting | **Either** |
| Production trading | **OANDA** |
| US indices trading | **OANDA** (only option) |
| Synthetic indices | **Deriv** (only option) |

## Getting Started

### Option 1: Deriv (Recommended for Quick Start)

```bash
# 1. Start database
cd docker
docker compose up -d timescaledb

# 2. Load data (no credentials needed!)
python scripts/load_historical_data_deriv.py --instrument EURUSD --timeframe D1

# 3. If successful, load all data
python scripts/load_historical_data_deriv.py
```

### Option 2: OANDA (For Production)

```bash
# 1. Get OANDA demo account and API key
# Visit: https://www.oanda.com/demo-account/

# 2. Update .env file with credentials
# OANDA_API_KEY=your_key_here
# OANDA_ACCOUNT_ID=your_account_id_here

# 3. Start database
cd docker
docker compose up -d timescaledb

# 4. Load data
python scripts/load_historical_data.py --instrument EURUSD --timeframe D1

# 5. If successful, load all data
python scripts/load_historical_data.py
```

## Mixing Data Sources

You can use **both** data sources! The `source` column in the database tracks where each candle came from:

```sql
-- View data by source
SELECT source, instrument, COUNT(*) as count
FROM candles
GROUP BY source, instrument
ORDER BY source, instrument;

-- Deriv data
SELECT * FROM candles WHERE source = 'deriv' LIMIT 10;

-- OANDA data
SELECT * FROM candles WHERE source = 'oanda' LIMIT 10;
```

## Next Steps

After loading historical data from either source:

1. ✅ **Task 7 Complete** - Historical data loaded
2. 🔄 **Task 8** - Implement economic calendar ingestion
3. 🔄 **Task 9** - Implement HTF auto-timeframe selection
4. 🔄 **Task 10** - Implement HTF OHLC computation

The ML models and trading logic don't care which source you use - they work with both!
