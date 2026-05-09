# Pattern Detector - Labelling Tool

Manual labelling tool for creating training data for the Pattern Detector ML model.

## Overview

The Pattern Labelling Tool provides an interactive Streamlit UI for manually labelling candle patterns in historical market data. This creates the training dataset needed for the Pattern Detector XGBoost model.

## Pattern Labels

The tool supports labelling the following 8 patterns:

1. **BOS_CONFIRMED** - Break of Structure confirmed (window: 10 candles)
2. **CHOCH_DETECTED** - Change of Character detected (window: 10 candles)
3. **SUPPLY_ZONE_REJECTION** - Price rejected from supply zone (window: 8 candles)
4. **DEMAND_ZONE_BOUNCE** - Price bounced from demand zone (window: 8 candles)
5. **FVG_PRESENT** - Fair Value Gap present (window: 5 candles)
6. **LIQUIDITY_SWEEP** - Liquidity sweep detected (window: 12 candles)
7. **ORDER_BLOCK** - Order block identified (window: 6 candles)
8. **INDUCEMENT** - Inducement pattern detected (window: 10 candles)

**Target:** Minimum 500 labelled examples per pattern (4,000 total examples)

## Architecture

### Components

1. **labeller.py** - Core labelling logic
   - `PatternLabeller` class for database connections
   - `load_candles_from_timescale()` - Load historical candles from TimescaleDB
   - `save_labelled_example()` - Save labelled patterns to MongoDB

2. **labeller_ui.py** - Streamlit UI
   - Interactive candlestick charts
   - Pattern labelling buttons
   - Progress tracking
   - Navigation controls

3. **test_pattern_labeller.py** - Unit tests
   - Tests for data loading
   - Tests for label saving
   - Tests for label counting

### Data Flow

```
TimescaleDB (candles) 
    ↓
PatternLabeller.get_candles()
    ↓
Streamlit UI (display + label)
    ↓
PatternLabeller.save_label()
    ↓
MongoDB (setups collection)
```

## Setup

### Prerequisites

1. **TimescaleDB** running with historical candle data
2. **MongoDB** running for storing labels
3. **Python dependencies** installed (see requirements.txt)

### Environment Variables

Set these in your `.env` file:

```bash
# TimescaleDB
TIMESCALE_URL=postgresql+asyncpg://agentictrader:changeme@localhost:5432/agentictrader

# MongoDB
MONGODB_URL=mongodb://localhost:27017
MONGODB_DB=agentictrader
```

### Database Schema

**TimescaleDB - candles table:**
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
    PRIMARY KEY (time, instrument, timeframe)
);
```

**MongoDB - setups collection:**
```javascript
{
    label: String,              // Pattern label (e.g., 'BOS_CONFIRMED')
    candle_window: Array,       // Array of candle objects
    instrument: String,         // Trading instrument (e.g., 'EURUSD')
    timeframe: String,          // Candle timeframe (e.g., 'M5')
    timestamp: Date,            // Timestamp of the pattern
    notes: String,              // Optional notes
    labelled_by: String,        // User identifier
    created_at: Date            // Creation timestamp
}
```

## Usage

### Running the UI

```bash
# From project root
streamlit run ml/models/pattern_detector/labeller_ui.py --server.port 8502
```

The UI will be available at: http://localhost:8502

### Labelling Workflow

1. **Load Data**
   - Select instrument (EURUSD, GBPUSD, US500, US30, XAUUSD)
   - Select timeframe (M1, M5, M15, H1, H4, D1)
   - Choose date range
   - Click "Load Candles"

2. **Navigate Candles**
   - Use navigation buttons: First, Previous, Next, Last
   - Or jump to specific candle index
   - Current candle is highlighted with a yellow star

3. **Label Patterns**
   - Review the candlestick chart
   - Add optional notes
   - Click the appropriate pattern label button
   - The tool automatically saves and advances to the next candle

4. **Track Progress**
   - View label counts in the sidebar
   - Progress bars show completion toward 500 examples per pattern
   - Refresh counts to see latest statistics

### Programmatic Usage

```python
import asyncio
from datetime import datetime, timedelta
from ml.models.pattern_detector.labeller import PatternLabeller

async def label_patterns():
    # Initialize labeller
    async with PatternLabeller(
        timescale_url='postgresql+asyncpg://user:pass@localhost/db',
        mongo_url='mongodb://localhost:27017',
        mongo_db='agentictrader'
    ) as labeller:
        
        # Load candles
        candles = await labeller.get_candles(
            instrument='EURUSD',
            timeframe='M5',
            start_time=datetime.now() - timedelta(days=30),
            end_time=datetime.now(),
            limit=1000
        )
        
        # Save a label
        doc_id = await labeller.save_label(
            label='BOS_CONFIRMED',
            candle_window=candles[0:10],
            instrument='EURUSD',
            timeframe='M5',
            timestamp=candles[9]['time'],
            notes='Clear break of structure',
            labelled_by='analyst_1'
        )
        
        # Get label counts
        counts = await labeller.get_label_counts()
        print(counts)

# Run
asyncio.run(label_patterns())
```

## Testing

Run the test suite:

```bash
# From project root
python -m pytest backend/tests/test_pattern_labeller.py -v
```

Test coverage:
- ✅ Loading candles from TimescaleDB
- ✅ Saving labelled examples to MongoDB
- ✅ PatternLabeller initialization
- ✅ Getting candles for labelling
- ✅ Saving labels with metadata
- ✅ Getting label counts
- ✅ Context manager usage
- ✅ Empty result handling

## Data Quality Guidelines

When labelling patterns, follow these guidelines:

### BOS_CONFIRMED (Break of Structure)
- Clear break above previous swing high (bullish) or below previous swing low (bearish)
- Price closes beyond the structure level
- Ideally with strong momentum candle

### CHOCH_DETECTED (Change of Character)
- Shift in market structure direction
- First sign of potential trend reversal
- Look for failure to make new high/low

### SUPPLY_ZONE_REJECTION
- Price reaches supply zone (previous resistance)
- Strong rejection candle (long upper wick)
- Price closes below zone

### DEMAND_ZONE_BOUNCE
- Price reaches demand zone (previous support)
- Strong bounce candle (long lower wick)
- Price closes above zone

### FVG_PRESENT (Fair Value Gap)
- Gap between candle 1 high and candle 3 low (bullish FVG)
- Or gap between candle 1 low and candle 3 high (bearish FVG)
- Clear imbalance visible on chart

### LIQUIDITY_SWEEP
- Price briefly breaks swing high/low
- Then reverses sharply in opposite direction
- "Stop hunt" pattern

### ORDER_BLOCK
- Last bullish candle before bearish move (bearish OB)
- Or last bearish candle before bullish move (bullish OB)
- Institutional order accumulation zone

### INDUCEMENT
- False move to attract retail traders
- Followed by reversal in opposite direction
- Often precedes major move

## Next Steps

After collecting sufficient labelled data:

1. **Feature Engineering** (Task 19)
   - Extract features from labelled candle windows
   - Compute HTF projections, zone features, session features

2. **Model Training** (Task 21)
   - Train XGBoost classifier on labelled data
   - Validate with walk-forward testing
   - Tune hyperparameters with Optuna

3. **Model Deployment** (Task 22)
   - Deploy trained model to production
   - Integrate with real-time pattern detection pipeline

## Troubleshooting

### Connection Issues

**TimescaleDB connection fails:**
```bash
# Check TimescaleDB is running
docker ps | grep timescaledb

# Test connection
psql postgresql://agentictrader:changeme@localhost:5432/agentictrader
```

**MongoDB connection fails:**
```bash
# Check MongoDB is running
docker ps | grep mongo

# Test connection
mongosh mongodb://localhost:27017
```

### No Candles Loaded

- Verify historical data exists in TimescaleDB
- Check date range is valid
- Ensure instrument and timeframe have data
- Run: `python scripts/load_historical_data.py` to populate data

### UI Not Responding

- Check Streamlit logs for errors
- Verify all dependencies are installed
- Try restarting the Streamlit server
- Clear browser cache

## Performance

- **Load time:** ~1-2 seconds for 1000 candles
- **Save time:** ~100-200ms per label
- **UI responsiveness:** Real-time chart updates
- **Concurrent users:** Supports multiple labellers simultaneously

## Contributing

When adding new pattern labels:

1. Add label to `PATTERN_LABELS` list in `labeller.py`
2. Add window size to `WINDOW_SIZES` dict in `labeller_ui.py`
3. Update this README with pattern description
4. Add test cases for the new label

## License

Part of the AgentICTrader.AI platform.
