"""
Tests for algo_backtester/account.py — the simulated account.

Task 202 (.kiro/specs/algo-backtester/tasks.md). SimAccount tracks equity,
open positions marked at the bar close, and daily and weekly drawdown from
anchors reset at 17:00 New York (the strategy calendar's D1 and W1 periods).
Its exposure dict is what RiskEngine.validate() reads, as live.
Validates: Requirements 1.4, 6.3, 6.4 (.kiro/specs/algo-backtester/requirements.md)
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import fakeredis
import pytest

from agent.brokers.fill_model import Bar
from agent.instruments import CommissionSpec, InstrumentSpec, InstrumentSpecs
from agent.strategy_config import PendingExpiry
from algo_backtester.account import SimAccount
from algo_backtester.sim_broker import ClosedTrade, SimBroker
from services.risk_engine.main import RiskEngine, ValidateRequest

UTC = timezone.utc
MIN = timedelta(minutes=1)


def closed(pnl: float, at: datetime) -> ClosedTrade:
    return ClosedTrade(
        order_id="sim-000001", setup_id="s", instrument="EURUSD", direction="LONG", kind="LIMIT", entry=1.1,
        stop=1.099, target=1.105, lots=1.0, risk_amount=100.0, placed_at=at - MIN, expires_at=None,
        filled_at=at - MIN, closed_at=at, exit_reason="SL" if pnl < 0 else "TP", ideal_fill=1.0999, fill=1.1,
        ideal_exit=1.099, exit=1.099, initial_risk=0.001, gross_r=pnl / 100, net_r=pnl / 100, cost_r_spread=0.0,
        cost_r_slippage=0.0, cost_r_commission=0.0, mae_r=-1.0, mfe_r=0.0, pnl=pnl, cost_flag=False,
    )


# ── drawdown anchors ───────────────────────────────────────────────────────

@pytest.mark.parametrize("day_close_utc", [
    datetime(2026, 1, 14, 22, 0, tzinfo=UTC),   # winter: 17:00 New York is 22:00 UTC
    datetime(2026, 7, 15, 21, 0, tzinfo=UTC),   # summer: 17:00 New York is 21:00 UTC
])
def test_daily_anchor_resets_17_00_new_york_winter_and_summer(day_close_utc):
    account = SimAccount(initial_equity=10_000.0, risk_per_trade=0.01)
    account.mark(day_close_utc - timedelta(hours=2), open_pnl=-200.0, open_trades=1)
    assert account.daily_dd_pct == pytest.approx(2.0)
    account.mark(day_close_utc - timedelta(minutes=30), open_pnl=-200.0, open_trades=1)   # an hour off by DST
    account.mark(day_close_utc, open_pnl=-200.0, open_trades=1)        # the bar closing at 17:00 ends the day
    assert account.daily_dd_pct == pytest.approx(2.0)

    account.mark(day_close_utc + MIN, open_pnl=-200.0, open_trades=1)  # a new day, anchored on 9,800
    assert account.daily_dd_pct == 0.0
    account.mark(day_close_utc + 30 * MIN, open_pnl=-300.0, open_trades=1)
    assert account.daily_dd_pct == pytest.approx(100 / 9_800 * 100)
    assert account.weekly_dd_pct == pytest.approx(3.0)                 # the week carries on


def test_weekly_anchor_resets_sunday_open():
    account = SimAccount(initial_equity=10_000.0, risk_per_trade=0.01)
    tuesday = datetime(2026, 9, 29, 14, 0, tzinfo=UTC)
    account.book(closed(-200.0, tuesday))
    account.mark(tuesday, open_pnl=0.0, open_trades=0)
    account.mark(tuesday + timedelta(days=1), open_pnl=0.0, open_trades=0)          # Wednesday: a new day
    assert (account.daily_dd_pct, account.weekly_dd_pct) == (0.0, pytest.approx(2.0))

    friday = datetime(2026, 10, 2, 19, 0, tzinfo=UTC)                               # 15:00 New York
    account.book(closed(-200.0, friday))
    account.mark(friday, open_pnl=0.0, open_trades=0)
    assert account.weekly_dd_pct == pytest.approx(4.0)

    sunday_open = datetime(2026, 10, 4, 21, 5, tzinfo=UTC)                          # Sunday 17:05 New York
    account.mark(sunday_open, open_pnl=0.0, open_trades=0)
    assert (account.daily_dd_pct, account.weekly_dd_pct) == (0.0, 0.0)
    account.book(closed(-96.0, sunday_open + MIN))
    account.mark(sunday_open + MIN, open_pnl=0.0, open_trades=0)
    assert account.weekly_dd_pct == pytest.approx(96 / 9_600 * 100)                 # anchored on 9,600


def test_drawdown_includes_open_positions_marked_to_close():
    specs = InstrumentSpecs("mt5", "USD", {"EURUSD": InstrumentSpec(
        symbol="EURUSD", venue="mt5", point=1e-5, tick_size=1e-5, contract_size=100_000.0, volume_min=0.01,
        volume_step=0.01, volume_max=100.0, base_ccy="EUR", quote_ccy="USD", default_spread=0.0001,
        stop_slippage=0.00002, commission=CommissionSpec("PER_LOT_PER_SIDE", 0.0))})
    t = datetime(2026, 9, 30, 13, 0, tzinfo=UTC)
    broker = SimBroker(specs, clock=lambda: t, expiry_rule=PendingExpiry.KILLZONE_END, fallback_ttl=timedelta(hours=3))
    broker.advance("EURUSD", Bar(t - MIN, 1.1000, 1.1000, 1.1000, 1.1000, 0.0001))
    broker.place_order({"instrument": "EURUSD", "direction": "LONG", "entry": 1.1001, "stop_loss": 1.0981,
                        "take_profit": 1.1100, "risk_amount": 200.0})       # 1 lot at market
    broker.advance("EURUSD", Bar(t, 1.1000, 1.1002, 1.0985, 1.0986, 0.0001))  # fills at the ask 1.1001

    account = SimAccount(initial_equity=10_000.0, risk_per_trade=0.01)
    account.mark(t + MIN, open_pnl=broker.open_pnl(), open_trades=broker.active_count())
    # marked at the close on the closing side: the bid 1.0986, 15 pips below the fill
    assert broker.open_pnl() == pytest.approx(-150.0)
    assert account.equity == 10_000.0 and account.equity_mark == pytest.approx(9_850.0)
    assert account.daily_dd_pct == pytest.approx(1.5) and account.exposure()["open_trades"] == 1

    account.mark(t + 2 * MIN, open_pnl=100.0, open_trades=1)
    assert account.daily_dd_pct == 0.0 and account.weekly_dd_pct == 0.0            # never negative


# ── what RiskEngine reads ──────────────────────────────────────────────────

def _validate(account: SimAccount):
    redis = fakeredis.FakeRedis(decode_responses=True)
    redis.set("risk:exposure:default", json.dumps(account.exposure()))
    request = ValidateRequest(user_id="default", instrument="EURUSD", confidence=0.8, sl_distance_pips=10.0)
    return RiskEngine(redis).validate(request)


@pytest.mark.parametrize("loss, approved", [(290.0, True), (300.0, False)])
def test_exposure_dict_drives_risk_engine_daily_limit(loss, approved):
    t = datetime(2026, 9, 30, 13, 0, tzinfo=UTC)
    account = SimAccount(initial_equity=10_000.0, risk_per_trade=0.01)
    account.book(closed(-loss, t))
    account.mark(t, open_pnl=0.0, open_trades=0)
    response = _validate(account)
    assert response.approved is approved
    if not approved:
        assert "daily drawdown 3.00%" in response.reason


def test_non_compounding_risk_amount_fixed():
    t = datetime(2026, 9, 30, 13, 0, tzinfo=UTC)
    flat = SimAccount(initial_equity=10_000.0, risk_per_trade=0.01)
    compounding = SimAccount(initial_equity=10_000.0, risk_per_trade=0.01, compounding=True)
    for account in (flat, compounding):
        account.book(closed(+500.0, t))
        account.book(closed(-100.0, t + MIN))
        account.mark(t + MIN, open_pnl=0.0, open_trades=0)

    assert flat.equity == 10_400.0 and flat.risk_amount == 100.0
    assert _validate(flat).risk_amount == pytest.approx(100.0)          # RiskEngine sizes on the fixed budget
    assert compounding.risk_amount == pytest.approx(104.0)
    assert _validate(compounding).risk_amount == pytest.approx(104.0)


def test_risk_per_trade_reaches_risk_engine():
    # RiskEngine sizes at a fixed 1% of the equity it reads; the account's own risk_per_trade must still apply
    account = SimAccount(initial_equity=10_000.0, risk_per_trade=0.02)
    account.mark(datetime(2026, 9, 30, 13, 0, tzinfo=UTC), open_pnl=0.0, open_trades=0)
    assert _validate(account).risk_amount == pytest.approx(200.0)
