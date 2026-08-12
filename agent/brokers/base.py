"""BrokerClient — the interface every broker adapter implements.

agent/nodes/execute_node.py and agent/nodes/review_node.py already call a
broker_client duck-typed (place_order / partial_close / ...); this ABC makes
that contract explicit so agent/brokers/factory.py can hand back any
registered broker by name, instead of every caller wiring up OANDA directly.

Validates: Requirements FR-6 (Agentic Execution Loop) — broker abstraction.
"""
from __future__ import annotations

import abc
from typing import Any

__all__ = ["BrokerClient"]


class BrokerClient(abc.ABC):
    """Abstract broker adapter for one live/practice trading account.

    All methods are synchronous from the caller's perspective — execute_node
    and review_node call them without `await` — even when an adapter's
    underlying transport is async (see agent/brokers/oanda.py).
    """

    @abc.abstractmethod
    def place_order(self, order: dict[str, Any]) -> dict[str, Any]:
        """Submit a market order.

        Returns a dict with at least ``order_id`` and ``trade_id`` keys.
        """

    @abc.abstractmethod
    def set_sl_tp(self, trade_id: str, sl_price: float, tp_price: float) -> bool:
        """Update stop-loss and take-profit on an open trade."""

    @abc.abstractmethod
    def close_position(self, trade_id: str) -> bool:
        """Close an open trade at market, in full."""

    @abc.abstractmethod
    def partial_close(self, trade_id: str, ratio: float = 0.5) -> dict[str, Any]:
        """Close ``ratio`` of an open trade's current size at market."""

    @abc.abstractmethod
    def get_position_status(self, trade_id: str) -> dict[str, Any]:
        """Fetch ``{"status", "unrealised_pnl", "current_price"}`` for a trade."""
