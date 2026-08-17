"""Tests for agent.brokers.factory.create_broker_client().

TDD Phase: RED — these tests are written BEFORE agent/brokers/factory.py exists.

This is the piece that lets a user pick "whatever broker they want": one
name + one set of credentials in, a ready BrokerClient out.

Validates: Requirements FR-6 (Agentic Execution Loop) — broker abstraction.
"""
from __future__ import annotations

import pytest

from agent.brokers.base import BrokerClient
from agent.brokers.factory import BROKER_REGISTRY, UnsupportedBrokerError, create_broker_client
from agent.brokers.mt5 import MT5BrokerAdapter
from agent.brokers.oanda import OANDABrokerAdapter
from agent.brokers.pepperstone import PepperstoneBrokerClient


class TestCreateBrokerClient:
    def test_creates_oanda_adapter(self):
        client = create_broker_client(
            "oanda", account_id="001-001-1234567-001", access_token="tok"
        )
        assert isinstance(client, OANDABrokerAdapter)
        assert isinstance(client, BrokerClient)

    def test_broker_name_is_case_insensitive(self):
        client = create_broker_client(
            "OANDA", account_id="001-001-1234567-001", access_token="tok"
        )
        assert isinstance(client, OANDABrokerAdapter)

    def test_broker_name_tolerates_surrounding_whitespace(self):
        client = create_broker_client(
            "  oanda  ", account_id="001-001-1234567-001", access_token="tok"
        )
        assert isinstance(client, OANDABrokerAdapter)

    def test_unknown_broker_raises_unsupported_broker_error(self):
        with pytest.raises(UnsupportedBrokerError):
            create_broker_client("mt4", account_id="x", access_token="y")

    def test_registry_lists_oanda_pepperstone_and_mt5(self):
        assert "oanda" in BROKER_REGISTRY
        assert "pepperstone" in BROKER_REGISTRY
        assert "mt5" in BROKER_REGISTRY

    def test_creates_pepperstone_placeholder_but_it_is_not_usable_yet(self):
        client = create_broker_client("pepperstone")
        assert isinstance(client, PepperstoneBrokerClient)
        with pytest.raises(NotImplementedError):
            client.place_order({})

    def test_creates_mt5_adapter(self):
        client = create_broker_client(
            "mt5", login=12345678, password="pw", server="Broker-Demo"
        )
        assert isinstance(client, MT5BrokerAdapter)
        assert isinstance(client, BrokerClient)
