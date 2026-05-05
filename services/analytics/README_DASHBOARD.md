# Edge Analysis Dashboard

Interactive Streamlit dashboard for visualizing trading edge metrics from the Analytics Service.

## Features

### 📊 Win Rate by Condition
- Group edge metrics by session, instrument, day of week, setup tag, or HTF bias
- Interactive bar charts with color-coded performance
- Detailed metrics table with win rate, R-multiple, expectancy, and P&L

### 📉 R-Multiple Distribution
- Histogram showing distribution of R-multiples across all trades
- Box plot for outlier detection
- Statistical summary (mean, median, min, max)

### 💰 Equity Curve
- Time-series visualization of cumulative P&L
- Drawdown analysis with running maximum
- Max drawdown metrics (absolute and percentage)

### 🕐 Session Breakdown
- Win rate, R-multiple, and trade count by trading session
- Side-by-side comparison charts
- Session performance table

### 🎯 HTF Bias Performance
- Compare BULLISH vs BEARISH HTF open bias performance
- Win rate, R-multiple, and expectancy by bias
- Automated insights on best performing bias

## Prerequisites

1. **Analytics Service must be running**
   - The dashboard connects to the Analytics Service REST API
   - Default URL: `http://localhost:8000`
   - Configure via `ANALYTICS_SERVICE_URL` environment variable

2. **MongoDB with trade journal data**
   - Analytics Service requires MongoDB with populated `trade_journal` collection
   - See `services/analytics/journal_importer.py` for data import

3. **Python dependencies**
   ```bash
   pip install streamlit plotly pandas requests
   ```

## Running the Dashboard

### Option 1: Default Port (8501)
```bash
streamlit run services/analytics/dashboard.py --server.port 8501
```

### Option 2: Custom Port
```bash
streamlit run services/analytics/dashboard.py --server.port 8502
```

### Option 3: With Custom Analytics Service URL
```bash
export ANALYTICS_SERVICE_URL=http://analytics-service:8000
streamlit run services/analytics/dashboard.py --server.port 8501
```

## Configuration

### Environment Variables

- `ANALYTICS_SERVICE_URL`: URL of the Analytics Service (default: `http://localhost:8000`)

### Filters

The dashboard provides sidebar filters:
- **Instrument**: Filter by specific instrument (US500, US30, EURUSD, GBPUSD, XAUUSD) or view all
- **Session**: Filter by trading session (LONDON, NEW_YORK, ASIAN) or view all

## Dashboard Layout

### Header Metrics
- Win Rate
- Avg R-Multiple
- Expectancy
- Total Trades
- Total P&L
- Avg P&L per Trade

### Tabs
1. **Win Rate by Condition**: Group and compare win rates across different dimensions
2. **R-Multiple Distribution**: Analyze the distribution of trade outcomes
3. **Equity Curve**: Track cumulative performance and drawdowns over time
4. **Session Breakdown**: Compare performance across trading sessions
5. **HTF Bias Performance**: Analyze edge based on HTF open bias direction

## API Endpoints Used

The dashboard consumes the following Analytics Service endpoints:

- `GET /analytics/summary` - Overall edge metrics with optional filters
- `GET /analytics/edge?group_by={dimension}` - Grouped edge metrics
- `GET /analytics/equity-curve` - Time-ordered cumulative P&L data

## Development

### Local Development
```bash
# Install dependencies
pip install -r requirements.txt

# Start Analytics Service (in separate terminal)
cd services/analytics
uvicorn edge_analysis:app --reload --port 8000

# Start dashboard
streamlit run services/analytics/dashboard.py --server.port 8501
```

### Docker Deployment
```bash
# Build and run with docker-compose
docker-compose up analytics-dashboard
```

## Troubleshooting

### Dashboard shows "No data available"
- Verify Analytics Service is running: `curl http://localhost:8000/analytics/summary`
- Check MongoDB has trade journal data: `db.trade_journal.countDocuments({})`
- Import sample data: `python services/analytics/journal_importer.py`

### Connection errors
- Verify `ANALYTICS_SERVICE_URL` is correct
- Check Analytics Service logs for errors
- Ensure MongoDB is accessible from Analytics Service

### Slow performance
- Reduce date range filters
- Add indexes to MongoDB trade_journal collection:
  ```javascript
  db.trade_journal.createIndex({"entry.time": 1})
  db.trade_journal.createIndex({"instrument": 1})
  db.trade_journal.createIndex({"setup.session": 1})
  ```

## Future Enhancements

- [ ] Real-time updates via WebSocket
- [ ] Export charts as PNG/PDF
- [ ] Custom date range filters
- [ ] Multi-instrument comparison view
- [ ] Trade detail drill-down
- [ ] Performance attribution analysis
- [ ] Monte Carlo simulation
- [ ] Risk-adjusted metrics (Sharpe, Sortino, Calmar)

## Related Files

- `services/analytics/edge_analysis.py` - Analytics Service implementation
- `services/analytics/journal_importer.py` - Trade journal data importer
- `backend/tests/test_edge_analysis.py` - Analytics Service tests
