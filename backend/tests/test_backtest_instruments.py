"""
Tests for agent/instruments.py — instrument specs, money conversion, spec files.

Task 182 (.kiro/specs/algo-backtester/tasks.md).
Validates: Requirements 5.2, 6.1 (.kiro/specs/algo-backtester/requirements.md)
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from agent.instruments import (
    NO_SWAP,
    SwapSpec,
    swap_per_lot_per_night,
    CommissionSpec,
    InstrumentSpec,
    InstrumentSpecs,
    UnknownInstrumentError,
    commission_per_side,
    dumps_specs,
    load_specs,
    money_per_price_unit,
)


def _spec(symbol: str, base: str, quote: str, **overrides) -> InstrumentSpec:
    fields = dict(
        symbol=symbol,
        venue="mt5",
        point=0.00001,
        tick_size=0.00001,
        contract_size=100_000.0,
        volume_min=0.01,
        volume_step=0.01,
        volume_max=100.0,
        base_ccy=base,
        quote_ccy=quote,
        default_spread=0.00012,
        stop_slippage=0.00002,
        commission=CommissionSpec(kind="PER_LOT_PER_SIDE", value=3.5),
    )
    fields.update(overrides)
    return InstrumentSpec(**fields)


EURUSD = _spec("EURUSD", "EUR", "USD")
USDJPY = _spec("USDJPY", "USD", "JPY", point=0.001, tick_size=0.001, default_spread=0.012, stop_slippage=0.002)
EURGBP = _spec("EURGBP", "EUR", "GBP")
BTCUSDT = _spec(
    "BTCUSDT", "BTC", "USDT",
    venue="binance", point=0.01, tick_size=0.01, contract_size=1.0,
    volume_min=0.00001, volume_step=0.00001, volume_max=9000.0,
    default_spread=0.01, stop_slippage=0.0005,
    commission=CommissionSpec(kind="RATE_PER_SIDE", value=0.001),
)


# ── money per one-unit price move, per lot ─────────────────────────────────

def test_money_per_price_unit_usd_quote():
    # Quote currency is the account currency: 1.0 price unit on 1 lot = contract size.
    assert money_per_price_unit(EURUSD, price=1.0850) == pytest.approx(100_000.0)


def test_money_per_price_unit_usd_base():
    # Base currency is the account currency: convert quote (JPY) at the pair's own price.
    assert money_per_price_unit(USDJPY, price=150.0) == pytest.approx(100_000.0 / 150.0)


def test_money_per_price_unit_cross_uses_conversion():
    # EURGBP: GBP moves are worth GBPUSD dollars each.
    assert money_per_price_unit(EURGBP, price=0.85, conversion=1.27) == pytest.approx(100_000.0 * 1.27)


def test_cross_without_conversion_raises():
    with pytest.raises(ValueError, match="GBP"):
        money_per_price_unit(EURGBP, price=0.85)


def test_account_currency_is_configurable():
    # Binance accounts are denominated in USDT, so USDT-quoted pairs need no conversion.
    assert money_per_price_unit(BTCUSDT, price=60_000.0, account_ccy="USDT") == pytest.approx(1.0)


# ── commission ─────────────────────────────────────────────────────────────

def test_commission_spec_per_lot_and_rate_variants():
    # MT5: fixed money per lot per side, independent of price.
    assert commission_per_side(EURUSD, lots=2.0, price=1.0850) == pytest.approx(7.0)
    # Binance: rate on notional per side. 0.5 BTC at 60,000 = 30,000 USDT notional.
    assert commission_per_side(BTCUSDT, lots=0.5, price=60_000.0, account_ccy="USDT") == pytest.approx(30.0)


def test_rate_commission_on_cross_uses_conversion():
    rate_spec = _spec("EURGBP", "EUR", "GBP", commission=CommissionSpec(kind="RATE_PER_SIDE", value=0.0001))
    # notional = 1 lot * 100,000 EUR * 0.85 GBP/EUR * 1.27 USD/GBP
    expected = 0.0001 * 100_000.0 * 0.85 * 1.27
    assert commission_per_side(rate_spec, lots=1.0, price=0.85, conversion=1.27) == pytest.approx(expected)


def test_invalid_commission_kind_rejected():
    with pytest.raises(ValueError, match="commission kind"):
        CommissionSpec(kind="PER_TRADE", value=1.0)


@pytest.mark.parametrize("field", ["tick_size", "contract_size", "volume_min", "volume_step", "volume_max"])
def test_nonpositive_size_fields_rejected(field):
    with pytest.raises(ValueError, match=field):
        _spec("EURUSD", "EUR", "USD", **{field: 0.0})


# ── spec collections and files ─────────────────────────────────────────────

def test_unknown_instrument_raises_with_available_list():
    specs = InstrumentSpecs(venue="mt5", account_ccy="USD", specs={"EURUSD": EURUSD, "USDJPY": USDJPY})
    with pytest.raises(UnknownInstrumentError) as exc_info:
        specs["GBPUSD"]
    message = str(exc_info.value)
    assert "GBPUSD" in message
    assert "EURUSD" in message and "USDJPY" in message


def test_load_specs_from_toml_round_trip(tmp_path):
    original = InstrumentSpecs(
        venue="mt5", account_ccy="USD", specs={"EURUSD": EURUSD, "USDJPY": USDJPY, "EURGBP": EURGBP}
    )
    path = tmp_path / "mt5.toml"
    path.write_text(dumps_specs(original), encoding="utf-8")

    loaded = load_specs(path)

    assert loaded == original
    assert loaded["USDJPY"].tick_size == 0.001


def test_load_specs_rejects_unknown_field(tmp_path):
    # A typo in a hand-edited spec file must fail loudly, not be ignored.
    original = InstrumentSpecs(venue="mt5", account_ccy="USD", specs={"EURUSD": EURUSD})
    text = dumps_specs(original).replace("stop_slippage", "stop_slipage", 1)
    path = tmp_path / "typo.toml"
    path.write_text(text, encoding="utf-8")

    with pytest.raises(ValueError, match="stop_slipage"):
        load_specs(path)


def test_load_specs_names_missing_field(tmp_path):
    original = InstrumentSpecs(venue="mt5", account_ccy="USD", specs={"EURUSD": EURUSD})
    text = "\n".join(
        line for line in dumps_specs(original).splitlines() if not line.startswith("contract_size")
    )
    path = tmp_path / "missing.toml"
    path.write_text(text, encoding="utf-8")

    with pytest.raises(ValueError, match="EURUSD.*contract_size"):
        load_specs(path)


def test_specs_must_match_collection_venue():
    with pytest.raises(ValueError, match="venue"):
        InstrumentSpecs(venue="mt5", account_ccy="USD", specs={"BTCUSDT": BTCUSDT})


def test_dumps_specs_records_source_as_comment(tmp_path):
    specs = InstrumentSpecs(venue="mt5", account_ccy="USD", specs={"EURUSD": EURUSD})
    text = dumps_specs(specs, source="Some Broker / Some-Server, exported 2026-10-05")
    assert "# Source: Some Broker / Some-Server, exported 2026-10-05" in text
    path = tmp_path / "mt5.toml"
    path.write_text(text, encoding="utf-8")
    assert load_specs(path) == specs  # a comment, so loading is unaffected


# ── swap (liquidity-engine Req 25.1, task 240) ─────────────────────────────

REPO = Path(__file__).resolve().parents[2]


def test_spec_files_without_swap_load_with_none(tmp_path):
    # Files written before swap was recorded, and venues without it (Binance spot), mean no swap.
    old = tmp_path / "old.toml"
    old.write_text(dumps_specs(InstrumentSpecs(venue="mt5", account_ccy="USD", specs={"EURUSD": EURUSD})),
                   encoding="utf-8")
    assert "swap" not in old.read_text(encoding="utf-8") and load_specs(old)["EURUSD"].swap == NO_SWAP
    assert all(spec.swap == NO_SWAP for spec in load_specs(REPO / "config" / "instruments" / "binance.toml").values())


def test_swap_round_trips_through_the_spec_file(tmp_path):
    swapped = replace(EURUSD, swap=SwapSpec(mode="POINTS", long=-7.25, short=1.5, triple_day=3))
    original = InstrumentSpecs(venue="mt5", account_ccy="USD", specs={"EURUSD": swapped, "USDJPY": USDJPY})
    path = tmp_path / "mt5.toml"
    path.write_text(dumps_specs(original), encoding="utf-8")
    assert load_specs(path) == original
    assert "swap" not in path.read_text(encoding="utf-8").split('["USDJPY"]')[1]   # no swap, no line


@pytest.mark.parametrize("mode", ["INTEREST_CURRENT", "CURRENCY_MARGIN", "points"])
def test_unsupported_swap_mode_rejected(mode):
    with pytest.raises(ValueError, match="swap mode"):
        SwapSpec(mode=mode, long=-1.0, short=-1.0, triple_day=3)


def test_swap_triple_day_is_an_mt5_weekday():
    with pytest.raises(ValueError, match="triple_day"):
        SwapSpec(mode="POINTS", long=-1.0, short=-1.0, triple_day=7)


@pytest.mark.parametrize("spec, direction, price, expected", [
    (replace(EURUSD, swap=SwapSpec("POINTS", -7.0, 2.0, 3)), "LONG", 1.10, -7.0),       # 7 points x 1e-5 x 100k USD
    (replace(EURUSD, swap=SwapSpec("POINTS", -7.0, 2.0, 3)), "SHORT", 1.10, 2.0),
    (replace(USDJPY, swap=SwapSpec("POINTS", -1.0, 3.0, 3)), "SHORT", 150.0, 2.0),     # 3 x 0.001 x 100k JPY / 150
    (replace(EURUSD, swap=SwapSpec("CURRENCY_SYMBOL", -5.0, 1.0, 3)), "LONG", 1.10, -5.5),   # EUR 5 at 1.10
    (replace(EURUSD, swap=SwapSpec("CURRENCY_DEPOSIT", -4.0, 1.0, 3)), "LONG", 1.10, -4.0),
    (EURUSD, "LONG", 1.10, 0.0),
])
def test_swap_per_lot_per_night_in_account_currency(spec, direction, price, expected):
    assert swap_per_lot_per_night(spec, direction, price) == pytest.approx(expected)
