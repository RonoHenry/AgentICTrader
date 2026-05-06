# Edge Analysis Dashboard - Quick Start Guide

## Prerequisites

Ensure you have the following running:

1. **MongoDB** - Contains trade journal data
2. **Analytics Service** - FastAPI service on port 8000

## Step 1: Install Dependencies

If not already installed:

```bash
pip install streamlit plotly pandas requests
```

Or use the project requirements:

```bash
pip install -r requirements.txt
```

## Step 2: Verify Analytics Service is Running

Test the Analytics Service endpoints:

```bash
curl http://localhost:8000/analytics/summary
```

Expected response:
```json
{
  "win_rate": 0.75,
  "avg_r_multiple": 2.5,
  "expectancy": 2.0,
  "trade_count": 10,
  "total_pnl": 5000.0,
  "avg_pnl": 500.0
}
```

If you get an error, start the Analytics Service first.

## Step 3: Run the Dashboard

### Option A: Direct Command

```bash
streamlit run services/analytics/dashboard.py --server.port 8501
```

### Option B: Using Shell Script (Linux/Mac)

```bash
chmod +x services/analytics/run_dashboard.sh
./services/analytics/run_dashboard.sh
```

### Option C: Using Batch Script (Windows)

```cmd
services\analytics\run_dashboard.bat
```

## Step 4: Access the Dashboard

Open your browser to:

```
http://localhost:8501
```

## Dashboard Pages

### 📈 Overview
- Key performance metrics at a glance
- Win rate, avg R-multiple, expectancy, trade count
- Total P&L and average P&L per trade
- Quick insights with color-coded alerts

### 🎯 Win Rate by Condition
- Group by: Session, Instrument, HTF Open Bias, Day of Week
- Interactive bar charts
- Detailed breakdown table

### 📊 R-Multiple Distribution
- Average R-Multiple by various dimensions
- Expectancy comparison
- Statistical breakdown

### 💰 Equity Curve
- Cumulative P&L over time
- Peak P&L and max drawdown
- Trade-by-trade history

### 🕐 Session Breakdown
- Performance metrics by trading session
- Multi-chart comparison view
- Session statistics

### 🔄 HTF Bias Performance
- Performance by HTF Open Bias (BULLISH, BEARISH, NEUTRAL)
- Trade distribution
- Best/worst performing bias insights

## Filters

Use the sidebar to filter data:

- **Instrument**: EURUSD, GBPUSD, US500, US30, XAUUSD, or All
- **Session**: LONDON, NEW_YORK, ASIAN, or All

## Troubleshooting

### "Failed to fetch" errors

**Problem**: Analytics Service is not running or URL is incorrect

**Solution**:
```bash
# Check if service is running
curl http://localhost:8000/analytics/summary

# If not running, start it
# (Refer to Analytics Service documentation)
```

### No data displayed

**Problem**: No trades in the database

**Solution**:
```bash
# Import sample trade data
python services/analytics/journal_importer.py --file path/to/trades.csv
```

### Port 8501 already in use

**Problem**: Another Streamlit app is running

**Solution**:
```bash
# Use a different port
streamlit run services/analytics/dashboard.py --server.port 8502
```

## Configuration

### Custom Analytics Service URL

Set via environment variable:

```bash
export ANALYTICS_SERVICE_URL=http://your-host:8000
streamlit run services/analytics/dashboard.py --server.port 8501
```

Or in `.env` file:
```
ANALYTICS_SERVICE_URL=http://localhost:8000
```

## Next Steps

1. **Import Trade Data**: Use the journal importer to load historical trades
2. **Explore Metrics**: Navigate through different pages to analyze your edge
3. **Identify Patterns**: Look for high-performing conditions (sessions, instruments, HTF bias)
4. **Optimize Strategy**: Focus on setups with positive expectancy

## Support

For issues or questions:
- Check the main README: `services/analytics/README_DASHBOARD.md`
- Review test cases: `backend/tests/test_dashboard.py`
- Verify Analytics Service: `backend/tests/test_edge_analysis.py`
