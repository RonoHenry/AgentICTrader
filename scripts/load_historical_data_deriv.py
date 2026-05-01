#!/usr/bin/env python3
"""
Load 3 years of historical OHLCV data from Deriv API.

This script fetches historical candle data for configured instruments and timeframes
from Deriv's WebSocket API and loads it into TimescaleDB.

Features:
- Uses Deriv API (no signup required for demo data)
- Handles pagination (max 5000 candles per request)
- Validates OHLC integrity
- Detects gaps in data
- Supports resuming from last loaded timestamp
- Batch inserts for performance
- Detailed logging and summary statistics

Usage:
    python scripts/load_historical_data_deriv.py [--instrument EURUSD] [--timeframe M1] [--resume]

Environment Variables:
    DERIV_APP_ID: Deriv app ID (default: 1089 for testing)
    TIMESCALE_URL: PostgreSQL connection string
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import json
import time

import asyncpg

# ── DERIV API CLIENT (Embedded) ────────────────────────────────────────────

class APIError(Exception):
    """Base class for API related errors"""
    def __init__(self, code: str = None, message: str = None):
        self.code = code
        self.message = message
        super().__init__(message or code)


class DerivAPIClientSimple:
    """Simplified Deriv API client for historical data fetching."""

    def __init__(self, app_id: str = "1089", rate_limit_per_second: int = 2):
        self.app_id = app_id
        self._endpoint = f"wss://ws.binaryws.com/websockets/v3?app_id={app_id}"
        self.rate_limit = rate_limit_per_second
        self.last_request_time = 0.0
        self._ws = None
        self._connected = False

    async def connect(self) -> None:
        """Establish WebSocket connection."""
        if not self._connected:
            import websockets
            logger.info(f"Connecting to Deriv API...")
            self._ws = await websockets.connect(self._endpoint)
            self._connected = True
            logger.info("Connected to Deriv API")

    async def close(self) -> None:
        """Close the WebSocket connection."""
        if self._ws:
            try:
                await self._ws.close()
            except Exception as e:
                logger.warning(f"Error closing connection: {e}")
            finally:
                self._ws = None
                self._connected = False

    async def get_ohlc(self, symbol: str, interval: int = 60, count: int = 100) -> List[Dict]:
        """Get historical OHLC candles."""
        if not self._ws:
            await self.connect()

        await self._apply_rate_limit()

        request = {
            "ticks_history": symbol,
            "adjust_start_time": 1,
            "count": count,
            "end": "latest",
            "granularity": interval,
            "style": "candles"
        }

        await self._ws.send(json.dumps(request))
        response_data = json.loads(await self._ws.recv())

        if "error" in response_data:
            raise APIError(
                code=response_data["error"].get("code", "UnknownError"),
                message=response_data["error"].get("message", "Unknown error")
            )

        candles = response_data.get("candles", [])
        
        # Validate candles
        for candle in candles:
            if not all(k in candle for k in ["open", "high", "low", "close"]):
                raise APIError(code="InvalidData", message="Incomplete OHLC data received")
            if not (float(candle["low"]) <= float(candle["open"]) <= float(candle["high"]) and
                    float(candle["low"]) <= float(candle["close"]) <= float(candle["high"])):
                raise APIError(code="InvalidData", message="OHLC values are inconsistent")
        
        return candles

    async def _apply_rate_limit(self) -> None:
        """Enforce rate limiting between requests."""
        if self.rate_limit <= 0:
            return
        min_interval = 1.0 / self.rate_limit
        wait_time = min_interval - (time.time() - self.last_request_time)
        if wait_time > 0:
            await asyncio.sleep(wait_time)
        self.last_request_time = time.time()


# ── CONFIGURATION ──────────────────────────────────────────────────────────

# Instrument mapping: Platform name → Deriv symbol
INSTRUMENT_MAPPING = {
    "EURUSD": "frxEURUSD",
    "GBPUSD": "frxGBPUSD",
    "XAUUSD": "frxXAUUSD",
    # Deriv also has synthetic indices
    "R_100": "R_100",  # Volatility 100 Index
    "R_50": "R_50",    # Volatility 50 Index
}

# Timeframe mapping: Platform name → Deriv granularity (seconds)
TIMEFRAME_MAPPING = {
    "M1": 60,
    "M5": 300,
    "M15": 900,
    "H1": 3600,
    "H4": 14400,
    "D1": 86400,
}

# Timeframe durations in seconds (for gap detection)
TIMEFRAME_DURATIONS = TIMEFRAME_MAPPING.copy()

# Deriv API configuration
MAX_CANDLES_PER_REQUEST = 5000
BATCH_INSERT_SIZE = 1000
RATE_LIMIT_PER_SECOND = 2  # Deriv allows ~2 requests per second

# Historical data period
HISTORICAL_YEARS = 3

# ── LOGGING ────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("load_historical_data_deriv.log"),
    ],
)
logger = logging.getLogger(__name__)


# ── DATA MODELS ────────────────────────────────────────────────────────────

@dataclass
class Candle:
    """Represents a single OHLCV candle."""
    time: datetime
    instrument: str
    timeframe: str
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    complete: bool
    source: str = "deriv"

    def validate_ohlc(self) -> bool:
        """Validate OHLC integrity: high >= open/close/low, low <= open/close/high."""
        if self.high < self.open or self.high < self.close or self.high < self.low:
            return False
        if self.low > self.open or self.low > self.close or self.low > self.high:
            return False
        return True


@dataclass
class LoadSummary:
    """Summary statistics for a data load operation."""
    instrument: str
    timeframe: str
    row_count: int
    date_range_start: Optional[datetime]
    date_range_end: Optional[datetime]
    gap_count: int
    validation_errors: int
    duration_seconds: float


# ── DERIV API CLIENT ───────────────────────────────────────────────────────

class DerivHistoricalClient:
    """Client for fetching historical candle data from Deriv API."""

    def __init__(self, app_id: str = "1089"):
        """
        Initialize the Deriv historical data client.

        Args:
            app_id: Deriv app ID (default: 1089 for testing)
        """
        self.client = DerivAPIClientSimple(
            app_id=app_id,
            rate_limit_per_second=RATE_LIMIT_PER_SECOND
        )

    async def connect(self):
        """Connect to Deriv API."""
        await self.client.connect()
        logger.info("Connected to Deriv API")

    async def close(self):
        """Close connection."""
        await self.client.close()

    async def fetch_all_candles(
        self,
        symbol: str,
        granularity: int,
        from_time: datetime,
        to_time: datetime,
        platform_instrument: str,
        platform_timeframe: str,
    ) -> List[Candle]:
        """
        Fetch all candles for a time range, handling pagination.

        Args:
            symbol: Deriv symbol (e.g., 'frxEURUSD')
            granularity: Candle interval in seconds
            from_time: Start time (inclusive)
            to_time: End time (inclusive)
            platform_instrument: Platform instrument name
            platform_timeframe: Platform timeframe name

        Returns:
            List of Candle objects
        """
        all_candles: List[Candle] = []
        current_to = to_time

        logger.info(
            f"Fetching {symbol} (granularity={granularity}s) from {from_time} to {to_time}"
        )

        # Deriv API works backwards from end time
        while current_to > from_time:
            try:
                # Fetch batch of candles
                raw_candles = await self.client.get_ohlc(
                    symbol=symbol,
                    interval=granularity,
                    count=MAX_CANDLES_PER_REQUEST,
                )

                if not raw_candles:
                    logger.info(f"No more candles available before {current_to}")
                    break

                # Parse candles
                batch_candles = []
                for raw_candle in raw_candles:
                    try:
                        candle = self._parse_candle(
                            raw_candle,
                            platform_instrument,
                            platform_timeframe,
                        )
                        
                        # Only include candles within our time range
                        if from_time <= candle.time <= to_time:
                            batch_candles.append(candle)
                    except Exception as e:
                        logger.error(f"Failed to parse candle: {e} - {raw_candle}")

                if not batch_candles:
                    break

                all_candles.extend(batch_candles)

                # Update pagination cursor (move backwards in time)
                oldest_candle_time = min(c.time for c in batch_candles)
                if oldest_candle_time >= current_to:
                    # Safety check to prevent infinite loop
                    logger.warning("Pagination cursor did not move backwards. Breaking.")
                    break
                
                current_to = oldest_candle_time - timedelta(seconds=1)

                logger.info(
                    f"Fetched {len(batch_candles)} candles. "
                    f"Total: {len(all_candles)}. Oldest: {oldest_candle_time}"
                )

                # Check if we've gone far enough back
                if oldest_candle_time <= from_time:
                    break

            except APIError as e:
                logger.error(f"API error: {e.code} - {e.message}")
                if e.code == "RateLimit":
                    logger.info("Rate limited. Waiting 5 seconds...")
                    await asyncio.sleep(5)
                    continue
                else:
                    raise

        # Sort by time (ascending)
        all_candles.sort(key=lambda c: c.time)

        logger.info(
            f"Completed fetching {symbol}: {len(all_candles)} candles"
        )
        return all_candles

    def _parse_candle(
        self,
        raw_candle: Dict[str, Any],
        instrument: str,
        timeframe: str,
    ) -> Candle:
        """Parse Deriv candle response into Candle object."""
        return Candle(
            time=datetime.fromtimestamp(int(raw_candle["epoch"]), tz=timezone.utc),
            instrument=instrument,
            timeframe=timeframe,
            open=Decimal(str(raw_candle["open"])),
            high=Decimal(str(raw_candle["high"])),
            low=Decimal(str(raw_candle["low"])),
            close=Decimal(str(raw_candle["close"])),
            volume=0,  # Deriv doesn't provide volume for forex
            complete=True,
            source="deriv",
        )


# ── DATABASE OPERATIONS ────────────────────────────────────────────────────

class TimescaleDBLoader:
    """Handles loading candle data into TimescaleDB."""

    def __init__(self, connection_string: str):
        """
        Initialize the TimescaleDB loader.

        Args:
            connection_string: PostgreSQL connection string
        """
        self.connection_string = connection_string
        self.pool: Optional[asyncpg.Pool] = None

    async def connect(self) -> None:
        """Create database connection pool."""
        self.pool = await asyncpg.create_pool(
            self.connection_string,
            min_size=5,
            max_size=20,
        )
        logger.info("Connected to TimescaleDB")

    async def close(self) -> None:
        """Close database connection pool."""
        if self.pool:
            await self.pool.close()
            logger.info("Closed TimescaleDB connection")

    async def get_last_loaded_time(
        self,
        instrument: str,
        timeframe: str,
    ) -> Optional[datetime]:
        """
        Get the timestamp of the last loaded candle for resuming.

        Args:
            instrument: Platform instrument name
            timeframe: Platform timeframe

        Returns:
            Last candle timestamp or None if no data exists
        """
        if not self.pool:
            raise RuntimeError("Database not connected")

        query = """
            SELECT MAX(time) as last_time
            FROM candles
            WHERE instrument = $1 AND timeframe = $2 AND source = 'deriv'
        """

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, instrument, timeframe)
            return row["last_time"] if row and row["last_time"] else None

    async def load_candles(
        self,
        candles: List[Candle],
        batch_size: int = BATCH_INSERT_SIZE,
    ) -> Tuple[int, int]:
        """
        Load candles into TimescaleDB with batch inserts.

        Uses ON CONFLICT DO UPDATE to handle duplicate timestamps.

        Args:
            candles: List of Candle objects
            batch_size: Number of candles per batch insert

        Returns:
            Tuple of (inserted_count, validation_error_count)
        """
        if not self.pool:
            raise RuntimeError("Database not connected")

        if not candles:
            return 0, 0

        insert_query = """
            INSERT INTO candles (
                time, instrument, timeframe, open, high, low, close,
                volume, spread, complete, source, created_at
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, NOW())
            ON CONFLICT (time, instrument, timeframe)
            DO UPDATE SET
                open = EXCLUDED.open,
                high = EXCLUDED.high,
                low = EXCLUDED.low,
                close = EXCLUDED.close,
                volume = EXCLUDED.volume,
                complete = EXCLUDED.complete,
                source = EXCLUDED.source
        """

        inserted_count = 0
        validation_error_count = 0

        async with self.pool.acquire() as conn:
            for i in range(0, len(candles), batch_size):
                batch = candles[i:i + batch_size]
                batch_data = []

                for candle in batch:
                    # Validate OHLC integrity
                    if not candle.validate_ohlc():
                        logger.warning(
                            f"OHLC validation failed: {candle.instrument} "
                            f"{candle.timeframe} {candle.time} "
                            f"O={candle.open} H={candle.high} L={candle.low} C={candle.close}"
                        )
                        validation_error_count += 1
                        continue

                    batch_data.append((
                        candle.time,
                        candle.instrument,
                        candle.timeframe,
                        candle.open,
                        candle.high,
                        candle.low,
                        candle.close,
                        candle.volume,
                        None,  # spread
                        candle.complete,
                        candle.source,
                    ))

                if batch_data:
                    await conn.executemany(insert_query, batch_data)
                    inserted_count += len(batch_data)

                logger.info(
                    f"Inserted batch {i // batch_size + 1}: "
                    f"{len(batch_data)} candles (total: {inserted_count})"
                )

        return inserted_count, validation_error_count


# ── DATA VALIDATION ────────────────────────────────────────────────────────

def detect_gaps(
    candles: List[Candle],
    timeframe: str,
) -> List[Tuple[datetime, datetime, float]]:
    """
    Detect gaps in candle data (> 2x timeframe duration).

    Args:
        candles: List of Candle objects (must be sorted by time)
        timeframe: Platform timeframe

    Returns:
        List of (gap_start, gap_end, gap_hours) tuples
    """
    if not candles or len(candles) < 2:
        return []

    gaps = []
    timeframe_seconds = TIMEFRAME_DURATIONS.get(timeframe, 60)
    max_gap_seconds = timeframe_seconds * 2

    for i in range(1, len(candles)):
        prev_candle = candles[i - 1]
        curr_candle = candles[i]
        gap_seconds = (curr_candle.time - prev_candle.time).total_seconds()

        if gap_seconds > max_gap_seconds:
            gap_hours = gap_seconds / 3600
            gaps.append((prev_candle.time, curr_candle.time, gap_hours))
            logger.warning(
                f"Gap detected: {prev_candle.instrument} {timeframe} "
                f"{prev_candle.time} → {curr_candle.time} ({gap_hours:.2f} hours)"
            )

    return gaps


# ── MAIN ORCHESTRATION ─────────────────────────────────────────────────────

async def load_instrument_timeframe(
    deriv_client: DerivHistoricalClient,
    db_loader: TimescaleDBLoader,
    instrument: str,
    timeframe: str,
    resume: bool = False,
) -> LoadSummary:
    """
    Load historical data for a single instrument-timeframe pair.

    Args:
        deriv_client: Deriv API client
        db_loader: Database loader
        instrument: Platform instrument name
        timeframe: Platform timeframe
        resume: If True, resume from last loaded timestamp

    Returns:
        LoadSummary with statistics
    """
    start_time = datetime.now()

    # Map to Deriv names
    deriv_symbol = INSTRUMENT_MAPPING[instrument]
    deriv_granularity = TIMEFRAME_MAPPING[timeframe]

    # Determine time range
    to_time = datetime.now(timezone.utc)
    from_time = to_time - timedelta(days=HISTORICAL_YEARS * 365)

    # Resume from last loaded timestamp if requested
    if resume:
        last_time = await db_loader.get_last_loaded_time(instrument, timeframe)
        if last_time:
            from_time = last_time
            logger.info(
                f"Resuming {instrument} {timeframe} from {from_time}"
            )

    # Fetch candles
    candles = await deriv_client.fetch_all_candles(
        symbol=deriv_symbol,
        granularity=deriv_granularity,
        from_time=from_time,
        to_time=to_time,
        platform_instrument=instrument,
        platform_timeframe=timeframe,
    )

    # Detect gaps
    gaps = detect_gaps(candles, timeframe)

    # Load into database
    inserted_count, validation_errors = await db_loader.load_candles(candles)

    # Calculate summary
    duration = (datetime.now() - start_time).total_seconds()
    date_range_start = candles[0].time if candles else None
    date_range_end = candles[-1].time if candles else None

    summary = LoadSummary(
        instrument=instrument,
        timeframe=timeframe,
        row_count=inserted_count,
        date_range_start=date_range_start,
        date_range_end=date_range_end,
        gap_count=len(gaps),
        validation_errors=validation_errors,
        duration_seconds=duration,
    )

    logger.info(
        f"✓ {instrument} {timeframe}: {inserted_count} candles loaded, "
        f"{len(gaps)} gaps, {validation_errors} validation errors, "
        f"{duration:.2f}s"
    )

    return summary


async def load_all_data(
    instruments: List[str],
    timeframes: List[str],
    resume: bool = False,
) -> List[LoadSummary]:
    """
    Load historical data for all instrument-timeframe combinations.

    Args:
        instruments: List of platform instrument names
        timeframes: List of platform timeframes
        resume: If True, resume from last loaded timestamps

    Returns:
        List of LoadSummary objects
    """
    # Get environment variables
    app_id = os.getenv("DERIV_APP_ID", "1089")  # Default test app ID
    connection_string = os.getenv("TIMESCALE_URL")

    if not connection_string:
        raise ValueError("TIMESCALE_URL environment variable not set")

    logger.info("=" * 80)
    logger.info("AgentICTrader Historical Data Loader (Deriv)")
    logger.info("=" * 80)
    logger.info(f"Instruments: {', '.join(instruments)}")
    logger.info(f"Timeframes: {', '.join(timeframes)}")
    logger.info(f"Historical period: {HISTORICAL_YEARS} years")
    logger.info(f"Deriv App ID: {app_id}")
    logger.info(f"Resume mode: {resume}")
    logger.info("=" * 80)

    summaries: List[LoadSummary] = []

    # Initialize clients
    deriv_client = DerivHistoricalClient(app_id)
    await deriv_client.connect()

    db_loader = TimescaleDBLoader(connection_string)
    await db_loader.connect()

    try:
        # Load each instrument-timeframe combination
        for instrument in instruments:
            for timeframe in timeframes:
                try:
                    summary = await load_instrument_timeframe(
                        deriv_client=deriv_client,
                        db_loader=db_loader,
                        instrument=instrument,
                        timeframe=timeframe,
                        resume=resume,
                    )
                    summaries.append(summary)
                except Exception as e:
                    logger.error(
                        f"Failed to load {instrument} {timeframe}: {e}",
                        exc_info=True,
                    )
                    # Continue with next combination
                    summaries.append(
                        LoadSummary(
                            instrument=instrument,
                            timeframe=timeframe,
                            row_count=0,
                            date_range_start=None,
                            date_range_end=None,
                            gap_count=0,
                            validation_errors=0,
                            duration_seconds=0,
                        )
                    )
    finally:
        await deriv_client.close()
        await db_loader.close()

    return summaries


def print_summary_report(summaries: List[LoadSummary]) -> None:
    """Print a formatted summary report."""
    logger.info("")
    logger.info("=" * 80)
    logger.info("LOAD SUMMARY REPORT")
    logger.info("=" * 80)
    logger.info(
        f"{'Instrument':<10} {'Timeframe':<10} {'Rows':<10} "
        f"{'Date Range':<40} {'Gaps':<6} {'Errors':<8} {'Duration':<10}"
    )
    logger.info("-" * 80)

    total_rows = 0
    total_gaps = 0
    total_errors = 0
    total_duration = 0.0

    for summary in summaries:
        date_range = "N/A"
        if summary.date_range_start and summary.date_range_end:
            date_range = (
                f"{summary.date_range_start.strftime('%Y-%m-%d')} → "
                f"{summary.date_range_end.strftime('%Y-%m-%d')}"
            )

        logger.info(
            f"{summary.instrument:<10} {summary.timeframe:<10} "
            f"{summary.row_count:<10} {date_range:<40} "
            f"{summary.gap_count:<6} {summary.validation_errors:<8} "
            f"{summary.duration_seconds:<10.2f}s"
        )

        total_rows += summary.row_count
        total_gaps += summary.gap_count
        total_errors += summary.validation_errors
        total_duration += summary.duration_seconds

    logger.info("-" * 80)
    logger.info(
        f"{'TOTAL':<10} {'':<10} {total_rows:<10} {'':<40} "
        f"{total_gaps:<6} {total_errors:<8} {total_duration:<10.2f}s"
    )
    logger.info("=" * 80)


# ── CLI ENTRY POINT ────────────────────────────────────────────────────────

def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Load historical OHLCV data from Deriv API"
    )
    parser.add_argument(
        "--instrument",
        type=str,
        help="Single instrument to load (default: all)",
    )
    parser.add_argument(
        "--timeframe",
        type=str,
        help="Single timeframe to load (default: all)",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from last loaded timestamp",
    )

    args = parser.parse_args()

    # Determine instruments and timeframes to load
    instruments = (
        [args.instrument] if args.instrument else list(INSTRUMENT_MAPPING.keys())
    )
    timeframes = (
        [args.timeframe] if args.timeframe else list(TIMEFRAME_MAPPING.keys())
    )

    # Validate inputs
    invalid_instruments = [i for i in instruments if i not in INSTRUMENT_MAPPING]
    if invalid_instruments:
        logger.error(f"Invalid instruments: {invalid_instruments}")
        logger.error(f"Valid instruments: {list(INSTRUMENT_MAPPING.keys())}")
        sys.exit(1)

    invalid_timeframes = [t for t in timeframes if t not in TIMEFRAME_MAPPING]
    if invalid_timeframes:
        logger.error(f"Invalid timeframes: {invalid_timeframes}")
        logger.error(f"Valid timeframes: {list(TIMEFRAME_MAPPING.keys())}")
        sys.exit(1)

    # Run async load
    try:
        summaries = asyncio.run(
            load_all_data(
                instruments=instruments,
                timeframes=timeframes,
                resume=args.resume,
            )
        )
        print_summary_report(summaries)
        logger.info("✓ Historical data load completed successfully")
    except KeyboardInterrupt:
        logger.warning("Load interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Load failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
