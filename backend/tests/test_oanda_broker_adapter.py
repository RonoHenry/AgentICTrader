"""Tests for OANDABrokerAdapter — the synchronous BrokerClient facade over
the async OANDA v20 functions in agent/broker_tools.py.

TDD Phase: RED — these tests are written BEFORE agent/brokers/oanda.py exists.

execute_node.py and review_node.py call broker_client methods synchronously
(no `await`); this adapter is what makes agent.broker_tools' async functions
satisfy that call shape.

Validates: Requirements FR-6 (Agentic Execution Loop) — broker abstraction.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from agent.brokers.base import BrokerClient
from agent.brokers.oanda import OANDABrokerAdapter

FAKE_ACCOUNT_ID = "001-001-1234567-001"
FAKE_ACCESS_TOKEN = "test-access-token-abc123"


@pytest.fixture
def adapter():
    return OANDABrokerAdapter(account_id=FAKE_ACCOUNT_ID, access_token=FAKE_ACCESS_TOKEN)


class TestOANDABrokerAdapterIsABrokerClient:
    def test_adapter_is_a_broker_client(self, adapter):
        assert isinstance(adapter, BrokerClient)


class TestOANDABrokerAdapterDelegation:
    """Every method must delegate to agent.broker_tools synchronously."""

    def test_place_order_delegates_and_returns_result(self, adapter):
        order = {"instrument": "EURUSD", "direction": "LONG", "size": 0.01}
        with patch("agent.brokers.oanda._place_order", new_callable=AsyncMock) as mock_fn:
            mock_fn.return_value = {"order_id": "1", "trade_id": "2"}
            result = adapter.place_order(order)

        mock_fn.assert_awaited_once_with(adapter._client, order)
        assert result == {"order_id": "1", "trade_id": "2"}

    def test_set_sl_tp_delegates(self, adapter):
        with patch("agent.brokers.oanda._set_sl_tp", new_callable=AsyncMock) as mock_fn:
            mock_fn.return_value = True
            result = adapter.set_sl_tp("67890", 1.08, 1.09)

        mock_fn.assert_awaited_once_with(adapter._client, "67890", 1.08, 1.09)
        assert result is True

    def test_close_position_delegates(self, adapter):
        with patch("agent.brokers.oanda._close_position", new_callable=AsyncMock) as mock_fn:
            mock_fn.return_value = True
            result = adapter.close_position("67890")

        mock_fn.assert_awaited_once_with(adapter._client, "67890")
        assert result is True

    def test_partial_close_delegates_with_default_ratio(self, adapter):
        with patch("agent.brokers.oanda._partial_close", new_callable=AsyncMock) as mock_fn:
            mock_fn.return_value = {"trade_id": "67890", "closed_units": 500}
            result = adapter.partial_close("67890")

        mock_fn.assert_awaited_once_with(adapter._client, "67890", 0.5)
        assert result == {"trade_id": "67890", "closed_units": 500}

    def test_partial_close_forwards_custom_ratio(self, adapter):
        with patch("agent.brokers.oanda._partial_close", new_callable=AsyncMock) as mock_fn:
            mock_fn.return_value = {"trade_id": "67890", "closed_units": 250}
            adapter.partial_close("67890", ratio=0.25)

        mock_fn.assert_awaited_once_with(adapter._client, "67890", 0.25)

    def test_get_position_status_delegates(self, adapter):
        with patch("agent.brokers.oanda._get_position_status", new_callable=AsyncMock) as mock_fn:
            mock_fn.return_value = {
                "status": "OPEN",
                "unrealised_pnl": 1.0,
                "current_price": 1.09,
            }
            result = adapter.get_position_status("67890")

        mock_fn.assert_awaited_once_with(adapter._client, "67890")
        assert result["status"] == "OPEN"
