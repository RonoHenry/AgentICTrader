#!/bin/sh
# Fill any gap in TimescaleDB since the last run, then start the live loop.
# A failed backfill (feed down at startup) doesn't block the loop — the loop
# retries the feed every pass and stores what it fetches.
set -u

# When Docker itself restarts (Docker Desktop launch, reboot), restart
# policies bring both containers up together and ignore depends_on, so the
# backfill used to hit "the database system is starting up" and skip. Wait
# for TimescaleDB to accept connections first (up to 2 minutes).
python - <<'EOF' || echo "TimescaleDB not reachable after 120 s - continuing; the backfill will report it"
import asyncio, os, time
import asyncpg

async def wait_for_db():
    deadline = time.monotonic() + 120
    while True:
        try:
            conn = await asyncpg.connect(os.environ["TIMESCALE_URL"], timeout=5)
            await conn.close()
            print("TimescaleDB is ready", flush=True)
            return
        except Exception as exc:
            if time.monotonic() > deadline:
                raise
            print(f"Waiting for TimescaleDB: {exc}", flush=True)
            await asyncio.sleep(3)

asyncio.run(wait_for_db())
EOF

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
