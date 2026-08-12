"""create_broker_client — pick a broker by name, get a ready BrokerClient.

This is the piece that lets a user choose whatever broker they want: the
AgentGraph itself only ever depends on the BrokerClient interface (see
agent/brokers/base.py), so wiring code just needs a broker name and that
broker's credentials.

Validates: Requirements FR-6 (Agentic Execution Loop) — broker abstraction.
"""
from __future__ import annotations

from typing import Any

from agent.brokers.base import BrokerClient
from agent.brokers.oanda import OANDABrokerAdapter
from agent.brokers.pepperstone import PepperstoneBrokerClient

__all__ = ["BROKER_REGISTRY", "UnsupportedBrokerError", "create_broker_client"]


class UnsupportedBrokerError(ValueError):
    """Raised by create_broker_client() for an unregistered broker name."""


#: Registry key -> BrokerClient subclass. Add a new broker by implementing
#: BrokerClient and registering it here — nothing else needs to change.
BROKER_REGISTRY: dict[str, type[BrokerClient]] = {
    "oanda": OANDABrokerAdapter,
    "pepperstone": PepperstoneBrokerClient,
}


def create_broker_client(broker_name: str, **credentials: Any) -> BrokerClient:
    """Instantiate the BrokerClient adapter registered under ``broker_name``.

    Args:
        broker_name:   Registry key, case-insensitive (e.g. ``"oanda"``).
        **credentials: Forwarded verbatim to the adapter's constructor.

    Raises:
        UnsupportedBrokerError: If no adapter is registered under that name.
    """
    key = broker_name.strip().lower()
    try:
        adapter_cls = BROKER_REGISTRY[key]
    except KeyError:
        raise UnsupportedBrokerError(
            f"No broker adapter registered for {broker_name!r}. "
            f"Available: {sorted(BROKER_REGISTRY)}"
        ) from None
    return adapter_cls(**credentials)
