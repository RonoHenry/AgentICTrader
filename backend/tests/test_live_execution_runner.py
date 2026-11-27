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
