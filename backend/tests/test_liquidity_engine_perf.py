"""
Performance work on LiquidityMappingEngine must not change its output.

Task 214 (.kiro/specs/algo-backtester/tasks.md). The fixtures were captured
from the engine *before* optimisation by scripts/export_engine_windows.py:
real live-runner windows (Binance BTCUSDT, MT5 EURUSD) plus the exact
LiquidityMap JSON the engine produced for each.
Validates: Requirements 1.1, 7.5
"""
from __future__ import annotations

import gzip
import json
from datetime import datetime
from pathlib import Path

import pytest

import liquidity_engine.detectors.internal as internal
import liquidity_engine.ipda.classifier as classifier
from liquidity_engine import LiquidityMappingEngine
from liquidity_engine.models import Candle, Timeframe
from liquidity_engine.utils.candle_utils import atr_series, calculate_atr

FIXTURES = Path(__file__).parent / "fixtures" / "backtester" / "engine_windows"
WINDOW_FILES = sorted(FIXTURES.glob("*.json.gz"))


def _load(path: Path):
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        record = json.load(fh)
    instrument = record["instrument"]
    candles_by_tf = {
        Timeframe(tf): [
            Candle(timestamp=datetime.fromisoformat(ts), open=o, high=h, low=lo, close=c, volume=v,
                   timeframe=Timeframe(tf), instrument=instrument)
            for ts, o, h, lo, c, v in rows
        ]
        for tf, rows in record["candles"].items()
    }
    return record, candles_by_tf, datetime.fromisoformat(record["timestamp"])


def test_fixture_windows_present():
    assert {p.name for p in WINDOW_FILES} == {
        "BTCUSDT_M5.json.gz", "BTCUSDT_M15.json.gz", "EURUSD_M15.json.gz", "EURUSD_M5.json.gz",
    }


@pytest.mark.parametrize("path", WINDOW_FILES, ids=lambda p: p.name.split(".")[0])
def test_engine_output_unchanged_on_fixture_windows(path):
    record, candles_by_tf, t = _load(path)
    result = LiquidityMappingEngine().analyze(candles_by_tf, record["instrument"], t)
    # Byte-identical, including list order: not "close enough".
    assert result.model_dump_json() == record["expected_json"]


@pytest.mark.parametrize("path", WINDOW_FILES, ids=lambda p: p.name.split(".")[0])
def test_atr_series_matches_per_candle_calculate_atr(path):
    _, candles_by_tf, _ = _load(path)
    for tf, candles in candles_by_tf.items():
        series = atr_series(candles)
        assert len(series) == len(candles)
        for i in range(2, len(candles)):
            # Exact equality: same values summed in the same order as the original.
            assert series[i] == calculate_atr(candles[:i], period=min(14, i)), (tf, i)


def test_calculate_atr_not_called_per_candle(monkeypatch):
    # A call-count spy: a deterministic stand-in for timing assertions, which flake.
    # Before task 214, PDArrayDetector called calculate_atr once per candle on
    # an ever-growing prefix (~1,000 calls, quadratic). What legitimately
    # remains is the CRT classifier's _range_stats: at most one call per phase
    # check (C4, C3, C2, C1) per timeframe, each on a fixed-size lookback
    # window, so constant cost per timeframe.
    calls = []

    def counting(candles, period=14):
        calls.append(len(candles))
        return calculate_atr(candles, period)

    monkeypatch.setattr(internal, "calculate_atr", counting, raising=False)
    monkeypatch.setattr(classifier, "calculate_atr", counting, raising=False)

    record, candles_by_tf, t = _load(FIXTURES / "BTCUSDT_M5.json.gz")
    LiquidityMappingEngine().analyze(candles_by_tf, record["instrument"], t)

    assert len(calls) <= 4 * len(candles_by_tf), f"{len(calls)} calculate_atr calls for {len(candles_by_tf)} timeframes"
    assert max(calls) <= classifier._C1_LOOKBACK, f"calculate_atr called on a {max(calls)}-candle window"
