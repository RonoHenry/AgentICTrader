#!/usr/bin/env python3
"""
Load historical OHLCV data from the local MetaTrader 5 terminal into TimescaleDB.

This is the same feed the live agent trades on (scripts/run_live_agent.py), so
models and backtests see the prices, session boundaries and daily candles the
agent will see live. Reuses the OANDA loader's TimescaleDB writer, OHLC
validation and gap detection — only the fetch differs.

MT5 specifics:
- Bar times are broker server time, not UTC. They are converted with
  MT5_SERVER_TIMEZONE (see services/market_data/mt5_clock.py), and that rule
  is checked against a live tick before anything is written.
- The terminal only serves history within Tools > Options > Charts >
  "Max bars in chart" (default 100000, ~69 days of M1). Set it to Unlimited
  and restart the terminal to get years of M1; the loader warns whenever a
  series starts later than requested.
- Rows are written with source='mt5'. The candles primary key is
  (time, instrument, timeframe), so they replace OANDA/Deriv rows that share
  a timestamp.

Usage:
    python scripts/load_historical_data_mt5.py [--instruments EURUSD,GBPUSD]
        [--timeframes M15,H1] [--years 3] [--resume] [--dry-run]

Environment (.env):
    MT5_LOGIN, MT5_PASSWORD, MT5_SERVER, MT5_PATH, MT5_SYMBOL_SUFFIX
    MT5_SERVER_TIMEZONE: 'ny_close' (default) or a fixed UTC offset like '+2'
    TIMESCALE_URL: PostgreSQL connection string (not needed with --dry-run)
"""
from __future__ import annotations

import os

# Must be set before numpy/MetaTrader5 are imported — see scripts/run_live_agent.py.
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")

import argparse
import asyncio
import logging
import sys
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import List, Optional

from decouple import Config, RepositoryEnv

sys.stdout.reconfigure(encoding="utf-8")

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import MetaTrader5 as mt5

from load_historical_data import (
    TIMEFRAME_DURATIONS,
    Candle,
    LoadSummary,
    TimescaleDBLoader,
    detect_gaps,
    print_summary_report,
)
from services.market_data.mt5_clock import MT5ServerClock, NY_CLOSE

logger = logging.getLogger("load_historical_data_mt5")

config = Config(RepositoryEnv(str(REPO_ROOT / ".env")))

# ── CONFIGURATION ──────────────────────────────────────────────────────────

# What the live runner trades plus the OANDA loader's instruments.
DEFAULT_INSTRUMENTS = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "XAUUSD", "US500", "US30"]

# Platform timeframe → MT5 constant. Covers the OANDA loader's set plus the
# extra timeframes liquidity_engine uses.
TIMEFRAMES = {
    "M1": mt5.TIMEFRAME_M1,
    "M3": mt5.TIMEFRAME_M3,
    "M5": mt5.TIMEFRAME_M5,
    "M15": mt5.TIMEFRAME_M15,
    "H1": mt5.TIMEFRAME_H1,
    "H3": mt5.TIMEFRAME_H3,
    "H4": mt5.TIMEFRAME_H4,
    "H6": mt5.TIMEFRAME_H6,
    "H8": mt5.TIMEFRAME_H8,
    "H12": mt5.TIMEFRAME_H12,
    "D1": mt5.TIMEFRAME_D1,
    "W1": mt5.TIMEFRAME_W1,
}

HISTORICAL_YEARS = 3
# copy_rates_range rejects a request outright ("Invalid params") when it spans
# too many bars, so ranges are fetched in chunks of roughly this many bars.
BARS_PER_CHUNK = 40_000
MAX_CHUNK_DAYS = 180
# Allowed slack between the requested start and the first bar returned
# (weekends/holidays) before warning that the terminal's history is short.
COVERAGE_SLACK = timedelta(days=7)


# ── MT5 FETCH ──────────────────────────────────────────────────────────────

def fetch_mt5_candles(
    symbol: str,
    instrument: str,
    timeframe: str,
    from_time: datetime,
    to_time: datetime,
    clock: MT5ServerClock,
) -> List[Candle]:
    """Fetch [from_time, to_time) (real UTC) from the terminal in chunks."""
    mt5_tf = TIMEFRAMES[timeframe]
    tf_seconds = TIMEFRAME_DURATIONS[timeframe]
    chunk = timedelta(days=min(MAX_CHUNK_DAYS, max(1, BARS_PER_CHUNK * tf_seconds // 86400)))
    now = datetime.now(timezone.utc)

    by_time: dict[datetime, Candle] = {}
    cursor = from_time
    while cursor < to_time:
        chunk_end = min(cursor + chunk, to_time)
        rates = mt5.copy_rates_range(symbol, mt5_tf, clock.to_server(cursor), clock.to_server(chunk_end))
        if rates is None:
            raise RuntimeError(f"copy_rates_range failed for {symbol} {timeframe}: {mt5.last_error()}")

        for r in rates:
            bar_time = clock.to_utc(r["time"])
            # The terminal returns a stray in-window bar for ranges older than
            # its history, and chunk edges overlap — keep only this chunk.
            if not (cursor <= bar_time < chunk_end):
                continue
            by_time[bar_time] = Candle(
                time=bar_time,
                instrument=instrument,
                timeframe=timeframe,
                open=Decimal(str(r["open"])),
                high=Decimal(str(r["high"])),
                low=Decimal(str(r["low"])),
                close=Decimal(str(r["close"])),
                volume=int(r["tick_volume"]),
                complete=bar_time + timedelta(seconds=tf_seconds) <= now,
                source="mt5",
            )
        cursor = chunk_end

    candles = sorted(by_time.values(), key=lambda c: c.time)
    if candles and candles[0].time - from_time > COVERAGE_SLACK:
        logger.warning(
            f"{instrument} {timeframe}: terminal history starts at {candles[0].time:%Y-%m-%d}, "
            f"not {from_time:%Y-%m-%d} — raise 'Max bars in chart' (Tools > Options > Charts) "
            f"to Unlimited and restart MT5 for the full range"
        )
    return candles


# ── MAIN ORCHESTRATION ─────────────────────────────────────────────────────

async def load_instrument_timeframe(
    db_loader: Optional[TimescaleDBLoader],
    clock: MT5ServerClock,
    symbol_suffix: str,
    instrument: str,
    timeframe: str,
    years: float,
    resume: bool,
) -> LoadSummary:
    started = time.monotonic()
    to_time = datetime.now(timezone.utc)
    from_time = to_time - timedelta(days=years * 365)

    if resume and db_loader:
        last_time = await db_loader.get_last_loaded_time(instrument, timeframe, source="mt5")
        if last_time:
            # Re-fetch the last bar too: it may have been stored incomplete.
            from_time = last_time
            logger.info(f"Resuming {instrument} {timeframe} from {from_time}")

    symbol = f"{instrument}{symbol_suffix}"
    if not mt5.symbol_select(symbol, True):
        raise RuntimeError(f"Symbol {symbol} not available in this terminal: {mt5.last_error()}")

    logger.info(f"Fetching {symbol} {timeframe} from {from_time:%Y-%m-%d %H:%M} to {to_time:%Y-%m-%d %H:%M} UTC")
    candles = fetch_mt5_candles(symbol, instrument, timeframe, from_time, to_time, clock)
    gaps = detect_gaps(candles, timeframe)

    if db_loader:
        inserted_count, validation_errors = await db_loader.load_candles(candles)
    else:
        inserted_count = sum(1 for c in candles if c.validate_ohlc())
        validation_errors = len(candles) - inserted_count

    summary = LoadSummary(
        instrument=instrument,
        timeframe=timeframe,
        row_count=inserted_count,
        date_range_start=candles[0].time if candles else None,
        date_range_end=candles[-1].time if candles else None,
        gap_count=len(gaps),
        validation_errors=validation_errors,
        duration_seconds=time.monotonic() - started,
    )
    logger.info(
        f"✓ {instrument} {timeframe}: {inserted_count} candles {'validated' if db_loader is None else 'loaded'}, "
        f"{len(gaps)} gaps, {validation_errors} validation errors"
    )
    return summary


def connect_mt5() -> None:
    init_kwargs = {
        "login": config("MT5_LOGIN", cast=int),
        "password": config("MT5_PASSWORD"),
        "server": config("MT5_SERVER"),
    }
    mt5_path = config("MT5_PATH", default="")
    if mt5_path:
        init_kwargs["path"] = mt5_path
    if not mt5.initialize(**init_kwargs):
        code, desc = mt5.last_error()
        raise RuntimeError(f"MT5 initialize failed ({code}): {desc}")


def verify_server_clock(clock: MT5ServerClock, instruments: List[str], symbol_suffix: str) -> None:
    """Fail fast if MT5_SERVER_TIMEZONE doesn't match the terminal's clock —
    otherwise every row written would be shifted by the difference."""
    tick_times = []
    for instrument in instruments:
        symbol = f"{instrument}{symbol_suffix}"
        mt5.symbol_select(symbol, True)
        tick = mt5.symbol_info_tick(symbol)
        if tick is not None and tick.time:
            tick_times.append(tick.time)

    now = datetime.now(timezone.utc)
    measured = clock.check(tick_times, now)
    if measured is None:
        logger.warning(
            f"No fresh tick to verify the server clock against (market closed?) — trusting "
            f"MT5_SERVER_TIMEZONE={clock.spec!r} (UTC{clock.utc_offset_at(now).total_seconds() / 3600:+g} now)"
        )
    else:
        logger.info(f"MT5 server clock verified: UTC{measured.total_seconds() / 3600:+g} ({clock.spec})")


async def load_all_data(
    instruments: List[str],
    timeframes: List[str],
    years: float,
    resume: bool,
    dry_run: bool,
) -> List[LoadSummary]:
    symbol_suffix = config("MT5_SYMBOL_SUFFIX", default="")
    clock = MT5ServerClock(config("MT5_SERVER_TIMEZONE", default=NY_CLOSE))

    logger.info("=" * 80)
    logger.info("AgentICTrader Historical Data Loader — MetaTrader 5")
    logger.info("=" * 80)
    logger.info(f"Instruments: {', '.join(instruments)}")
    logger.info(f"Timeframes: {', '.join(timeframes)}")
    logger.info(f"Historical period: {years} years")
    logger.info(f"Resume mode: {resume}   Dry run: {dry_run}")
    logger.info("=" * 80)

    connect_mt5()
    db_loader: Optional[TimescaleDBLoader] = None
    summaries: List[LoadSummary] = []
    try:
        account = mt5.account_info()
        logger.info(f"Connected to MT5 server {account.server if account else '?'}")
        verify_server_clock(clock, instruments, symbol_suffix)

        if not dry_run:
            connection_string = config("TIMESCALE_URL", default="")
            if not connection_string:
                raise ValueError("TIMESCALE_URL not set (use --dry-run to fetch without writing)")
            db_loader = TimescaleDBLoader(connection_string)
            await db_loader.connect()

        for instrument in instruments:
            for timeframe in timeframes:
                try:
                    summaries.append(
                        await load_instrument_timeframe(
                            db_loader, clock, symbol_suffix, instrument, timeframe, years, resume
                        )
                    )
                except Exception as e:
                    logger.error(f"Failed to load {instrument} {timeframe}: {e}")
                    summaries.append(LoadSummary(instrument, timeframe, 0, None, None, 0, 0, 0))
    finally:
        if db_loader:
            await db_loader.close()
        mt5.shutdown()

    return summaries


# ── CLI ENTRY POINT ────────────────────────────────────────────────────────

def _csv(value: str) -> List[str]:
    return [v.strip().upper() for v in value.split(",") if v.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(description="Load historical OHLCV data from the local MT5 terminal")
    parser.add_argument("--instruments", type=_csv, default=DEFAULT_INSTRUMENTS,
                        help=f"Comma-separated instruments (default: {','.join(DEFAULT_INSTRUMENTS)})")
    parser.add_argument("--timeframes", type=_csv, default=list(TIMEFRAMES),
                        help=f"Comma-separated timeframes (default: {','.join(TIMEFRAMES)})")
    parser.add_argument("--years", type=float, default=HISTORICAL_YEARS,
                        help=f"Years of history to load (default: {HISTORICAL_YEARS})")
    parser.add_argument("--resume", action="store_true", help="Resume from the last loaded MT5 timestamp")
    parser.add_argument("--dry-run", action="store_true", help="Fetch and validate without writing to TimescaleDB")
    args = parser.parse_args()

    invalid = [t for t in args.timeframes if t not in TIMEFRAMES]
    if invalid:
        logger.error(f"Invalid timeframes: {invalid}. Valid: {list(TIMEFRAMES)}")
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
