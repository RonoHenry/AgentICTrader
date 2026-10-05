#!/usr/bin/env python3
"""Export instrument specs from a venue into config/instruments/<venue>.toml.

The backtester and live sizing read contract sizes, volume limits, spreads
and commission from these files (agent/instruments.py). Generating them from
the venue keeps those numbers exact; hand-typed tick sizes and commission
are exactly the kind of quiet error that flatters a backtest.

MT5 (reads only, places nothing):
- Contract and volume fields come from mt5.symbol_info().
- Default spread is the median (ask - bid) over recent ticks. M1 bar
  spreads aren't used: some servers record them as 0 for almost every bar.
  A zero spread is never a real cost, so it is reported as a problem;
  --spread SYMBOL=points supplies the value (e.g. your live broker's typical).
- Commission per lot per side is total commission (+ fee) divided by total
  traded volume over recent deal history. That is correct whether the broker
  splits commission across entry and exit deals or charges the round trip
  on entry (decision D2, .kiro/specs/algo-backtester/requirements.md).
- Stop slippage is 25% of the typical spread, minimum 2 points (decision D3,
  amended): 0.2 pip on EURUSD at 0.8 pip spread, $0.06 on XAUUSD at $0.24.
  A fixed 2 points would be only $0.002 on gold's 0.001 point.
- Cross-check: our money-per-tick must match the broker's trade_tick_value
  for pairs quoted or based in the account currency. A mismatch means the
  currency conversion would be wrong, so the file is not written.

Binance (public endpoints, no key): tick and lot sizes from exchangeInfo.
Fee is 0.001 per side, default spread is one tick, and stop slippage is
0.05% of the current price, stored in price units (D3).

Nothing is written while any problem remains. Problems go to stderr and the
exit code is 1. The file header records which broker/server the costs came
from: a demo server's pricing (e.g. MetaQuotes-Demo) is not a live broker's.

Usage:
    python scripts/export_instrument_specs.py --venue mt5 \\
        [--instruments EURUSD,GBPUSD,USDJPY,XAUUSD] [--commission XAUUSD=3.5] [--spread EURUSD=8] \\
        [--deals-days 180] [--out config/instruments/mt5.toml]
    python scripts/export_instrument_specs.py --venue binance \\
        [--instruments BTCUSDT,ETHUSDT] [--out config/instruments/binance.toml]
"""
from __future__ import annotations

import argparse
import json
import sys
from decimal import Decimal
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agent.instruments import (  # noqa: E402
    CommissionSpec,
    InstrumentSpec,
    InstrumentSpecs,
    dumps_specs,
    money_per_price_unit,
)

DEFAULT_INSTRUMENTS = {
    "mt5": ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD"],                              # D1
    "binance": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT"],  # forward test
}
STOP_SLIPPAGE_SPREAD_SHARE = 0.25  # D3 (amended): stop slippage = 25% of typical spread...
STOP_SLIPPAGE_MIN_POINTS = 2       # ...but never below 2 points
SPREAD_LOOKBACK = timedelta(hours=72)  # reaches back past a weekend
TICK_VALUE_TOLERANCE = 0.02       # 2% — tick values move with price between snapshots
BINANCE_ACCOUNT_CCY = "USDT"
BINANCE_FEE_RATE = 0.001          # spot taker/maker, per side
BINANCE_STOP_SLIPPAGE_RATE = 0.0005


# ── MT5 ────────────────────────────────────────────────────────────────────

def commission_per_lot_per_side(deals: Iterable[Any], symbol: str, mt5: Any) -> Optional[float]:
    """Average commission (+ fee) per lot per side for ``symbol``, or None without deals."""
    trade_types = (mt5.DEAL_TYPE_BUY, mt5.DEAL_TYPE_SELL)
    volume = cost = 0.0
    for deal in deals:
        if deal.symbol != symbol or deal.type not in trade_types or deal.volume <= 0:
            continue
        volume += deal.volume
        cost += abs(deal.commission) + abs(getattr(deal, "fee", 0.0) or 0.0)
    return cost / volume if volume > 0 else None


def mt5_specs(
    mt5: Any,
    instruments: Iterable[str],
    symbol_suffix: str = "",
    commission_overrides: Optional[Mapping[str, float]] = None,
    spread_overrides: Optional[Mapping[str, float]] = None,
    deals_days: int = 180,
) -> tuple[InstrumentSpecs, list[str]]:
    overrides = dict(commission_overrides or {})
    spread_points_overrides = dict(spread_overrides or {})
    account_ccy = mt5.account_info().currency
    now = datetime.now(timezone.utc)
    deals = mt5.history_deals_get(now - timedelta(days=deals_days), now) or ()

    specs: dict[str, InstrumentSpec] = {}
    problems: list[str] = []
    for instrument in instruments:
        symbol = f"{instrument}{symbol_suffix}"
        info = mt5.symbol_info(symbol) if mt5.symbol_select(symbol, True) else None
        if info is None:
            problems.append(f"{instrument}: symbol {symbol!r} not found on this MT5 server")
            continue

        if instrument in overrides:
            commission = overrides[instrument]
        else:
            commission = commission_per_lot_per_side(deals, symbol, mt5)
        if commission is None:
            problems.append(
                f"{instrument}: no {symbol} deals in the last {deals_days} days to measure commission from; "
                f"pass --commission {instrument}=<account currency per lot per side>"
            )
            continue

        point = float(info.point)
        if instrument in spread_points_overrides:
            spread_points = float(spread_points_overrides[instrument])
        else:
            ticks = mt5.copy_ticks_range(symbol, now - SPREAD_LOOKBACK, now, mt5.COPY_TICKS_INFO)
            if ticks is None or len(ticks) == 0:
                problems.append(f"{instrument}: no recent ticks to measure the typical spread from")
                continue
            spread_points = float(np.median(ticks["ask"] - ticks["bid"])) / point
        if spread_points <= 0:
            problems.append(
                f"{instrument}: {symbol} trades at a median spread of 0 on this server, which is not a real cost; "
                f"pass --spread {instrument}=<typical spread in points>"
            )
            continue

        spec = InstrumentSpec(
            symbol=instrument,
            venue="mt5",
            point=point,
            tick_size=float(info.trade_tick_size),
            contract_size=float(info.trade_contract_size),
            volume_min=float(info.volume_min),
            volume_step=float(info.volume_step),
            volume_max=float(info.volume_max),
            base_ccy=info.currency_base,
            # Profit currency is what a price move is paid in, i.e. the quote
            # currency for FX, metals and indices alike.
            quote_ccy=info.currency_profit,
            default_spread=_price_units(spread_points, point),
            stop_slippage=_price_units(
                max(STOP_SLIPPAGE_MIN_POINTS, STOP_SLIPPAGE_SPREAD_SHARE * spread_points), point
            ),
            commission=CommissionSpec(kind="PER_LOT_PER_SIDE", value=float(commission)),
        )
        mismatch = _tick_value_mismatch(spec, info, mt5.symbol_info_tick(symbol), account_ccy)
        if mismatch:
            problems.append(mismatch)
            continue
        specs[instrument] = spec
    return InstrumentSpecs(venue="mt5", account_ccy=account_ccy, specs=specs), problems


def _price_units(points: float, point: float) -> float:
    """``points`` × ``point`` rounded to a tenth of a point, so ask - bid
    float noise (8.000000000008e-05) doesn't reach the human-read spec file."""
    decimals = max(0, -Decimal(repr(point)).as_tuple().exponent) + 1
    return round(points * point, decimals)


def _tick_value_mismatch(spec: InstrumentSpec, info: Any, tick: Any, account_ccy: str) -> Optional[str]:
    if account_ccy not in (spec.base_ccy, spec.quote_ccy):
        return None  # a cross: the backtest supplies a conversion series, nothing to check here
    price = tick.bid if tick is not None and tick.bid else info.bid
    ours = money_per_price_unit(spec, price, account_ccy=account_ccy) * spec.tick_size
    broker = float(info.trade_tick_value)
    if broker <= 0 or abs(ours - broker) / broker > TICK_VALUE_TOLERANCE:
        return (
            f"{spec.symbol}: tick value disagrees with the broker — computed {ours:.6g} {account_ccy} per tick "
            f"per lot, broker reports {broker:.6g}. Check base/quote currency and contract size."
        )
    return None


def _connect_mt5() -> tuple[Any, str]:
    import MetaTrader5 as mt5  # Windows-only; imported here so tests and Binance runs don't need it
    from decouple import Config, RepositoryEnv

    config = Config(RepositoryEnv(str(REPO_ROOT / ".env")))
    kwargs: dict[str, Any] = {
        "login": config("MT5_LOGIN", cast=int),
        "password": config("MT5_PASSWORD"),
        "server": config("MT5_SERVER"),
    }
    path = config("MT5_PATH", default="")
    if path:
        kwargs["path"] = path
    if not mt5.initialize(**kwargs):
        code, desc = mt5.last_error()
        raise RuntimeError(f"MT5 initialize failed ({code}): {desc}")
    return mt5, config("MT5_SYMBOL_SUFFIX", default="")


# ── Binance ────────────────────────────────────────────────────────────────

def binance_specs(
    exchange_info: Mapping[str, Any],
    instruments: Iterable[str],
    prices: Mapping[str, float],
    fee_rate: float = BINANCE_FEE_RATE,
    stop_slippage_rate: float = BINANCE_STOP_SLIPPAGE_RATE,
) -> tuple[InstrumentSpecs, list[str]]:
    by_symbol = {s["symbol"]: s for s in exchange_info.get("symbols", [])}
    specs: dict[str, InstrumentSpec] = {}
    problems: list[str] = []
    for instrument in instruments:
        info = by_symbol.get(instrument)
        if info is None:
            problems.append(f"{instrument}: not listed in Binance exchangeInfo")
            continue
        price = prices.get(instrument)
        if not price:
            problems.append(f"{instrument}: no current price to size stop slippage from")
            continue
        filters = {f["filterType"]: f for f in info["filters"]}
        tick = float(filters["PRICE_FILTER"]["tickSize"])
        lot = filters["LOT_SIZE"]
        specs[instrument] = InstrumentSpec(
            symbol=instrument,
            venue="binance",
            point=tick,
            tick_size=tick,
            contract_size=1.0,
            volume_min=float(lot["minQty"]),
            volume_step=float(lot["stepSize"]),
            volume_max=float(lot["maxQty"]),
            base_ccy=info["baseAsset"],
            quote_ccy=info["quoteAsset"],
            default_spread=tick,  # liquid spot books are usually one tick wide
            stop_slippage=stop_slippage_rate * float(price),
            commission=CommissionSpec(kind="RATE_PER_SIDE", value=fee_rate),
        )
    return InstrumentSpecs(venue="binance", account_ccy=BINANCE_ACCOUNT_CCY, specs=specs), problems


def _fetch_binance(instruments: list[str]) -> tuple[dict, dict[str, float]]:
    import requests

    from services.market_data.binance import DEFAULT_BASE_URL

    symbols = json.dumps(instruments, separators=(",", ":"))
    info = requests.get(f"{DEFAULT_BASE_URL}/api/v3/exchangeInfo", params={"symbols": symbols}, timeout=30)
    info.raise_for_status()
    ticker = requests.get(f"{DEFAULT_BASE_URL}/api/v3/ticker/price", params={"symbols": symbols}, timeout=30)
    ticker.raise_for_status()
    prices = {row["symbol"]: float(row["price"]) for row in ticker.json()}
    return info.json(), prices


# ── CLI ────────────────────────────────────────────────────────────────────

def _parse_overrides(text: str) -> dict[str, float]:
    overrides = {}
    for item in filter(None, (part.strip() for part in text.split(","))):
        symbol, _, value = item.partition("=")
        overrides[symbol.strip().upper()] = float(value)
    return overrides


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--venue", choices=sorted(DEFAULT_INSTRUMENTS), required=True)
    parser.add_argument("--instruments", help="comma-separated; default depends on --venue")
    parser.add_argument("--out", help="output file (default: config/instruments/<venue>.toml)")
    parser.add_argument("--commission", default="", help="MT5 overrides, e.g. XAUUSD=3.5 (per lot per side)")
    parser.add_argument("--spread", default="", help="MT5 overrides in points, e.g. EURUSD=8,GBPUSD=10")
    parser.add_argument("--deals-days", type=int, default=180, help="MT5 deal history window for commission")
    args = parser.parse_args(argv)

    instruments = (
        [s.strip().upper() for s in args.instruments.split(",") if s.strip()]
        if args.instruments
        else DEFAULT_INSTRUMENTS[args.venue]
    )
    out = Path(args.out) if args.out else REPO_ROOT / "config" / "instruments" / f"{args.venue}.toml"

    if args.venue == "mt5":
        mt5, suffix = _connect_mt5()
        try:
            account = mt5.account_info()
            source = f"{account.company} / {account.server}"
            specs, problems = mt5_specs(
                mt5, instruments, symbol_suffix=suffix,
                commission_overrides=_parse_overrides(args.commission),
                spread_overrides=_parse_overrides(args.spread),
                deals_days=args.deals_days,
            )
        finally:
            shutdown = getattr(mt5, "shutdown", None)
            if shutdown:
                shutdown()
    else:
        exchange_info, prices = _fetch_binance(instruments)
        specs, problems = binance_specs(exchange_info, instruments, prices)
        source = "Binance public exchangeInfo"

    if problems:
        print(f"Not writing {out} — fix these first:", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1

    out.parent.mkdir(parents=True, exist_ok=True)
    source = f"{source}, exported {datetime.now(timezone.utc):%Y-%m-%d}"
    out.write_text(dumps_specs(specs, source=source), encoding="utf-8")
    print(f"Wrote {len(specs)} {args.venue} spec(s) to {out} (source {source}; account currency {specs.account_ccy}):")
    for symbol, spec in specs.items():
        print(
            f"  {symbol:<9} tick {spec.tick_size:g}  contract {spec.contract_size:g}  "
            f"volume {spec.volume_min:g}..{spec.volume_max:g} step {spec.volume_step:g}  "
            f"spread {spec.default_spread:g}  commission {spec.commission.kind} {spec.commission.value:g}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
