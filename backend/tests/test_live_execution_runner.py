"""The live runner on MT5 (live-execution Requirements 4-6; tasks 455, 457, 458).

The runner trades the backtested configuration: with ``--config`` it reads and
orders through the run's broker profile (symbols, server clock, specs).
These tests never touch a terminal: the credentials are stubbed and the
adapter connects only on first use.

Validates: Requirements 6.1, 6.2 (.kiro/specs/live-execution/requirements.md)
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import scripts.run_live_agent as runner
from agent.brokers.mt5 import MT5BrokerAdapter
from algo_backtester.config import load_run_config

REPO_ROOT = Path(__file__).resolve().parents[2]
FAKE_CREDENTIALS = {"login": 1, "password": "x", "server": "Demo"}


@pytest.fixture
def run_cfg():
    return load_run_config(REPO_ROOT / "config" / "backtests" / "focus.toml", "fresh_near_gap_dis")


class TestTheRunsBrokerProfile:
    def test_orders_use_the_profiles_symbols(self, run_cfg):
        with patch.object(runner, "_mt5_credentials", return_value=FAKE_CREDENTIALS):
            broker = runner._mt5_broker_client(run_cfg)
        assert isinstance(broker, MT5BrokerAdapter)
        assert broker._resolve_symbol("EURUSD") == "EURUSDm"
        assert broker._resolve_symbol("US100") == "USTECm"

    def test_the_backstop_gets_the_profiles_specs(self, run_cfg):
        with patch.object(runner, "_mt5_credentials", return_value=FAKE_CREDENTIALS):
            broker = runner._mt5_broker_client(run_cfg)
        assert broker._specs is not None and "XAUUSD" in broker._specs

    def test_without_a_config_the_suffix_still_applies(self, monkeypatch):
        with patch.object(runner, "_mt5_credentials", return_value=FAKE_CREDENTIALS), \
                patch.object(runner, "config", side_effect=lambda name, default=None, **_: {
                    "MT5_SYMBOL_SUFFIX": ".a"}.get(name, default)):
            broker = runner._mt5_broker_client(None)
        assert broker._resolve_symbol("EURUSD") == "EURUSD.a"

    def test_the_profiles_server_clock(self, run_cfg):
        assert runner._server_clock(run_cfg).spec == "+0"   # config/brokers/exness-standard.toml

    def test_without_a_config_the_environment_clock(self):
        with patch.object(runner, "config", side_effect=lambda name, default=None, **_: {
                "MT5_SERVER_TIMEZONE": "+2"}.get(name, default)):
            assert runner._server_clock(None).spec == "+2"


class TestExpiryInTheRunner:
    """Requirement 3 (task 456): the runner hands the adapter the run's expiry and a ledger, and syncs it."""

    def test_the_adapter_gets_the_runs_expiry_and_ledger(self, run_cfg, tmp_path):
        cfg = run_cfg.strategy
        with patch.object(runner, "_mt5_credentials", return_value=FAKE_CREDENTIALS):
            broker = runner._mt5_broker_client(run_cfg, expiry_rule=cfg.pending_expiry, fallback_ttl=cfg.fallback_ttl,
                                               server_clock=runner._server_clock(run_cfg),
                                               ledger_path=tmp_path / "ledger.json")
        assert broker._expiry_rule == cfg.pending_expiry and broker._fallback_ttl == cfg.fallback_ttl
        assert broker._server_clock.spec == "+0"

    def test_manage_syncs_and_prints_each_change(self, capsys):
        broker = MagicMock()
        broker.sync.return_value = [{"instrument": "EURUSD", "event": "EXPIRED", "direction": "LONG",
                                     "kind": "LIMIT", "entry": 1.099, "stop_loss": 1.097, "take_profit": 1.11,
                                     "lots": 0.5, "tickets": [555]}]
        assert [e["event"] for e in runner._manage(broker)] == ["EXPIRED"]
        assert "[EURUSD] MT5 EXPIRED" in capsys.readouterr().out

    def test_manage_logs_a_terminal_error_and_carries_on(self):
        broker = MagicMock()
        broker.sync.side_effect = RuntimeError("terminal gone")
        assert runner._manage(broker) == []


# ── one trade per market, one attempt per setup (task 458) ─────────────────

def _intent(setup_id="EURUSD-M15-ob-1"):
    from types import SimpleNamespace

    return SimpleNamespace(
        setup_id=setup_id, grade=SimpleNamespace(value="A"), direction="LONG", entry=1.1, stop_loss=1.09,
        take_profit_1=1.12, take_profit_2=None, r_ratio=2.0,
        time_features=SimpleNamespace(time_window="NY_AM", is_killzone=True),
        to_message=lambda mode, detected_at=None: {"setup_id": setup_id})


@pytest.fixture
def engine_stub(monkeypatch):
    """The engine grades one setup; the graph records whether it ran."""
    from types import SimpleNamespace

    monkeypatch.setattr(runner, "LiquidityMappingEngine", lambda *a: SimpleNamespace(
        analyze=lambda *a: SimpleNamespace(to_agent_context=lambda: "")))
    monkeypatch.setattr(runner, "build_order_intent", lambda *a, **k: _intent())
    ran = []
    graph = SimpleNamespace(run=lambda message: ran.append(message) or SimpleNamespace(
        decision=None, decision_reason="", error=None, trade_id="t1"))
    return graph, ran


class TestOneTradePerMarket:
    def test_an_active_trade_skips_the_market(self):
        broker = MagicMock()
        broker.active_trade.return_value = {"trade_id": "555", "status": "PENDING"}
        assert runner._skip_in_trade("EURUSD", broker) == {
            "instrument": "EURUSD", "grade": "-", "decision": "IN TRADE (PENDING)", "trade_id": "555"}
        broker.active_trade.assert_called_once_with("EURUSD")

    def test_no_active_trade_no_skip(self):
        broker = MagicMock()
        broker.active_trade.return_value = None
        assert runner._skip_in_trade("EURUSD", broker) is None


class TestOneAttemptPerSetup:
    def test_an_attempted_setup_is_not_ordered_again(self, engine_stub):
        from datetime import datetime, timezone

        graph, ran = engine_stub
        summary = runner._process_instrument("EURUSD", {}, datetime(2026, 9, 30, 13, tzinfo=timezone.utc), graph,
                                             MagicMock(), "AUTONOMOUS", verbose=False,
                                             attempted=lambda: {"EURUSD-M15-ob-1"})
        assert summary["decision"] == "SETUP_ALREADY_ATTEMPTED" and ran == []

    def test_a_new_setup_goes_to_the_graph(self, engine_stub):
        from datetime import datetime, timezone

        graph, ran = engine_stub
        runner._process_instrument("EURUSD", {}, datetime(2026, 9, 30, 13, tzinfo=timezone.utc), graph,
                                   MagicMock(), "AUTONOMOUS", verbose=False, attempted=lambda: {"other"})
        assert len(ran) == 1

    def test_attempted_comes_from_the_paper_trades(self):
        paper = MagicMock()
        paper.trades.return_value = [{"setup_id": "a", "status": "CLOSED"}, {"setup_id": "b", "status": "OPEN"},
                                     {"setup_id": None, "status": "CLOSED"}]
        assert runner._attempted(paper=paper)() == {"a", "b"}

    def test_attempted_comes_from_the_mt5_ledger(self):
        broker = MagicMock()
        broker.attempted_setups.return_value = {"x"}
        assert runner._attempted(mt5_broker=broker)() == {"x"}


class TestPaperExposure:
    def test_open_trades_from_the_paper_trades_before_each_decision(self):
        import json

        import fakeredis

        paper = MagicMock()
        paper.trades.return_value = [{"status": "OPEN"}, {"status": "PENDING"}, {"status": "CLOSED"}]
        redis = fakeredis.FakeRedis(decode_responses=True)
        runner._paper_exposure(paper, redis)()
        exposure = json.loads(redis.get(f"risk:exposure:{runner._USER_ID}"))
        assert exposure["open_trades"] == 2 and exposure["daily_dd_pct"] == 0.0
