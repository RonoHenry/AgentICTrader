"""Pepperstone broker adapter — NOT YET IMPLEMENTED.

Pepperstone, like most retail CFD/FX brokers, does not run its own public
trading REST API. Retail order execution goes through one of:

  1. MetaTrader 5 terminal + the `MetaTrader5` Python package — requires a
     running MT5 terminal logged into the account. Windows-only; does not
     run inside the Linux containers in docker/docker-compose.yml without a
     Wine-based workaround.
  2. cTrader Open API — OAuth2 + REST/WebSocket, cloud-reachable, fits this
     codebase's existing async httpx pattern (see agent/broker_tools.py).
  3. A third-party MT4/5 bridge (e.g. MetaApi.cloud) — wraps the MT5
     terminal in a hosted REST/WebSocket API; paid service, but works for
     every MT4/5 broker, not just Pepperstone.

Which of these to build against changes the implementation entirely, so
this class only reserves the registry slot and pins down the BrokerClient
contract — pick a route before implementing any method below.

Validates: Requirements FR-6 (Agentic Execution Loop) — broker abstraction.
"""
from __future__ import annotations

from typing import Any

from agent.brokers.base import BrokerClient

__all__ = ["PepperstoneBrokerClient"]

_NOT_IMPLEMENTED = (
    "PepperstoneBrokerClient has no backing implementation yet — see the "
    "module docstring in agent/brokers/pepperstone.py for the MT5 / cTrader "
    "Open API / MetaApi decision that has to be made before this can trade."
)


class PepperstoneBrokerClient(BrokerClient):
    """Placeholder BrokerClient for Pepperstone — see module docstring.

    Accepts arbitrary credentials at construction time without raising, so
    wiring/factory code can build one ahead of time; every trading method
    raises NotImplementedError so a misconfigured deployment fails loudly
    the moment it tries to place a real order, not silently.
    """

    def __init__(self, **credentials: Any) -> None:
        self._credentials = credentials

    def place_order(self, order: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError(_NOT_IMPLEMENTED)

    def set_sl_tp(self, trade_id: str, sl_price: float, tp_price: float) -> bool:
        raise NotImplementedError(_NOT_IMPLEMENTED)

    def close_position(self, trade_id: str) -> bool:
        raise NotImplementedError(_NOT_IMPLEMENTED)

    def partial_close(self, trade_id: str, ratio: float = 0.5) -> dict[str, Any]:
        raise NotImplementedError(_NOT_IMPLEMENTED)

    def get_position_status(self, trade_id: str) -> dict[str, Any]:
        raise NotImplementedError(_NOT_IMPLEMENTED)
