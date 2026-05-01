#!/usr/bin/env python3
"""
Load 3 years of historical OHLCV data from OANDA v20 REST API.

This script fetches historical candle data for all configured instruments and timeframes,
validates data integrity, and loads it into TimescaleDB.

Features:
- Fetches from OANDA v20 REST API: GET /v3/instruments/{instrument}/candles
- Handles pagination (max 5000 candles per request)
- Validates OHLC integrity (high >= open/close/low, low <= open/close/high)
- Detects gaps in data (> 2x timeframe duration on trading days)
- Supports resuming from last loaded timestamp
- Batch inserts for performance
- Detailed logging and summary statistics

Usage:
    python scripts/load_historical_data.py [--instrument EURUSD] [--timeframe M1] [--resume]

Environment Variables:
    OANDA_API_KEY: OANDA API access token
    OANDA_ACCOUNT_ID: OANDA account ID
    OANDA_ENVIRONMENT: practice or live (default: practice)
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
from typing import Any, Dict, List, Optional, Tuple

import aiohttp
import asyncpg
from dateutil import parser as date_parser

# ── CONFIGURATION ──────────────────────────────────────────────────────────

# Instrument mapping: Platform name → OANDA API name
INSTRUMENT_MAPPING = {
    "EURUSD": "EUR_USD",
    "GBPUSD": "GBP_USD",
    "US500": "SPX500_USD",
    "US30": "US30_USD",
    "XAUUSD": "XAU_USD",
}

# Timeframe mapping: Platform name → OANDA granularity
TIMEFRAME_MAPPING = {
    "M1": "M1",
    "M5": "M5",
    "M15": "M15",
    "H1": "H1",
    "H4": "H4",
    "D1": "D",
    "W1": "W",
}

# Timeframe durations in seconds (for gap detection)
TIMEFRAME_DURATIONS = {
    "M1": 60,
    "M5": 300,
    "M15": 900,
    "H1": 3600,
    "H4": 14400,
    "D1": 86400,
    "W1": 604800,
}

# OANDA API configuration
OANDA_REST_API_URLS = {
    "practice": "https://api-fxpractice.oanda.com",
    "live": "https://api-fxtrade.oanda.com",
}

MAX_CANDLES_PER_REQUEST = 5000
BATCH_INSERT_SIZE = 1000
MAX_RETRIES = 3
RETRY_DELAY = 2.0  # seconds

# Historical data period
HISTORICAL_YEARS = 3

# ── LOGGING ────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("load_historical_data.log"),
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
    source: str = "oanda"

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


# ── OANDA API CLIENT ───────────────────────────────────────────────────────

class OANDAHistoricalClient:
    """Client for fetching historical candle data from OANDA v20 REST API."""

    def __init__(
        self,
        api_key: str,
        environment: str = "practice",
        max_retries: int = MAX_RETRIES,
    ):
        """
        Initialize the OANDA historical data client.

        Args:
            api_key: OANDA API access token
            environment: 'practice' or 'live'
            max_retries: Maximum number of retry attempts for failed requests
        """
        self.api_key = api_key
        self.base_url = OANDA_REST_API_URLS[environment]
        self.max_retries = max_retries
        self.session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self):
        """Create aiohttp session."""
        self.session = aiohttp.ClientSession(
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Close aiohttp session."""
        if self.session:
            await self.session.close()

    async def fetch_candles(
        self,
        instrument: str,
        granularity: str,
        from_time: datetime,
        to_time: datetime,
        count: int = MAX_CANDLES_PER_REQUEST,
    ) -> List[Dict[str, Any]]:
        """
        Fetch candles from OANDA API with retry logic.

        Args:
            instrument: OANDA instrument name (e.g., 'EUR_USD')
            granularity: OANDA granularity (e.g., 'M1', 'H1', 'D')
            from_time: Start time (inclusive)
            to_time: End time (inclusive)
            count: Maximum number of candles to fetch (max 5000)

        Returns:
            List of candle dictionaries

        Raises:
            Exception: If all retry attempts fail
        """
        if not self.session:
            raise RuntimeError("Client not initialized. Use async context manager.")

        url = f"{self.base_url}/v3/instruments/{instrument}/candles"
        params = {
            "granularity": granularity,
            "from": from_time.strftime("%Y-%m-%dT%H:%M:%S.000000000Z"),
            "to": to_time.strftime("%Y-%m-%dT%H:%M:%S.000000000Z"),
            "count": count,
        }

        for attempt in range(self.max_retries):
            try:
                async with self.session.get(url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data.get("candles", [])
                    elif response.status == 429:
                        # Rate limit - wait and retry
                        retry_after = int(response.headers.get("Retry-After", RETRY_DELAY))
                        logger.warning(
                            f"Rate limited. Waiting {retry_after}s before retry "
                            f"(attempt {attempt + 1}/{self.max_retries})"
                        )
                        await asyncio.sleep(retry_after)
                    else:
                        error_text = await response.text()
                        logger.error(
                            f"API error {response.status}: {error_text} "
                            f"(attempt {attempt + 1}/{self.max_retries})"
                        )
                        if attempt < self.max_retries - 1:
                            await asyncio.sleep(RETRY_DELAY * (attempt + 1))
            except aiohttp.ClientError as e:
                logger.error(
                    f"Network error: {e} (attempt {attempt + 1}/{self.max_retries})"
                )
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(RETRY_DELAY * (attempt + 1))
            except Exception as e:
                logger.error(
                    f"Unexpected error: {e} (attempt {attempt + 1}/{self.max_retries})"
                )
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(RETRY_DELAY * (attempt + 1))

        raise Exception(
            f"Failed to fetch candles after {self.max_retries} attempts: "
            f"{instrument} {granularity} {from_time} to {to_time}"
        )

    async def fetch_all_candles(
        self,
        instrument: str,
        granularity: str,
        from_time: datetime,
        to_time: datetime,
    ) -> List[Candle]:
        """
        Fetch all candles for a time range, handling pagination.

        Args:
            instrument: OANDA instrument name (e.g., 'EUR_USD')
            granularity: OANDA granularity (e.g., 'M1', 'H1', 'D')
            from_time: Start time (inclusive)
            to_time: End time (inclusive)

        Returns:
            List of Candle objects
        """
        all_candles: List[Candle] = []
        current_from = from_time
        platform_instrument = self._get_platform_instrument(instrument)
        platform_timeframe = self._get_platform_timeframe(granularity)

        logger.info(
            f"Fetching {instrument} {granularity} from {from_time} to {to_time}"
        )

        while current_from < to_time:
            raw_candles = await self.fetch_candles(
                instrument=instrument,
                granularity=granularity,
                from_time=current_from,
                to_time=to_time,
                count=MAX_CANDLES_PER_REQUEST,
            )

            if not raw_candles:
                logger.info(f"No more candles available from {current_from}")
                break

            # Parse candles
            for raw_candle in raw_candles:
                try:
                    candle = self._parse_candle(
                        raw_candle,
                        platform_instrument,
                        platform_timeframe,
                    )
                    all_candles.append(candle)
                except Exception as e:
                    logger.error(f"Failed to parse candle: {e} - {raw_candle}")

            # Update pagination cursor
            last_candle_time = date_parser.isoparse(raw_candles[-1]["time"])
            if last_candle_time >= current_from:
                current_from = last_candle_time + timedelta(seconds=1)
            else:
                # Safety check to prevent infinite loop
                logger.warning("Pagination cursor did not advance. Breaking.")
                break

            logger.info(
                f"Fetched {len(raw_candles)} candles. "
                f"Total: {len(all_candles)}. Last: {last_candle_time}"
            )

            # Rate limiting: small delay between requests
            await asyncio.sleep(0.1)

        logger.info(
            f"Completed fetching {instrument} {granularity}: {len(all_candles)} candles"
        )
        return all_candles

    def _parse_candle(
        self,
        raw_candle: Dict[str, Any],
        instrument: str,
        timeframe: str,
    ) -> Candle:
        """Parse OANDA candle response into Candle object."""
        mid = raw_candle["mid"]
        return Candle(
            time=date_parser.isoparse(raw_candle["time"]),
            instrument=instrument,
            timeframe=timeframe,
            open=Decimal(str(mid["o"])),
            high=Decimal(str(mid["h"])),
            low=Decimal(str(mid["l"])),
            close=Decimal(str(mid["c"])),
            volume=int(raw_candle.get("volume", 0)),
            complete=raw_candle.get("complete", True),
            source="oanda",
        )

    @staticmethod
    def _get_platform_instrument(oanda_instrument: str) -> str:
        """Convert OANDA instrument name to platform name."""
        for platform_name, oanda_name in INSTRUMENT_MAPPING.items():
            if oanda_name == oanda_instrument:
                return platform_name
        return oanda_instrument.replace("_", "")

    @staticmethod
    def _get_platform_timeframe(oanda_granularity: str) -> str:
        """Convert OANDA granularity to platform timeframe."""
        for platform_tf, oanda_tf in TIMEFRAME_MAPPING.items():
            if oanda_tf == oanda_granularity:
                return platform_tf
        return oanda_granularity


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
            WHERE instrument = $1 AND timeframe = $2 AND source = 'oanda'
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
                        None,  # spread (not available in historical data)
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
            # Check if gap occurs on a trading day (skip weekends for Forex)
            # Simplified: flag all gaps > 2x timeframe
            gap_hours = gap_seconds / 3600
            gaps.append((prev_candle.time, curr_candle.time, gap_hours))
            logger.warning(
                f"Gap detected: {prev_candle.instrument} {timeframe} "
                f"{prev_candle.time} → {curr_candle.time} ({gap_hours:.2f} hours)"
            )

    return gaps


# ── MAIN ORCHESTRATION ─────────────────────────────────────────────────────

async def load_instrument_timeframe(
    oanda_client: OANDAHistoricalClient,
    db_loader: TimescaleDBLoader,
    instrument: str,
    timeframe: str,
    resume: bool = False,
) -> LoadSummary:
    """
    Load historical data for a single instrument-timeframe pair.

    Args:
        oanda_client: OANDA API client
        db_loader: Database loader
        instrument: Platform instrument name
        timeframe: Platform timeframe
        resume: If True, resume from last loaded timestamp

    Returns:
        LoadSummary with statistics
    """
    start_time = datetime.now()

    # Map to OANDA names
    oanda_instrument = INSTRUMENT_MAPPING[instrument]
    oanda_granularity = TIMEFRAME_MAPPING[timeframe]

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
    candles = await oanda_client.fetch_all_candles(
        instrument=oanda_instrument,
        granularity=oanda_granularity,
        from_time=from_time,
        to_time=to_time,
    )

    # Sort by time
    candles.sort(key=lambda c: c.time)

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
    api_key = os.getenv("OANDA_API_KEY")
    environment = os.getenv("OANDA_ENVIRONMENT", "practice")
    connection_string = os.getenv("TIMESCALE_URL")

    if not api_key:
        raise ValueError("OANDA_API_KEY environment variable not set")
    if not connection_string:
        raise ValueError("TIMESCALE_URL environment variable not set")

    logger.info("=" * 80)
    logger.info("AgentICTrader Historical Data Loader")
    logger.info("=" * 80)
    logger.info(f"Instruments: {', '.join(instruments)}")
    logger.info(f"Timeframes: {', '.join(timeframes)}")
    logger.info(f"Historical period: {HISTORICAL_YEARS} years")
    logger.info(f"OANDA environment: {environment}")
    logger.info(f"Resume mode: {resume}")
    logger.info("=" * 80)

    summaries: List[LoadSummary] = []

    # Initialize clients
    async with OANDAHistoricalClient(api_key, environment) as oanda_client:
        db_loader = TimescaleDBLoader(connection_string)
        await db_loader.connect()

        try:
            # Load each instrument-timeframe combination
            for instrument in instruments:
                for timeframe in timeframes:
                    try:
                        summary = await load_instrument_timeframe(
                            oanda_client=oanda_client,
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
        description="Load historical OHLCV data from OANDA v20 API"
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
