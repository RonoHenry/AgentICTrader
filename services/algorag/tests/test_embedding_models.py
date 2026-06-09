"""
TDD – Task 4.1: Tests for the NarrativeEmbeddingModel and model loading utility.

RED  phase: tests that fail before implementation exists.
GREEN phase: implementation in services/algorag/embedding_models.py satisfies all assertions.
REFACTOR: singleton caching, batch processing, error handling.

Validates: Requirements FR-RAG-2 (multi-modal embeddings, narrative component is 384-dim).

Invariants enforced:
- Output is always exactly 384-dim
- No NaN values in output
- Same input always produces same output (determinism)
- Singleton caching: get_embedding_model() returns same instance on repeated calls
"""

from __future__ import annotations

import numpy as np
import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

# ---------------------------------------------------------------------------
# Import under test — will fail (RED) until embedding_models.py is created
# ---------------------------------------------------------------------------
from services.algorag.embedding_models import (
    NarrativeEmbeddingModel,
    get_embedding_model,
)

NARRATIVE_DIM = 384


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def model() -> NarrativeEmbeddingModel:
    """Shared model instance for the test module — loads once."""
    return get_embedding_model()


# ---------------------------------------------------------------------------
# 1. Model loading tests
# ---------------------------------------------------------------------------


class TestModelLoading:
    """Verify the model loads and the singleton cache works."""

    def test_model_loads_successfully(self):
        """NarrativeEmbeddingModel can be instantiated without error."""
        m = NarrativeEmbeddingModel()
        assert m is not None

    def test_singleton_caching(self):
        """get_embedding_model() returns the same instance on repeated calls."""
        m1 = get_embedding_model()
        m2 = get_embedding_model()
        assert m1 is m2

    def test_model_has_encode_method(self, model):
        """Model exposes an encode() method."""
        assert callable(getattr(model, "encode", None))

    def test_model_has_encode_batch_method(self, model):
        """Model exposes an encode_batch() method."""
        assert callable(getattr(model, "encode_batch", None))


# ---------------------------------------------------------------------------
# 2. Single text encoding tests
# ---------------------------------------------------------------------------


class TestSingleTextEncoding:
    """Verify encode(text) returns a 384-dim numpy array with no NaN values."""

    def test_encode_returns_numpy_array(self, model):
        """encode() returns a numpy ndarray."""
        result = model.encode("Price swept Asian low before reversing bullish.")
        assert isinstance(result, np.ndarray)

    def test_encode_returns_384_dim(self, model):
        """encode() returns exactly 384-dimensional vector."""
        result = model.encode("Price swept Asian low before reversing bullish.")
        assert result.shape == (NARRATIVE_DIM,)

    def test_no_nan_values_single(self, model):
        """encode() output contains no NaN values."""
        result = model.encode("Bearish FVG detected in premium of dealing range.")
        assert not np.isnan(result).any()

    def test_encode_short_text(self, model):
        """encode() handles a single-word input."""
        result = model.encode("BOS")
        assert result.shape == (NARRATIVE_DIM,)
        assert not np.isnan(result).any()

    def test_encode_long_text(self, model):
        """encode() handles a long narrative without error."""
        long_text = (
            "Price traded up into the premium of the HTF dealing range, "
            "swept the Asian session high liquidity pool, formed a CHoCH on the "
            "M5 timeframe, and delivered bearish displacement into a mitigation "
            "block sitting at the 61.8% Fibonacci retracement level during the "
            "London Killzone. The confluence factors included: HTF bearish bias, "
            "FVG present, BOS confirmed, and liquidity sweep detected."
        ) * 3
        result = model.encode(long_text)
        assert result.shape == (NARRATIVE_DIM,)
        assert not np.isnan(result).any()


# ---------------------------------------------------------------------------
# 3. Determinism tests
# ---------------------------------------------------------------------------


class TestDeterminism:
    """Same input must always produce the same output vector."""

    def test_determinism_single_encode(self, model):
        """Calling encode() twice on the same text returns identical vectors."""
        text = "HTF bullish bias with FVG present at discount."
        v1 = model.encode(text)
        v2 = model.encode(text)
        np.testing.assert_array_equal(v1, v2)

    def test_determinism_batch_encode(self, model):
        """Calling encode_batch() twice on the same texts returns identical arrays."""
        texts = [
            "London Killzone BOS confirmed.",
            "NY session liquidity sweep detected.",
        ]
        b1 = model.encode_batch(texts)
        b2 = model.encode_batch(texts)
        np.testing.assert_array_equal(b1, b2)


# ---------------------------------------------------------------------------
# 4. Batch encoding tests
# ---------------------------------------------------------------------------


class TestBatchEncoding:
    """Verify encode_batch() returns an array of shape (N, 384)."""

    def test_encode_batch_single_text(self, model):
        """encode_batch() with one text returns shape (1, 384)."""
        result = model.encode_batch(["Single narrative text."])
        assert result.shape == (1, NARRATIVE_DIM)

    def test_encode_batch_returns_correct_shape(self, model):
        """encode_batch() with N texts returns shape (N, 384)."""
        texts = [
            "BOS on M5.",
            "FVG in premium zone.",
            "Liquidity sweep below Asian low.",
            "CHoCH confirmed on M1.",
            "HTF bearish, entering at discount.",
        ]
        result = model.encode_batch(texts)
        assert result.shape == (len(texts), NARRATIVE_DIM)

    def test_encode_batch_no_nan(self, model):
        """encode_batch() output contains no NaN values."""
        texts = ["First setup narrative.", "Second setup narrative.", "Third."]
        result = model.encode_batch(texts)
        assert not np.isnan(result).any()

    def test_encode_batch_consistent_with_single(self, model):
        """Each row of encode_batch() matches the corresponding encode() call."""
        texts = ["Setup A narrative.", "Setup B narrative."]
        batch_result = model.encode_batch(texts)
        for i, text in enumerate(texts):
            single_result = model.encode(text)
            np.testing.assert_array_almost_equal(batch_result[i], single_result)


# ---------------------------------------------------------------------------
# 5. Property-based tests
# ---------------------------------------------------------------------------


@pytest.mark.property
class TestEmbeddingProperties:
    """
    Property-based tests enforcing invariants across arbitrary non-empty strings.

    Validates: Requirements FR-RAG-2
    """

    @given(text=st.text(min_size=1, max_size=500))
    @settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow])
    def test_output_is_always_384_dim(self, text: str) -> None:
        """For any non-empty string, encode() always returns a 384-dim vector.

        Validates: Requirements FR-RAG-2
        """
        model = get_embedding_model()
        result = model.encode(text)
        assert result.shape == (NARRATIVE_DIM,), (
            f"Expected shape ({NARRATIVE_DIM},), got {result.shape} for text: {text!r}"
        )

    @given(text=st.text(min_size=1, max_size=500))
    @settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow])
    def test_output_has_no_nan_values(self, text: str) -> None:
        """For any non-empty string, encode() output never contains NaN.

        Validates: Requirements FR-RAG-2
        """
        model = get_embedding_model()
        result = model.encode(text)
        assert not np.isnan(result).any(), (
            f"NaN values found in embedding for text: {text!r}"
        )
