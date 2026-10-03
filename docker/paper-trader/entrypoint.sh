#!/bin/sh
# Fill any gap in TimescaleDB since the last run, then start the live loop.
# A failed backfill (feed down at startup) doesn't block the loop — the loop
# retries the feed every pass and stores what it fetches.
set -u

python scripts/load_historical_data_binance.py \
    --resume --years "${BACKFILL_YEARS}" --instruments "${INSTRUMENTS}" \
    || echo "Backfill failed - starting the live loop anyway"

exec python scripts/run_live_agent.py \
    --feed binance --loop \
    --timeframe "${ENTRY_TIMEFRAME}" \
    --instruments "${INSTRUMENTS}" \
    --store-candles \
    --heartbeat /app/data/heartbeat \
    --paper-state /app/data/paper_trades.json
