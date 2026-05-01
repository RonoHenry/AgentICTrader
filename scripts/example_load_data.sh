#!/bin/bash
# Example script to load historical data from OANDA
# This demonstrates various usage patterns

# Ensure environment variables are set
if [ -z "$OANDA_API_KEY" ]; then
    echo "Error: OANDA_API_KEY not set"
    echo "Please set: export OANDA_API_KEY='your_key_here'"
    exit 1
fi

if [ -z "$TIMESCALE_URL" ]; then
    echo "Error: TIMESCALE_URL not set"
    echo "Please set: export TIMESCALE_URL='postgresql+asyncpg://user:pass@host:port/db'"
    exit 1
fi

echo "==================================================================="
echo "AgentICTrader Historical Data Loading Examples"
echo "==================================================================="
echo ""

# Example 1: Load a single instrument-timeframe for testing
echo "Example 1: Load EURUSD H1 data (quick test)"
echo "-------------------------------------------------------------------"
python scripts/load_historical_data.py --instrument EURUSD --timeframe H1
echo ""

# Example 2: Load all timeframes for a single instrument
echo "Example 2: Load all EURUSD timeframes"
echo "-------------------------------------------------------------------"
python scripts/load_historical_data.py --instrument EURUSD
echo ""

# Example 3: Load a specific timeframe for all instruments
echo "Example 3: Load D1 data for all instruments"
echo "-------------------------------------------------------------------"
python scripts/load_historical_data.py --timeframe D1
echo ""

# Example 4: Load everything (this will take 2-4 hours)
echo "Example 4: Load all instruments and timeframes (FULL LOAD)"
echo "-------------------------------------------------------------------"
echo "WARNING: This will take 2-4 hours to complete!"
read -p "Continue? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    python scripts/load_historical_data.py
fi
echo ""

# Example 5: Resume interrupted load
echo "Example 5: Resume interrupted load"
echo "-------------------------------------------------------------------"
python scripts/load_historical_data.py --resume
echo ""

echo "==================================================================="
echo "Examples completed!"
echo "==================================================================="
