"""
Tests for the user's markets (algo-research update 2026-10f): the Exness focus instruments, and the charts'
precision and order.

Task 317 (.kiro/specs/algo-research/tasks.md).
Validates: Requirements 22.2, 22.5 (.kiro/specs/algo-research/requirements.md)
"""
from __future__ import annotations

import pandas as pd
import pytest

from agent.broker_profiles import load_profile
from algo_backtester.watch import WatchApp
from algo_research.replay.bars import ReplayBars
from algo_research.replay.charts import ChartsApp
from tests.test_replay import END, FIRST, synthetic_m1

NEW_SYMBOLS = {"DXY": "DXYm", "US100": "USTECm", "US500": "US500m", "US30": "US30m", "GER40": "DE30m",
               "UK100": "UK100m"}
OLD_SYMBOLS = {"EURUSD": "EURUSDm", "GBPUSD": "GBPUSDm", "USDJPY": "USDJPYm", "XAUUSD": "XAUUSDm"}


# ── the Exness focus instruments (22.2) ─────────────────────────────────────

def test_the_exness_profile_maps_the_focus_instruments_and_keeps_the_old_ones():
    profile = load_profile("exness-standard")
    for instrument, symbol in {**NEW_SYMBOLS, **OLD_SYMBOLS}.items():
        assert profile.symbol(instrument) == symbol


def test_the_exness_spec_file_prices_the_focus_instruments_in_their_own_currencies():
    specs = load_profile("exness-standard").specs()
    quote = {"DXY": "USD", "US100": "USD", "US500": "USD", "US30": "USD", "GER40": "EUR", "UK100": "GBP"}
    for instrument, ccy in quote.items():
        spec = specs[instrument]
        assert spec.quote_ccy == ccy, instrument
        assert spec.default_spread > 0 and spec.stop_slippage > 0 and spec.contract_size > 0
        assert spec.commission.value == 0                     # a Standard account charges no commission
    assert set(OLD_SYMBOLS) <= set(specs)


# ── chart precision (22.5) ──────────────────────────────────────────────────

def _bars(prices, instrument="UK100") -> ReplayBars:
    times = pd.date_range("2025-01-08 15:00", periods=len(prices), freq="1min", tz="UTC")
    frame = pd.DataFrame({"time": times, "open": prices, "high": prices, "low": prices, "close": prices})
    return ReplayBars(frame, instrument)


@pytest.mark.parametrize("prices, digits", [
    ([10708.61, 10708.6, 10709.0], 2),                        # UK100
    ([44120.5, 44121.0], 1),                                  # US30
    ([98.123, 98.12], 3),                                     # DXY
    ([1.16512, 1.1651], 5),                                   # EURUSD
    ([108234.0, 108240.0], 0),
    ([1.1 + 0.2, 1.4], 1),                                    # float noise adds no decimals
])
def test_digits_are_the_fewest_decimals_that_write_every_price(prices, digits):
    assert _bars(prices).digits == digits


def test_digits_fall_back_to_the_old_rule_without_a_grid_or_data():
    assert ReplayBars(synthetic_m1(3), "XAUUSD").digits == 3                  # simulated prices: no grid
    assert ReplayBars(synthetic_m1(3), "EURUSD").digits == 5
    assert _bars([], "USDJPY").digits == 3
    assert _bars([], "UK100").digits == 5


# ── chart order (22.5) ──────────────────────────────────────────────────────

def test_the_chart_tabs_follow_the_configured_order(tmp_path):
    snap = tmp_path / "snapshot"
    snap.mkdir()
    for inst in ("XAUUSD", "EURUSD", "UK100", "AUDUSD"):
        synthetic_m1(3).to_parquet(snap / f"{inst}_M1.parquet", index=False)
    config = tmp_path / "base.toml"
    config.write_text("[run]\nprofile = \"exness-standard\"\n", encoding="utf-8")
    watch = WatchApp(config, snap, (FIRST, END), picks=tmp_path / "picks.jsonl")
    charts = ChartsApp(snap, tmp_path / "journal", (FIRST, END), watch, default="XAUUSD",
                       order=("DXY", "XAUUSD", "EURUSD", "UK100"))
    assert charts.instruments == ["XAUUSD", "EURUSD", "UK100", "AUDUSD"]   # DXY has no file; AUDUSD isn't configured
    assert ChartsApp(snap, tmp_path / "journal", (FIRST, END), watch).instruments == sorted(
        ["XAUUSD", "EURUSD", "UK100", "AUDUSD"])                             # no order: sorted, as before
