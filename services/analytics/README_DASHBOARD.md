# Edge Analysis Streamlit Dashboard

Interactive dashboard for visualizing trading edge metrics from the Analytics Service.

## Features

### 📈 Overview Page
- Key performance metrics (Win Rate, Avg R-Multiple, Expectancy, Trade Count)
- Total P&L and Average P&L per trade
- Quick insights with color-coded alerts

### 🎯 Win Rate by Condition
- Group by: Session, Instrument, HTF Open Bias, Day of Week
- Interactive bar charts with color-coded win rates
- Detailed breakdown table

### 📊 R-Multiple Distribution
- Average R-Multiple by various dimensions
- Expectancy comparison charts
- Break-even reference lines

### 💰 Equity Curve
- Cumulative P&L over time
- Peak P&L and Max Drawdown metrics
- Trade-by-trade history

### 🕐 Session Breakdown
- Win Rate, Trade Count, Avg R-Multiple, and Expectancy by session
- Multi-chart comparison view
- Session statistics table

### 🔄 HTF Bias Performance
- Performance metrics by HTF Open Bias (BULLISH, BEARISH, NEUTRAL)
- Trade distribution pie chart
- Best/worst performing bias insights

## Prerequisites

```bash
pip install streamlit plotly pandas requests
```

Or install from requirements.txt:
```bash
pip install -r requirements.txt
```

## Configuration

The dashboard connects to the Analytics Service via the `ANALYTICS_SERVICE_URL` environment variable.

**Default:** `http://localhost:8000`

To change:
```bash
export ANALYTICS_SERVICE_URL=http://your-analytics-service:8000
```

Or set in `.env` file:
```
ANALYTICS_SERVICE_URL=http://localhost:8000
```

## Running the Dashboard

### Option 1: Direct Command

```bash
streamlit run services/analytics/dashboard.py --server.port 8501
```

### Option 2: Using Shell Script (Linux/Mac)

```bash
chmod +x services/analytics/run_dashboard.sh
./services/analytics/run_dashboard.sh
```

### Option 3: Using Batch Script (Windows)

```cmd
services\analytics\run_dashboard.bat
```

## Accessing the Dashboard

Once running, open your browser to:

```
http://localhost:8501
```

## Filters

Use the sidebar to filter data:
- **Instrument:** Filter by specific instrument (EURUSD, GBPUSD, US500, US30, XAUUSD) or view all
- **Session:** Filter by trading session (LONDON, NEW_YORK, ASIAN) or view all

## API Endpoints Used

The dashboard consumes the following Analytics Service endpoints:

- `GET /analytics/summary` - Overall edge metrics
- `GET /analytics/edge?group_by={dimension}` - Grouped edge metrics
- `GET /analytics/equity-curve` - Equity curve data points

## Troubleshooting

### Dashboard shows "Failed to fetch" errors

**Cause:** Analytics Service is not running or URL is incorrect

**Solution:**
1. Verify Analytics Service is running: `curl http://localhost:8000/analytics/summary`
2. Check `ANALYTICS_SERVICE_URL` environment variable
3. Ensure MongoDB is running and populated with trade data

### No data displayed

**Cause:** No trades in the database

**Solution:**
1. Import trade journal data using `services/analytics/journal_importer.py`
2. Verify trades exist: Check MongoDB `trade_journal` collection

### Port 8501 already in use

**Cause:** Another Streamlit app is running on port 8501

**Solution:**
```bash
# Use a different port
streamlit run services/analytics/dashboard.py --server.port 8502
```

## Development

### Adding New Pages

1. Add a new page option to the sidebar radio:
```python
page = st.sidebar.radio(
    "Navigation",
    options=[
        "📈 Overview",
        "🆕 Your New Page"
    ]
)
```

2. Add the page logic:
```python
elif page == "🆕 Your New Page":
    st.header("🆕 Your New Page")
    # Your page content here
```

### Customizing Charts

The dashboard uses Plotly for interactive charts. Customize by modifying the `plotly.express` or `plotly.graph_objects` calls.

Example:
```python
fig = px.bar(
    df,
    x='session',
    y='win_rate',
    color='win_rate',
    color_continuous_scale='RdYlGn',  # Change color scheme
    title="Your Custom Title"
)
```

## Production Deployment

### Docker

Create a `Dockerfile`:
```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/analytics/dashboard.py services/analytics/

EXPOSE 8501

CMD ["streamlit", "run", "services/analytics/dashboard.py", "--server.port=8501", "--server.address=0.0.0.0"]
```

Build and run:
```bash
docker build -t agentictrader-dashboard .
docker run -p 8501:8501 -e ANALYTICS_SERVICE_URL=http://analytics:8000 agentictrader-dashboard
```

### Streamlit Cloud

1. Push code to GitHub
2. Connect repository to [Streamlit Cloud](https://streamlit.io/cloud)
3. Set `ANALYTICS_SERVICE_URL` in Streamlit Cloud secrets
4. Deploy

## License

Part of the AgentICTrader.AI platform.
