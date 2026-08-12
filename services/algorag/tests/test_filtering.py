"""
Unit tests for metadata filtering (Task 10.2).

Covers construction of the Qdrant Filter from a RetrievalRequest: required
instrument condition, optional time_window / htf_open_bias / outcome_result
conditions, and the "no outcome filter" escape hatch.

Requirements: FR-RAG-2
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from qdrant_client.http import models as qmodels

from services.algorag.filtering import build_qdrant_filter
from services.algorag.models import RetrievalRequest


def _make_request(**overrides) -> RetrievalRequest:
    defaults = dict(
        instrument="EURUSD",
        timestamp=datetime(2024, 5, 6, 9, 15, tzinfo=timezone.utc),
    )
    defaults.update(overrides)
    return RetrievalRequest(**defaults)


def _condition_map(qfilter: qmodels.Filter) -> dict:
    """Map field key -> matched value for every FieldCondition in `must`."""
    return {c.key: c.match.value for c in qfilter.must}


class TestInstrumentFilter:
    def test_instrument_always_included(self):
        request = _make_request(outcome_filter=None)
        qfilter = build_qdrant_filter(request)
        assert qfilter is not None
        assert _condition_map(qfilter)["instrument"] == "EURUSD"

    def test_instrument_uppercased(self):
        # RetrievalRequest.instrument_uppercase validator already uppercases,
        # filter must not silently rely on it doing so twice / re-lowercasing.
        request = _make_request(instrument="eurusd", outcome_filter=None)
        qfilter = build_qdrant_filter(request)
        assert _condition_map(qfilter)["instrument"] == "EURUSD"


class TestOutcomeFilter:
    def test_default_outcome_filter_is_win(self):
        request = _make_request()
        qfilter = build_qdrant_filter(request)
        assert _condition_map(qfilter)["outcome_result"] == "WIN"

    def test_outcome_filter_loss(self):
        request = _make_request(outcome_filter="LOSS")
        qfilter = build_qdrant_filter(request)
        assert _condition_map(qfilter)["outcome_result"] == "LOSS"

    def test_outcome_filter_none_omits_condition(self):
        request = _make_request(outcome_filter=None)
        qfilter = build_qdrant_filter(request)
        assert "outcome_result" not in _condition_map(qfilter)

    def test_outcome_filter_literal_none_string_omits_condition(self):
        request = _make_request(outcome_filter="None")
        qfilter = build_qdrant_filter(request)
        assert "outcome_result" not in _condition_map(qfilter)


class TestOptionalFilters:
    def test_time_window_included_when_present(self):
        request = _make_request(time_window="LONDON_KILLZONE", outcome_filter=None)
        qfilter = build_qdrant_filter(request)
        assert _condition_map(qfilter)["time_window"] == "LONDON_KILLZONE"

    def test_time_window_omitted_when_absent(self):
        request = _make_request(outcome_filter=None)
        qfilter = build_qdrant_filter(request)
        assert "time_window" not in _condition_map(qfilter)

    def test_htf_open_bias_included_when_present(self):
        request = _make_request(htf_open_bias="BULLISH", outcome_filter=None)
        qfilter = build_qdrant_filter(request)
        assert _condition_map(qfilter)["htf_open_bias"] == "BULLISH"

    def test_htf_open_bias_omitted_when_absent(self):
        request = _make_request(outcome_filter=None)
        qfilter = build_qdrant_filter(request)
        assert "htf_open_bias" not in _condition_map(qfilter)

    def test_all_filters_combined(self):
        request = _make_request(
            time_window="NY_KILLZONE",
            htf_open_bias="BEARISH",
            outcome_filter="WIN",
        )
        qfilter = build_qdrant_filter(request)
        conditions = _condition_map(qfilter)
        assert conditions == {
            "instrument": "EURUSD",
            "time_window": "NY_KILLZONE",
            "htf_open_bias": "BEARISH",
            "outcome_result": "WIN",
        }


class TestFilterType:
    def test_returns_qdrant_filter_instance(self):
        request = _make_request()
        qfilter = build_qdrant_filter(request)
        assert isinstance(qfilter, qmodels.Filter)
