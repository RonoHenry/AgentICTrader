#!/usr/bin/env python3
"""
Load historical crypto OHLCV data from Binance into TimescaleDB.

Crypto trades 24/7, so this keeps development going when FX/indices are
closed (the MT5 demo server lists no crypto CFDs). Uses Binance's public
market-data API via services/market_data/binance.py — no account or key.
Reuses the OANDA loader's TimescaleDB writer, OHLC validation, gap detection
and summary report.

- Bars are UTC-aligned (D1 opens 00:00 UTC, W1 Monday 00:00 UTC); H3 is built
  from H1.
- volume = trade count per bar (integer, the closest analogue to MT5's
  tick_volume).
- Rows are written with source='binance' under the exchange's own symbol
  (e.g. BTCUSDT), so they never collide with broker rows.
- Pages are streamed into the database in batches, so years of M1 don't have
  to fit in memory.

Usage:
    python scripts/load_historical_data_binance.py [--instruments BTCUSDT,ETHUSDT]
        [--timeframes M15,H1] [--years 3] [--resume] [--dry-run]

Environment (.env):
    TIMESCALE_URL: PostgreSQL connection string (not needed with --dry-run)
    BINANCE_API_URL: optional, defaults to https://data-api.binance.vision
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import List, Optional

from decouple import AutoConfig

sys.stdout.reconfigure(encoding="utf-8")

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from load_historical_data import (
    Candle,
    LoadSummary,
    TimescaleDBLoader,
    detect_gaps,
    print_summary_report,
)
from services.market_data.binance import TIMEFRAMES, BinanceKlineClient, Kline

logger = logging.getLogger("load_historical_data_binance")

# Environment variables win; the repo .env is the fallback (absent in Docker).
config = AutoConfig(search_path=str(REPO_ROOT))

DEFAULT_INSTRUMENTS = ["BTCUSDT", "ETHUSDT"]
HISTORICAL_YEARS = 3
# Candles accumulated before each database write.
WRITE_BATCH = 20_000


def _to_candle(k: Kline, instrument: str, timeframe: str) -> Candle:
    return Candle(
        time=k.open_time,
        instrument=instrument,
        timeframe=timeframe,
        open=Decimal(k.open),
        high=Decimal(k.high),
        low=Decimal(k.low),
        close=Decimal(k.close),
        volume=k.trades,
        complete=k.complete,
        source="binance",
    )


async def load_instrument_timeframe(
    client: BinanceKlineClient,
    db_loader: Optional[TimescaleDBLoader],
    instrument: str,
    timeframe: str,
    years: float,
    resume: bool,
) -> LoadSummary:
    started = time.monotonic()
    to_time = datetime.now(timezone.utc)
    from_time = to_time - timedelta(days=years * 365)

    if resume and db_loader:
        last_time = await db_loader.get_last_loaded_time(instrument, timeframe, source="binance")
        if last_time:
            # Re-fetch the last bar too: it may have been stored incomplete.
            from_time = last_time
            logger.info(f"Resuming {instrument} {timeframe} from {from_time}")

    logger.info(f"Fetching {instrument} {timeframe} from {from_time:%Y-%m-%d %H:%M} to {to_time:%Y-%m-%d %H:%M} UTC")

    loaded = errors = gaps = 0
    first: Optional[Candle] = None
    last: Optional[Candle] = None
    pending: List[Candle] = []

    async def flush() -> None:
        nonlocal loaded, errors, gaps, last
        if not pending:
            return
        # Prepend the previous batch's last bar so gaps across batches count.
        gaps += len(detect_gaps(([last] if last else []) + pending, timeframe))
        if db_loader:
            n, e = await db_loader.load_candles(pending)
        else:
            n = sum(1 for c in pending if c.validate_ohlc())
            e = len(pending) - n
        loaded += n
        errors += e
        last = pending[-1]
        pending.clear()

    for page in client.iter_range(instrument, timeframe, from_time, to_time):
        candles = [_to_candle(k, instrument, timeframe) for k in page]
        if first is None and candles:
            first = candles[0]
        pending.extend(candles)
        if len(pending) >= WRITE_BATCH:
            await flush()
            logger.info(f"  {instrument} {timeframe}: {loaded} candles through {last.time:%Y-%m-%d %H:%M}")
    await flush()

    if first and first.time - from_time > timedelta(days=7):
        logger.warning(f"{instrument} {timeframe}: history starts at {first.time:%Y-%m-%d} (listing date)")

    logger.info(
        f"✓ {instrument} {timeframe}: {loaded} candles {'loaded' if db_loader else 'validated'}, "
        f"{gaps} gaps, {errors} validation errors"
    )
    return LoadSummary(
        instrument=instrument,
        timeframe=timeframe,
        row_count=loaded,
        date_range_start=first.time if first else None,
        date_range_end=last.time if last else None,
        gap_count=gaps,
        validation_errors=errors,
        duration_seconds=time.monotonic() - started,
    )


async def load_all_data(
    instruments: List[str],
    timeframes: List[str],
    years: float,
    resume: bool,
    dry_run: bool,
) -> List[LoadSummary]:
    client = BinanceKlineClient(base_url=config("BINANCE_API_URL", default="") or None)

    logger.info("=" * 80)
    logger.info("AgentICTrader Historical Data Loader — Binance (crypto)")
    logger.info("=" * 80)
    logger.info(f"Source: {client.base_url}")
    logger.info(f"Instruments: {', '.join(instruments)}")
    logger.info(f"Timeframes: {', '.join(timeframes)}")
    logger.info(f"Historical period: {years} years")
    logger.info(f"Resume mode: {resume}   Dry run: {dry_run}")
    logger.info("=" * 80)

    db_loader: Optional[TimescaleDBLoader] = None
    if not dry_run:
        connection_string = config("TIMESCALE_URL", default="")
        if not connection_string:
            raise ValueError("TIMESCALE_URL not set (use --dry-run to fetch without writing)")
        db_loader = TimescaleDBLoader(connection_string)
        await db_loader.connect()

    summaries: List[LoadSummary] = []
    try:
        for instrument in instruments:
            for timeframe in timeframes:
                try:
                    summaries.append(
                        await load_instrument_timeframe(client, db_loader, instrument, timeframe, years, resume)
                    )
                except Exception as e:
                    logger.error(f"Failed to load {instrument} {timeframe}: {e}")
                    summaries.append(LoadSummary(instrument, timeframe, 0, None, None, 0, 0, 0))
    finally:
        if db_loader:
            await db_loader.close()
    return summaries


def _csv(value: str) -> List[str]:
    return [v.strip().upper() for v in value.split(",") if v.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(description="Load historical crypto OHLCV data from Binance")
    parser.add_argument("--instruments", type=_csv, default=DEFAULT_INSTRUMENTS,
                        help=f"Comma-separated Binance symbols (default: {','.join(DEFAULT_INSTRUMENTS)})")
    parser.add_argument("--timeframes", type=_csv, default=list(TIMEFRAMES),
                        help=f"Comma-separated timeframes (default: {','.join(TIMEFRAMES)})")
    parser.add_argument("--years", type=float, default=HISTORICAL_YEARS,
                        help=f"Years of history to load (default: {HISTORICAL_YEARS})")
    parser.add_argument("--resume", action="store_true", help="Resume from the last loaded Binance timestamp")
    parser.add_argument("--dry-run", action="store_true", help="Fetch and validate without writing to TimescaleDB")
    args = parser.parse_args()

    invalid = [t for t in args.timeframes if t not in TIMEFRAMES]
    if invalid:
        logger.error(f"Invalid timeframes: {invalid}. Valid: {TIMEFRAMES}")
        sys.exit(1)

    try:
        summaries = asyncio.run(
            load_all_data(args.instruments, args.timeframes, args.years, args.resume, args.dry_run)
        )
        print_summary_report(summaries)
    except KeyboardInterrupt:
        logger.warning("Load interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Load failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
