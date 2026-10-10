#!/usr/bin/env python3
"""Export real venue bars for the aggregation-parity test.

Task 186 (.kiro/specs/algo-backtester/tasks.md). The backtester builds every
higher timeframe from finer bars on the New York-close strategy calendar
(services/market_data/strategy_calendar.py). These fixtures hold a venue's own
native bars next to the finer bars they are built from, so
backend/tests/test_backtest_aggregation_parity.py can check the calendar
against the venue: wherever StrategyCalendar.matches_native() says they line
up, the aggregated bars must equal the native ones to within one tick.

One file per (profile, instrument, base timeframe):
  M1 base: one strategy-calendar week of M1, plus native H1/H4/D1/W1.
  H1 base (--h1-weeks N): N weeks of H1, plus native H4/D1/W1. M1 history in
           an MT5 terminal is short (about 69 days by default); H1 goes back
           years, so this covers both US DST changes. It is also what the live
           runner aggregates from (design L3).

Sources: an MT5 broker profile (read-only; --attach uses the account the
terminal is already logged into) or the binance profile (public klines).

Usage:
    python scripts/export_aggregation_fixture.py --profile metaquotes-demo --attach --instruments EURUSD,XAUUSD --h1-weeks 52
    python scripts/export_aggregation_fixture.py --profile exness-standard --instruments EURUSD,XAUUSD
    python scripts/export_aggregation_fixture.py --profile binance --instruments BTCUSDT
Options: --week-of YYYY-MM-DD (default: the last complete week), --out DIR
"""
from __future__ import annotations

import os

os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")

import argparse
import gzip
import json
import sys
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Callable, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
for path in (REPO_ROOT, REPO_ROOT / "scripts"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from agent import broker_profiles  # noqa: E402
from liquidity_engine.models import Timeframe  # noqa: E402
from services.market_data.binance import BinanceKlineClient  # noqa: E402
from services.market_data.strategy_calendar import StrategyCalendar  # noqa: E402

DEFAULT_OUT = REPO_ROOT / "backend" / "tests" / "fixtures" / "backtester" / "aggregation"
NATIVE = {
    Timeframe.M1: (Timeframe.H1, Timeframe.H4, Timeframe.D1, Timeframe.W1),
    Timeframe.H1: (Timeframe.H4, Timeframe.D1, Timeframe.W1),
}
# The base series must reach within this of both ends of the window (the FX
# week opens a day after the calendar week starts; holidays add a little).
COVERAGE_SLACK = timedelta(days=3)

Row = list  # [iso timestamp, open, high, low, close, volume]
Fetch = Callable[[Timeframe, datetime, datetime], list[Row]]

CALENDAR = StrategyCalendar()


def last_complete_week(now: datetime) -> tuple[datetime, datetime]:
    end = CALENDAR.period_start(now, Timeframe.W1)
    return CALENDAR.period_start(end - timedelta(minutes=1), Timeframe.W1), end


def week_containing(day: date) -> tuple[datetime, datetime]:
    noon = datetime.combine(day, time(12), tzinfo=timezone.utc)
    return CALENDAR.period_start(noon, Timeframe.W1), CALENDAR.period_end(noon, Timeframe.W1)


def mt5_fetcher(profile: broker_profiles.BrokerProfile, instrument: str) -> Fetch:
    # The history loader's own fetch, so the fixture also covers its server-clock conversion.
    import load_historical_data_mt5 as loader

    symbol, clock = profile.symbol(instrument), profile.clock()

    def fetch(tf: Timeframe, start: datetime, end: datetime) -> list[Row]:
        return [
            [c.time.isoformat(), float(c.open), float(c.high), float(c.low), float(c.close), c.volume]
            for c in loader.fetch_mt5_candles(symbol, instrument, tf.value, start, end, clock)
        ]

    return fetch


def binance_fetcher(client: BinanceKlineClient, instrument: str) -> Fetch:
    def fetch(tf: Timeframe, start: datetime, end: datetime) -> list[Row]:
        return [
            [k.open_time.isoformat(), float(k.open), float(k.high), float(k.low), float(k.close), k.trades]
            for page in client.iter_range(instrument, tf.value, start, end)
            for k in page
        ]

    return fetch


def capture(fetch: Fetch, base: Timeframe, start: datetime, end: datetime) -> dict[str, list[Row]]:
    bars = {tf.value: fetch(tf, start, end) for tf in (base, *NATIVE[base])}
    problems = [f"no {tf} bars" for tf, rows in bars.items() if not rows]
    rows = bars[base.value]
    if rows:
        first, last = datetime.fromisoformat(rows[0][0]), datetime.fromisoformat(rows[-1][0])
        if first - start > COVERAGE_SLACK or end - last > COVERAGE_SLACK:
            problems.append(f"{base.value} covers {first} .. {last}, not {start} .. {end} (history too short?)")
    if problems:
        raise RuntimeError("; ".join(problems))
    return bars


def write(out: Path, record: dict) -> Path:
    start = datetime.fromisoformat(record["start"])
    path = out / f"{record['profile']}_{record['instrument']}_{record['base_tf']}_{start:%Y%m%d}.json.gz"
    with gzip.open(path, "wt", encoding="utf-8") as fh:
        json.dump(record, fh, separators=(",", ":"))
    counts = ", ".join(f"{tf} {len(rows)}" for tf, rows in record["bars"].items())
    print(f"{path.name}: {counts}; {path.stat().st_size // 1024} KiB")
    return path


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--profile", required=True, help="broker profile (config/brokers/<name>.toml)")
    parser.add_argument("--attach", action="store_true",
                        help="MT5: use the account the terminal is logged into instead of logging in")
    parser.add_argument("--instruments", required=True, help="comma-separated, e.g. EURUSD,XAUUSD")
    parser.add_argument("--week-of", type=date.fromisoformat, help="a date in the week to export (default: last complete week)")
    parser.add_argument("--h1-weeks", type=int, default=0, help="also export this many weeks of H1, ending with that week")
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args(argv)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    profile = broker_profiles.load_profile(args.profile)
    instruments = [s.strip().upper() for s in args.instruments.split(",") if s.strip()]
    now = datetime.now(timezone.utc)
    start, end = week_containing(args.week_of) if args.week_of else last_complete_week(now)
    if end > now:
        raise SystemExit(f"The week {start} .. {end} isn't complete yet")
    windows = [(Timeframe.M1, start, end)]
    if args.h1_weeks:
        h1_start = start
        for _ in range(args.h1_weeks - 1):
            h1_start = CALENDAR.period_start(h1_start - timedelta(minutes=1), Timeframe.W1)
        windows.append((Timeframe.H1, h1_start, end))

    source = {"profile": profile.name, "venue": profile.venue, "server_clock": profile.server_clock}
    mt5 = None
    if profile.venue == "mt5":
        mt5 = broker_profiles.connect_mt5(profile, attach=args.attach)
        # Fixture times are only as good as the clock: require a measured one.
        ticks = []
        for instrument in instruments:
            mt5.symbol_select(profile.symbol(instrument), True)
            tick = mt5.symbol_info_tick(profile.symbol(instrument))
            if tick is not None and tick.time:
                ticks.append(tick.time)
        measured = profile.clock().check(ticks, now)
        if measured is None:
            mt5.shutdown()
            raise SystemExit("No fresh tick to verify the server clock against (market closed?); not exporting")
        source["server"] = mt5.account_info().server
        source["measured_utc_offset_hours"] = measured.total_seconds() / 3600
    else:
        source["server"] = "binance"
        client = BinanceKlineClient()

    try:
        for instrument in instruments:
            if mt5 is not None:
                fetch = mt5_fetcher(profile, instrument)
                info = mt5.symbol_info(profile.symbol(instrument))
                tick_size = info.trade_tick_size
            else:
                fetch = binance_fetcher(client, instrument)
                tick_size = profile.specs()[instrument].tick_size
            for base, window_start, window_end in windows:
                bars = capture(fetch, base, window_start, window_end)
                write(out, {
                    **source,
                    "instrument": instrument,
                    "symbol": profile.symbol(instrument),
                    "tick_size": tick_size,
                    "base_tf": base.value,
                    "start": window_start.isoformat(),
                    "end": window_end.isoformat(),
                    "exported_at": now.isoformat(timespec="seconds"),
                    "bars": bars,
                })
    finally:
        if mt5 is not None:
            mt5.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
