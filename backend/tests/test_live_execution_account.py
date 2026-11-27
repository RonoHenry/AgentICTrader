"""The live account the risk engine sees (live-execution Requirement 4; task 457).

LiveAccount is SimAccount with its balance and equity read from the terminal:
the same daily and weekly anchors, the same budget rule, persisted so a
restart keeps them.

Validates: Requirements 4.1-4.4 (.kiro/specs/live-execution/requirements.md)
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import fakeredis
import pytest

from algo_backtester.account import LiveAccount, SimAccount
from services.risk_engine.main import RiskEngine, ValidateRequest

UTC = timezone.utc
# Wednesday 30 Sep 2026, 13:00 UTC (09:00 New York); the D1 period ends at 17:00 New York = 21:00 UTC.
T0 = datetime(2026, 9, 30, 13, 0, tzinfo=UTC)
DAY_CLOSE = datetime(2026, 9, 30, 21, 0, tzinfo=UTC)


class TestTheBudget:
    def test_fixed_at_the_first_balance_without_compounding(self):
        account = LiveAccount(risk_per_trade=0.01)
        account.sync(T0, balance=8_000.0, equity=8_000.0, open_trades=0)
        assert account.risk_amount == 80.0
        account.sync(T0 + timedelta(hours=1), balance=7_000.0, equity=7_000.0, open_trades=0)
        assert account.risk_amount == 80.0
        assert account.exposure()["equity"] == pytest.approx(8_000.0)   # whose 1% is the budget

    def test_follows_the_balance_with_compounding(self):
        account = LiveAccount(risk_per_trade=0.01, compounding=True)
        account.sync(T0, balance=8_000.0, equity=8_000.0, open_trades=0)
        account.sync(T0 + timedelta(hours=1), balance=9_000.0, equity=9_000.0, open_trades=0)
        assert account.risk_amount == 90.0

    def test_open_trades_from_the_broker(self):
        account = LiveAccount(risk_per_trade=0.01)
        account.sync(T0, balance=8_000.0, equity=8_000.0, open_trades=2)
        assert account.exposure()["open_trades"] == 2


class TestTheAnchorsAreSimAccounts:
    MARKS = [   # (t, balance, equity): a loss inside the day, a new day, a loss on it
        (T0, 10_000.0, 10_000.0),
        (T0 + timedelta(hours=2), 10_000.0, 9_700.0),     # open loss: 3% down on the day
        (DAY_CLOSE, 9_750.0, 9_750.0),                    # the bar closing at 17:00 New York ends the day
        (DAY_CLOSE + timedelta(minutes=1), 9_750.0, 9_750.0),
        (DAY_CLOSE + timedelta(hours=3), 9_500.0, 9_400.0),
    ]

    def test_daily_and_weekly_drawdown_match_simaccount(self):
        live = LiveAccount(risk_per_trade=0.01)
        sim = SimAccount(10_000.0, 0.01)
        for t, balance, equity in self.MARKS:
            live.sync(t, balance, equity, open_trades=0)
            sim.equity = balance
            sim.mark(t, equity - balance, 0)
            assert live.daily_dd_pct == pytest.approx(sim.daily_dd_pct)
            assert live.weekly_dd_pct == pytest.approx(sim.weekly_dd_pct)
        assert live.daily_dd_pct == pytest.approx((9_750.0 - 9_400.0) / 9_750.0 * 100)   # from the new day's anchor
        assert live.weekly_dd_pct == pytest.approx(6.0)

    def test_the_drawdown_limit_stops_new_orders(self):
        live = LiveAccount(risk_per_trade=0.01)
        live.sync(T0, 10_000.0, 10_000.0, 0)
        live.sync(T0 + timedelta(hours=1), 10_000.0, 9_690.0, 1)   # 3.1% down on the day
        redis = fakeredis.FakeRedis(decode_responses=True)
        redis.set("risk:exposure:u", json.dumps(live.exposure()))
        response = RiskEngine(redis).validate(ValidateRequest(user_id="u", instrument="EURUSD", confidence=0.9,
                                                              sl_distance_pips=10.0))
        assert not response.approved and "daily drawdown" in response.reason


class TestPersistence:
    def test_a_restart_keeps_the_first_balance_and_the_anchors(self, tmp_path):
        path = tmp_path / "account.json"
        first = LiveAccount(risk_per_trade=0.01, state_path=path)
        first.sync(T0, 10_000.0, 10_000.0, 0)
        first.sync(T0 + timedelta(hours=1), 10_000.0, 9_800.0, 1)

        again = LiveAccount(risk_per_trade=0.01, state_path=path)
        again.sync(T0 + timedelta(hours=2), 10_000.0, 9_800.0, 1)
        assert again.risk_amount == 100.0
        assert again.daily_dd_pct == pytest.approx(2.0)
        assert not list(tmp_path.glob("*.tmp"))


# ── the runner writes it before every decision (Requirement 4.1) ───────────

class TestTheRunnerWritesTheExposure:
    def test_from_the_terminal_and_the_ledger(self):
        import scripts.run_live_agent as runner

        broker = MagicMock()
        broker.account_snapshot.return_value = (10_000.0, 9_650.0)
        broker.active_count.return_value = 2
        redis = fakeredis.FakeRedis(decode_responses=True)
        account = LiveAccount(risk_per_trade=0.01)
        refresh = runner._mt5_exposure(broker, account, redis, clock=lambda: T0)
        refresh()
        exposure = json.loads(redis.get(f"risk:exposure:{runner._USER_ID}"))
        assert exposure["open_trades"] == 2 and exposure["equity"] == pytest.approx(10_000.0)
        broker.account_snapshot.return_value = (10_000.0, 9_600.0)
        refresh()
        assert json.loads(redis.get(f"risk:exposure:{runner._USER_ID}"))["daily_dd_pct"] == pytest.approx(4.0)

    def test_before_the_graph_runs(self, monkeypatch):
        import scripts.run_live_agent as runner

        order = []
        intent = SimpleNamespace(
            setup_id="s1", grade=SimpleNamespace(value="A"), direction="LONG", entry=1.1, stop_loss=1.09,
            take_profit_1=1.12, take_profit_2=None, r_ratio=2.0,
            time_features=SimpleNamespace(time_window="NY_AM", is_killzone=True),
            to_message=lambda mode, detected_at=None: {"setup_id": "s1"})
        monkeypatch.setattr(runner, "LiquidityMappingEngine", lambda *a: SimpleNamespace(
            analyze=lambda *a: SimpleNamespace(to_agent_context=lambda: "")))
        monkeypatch.setattr(runner, "build_order_intent", lambda *a, **k: intent)
        graph = SimpleNamespace(run=lambda message: order.append("graph") or SimpleNamespace(
            decision=None, decision_reason="", error=None, trade_id="t1"))
        runner._process_instrument("EURUSD", {}, T0, graph, MagicMock(), "AUTONOMOUS", verbose=False,
                                   before_decision=lambda: order.append("exposure"))
        assert order == ["exposure", "graph"]


class TestTheAdaptersSnapshot:
    def test_balance_and_equity_from_account_info(self):
        from agent.brokers.mt5 import MT5BrokerAdapter

        with patch("agent.brokers.mt5.mt5") as mt5:
            mt5.initialize.return_value = True
            mt5.account_info.return_value = SimpleNamespace(balance=10_000.0, equity=9_900.0)
            assert MT5BrokerAdapter(login=1, password="x", server="Demo").account_snapshot() == (10_000.0, 9_900.0)

    def test_no_account_info_is_an_error(self):
        from agent.brokers.mt5 import MT5BrokerAdapter, MT5BrokerError

        with patch("agent.brokers.mt5.mt5") as mt5:
            mt5.initialize.return_value = True
            mt5.account_info.return_value = None
            mt5.last_error.return_value = (-1, "no connection")
            with pytest.raises(MT5BrokerError):
                MT5BrokerAdapter(login=1, password="x", server="Demo").account_snapshot()
