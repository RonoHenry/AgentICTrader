"""SimBroker and the MT5 adapter place the same order (live-execution Requirement 8; task 460).

The same instrument spec, account budget, order, market and time go to the
backtest's broker and to the live one on a fake terminal built from that spec.
Both must agree on: refused or not, and why; limit or market; the lots; the
expiry instant; the partial's split. The stop backstop is on in both (LX-D1).

The fake terminal prices a lot as MT5 does, trade_tick_value per
trade_tick_size. For instruments quoted in the account currency (EURUSD,
XAUUSD on a USD account) that is SimBroker's contract size exactly. For a
USD-based pair or a cross MT5 converts at the current price while SimBroker
converts at the entry: a known divergence (design.md), not drawn here.

Validates: Requirement 8.1 (.kiro/specs/live-execution/requirements.md)
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from agent.brokers.fill_model import Bar, partial_level
from agent.brokers.mt5 import MT5BrokerAdapter, MT5BrokerError
from agent.instruments import CommissionSpec, InstrumentSpec, InstrumentSpecs
from agent.strategy_config import PendingExpiry
from algo_backtester.sim_broker import SimBroker, SimBrokerError

UTC = timezone.utc
WEEK = datetime(2026, 9, 28, 0, 0, tzinfo=UTC)   # a Monday
TTL = timedelta(hours=3)

SPECS = InstrumentSpecs("mt5", "USD", {
    "EURUSD": InstrumentSpec(symbol="EURUSD", venue="mt5", point=1e-5, tick_size=1e-5, contract_size=100_000.0,
                             volume_min=0.01, volume_step=0.01, volume_max=50.0, base_ccy="EUR", quote_ccy="USD",
                             default_spread=0.0001, stop_slippage=0.00002, commission=CommissionSpec("PER_LOT_PER_SIDE",
                                                                                                    3.5)),
    "XAUUSD": InstrumentSpec(symbol="XAUUSD", venue="mt5", point=0.01, tick_size=0.01, contract_size=100.0,
                             volume_min=0.01, volume_step=0.01, volume_max=20.0, base_ccy="XAU", quote_ccy="USD",
                             default_spread=0.2, stop_slippage=0.05, commission=CommissionSpec("PER_LOT_PER_SIDE",
                                                                                              3.5)),
})
PRICE = {"EURUSD": (1.05, 1.25, 0.00004, 0.0004), "XAUUSD": (1800.0, 2800.0, 0.08, 0.8)}   # close range, spreads


@st.composite
def cases(draw):
    instrument = draw(st.sampled_from(sorted(PRICE)))
    low, high, min_spread, max_spread = PRICE[instrument]
    close = draw(st.floats(low, high))
    spread = draw(st.floats(min_spread, max_spread))
    direction = draw(st.sampled_from(["LONG", "SHORT"]))
    sign = 1 if direction == "LONG" else -1
    unit = max_spread * 10
    # The entry from well inside to past the market (limit and market orders), the stop from a hair to wide.
    entry = close + spread * (sign > 0) + draw(st.floats(-3.0, 1.0)) * unit * sign
    stop_distance = draw(st.floats(0.05, 8.0)) * unit
    stop = entry - sign * stop_distance
    target = entry + sign * stop_distance * draw(st.floats(1.0, 8.0))
    return dict(
        instrument=instrument, close=close, spread=spread, direction=direction,
        entry=round(entry, 5), stop=round(stop, 5), target=round(target, 5),
        risk=draw(st.floats(1.0, 600.0)),
        now=WEEK + timedelta(minutes=draw(st.integers(0, 5 * 24 * 60 - 1))),
        partial=draw(st.booleans()),
    )


def _sim(case) -> tuple:
    broker = SimBroker(SPECS, clock=lambda: case["now"], expiry_rule=PendingExpiry.KILLZONE_END, fallback_ttl=TTL,
                       max_stop_overrun=0.5, partial_r=3.0 if case["partial"] else 0.0,
                       partial_fraction=1 / 3 if case["partial"] else 0.0)
    c = case["close"]
    broker.advance(case["instrument"], Bar(timestamp=case["now"] - timedelta(minutes=1), open=c, high=c, low=c,
                                           close=c, spread=case["spread"]))
    try:
        broker.place_order(_order(case))
    except SimBrokerError as exc:
        return ("REFUSED", exc.reason)
    trade = broker.active_trade(case["instrument"])
    level = partial_level(case["direction"], trade.entry, trade.stop, trade.target, 3.0) if case["partial"] else None
    part = round(trade.lots * trade.partial_fraction, 9) if level is not None and trade.partial_r else 0.0
    return ("PLACED", trade.kind, trade.lots, trade.expires_at, part)


def _mt5(case) -> tuple:
    spec = SPECS[case["instrument"]]
    with patch("agent.brokers.mt5.mt5") as mt5:
        mt5.initialize.return_value = True
        mt5.ORDER_TYPE_BUY, mt5.ORDER_TYPE_SELL, mt5.ORDER_TYPE_BUY_LIMIT, mt5.ORDER_TYPE_SELL_LIMIT = 0, 1, 2, 3
        mt5.TRADE_ACTION_DEAL, mt5.TRADE_ACTION_PENDING = 1, 5
        mt5.ORDER_TIME_GTC, mt5.ORDER_FILLING_IOC, mt5.ORDER_FILLING_RETURN = 0, 1, 2
        mt5.symbol_info.return_value = MagicMock(
            filling_mode=2, volume_min=spec.volume_min, volume_step=spec.volume_step, volume_max=spec.volume_max,
            trade_tick_size=spec.tick_size, trade_tick_value=spec.contract_size * spec.tick_size, expiration_mode=1)
        mt5.symbol_info_tick.return_value = MagicMock(bid=case["close"], ask=case["close"] + case["spread"])
        mt5.order_send.side_effect = lambda request: MagicMock(retcode=10009, order=mt5.order_send.call_count)
        adapter = MT5BrokerAdapter(login=1, password="x", server="Demo", specs=SPECS, clock=lambda: case["now"],
                                   expiry_rule=PendingExpiry.KILLZONE_END, fallback_ttl=TTL,
                                   partial_r=3.0 if case["partial"] else 0.0,
                                   partial_fraction=1 / 3 if case["partial"] else 0.0)
        try:
            adapter.place_order(_order(case))
        except MT5BrokerError as exc:
            return ("REFUSED", exc.reason)
    trade = adapter.ledger.trades()[-1]
    expires = datetime.fromisoformat(trade["expires_at"]) if trade["expires_at"] else None
    part = trade["partial"]["lots"] if trade["partial"] else 0.0
    return ("PLACED", trade["kind"], trade["lots"], expires, part)


def _order(case) -> dict:
    return {"instrument": case["instrument"], "direction": case["direction"], "entry": case["entry"],
            "stop_loss": case["stop"], "take_profit": case["target"], "risk_amount": case["risk"], "setup_id": "p"}


@settings(max_examples=400, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(cases())
def test_the_backtest_and_the_live_broker_place_the_same_order(case):
    assert _mt5(case) == _sim(case)


def test_the_cases_reach_every_outcome():
    """The generator draws limits, markets and each refusal, so the property above isn't vacuous."""
    seen = set()

    @settings(max_examples=400, deadline=None, database=None)
    @given(cases())
    def collect(case):
        outcome = _sim(case)
        seen.add(outcome[1] if outcome[0] == "REFUSED" else outcome[1])

    collect()
    assert {"LIMIT", "MARKET", "STOP_TOO_TIGHT", "MIN_VOLUME_OVER_RISK"} <= seen
