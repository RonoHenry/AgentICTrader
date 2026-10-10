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
        mock.TRADE_ACTION_PENDING = 5
        mock.TRADE_ACTION_REMOVE = 8
        mock.ORDER_TYPE_BUY_LIMIT = 2
        mock.ORDER_TYPE_SELL_LIMIT = 3
        mock.ORDER_TIME_GTC = 0
        mock.ORDER_FILLING_IOC = 1
        mock.ORDER_FILLING_RETURN = 2
        mock.symbol_info.return_value = MagicMock(
            filling_mode=2, volume_step=0.01, volume_min=0.01, volume_max=100.0
        )
        # Default: no pending order found — tests exercising the PENDING
        # path override this explicitly. Without this default, a bare
        # MagicMock() (truthy) would make every "no position" test look
        # like a pending order was found instead of a real CLOSED/missing
        # ticket.
        mock.orders_get.return_value = ()
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

        assert result == {"order_id": "777", "trade_id": "777", "pending": False}

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


class TestMT5BrokerAdapterPendingOrders:
    """ICT setups grade a zone as valid to trade from, not necessarily
    fillable this instant — a requested entry away from the live price
    must become a resting limit order, not a market order with SL/TP
    computed relative to a price never actually entered at."""

    def test_long_entry_below_ask_places_buy_limit(self, adapter, mock_mt5):
        mock_mt5.symbol_info_tick.return_value = MagicMock(ask=1.0900, bid=1.0898)
        mock_mt5.order_send.return_value = MagicMock(retcode=mock_mt5.TRADE_RETCODE_DONE, order=555)

        result = adapter.place_order({
            "instrument": "EURUSD", "direction": "LONG", "size": 0.01,
            "entry": 1.0850, "stop_loss": 1.0820, "take_profit": 1.0950,
        })

        sent_request = mock_mt5.order_send.call_args[0][0]
        assert sent_request["action"] == mock_mt5.TRADE_ACTION_PENDING
        assert sent_request["type"] == mock_mt5.ORDER_TYPE_BUY_LIMIT
        assert sent_request["price"] == 1.0850
        assert sent_request["type_filling"] == mock_mt5.ORDER_FILLING_RETURN
        assert result["pending"] is True

    def test_short_entry_above_bid_places_sell_limit(self, adapter, mock_mt5):
        mock_mt5.symbol_info_tick.return_value = MagicMock(ask=1.0900, bid=1.0898)
        mock_mt5.order_send.return_value = MagicMock(retcode=mock_mt5.TRADE_RETCODE_DONE, order=556)

        result = adapter.place_order({
            "instrument": "EURUSD", "direction": "SHORT", "size": 0.01,
            "entry": 1.0950, "stop_loss": 1.0980, "take_profit": 1.0850,
        })

        sent_request = mock_mt5.order_send.call_args[0][0]
        assert sent_request["action"] == mock_mt5.TRADE_ACTION_PENDING
        assert sent_request["type"] == mock_mt5.ORDER_TYPE_SELL_LIMIT
        assert sent_request["price"] == 1.0950
        assert result["pending"] is True

    def test_long_entry_already_reached_falls_back_to_market(self, adapter, mock_mt5):
        mock_mt5.symbol_info_tick.return_value = MagicMock(ask=1.0900, bid=1.0898)
        mock_mt5.order_send.return_value = MagicMock(retcode=mock_mt5.TRADE_RETCODE_DONE, order=557)

        result = adapter.place_order({
            "instrument": "EURUSD", "direction": "LONG", "size": 0.01,
            "entry": 1.0900, "stop_loss": 1.0850, "take_profit": 1.0950,
        })

        sent_request = mock_mt5.order_send.call_args[0][0]
        assert sent_request["action"] == mock_mt5.TRADE_ACTION_DEAL
        assert sent_request["type"] == mock_mt5.ORDER_TYPE_BUY
        assert sent_request["price"] == 1.0900
        assert result["pending"] is False

    def test_missing_entry_falls_back_to_market(self, adapter, mock_mt5):
        mock_mt5.symbol_info_tick.return_value = MagicMock(ask=1.0900, bid=1.0898)
        mock_mt5.order_send.return_value = MagicMock(retcode=mock_mt5.TRADE_RETCODE_DONE, order=558)

        result = adapter.place_order({"instrument": "EURUSD", "direction": "LONG", "size": 0.01})

        sent_request = mock_mt5.order_send.call_args[0][0]
        assert sent_request["action"] == mock_mt5.TRADE_ACTION_DEAL
        assert result["pending"] is False


class TestMT5BrokerAdapterVolumeNormalization:
    """A risk-engine-computed size is rarely already a clean multiple of the
    broker's volume_step — MT5 rejects anything else outright with "Invalid
    volume" rather than rounding it for you (observed live: 0.032 lots
    rejected on a 0.01 step)."""

    def test_rounds_to_volume_step(self, adapter, mock_mt5):
        mock_mt5.symbol_info_tick.return_value = MagicMock(ask=1.0900, bid=1.0898)
        mock_mt5.order_send.return_value = MagicMock(retcode=mock_mt5.TRADE_RETCODE_DONE, order=555)

        adapter.place_order({"instrument": "EURUSD", "direction": "LONG", "size": 0.032})

        sent_request = mock_mt5.order_send.call_args[0][0]
        assert sent_request["volume"] == 0.03

    def test_clamps_to_volume_min(self, adapter, mock_mt5):
        mock_mt5.symbol_info_tick.return_value = MagicMock(ask=1.0900, bid=1.0898)
        mock_mt5.order_send.return_value = MagicMock(retcode=mock_mt5.TRADE_RETCODE_DONE, order=555)

        adapter.place_order({"instrument": "EURUSD", "direction": "LONG", "size": 0.001})

        sent_request = mock_mt5.order_send.call_args[0][0]
        assert sent_request["volume"] == 0.01

    def test_clamps_to_volume_max(self, adapter, mock_mt5):
        mock_mt5.symbol_info.return_value = MagicMock(
            filling_mode=2, volume_step=0.01, volume_min=0.01, volume_max=5.0
        )
        mock_mt5.symbol_info_tick.return_value = MagicMock(ask=1.0900, bid=1.0898)
        mock_mt5.order_send.return_value = MagicMock(retcode=mock_mt5.TRADE_RETCODE_DONE, order=555)

        adapter.place_order({"instrument": "EURUSD", "direction": "LONG", "size": 12.0})

        sent_request = mock_mt5.order_send.call_args[0][0]
        assert sent_request["volume"] == 5.0


class TestMT5BrokerAdapterRiskBasedSizing:
    """RiskEngine's position_size (order["size"]) is OANDA-unit-shaped —
    passed straight through as MT5 lot volume it's a real unit mismatch.
    order["risk_amount"] (money terms) plus the symbol's own
    trade_tick_value/trade_tick_size compute real lots instead;
    order["size"] is only used as a fallback when that isn't possible."""

    def test_computes_lots_from_risk_amount(self, adapter, mock_mt5):
        mock_mt5.symbol_info.return_value = MagicMock(
            filling_mode=2, volume_step=0.01, volume_min=0.01, volume_max=100.0,
            trade_tick_size=0.0001, trade_tick_value=10.0,
        )
        mock_mt5.symbol_info_tick.return_value = MagicMock(ask=1.1000, bid=1.0998)
        mock_mt5.order_send.return_value = MagicMock(retcode=mock_mt5.TRADE_RETCODE_DONE, order=555)

        adapter.place_order({
            "instrument": "EURUSD", "direction": "LONG",
            "entry": 1.1000, "stop_loss": 1.0980,
            "size": 5.0,            # legacy OANDA-unit figure — must be ignored
            "risk_amount": 100.0,   # $100 risk / 20 pip SL / $10 per pip per lot -> 0.5 lots
        })

        sent_request = mock_mt5.order_send.call_args[0][0]
        assert sent_request["volume"] == 0.5

    def test_falls_back_to_size_when_risk_amount_absent(self, adapter, mock_mt5):
        mock_mt5.symbol_info_tick.return_value = MagicMock(ask=1.1000, bid=1.0998)
        mock_mt5.order_send.return_value = MagicMock(retcode=mock_mt5.TRADE_RETCODE_DONE, order=555)

        adapter.place_order({
            "instrument": "EURUSD", "direction": "LONG",
            "entry": 1.1000, "stop_loss": 1.0980,
            "size": 0.05,
        })

        sent_request = mock_mt5.order_send.call_args[0][0]
        assert sent_request["volume"] == 0.05

    def test_falls_back_to_size_when_stop_loss_missing(self, adapter, mock_mt5):
        mock_mt5.symbol_info_tick.return_value = MagicMock(ask=1.1000, bid=1.0998)
        mock_mt5.order_send.return_value = MagicMock(retcode=mock_mt5.TRADE_RETCODE_DONE, order=555)

        adapter.place_order({
            "instrument": "EURUSD", "direction": "LONG",
            "entry": 1.1000,
            "size": 0.05,
            "risk_amount": 100.0,
        })

        sent_request = mock_mt5.order_send.call_args[0][0]
        assert sent_request["volume"] == 0.05

    def test_falls_back_to_size_when_symbol_missing_tick_value(self, adapter, mock_mt5):
        mock_mt5.symbol_info.return_value = MagicMock(
            filling_mode=2, volume_step=0.01, volume_min=0.01, volume_max=100.0,
            trade_tick_size=0.0, trade_tick_value=0.0,
        )
        mock_mt5.symbol_info_tick.return_value = MagicMock(ask=1.1000, bid=1.0998)
        mock_mt5.order_send.return_value = MagicMock(retcode=mock_mt5.TRADE_RETCODE_DONE, order=555)

        adapter.place_order({
            "instrument": "EURUSD", "direction": "LONG",
            "entry": 1.1000, "stop_loss": 1.0980,
            "size": 0.05,
            "risk_amount": 100.0,
        })

        sent_request = mock_mt5.order_send.call_args[0][0]
        assert sent_request["volume"] == 0.05


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

    def test_close_position_cancels_pending_order_when_not_yet_filled(self, adapter, mock_mt5):
        """A resting limit order that hasn't filled yet has nothing to close
        via a market deal — close_position() cancels it instead of raising
        "no open position" for a trade that's actually still live."""
        mock_mt5.positions_get.return_value = ()
        pending_order = MagicMock(symbol="GBPUSD", ticket=777)
        mock_mt5.orders_get.return_value = (pending_order,)
        mock_mt5.order_send.return_value = MagicMock(retcode=mock_mt5.TRADE_RETCODE_DONE, order=777)

        result = adapter.close_position("777")

        sent_request = mock_mt5.order_send.call_args[0][0]
        assert sent_request["action"] == mock_mt5.TRADE_ACTION_REMOVE
        assert sent_request["order"] == 777
        assert result is True


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

    def test_partial_close_raises_clear_error_when_still_pending(self, adapter, mock_mt5):
        """review_node only calls partial_close once r_multiple is
        computable, which structurally implies a fill already happened —
        a still-pending order here should never occur in practice, but if
        it does, it must raise a specific, honest error rather than the
        old misleading "no open position"."""
        mock_mt5.positions_get.return_value = ()
        pending_order = MagicMock(symbol="GBPUSD", ticket=777)
        mock_mt5.orders_get.return_value = (pending_order,)

        from agent.brokers.mt5 import MT5BrokerError

        with pytest.raises(MT5BrokerError, match="still pending"):
            adapter.partial_close("777", ratio=0.5)


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

    def test_get_position_status_pending_when_resting_order_not_yet_filled(self, adapter, mock_mt5):
        """This is the exact scenario that motivated the fix: a resting
        BUY_LIMIT that hasn't triggered yet used to read as CLOSED."""
        mock_mt5.positions_get.return_value = ()
        pending_order = MagicMock(symbol="GBPUSD", type=mock_mt5.ORDER_TYPE_BUY_LIMIT)
        mock_mt5.orders_get.return_value = (pending_order,)
        mock_mt5.symbol_info_tick.return_value = MagicMock(ask=1.3560, bid=1.3558)

        result = adapter.get_position_status("777")

        assert result == {
            "status": "PENDING",
            "unrealised_pnl": 0.0,
            "current_price": 1.3560,
        }

    def test_get_position_status_pending_sell_limit_uses_bid(self, adapter, mock_mt5):
        mock_mt5.positions_get.return_value = ()
        pending_order = MagicMock(symbol="USDJPY", type=mock_mt5.ORDER_TYPE_SELL_LIMIT)
        mock_mt5.orders_get.return_value = (pending_order,)
        mock_mt5.symbol_info_tick.return_value = MagicMock(ask=159.30, bid=159.28)

        result = adapter.get_position_status("777")

        assert result["status"] == "PENDING"
        assert result["current_price"] == 159.28
