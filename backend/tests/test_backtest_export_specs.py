"""
Tests for scripts/export_instrument_specs.py — venue specs → config/instruments/<venue>.toml.

Task 183 (.kiro/specs/algo-backtester/tasks.md). No terminal or network:
the MT5 module and the Binance exchange-info payload are faked.
Validates: Requirements 5.1, 5.2
"""
from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from agent.instruments import load_specs
from scripts.export_instrument_specs import (
    binance_specs,
    commission_per_lot_per_side,
    main,
    mt5_specs,
)

DEAL_BUY, DEAL_SELL, DEAL_BALANCE = 0, 1, 2


def _deal(symbol, volume, commission, fee=0.0, type_=DEAL_BUY):
    return SimpleNamespace(symbol=symbol, volume=volume, commission=commission, fee=fee, type=type_)


def _symbol_info(**overrides):
    info = dict(
        point=0.00001,
        trade_tick_size=0.00001,
        trade_tick_value=1.0,          # USD per tick per lot for EURUSD on a USD account
        trade_contract_size=100_000.0,
        volume_min=0.01,
        volume_step=0.01,
        volume_max=100.0,
        currency_base="EUR",
        currency_profit="USD",
        bid=1.0850,
    )
    info.update(overrides)
    return SimpleNamespace(**info)


class FakeMT5:
    DEAL_TYPE_BUY = DEAL_BUY
    DEAL_TYPE_SELL = DEAL_SELL

    COPY_TICKS_INFO = 2

    def __init__(self, infos, deals, spreads_points, account_ccy="USD"):
        self._infos = infos
        self._deals = deals
        self._spreads = spreads_points
        self._account_ccy = account_ccy

    def symbol_select(self, symbol, enable):
        return symbol in self._infos

    def symbol_info(self, symbol):
        return self._infos.get(symbol)

    def symbol_info_tick(self, symbol):
        info = self._infos[symbol]
        return SimpleNamespace(bid=info.bid, ask=info.bid)

    def account_info(self):
        return SimpleNamespace(currency=self._account_ccy, company="Test Broker Ltd", server="TestBroker-Demo")

    def history_deals_get(self, date_from, date_to):
        return tuple(self._deals)

    def copy_ticks_range(self, symbol, date_from, date_to, flags):
        point = self._infos[symbol].point
        spreads = self._spreads[symbol]
        ticks = np.zeros(len(spreads), dtype=[("bid", "f8"), ("ask", "f8")])
        ticks["bid"] = 1.0
        ticks["ask"] = 1.0 + np.asarray(spreads, dtype=float) * point
        return ticks


# ── commission from deal history ───────────────────────────────────────────

def test_commission_per_side_when_split_across_deals():
    # $3.50 per lot charged on the entry deal and again on the exit deal.
    deals = [_deal("EURUSD", 1.0, -3.5), _deal("EURUSD", 1.0, -3.5, type_=DEAL_SELL)]
    assert commission_per_lot_per_side(deals, "EURUSD", FakeMT5) == pytest.approx(3.5)


def test_commission_per_side_when_charged_at_entry_only():
    # $7 round trip charged entirely on the entry deal; the exit deal shows 0.
    deals = [_deal("EURUSD", 2.0, -14.0), _deal("EURUSD", 2.0, 0.0, type_=DEAL_SELL)]
    assert commission_per_lot_per_side(deals, "EURUSD", FakeMT5) == pytest.approx(3.5)


def test_commission_counts_fee_field_and_ignores_other_symbols_and_non_trade_deals():
    deals = [
        _deal("EURUSD", 1.0, -2.5, fee=-1.0),
        _deal("EURUSD", 1.0, -2.5, fee=-1.0, type_=DEAL_SELL),
        _deal("GBPUSD", 5.0, -50.0),
        _deal("", 0.0, -100.0, type_=DEAL_BALANCE),
    ]
    assert commission_per_lot_per_side(deals, "EURUSD", FakeMT5) == pytest.approx(3.5)


def test_commission_none_without_deals_for_symbol():
    assert commission_per_lot_per_side([_deal("GBPUSD", 1.0, -3.5)], "EURUSD", FakeMT5) is None


# ── MT5 specs ──────────────────────────────────────────────────────────────

def _fake_eurusd(**info_overrides):
    return FakeMT5(
        infos={"EURUSD": _symbol_info(**info_overrides)},
        deals=[_deal("EURUSD", 1.0, -3.5), _deal("EURUSD", 1.0, -3.5, type_=DEAL_SELL)],
        spreads_points={"EURUSD": [10, 12, 14, 12, 200]},  # one news spike; median ignores it
    )


def test_maps_symbol_info_fields():
    specs, problems = mt5_specs(_fake_eurusd(), ["EURUSD"])
    assert problems == []
    spec = specs["EURUSD"]
    assert spec.venue == "mt5"
    assert spec.point == 0.00001 and spec.tick_size == 0.00001
    assert spec.contract_size == 100_000.0
    assert (spec.volume_min, spec.volume_step, spec.volume_max) == (0.01, 0.01, 100.0)
    assert (spec.base_ccy, spec.quote_ccy) == ("EUR", "USD")
    assert spec.commission.kind == "PER_LOT_PER_SIDE"
    assert spec.commission.value == pytest.approx(3.5)
    assert specs.account_ccy == "USD"


def test_default_spread_from_recent_ticks_median():
    specs, _ = mt5_specs(_fake_eurusd(), ["EURUSD"])
    # Exact, not approx: ask - bid arithmetic leaves float noise (8.000000000008e-05),
    # and the spec file is read by people. Rounded to a tenth of a point.
    assert specs["EURUSD"].default_spread == 0.00012


def test_zero_spread_is_a_problem_unless_overridden():
    # A zero spread is never a real cost; MetaQuotes-Demo records exactly that for EURUSD.
    fake = FakeMT5(
        infos={"EURUSD": _symbol_info()},
        deals=[_deal("EURUSD", 1.0, -3.5), _deal("EURUSD", 1.0, -3.5, type_=DEAL_SELL)],
        spreads_points={"EURUSD": [0, 0, 0, 1]},
    )
    _, problems = mt5_specs(fake, ["EURUSD"])
    assert any("EURUSD" in p and "spread" in p for p in problems)

    specs, problems = mt5_specs(fake, ["EURUSD"], spread_overrides={"EURUSD": 8})
    assert problems == []
    assert specs["EURUSD"].default_spread == pytest.approx(8 * 0.00001)


@pytest.mark.parametrize(
    "symbol, info_overrides, spread_points, expected",
    [
        # EURUSD at 0.8 pip typical spread: 25% = 0.2 pip.
        ("EURUSD", {}, 8, 0.00002),
        # XAUUSD at $0.24 (240 points of 0.001): 25% = $0.06. A fixed 2 points would be $0.002.
        ("XAUUSD", dict(point=0.001, trade_tick_size=0.001, trade_tick_value=0.1, trade_contract_size=100.0,
                        currency_base="XAU", currency_profit="USD", bid=2400.0), 240, 0.06),
        # A 1-point spread: 25% is 0.25 point, so the 2-point minimum applies.
        ("EURUSD", {}, 1, 0.00002),
    ],
)
def test_stop_slippage_is_quarter_of_typical_spread_with_two_point_minimum(
    symbol, info_overrides, spread_points, expected
):
    # D3 (amended): stop slippage scales with the instrument's typical spread.
    fake = FakeMT5(
        infos={symbol: _symbol_info(**info_overrides)},
        deals=[_deal(symbol, 1.0, -3.5), _deal(symbol, 1.0, -3.5, type_=DEAL_SELL)],
        spreads_points={symbol: [spread_points]},
    )
    specs, problems = mt5_specs(fake, [symbol])
    assert problems == []
    assert specs[symbol].stop_slippage == expected


def test_symbol_suffix_resolved_but_key_is_instrument():
    fake = FakeMT5(
        infos={"EURUSD.a": _symbol_info()},
        deals=[_deal("EURUSD.a", 1.0, -3.5), _deal("EURUSD.a", 1.0, -3.5, type_=DEAL_SELL)],
        spreads_points={"EURUSD.a": [12]},
    )
    specs, problems = mt5_specs(fake, ["EURUSD"], symbol_suffix=".a")
    assert problems == []
    assert list(specs) == ["EURUSD"]


def test_no_deals_for_symbol_is_a_problem_unless_overridden():
    fake = FakeMT5(infos={"EURUSD": _symbol_info()}, deals=[], spreads_points={"EURUSD": [12]})

    _, problems = mt5_specs(fake, ["EURUSD"])
    assert any("EURUSD" in p and "commission" in p for p in problems)

    specs, problems = mt5_specs(fake, ["EURUSD"], commission_overrides={"EURUSD": 3.0})
    assert problems == []
    assert specs["EURUSD"].commission.value == 3.0


def test_unknown_symbol_is_a_problem():
    _, problems = mt5_specs(_fake_eurusd(), ["EURUSD", "GBPUSD"])
    assert any("GBPUSD" in p for p in problems)


def test_tick_value_cross_check_flags_mismatch():
    # The broker says a tick is worth $1.30, but EURUSD on a USD account must be $1.00.
    # A disagreement means our currency conversion would be wrong for this symbol.
    _, problems = mt5_specs(_fake_eurusd(trade_tick_value=1.30), ["EURUSD"])
    assert any("EURUSD" in p and "tick value" in p for p in problems)


def test_tick_value_cross_check_passes_for_usd_base_pair():
    fake = FakeMT5(
        infos={"USDJPY": _symbol_info(
            point=0.001, trade_tick_size=0.001, trade_tick_value=100_000 * 0.001 / 150.0,
            currency_base="USD", currency_profit="JPY", bid=150.0,
        )},
        deals=[_deal("USDJPY", 1.0, -3.5), _deal("USDJPY", 1.0, -3.5, type_=DEAL_SELL)],
        spreads_points={"USDJPY": [15]},
    )
    _, problems = mt5_specs(fake, ["USDJPY"])
    assert problems == []


# ── Binance specs ──────────────────────────────────────────────────────────

_BINANCE_EXCHANGE_INFO = {
    "symbols": [
        {
            "symbol": "BTCUSDT",
            "baseAsset": "BTC",
            "quoteAsset": "USDT",
            "filters": [
                {"filterType": "PRICE_FILTER", "tickSize": "0.01000000"},
                {"filterType": "LOT_SIZE", "minQty": "0.00001000", "maxQty": "9000.00000000",
                 "stepSize": "0.00001000"},
            ],
        }
    ]
}


def test_binance_specs_from_exchange_info():
    specs, problems = binance_specs(_BINANCE_EXCHANGE_INFO, ["BTCUSDT"], prices={"BTCUSDT": 60_000.0})
    assert problems == []
    spec = specs["BTCUSDT"]
    assert specs.venue == "binance" and specs.account_ccy == "USDT"
    assert spec.tick_size == 0.01 and spec.point == 0.01
    assert (spec.volume_min, spec.volume_step, spec.volume_max) == (0.00001, 0.00001, 9000.0)
    assert spec.contract_size == 1.0
    assert (spec.commission.kind, spec.commission.value) == ("RATE_PER_SIDE", 0.001)
    assert spec.default_spread == 0.01                  # one tick
    assert spec.stop_slippage == pytest.approx(30.0)    # D3: 0.05% of the export-time price


def test_binance_unknown_symbol_is_a_problem():
    _, problems = binance_specs(_BINANCE_EXCHANGE_INFO, ["BTCUSDT", "NOPEUSDT"], prices={"BTCUSDT": 60_000.0})
    assert any("NOPEUSDT" in p for p in problems)


# ── CLI ────────────────────────────────────────────────────────────────────

def test_main_writes_loadable_file(tmp_path, monkeypatch):
    out = tmp_path / "mt5.toml"
    monkeypatch.setattr("scripts.export_instrument_specs._connect_mt5", lambda: (_fake_eurusd(), ""))
    assert main(["--venue", "mt5", "--instruments", "EURUSD", "--out", str(out)]) == 0
    assert load_specs(out)["EURUSD"].commission.value == pytest.approx(3.5)
    # Provenance: which broker and server the costs came from.
    assert "Test Broker Ltd / TestBroker-Demo" in out.read_text(encoding="utf-8")


def test_main_refuses_to_write_when_problems(tmp_path, monkeypatch, capsys):
    out = tmp_path / "mt5.toml"
    fake = FakeMT5(infos={"EURUSD": _symbol_info()}, deals=[], spreads_points={"EURUSD": [12]})
    monkeypatch.setattr("scripts.export_instrument_specs._connect_mt5", lambda: (fake, ""))
    assert main(["--venue", "mt5", "--instruments", "EURUSD", "--out", str(out)]) != 0
    assert not out.exists()
    assert "commission" in capsys.readouterr().err
