"""agent.brokers — pluggable BrokerClient adapters.

Public API:
  BrokerClient          — abstract interface every adapter implements.
  create_broker_client  — factory: broker name + credentials -> BrokerClient.
  UnsupportedBrokerError
  BROKER_REGISTRY       — registry key -> BrokerClient subclass.
  OANDABrokerAdapter     — working OANDA v20 REST implementation.
  PepperstoneBrokerClient — placeholder; not yet implemented (see its module docstring).
"""
from agent.brokers.base import BrokerClient
from agent.brokers.factory import BROKER_REGISTRY, UnsupportedBrokerError, create_broker_client
from agent.brokers.oanda import OANDABrokerAdapter
from agent.brokers.pepperstone import PepperstoneBrokerClient

__all__ = [
    "BrokerClient",
    "create_broker_client",
    "UnsupportedBrokerError",
    "BROKER_REGISTRY",
    "OANDABrokerAdapter",
    "PepperstoneBrokerClient",
]
