"""Tests for MT5BrokerAdapter — BrokerClient backed by the local MetaTrader5
terminal via the `MetaTrader5` Python package.

Unlike OANDA (stateless REST calls) MT5's Python package is a process-wide
singleton: `mt5.initialize()` / `mt5.login()` attach to a terminal already
installed on this machine, and every other call is a plain module-level
function. These tests patch `agent.brokers.mt5.mt5` (the imported module
object) so they never touch a real terminal.

TDD Phase: RED — these tests are written BEFORE agent/brokers/mt5.py exists.

Validates: Requirements FR-6 (Agentic Execution Loop) — broker abstraction.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from agent.brokers.base import BrokerClient

FAKE_LOGIN = 12345678
FAKE_PASSWORD = "test-password"
FAKE_SERVER = "Broker-Demo"


@pytest.fixture
def adapter():
    from agent.brokers.mt5 import MT5BrokerAdapter

    return MT5BrokerAdapter(login=FAKE_LOGIN, password=FAKE_PASSWORD, server=FAKE_SERVER)


@pytest.fixture
def mock_mt5():
    with patch("agent.brokers.mt5.mt5") as mock:
        mock.initialize.return_value = True
        mock.TRADE_RETCODE_DONE = 10009
        mock.ORDER_TYPE_BUY = 0
        mock.ORDER_TYPE_SELL = 1
        mock.TRADE_ACTION_DEAL = 1
        mock.TRADE_ACTION_SLTP = 2
        mock.ORDER_TIME_GTC = 0
        mock.ORDER_FILLING_IOC = 1
        yield mock


class TestMT5BrokerAdapterIsABrokerClient:
    def test_adapter_is_a_broker_client(self, adapter):
        assert isinstance(adapter, BrokerClient)

    def test_accepts_credentials_without_connecting_at_construction(self):
        # Construction must not touch the MT5 terminal — only the first real
        # call should, same convention as OANDA/Pepperstone adapters.
        with patch("agent.brokers.mt5.mt5") as mock:
            from agent.brokers.mt5 import MT5BrokerAdapter

            MT5BrokerAdapter(login=FAKE_LOGIN, password=FAKE_PASSWORD, server=FAKE_SERVER)
            mock.initialize.assert_not_called()


class TestMT5BrokerAdapterConnection:
    def test_place_order_initializes_with_credentials(self, adapter, mock_mt5):
        mock_mt5.symbol_info_tick.return_value = MagicMock(ask=1.0900, bid=1.0898)
        result_mock = MagicMock(retcode=mock_mt5.TRADE_RETCODE_DONE, order=555)
        mock_mt5.order_send.return_value = result_mock

        adapter.place_order({"instrument": "EURUSD", "direction": "LONG", "size": 0.01})

        mock_mt5.initialize.assert_called_once_with(
            login=FAKE_LOGIN, password=FAKE_PASSWORD, server=FAKE_SERVER
        )

    def test_raises_when_initialize_fails(self, adapter, mock_mt5):
        mock_mt5.initialize.return_value = False
        mock_mt5.last_error.return_value = (1, "Terminal not found")

        from agent.brokers.mt5 import MT5BrokerError

        with pytest.raises(MT5BrokerError):
            adapter.place_order({"instrument": "EURUSD", "direction": "LONG", "size": 0.01})

    def test_reuses_connection_across_calls(self, adapter, mock_mt5):
        mock_mt5.symbol_info_tick.return_value = MagicMock(ask=1.0900, bid=1.0898)
        mock_mt5.order_send.return_value = MagicMock(retcode=mock_mt5.TRADE_RETCODE_DONE, order=555)

        adapter.place_order({"instrument": "EURUSD", "direction": "LONG", "size": 0.01})
        adapter.place_order({"instrument": "EURUSD", "direction": "LONG", "size": 0.01})

        mock_mt5.initialize.assert_called_once()


class TestMT5BrokerAdapterPlaceOrder:
    def test_place_order_buy_uses_ask_price(self, adapter, mock_mt5):
        mock_mt5.symbol_info_tick.return_value = MagicMock(ask=1.0900, bid=1.0898)
        mock_mt5.order_send.return_value = MagicMock(retcode=mock_mt5.TRADE_RETCODE_DONE, order=555)

        adapter.place_order({"instrument": "EURUSD", "direction": "LONG", "size": 0.01})

        sent_request = mock_mt5.order_send.call_args[0][0]
        assert sent_request["type"] == mock_mt5.ORDER_TYPE_BUY
        assert sent_request["price"] == 1.0900
        assert sent_request["symbol"] == "EURUSD"
        assert sent_request["volume"] == 0.01

    def test_place_order_sell_uses_bid_price(self, adapter, mock_mt5):
        mock_mt5.symbol_info_tick.return_value = MagicMock(ask=1.0900, bid=1.0898)
        mock_mt5.order_send.return_value = MagicMock(retcode=mock_mt5.TRADE_RETCODE_DONE, order=556)

        adapter.place_order({"instrument": "EURUSD", "direction": "SHORT", "size": 0.01})

        sent_request = mock_mt5.order_send.call_args[0][0]
        assert sent_request["type"] == mock_mt5.ORDER_TYPE_SELL
        assert sent_request["price"] == 1.0898

    def test_place_order_forwards_sl_tp(self, adapter, mock_mt5):
        mock_mt5.symbol_info_tick.return_value = MagicMock(ask=1.0900, bid=1.0898)
        mock_mt5.order_send.return_value = MagicMock(retcode=mock_mt5.TRADE_RETCODE_DONE, order=555)

        adapter.place_order({
            "instrument": "EURUSD", "direction": "LONG", "size": 0.01,
            "stop_loss": 1.0850, "take_profit": 1.0950,
        })

        sent_request = mock_mt5.order_send.call_args[0][0]
        assert sent_request["sl"] == 1.0850
        assert sent_request["tp"] == 1.0950

    def test_place_order_returns_ticket_as_order_and_trade_id(self, adapter, mock_mt5):
        mock_mt5.symbol_info_tick.return_value = MagicMock(ask=1.0900, bid=1.0898)
        mock_mt5.order_send.return_value = MagicMock(retcode=mock_mt5.TRADE_RETCODE_DONE, order=777)

        result = adapter.place_order({"instrument": "EURUSD", "direction": "LONG", "size": 0.01})

        assert result == {"order_id": "777", "trade_id": "777"}

    def test_place_order_raises_on_bad_retcode(self, adapter, mock_mt5):
        mock_mt5.symbol_info_tick.return_value = MagicMock(ask=1.0900, bid=1.0898)
        mock_mt5.order_send.return_value = MagicMock(
            retcode=10004, comment="Requote", order=0
        )

        from agent.brokers.mt5 import MT5BrokerError

        with pytest.raises(MT5BrokerError):
            adapter.place_order({"instrument": "EURUSD", "direction": "LONG", "size": 0.01})

    def test_place_order_raises_when_symbol_has_no_tick(self, adapter, mock_mt5):
        mock_mt5.symbol_info_tick.return_value = None

        from agent.brokers.mt5 import MT5BrokerError

        with pytest.raises(MT5BrokerError):
            adapter.place_order({"instrument": "UNKNOWN", "direction": "LONG", "size": 0.01})

    def test_place_order_appends_symbol_suffix_when_configured(self, mock_mt5):
        from agent.brokers.mt5 import MT5BrokerAdapter

        suffixed_adapter = MT5BrokerAdapter(
            login=FAKE_LOGIN, password=FAKE_PASSWORD, server=FAKE_SERVER, symbol_suffix=".a",
        )
        mock_mt5.symbol_info_tick.return_value = MagicMock(ask=1.0900, bid=1.0898)
        mock_mt5.order_send.return_value = MagicMock(retcode=mock_mt5.TRADE_RETCODE_DONE, order=555)

        suffixed_adapter.place_order({"instrument": "EURUSD", "direction": "LONG", "size": 0.01})

        mock_mt5.symbol_info_tick.assert_called_once_with("EURUSD.a")
        sent_request = mock_mt5.order_send.call_args[0][0]
        assert sent_request["symbol"] == "EURUSD.a"


class TestMT5BrokerAdapterSetSlTp:
    def test_set_sl_tp_sends_sltp_action(self, adapter, mock_mt5):
        mock_mt5.positions_get.return_value = (MagicMock(symbol="EURUSD"),)
        mock_mt5.order_send.return_value = MagicMock(retcode=mock_mt5.TRADE_RETCODE_DONE)

        result = adapter.set_sl_tp("777", 1.0850, 1.0950)

        sent_request = mock_mt5.order_send.call_args[0][0]
        assert sent_request["action"] == mock_mt5.TRADE_ACTION_SLTP
        assert sent_request["position"] == 777
        assert sent_request["sl"] == 1.0850
        assert sent_request["tp"] == 1.0950
        assert result is True

    def test_set_sl_tp_raises_when_position_missing(self, adapter, mock_mt5):
        mock_mt5.positions_get.return_value = ()

        from agent.brokers.mt5 import MT5BrokerError

        with pytest.raises(MT5BrokerError):
            adapter.set_sl_tp("777", 1.0850, 1.0950)


class TestMT5BrokerAdapterClosePosition:
    def test_close_position_sends_opposite_deal_for_full_volume(self, adapter, mock_mt5):
        position = MagicMock(symbol="EURUSD", volume=0.02, type=mock_mt5.ORDER_TYPE_BUY, ticket=777)
        mock_mt5.positions_get.return_value = (position,)
        mock_mt5.symbol_info_tick.return_value = MagicMock(ask=1.0900, bid=1.0898)
        mock_mt5.order_send.return_value = MagicMock(retcode=mock_mt5.TRADE_RETCODE_DONE, order=999)

        result = adapter.close_position("777")

        sent_request = mock_mt5.order_send.call_args[0][0]
        assert sent_request["type"] == mock_mt5.ORDER_TYPE_SELL
        assert sent_request["volume"] == 0.02
        assert sent_request["position"] == 777
        assert result is True

    def test_close_position_raises_when_position_missing(self, adapter, mock_mt5):
        mock_mt5.positions_get.return_value = ()

        from agent.brokers.mt5 import MT5BrokerError

        with pytest.raises(MT5BrokerError):
            adapter.close_position("777")


class TestMT5BrokerAdapterPartialClose:
    def test_partial_close_uses_ratio_of_volume(self, adapter, mock_mt5):
        position = MagicMock(symbol="EURUSD", volume=0.02, type=mock_mt5.ORDER_TYPE_BUY, ticket=777)
        mock_mt5.positions_get.return_value = (position,)
        mock_mt5.symbol_info_tick.return_value = MagicMock(ask=1.0900, bid=1.0898)
        mock_mt5.order_send.return_value = MagicMock(retcode=mock_mt5.TRADE_RETCODE_DONE, order=1000)

        result = adapter.partial_close("777", ratio=0.5)

        sent_request = mock_mt5.order_send.call_args[0][0]
        assert sent_request["volume"] == pytest.approx(0.01)
        assert result["trade_id"] == "777"
        assert result["closed_units"] == pytest.approx(0.01)


class TestMT5BrokerAdapterGetPositionStatus:
    def test_get_position_status_open(self, adapter, mock_mt5):
        position = MagicMock(symbol="EURUSD", type=mock_mt5.ORDER_TYPE_BUY, profit=12.5)
        mock_mt5.positions_get.return_value = (position,)
        mock_mt5.symbol_info_tick.return_value = MagicMock(ask=1.0900, bid=1.0898)

        result = adapter.get_position_status("777")

        assert result == {
            "status": "OPEN",
            "unrealised_pnl": 12.5,
            "current_price": 1.0898,
        }

    def test_get_position_status_closed_when_no_position_found(self, adapter, mock_mt5):
        mock_mt5.positions_get.return_value = ()

        result = adapter.get_position_status("777")

        assert result["status"] == "CLOSED"
