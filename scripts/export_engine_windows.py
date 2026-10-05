#!/usr/bin/env python3
"""Capture engine benchmark windows and today's analyze() output as test fixtures.

Task 214 (.kiro/specs/algo-backtester/tasks.md). Freezes the exact windows the
live runner analyses (_CANDLE_COUNT per timeframe) together with the
LiquidityMap the engine produces for them. backend/tests/test_liquidity_engine_perf.py
then asserts that performance work leaves that output byte-identical.

Run this BEFORE changing engine code: the captured output is the reference.

Sources:
  BTCUSDT  M5, M15  Binance public klines (no key)
  EURUSD   M5, M15  MT5 via a broker profile (default exness-standard), read-only

Usage:
    python scripts/export_engine_windows.py [--profile exness-standard] [--out DIR]
"""
from __future__ import annotations

import os

os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")

import argparse
import gzip
import json
import sys
from pathlib import Path
from typing import Callable

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agent import broker_profiles  # noqa: E402
from liquidity_engine import LiquidityMappingEngine  # noqa: E402
from liquidity_engine.models import Candle, Timeframe  # noqa: E402
from services.market_data.binance import BinanceKlineClient  # noqa: E402

DEFAULT_OUT = REPO_ROOT / "backend" / "tests" / "fixtures" / "backtester" / "engine_windows"

# The live runner's window: D1, W1, the HTF context stack, and the entry timeframe.
CONTEXT_TIMEFRAMES = (Timeframe.H12, Timeframe.H8, Timeframe.H6, Timeframe.H4, Timeframe.H3)
CANDLE_COUNT = {
    Timeframe.M5: 300, Timeframe.M15: 200,
    Timeframe.H3: 150, Timeframe.H4: 150, Timeframe.H6: 120, Timeframe.H8: 100, Timeframe.H12: 90,
    Timeframe.D1: 90, Timeframe.W1: 30,
}
WINDOWS = [("BTCUSDT", Timeframe.M5), ("BTCUSDT", Timeframe.M15), ("EURUSD", Timeframe.M15), ("EURUSD", Timeframe.M5)]


def window(fetch: Callable[[Timeframe], list[Candle]], entry_tf: Timeframe) -> dict[Timeframe, list[Candle]]:
    return {
        Timeframe.D1: fetch(Timeframe.D1),
        Timeframe.W1: fetch(Timeframe.W1),
        **{tf: fetch(tf) for tf in CONTEXT_TIMEFRAMES},
        entry_tf: fetch(entry_tf),
    }


def binance_fetcher(client: BinanceKlineClient, instrument: str) -> Callable[[Timeframe], list[Candle]]:
    def fetch(tf: Timeframe) -> list[Candle]:
        return [
            Candle(timestamp=k.open_time, open=float(k.open), high=float(k.high), low=float(k.low),
                   close=float(k.close), volume=k.trades, timeframe=tf, instrument=instrument)
            for k in client.latest(instrument, tf.value, CANDLE_COUNT[tf])
        ]
    return fetch


def mt5_fetcher(mt5, profile, instrument: str) -> Callable[[Timeframe], list[Candle]]:
    tf_const = {tf: getattr(mt5, f"TIMEFRAME_{tf.value}") for tf in CANDLE_COUNT}
    clock, symbol = profile.clock(), profile.symbol(instrument)
    mt5.symbol_select(symbol, True)

    def fetch(tf: Timeframe) -> list[Candle]:
        rates = mt5.copy_rates_from_pos(symbol, tf_const[tf], 0, CANDLE_COUNT[tf])
        if rates is None or len(rates) == 0:
            raise RuntimeError(f"No {tf.value} bars for {symbol}: {mt5.last_error()}")
        return [
            Candle(timestamp=clock.to_utc(int(r["time"])), open=float(r["open"]), high=float(r["high"]),
                   low=float(r["low"]), close=float(r["close"]), volume=int(r["tick_volume"]),
                   timeframe=tf, instrument=instrument)
            for r in rates
        ]
    return fetch


def capture(candles_by_tf: dict[Timeframe, list[Candle]], instrument: str, entry_tf: Timeframe, source: str) -> dict:
    t = candles_by_tf[entry_tf][-1].timestamp
    engine = LiquidityMappingEngine()
    expected = engine.analyze(candles_by_tf, instrument, t).model_dump_json()
    if engine.analyze(candles_by_tf, instrument, t).model_dump_json() != expected:
        raise RuntimeError(f"{instrument} {entry_tf.value}: analyze() is not deterministic on this window")
    return {
        "instrument": instrument,
        "entry_tf": entry_tf.value,
        "timestamp": t.isoformat(),
        "source": source,
        "candles": {
            tf.value: [[c.timestamp.isoformat(), c.open, c.high, c.low, c.close, c.volume] for c in candles]
            for tf, candles in candles_by_tf.items()
        },
        "expected_json": expected,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--profile", default="exness-standard", help="MT5 broker profile for EURUSD")
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    client = BinanceKlineClient()
    profile = broker_profiles.load_profile(args.profile)
    mt5 = broker_profiles.connect_mt5(profile)
    try:
        for instrument, entry_tf in WINDOWS:
            if instrument == "BTCUSDT":
                fetch, source = binance_fetcher(client, instrument), "binance"
            else:
                fetch, source = mt5_fetcher(mt5, profile, instrument), f"mt5:{profile.name}"
            record = capture(window(fetch, entry_tf), instrument, entry_tf, source)
            path = out / f"{instrument}_{entry_tf.value}.json.gz"
            with gzip.open(path, "wt", encoding="utf-8") as fh:
                json.dump(record, fh, separators=(",", ":"))
            pd_arrays = len(json.loads(record["expected_json"])["pd_arrays"])
            print(f"{path.name}: {sum(len(v) for v in record['candles'].values())} candles, "
                  f"{pd_arrays} PD arrays, {path.stat().st_size // 1024} KiB")
    finally:
        mt5.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
