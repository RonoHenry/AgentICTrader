"""Tests for the BrokerClient ABC contract.

TDD Phase: RED — these tests are written BEFORE agent/brokers/base.py exists.

Validates: Requirements FR-6 (Agentic Execution Loop) — broker abstraction.
"""
from __future__ import annotations

import pytest

from agent.brokers.base import BrokerClient


class TestBrokerClientIsAbstract:
    """BrokerClient defines the contract every adapter must satisfy."""

    def test_cannot_instantiate_broker_client_directly(self):
        with pytest.raises(TypeError):
            BrokerClient()

    def test_broker_client_declares_required_methods(self):
        required = {
            "place_order",
            "set_sl_tp",
            "close_position",
            "partial_close",
            "get_position_status",
        }
        assert required <= BrokerClient.__abstractmethods__

    def test_subclass_missing_a_method_cannot_be_instantiated(self):
        class Incomplete(BrokerClient):
            def place_order(self, order):
                return {}

            def set_sl_tp(self, trade_id, sl_price, tp_price):
                return True

            def close_position(self, trade_id):
                return True

            def partial_close(self, trade_id, ratio=0.5):
                return {}

            # get_position_status intentionally omitted

        with pytest.raises(TypeError):
            Incomplete()

    def test_complete_subclass_can_be_instantiated(self):
        class Complete(BrokerClient):
            def place_order(self, order):
                return {}

            def set_sl_tp(self, trade_id, sl_price, tp_price):
                return True

            def close_position(self, trade_id):
                return True

            def partial_close(self, trade_id, ratio=0.5):
                return {}

            def get_position_status(self, trade_id):
                return {}

        assert isinstance(Complete(), BrokerClient)
