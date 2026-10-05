"""Instrument specifications: contract size, volume limits, costs, and the
conversion from an instrument's quote currency into the account currency.

Shared by live sizing and AlgoBacktester (.kiro/specs/algo-backtester,
task 182). Specs live one file per venue in config/instruments/<venue>.toml:

    venue = "mt5"
    account_ccy = "USD"

    ["EURUSD"]
    point = 1e-05
    tick_size = 1e-05
    contract_size = 100000.0
    volume_min = 0.01
    volume_step = 0.01
    volume_max = 100.0
    base_ccy = "EUR"
    quote_ccy = "USD"
    default_spread = 0.00012
    stop_slippage = 2e-05
    commission = { kind = "PER_LOT_PER_SIDE", value = 3.5 }

Prices, spreads and slippage are in price units. Commission is account
currency per lot per side (MT5) or a rate on notional per side (Binance).

Validates: Requirements 5.2, 6.1 (.kiro/specs/algo-backtester/requirements.md)
"""
from __future__ import annotations

import json
import math
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Optional

__all__ = [
    "COMMISSION_KINDS",
    "VENUES",
    "CommissionSpec",
    "InstrumentSpec",
    "InstrumentSpecs",
    "UnknownInstrumentError",
    "commission_per_side",
    "dumps_specs",
    "load_specs",
    "money_per_price_unit",
    "quote_to_account_rate",
]

COMMISSION_KINDS = ("PER_LOT_PER_SIDE", "RATE_PER_SIDE")
VENUES = ("mt5", "binance")

# Spec-file field order, also the order dumps_specs() writes them in.
_NUMERIC_FIELDS = (
    "point",
    "tick_size",
    "contract_size",
    "volume_min",
    "volume_step",
    "volume_max",
)
_FIELDS = (*_NUMERIC_FIELDS, "base_ccy", "quote_ccy", "default_spread", "stop_slippage", "commission")


class UnknownInstrumentError(KeyError):
    """No spec for the requested instrument. A KeyError, so Mapping.get() works."""

    def __str__(self) -> str:
        return self.args[0]


@dataclass(frozen=True)
class CommissionSpec:
    kind: str
    value: float

    def __post_init__(self) -> None:
        if self.kind not in COMMISSION_KINDS:
            raise ValueError(f"Unknown commission kind {self.kind!r}; expected one of {COMMISSION_KINDS}")
        if not math.isfinite(self.value) or self.value < 0:
            raise ValueError(f"Commission value must be finite and >= 0, got {self.value}")


@dataclass(frozen=True)
class InstrumentSpec:
    symbol: str
    venue: str
    point: float
    tick_size: float
    contract_size: float
    volume_min: float
    volume_step: float
    volume_max: float
    base_ccy: str
    quote_ccy: str
    default_spread: float
    stop_slippage: float
    commission: CommissionSpec

    def __post_init__(self) -> None:
        if self.venue not in VENUES:
            raise ValueError(f"{self.symbol}: unknown venue {self.venue!r}; expected one of {VENUES}")
        for name in _NUMERIC_FIELDS:
            value = getattr(self, name)
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{self.symbol}: {name} must be finite and > 0, got {value}")
        for name in ("default_spread", "stop_slippage"):
            value = getattr(self, name)
            if not math.isfinite(value) or value < 0:
                raise ValueError(f"{self.symbol}: {name} must be finite and >= 0, got {value}")
        if self.volume_min > self.volume_max:
            raise ValueError(f"{self.symbol}: volume_min {self.volume_min} exceeds volume_max {self.volume_max}")


class InstrumentSpecs(Mapping):
    """All instrument specs for one venue, keyed by instrument name."""

    def __init__(self, venue: str, account_ccy: str, specs: Mapping[str, InstrumentSpec]) -> None:
        if venue not in VENUES:
            raise ValueError(f"Unknown venue {venue!r}; expected one of {VENUES}")
        for key, spec in specs.items():
            if spec.symbol != key:
                raise ValueError(f"Spec keyed {key!r} is for symbol {spec.symbol!r}")
            if spec.venue != venue:
                raise ValueError(f"{key}: spec venue {spec.venue!r} does not match collection venue {venue!r}")
        self.venue = venue
        self.account_ccy = account_ccy
        self._specs = dict(specs)

    def __getitem__(self, symbol: str) -> InstrumentSpec:
        try:
            return self._specs[symbol]
        except KeyError:
            raise UnknownInstrumentError(
                f"No {self.venue} spec for {symbol!r}. Available: {sorted(self._specs)}"
            ) from None

    def __iter__(self) -> Iterator[str]:
        return iter(self._specs)

    def __len__(self) -> int:
        return len(self._specs)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, InstrumentSpecs):
            return NotImplemented
        return (self.venue, self.account_ccy, self._specs) == (other.venue, other.account_ccy, other._specs)

    __hash__ = None  # defines __eq__ over a dict, so unhashable like dict

    def __repr__(self) -> str:
        return f"InstrumentSpecs(venue={self.venue!r}, account_ccy={self.account_ccy!r}, symbols={sorted(self._specs)})"


def quote_to_account_rate(
    spec: InstrumentSpec, price: float, conversion: Optional[float] = None, account_ccy: str = "USD"
) -> float:
    """Account-currency value of one unit of the instrument's quote currency.

    ``conversion`` is the quote→account rate at that moment. It is required
    only for crosses, where neither leg is the account currency (e.g. the
    GBPUSD rate for EURGBP on a USD account).
    """
    if spec.quote_ccy == account_ccy:
        return 1.0
    if spec.base_ccy == account_ccy:
        return 1.0 / price
    if conversion is None:
        raise ValueError(
            f"{spec.symbol}: quote currency {spec.quote_ccy} is not the account currency {account_ccy}; "
            f"pass conversion = the {spec.quote_ccy}->{account_ccy} rate"
        )
    return conversion


def money_per_price_unit(
    spec: InstrumentSpec, price: float, conversion: Optional[float] = None, account_ccy: str = "USD"
) -> float:
    """Account-currency value of a 1.0 price move on 1 lot."""
    return spec.contract_size * quote_to_account_rate(spec, price, conversion, account_ccy)


def commission_per_side(
    spec: InstrumentSpec,
    lots: float,
    price: float,
    conversion: Optional[float] = None,
    account_ccy: str = "USD",
) -> float:
    """Commission in account currency for one side (entry or exit) of a trade."""
    commission = spec.commission
    if commission.kind == "PER_LOT_PER_SIDE":
        return commission.value * lots
    notional = lots * spec.contract_size * price * quote_to_account_rate(spec, price, conversion, account_ccy)
    return commission.value * notional


# ── spec files ─────────────────────────────────────────────────────────────

def load_specs(path: str | Path) -> InstrumentSpecs:
    """Load a venue's spec file. Unknown or missing fields raise ValueError."""
    data = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    venue = data.pop("venue", None)
    account_ccy = data.pop("account_ccy", None)
    if venue is None or account_ccy is None:
        raise ValueError(f"{path}: top-level 'venue' and 'account_ccy' are required")

    specs = {}
    for symbol, table in data.items():
        if not isinstance(table, dict):
            raise ValueError(f"{path}: unexpected top-level key {symbol!r}")
        unknown = sorted(set(table) - set(_FIELDS))
        if unknown:
            raise ValueError(f"{path}: {symbol}: unknown field(s) {unknown}")
        missing = [name for name in _FIELDS if name not in table]
        if missing:
            raise ValueError(f"{path}: {symbol}: missing field(s) {missing}")
        fields = dict(table)
        for name in (*_NUMERIC_FIELDS, "default_spread", "stop_slippage"):
            fields[name] = float(fields[name])
        commission = fields.pop("commission")
        specs[symbol] = InstrumentSpec(
            symbol=symbol,
            venue=venue,
            commission=CommissionSpec(kind=commission["kind"], value=float(commission["value"])),
            **fields,
        )
    return InstrumentSpecs(venue=venue, account_ccy=account_ccy, specs=specs)


def dumps_specs(specs: InstrumentSpecs) -> str:
    """Serialise to the spec-file format. Floats use repr(), so they round-trip exactly."""
    lines = [
        f"# Instrument specs for venue {specs.venue!r}. Prices, spreads and slippage are in price units.",
        f"venue = {_toml_str(specs.venue)}",
        f"account_ccy = {_toml_str(specs.account_ccy)}",
    ]
    for symbol in sorted(specs):
        spec = specs[symbol]
        lines.append("")
        lines.append(f"[{_toml_str(symbol)}]")
        for name in _FIELDS:
            value = getattr(spec, name)
            if isinstance(value, CommissionSpec):
                lines.append(
                    f"{name} = {{ kind = {_toml_str(value.kind)}, value = {_toml_float(value.value)} }}"
                )
            elif isinstance(value, str):
                lines.append(f"{name} = {_toml_str(value)}")
            else:
                lines.append(f"{name} = {_toml_float(value)}")
    return "\n".join(lines) + "\n"


def _toml_str(value: str) -> str:
    # JSON string escaping is valid for TOML basic strings.
    return json.dumps(value)


def _toml_float(value: float) -> str:
    # repr() of a finite float always contains "." or "e", so TOML reads it back as a float.
    return repr(float(value))
