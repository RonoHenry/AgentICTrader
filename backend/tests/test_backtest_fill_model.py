"""
Tests for agent/brokers/fill_model.py — the one fill model the paper broker
and the backtester share.

Task 194 (.kiro/specs/algo-backtester/tasks.md). Hand-built M1 bars; prices
are bid, ask = bid + spread. Here spread = 0.1 and stop slippage = 0.05.
Validates: Requirements 4.2-4.12 (.kiro/specs/algo-backtester/requirements.md)
"""
from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from agent.brokers.fill_model import Bar, FillModel, SimOrder, pending_expiry
from agent.strategy_config import PendingExpiry

UTC = timezone.utc
NY = ZoneInfo("America/New_York")
MIN = timedelta(minutes=1)
SPREAD, SLIP = 0.1, 0.05
T0 = datetime(2026, 1, 14, 9, 0, tzinfo=NY).astimezone(UTC)  # Wednesday 09:00 New York (NY AM killzone)
FM = FillModel(stop_slippage=SLIP)


def bar(i: int, o: float, h: float, lo: float, c: float, spread: float = SPREAD, start: datetime = T0) -> Bar:
    return Bar(timestamp=start + i * MIN, open=o, high=h, low=lo, close=c, spread=spread)


def order(direction: str = "LONG", kind: str = "LIMIT", entry: float = 100.0, stop: float = 99.0,
          target: Optional[float] = 103.0, placed_at: datetime = T0, expires_at: Optional[datetime] = None) -> SimOrder:
    return SimOrder(order_id="o1", setup_id="s1", instrument="EURUSD", direction=direction, kind=kind,
                    entry=entry, stop=stop, target=target, placed_at=placed_at, expires_at=expires_at)


def run(o: SimOrder, bars: list[Bar], model: FillModel = FM) -> list[str]:
    return [event.kind for b in bars for event in model.step(o, b)]


def short() -> SimOrder:
    return order(direction="SHORT", entry=100.0, stop=101.0, target=97.0)


# ── market entries (4.3) ────────────────────────────────────────────────────

def test_market_long_fills_next_open_at_ask():
    o = order(kind="MARKET", entry=100.2)
    assert run(o, [bar(0, 100.2, 100.4, 100.1, 100.3)]) == ["FILLED"]
    assert (o.status, o.filled_at) == ("OPEN", T0)
    assert o.fill == pytest.approx(100.3) and o.ideal_fill == pytest.approx(100.2)


def test_market_short_fills_next_open_at_bid():
    o = order(direction="SHORT", kind="MARKET", entry=100.2, stop=101.5, target=97.0)
    assert run(o, [bar(0, 100.2, 100.4, 100.1, 100.3)]) == ["FILLED"]
    assert o.fill == pytest.approx(100.2) and o.ideal_fill == pytest.approx(100.2)


def test_market_order_rejected_when_open_beyond_stop():
    # Price gapped past the stop before the order could fill: a broker rejects the stops.
    o = order(kind="MARKET", entry=100.2, stop=100.5, target=103.0)
    assert run(o, [bar(0, 100.2, 100.4, 100.1, 100.3)]) == ["REJECTED"]
    assert (o.status, o.exit_reason, o.fill) == ("CLOSED", "INVALID_STOPS", None)


def test_market_fill_bar_allows_target():
    # Req 4.9 holds back targets on a limit's fill bar; a market fill at the open precedes the whole bar.
    o = order(kind="MARKET", entry=100.2)
    assert run(o, [bar(0, 100.2, 103.1, 100.1, 103.0)]) == ["FILLED", "TP"]


# ── limit entries (4.4) ─────────────────────────────────────────────────────

def test_limit_long_touch_does_not_fill():
    o = order()
    assert run(o, [bar(0, 100.3, 100.4, 99.9, 100.2)]) == []  # ask low 100.0 = entry: a touch
    assert o.status == "PENDING"


def test_limit_long_trades_through_fills_at_entry():
    o = order()
    assert run(o, [bar(0, 100.3, 100.4, 99.85, 100.2)]) == ["FILLED"]  # ask low 99.95 < 100
    assert o.fill == pytest.approx(100.0)
    assert o.ideal_fill == pytest.approx(99.9)  # the bid when the ask was at the limit


def test_limit_short_mirror():
    o = short()
    assert run(o, [bar(0, 99.8, 100.0, 99.7, 99.9)]) == []  # bid high = entry: a touch
    assert run(o, [bar(1, 99.8, 100.01, 99.7, 99.9)]) == ["FILLED"]
    assert o.fill == pytest.approx(100.0) and o.ideal_fill == pytest.approx(100.0)


# ── stops (4.5-4.7) ─────────────────────────────────────────────────────────

def filled_long() -> SimOrder:
    o = order()
    assert run(o, [bar(0, 100.3, 100.4, 99.8, 100.1)]) == ["FILLED"]
    return o


def filled_short() -> SimOrder:
    o = short()
    assert run(o, [bar(0, 99.8, 100.05, 99.7, 99.9)]) == ["FILLED"]
    return o


def test_long_stop_triggers_on_bid():
    o = filled_long()
    assert run(o, [bar(1, 99.5, 99.6, 99.01, 99.2)]) == []
    assert run(o, [bar(2, 99.3, 99.4, 99.0, 99.1)]) == ["SL"]
    assert (o.status, o.exit_reason, o.closed_at) == ("CLOSED", "SL", T0 + 2 * MIN)
    assert o.ideal_exit == pytest.approx(99.0) and o.exit == pytest.approx(98.95)


def test_short_stop_triggers_on_ask():
    o = filled_short()
    assert run(o, [bar(1, 100.5, 100.85, 100.4, 100.6)]) == []  # ask high 100.95
    assert run(o, [bar(2, 100.5, 100.9, 100.4, 100.6)]) == ["SL"]  # ask high 101.0
    assert o.exit == pytest.approx(101.05)
    assert o.ideal_exit == pytest.approx(100.9)  # the bid when the ask hit the stop


def test_gap_beyond_stop_fills_at_open():
    long_ = filled_long()
    assert run(long_, [bar(1, 98.5, 98.7, 98.4, 98.6)]) == ["SL"]
    assert long_.ideal_exit == pytest.approx(98.5) and long_.exit == pytest.approx(98.45)

    short_ = filled_short()
    assert run(short_, [bar(1, 101.2, 101.4, 101.1, 101.3)]) == ["SL"]  # ask open 101.3, beyond 101
    assert short_.ideal_exit == pytest.approx(101.2) and short_.exit == pytest.approx(101.35)


def test_stop_slippage_applied():
    for make, stop_bar in ((filled_long, bar(1, 99.3, 99.4, 99.0, 99.1)), (filled_short, bar(1, 100.5, 100.9, 100.4, 100.6))):
        exits = []
        for slippage in (0.0, 0.2):
            o = make()
            FillModel(stop_slippage=slippage).step(o, stop_bar)
            exits.append(o.exit)
        sign = 1 if make is filled_short else -1  # slippage always worsens the exit
        assert exits[1] - exits[0] == pytest.approx(sign * 0.2)


# ── targets (4.5, 4.8, 4.9) ─────────────────────────────────────────────────

def test_target_exit_no_slippage():
    long_ = filled_long()
    assert run(long_, [bar(1, 102.0, 103.0, 101.9, 102.8)]) == ["TP"]
    assert long_.exit == pytest.approx(103.0) and long_.ideal_exit == pytest.approx(103.0)

    short_ = filled_short()
    assert run(short_, [bar(1, 98.0, 98.1, 96.9, 97.5)]) == ["TP"]  # ask low 97.0
    assert short_.exit == pytest.approx(97.0) and short_.ideal_exit == pytest.approx(96.9)


def test_same_bar_stop_and_target_is_stop():
    o = filled_long()
    assert run(o, [bar(1, 100.0, 103.1, 98.9, 101.0)]) == ["SL"]
    o = filled_short()
    assert run(o, [bar(1, 100.0, 101.2, 96.5, 99.0)]) == ["SL"]


def test_fill_bar_allows_stop_not_target():
    o = order()
    assert run(o, [bar(0, 100.3, 103.2, 99.8, 103.0)]) == ["FILLED"]  # reached the target, but on the fill bar
    assert o.status == "OPEN"

    # Stopped out on the fill bar: at the stop, not at an open the position never saw.
    o = order()
    assert run(o, [bar(0, 98.8, 99.2, 98.7, 98.9)]) == ["FILLED", "SL"]
    assert o.ideal_exit == pytest.approx(99.0) and o.exit == pytest.approx(98.95)


# ── expiry (4.10, 4.11) ─────────────────────────────────────────────────────

def ny(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 1, day, hour, minute, tzinfo=NY).astimezone(UTC)


def test_expiry_killzone_end():
    assert pending_expiry(ny(14, 9), PendingExpiry.KILLZONE_END, timedelta(hours=3)) == ny(14, 10)       # NY AM
    assert pending_expiry(ny(14, 3, 30), PendingExpiry.KILLZONE_END, timedelta(hours=3)) == ny(14, 5)    # London
    assert pending_expiry(ny(14, 14), PendingExpiry.KILLZONE_END, timedelta(hours=3)) == ny(14, 16)      # NY PM
    # The rule taken literally: placed at the killzone's last instant, it expires at once.
    assert pending_expiry(ny(14, 10), PendingExpiry.KILLZONE_END, timedelta(hours=3)) == ny(14, 10)

    o = order(placed_at=ny(14, 9), expires_at=ny(14, 10))
    assert run(o, [bar(0, 100.3, 100.4, 100.1, 100.2, start=ny(14, 9, 59))]) == []
    # Would trade through the entry, but the killzone is over.
    assert run(o, [bar(0, 100.3, 100.4, 99.5, 100.2, start=ny(14, 10))]) == ["EXPIRED"]
    assert (o.status, o.exit_reason, o.fill, o.closed_at) == ("CLOSED", "EXPIRED", None, ny(14, 10))


def test_expiry_fallback_ttl_outside_killzone():
    assert pending_expiry(ny(14, 11), PendingExpiry.KILLZONE_END, timedelta(hours=3)) == ny(14, 14)
    assert pending_expiry(ny(14, 9), PendingExpiry.FIXED_TTL, timedelta(hours=3)) == ny(14, 12)


def test_order_expiring_over_weekend_expires_on_first_bar_after_open():
    placed = ny(16, 16, 30)  # Friday, after the NY PM killzone: 3 h fallback, inside the weekend
    o = order(placed_at=placed, expires_at=pending_expiry(placed, PendingExpiry.KILLZONE_END, timedelta(hours=3)))
    friday = bar(0, 100.3, 100.4, 100.1, 100.2, start=ny(16, 16, 59))
    sunday = bar(0, 100.3, 100.4, 99.5, 100.2, start=ny(18, 17))  # first bar after the FX open
    assert run(o, [friday, sunday]) == ["EXPIRED"]
    assert o.closed_at == ny(18, 17)


# ── other ───────────────────────────────────────────────────────────────────

def test_bars_before_placement_ignored():
    o = order(placed_at=T0 + 5 * MIN)
    before = copy.deepcopy(o)
    assert run(o, [bar(i, 100.3, 103.5, 98.0, 100.2) for i in range(5)]) == []
    assert o == before


def test_mae_mfe_tracked_on_closing_side():
    # LONG closes on the bid. The fill bar's high may predate the fill: only its low counts.
    o = order()
    run(o, [bar(0, 100.3, 100.6, 99.8, 100.1)])
    assert (o.mae_price, o.mfe_price) == (pytest.approx(99.8), pytest.approx(99.9))
    run(o, [bar(1, 100.0, 101.5, 99.5, 101.0)])
    assert (o.mae_price, o.mfe_price) == (pytest.approx(99.5), pytest.approx(101.5))
    run(o, [bar(2, 101.0, 103.2, 100.0, 103.0)])  # target 103: favourable excursion ends there
    assert (o.exit_reason, o.mae_price, o.mfe_price) == ("TP", pytest.approx(99.5), pytest.approx(103.0))

    # SHORT closes on the ask.
    o = short()
    run(o, [bar(0, 99.8, 100.05, 99.7, 99.9)])
    assert (o.mae_price, o.mfe_price) == (pytest.approx(100.15), pytest.approx(100.1))
    run(o, [bar(1, 99.9, 100.5, 98.0, 99.0)])
    assert (o.mae_price, o.mfe_price) == (pytest.approx(100.6), pytest.approx(98.1))
    run(o, [bar(2, 100.0, 100.95, 99.9, 100.5)])  # stop 101 on the ask: adverse excursion ends there
    assert (o.exit_reason, o.mae_price, o.mfe_price) == ("SL", pytest.approx(101.0), pytest.approx(98.1))


# ── properties 4, 5, 7 ──────────────────────────────────────────────────────

@st.composite
def scenario(draw):
    n = draw(st.integers(min_value=1, max_value=120))
    spread = draw(st.sampled_from([0.0, 0.02, 0.1, 0.3]))
    bars, price, ts = [], 100.0, T0
    for _ in range(n):
        ts += MIN * draw(st.sampled_from([1, 1, 1, 1, 60, 2880]))  # the odd gap in time (closed venue)
        o = round(price + draw(st.floats(min_value=-1.5, max_value=1.5)), 2)  # can gap
        c = round(o + draw(st.floats(min_value=-1.0, max_value=1.0)), 2)
        # Mostly ordinary bars; some wide outside bars, so one bar can reach both stop and target.
        reach = st.one_of(st.floats(min_value=0, max_value=1.0), st.floats(min_value=3.0, max_value=8.0))
        h = round(max(o, c) + draw(reach), 2)
        lo = round(min(o, c) - draw(reach), 2)
        bars.append(Bar(timestamp=ts, open=o, high=h, low=lo, close=c, spread=spread))
        price = c
    direction = draw(st.sampled_from(["LONG", "SHORT"]))
    sign = 1 if direction == "LONG" else -1
    entry = round(100.0 + draw(st.floats(min_value=-2, max_value=2)), 2)
    risk = draw(st.floats(min_value=0.2, max_value=3.0))
    reward = draw(st.floats(min_value=0.2, max_value=6.0))
    placed = bars[draw(st.integers(min_value=0, max_value=n - 1))].timestamp
    expires = draw(st.one_of(st.none(), st.integers(min_value=0, max_value=600).map(lambda m: placed + m * MIN)))
    o = SimOrder(order_id="p", setup_id="p", instrument="X", direction=direction,
                 kind=draw(st.sampled_from(["LIMIT", "MARKET"])), entry=entry, stop=entry - sign * risk,
                 target=draw(st.one_of(st.none(), st.just(entry + sign * reward))),
                 placed_at=placed, expires_at=expires)
    return o, bars


def _reaches_stop(o: SimOrder, b: Bar) -> bool:
    return b.low <= o.stop if o.direction == "LONG" else b.high + b.spread >= o.stop


def _reaches_target(o: SimOrder, b: Bar) -> bool:
    if o.target is None:
        return False
    return b.high >= o.target if o.direction == "LONG" else b.low + b.spread <= o.target


@settings(max_examples=200, deadline=None)
@given(scenario())
def test_property_4_no_fill_before_placement_or_after_expiry(case):
    o, bars = case
    for b in bars:
        before = copy.deepcopy(o)
        FM.step(o, b)
        if b.timestamp < o.placed_at:
            assert o == before
    if o.filled_at is not None:
        assert o.filled_at >= o.placed_at
        assert o.expires_at is None or o.filled_at < o.expires_at


@settings(max_examples=200, deadline=None)
@given(scenario())
def test_property_5_fills_never_better_than_the_orders_levels(case):
    o, bars = case
    exit_bar = None
    for b in bars:
        FM.step(o, b)
        if o.status == "CLOSED" and exit_bar is None and o.closed_at == b.timestamp:
            exit_bar = b
    sign = 1 if o.direction == "LONG" else -1
    if o.fill is not None and o.kind == "LIMIT":
        assert sign * (o.fill - o.entry) <= 1e-9
    if o.exit_reason == "SL":
        assert sign * (o.exit - o.stop) <= 1e-9
    if o.exit_reason in ("SL", "TP") and _reaches_stop(o, exit_bar) and _reaches_target(o, exit_bar):
        assert o.exit_reason == "SL"


@settings(max_examples=200, deadline=None)
@given(scenario())
def test_property_7_loss_bounded_by_stop_unless_gapped(case):
    o, bars = case
    for b in bars:
        FM.step(o, b)
        if o.status == "CLOSED":
            break
    if o.exit_reason != "SL":
        return
    stop_bar = b
    opened_beyond = (stop_bar.open < o.stop) if o.direction == "LONG" else (stop_bar.open + stop_bar.spread > o.stop)
    if o.filled_at != stop_bar.timestamp and opened_beyond:
        return  # a gap: the only way to lose more than the planned risk
    sign = 1 if o.direction == "LONG" else -1
    risk = abs(o.ideal_fill - o.stop)
    gross_r = sign * (o.ideal_exit - o.ideal_fill) / risk
    assert gross_r >= -1 - 1e-9
