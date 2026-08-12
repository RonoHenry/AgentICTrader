"""
Unit tests for query-time embedding generation (Task 10.3).

Covers generate_query_embedding(): shape/dtype invariants, determinism, and
that the narrative / structured / temporal components actually respond to
the request content — guarding against the original stub regressing back to
a constant zero vector.

Requirements: FR-RAG-2
"""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pytest

from scripts.rag.utils.narrative_embedder import NarrativeEmbedder
from scripts.rag.utils.temporal_embedder import TemporalEmbedder
from services.algorag.embedding_generation import generate_query_embedding
from services.algorag.models import RetrievalRequest

COMBINED_DIM = 528
NARRATIVE_SLICE = slice(0, 384)
STRUCTURED_SLICE = slice(384, 512)
TEMPORAL_SLICE = slice(512, 528)


def _make_request(**overrides) -> RetrievalRequest:
    defaults = dict(
        instrument="EURUSD",
        timestamp=datetime(2024, 5, 6, 9, 15, tzinfo=timezone.utc),
        narrative="Price swept the Asian low before reversing bullish through the FVG.",
    )
    defaults.update(overrides)
    return RetrievalRequest(**defaults)


class TestOutputShape:
    def test_returns_528_floats(self):
        vector = generate_query_embedding(_make_request())
        assert len(vector) == COMBINED_DIM
        assert all(isinstance(v, float) for v in vector)

    def test_no_nan_values(self):
        vector = generate_query_embedding(_make_request())
        assert not np.isnan(np.asarray(vector)).any()

    def test_no_inf_values(self):
        vector = generate_query_embedding(_make_request())
        assert not np.isinf(np.asarray(vector)).any()

    def test_not_the_degenerate_zero_vector(self):
        """Regression guard: the original stub returned [0.0] * 528."""
        vector = generate_query_embedding(_make_request())
        assert any(v != 0.0 for v in vector)


class TestDeterminism:
    def test_same_request_produces_same_vector(self):
        request = _make_request()
        v1 = generate_query_embedding(request)
        v2 = generate_query_embedding(request)
        np.testing.assert_array_almost_equal(v1, v2)


class TestNarrativeComponent:
    def test_matches_narrative_embedder_scaled_by_weight(self):
        request = _make_request(narrative="HTF bullish bias with FVG present at discount.")
        vector = np.asarray(generate_query_embedding(request))

        expected = np.asarray(
            NarrativeEmbedder().embed(request.narrative), dtype=np.float32
        ) * 0.4
        np.testing.assert_array_almost_equal(vector[NARRATIVE_SLICE], expected, decimal=4)

    def test_missing_narrative_does_not_raise(self):
        request = _make_request(narrative=None)
        vector = generate_query_embedding(request)
        assert len(vector) == COMBINED_DIM

    def test_different_narratives_produce_different_vectors(self):
        v1 = generate_query_embedding(_make_request(narrative="Bullish sweep of Asian low."))
        v2 = generate_query_embedding(_make_request(narrative="Bearish rejection at premium."))
        assert v1 != v2


class TestTemporalComponent:
    def test_matches_temporal_embedder_scaled_by_weight(self):
        request = _make_request()
        vector = np.asarray(generate_query_embedding(request))

        expected = np.asarray(
            TemporalEmbedder().encode(request.timestamp), dtype=np.float32
        ) * 0.2
        np.testing.assert_array_almost_equal(vector[TEMPORAL_SLICE], expected, decimal=4)

    def test_different_timestamps_produce_different_temporal_slice(self):
        v1 = np.asarray(
            generate_query_embedding(_make_request(timestamp=datetime(2024, 5, 6, 2, 0, tzinfo=timezone.utc)))
        )
        v2 = np.asarray(
            generate_query_embedding(_make_request(timestamp=datetime(2024, 5, 6, 14, 0, tzinfo=timezone.utc)))
        )
        assert not np.allclose(v1[TEMPORAL_SLICE], v2[TEMPORAL_SLICE])


class TestStructuredComponent:
    def test_bullish_vs_bearish_bias_differ(self):
        v1 = np.asarray(generate_query_embedding(_make_request(htf_open_bias="BULLISH")))
        v2 = np.asarray(generate_query_embedding(_make_request(htf_open_bias="BEARISH")))
        assert not np.allclose(v1[STRUCTURED_SLICE], v2[STRUCTURED_SLICE])

    def test_confluence_factor_count_affects_structured_slice(self):
        v1 = np.asarray(generate_query_embedding(_make_request(confluence_factors=None)))
        v2 = np.asarray(
            generate_query_embedding(
                _make_request(confluence_factors=["BOS", "FVG", "LIQUIDITY_SWEEP"])
            )
        )
        assert not np.allclose(v1[STRUCTURED_SLICE], v2[STRUCTURED_SLICE])

    def test_missing_htf_structure_and_pd_arrays_does_not_raise(self):
        request = _make_request(htf_structure=None, pd_arrays=None)
        vector = generate_query_embedding(request)
        assert len(vector) == COMBINED_DIM

    def test_pd_array_flags_affect_structured_slice(self):
        v1 = np.asarray(generate_query_embedding(_make_request(pd_arrays=None)))
        v2 = np.asarray(
            generate_query_embedding(
                _make_request(pd_arrays={"bos_detected": True, "fvg_present": True})
            )
        )
        assert not np.allclose(v1[STRUCTURED_SLICE], v2[STRUCTURED_SLICE])
