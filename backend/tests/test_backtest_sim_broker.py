"""
Tests for algo_backtester/sim_broker.py — the backtest's broker.

Task 201 (.kiro/specs/algo-backtester/tasks.md). SimBroker is a BrokerClient
that execute_node calls exactly as it calls the MT5 or paper broker: it picks
a limit or market order like MT5BrokerAdapter, sizes in lots from the money
risk, and steps orders through the shared FillModel. Closed trades carry R,
split into spread, slippage and commission.
Validates: Requirements 5.1, 5.3, 5.5, 6.1, 6.2 (.kiro/specs/algo-backtester/requirements.md)
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timedelta, timezone

import fakeredis
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from agent.brokers.fill_model import Bar
from agent.instruments import CommissionSpec, InstrumentSpec, InstrumentSpecs, money_per_price_unit
from agent.nodes.execute_node import execute_node
from agent.state import AgentMode, AgentState, DecisionAction, Direction, TradePlan
from agent.strategy_config import PendingExpiry
from algo_backtester.sim_broker import ClosedTrade, SimBroker, SimBrokerError
from services.risk_engine.main import RiskEngine

UTC = timezone.utc
T0 = datetime(2026, 9, 30, 13, 0, tzinfo=UTC)   # 09:00 New York: inside the NY AM killzone
MIN = timedelta(minutes=1)


def spec(symbol: str, base: str, quote: str, contract: float = 100_000.0, volume_min: float = 0.01,
         volume_step: float = 0.01, volume_max: float = 100.0, slippage: float = 0.00002,
         commission: float = 3.5) -> InstrumentSpec:
    return InstrumentSpec(symbol=symbol, venue="mt5", point=1e-5, tick_size=1e-5, contract_size=contract,
                          volume_min=volume_min, volume_step=volume_step, volume_max=volume_max, base_ccy=base,
                          quote_ccy=quote, default_spread=0.0001, stop_slippage=slippage,
                          commission=CommissionSpec("PER_LOT_PER_SIDE", commission))


SPECS = InstrumentSpecs("mt5", "USD", {
    "EURUSD": spec("EURUSD", "EUR", "USD"),
    "USDJPY": spec("USDJPY", "USD", "JPY", slippage=0.002),
    "EURGBP": spec("EURGBP", "EUR", "GBP"),
    "XAUUSD": spec("XAUUSD", "XAU", "USD", contract=100.0, slippage=0.02),
})
GBPUSD = 1.27   # the GBP -> USD rate for EURGBP


class Clock:
    def __init__(self, now: datetime = T0):
        self.now = now

    def __call__(self) -> datetime:
        return self.now


def broker(specs: InstrumentSpecs = SPECS, clock: Clock = None, **kwargs) -> SimBroker:
    return SimBroker(specs, clock=clock or Clock(), expiry_rule=PendingExpiry.KILLZONE_END,
                     fallback_ttl=timedelta(hours=3), conversion=lambda instrument, t: GBPUSD, **kwargs)


def bar(at: datetime, open_: float, high: float, low: float, close: float, spread: float = 0.0001) -> Bar:
    return Bar(timestamp=at, open=open_, high=high, low=low, close=close, spread=spread)


def priced(b: SimBroker, instrument: str, close: float, spread: float = 0.0001) -> SimBroker:
    """The M1 bar that closed at T0, so the broker knows the market at T0."""
    b.advance(instrument, bar(T0 - MIN, close, close, close, close, spread))
    return b


def order(direction="LONG", entry=1.1000, stop=1.0990, target=1.1040, risk_amount=100.0, instrument="EURUSD",
          **extra) -> dict:
    return {"instrument": instrument, "direction": direction, "entry": entry, "stop_loss": stop,
            "take_profit": target, "size": 0.01, "risk_amount": risk_amount, "setup_id": "setup-1", **extra}


# ── order type and sizing ──────────────────────────────────────────────────

@pytest.mark.parametrize("direction, entry, stop, target, kind", [
    ("LONG", 1.1000, 1.0990, 1.1100, "LIMIT"),    # below the ask (1.1011): rests
    ("LONG", 1.1011, 1.0990, 1.1100, "MARKET"),   # at the ask: already reached
    ("LONG", 1.1020, 1.0990, 1.1100, "MARKET"),   # above the ask
    ("SHORT", 1.1020, 1.1030, 1.0900, "LIMIT"),   # above the bid (1.1010): rests
    ("SHORT", 1.1010, 1.1030, 1.0900, "MARKET"),  # at the bid
    ("SHORT", 1.1000, 1.1030, 1.0900, "MARKET"),  # below the bid
])
def test_limit_vs_market_selection_like_mt5_adapter(direction, entry, stop, target, kind):
    b = priced(broker(), "EURUSD", close=1.1010)
    result = b.place_order(order(direction, entry, stop, target))
    assert result["pending"] is (kind == "LIMIT")
    assert result["order_id"] == result["trade_id"]
    active = b.active_trade("EURUSD")
    assert active.kind == kind and active.placed_at == T0 and active.direction == direction
    # a resting limit expires at the end of its killzone (10:00 New York); a market order fills now
    assert active.expires_at == (datetime(2026, 9, 30, 14, 0, tzinfo=UTC) if kind == "LIMIT" else None)


@pytest.mark.parametrize("instrument, price, stop_distance, expected_lots, per_lot", [
    ("EURUSD", 1.10000, 0.00265, 0.37, 100_000.0 * 0.00265),            # quote USD: 0.3774 -> 0.37
    ("USDJPY", 150.000, 0.265, 0.56, 100_000.0 / 150.0 * 0.265),        # base USD: 0.5660 -> 0.56
    ("EURGBP", 0.86000, 0.00265, 0.29, 100_000.0 * GBPUSD * 0.00265),   # cross: 0.2971 -> 0.29
])
def test_sizing_rounds_down_per_instrument_class(instrument, price, stop_distance, expected_lots, per_lot):
    b = priced(broker(), instrument, close=price * 1.01)
    b.place_order(order("LONG", price, price - stop_distance, price * 1.05, 100.0, instrument))
    lots = b.active_trade(instrument).lots
    assert lots == expected_lots                       # down, never to nearest (0.38, 0.57, 0.30)
    assert lots * per_lot <= 100.0 < (lots + 0.01) * per_lot


def test_size_clamped_to_volume_max():
    specs = InstrumentSpecs("mt5", "USD", {"EURUSD": spec("EURUSD", "EUR", "USD", volume_max=0.2)})
    b = priced(broker(specs), "EURUSD", close=1.1010)
    b.place_order(order(risk_amount=100.0))           # 1.0 lots wanted
    assert b.active_trade("EURUSD").lots == 0.2


def _state(entry=1.1000, stop=1.0980) -> AgentState:
    return AgentState(setup_id="setup-1", instrument="EURUSD", timeframe="M15", direction=Direction.LONG,
                      detected_at=T0, raw_confidence=0.8, final_confidence=0.8, mode=AgentMode.AUTONOMOUS,
                      trade_plan=TradePlan(entry=entry, stop_loss=stop, take_profit_1=1.1100, r_ratio=5.0,
                                           recommended_size=0.01))


def test_min_volume_over_risk_raises_and_execute_node_skips():
    b = priced(broker(), "EURUSD", close=1.1010)
    # 0.01 lots over a 20-pip stop risk $2: double a $1 budget
    with pytest.raises(SimBrokerError, match="MIN_VOLUME_OVER_RISK") as raised:
        b.place_order(order(stop=1.0980, risk_amount=1.0))
    assert raised.value.reason == "MIN_VOLUME_OVER_RISK"
    # within the 10% tolerance, the minimum volume is taken: $2 against $1.85
    b.place_order(order(stop=1.0980, risk_amount=1.85))
    assert b.active_trade("EURUSD").lots == 0.01

    redis = fakeredis.FakeRedis(decode_responses=True)
    redis.set("risk:exposure:default", json.dumps({"daily_dd_pct": 0.0, "weekly_dd_pct": 0.0,
                                                   "open_trades": 0, "equity": 100.0}))   # risk: $1
    fresh = priced(broker(), "EURUSD", close=1.1010)
    state = execute_node(_state(), risk_engine=RiskEngine(redis), broker_client=fresh)
    assert state.decision == DecisionAction.SKIP
    assert "MIN_VOLUME_OVER_RISK" in state.decision_reason
    assert fresh.active_trade("EURUSD") is None


@pytest.mark.parametrize("missing", ["direction", "stop_loss", "risk_amount"])
def test_missing_direction_or_stop_raises(missing):
    b = priced(broker(), "EURUSD", close=1.1010)
    without = {k: v for k, v in order().items() if k != missing}
    with pytest.raises(SimBrokerError):
        b.place_order(without)
    with pytest.raises(SimBrokerError):
        b.place_order({**order(), missing: None})
    assert b.active_trade("EURUSD") is None


def test_unknown_direction_and_no_price_raise():
    with pytest.raises(SimBrokerError, match="NO_PRICE"):
        broker().place_order(order())
    with pytest.raises(SimBrokerError):
        priced(broker(), "EURUSD", close=1.1010).place_order(order(direction="BUY"))


@pytest.mark.parametrize("direction, entry, stop, target", [
    ("LONG", 1.1000, 1.1005, 1.1100),    # limit: stop above entry
    ("LONG", 1.1000, 1.0990, 1.0995),    # limit: target below entry (a draw-on-liquidity fallback can do this)
    ("SHORT", 1.1020, 1.1030, 1.1025),   # limit: target above entry
    ("LONG", 1.1020, 1.1015, 1.1100),    # market: stop above the fill (ask 1.1011)
    ("SHORT", 1.1000, 1.1030, 1.1015),   # market: target above the fill (bid 1.1010)
    ("LONG", 1.1000, 1.1000, 1.1100),    # no stop distance
])
def test_invalid_stops_rejected_at_placement(direction, entry, stop, target):
    # MT5's order_send refuses them; execute_node then skips with the reason
    b = priced(broker(), "EURUSD", close=1.1010)
    with pytest.raises(SimBrokerError, match="INVALID_STOPS"):
        b.place_order(order(direction, entry, stop, target))


def test_sequential_order_ids():
    b = priced(broker(), "EURUSD", close=1.1010)
    priced(b, "XAUUSD", close=2650.0, spread=0.2)
    ids = [b.place_order(order())["order_id"],
           b.place_order(order(entry=2640.0, stop=2630.0, target=2700.0, instrument="XAUUSD"))["order_id"],
           b.place_order(order())["order_id"]]
    assert ids == ["sim-000001", "sim-000002", "sim-000003"]


# ── closed trades: R and costs ─────────────────────────────────────────────

def test_r_and_cost_split_accounting():
    # LONG limit at 1.1000, stop 1.0990: fills when the ask trades below 1.1000, then stops out.
    b = priced(broker(), "EURUSD", close=1.1010)
    b.place_order(order("LONG", 1.1000, 1.0990, 1.1040, risk_amount=100.0))
    assert b.active_trade("EURUSD").lots == 1.0
    assert b.advance("EURUSD", bar(T0, 1.1005, 1.1006, 1.0998, 1.1000)) == []        # filled, no exit
    [trade] = b.advance("EURUSD", bar(T0 + MIN, 1.0995, 1.0996, 1.0985, 1.0986))     # stop hit

    # 1R = 10 pips, the distance it was sized on; the bid at the fill was 1.0999
    assert isinstance(trade, ClosedTrade) and trade.filled and trade.exit_reason == "SL"
    assert (trade.fill, trade.ideal_fill, trade.exit, trade.ideal_exit) == pytest.approx(
        (1.1000, 1.0999, 1.0990 - 0.00002, 1.0990))
    assert trade.initial_risk == pytest.approx(0.0010)
    assert trade.gross_r == pytest.approx(-0.9)                  # bid to bid: 9 pips
    assert trade.cost_r_spread == pytest.approx(0.1)             # 1 pip, paid on the buy
    assert trade.cost_r_slippage == pytest.approx(0.02)          # 0.2 pip on the stop exit
    assert trade.cost_r_commission == pytest.approx(0.07)        # $3.50 x 1 lot x 2 sides over $100 at risk
    assert trade.net_r == pytest.approx(-1.09)                   # money: -$109 on a $100 budget
    assert trade.cost_r == pytest.approx(trade.gross_r - trade.net_r)
    assert trade.pnl == pytest.approx(-109.0)
    assert (trade.placed_at, trade.filled_at, trade.closed_at) == (T0, T0, T0 + MIN)
    assert trade.holding_time == MIN
    assert trade.mae_r == pytest.approx(-1.0)                    # executed prices, closing side
    assert trade.mfe_r == pytest.approx(-0.1)                    # born down the spread
    assert b.active_trade("EURUSD") is None and b.closed_trades() == [trade]


def test_short_pays_spread_on_exit():
    # SHORT market at the bid, target hit: the exit buys at the ask.
    b = priced(broker(), "EURUSD", close=1.1000)
    b.place_order(order("SHORT", 1.0995, 1.1020, 1.0960, risk_amount=100.0))
    assert b.active_trade("EURUSD").lots == 0.4                       # sized on the requested entry, as MT5
    b.advance("EURUSD", bar(T0, 1.1000, 1.1005, 1.0990, 1.0995))       # fills at the open's bid
    [trade] = b.advance("EURUSD", bar(T0 + MIN, 1.0990, 1.0992, 1.0950, 1.0955, spread=0.0002))

    # 1R = 25 pips, from the requested entry it was sized on; the better fill shows up as extra R
    assert trade.exit_reason == "TP" and (trade.fill, trade.exit) == pytest.approx((1.1000, 1.0960))
    assert trade.initial_risk == pytest.approx(0.0025)
    assert trade.gross_r == pytest.approx((1.1000 - 1.0958) / 0.0025)
    assert trade.cost_r_spread == pytest.approx(0.0002 / 0.0025)       # the exit bar's spread
    assert trade.cost_r_slippage == 0.0
    assert trade.net_r == pytest.approx(0.0040 / 0.0025 - 2 * 3.5 * 0.4 / (0.4 * 0.0025 * 100_000))


def test_expired_limit_closes_unfilled():
    b = priced(broker(), "EURUSD", close=1.1010)
    b.place_order(order("LONG", 1.1000, 1.0990, 1.1040))
    expiry = datetime(2026, 9, 30, 14, 0, tzinfo=UTC)
    assert b.advance("EURUSD", bar(expiry - MIN, 1.1010, 1.1012, 1.1005, 1.1010)) == []
    [trade] = b.advance("EURUSD", bar(expiry, 1.1010, 1.1012, 1.0950, 1.1010))
    assert not trade.filled and trade.exit_reason == "EXPIRED"
    assert trade.gross_r is None and trade.net_r is None and trade.pnl == 0.0 and not trade.cost_flag


def test_bars_before_placement_ignored_and_other_instruments_untouched():
    b = priced(broker(), "EURUSD", close=1.1010)
    b.place_order(order("LONG", 1.1000, 1.0990, 1.1040))
    assert b.advance("EURUSD", bar(T0 - MIN, 1.1010, 1.1010, 1.0900, 1.1010)) == []   # opened before t
    assert b.advance("XAUUSD", bar(T0, 2650.0, 2651.0, 2600.0, 2640.0, 0.2)) == []
    assert b.active_trade("EURUSD").status == "PENDING"


@pytest.mark.parametrize("fraction, flagged", [(0.25, False), (0.15, True)])
def test_cost_flag_above_fraction_of_risk(fraction, flagged):
    b = priced(broker(cost_flag_fraction=fraction), "EURUSD", close=1.1010)
    b.place_order(order("LONG", 1.1000, 1.0990, 1.1040))
    b.advance("EURUSD", bar(T0, 1.1005, 1.1006, 1.0998, 1.1000))
    [trade] = b.advance("EURUSD", bar(T0 + MIN, 1.0995, 1.0996, 1.0985, 1.0986))
    assert trade.cost_r == pytest.approx(0.19)   # 0.10 spread + 0.02 slippage + 0.07 commission
    assert trade.cost_flag is flagged


def test_spread_wider_than_stop_still_measured_in_sized_risk():
    # A 0.6-pip stop against a 0.8-pip spread, as on real EURUSD (task 217): the limit
    # fills with the bid already below the stop and is out on the same bar.
    b = priced(broker(), "EURUSD", close=1.1010, spread=0.00008)
    b.place_order(order("LONG", 1.10000, 1.09994, 1.10040, risk_amount=100.0))
    [trade] = b.advance("EURUSD", bar(T0, 1.10005, 1.10006, 1.09990, 1.09995, spread=0.00008))
    assert trade.exit_reason == "SL" and trade.initial_risk == pytest.approx(0.00006)
    assert trade.net_r == pytest.approx((1.09994 - 0.00002 - 1.10000) / 0.00006 - trade.cost_r_commission)
    assert trade.pnl == pytest.approx(trade.net_r * trade.lots * 0.00006 * 100_000)
    assert trade.cost_flag


# ── the rest of the BrokerClient interface ─────────────────────────────────

def test_close_position_cancels_pending_and_closes_open_at_market():
    b = priced(broker(), "EURUSD", close=1.1010)
    pending = b.place_order(order("LONG", 1.1000, 1.0990, 1.1040))["trade_id"]
    assert b.get_position_status(pending)["status"] == "PENDING"
    assert b.close_position(pending) is True
    assert b.closed_trades()[-1].exit_reason == "CANCELLED" and b.active_trade("EURUSD") is None

    market = b.place_order(order("LONG", 1.1020, 1.0990, 1.1100))["trade_id"]
    b.advance("EURUSD", bar(T0, 1.1010, 1.1015, 1.1008, 1.1012))
    status = b.get_position_status(market)
    assert status["status"] == "OPEN" and status["current_price"] == 1.1012
    assert b.close_position(market)
    closed = b.closed_trades()[-1]
    assert closed.exit_reason == "MANUAL" and closed.exit == 1.1012 and closed.filled
    assert b.get_position_status(market)["status"] == "CLOSED"


def test_set_sl_tp_moves_levels_and_partial_close_refused():
    b = priced(broker(), "EURUSD", close=1.1010)
    trade_id = b.place_order(order("LONG", 1.1000, 1.0990, 1.1040))["trade_id"]
    assert b.set_sl_tp(trade_id, 1.0985, 1.1050)
    assert (b.active_trade("EURUSD").stop, b.active_trade("EURUSD").target) == (1.0985, 1.1050)
    with pytest.raises(SimBrokerError):
        b.partial_close(trade_id)                     # scale-out is not simulated (D19)


# ── properties ─────────────────────────────────────────────────────────────

@st.composite
def trades(draw):
    """A random order on EURUSD or USDJPY and a random-walk bar sequence after it."""
    instrument = draw(st.sampled_from(["EURUSD", "USDJPY"]))
    scale = 1.0 if instrument == "EURUSD" else 100.0
    price = draw(st.floats(1.0, 1.5)) * scale
    direction = draw(st.sampled_from(["LONG", "SHORT"]))
    sign = 1 if direction == "LONG" else -1
    entry = price + draw(st.floats(-0.003, 0.003)) * scale
    stop = entry - sign * draw(st.floats(0.0002, 0.003)) * scale
    target = entry + sign * draw(st.floats(0.0005, 0.01)) * scale
    commission = draw(st.floats(0.0, 10.0))
    slippage = draw(st.floats(0.0, 0.0001)) * scale
    spreads = st.floats(0.0, 0.0003).map(lambda s: s * scale)
    bars, t, last = [], T0, price
    for _ in range(draw(st.integers(1, 40))):
        o = last + draw(st.floats(-0.0005, 0.0005)) * scale
        c = o + draw(st.floats(-0.001, 0.001)) * scale
        h = max(o, c) + draw(st.floats(0, 0.001)) * scale
        lo = min(o, c) - draw(st.floats(0, 0.001)) * scale
        bars.append(bar(t, o, h, lo, c, draw(spreads)))
        t, last = t + MIN, c
    return instrument, price, direction, entry, stop, target, commission, slippage, bars


@settings(max_examples=100, deadline=None)
@given(trades())
def test_property_6_costs_only_subtract(case):
    instrument, price, direction, entry, stop, target, commission, slippage, bars = case
    one = spec(instrument, *(("EUR", "USD") if instrument == "EURUSD" else ("USD", "JPY")),
               slippage=slippage, commission=commission)
    b = priced(broker(InstrumentSpecs("mt5", "USD", {instrument: one})), instrument, close=price)
    try:
        b.place_order(order(direction, entry, stop, target, 100.0, instrument))
    except SimBrokerError:
        return   # an invalid or undersized order never trades
    for each in bars:
        b.advance(instrument, each)
    for trade in b.closed_trades():
        if trade.filled:
            assert trade.cost_r_spread >= 0 and trade.cost_r_slippage >= 0 and trade.cost_r_commission >= 0
            assert trade.net_r <= trade.gross_r


@st.composite
def sizing_cases(draw):
    instrument = draw(st.sampled_from(["EURUSD", "USDJPY", "EURGBP", "XAUUSD"]))
    price = {"EURUSD": 1.1, "USDJPY": 150.0, "EURGBP": 0.86, "XAUUSD": 2650.0}[instrument]
    step = draw(st.sampled_from([0.001, 0.01, 0.1, 1.0]))
    volume_min = step * draw(st.integers(1, 10))
    volume_max = volume_min * draw(st.integers(1, 10_000))
    distance = price * draw(st.floats(0.0001, 0.05))
    risk_amount = draw(st.floats(0.5, 50_000.0))
    return instrument, price, step, volume_min, volume_max, distance, risk_amount


@settings(max_examples=100, deadline=None)
@given(sizing_cases())
def test_property_8_sizing_never_over_risks(case):
    instrument, price, step, volume_min, volume_max, distance, risk_amount = case
    base = SPECS[instrument]
    one = spec(instrument, base.base_ccy, base.quote_ccy, contract=base.contract_size, volume_min=volume_min,
               volume_step=step, volume_max=volume_max)
    entry = price
    # The broker sizes on the placed prices' distance, which floats can make differ from `distance`.
    per_lot = (entry - (entry - distance)) * money_per_price_unit(one, price, GBPUSD if instrument == "EURGBP" else None)
    b = priced(broker(InstrumentSpecs("mt5", "USD", {instrument: one})), instrument, close=price * 1.01)
    try:
        b.place_order(order("LONG", entry, entry - distance, entry * 1.1, risk_amount, instrument))
    except SimBrokerError as exc:
        assert exc.reason == "MIN_VOLUME_OVER_RISK"
        assert volume_min * per_lot > risk_amount * 1.10    # refused only when the minimum over-risks
        return
    lots = b.active_trade(instrument).lots
    assert volume_min <= lots <= volume_max
    assert math.isclose(lots / step, round(lots / step), abs_tol=1e-6)
    assert lots * per_lot <= risk_amount * 1.10
