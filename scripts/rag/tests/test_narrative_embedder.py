"""
TDD – Task 4.2: Tests for NarrativeEmbedder pipeline component.

RED  phase: tests that define the expected behaviour of NarrativeEmbedder
            before the implementation exists.
GREEN phase: implementation in scripts/rag/utils/narrative_embedder.py
             satisfies all assertions.
REFACTOR: batch_size parameter, validation, error handling.

Validates: Requirements FR-RAG-2 (multi-modal embeddings – narrative component).

Invariants enforced:
- Output is always exactly 384-dim
- No NaN values in output
- Same input always produces same output (determinism)
- Batch output shape is (N, 384) for N narratives
- Empty batch returns empty array of shape (0, 384)
- Non-string inputs raise ValueError
"""

from __future__ import annotations

import numpy as np
import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

from scripts.rag.utils.narrative_embedder import NarrativeEmbedder

NARRATIVE_DIM = 384


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def embedder() -> NarrativeEmbedder:
    """Shared NarrativeEmbedder instance — model loads once per test session."""
    return NarrativeEmbedder()


# ---------------------------------------------------------------------------
# 1. Instantiation tests
# ---------------------------------------------------------------------------


class TestNarrativeEmbedderInstantiation:
    """Verify NarrativeEmbedder can be created and exposes the right interface."""

    def test_instantiates_without_error(self):
        """NarrativeEmbedder() should not raise on construction."""
        emb = NarrativeEmbedder()
        assert emb is not None

    def test_has_embed_method(self, embedder: NarrativeEmbedder):
        """NarrativeEmbedder exposes an embed() single-text method."""
        assert callable(getattr(embedder, "embed", None))

    def test_has_embed_batch_method(self, embedder: NarrativeEmbedder):
        """NarrativeEmbedder exposes an embed_batch() method."""
        assert callable(getattr(embedder, "embed_batch", None))

    def test_exposes_dim_attribute(self, embedder: NarrativeEmbedder):
        """NarrativeEmbedder exposes a .dim attribute equal to 384."""
        assert embedder.dim == NARRATIVE_DIM


# ---------------------------------------------------------------------------
# 2. Single narrative embedding tests (RED → GREEN)
# ---------------------------------------------------------------------------


class TestSingleNarrativeEmbedding:
    """Verify embed() encodes a single narrative string to a 384-dim vector."""

    def test_embed_returns_numpy_array(self, embedder: NarrativeEmbedder):
        """embed() must return a numpy ndarray."""
        result = embedder.embed("Price swept Asian low before reversing bullish.")
        assert isinstance(result, np.ndarray)

    def test_embed_returns_384_dim(self, embedder: NarrativeEmbedder):
        """embed() must return exactly 384-dimensional vector."""
        result = embedder.embed("Price swept Asian low before reversing bullish.")
        assert result.shape == (NARRATIVE_DIM,), (
            f"Expected shape ({NARRATIVE_DIM},), got {result.shape}"
        )

    def test_embed_dtype_is_float32(self, embedder: NarrativeEmbedder):
        """embed() must return float32 array (memory-efficient for Qdrant)."""
        result = embedder.embed("HTF bearish bias confirmed at premium.")
        assert result.dtype == np.float32

    def test_embed_no_nan_values(self, embedder: NarrativeEmbedder):
        """embed() output must not contain NaN values."""
        result = embedder.embed("Bearish FVG detected in premium of dealing range.")
        assert not np.isnan(result).any(), "NaN values found in embedding output"

    def test_embed_no_inf_values(self, embedder: NarrativeEmbedder):
        """embed() output must not contain Inf values."""
        result = embedder.embed("BOS on M5 confirmed.")
        assert not np.isinf(result).any(), "Inf values found in embedding output"

    def test_embed_ict_narrative(self, embedder: NarrativeEmbedder):
        """embed() handles a full ICT-style setup narrative."""
        narrative = (
            "During the London Killzone, price swept the Asian session high "
            "liquidity pool and formed a CHoCH on the M5 timeframe. HTF H1 candle "
            "shows bearish bias with price in the Premium of the Dealing Range. "
            "FVG present as PD array, BOS confirmed, confluence count: 4."
        )
        result = embedder.embed(narrative)
        assert result.shape == (NARRATIVE_DIM,)
        assert not np.isnan(result).any()

    def test_embed_single_word(self, embedder: NarrativeEmbedder):
        """embed() handles a single-word narrative without error."""
        result = embedder.embed("BOS")
        assert result.shape == (NARRATIVE_DIM,)
        assert not np.isnan(result).any()

    def test_embed_long_narrative(self, embedder: NarrativeEmbedder):
        """embed() handles unusually long narratives without error or truncation."""
        long_text = (
            "Price traded up into the premium of the HTF dealing range, "
            "swept the Asian session high liquidity pool, formed a CHoCH on "
            "the M5 timeframe, and delivered bearish displacement into a "
            "mitigation block at the London Killzone. "
        ) * 5
        result = embedder.embed(long_text)
        assert result.shape == (NARRATIVE_DIM,)
        assert not np.isnan(result).any()


# ---------------------------------------------------------------------------
# 3. Determinism tests
# ---------------------------------------------------------------------------


class TestDeterminism:
    """The same narrative must always produce the same embedding vector."""

    def test_single_embed_is_deterministic(self, embedder: NarrativeEmbedder):
        """Calling embed() twice on the same text returns identical arrays."""
        text = "HTF bullish bias with FVG present at discount of the dealing range."
        v1 = embedder.embed(text)
        v2 = embedder.embed(text)
        np.testing.assert_array_equal(v1, v2)

    def test_batch_embed_is_deterministic(self, embedder: NarrativeEmbedder):
        """Calling embed_batch() twice on the same texts returns identical arrays."""
        texts = [
            "London Killzone BOS confirmed on M5.",
            "NY AM session liquidity sweep detected below Asian low.",
            "CHoCH on M1 after sweeping swing high.",
        ]
        b1 = embedder.embed_batch(texts)
        b2 = embedder.embed_batch(texts)
        np.testing.assert_array_equal(b1, b2)


# ---------------------------------------------------------------------------
# 4. Batch embedding tests (REFACTOR — batch processing)
# ---------------------------------------------------------------------------


class TestBatchEmbedding:
    """Verify embed_batch() encodes multiple narratives efficiently."""

    def test_embed_batch_returns_numpy_array(self, embedder: NarrativeEmbedder):
        """embed_batch() must return a numpy ndarray."""
        result = embedder.embed_batch(["Narrative A.", "Narrative B."])
        assert isinstance(result, np.ndarray)

    def test_embed_batch_shape_single(self, embedder: NarrativeEmbedder):
        """embed_batch() with 1 text returns shape (1, 384)."""
        result = embedder.embed_batch(["Single narrative text."])
        assert result.shape == (1, NARRATIVE_DIM)

    def test_embed_batch_shape_multiple(self, embedder: NarrativeEmbedder):
        """embed_batch() with N texts returns shape (N, 384)."""
        texts = [
            "BOS on M5 after CHoCH.",
            "FVG in premium zone mitigation.",
            "Liquidity sweep below Asian session low.",
            "HTF H4 bearish bias with displacement.",
            "NY Killzone entry after London sweep.",
        ]
        result = embedder.embed_batch(texts)
        assert result.shape == (len(texts), NARRATIVE_DIM)

    def test_embed_batch_dtype_is_float32(self, embedder: NarrativeEmbedder):
        """embed_batch() must return float32 array."""
        result = embedder.embed_batch(["Setup A.", "Setup B."])
        assert result.dtype == np.float32

    def test_embed_batch_no_nan(self, embedder: NarrativeEmbedder):
        """embed_batch() output must not contain NaN values."""
        texts = ["First setup.", "Second setup.", "Third setup with CHoCH."]
        result = embedder.embed_batch(texts)
        assert not np.isnan(result).any()

    def test_embed_batch_empty_list_returns_empty_array(self, embedder: NarrativeEmbedder):
        """embed_batch([]) must return an empty array of shape (0, 384)."""
        result = embedder.embed_batch([])
        assert result.shape == (0, NARRATIVE_DIM)

    def test_embed_batch_consistent_with_single(self, embedder: NarrativeEmbedder):
        """Each row of embed_batch() must match the corresponding embed() call."""
        texts = [
            "Setup A — BOS confirmed during London Killzone.",
            "Setup B — CHoCH after liquidity sweep at Premium.",
        ]
        batch_result = embedder.embed_batch(texts)
        for i, text in enumerate(texts):
            single_result = embedder.embed(text)
            np.testing.assert_array_almost_equal(
                batch_result[i], single_result, decimal=5,
                err_msg=f"Batch row {i} differs from single embed for text: {text!r}",
            )

    def test_embed_batch_custom_batch_size(self, embedder: NarrativeEmbedder):
        """embed_batch() accepts a custom batch_size without error."""
        texts = [f"Trading setup narrative number {i}." for i in range(10)]
        result = embedder.embed_batch(texts, batch_size=4)
        assert result.shape == (10, NARRATIVE_DIM)
        assert not np.isnan(result).any()

    def test_embed_batch_large(self, embedder: NarrativeEmbedder):
        """embed_batch() handles 50 narratives without error (batch processing)."""
        texts = [
            f"ICT setup {i}: Price formed {'BOS' if i % 2 == 0 else 'CHoCH'} "
            f"during {'London' if i % 3 == 0 else 'NY'} Killzone with "
            f"{'FVG' if i % 4 == 0 else 'OB'} as PD array."
            for i in range(50)
        ]
        result = embedder.embed_batch(texts)
        assert result.shape == (50, NARRATIVE_DIM)
        assert not np.isnan(result).any()


# ---------------------------------------------------------------------------
# 5. Input validation tests
# ---------------------------------------------------------------------------


class TestInputValidation:
    """Verify NarrativeEmbedder validates inputs and raises appropriate errors."""

    def test_embed_raises_on_non_string(self, embedder: NarrativeEmbedder):
        """embed() must raise ValueError when passed a non-string."""
        with pytest.raises((ValueError, TypeError)):
            embedder.embed(12345)  # type: ignore[arg-type]

    def test_embed_raises_on_none(self, embedder: NarrativeEmbedder):
        """embed() must raise ValueError when passed None."""
        with pytest.raises((ValueError, TypeError)):
            embedder.embed(None)  # type: ignore[arg-type]

    def test_embed_batch_raises_on_non_list(self, embedder: NarrativeEmbedder):
        """embed_batch() must raise TypeError when passed a non-list."""
        with pytest.raises((ValueError, TypeError)):
            embedder.embed_batch("single string")  # type: ignore[arg-type]

    def test_embed_batch_raises_on_list_with_non_strings(self, embedder: NarrativeEmbedder):
        """embed_batch() must raise ValueError when list contains non-strings."""
        with pytest.raises((ValueError, TypeError)):
            embedder.embed_batch(["valid narrative", 42, "another valid"])  # type: ignore[list-item]


# ---------------------------------------------------------------------------
# 6. Property-based tests
# ---------------------------------------------------------------------------


@pytest.mark.property
class TestNarrativeEmbedderProperties:
    """
    Property-based tests enforcing invariants across arbitrary non-empty narratives.

    Validates: Requirements FR-RAG-2
    """

    @given(text=st.text(min_size=1, max_size=400))
    @settings(
        max_examples=25,
        suppress_health_check=[HealthCheck.too_slow],
        deadline=None,  # SBERT model load on first example exceeds default 200ms deadline
    )
    def test_embed_always_returns_384_dim(self, text: str) -> None:
        """For any non-empty string, embed() always produces a 384-dim vector.

        Validates: Requirements FR-RAG-2
        """
        emb = NarrativeEmbedder()
        result = emb.embed(text)
        assert result.shape == (NARRATIVE_DIM,), (
            f"Expected ({NARRATIVE_DIM},), got {result.shape} for: {text!r}"
        )

    @given(text=st.text(min_size=1, max_size=400))
    @settings(
        max_examples=25,
        suppress_health_check=[HealthCheck.too_slow],
        deadline=None,
    )
    def test_embed_never_contains_nan(self, text: str) -> None:
        """For any non-empty string, embed() output never contains NaN.

        Validates: Requirements FR-RAG-2
        """
        emb = NarrativeEmbedder()
        result = emb.embed(text)
        assert not np.isnan(result).any(), (
            f"NaN values found for text: {text!r}"
        )

    @given(
        texts=st.lists(
            st.text(min_size=1, max_size=200),
            min_size=1,
            max_size=8,
        )
    )
    @settings(
        max_examples=15,
        suppress_health_check=[HealthCheck.too_slow],
        deadline=None,
    )
    def test_embed_batch_shape_invariant(self, texts: list) -> None:
        """For any non-empty list of strings, embed_batch() shape is (N, 384).

        Validates: Requirements FR-RAG-2
        """
        emb = NarrativeEmbedder()
        result = emb.embed_batch(texts)
        assert result.shape == (len(texts), NARRATIVE_DIM), (
            f"Expected ({len(texts)}, {NARRATIVE_DIM}), got {result.shape}"
        )
