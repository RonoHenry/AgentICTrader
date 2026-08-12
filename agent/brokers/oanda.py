"""OANDABrokerAdapter — synchronous BrokerClient facade over the async
OANDA v20 functions in agent/broker_tools.py.

execute_node.py and review_node.py call broker_client methods without
`await`; this adapter bridges to those async functions with asyncio.run()
per call, so it must not be constructed/used from inside an already-running
event loop.

Validates: Requirements FR-6 (Agentic Execution Loop) — broker abstraction.
"""
from __future__ import annotations

import asyncio
from typing import Any

from agent.broker_tools import (
    OANDABrokerClient,
    close_position as _close_position,
    get_position_status as _get_position_status,
    partial_close as _partial_close,
    place_order as _place_order,
    set_sl_tp as _set_sl_tp,
)
from agent.brokers.base import BrokerClient

__all__ = ["OANDABrokerAdapter"]


class OANDABrokerAdapter(BrokerClient):
    """BrokerClient implementation backed by the OANDA v20 REST API."""

    def __init__(
        self,
        account_id: str,
        access_token: str,
        api_url: str | None = None,
    ) -> None:
        self._client = OANDABrokerClient(account_id, access_token, api_url)

    def place_order(self, order: dict[str, Any]) -> dict[str, Any]:
        return asyncio.run(_place_order(self._client, order))

    def set_sl_tp(self, trade_id: str, sl_price: float, tp_price: float) -> bool:
        return asyncio.run(_set_sl_tp(self._client, trade_id, sl_price, tp_price))

    def close_position(self, trade_id: str) -> bool:
        return asyncio.run(_close_position(self._client, trade_id))

    def partial_close(self, trade_id: str, ratio: float = 0.5) -> dict[str, Any]:
        return asyncio.run(_partial_close(self._client, trade_id, ratio))

    def get_position_status(self, trade_id: str) -> dict[str, Any]:
        return asyncio.run(_get_position_status(self._client, trade_id))
