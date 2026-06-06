"""
TDD – Task 4.5: Tests for MultiModalEmbedder pipeline component.

RED  phase: tests that define the expected behaviour of MultiModalEmbedder
            before the implementation exists.
GREEN phase: implementation in scripts/rag/utils/multi_modal_embedder.py
             satisfies all assertions.
REFACTOR: embedding validation (dimension check, NaN check, type coercion).

Validates: Requirements FR-RAG-2 (multi-modal embeddings – combined component).

Architecture (from rag-pipeline.md):
  - Narrative embedding:   384-dim, weight 40%  → narrative_emb * 0.4
  - Structured embedding:  128-dim, weight 40%  → structured_emb * 0.4
  - Temporal embedding:     16-dim, weight 20%  → temporal_emb * 0.2
  - Combined:              528-dim (concatenation of the three weighted components)

Combination formula:
    combined = np.concatenate([
        narrative_emb  * 0.4,   # → 384-dim slice
        structured_emb * 0.4,   # → 128-dim slice
        temporal_emb   * 0.2,   # →  16-dim slice
    ])

Invariants enforced (critical for downstream Qdrant storage):
  - Output is always exactly 528-dim
  - Output dtype is float32
  - No NaN values in output
  - No Inf values in output
  - Same input always produces same output (determinism)
  - Weights are applied correctly: slice proportions match 40/40/20
  - embed() raises on invalid inputs
"""

from __future__ import annotations

import sys
import os

_WORKSPACE_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..")
)
if _WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, _WORKSPACE_ROOT)

from datetime import datetime, timezone
from typing import Optional

import numpy as np
import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

from scripts.rag.utils.setup_enricher import EnrichedSetup

# Import under test — will fail (RED phase) until multi_modal_embedder.py is created
from scripts.rag.utils.multi_modal_embedder import MultiModalEmbedder

COMBINED_DIM: int = 528
NARRATIVE_DIM: int = 384
STRUCTURED_DIM: int = 128
TEMPORAL_DIM: int = 16

NARRATIVE_WEIGHT: float = 0.4
STRUCTURED_WEIGHT: float = 0.4
TEMPORAL_WEIGHT: float = 0.2


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_enriched_setup(**overrides) -> EnrichedSetup:
    """Return a valid EnrichedSetup with sensible defaults, allowing field overrides."""
    defaults = dict(
        trade_id="TRD-001",
        timestamp=datetime(2024, 3, 15, 9, 15, 0, tzinfo=timezone.utc),
        instrument="EURUSD",
        direction="BUY",
        entry_price=1.0850,
        exit_price=1.0900,
        stop_loss=1.0820,
        take_profit=1.0920,
        r_multiple=2.0,
        outcome_result="WIN",
        htf_timeframe="H1",
        htf_open=1.0840,
        htf_high=1.0950,
        htf_low=1.0800,
        htf_open_bias="BULLISH",
        htf_high_proximity_pct=66.67,
        htf_low_proximity_pct=33.33,
        htf_body_pct=60.0,
        htf_close_position=50.0,
        bos_detected=True,
        choch_detected=False,
        fvg_present=True,
        liquidity_sweep=True,
        swing_high_distance=0.0050,
        swing_low_distance=0.0030,
        htf_trend_bias="BULLISH",
        time_window="LONDON_KILLZONE",
        narrative_phase="MANIPULATION",
        time_window_weight=0.9,
        is_killzone=True,
        narrative="Price swept Asian low before reversing bullish.",
        confluence_count=4,
        full_setup=None,
    )
    defaults.update(overrides)
    return EnrichedSetup(**defaults)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def embedder() -> MultiModalEmbedder:
    """Shared MultiModalEmbedder instance — model loads once per test session."""
    return MultiModalEmbedder()


@pytest.fixture
def sample_setup() -> EnrichedSetup:
    return _make_enriched_setup()


# ---------------------------------------------------------------------------
# 1. Instantiation tests
# ---------------------------------------------------------------------------


class TestMultiModalEmbedderInstantiation:
    """Verify MultiModalEmbedder can be created and exposes the expected interface."""

    def test_instantiates_without_error(self):
        """MultiModalEmbedder() should not raise on construction."""
        emb = MultiModalEmbedder()
        assert emb is not None

    def test_exposes_dim_attribute(self, embedder: MultiModalEmbedder):
        """MultiModalEmbedder must expose .dim == 528."""
        assert embedder.dim == COMBINED_DIM

    def test_has_embed_method(self, embedder: MultiModalEmbedder):
        """MultiModalEmbedder exposes an embed() method."""
        assert callable(getattr(embedder, "embed", None))

    def test_exposes_narrative_weight(self, embedder: MultiModalEmbedder):
        """MultiModalEmbedder exposes .narrative_weight == 0.4."""
        assert embedder.narrative_weight == pytest.approx(NARRATIVE_WEIGHT)

    def test_exposes_structured_weight(self, embedder: MultiModalEmbedder):
        """MultiModalEmbedder exposes .structured_weight == 0.4."""
        assert embedder.structured_weight == pytest.approx(STRUCTURED_WEIGHT)

    def test_exposes_temporal_weight(self, embedder: MultiModalEmbedder):
        """MultiModalEmbedder exposes .temporal_weight == 0.2."""
        assert embedder.temporal_weight == pytest.approx(TEMPORAL_WEIGHT)


# ---------------------------------------------------------------------------
# 2. Output shape and type tests (RED → GREEN)
# ---------------------------------------------------------------------------


class TestOutputShapeAndType:
    """Verify embed() produces a 528-dim float32 array."""

    def test_embed_returns_numpy_array(
        self, embedder: MultiModalEmbedder, sample_setup: EnrichedSetup
    ):
        """embed() must return a numpy ndarray."""
        result = embedder.embed(sample_setup)
        assert isinstance(result, np.ndarray)

    def test_embed_returns_528_dim(
        self, embedder: MultiModalEmbedder, sample_setup: EnrichedSetup
    ):
        """embed() must return exactly 528-dimensional vector."""
        result = embedder.embed(sample_setup)
        assert result.shape == (COMBINED_DIM,), (
            f"Expected shape ({COMBINED_DIM},), got {result.shape}"
        )

    def test_embed_dtype_is_float32(
        self, embedder: MultiModalEmbedder, sample_setup: EnrichedSetup
    ):
        """embed() must return a float32 array for Qdrant compatibility."""
        result = embedder.embed(sample_setup)
        assert result.dtype == np.float32

    def test_embed_is_1d(
        self, embedder: MultiModalEmbedder, sample_setup: EnrichedSetup
    ):
        """embed() must return a 1-D (not 2-D) array."""
        result = embedder.embed(sample_setup)
        assert result.ndim == 1


# ---------------------------------------------------------------------------
# 3. No NaN / Inf tests
# ---------------------------------------------------------------------------


class TestNoNaNOrInf:
    """Verify embed() output never contains NaN or Inf values."""

    def test_embed_no_nan(
        self, embedder: MultiModalEmbedder, sample_setup: EnrichedSetup
    ):
        """embed() output must not contain NaN values."""
        result = embedder.embed(sample_setup)
        assert not np.isnan(result).any(), "NaN values found in combined embedding"

    def test_embed_no_inf(
        self, embedder: MultiModalEmbedder, sample_setup: EnrichedSetup
    ):
        """embed() output must not contain Inf values."""
        result = embedder.embed(sample_setup)
        assert not np.isinf(result).any(), "Inf values found in combined embedding"

    def test_embed_no_nan_all_zero_features(self, embedder: MultiModalEmbedder):
        """Edge case: all numeric features at minimum — still no NaN."""
        setup = _make_enriched_setup(
            htf_high_proximity_pct=0.0,
            htf_low_proximity_pct=0.0,
            htf_body_pct=0.0,
            htf_close_position=0.0,
            htf_open_bias="NEUTRAL",
            bos_detected=False,
            choch_detected=False,
            fvg_present=False,
            liquidity_sweep=False,
            swing_high_distance=0.0,
            swing_low_distance=0.0,
            time_window_weight=0.0,
            is_killzone=False,
            r_multiple=0.0,
            outcome_result="LOSS",
            confluence_count=0,
            narrative="",
        )
        result = embedder.embed(setup)
        assert result.shape == (COMBINED_DIM,)
        assert not np.isnan(result).any()
        assert not np.isinf(result).any()

    def test_embed_no_nan_max_features(self, embedder: MultiModalEmbedder):
        """Edge case: all numeric features at maximum — still no NaN."""
        setup = _make_enriched_setup(
            htf_high_proximity_pct=100.0,
            htf_low_proximity_pct=100.0,
            htf_body_pct=100.0,
            htf_close_position=100.0,
            htf_open_bias="BULLISH",
            bos_detected=True,
            choch_detected=True,
            fvg_present=True,
            liquidity_sweep=True,
            swing_high_distance=1.0,
            swing_low_distance=1.0,
            time_window_weight=1.0,
            is_killzone=True,
            r_multiple=10.0,
            outcome_result="WIN",
            confluence_count=10,
            narrative=(
                "HTF bullish bias confirmed in Discount of Dealing Range. "
                "Price formed CHoCH and BOS after London Killzone liquidity sweep. "
                "FVG and OB present as PD arrays at confluence of 10."
            ),
        )
        result = embedder.embed(setup)
        assert result.shape == (COMBINED_DIM,)
        assert not np.isnan(result).any()
        assert not np.isinf(result).any()


# ---------------------------------------------------------------------------
# 4. Determinism tests
# ---------------------------------------------------------------------------


class TestDeterminism:
    """The same setup must always produce the same 528-dim embedding."""

    def test_embed_is_deterministic(
        self, embedder: MultiModalEmbedder, sample_setup: EnrichedSetup
    ):
        """Calling embed() twice on the same setup returns identical arrays."""
        v1 = embedder.embed(sample_setup)
        v2 = embedder.embed(sample_setup)
        np.testing.assert_array_equal(v1, v2)

    def test_embed_different_setups_differ(self, embedder: MultiModalEmbedder):
        """Two distinct setups should not produce identical embeddings."""
        setup_a = _make_enriched_setup(
            outcome_result="WIN",
            r_multiple=3.0,
            htf_open_bias="BULLISH",
            narrative="Price swept Asian low before reversing bullish.",
        )
        setup_b = _make_enriched_setup(
            outcome_result="LOSS",
            r_multiple=-1.0,
            htf_open_bias="BEARISH",
            narrative="HTF bearish premium — price failed to break Asian high.",
        )
        v_a = embedder.embed(setup_a)
        v_b = embedder.embed(setup_b)
        assert not np.allclose(v_a, v_b), (
            "Distinct setups produced identical combined embeddings"
        )


# ---------------------------------------------------------------------------
# 5. Weight application tests
# ---------------------------------------------------------------------------


class TestWeightApplication:
    """Verify the 40/40/20 weight scheme is applied to the correct vector slices."""

    def test_combined_vector_has_correct_slice_lengths(
        self, embedder: MultiModalEmbedder, sample_setup: EnrichedSetup
    ):
        """
        The 528-dim combined vector is structured as:
          [0:384]   narrative  * 0.4
          [384:512] structured * 0.4
          [512:528] temporal   * 0.2
        """
        result = embedder.embed(sample_setup)
        # Verify slice lengths sum to 528
        assert NARRATIVE_DIM + STRUCTURED_DIM + TEMPORAL_DIM == COMBINED_DIM
        assert result.shape[0] == COMBINED_DIM

    def test_narrative_slice_reflects_weight(self, embedder: MultiModalEmbedder):
        """
        Changing the narrative only changes the [0:384] slice.
        The [384:528] slices (structured + temporal) must remain the same when
        the non-narrative fields are identical.
        """
        setup_a = _make_enriched_setup(
            narrative="Price swept Asian low before reversing bullish.",
        )
        setup_b = _make_enriched_setup(
            narrative="Bearish FVG in Premium of Dealing Range at London open.",
        )
        v_a = embedder.embed(setup_a)
        v_b = embedder.embed(setup_b)

        # Narrative slices must differ
        assert not np.allclose(v_a[:NARRATIVE_DIM], v_b[:NARRATIVE_DIM]), (
            "Narrative slice did not change when narrative text changed"
        )
        # Structured + temporal slices must be identical (only narrative changed)
        np.testing.assert_array_almost_equal(
            v_a[NARRATIVE_DIM:],
            v_b[NARRATIVE_DIM:],
            decimal=5,
            err_msg="Structured/temporal slices changed when only narrative changed",
        )

    def test_structured_slice_reflects_weight(self, embedder: MultiModalEmbedder):
        """
        Changing structured fields only changes the [384:512] slice.
        The [0:384] narrative slice must remain identical when narrative is unchanged.
        """
        setup_a = _make_enriched_setup(htf_open_bias="BULLISH", outcome_result="WIN")
        setup_b = _make_enriched_setup(htf_open_bias="BEARISH", outcome_result="LOSS")

        v_a = embedder.embed(setup_a)
        v_b = embedder.embed(setup_b)

        # Narrative slices must be identical (same narrative text)
        np.testing.assert_array_almost_equal(
            v_a[:NARRATIVE_DIM],
            v_b[:NARRATIVE_DIM],
            decimal=5,
            err_msg="Narrative slice changed when only structured fields changed",
        )
        # Structured slice must differ
        assert not np.allclose(
            v_a[NARRATIVE_DIM:NARRATIVE_DIM + STRUCTURED_DIM],
            v_b[NARRATIVE_DIM:NARRATIVE_DIM + STRUCTURED_DIM],
        ), "Structured slice did not change when HTF bias changed"

    def test_temporal_slice_reflects_weight(self, embedder: MultiModalEmbedder):
        """
        Changing the timestamp only changes the [512:528] slice.
        """
        setup_morning = _make_enriched_setup(
            timestamp=datetime(2024, 3, 15, 9, 15, 0, tzinfo=timezone.utc)
        )
        setup_afternoon = _make_enriched_setup(
            timestamp=datetime(2024, 3, 15, 14, 30, 0, tzinfo=timezone.utc)
        )

        v_morning = embedder.embed(setup_morning)
        v_afternoon = embedder.embed(setup_afternoon)

        # Narrative + structured slices must be identical (same setup data)
        np.testing.assert_array_almost_equal(
            v_morning[:NARRATIVE_DIM + STRUCTURED_DIM],
            v_afternoon[:NARRATIVE_DIM + STRUCTURED_DIM],
            decimal=5,
            err_msg="Narrative/structured slices changed when only timestamp changed",
        )
        # Temporal slice must differ
        assert not np.allclose(
            v_morning[NARRATIVE_DIM + STRUCTURED_DIM:],
            v_afternoon[NARRATIVE_DIM + STRUCTURED_DIM:],
        ), "Temporal slice did not change when timestamp changed"


# ---------------------------------------------------------------------------
# 6. Input validation tests (REFACTOR)
# ---------------------------------------------------------------------------


class TestInputValidation:
    """Verify MultiModalEmbedder validates its input and raises on bad data."""

    def test_embed_raises_on_none(self, embedder: MultiModalEmbedder):
        """embed() must raise TypeError or ValueError when passed None."""
        with pytest.raises((TypeError, AttributeError, ValueError)):
            embedder.embed(None)  # type: ignore[arg-type]

    def test_embed_raises_on_dict(self, embedder: MultiModalEmbedder):
        """embed() must raise TypeError when passed a raw dict."""
        with pytest.raises((TypeError, AttributeError, ValueError)):
            embedder.embed({"instrument": "EURUSD"})  # type: ignore[arg-type]

    def test_embed_raises_on_string(self, embedder: MultiModalEmbedder):
        """embed() must raise TypeError when passed a string."""
        with pytest.raises((TypeError, AttributeError, ValueError)):
            embedder.embed("EURUSD setup")  # type: ignore[arg-type]

    def test_embed_raises_on_integer(self, embedder: MultiModalEmbedder):
        """embed() must raise TypeError when passed an integer."""
        with pytest.raises((TypeError, AttributeError, ValueError)):
            embedder.embed(42)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 7. validate_embedding() tests (REFACTOR)
# ---------------------------------------------------------------------------


class TestEmbeddingValidation:
    """Verify the validate_embedding() utility raises on malformed vectors."""

    def test_validate_correct_embedding_passes(self, embedder: MultiModalEmbedder):
        """A valid 528-dim float32 embedding passes validation without raising."""
        valid = np.zeros(COMBINED_DIM, dtype=np.float32)
        embedder.validate_embedding(valid)  # must not raise

    def test_validate_wrong_dimension_raises(self, embedder: MultiModalEmbedder):
        """validate_embedding() raises ValueError for wrong dimension."""
        wrong_dim = np.zeros(256, dtype=np.float32)
        with pytest.raises(ValueError, match="528"):
            embedder.validate_embedding(wrong_dim)

    def test_validate_nan_raises(self, embedder: MultiModalEmbedder):
        """validate_embedding() raises ValueError when embedding contains NaN."""
        with_nan = np.zeros(COMBINED_DIM, dtype=np.float32)
        with_nan[42] = float("nan")
        with pytest.raises(ValueError, match="[Nn][Aa][Nn]"):
            embedder.validate_embedding(with_nan)

    def test_validate_inf_raises(self, embedder: MultiModalEmbedder):
        """validate_embedding() raises ValueError when embedding contains Inf."""
        with_inf = np.zeros(COMBINED_DIM, dtype=np.float32)
        with_inf[100] = float("inf")
        with pytest.raises(ValueError, match="[Ii]nf"):
            embedder.validate_embedding(with_inf)

    def test_validate_negative_inf_raises(self, embedder: MultiModalEmbedder):
        """validate_embedding() raises ValueError for negative infinity."""
        with_neg_inf = np.zeros(COMBINED_DIM, dtype=np.float32)
        with_neg_inf[200] = float("-inf")
        with pytest.raises(ValueError, match="[Ii]nf"):
            embedder.validate_embedding(with_neg_inf)

    def test_validate_non_array_raises(self, embedder: MultiModalEmbedder):
        """validate_embedding() raises TypeError when passed a non-array."""
        with pytest.raises((TypeError, ValueError)):
            embedder.validate_embedding([0.0] * COMBINED_DIM)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 8. embed_and_validate() convenience method tests
# ---------------------------------------------------------------------------


class TestEmbedAndValidate:
    """Verify embed_and_validate() returns a validated 528-dim embedding."""

    def test_embed_and_validate_returns_valid_embedding(
        self, embedder: MultiModalEmbedder, sample_setup: EnrichedSetup
    ):
        """embed_and_validate() must return a 528-dim float32 array with no NaN."""
        result = embedder.embed_and_validate(sample_setup)
        assert isinstance(result, np.ndarray)
        assert result.shape == (COMBINED_DIM,)
        assert result.dtype == np.float32
        assert not np.isnan(result).any()
        assert not np.isinf(result).any()

    def test_embed_and_validate_matches_embed(
        self, embedder: MultiModalEmbedder, sample_setup: EnrichedSetup
    ):
        """embed_and_validate() must return the same array as embed()."""
        v1 = embedder.embed(sample_setup)
        v2 = embedder.embed_and_validate(sample_setup)
        np.testing.assert_array_equal(v1, v2)


# ---------------------------------------------------------------------------
# 9. Instruments and direction variety tests
# ---------------------------------------------------------------------------


class TestVariety:
    """Verify embed() works correctly for all supported instruments and directions."""

    @pytest.mark.parametrize("instrument", [
        "EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "US500", "US30",
    ])
    def test_embed_supported_instruments(
        self, embedder: MultiModalEmbedder, instrument: str
    ):
        """embed() must produce valid 528-dim vector for all supported instruments."""
        setup = _make_enriched_setup(instrument=instrument)
        result = embedder.embed(setup)
        assert result.shape == (COMBINED_DIM,)
        assert not np.isnan(result).any()

    @pytest.mark.parametrize("direction", ["BUY", "SELL"])
    def test_embed_buy_and_sell(self, embedder: MultiModalEmbedder, direction: str):
        """embed() must produce valid 528-dim vector for both trade directions."""
        setup = _make_enriched_setup(direction=direction)
        result = embedder.embed(setup)
        assert result.shape == (COMBINED_DIM,)
        assert not np.isnan(result).any()

    @pytest.mark.parametrize("htf_bias", ["BULLISH", "BEARISH", "NEUTRAL"])
    def test_embed_htf_bias_variants(
        self, embedder: MultiModalEmbedder, htf_bias: str
    ):
        """embed() must produce valid 528-dim vector for all HTF bias values."""
        setup = _make_enriched_setup(htf_open_bias=htf_bias)
        result = embedder.embed(setup)
        assert result.shape == (COMBINED_DIM,)
        assert not np.isnan(result).any()


# ---------------------------------------------------------------------------
# 10. Property-based tests
# ---------------------------------------------------------------------------


@pytest.mark.property
class TestMultiModalEmbedderProperties:
    """
    Property-based tests enforcing core invariants across arbitrary valid setups.

    Validates: Requirements FR-RAG-2
    """

    @given(
        htf_bias=st.sampled_from(["BULLISH", "BEARISH", "NEUTRAL"]),
        outcome=st.sampled_from(["WIN", "LOSS"]),
        r_mult=st.floats(min_value=-5.0, max_value=15.0, allow_nan=False, allow_infinity=False),
        conf_count=st.integers(min_value=0, max_value=12),
        is_kz=st.booleans(),
        tw_weight=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
        bos=st.booleans(),
        choch=st.booleans(),
    )
    @settings(
        max_examples=30,
        suppress_health_check=[HealthCheck.too_slow],
        deadline=None,
    )
    def test_embed_always_528_dim(
        self,
        htf_bias: str,
        outcome: str,
        r_mult: float,
        conf_count: int,
        is_kz: bool,
        tw_weight: float,
        bos: bool,
        choch: bool,
    ) -> None:
        """For arbitrary valid EnrichedSetup, embed() always returns (528,).

        Validates: Requirements FR-RAG-2
        """
        setup = _make_enriched_setup(
            htf_open_bias=htf_bias,
            outcome_result=outcome,
            r_multiple=r_mult,
            confluence_count=conf_count,
            is_killzone=is_kz,
            time_window_weight=tw_weight,
            bos_detected=bos,
            choch_detected=choch,
        )
        emb = MultiModalEmbedder()
        result = emb.embed(setup)
        assert result.shape == (COMBINED_DIM,), (
            f"Expected ({COMBINED_DIM},), got {result.shape}"
        )

    @given(
        htf_bias=st.sampled_from(["BULLISH", "BEARISH", "NEUTRAL"]),
        outcome=st.sampled_from(["WIN", "LOSS"]),
        r_mult=st.floats(min_value=-5.0, max_value=15.0, allow_nan=False, allow_infinity=False),
        conf_count=st.integers(min_value=0, max_value=12),
    )
    @settings(
        max_examples=30,
        suppress_health_check=[HealthCheck.too_slow],
        deadline=None,
    )
    def test_embed_never_contains_nan(
        self,
        htf_bias: str,
        outcome: str,
        r_mult: float,
        conf_count: int,
    ) -> None:
        """For arbitrary valid EnrichedSetup, embed() output never contains NaN.

        Validates: Requirements FR-RAG-2
        """
        setup = _make_enriched_setup(
            htf_open_bias=htf_bias,
            outcome_result=outcome,
            r_multiple=r_mult,
            confluence_count=conf_count,
        )
        emb = MultiModalEmbedder()
        result = emb.embed(setup)
        assert not np.isnan(result).any(), (
            f"NaN values found for htf_bias={htf_bias}, outcome={outcome}"
        )

    @given(
        htf_bias=st.sampled_from(["BULLISH", "BEARISH", "NEUTRAL"]),
        outcome=st.sampled_from(["WIN", "LOSS"]),
    )
    @settings(
        max_examples=20,
        suppress_health_check=[HealthCheck.too_slow],
        deadline=None,
    )
    def test_embed_always_float32(
        self,
        htf_bias: str,
        outcome: str,
    ) -> None:
        """For any valid EnrichedSetup, embed() always returns dtype float32.

        Validates: Requirements FR-RAG-2
        """
        setup = _make_enriched_setup(htf_open_bias=htf_bias, outcome_result=outcome)
        emb = MultiModalEmbedder()
        result = emb.embed(setup)
        assert result.dtype == np.float32, (
            f"Expected float32, got {result.dtype}"
        )
