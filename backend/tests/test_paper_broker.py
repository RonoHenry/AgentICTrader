"""Tests for agent.brokers.paper — simulated fills against live candles."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from agent.brokers import paper as paper_module
from agent.brokers.factory import BROKER_REGISTRY, create_broker_client
from agent.brokers.paper import PaperBrokerAdapter, PaperBrokerError

T0 = datetime(2026, 10, 3, 12, 0, tzinfo=timezone.utc)


def bar(minute: int, high: float, low: float, close: float | None = None, open_: float | None = None):
    mid = (high + low) / 2
    return SimpleNamespace(
        timestamp=T0 + timedelta(minutes=minute),
        open=open_ if open_ is not None else mid,
        high=high,
        low=low,
        close=close if close is not None else mid,
    )


@pytest.fixture(autouse=True)
def frozen_now(monkeypatch):
    monkeypatch.setattr(paper_module, "_now", lambda: T0)


def _broker(**kwargs) -> PaperBrokerAdapter:
    broker = PaperBrokerAdapter(**kwargs)
    broker.update("BTCUSDT", [bar(-1, 101, 99, close=100)])  # market = 100
    return broker


def _long(broker, entry=98.0, stop=97.0, target=103.0) -> str:
    return broker.place_order(
        {"instrument": "BTCUSDT", "direction": "LONG", "entry": entry, "stop_loss": stop,
         "take_profit": target, "size": 1.0, "setup_id": "s1"}
    )["trade_id"]


class TestPlacement:
    def test_entry_below_market_rests_as_pending_limit(self):
        broker = _broker()
        result = broker.place_order({"instrument": "BTCUSDT", "direction": "LONG", "entry": 98.0, "stop_loss": 97.0})
        assert result["pending"] is True
        assert broker.get_position_status(result["trade_id"])["status"] == "PENDING"

    def test_entry_already_reached_fills_at_market(self):
        broker = _broker()
        result = broker.place_order({"instrument": "BTCUSDT", "direction": "LONG", "entry": 100.5, "stop_loss": 99.0})
        assert result["pending"] is False
        trade = broker.active_trade("BTCUSDT")
        assert trade["status"] == "OPEN" and trade["fill_price"] == 100

    def test_market_fill_with_stop_beyond_price_is_rejected(self):
        broker = _broker()
        with pytest.raises(PaperBrokerError, match="wrong side"):
            broker.place_order({"instrument": "BTCUSDT", "direction": "LONG", "entry": None, "stop_loss": 100.5})

    def test_needs_a_price_first(self):
        with pytest.raises(PaperBrokerError, match="update"):
            PaperBrokerAdapter().place_order({"instrument": "ETHUSDT", "direction": "LONG", "stop_loss": 1})

    def test_registered_in_factory(self):
        assert BROKER_REGISTRY["paper"] is PaperBrokerAdapter
        assert isinstance(create_broker_client("paper"), PaperBrokerAdapter)


class TestSimulation:
    def test_limit_fill_then_target_scores_positive_r(self):
        broker = _broker()
        trade_id = _long(broker)
        events = broker.update("BTCUSDT", [bar(1, 100, 97.9), bar(2, 103.5, 99)])
        assert [e["event"] for e in events] == ["FILLED", "TP"]
        trade = broker.trades()[0]
        assert trade["trade_id"] == trade_id
        assert trade["gross_r"] == pytest.approx(5.0)

    def test_stop_and_target_in_one_bar_counts_as_stop(self):
        broker = _broker()
        _long(broker)
        broker.update("BTCUSDT", [bar(1, 100, 97.9)])
        events = broker.update("BTCUSDT", [bar(1, 100, 97.9), bar(2, 104, 96)])
        assert events[-1]["event"] == "SL"
        assert broker.trades()[0]["gross_r"] == pytest.approx(-1.0)

    def test_fill_bar_can_stop_out(self):
        broker = _broker()
        _long(broker)
        events = broker.update("BTCUSDT", [bar(1, 100, 96.5)])
        assert events[0]["event"] == "FILLED+SL"
        assert broker.trades()[0]["gross_r"] == pytest.approx(-1.0)

    def test_fill_bar_never_takes_profit_even_when_rescanned(self):
        broker = _broker()
        _long(broker)
        fill_bar = bar(1, 104, 97.5)  # touches entry and target, not stop
        assert [e["event"] for e in broker.update("BTCUSDT", [fill_bar])] == ["FILLED"]
        assert broker.update("BTCUSDT", [fill_bar]) == []
        assert broker.active_trade("BTCUSDT")["status"] == "OPEN"

    def test_bars_before_placement_are_ignored(self):
        broker = _broker()
        _long(broker)
        assert broker.update("BTCUSDT", [bar(-5, 100, 90)]) == []
        assert broker.active_trade("BTCUSDT")["status"] == "PENDING"

    def test_unfilled_order_expires(self):
        closed = []
        broker = _broker(pending_ttl=timedelta(minutes=30), on_close=closed.append)
        _long(broker)
        events = broker.update("BTCUSDT", [bar(10, 101, 99), bar(31, 101, 99)])
        assert events[0]["event"] == "EXPIRED"
        assert closed and closed[0]["gross_r"] is None

    def test_fees_reduce_net_r(self):
        broker = _broker(fee_rate=0.001)
        _long(broker)
        broker.update("BTCUSDT", [bar(1, 100, 97.9), bar(2, 103.5, 99)])
        trade = broker.trades()[0]
        # 0.1% of (98 entry + 103 exit) = 0.201, over 1.0 of risk.
        assert trade["net_r"] == pytest.approx(5.0 - 0.201)

    def test_on_close_fires_once_per_trade(self):
        closed = []
        broker = _broker(on_close=closed.append)
        _long(broker)
        broker.update("BTCUSDT", [bar(1, 100, 97.9), bar(2, 103.5, 99)])
        broker.update("BTCUSDT", [bar(1, 100, 97.9), bar(2, 103.5, 99), bar(3, 105, 100)])
        assert len(closed) == 1


class TestBrokerClientMethods:
    def test_close_pending_cancels(self):
        broker = _broker()
        trade_id = _long(broker)
        assert broker.close_position(trade_id)
        assert broker.trades()[0]["exit_reason"] == "CANCELLED"

    def test_partial_close_then_target_blends_r(self):
        broker = _broker()
        trade_id = _long(broker)
        broker.update("BTCUSDT", [bar(1, 100, 97.9)])
        broker.update("BTCUSDT", [bar(1, 100, 97.9), bar(2, 99.5, 98.5, close=99.0)])  # +1R
        broker.partial_close(trade_id, ratio=0.5)
        broker.update("BTCUSDT", [bar(3, 103.5, 99)])
        assert broker.trades()[0]["gross_r"] == pytest.approx(0.5 * 1.0 + 0.5 * 5.0)

    def test_partial_close_of_pending_raises(self):
        broker = _broker()
        with pytest.raises(PaperBrokerError, match="pending"):
            broker.partial_close(_long(broker))


class TestPersistence:
    def test_trades_survive_a_restart(self, tmp_path):
        path = tmp_path / "paper.json"
        broker = _broker(state_path=path)
        trade_id = _long(broker)

        reloaded = PaperBrokerAdapter(state_path=path)
        assert reloaded.active_trade("BTCUSDT")["trade_id"] == trade_id

    def test_save_is_atomic_and_leaves_no_temp_file(self, tmp_path):
        path = tmp_path / "paper.json"
        broker = _broker(state_path=path)
        _long(broker)
        assert path.exists()
        assert not (tmp_path / "paper.json.tmp").exists()

    def test_report_totals(self):
        broker = _broker()
        _long(broker)
        broker.update("BTCUSDT", [bar(1, 100, 97.9), bar(2, 103.5, 99)])
        report = broker.report()
        assert "1 filled & closed (1 won)" in report
        assert "+5.00R gross" in report
