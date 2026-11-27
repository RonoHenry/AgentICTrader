"""The MT5 adapter's live-execution behaviour (tasks 455, 456, 459).

The profile's symbols, expiry, the ledger, the split and sync, on the patched
``mt5`` module (as test_mt5_broker_adapter.py patches it): nothing here
touches a terminal.

Validates: Requirements 3, 6.1, 7 (.kiro/specs/live-execution/requirements.md)
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from agent.brokers.mt5 import MT5BrokerAdapter, MT5BrokerError
from agent.strategy_config import PendingExpiry
from services.market_data.mt5_clock import MT5ServerClock

CREDENTIALS = dict(login=1, password="x", server="Demo")


@pytest.fixture
def mock_mt5():
    with patch("agent.brokers.mt5.mt5") as mock:
        mock.initialize.return_value = True
        mock.TRADE_RETCODE_DONE = 10009
        mock.ORDER_TYPE_BUY, mock.ORDER_TYPE_SELL = 0, 1
        mock.ORDER_TYPE_BUY_LIMIT, mock.ORDER_TYPE_SELL_LIMIT = 2, 3
        mock.TRADE_ACTION_DEAL, mock.TRADE_ACTION_SLTP, mock.TRADE_ACTION_PENDING, mock.TRADE_ACTION_REMOVE = 1, 2, 5, 8
        mock.ORDER_TIME_GTC, mock.ORDER_TIME_SPECIFIED = 0, 2
        mock.ORDER_FILLING_IOC, mock.ORDER_FILLING_RETURN = 1, 2
        mock.symbol_info.return_value = MagicMock(
            filling_mode=2, volume_step=0.01, volume_min=0.01, volume_max=100.0,
            trade_tick_size=0.00001, trade_tick_value=1.0, expiration_mode=1 | 4,
        )
        mock.symbol_info_tick.return_value = MagicMock(ask=1.1001, bid=1.1000)
        mock.order_send.return_value = MagicMock(retcode=10009, order=555)
        mock.orders_get.return_value = ()
        mock.positions_get.return_value = ()
        yield mock


class TestTheProfilesSymbols:
    def test_a_symbol_map_names_the_broker_symbol(self, mock_mt5):
        adapter = MT5BrokerAdapter(**CREDENTIALS, symbol_of={"EURUSD": "EURUSDm"}.get)
        adapter.place_order({"instrument": "EURUSD", "direction": "LONG", "size": 0.01})
        assert mock_mt5.order_send.call_args[0][0]["symbol"] == "EURUSDm"
        mock_mt5.symbol_info_tick.assert_called_with("EURUSDm")


# ── expiry and the ledger (task 456) ───────────────────────────────────────

T0 = datetime(2026, 9, 30, 13, 0, tzinfo=timezone.utc)        # 09:00 New York: in the NY AM killzone
KILLZONE_END = datetime(2026, 9, 30, 14, 0, tzinfo=timezone.utc)   # 10:00 New York


class Clock:
    def __init__(self, now: datetime = T0) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


def _limit(**overrides) -> dict:
    """A LONG resting below the ask (1.1001), sized $100 over a 20-pip stop."""
    return {"instrument": "EURUSD", "direction": "LONG", "entry": 1.0990, "stop_loss": 1.0970,
            "take_profit": 1.1100, "risk_amount": 100.0, "setup_id": "setup-1", **overrides}


def _adapter(clock: Clock, tmp_path=None, **kwargs) -> MT5BrokerAdapter:
    return MT5BrokerAdapter(**CREDENTIALS, clock=clock, expiry_rule=PendingExpiry.KILLZONE_END,
                            fallback_ttl=timedelta(hours=3),
                            ledger_path=(tmp_path / "ledger.json") if tmp_path is not None else None, **kwargs)


def _tickets(pending=(), open_=()):
    """orders_get / positions_get answering by ticket."""
    def orders_get(ticket=None, **_):
        return tuple(MagicMock(ticket=t, type=2, symbol="EURUSD") for t in pending if t == ticket)

    def positions_get(ticket=None, **_):
        return tuple(MagicMock(ticket=t, type=0, symbol="EURUSD", price_open=1.0990, volume=0.5, profit=0.0,
                               sl=1.0970, tp=1.1100) for t in open_ if t == ticket)
    return orders_get, positions_get


class TestExpiryIsSent:
    def test_specified_in_server_time_when_the_symbol_allows_it(self, mock_mt5):
        adapter = _adapter(Clock(), server_clock=MT5ServerClock("+2"))
        adapter.place_order(_limit())
        request = mock_mt5.order_send.call_args[0][0]
        assert request["type_time"] == mock_mt5.ORDER_TIME_SPECIFIED
        assert request["expiration"] == int(MT5ServerClock("+2").to_server(KILLZONE_END).timestamp())

    def test_gtc_when_the_symbol_allows_only_gtc(self, mock_mt5):
        mock_mt5.symbol_info.return_value.expiration_mode = 1
        adapter = _adapter(Clock(), server_clock=MT5ServerClock("+2"))
        adapter.place_order(_limit())
        request = mock_mt5.order_send.call_args[0][0]
        assert request["type_time"] == mock_mt5.ORDER_TIME_GTC and "expiration" not in request
        assert adapter.active_trade("EURUSD")["expires_at"] == KILLZONE_END.isoformat()

    def test_gtc_without_a_server_clock(self, mock_mt5):
        adapter = _adapter(Clock())
        adapter.place_order(_limit())
        assert mock_mt5.order_send.call_args[0][0]["type_time"] == mock_mt5.ORDER_TIME_GTC

    def test_a_market_order_has_no_expiry(self, mock_mt5):
        adapter = _adapter(Clock(), server_clock=MT5ServerClock("+2"))
        adapter.place_order(_limit(entry=1.1005, stop_loss=1.0985))   # above the ask: market
        request = mock_mt5.order_send.call_args[0][0]
        assert request["type_time"] == mock_mt5.ORDER_TIME_GTC
        assert adapter.active_trade("EURUSD")["expires_at"] is None

    def test_an_order_expiring_at_placement_is_recorded_not_sent(self, mock_mt5):
        adapter = _adapter(Clock(KILLZONE_END), server_clock=MT5ServerClock("+2"))
        result = adapter.place_order(_limit())
        mock_mt5.order_send.assert_not_called()
        assert result["pending"] is True and result["trade_id"]
        assert adapter.active_trade("EURUSD") is None
        assert adapter.attempted_setups() == {"setup-1"}
        assert adapter.get_position_status(result["trade_id"])["status"] == "CLOSED"


class TestSync:
    def test_a_pending_order_past_its_expiry_is_cancelled(self, mock_mt5):
        clock = Clock()
        adapter = _adapter(clock)
        mock_mt5.orders_get.side_effect, mock_mt5.positions_get.side_effect = _tickets(pending=[555])
        adapter.place_order(_limit())
        mock_mt5.order_send.reset_mock()

        clock.now = KILLZONE_END - timedelta(minutes=1)
        assert adapter.sync() == []
        mock_mt5.order_send.assert_not_called()

        clock.now = KILLZONE_END
        events = adapter.sync()
        assert mock_mt5.order_send.call_args[0][0] == {"action": mock_mt5.TRADE_ACTION_REMOVE, "order": 555}
        assert [e["event"] for e in events] == ["EXPIRED"]
        assert adapter.active_trade("EURUSD") is None and adapter.active_count() == 0

    def test_a_fill_is_recorded_and_the_trade_stays_active(self, mock_mt5):
        clock = Clock()
        adapter = _adapter(clock)
        mock_mt5.orders_get.side_effect, mock_mt5.positions_get.side_effect = _tickets(open_=[555])
        adapter.place_order(_limit())
        clock.now = KILLZONE_END + timedelta(minutes=5)   # past the expiry, but filled: nothing to cancel
        events = adapter.sync()
        assert [e["event"] for e in events] == ["FILLED"]
        trade = adapter.active_trade("EURUSD")
        assert trade["fill_price"] == 1.0990 and trade["filled_at"] == clock.now.isoformat()
        mock_mt5.order_send.assert_called_once()   # the placement only
        assert adapter.sync() == []                # recorded once

    def test_a_ticket_gone_from_the_terminal_closes_the_trade(self, mock_mt5):
        clock = Clock()
        adapter = _adapter(clock)
        mock_mt5.orders_get.side_effect, mock_mt5.positions_get.side_effect = _tickets(open_=[555])
        adapter.place_order(_limit())
        adapter.sync()
        mock_mt5.orders_get.side_effect, mock_mt5.positions_get.side_effect = _tickets()
        events = adapter.sync()
        assert [e["event"] for e in events] == ["CLOSED"]
        assert adapter.active_count() == 0

    def test_one_the_broker_expired_closes_as_expired(self, mock_mt5):
        clock = Clock()
        adapter = _adapter(clock)
        mock_mt5.orders_get.side_effect, mock_mt5.positions_get.side_effect = _tickets()
        adapter.place_order(_limit())
        clock.now = KILLZONE_END
        assert [e["event"] for e in adapter.sync()] == ["EXPIRED"]


class TestTheLedger:
    def test_it_survives_a_restart(self, mock_mt5, tmp_path):
        _adapter(Clock(), tmp_path).place_order(_limit())
        reloaded = _adapter(Clock(), tmp_path)
        assert reloaded.active_trade("EURUSD")["tickets"] == [555]
        assert reloaded.attempted_setups() == {"setup-1"}
        assert not list(tmp_path.glob("*.tmp"))

    def test_a_refused_order_is_not_recorded(self, mock_mt5, tmp_path):
        adapter = _adapter(Clock(), tmp_path)
        with pytest.raises(MT5BrokerError):
            adapter.place_order(_limit(risk_amount=1.0))   # MIN_VOLUME_OVER_RISK
        assert adapter.attempted_setups() == set()

    def test_trades_are_found_by_instrument(self, mock_mt5):
        adapter = _adapter(Clock())
        adapter.place_order(_limit())
        assert adapter.active_trade("GBPUSD") is None
        assert adapter.active_trade("EURUSD")["setup_id"] == "setup-1"
        assert adapter.active_count() == 1
