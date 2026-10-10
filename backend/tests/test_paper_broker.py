"""Tests for agent.brokers.paper — simulated fills against live candles.

Since AlgoBacktester task 195 the paper broker fills through the shared
agent/brokers/fill_model.py (L4, D4). Assertions whose meaning changed on
purpose are marked "D4: stricter fill model".
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from agent.brokers import paper as paper_module
from agent.brokers.factory import BROKER_REGISTRY, create_broker_client
from agent.brokers.paper import PaperBrokerAdapter, PaperBrokerError
from agent.instruments import CommissionSpec, InstrumentSpec, InstrumentSpecs
from agent.strategy_config import PendingExpiry

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
        assert result["pending"] is False  # a market order, not a resting limit
        # D4: stricter fill model. A market order fills at the next bar's open,
        # not instantly at the last close.
        assert broker.active_trade("BTCUSDT")["status"] == "PENDING"
        broker.update("BTCUSDT", [bar(0, 100.6, 100.1, open_=100.2)])
        trade = broker.active_trade("BTCUSDT")
        assert trade["status"] == "OPEN" and trade["fill_price"] == 100.2

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



# ── on the shared FillModel (AlgoBacktester task 195, L4, D4) ───────────────

SPEC = InstrumentSpec(
    symbol="BTCUSDT", venue="binance", point=0.01, tick_size=0.01, contract_size=1.0,
    volume_min=0.00001, volume_step=0.00001, volume_max=9000.0, base_ccy="BTC", quote_ccy="USDT",
    default_spread=0.1, stop_slippage=0.05, commission=CommissionSpec("RATE_PER_SIDE", 0.001),
)
SPECS = InstrumentSpecs(venue="binance", account_ccy="USDT", specs={"BTCUSDT": SPEC})


def spread_bar(minute: int, high: float, low: float, open_: float, spread=None):
    b = bar(minute, high, low, open_=open_)
    if spread is not None:
        b.spread = spread
    return b


class TestFillModel:
    def test_paper_broker_uses_fill_model(self):
        broker = _broker(specs=SPECS)
        _long(broker)  # limit 98, stop 97, target 103; spread 0.1
        assert broker.update("BTCUSDT", [bar(1, 100, 97.9)]) == []  # ask low 98.0: a touch, not a fill
        assert [e["event"] for e in broker.update("BTCUSDT", [bar(2, 100, 97.85)])] == ["FILLED"]
        trade = broker.active_trade("BTCUSDT")
        assert trade["fill_price"] == 98.0 and trade["ideal_fill"] == pytest.approx(97.9)

        # A market order fills at the next bar's open, at the ask.
        market = _broker(specs=SPECS)
        market.place_order({"instrument": "BTCUSDT", "direction": "LONG", "entry": 100.5, "stop_loss": 99.0})
        market.update("BTCUSDT", [bar(0, 100.6, 100.1, open_=100.2)])
        assert market.active_trade("BTCUSDT")["fill_price"] == pytest.approx(100.3)

    def test_stop_exit_pays_slippage_and_spread_in_net_r(self):
        broker = _broker(specs=SPECS)
        _long(broker)
        broker.update("BTCUSDT", [bar(1, 100, 97.85), bar(2, 98.5, 96.9)])
        trade = broker.trades()[0]
        assert (trade["exit_reason"], trade["exit_price"]) == ("SL", pytest.approx(96.95))
        risk = 97.9 - 97.0  # measured on the chart (bid): ideal fill to stop
        assert trade["gross_r"] == pytest.approx(-1.0, abs=1e-3)
        assert trade["net_r"] == pytest.approx((96.95 - 98.0) / risk, abs=1e-3)

    def test_injected_clock_sets_placed_at(self):
        placed = datetime(2026, 10, 3, 18, 30, tzinfo=timezone.utc)
        broker = PaperBrokerAdapter(clock=lambda: placed)
        broker.update("BTCUSDT", [bar(-1, 101, 99, close=100)])
        _long(broker)
        assert broker.active_trade("BTCUSDT")["placed_at"] == placed.isoformat()

    def test_expiry_follows_the_strategy_rule(self):
        # 12:00 UTC on 2026-10-03 is 08:00 New York: inside the NY AM killzone, which ends at 10:00 (14:00 UTC).
        broker = _broker(expiry_rule=PendingExpiry.KILLZONE_END)
        _long(broker)
        assert broker.active_trade("BTCUSDT")["expires_at"] == datetime(2026, 10, 3, 14, 0, tzinfo=timezone.utc).isoformat()

    def test_bar_spread_is_max_of_recorded_and_typical(self):
        # Typical (spec) spread 0.1. A limit at 98 fills when the ask low is below 98.
        recorded_wider = _broker(specs=SPECS)
        _long(recorded_wider)
        assert recorded_wider.update("BTCUSDT", [spread_bar(1, 100, 97.85, 99, spread=0.3)]) == []  # ask low 98.15

        recorded_narrower = _broker(specs=SPECS)
        _long(recorded_narrower)
        assert recorded_narrower.update("BTCUSDT", [spread_bar(1, 100, 97.85, 99, spread=0.01)]) != []  # 0.1 applies

        binance_kline = _broker(specs=SPECS)  # klines carry no spread at all
        _long(binance_kline)
        assert binance_kline.update("BTCUSDT", [bar(1, 100, 97.9)]) == []  # ask low 98.0 with the typical 0.1

    def test_fee_rate_maps_to_rate_per_side_commission(self):
        broker = _broker(fee_rate=0.001)
        assert broker.commission == CommissionSpec("RATE_PER_SIDE", 0.001)
        assert _broker().commission == CommissionSpec("RATE_PER_SIDE", 0.0)

    def test_each_bar_processed_once(self):
        # update() takes closed bars and remembers how far it got, so feeding
        # overlapping windows (the runner refetches each pass) never re-steps a bar.
        broker = _broker()
        _long(broker)
        window = [bar(1, 100, 97.9), bar(2, 101, 99)]
        assert [e["event"] for e in broker.update("BTCUSDT", window)] == ["FILLED"]
        assert broker.update("BTCUSDT", window) == []
        assert broker.active_trade("BTCUSDT")["processed_through"] == window[-1].timestamp.isoformat()

    def test_state_file_from_previous_version_still_loads(self, tmp_path):
        # The format the running forward test wrote before task 195.
        old = {
            "trade_id": "paper-old", "setup_id": "s0", "instrument": "BTCUSDT", "direction": "LONG",
            "entry": 98.0, "requested_entry": 98.0, "stop_loss": 97.0, "take_profit": 103.0, "size": 1.0,
            "risk_amount": None, "status": "OPEN", "placed_at": (T0 - timedelta(hours=1)).isoformat(),
            "expires_at": None, "filled_at": (T0 - timedelta(minutes=50)).isoformat(), "fill_price": 98.0,
            "fill_bar": (T0 - timedelta(minutes=50)).isoformat(), "closed_at": None, "exit_price": None,
            "exit_reason": None, "remaining_ratio": 1.0, "partials": [], "gross_r": None, "net_r": None,
        }
        expired = {**old, "trade_id": "paper-exp", "instrument": "ETHUSDT", "status": "CLOSED", "exit_reason": "EXPIRED",
                   "fill_price": None, "filled_at": None, "closed_at": T0.isoformat()}
        path = tmp_path / "paper.json"
        path.write_text(json.dumps([old, expired]), encoding="utf-8")

        broker = PaperBrokerAdapter(state_path=path)

        assert "2 orders" in broker.report()
        assert [e["event"] for e in broker.update("BTCUSDT", [bar(1, 103.5, 99)])] == ["TP"]
        resumed = next(t for t in broker.trades() if t["trade_id"] == "paper-old")
        assert resumed["gross_r"] == pytest.approx(5.0)
