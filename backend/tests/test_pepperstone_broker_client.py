"""Tests for the Pepperstone BrokerClient placeholder.

Pepperstone has no backing implementation yet — see the module docstring
in agent/brokers/pepperstone.py for why (no public broker-run REST API;
retail execution goes through MT5, cTrader Open API, or a bridge like
MetaApi, and picking one is a decision, not an implementation detail).

These tests only pin down that the placeholder satisfies the BrokerClient
contract and fails loudly — not silently — when actually used, so it can't
be mistaken for a working adapter.

TDD Phase: RED — written before agent/brokers/pepperstone.py exists.
"""
from __future__ import annotations

import pytest

from agent.brokers.base import BrokerClient
from agent.brokers.pepperstone import PepperstoneBrokerClient


@pytest.fixture
def client():
    return PepperstoneBrokerClient()


class TestPepperstonePlaceholder:
    def test_is_a_broker_client(self, client):
        assert isinstance(client, BrokerClient)

    def test_accepts_arbitrary_credentials_without_raising_at_construction(self):
        # Must not raise at construction time — only when actually used —
        # so create_broker_client("pepperstone", ...) fails at the call site
        # that tries to trade, not at wiring time.
        PepperstoneBrokerClient(account_id="12345", access_token="tok")

    def test_place_order_raises_not_implemented(self, client):
        with pytest.raises(NotImplementedError):
            client.place_order({})

    def test_set_sl_tp_raises_not_implemented(self, client):
        with pytest.raises(NotImplementedError):
            client.set_sl_tp("1", 1.0, 1.1)

    def test_close_position_raises_not_implemented(self, client):
        with pytest.raises(NotImplementedError):
            client.close_position("1")

    def test_partial_close_raises_not_implemented(self, client):
        with pytest.raises(NotImplementedError):
            client.partial_close("1")

    def test_get_position_status_raises_not_implemented(self, client):
        with pytest.raises(NotImplementedError):
            client.get_position_status("1")
