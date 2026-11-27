"""The MT5 adapter's live-execution behaviour (tasks 455, 456, 459).

The profile's symbols, expiry, the ledger, the split and sync, on the patched
``mt5`` module (as test_mt5_broker_adapter.py patches it): nothing here
touches a terminal.

Validates: Requirements 3, 6.1, 7 (.kiro/specs/live-execution/requirements.md)
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from agent.brokers.mt5 import MT5BrokerAdapter

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
