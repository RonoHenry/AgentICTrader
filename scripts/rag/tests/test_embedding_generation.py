"""
TDD – Task 4.6: Unit tests for embedding generation pipeline.

This test module provides a consolidated view of all three embedding types
(narrative, structured, temporal) tested independently and together, with
particular focus on:

  - Each embedder type in isolation (dimensions, dtype, no NaN/Inf)
  - Edge cases: empty narrative, missing/zero features, boundary timestamps
  - Embedding consistency: same input always produces same output
  - Cross-embedder invariants: weights, slice layout, combined shape

Validates: Requirements FR-RAG-2 (multi-modal embeddings), NFR-RAG-4 (quality).

Marks:
  - All tests in this module are @pytest.mark.unit
  - Property-based tests are additionally @pytest.mark.property

Run:
    pytest scripts/rag/tests/test_embedding_generation.py -v
    pytest scripts/rag/tests/test_embedding_generation.py -m property -v
"""

from __future__ import annotations

import math
import sys
import os
from datetime import datetime, timezone, timedelta

import numpy as np
import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

# ---------------------------------------------------------------------------
# Ensure workspace root is on sys.path
# ---------------------------------------------------------------------------
_WORKSPACE_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..")
)
if _WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, _WORKSPACE_ROOT)

from scripts.rag.utils.narrative_embedder import NarrativeEmbedder
from scripts.rag.utils.structured_feature_embedder import StructuredFeatureEmbedder
from scripts.rag.utils.temporal_embedder import TemporalEmbedder
from scripts.rag.utils.multi_modal_embedder import MultiModalEmbedder
from scripts.rag.utils.setup_enricher import EnrichedSetup

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

NARRATIVE_DIM: int = 384
STRUCTURED_DIM: int = 128
TEMPORAL_DIM: int = 16
COMBINED_DIM: int = 528  # 384 + 128 + 16


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_setup(**overrides) -> EnrichedSetup:
    """Return a valid EnrichedSetup with sensible defaults, allowing field overrides."""
    defaults = dict(
        trade_id="TRD-TEST-001",
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
# Fixtures — module-scoped so SBERT loads once per session
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def narrative_embedder() -> NarrativeEmbedder:
    return NarrativeEmbedder()


@pytest.fixture(scope="module")
def structured_embedder() -> StructuredFeatureEmbedder:
    return StructuredFeatureEmbedder()


@pytest.fixture(scope="module")
def temporal_embedder() -> TemporalEmbedder:
    return TemporalEmbedder()


@pytest.fixture(scope="module")
def multi_modal_embedder() -> MultiModalEmbedder:
    return MultiModalEmbedder()


@pytest.fixture
def sample_setup() -> EnrichedSetup:
    return _make_setup()


# ===========================================================================
# Section 1: Narrative Embedder — independent unit tests
# ===========================================================================


@pytest.mark.unit
class TestNarrativeEmbedderUnit:
    """Unit tests for NarrativeEmbedder in isolation.

    Tests each edge case that is unique to the narrative modality.
    Validates: FR-RAG-2
    """

    def test_dim_attribute_is_384(self, narrative_embedder: NarrativeEmbedder):
        """Embedder exposes .dim == 384."""
        assert narrative_embedder.dim == NARRATIVE_DIM

    def test_embed_returns_1d_float32_384(self, narrative_embedder: NarrativeEmbedder):
        """Standard ICT narrative produces (384,) float32 with no NaN."""
        text = "Price swept Asian low; HTF H1 bullish; FVG at discount; BOS confirmed."
        result = narrative_embedder.embed(text)
        assert result.shape == (NARRATIVE_DIM,)
        assert result.dtype == np.float32
        assert not np.isnan(result).any()
        assert not np.isinf(result).any()

    # -- Edge case: empty string --

    def test_embed_empty_string_produces_valid_vector(
        self, narrative_embedder: NarrativeEmbedder
    ):
        """Empty narrative string must return a 384-dim vector with no NaN.

        SBERT can encode empty strings; the result is a valid (all-zero or
        near-zero) vector that should not crash downstream pipeline stages.
        """
        result = narrative_embedder.embed("")
        assert result.shape == (NARRATIVE_DIM,)
        assert result.dtype == np.float32
        assert not np.isnan(result).any()
        assert not np.isinf(result).any()

    # -- Edge case: whitespace-only string --

    def test_embed_whitespace_only_string(self, narrative_embedder: NarrativeEmbedder):
        """Whitespace-only narrative must return a valid 384-dim vector."""
        result = narrative_embedder.embed("   \t\n  ")
        assert result.shape == (NARRATIVE_DIM,)
        assert not np.isnan(result).any()

    # -- Edge case: unicode / special characters --

    def test_embed_unicode_narrative(self, narrative_embedder: NarrativeEmbedder):
        """Narrative with unicode characters (currency symbols, accents) encodes cleanly."""
        result = narrative_embedder.embed(
            "EURUSD: Preis bildete CHoCH nach Liquiditätssweep. R:R = 3:1. 📈"
        )
        assert result.shape == (NARRATIVE_DIM,)
        assert not np.isnan(result).any()

    # -- Edge case: very long narrative --

    def test_embed_very_long_narrative(self, narrative_embedder: NarrativeEmbedder):
        """Narrative exceeding typical SBERT token limit (512 tokens) stays 384-dim."""
        long_text = (
            "During the London Killzone, price swept the Asian session high "
            "liquidity pool and formed a CHoCH on the M5 timeframe. "
        ) * 20  # well over 512 tokens
        result = narrative_embedder.embed(long_text)
        assert result.shape == (NARRATIVE_DIM,)
        assert not np.isnan(result).any()

    # -- Edge case: numeric-only string --

    def test_embed_numeric_only_string(self, narrative_embedder: NarrativeEmbedder):
        """Narrative containing only numbers encodes without error."""
        result = narrative_embedder.embed("1.0850 1.0920 3.5 0.65")
        assert result.shape == (NARRATIVE_DIM,)
        assert not np.isnan(result).any()

    # -- Consistency --

    def test_embed_consistency_standard_narrative(
        self, narrative_embedder: NarrativeEmbedder
    ):
        """Same narrative text always returns identical vectors (determinism)."""
        text = "HTF bearish bias; price in Premium; FVG resistance; BOS on M5."
        v1 = narrative_embedder.embed(text)
        v2 = narrative_embedder.embed(text)
        np.testing.assert_array_equal(v1, v2)

    def test_embed_consistency_empty_string(
        self, narrative_embedder: NarrativeEmbedder
    ):
        """Empty string always returns the same vector (determinism on edge case)."""
        v1 = narrative_embedder.embed("")
        v2 = narrative_embedder.embed("")
        np.testing.assert_array_equal(v1, v2)

    # -- Different texts produce different vectors --

    def test_different_narratives_produce_different_vectors(
        self, narrative_embedder: NarrativeEmbedder
    ):
        """Semantically distinct narratives must not produce identical embeddings."""
        v_bullish = narrative_embedder.embed(
            "Price swept Asian low; bullish CHoCH; FVG at discount; London Killzone."
        )
        v_bearish = narrative_embedder.embed(
            "Price rejected Premium OB; bearish BOS; FVG imbalance filled; NY AM session."
        )
        assert not np.allclose(v_bullish, v_bearish), (
            "Distinctly different narratives produced identical embeddings"
        )

    # -- Input validation (errors) --

    def test_embed_raises_on_none(self, narrative_embedder: NarrativeEmbedder):
        with pytest.raises((ValueError, TypeError)):
            narrative_embedder.embed(None)  # type: ignore[arg-type]

    def test_embed_raises_on_int(self, narrative_embedder: NarrativeEmbedder):
        with pytest.raises((ValueError, TypeError)):
            narrative_embedder.embed(42)  # type: ignore[arg-type]

    def test_embed_batch_empty_returns_0_x_384(
        self, narrative_embedder: NarrativeEmbedder
    ):
        """embed_batch([]) returns shape (0, 384), not an error."""
        result = narrative_embedder.embed_batch([])
        assert result.shape == (0, NARRATIVE_DIM)

    def test_embed_batch_consistency(self, narrative_embedder: NarrativeEmbedder):
        """embed_batch() rows match individual embed() calls (consistency)."""
        texts = [
            "London Killzone BOS confirmed.",
            "CHoCH after NY AM liquidity sweep.",
        ]
        batch = narrative_embedder.embed_batch(texts)
        for i, text in enumerate(texts):
            single = narrative_embedder.embed(text)
            np.testing.assert_array_almost_equal(
                batch[i], single, decimal=5,
                err_msg=f"Batch row {i} differs from single embed for: {text!r}",
            )


# ===========================================================================
# Section 2: Structured Feature Embedder — independent unit tests
# ===========================================================================


@pytest.mark.unit
class TestStructuredFeatureEmbedderUnit:
    """Unit tests for StructuredFeatureEmbedder in isolation.

    Validates: FR-RAG-2
    """

    def test_dim_attribute_is_128(self, structured_embedder: StructuredFeatureEmbedder):
        assert structured_embedder.dim == STRUCTURED_DIM

    def test_feature_dim_attribute_is_64(
        self, structured_embedder: StructuredFeatureEmbedder
    ):
        assert structured_embedder.feature_dim == 64

    def test_embed_standard_setup_returns_128_float32_no_nan(
        self,
        structured_embedder: StructuredFeatureEmbedder,
        sample_setup: EnrichedSetup,
    ):
        result = structured_embedder.embed(sample_setup)
        assert result.shape == (STRUCTURED_DIM,)
        assert result.dtype == np.float32
        assert not np.isnan(result).any()
        assert not np.isinf(result).any()

    # -- Edge case: all features at zero/minimum --

    def test_embed_all_minimum_features(
        self, structured_embedder: StructuredFeatureEmbedder
    ):
        """Setup with all numeric features at their minimum produces valid embedding."""
        setup = _make_setup(
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
        )
        result = structured_embedder.embed(setup)
        assert result.shape == (STRUCTURED_DIM,)
        assert not np.isnan(result).any()

    # -- Edge case: all features at maximum --

    def test_embed_all_maximum_features(
        self, structured_embedder: StructuredFeatureEmbedder
    ):
        """Setup with all numeric features at their maximum produces valid embedding."""
        setup = _make_setup(
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
        )
        result = structured_embedder.embed(setup)
        assert result.shape == (STRUCTURED_DIM,)
        assert not np.isnan(result).any()

    # -- Edge case: extreme r_multiple (positive and negative) --

    @pytest.mark.parametrize("r_multiple,outcome", [
        (999.9, "WIN"),    # very large positive
        (-999.9, "LOSS"),  # very large negative
        (0.001, "WIN"),    # near-zero positive
    ])
    def test_embed_extreme_r_multiple(
        self,
        structured_embedder: StructuredFeatureEmbedder,
        r_multiple: float,
        outcome: str,
    ):
        """Extreme r_multiple values are clipped and produce valid embeddings."""
        setup = _make_setup(r_multiple=r_multiple, outcome_result=outcome)
        result = structured_embedder.embed(setup)
        assert result.shape == (STRUCTURED_DIM,)
        assert not np.isnan(result).any()

    # -- Edge case: extreme confluence count --

    @pytest.mark.parametrize("count", [0, 1, 10, 50, 100])
    def test_embed_extreme_confluence_count(
        self, structured_embedder: StructuredFeatureEmbedder, count: int
    ):
        """Any confluence count (including far beyond 10) produces a valid embedding."""
        setup = _make_setup(confluence_count=count)
        result = structured_embedder.embed(setup)
        assert result.shape == (STRUCTURED_DIM,)
        assert not np.isnan(result).any()

    # -- Edge case: swing distances at extremes --

    @pytest.mark.parametrize("distance", [0.0, 0.001, 0.1, 10.0])
    def test_embed_extreme_swing_distances(
        self, structured_embedder: StructuredFeatureEmbedder, distance: float
    ):
        """Extreme swing distances are clipped and produce valid embeddings."""
        setup = _make_setup(
            swing_high_distance=distance, swing_low_distance=distance
        )
        result = structured_embedder.embed(setup)
        assert result.shape == (STRUCTURED_DIM,)
        assert not np.isnan(result).any()

    # -- Consistency --

    def test_embed_consistency(
        self,
        structured_embedder: StructuredFeatureEmbedder,
        sample_setup: EnrichedSetup,
    ):
        """Same EnrichedSetup always returns identical embedding (determinism)."""
        v1 = structured_embedder.embed(sample_setup)
        v2 = structured_embedder.embed(sample_setup)
        np.testing.assert_array_equal(v1, v2)

    def test_extract_features_consistency(
        self,
        structured_embedder: StructuredFeatureEmbedder,
        sample_setup: EnrichedSetup,
    ):
        """extract_features() is deterministic for the same setup."""
        f1 = structured_embedder.extract_features(sample_setup)
        f2 = structured_embedder.extract_features(sample_setup)
        np.testing.assert_array_equal(f1, f2)

    def test_features_always_in_unit_range(
        self,
        structured_embedder: StructuredFeatureEmbedder,
        sample_setup: EnrichedSetup,
    ):
        """All 64 features must be in [0, 1] after normalisation."""
        features = structured_embedder.extract_features(sample_setup)
        assert (features >= 0.0).all(), f"Values below 0: {features[features < 0]}"
        assert (features <= 1.0).all(), f"Values above 1: {features[features > 1]}"

    # -- All three HTF bias values produce different embeddings --

    def test_htf_bias_variants_produce_different_embeddings(
        self, structured_embedder: StructuredFeatureEmbedder
    ):
        """BULLISH, BEARISH, NEUTRAL HTF bias must produce three distinct embeddings."""
        embeddings = {
            bias: structured_embedder.embed(_make_setup(htf_open_bias=bias))
            for bias in ["BULLISH", "BEARISH", "NEUTRAL"]
        }
        biases = list(embeddings.keys())
        for i in range(len(biases)):
            for j in range(i + 1, len(biases)):
                assert not np.allclose(
                    embeddings[biases[i]], embeddings[biases[j]]
                ), f"{biases[i]} and {biases[j]} produced identical embeddings"

    # -- Input validation --

    def test_embed_raises_on_none(
        self, structured_embedder: StructuredFeatureEmbedder
    ):
        with pytest.raises((TypeError, AttributeError, ValueError)):
            structured_embedder.embed(None)  # type: ignore[arg-type]

    def test_embed_raises_on_raw_dict(
        self, structured_embedder: StructuredFeatureEmbedder
    ):
        with pytest.raises((TypeError, AttributeError, ValueError)):
            structured_embedder.embed({"instrument": "EURUSD"})  # type: ignore[arg-type]


# ===========================================================================
# Section 3: Temporal Embedder — independent unit tests
# ===========================================================================


@pytest.mark.unit
class TestTemporalEmbedderUnit:
    """Unit tests for TemporalEmbedder in isolation.

    Validates: FR-RAG-2
    """

    def test_encode_standard_timestamp_returns_16_dim(
        self, temporal_embedder: TemporalEmbedder
    ):
        ts = datetime(2024, 3, 15, 9, 15, 0, tzinfo=timezone.utc)
        result = temporal_embedder.encode(ts)
        assert result.shape == (TEMPORAL_DIM,)
        assert not np.isnan(result).any()
        assert not np.isinf(result).any()

    # -- Edge case: boundary timestamps --

    def test_encode_unix_epoch(self, temporal_embedder: TemporalEmbedder):
        """Unix epoch (1970-01-01 00:00 UTC) encodes without error."""
        ts = datetime(1970, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        result = temporal_embedder.encode(ts)
        assert result.shape == (TEMPORAL_DIM,)
        assert not np.isnan(result).any()

    def test_encode_far_future_timestamp(self, temporal_embedder: TemporalEmbedder):
        """Far-future timestamp (2099-12-31) encodes without error."""
        ts = datetime(2099, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
        result = temporal_embedder.encode(ts)
        assert result.shape == (TEMPORAL_DIM,)
        assert not np.isnan(result).any()

    def test_encode_midnight_utc(self, temporal_embedder: TemporalEmbedder):
        """Midnight (00:00 UTC) encodes with correct hour sin=0, cos=1."""
        ts = datetime(2024, 6, 10, 0, 0, 0, tzinfo=timezone.utc)
        result = temporal_embedder.encode(ts)
        assert math.isclose(result[0], math.sin(0), abs_tol=1e-12)
        assert math.isclose(result[1], math.cos(0), abs_tol=1e-12)

    def test_encode_end_of_day(self, temporal_embedder: TemporalEmbedder):
        """23:59:59 UTC encodes cleanly (near but not equal to midnight)."""
        ts = datetime(2024, 6, 10, 23, 59, 59, tzinfo=timezone.utc)
        result = temporal_embedder.encode(ts)
        assert result.shape == (TEMPORAL_DIM,)
        assert not np.isnan(result).any()

    def test_encode_leap_day(self, temporal_embedder: TemporalEmbedder):
        """Feb 29 (leap day) encodes without error."""
        ts = datetime(2024, 2, 29, 12, 0, 0, tzinfo=timezone.utc)
        result = temporal_embedder.encode(ts)
        assert result.shape == (TEMPORAL_DIM,)
        assert not np.isnan(result).any()

    # -- Edge case: naive datetime (assumed UTC) --

    def test_encode_naive_datetime_treated_as_utc(
        self, temporal_embedder: TemporalEmbedder
    ):
        """Naive datetime is assumed UTC and produces same result as explicit UTC."""
        naive_ts = datetime(2024, 3, 15, 9, 15, 0)
        utc_ts = datetime(2024, 3, 15, 9, 15, 0, tzinfo=timezone.utc)
        v_naive = temporal_embedder.encode(naive_ts)
        v_utc = temporal_embedder.encode(utc_ts)
        np.testing.assert_array_equal(v_naive, v_utc)

    # -- Edge case: non-UTC aware datetime --

    def test_encode_non_utc_aware_datetime_normalised(
        self, temporal_embedder: TemporalEmbedder
    ):
        """UTC+2 at 11:15 is the same moment as UTC 09:15; encoding must match."""
        utc_plus_2 = timezone(timedelta(hours=2))
        local_ts = datetime(2024, 3, 15, 11, 15, 0, tzinfo=utc_plus_2)
        utc_ts = datetime(2024, 3, 15, 9, 15, 0, tzinfo=timezone.utc)
        np.testing.assert_array_equal(
            temporal_embedder.encode(local_ts),
            temporal_embedder.encode(utc_ts),
        )

    # -- Reserved dimensions --

    def test_reserved_dims_6_to_15_are_zero(
        self, temporal_embedder: TemporalEmbedder
    ):
        """Dims 6–15 are always zero (reserved for future features)."""
        ts = datetime(2024, 3, 15, 9, 15, 0, tzinfo=timezone.utc)
        result = temporal_embedder.encode(ts)
        np.testing.assert_array_equal(result[6:], np.zeros(10))

    def test_active_dims_0_to_5_in_valid_range(
        self, temporal_embedder: TemporalEmbedder
    ):
        """Dims 0–5 (sin/cos values) are always in [-1.0, 1.0]."""
        for month in range(1, 13):
            ts = datetime(2024, month, 15, 12, 0, 0, tzinfo=timezone.utc)
            result = temporal_embedder.encode(ts)
            for i in range(6):
                assert -1.0 <= result[i] <= 1.0, (
                    f"Dim {i} = {result[i]:.4f} is outside [-1, 1] for month={month}"
                )

    # -- Consistency --

    def test_encode_consistency(self, temporal_embedder: TemporalEmbedder):
        """Same timestamp always returns identical vector (determinism)."""
        ts = datetime(2024, 3, 15, 9, 15, 0, tzinfo=timezone.utc)
        v1 = temporal_embedder.encode(ts)
        v2 = temporal_embedder.encode(ts)
        np.testing.assert_array_equal(v1, v2)

    def test_different_hours_produce_different_vectors(
        self, temporal_embedder: TemporalEmbedder
    ):
        """Two timestamps differing only by hour produce different embeddings."""
        ts_morning = datetime(2024, 3, 15, 9, 0, 0, tzinfo=timezone.utc)
        ts_afternoon = datetime(2024, 3, 15, 15, 0, 0, tzinfo=timezone.utc)
        v1 = temporal_embedder.encode(ts_morning)
        v2 = temporal_embedder.encode(ts_afternoon)
        assert not np.array_equal(v1, v2), (
            "9:00 and 15:00 produced identical temporal embeddings"
        )

    # -- Killzone timestamps produce valid embeddings --

    @pytest.mark.parametrize("hour,label", [
        (2, "Asian"),
        (8, "London open"),
        (10, "London Killzone"),
        (13, "NY AM"),
        (15, "NY Silver Bullet"),
        (20, "NY PM"),
    ])
    def test_encode_all_killzone_hours(
        self,
        temporal_embedder: TemporalEmbedder,
        hour: int,
        label: str,
    ):
        """Each killzone hour encodes to a valid 16-dim vector."""
        ts = datetime(2024, 3, 15, hour, 0, 0, tzinfo=timezone.utc)
        result = temporal_embedder.encode(ts)
        assert result.shape == (TEMPORAL_DIM,), f"Bad shape for {label}"
        assert not np.isnan(result).any(), f"NaN for {label} at hour {hour}"


# ===========================================================================
# Section 4: Multi-Modal Embedder — edge cases and consistency
# ===========================================================================


@pytest.mark.unit
class TestMultiModalEmbedderUnit:
    """Unit tests for MultiModalEmbedder with emphasis on edge cases.

    These complement the per-component tests by testing the combined pipeline
    on setups that push the boundaries of each modality simultaneously.

    Validates: FR-RAG-2, NFR-RAG-4
    """

    def test_embed_standard_setup_returns_528_float32_no_nan(
        self,
        multi_modal_embedder: MultiModalEmbedder,
        sample_setup: EnrichedSetup,
    ):
        result = multi_modal_embedder.embed(sample_setup)
        assert result.shape == (COMBINED_DIM,)
        assert result.dtype == np.float32
        assert not np.isnan(result).any()
        assert not np.isinf(result).any()

    # -- Edge case: empty narrative --

    def test_embed_empty_narrative_produces_valid_combined_vector(
        self, multi_modal_embedder: MultiModalEmbedder
    ):
        """Setup with an empty narrative string must still produce a 528-dim vector.

        The narrative slice will encode an empty string; structured and temporal
        slices should be unaffected.  No NaN or Inf must appear.
        """
        setup = _make_setup(narrative="")
        result = multi_modal_embedder.embed(setup)
        assert result.shape == (COMBINED_DIM,)
        assert result.dtype == np.float32
        assert not np.isnan(result).any()
        assert not np.isinf(result).any()

    def test_embed_empty_narrative_structured_slice_unchanged(
        self, multi_modal_embedder: MultiModalEmbedder
    ):
        """Changing only the narrative must not affect the structured + temporal slices."""
        setup_a = _make_setup(
            narrative="Price swept Asian low before reversing bullish."
        )
        setup_b = _make_setup(narrative="")  # empty — all other fields identical

        v_a = multi_modal_embedder.embed(setup_a)
        v_b = multi_modal_embedder.embed(setup_b)

        # Structured + temporal slices (indices 384–527) must be identical
        np.testing.assert_array_almost_equal(
            v_a[NARRATIVE_DIM:],
            v_b[NARRATIVE_DIM:],
            decimal=5,
            err_msg="Structured/temporal slices changed when only narrative changed",
        )

    # -- Edge case: all-minimum structured features with rich narrative --

    def test_embed_min_features_rich_narrative(
        self, multi_modal_embedder: MultiModalEmbedder
    ):
        """Min structured features + rich narrative must produce valid combined vector."""
        setup = _make_setup(
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
            narrative=(
                "All ICT confluence absent. No BOS, no CHoCH, no FVG. "
                "Price in no-man's land. Setup not taken."
            ),
        )
        result = multi_modal_embedder.embed(setup)
        assert result.shape == (COMBINED_DIM,)
        assert not np.isnan(result).any()

    # -- Edge case: boundary timestamps in the combined pipeline --

    def test_embed_far_past_timestamp(
        self, multi_modal_embedder: MultiModalEmbedder
    ):
        """Setup with a very old timestamp (2000-01-01) embeds cleanly."""
        setup = _make_setup(
            timestamp=datetime(2000, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        )
        result = multi_modal_embedder.embed(setup)
        assert result.shape == (COMBINED_DIM,)
        assert not np.isnan(result).any()

    def test_embed_far_future_timestamp(
        self, multi_modal_embedder: MultiModalEmbedder
    ):
        """Setup with a far-future timestamp (2099-12-31) embeds cleanly."""
        setup = _make_setup(
            timestamp=datetime(2099, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
        )
        result = multi_modal_embedder.embed(setup)
        assert result.shape == (COMBINED_DIM,)
        assert not np.isnan(result).any()

    # -- Consistency --

    def test_embed_consistency_standard_setup(
        self,
        multi_modal_embedder: MultiModalEmbedder,
        sample_setup: EnrichedSetup,
    ):
        """Same setup always produces identical 528-dim vector (determinism)."""
        v1 = multi_modal_embedder.embed(sample_setup)
        v2 = multi_modal_embedder.embed(sample_setup)
        np.testing.assert_array_equal(v1, v2)

    def test_embed_consistency_edge_case_setup(
        self, multi_modal_embedder: MultiModalEmbedder
    ):
        """Determinism holds even for edge-case (all-zero) setups."""
        setup = _make_setup(
            narrative="",
            htf_high_proximity_pct=0.0,
            htf_body_pct=0.0,
            htf_open_bias="NEUTRAL",
            bos_detected=False,
            r_multiple=0.0,
            outcome_result="LOSS",
            confluence_count=0,
        )
        v1 = multi_modal_embedder.embed(setup)
        v2 = multi_modal_embedder.embed(setup)
        np.testing.assert_array_equal(v1, v2)

    def test_embed_consistency_across_new_embedder_instances(
        self, sample_setup: EnrichedSetup
    ):
        """Two freshly created MultiModalEmbedder instances produce identical output.

        This validates that the structured embedder's fixed projection seed (42)
        ensures cross-instance determinism.
        """
        v1 = MultiModalEmbedder().embed(sample_setup)
        v2 = MultiModalEmbedder().embed(sample_setup)
        np.testing.assert_array_almost_equal(
            v1, v2, decimal=5,
            err_msg="Two fresh MultiModalEmbedder instances produced different output",
        )

    # -- All supported instruments and directions --

    @pytest.mark.parametrize("instrument", [
        "EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "US500", "US30",
    ])
    def test_embed_all_supported_instruments(
        self, multi_modal_embedder: MultiModalEmbedder, instrument: str
    ):
        """Each supported instrument produces a valid 528-dim embedding."""
        setup = _make_setup(instrument=instrument)
        result = multi_modal_embedder.embed(setup)
        assert result.shape == (COMBINED_DIM,)
        assert not np.isnan(result).any()

    @pytest.mark.parametrize("direction", ["BUY", "SELL"])
    def test_embed_both_directions(
        self, multi_modal_embedder: MultiModalEmbedder, direction: str
    ):
        """BUY and SELL setups each produce a valid 528-dim embedding."""
        setup = _make_setup(direction=direction)
        result = multi_modal_embedder.embed(setup)
        assert result.shape == (COMBINED_DIM,)
        assert not np.isnan(result).any()

    # -- Slice integrity --

    def test_narrative_slice_occupies_correct_indices(
        self,
        multi_modal_embedder: MultiModalEmbedder,
        sample_setup: EnrichedSetup,
    ):
        """Indices 0–383 carry the narrative component (* 0.4 weight)."""
        result = multi_modal_embedder.embed(sample_setup)
        narrative_slice = result[:NARRATIVE_DIM]
        # Verify slice has correct length
        assert len(narrative_slice) == NARRATIVE_DIM
        # Verify the raw narrative embedding scaled by 0.4 matches the slice
        raw_narrative = NarrativeEmbedder().embed(sample_setup.narrative)
        np.testing.assert_array_almost_equal(
            narrative_slice,
            (raw_narrative * 0.4).astype(np.float32),
            decimal=5,
        )

    def test_structured_slice_occupies_correct_indices(
        self,
        multi_modal_embedder: MultiModalEmbedder,
        sample_setup: EnrichedSetup,
    ):
        """Indices 384–511 carry the structured component (* 0.4 weight)."""
        result = multi_modal_embedder.embed(sample_setup)
        structured_slice = result[NARRATIVE_DIM : NARRATIVE_DIM + STRUCTURED_DIM]
        assert len(structured_slice) == STRUCTURED_DIM
        raw_structured = StructuredFeatureEmbedder().embed(sample_setup)
        np.testing.assert_array_almost_equal(
            structured_slice,
            (raw_structured * 0.4).astype(np.float32),
            decimal=5,
        )

    def test_temporal_slice_occupies_correct_indices(
        self,
        multi_modal_embedder: MultiModalEmbedder,
        sample_setup: EnrichedSetup,
    ):
        """Indices 512–527 carry the temporal component (* 0.2 weight)."""
        result = multi_modal_embedder.embed(sample_setup)
        temporal_slice = result[NARRATIVE_DIM + STRUCTURED_DIM :]
        assert len(temporal_slice) == TEMPORAL_DIM
        raw_temporal = TemporalEmbedder().encode(sample_setup.timestamp)
        np.testing.assert_array_almost_equal(
            temporal_slice,
            (raw_temporal * 0.2).astype(np.float32),
            decimal=5,
        )


# ===========================================================================
# Section 5: Cross-embedder consistency tests
# ===========================================================================


@pytest.mark.unit
class TestCrossEmbedderConsistency:
    """Tests that verify consistent behaviour across all three embedder types.

    These are the key NFR-RAG-4 (quality) invariants:
      1. Same input → same output for every embedder type
      2. Different inputs → different outputs (sensitivity)
      3. Pipeline slices are self-consistent
    """

    def test_all_three_embedders_are_deterministic_for_same_setup(
        self,
        narrative_embedder: NarrativeEmbedder,
        structured_embedder: StructuredFeatureEmbedder,
        temporal_embedder: TemporalEmbedder,
        sample_setup: EnrichedSetup,
    ):
        """All three component embedders produce identical output on repeated calls."""
        v_narrative_1 = narrative_embedder.embed(sample_setup.narrative)
        v_narrative_2 = narrative_embedder.embed(sample_setup.narrative)
        np.testing.assert_array_equal(v_narrative_1, v_narrative_2, err_msg="narrative")

        v_structured_1 = structured_embedder.embed(sample_setup)
        v_structured_2 = structured_embedder.embed(sample_setup)
        np.testing.assert_array_equal(v_structured_1, v_structured_2, err_msg="structured")

        v_temporal_1 = temporal_embedder.encode(sample_setup.timestamp)
        v_temporal_2 = temporal_embedder.encode(sample_setup.timestamp)
        np.testing.assert_array_equal(v_temporal_1, v_temporal_2, err_msg="temporal")

    def test_changing_narrative_only_affects_narrative_slice(
        self, multi_modal_embedder: MultiModalEmbedder
    ):
        """Altering only the narrative changes only indices 0–383."""
        setup_a = _make_setup(narrative="London Killzone BOS after CHoCH on M5.")
        setup_b = _make_setup(
            narrative="NY AM session: price swept Asian high, bearish reversal expected."
        )
        v_a = multi_modal_embedder.embed(setup_a)
        v_b = multi_modal_embedder.embed(setup_b)

        # Narrative slices differ
        assert not np.allclose(v_a[:NARRATIVE_DIM], v_b[:NARRATIVE_DIM])
        # Structured + temporal slices are identical
        np.testing.assert_array_almost_equal(v_a[NARRATIVE_DIM:], v_b[NARRATIVE_DIM:], decimal=5)

    def test_changing_structured_fields_only_affects_structured_slice(
        self, multi_modal_embedder: MultiModalEmbedder
    ):
        """Altering only structured fields changes only indices 384–511."""
        setup_a = _make_setup(htf_open_bias="BULLISH", outcome_result="WIN", r_multiple=3.0)
        setup_b = _make_setup(htf_open_bias="BEARISH", outcome_result="LOSS", r_multiple=-1.0)
        v_a = multi_modal_embedder.embed(setup_a)
        v_b = multi_modal_embedder.embed(setup_b)

        # Narrative slices are identical (same narrative text)
        np.testing.assert_array_almost_equal(v_a[:NARRATIVE_DIM], v_b[:NARRATIVE_DIM], decimal=5)
        # Structured slice differs
        assert not np.allclose(
            v_a[NARRATIVE_DIM : NARRATIVE_DIM + STRUCTURED_DIM],
            v_b[NARRATIVE_DIM : NARRATIVE_DIM + STRUCTURED_DIM],
        )
        # Temporal slices are identical (same timestamp)
        np.testing.assert_array_almost_equal(
            v_a[NARRATIVE_DIM + STRUCTURED_DIM :],
            v_b[NARRATIVE_DIM + STRUCTURED_DIM :],
            decimal=5,
        )

    def test_changing_timestamp_only_affects_temporal_slice(
        self, multi_modal_embedder: MultiModalEmbedder
    ):
        """Altering only the timestamp changes only indices 512–527."""
        setup_a = _make_setup(
            timestamp=datetime(2024, 3, 15, 9, 15, 0, tzinfo=timezone.utc)
        )
        setup_b = _make_setup(
            timestamp=datetime(2024, 3, 15, 14, 30, 0, tzinfo=timezone.utc)
        )
        v_a = multi_modal_embedder.embed(setup_a)
        v_b = multi_modal_embedder.embed(setup_b)

        # Narrative + structured slices are identical
        np.testing.assert_array_almost_equal(
            v_a[: NARRATIVE_DIM + STRUCTURED_DIM],
            v_b[: NARRATIVE_DIM + STRUCTURED_DIM],
            decimal=5,
        )
        # Temporal slice differs
        assert not np.allclose(
            v_a[NARRATIVE_DIM + STRUCTURED_DIM :],
            v_b[NARRATIVE_DIM + STRUCTURED_DIM :],
        )

    def test_component_dims_sum_to_combined_dim(self):
        """Architectural constant: 384 + 128 + 16 == 528."""
        assert NARRATIVE_DIM + STRUCTURED_DIM + TEMPORAL_DIM == COMBINED_DIM

    def test_multi_modal_embed_matches_manual_combination(
        self,
        narrative_embedder: NarrativeEmbedder,
        structured_embedder: StructuredFeatureEmbedder,
        temporal_embedder: TemporalEmbedder,
        multi_modal_embedder: MultiModalEmbedder,
        sample_setup: EnrichedSetup,
    ):
        """MultiModalEmbedder.embed() must match the manual 40/40/20 concatenation."""
        v_narrative = narrative_embedder.embed(sample_setup.narrative)
        v_structured = structured_embedder.embed(sample_setup)
        v_temporal = temporal_embedder.encode(sample_setup.timestamp)

        manual_combined = np.concatenate([
            v_narrative.astype(np.float32) * 0.4,
            v_structured.astype(np.float32) * 0.4,
            v_temporal.astype(np.float32) * 0.2,
        ]).astype(np.float32)

        auto_combined = multi_modal_embedder.embed(sample_setup)

        np.testing.assert_array_almost_equal(
            auto_combined,
            manual_combined,
            decimal=5,
            err_msg=(
                "MultiModalEmbedder output does not match manual "
                "40% narrative + 40% structured + 20% temporal concatenation"
            ),
        )


# ===========================================================================
# Section 6: Property-based tests for cross-cutting invariants
# ===========================================================================


@pytest.mark.unit
@pytest.mark.property
class TestEmbeddingGenerationProperties:
    """
    Property-based tests enforcing invariants across arbitrary inputs.

    Critical invariants (from rag-pipeline.md):
    1. Output is always exactly 528-dim
    2. No NaN values
    3. Same input always produces same output (determinism)

    Validates: FR-RAG-2, NFR-RAG-4
    """

    @given(
        htf_bias=st.sampled_from(["BULLISH", "BEARISH", "NEUTRAL"]),
        outcome=st.sampled_from(["WIN", "LOSS"]),
        r_mult=st.floats(
            min_value=-10.0, max_value=20.0, allow_nan=False, allow_infinity=False
        ),
        conf_count=st.integers(min_value=0, max_value=15),
        bos=st.booleans(),
        choch=st.booleans(),
        fvg=st.booleans(),
        sweep=st.booleans(),
        is_kz=st.booleans(),
        tw_weight=st.floats(
            min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False
        ),
    )
    @settings(
        max_examples=25,
        suppress_health_check=[HealthCheck.too_slow],
        deadline=None,
    )
    def test_combined_embedding_always_528_no_nan(
        self,
        htf_bias: str,
        outcome: str,
        r_mult: float,
        conf_count: int,
        bos: bool,
        choch: bool,
        fvg: bool,
        sweep: bool,
        is_kz: bool,
        tw_weight: float,
    ) -> None:
        """For any valid EnrichedSetup, MultiModalEmbedder produces (528,) with no NaN.

        Validates: FR-RAG-2
        """
        setup = _make_setup(
            htf_open_bias=htf_bias,
            outcome_result=outcome,
            r_multiple=r_mult,
            confluence_count=conf_count,
            bos_detected=bos,
            choch_detected=choch,
            fvg_present=fvg,
            liquidity_sweep=sweep,
            is_killzone=is_kz,
            time_window_weight=tw_weight,
        )
        result = MultiModalEmbedder().embed(setup)
        assert result.shape == (COMBINED_DIM,), (
            f"Expected ({COMBINED_DIM},), got {result.shape}"
        )
        assert not np.isnan(result).any(), "NaN in combined embedding"
        assert not np.isinf(result).any(), "Inf in combined embedding"
        assert result.dtype == np.float32, f"Expected float32, got {result.dtype}"

    @given(
        ts=st.datetimes(
            min_value=datetime(2000, 1, 1),
            max_value=datetime(2099, 12, 31),
            timezones=st.just(timezone.utc),
        )
    )
    @settings(
        max_examples=30,
        suppress_health_check=[HealthCheck.too_slow],
        deadline=None,
    )
    def test_temporal_encoding_always_16_no_nan_for_arbitrary_date(
        self, ts: datetime
    ) -> None:
        """TemporalEmbedder produces (16,) with no NaN for any valid UTC timestamp.

        Validates: FR-RAG-2
        """
        result = TemporalEmbedder().encode(ts)
        assert result.shape == (TEMPORAL_DIM,), f"Expected (16,), got {result.shape}"
        assert not np.isnan(result).any(), f"NaN for ts={ts}"
        np.testing.assert_array_equal(result[6:], np.zeros(10), err_msg="Reserved dims non-zero")

    @given(
        htf_high=st.floats(
            min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False
        ),
        htf_low=st.floats(
            min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False
        ),
        htf_body=st.floats(
            min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False
        ),
        htf_bias=st.sampled_from(["BULLISH", "BEARISH", "NEUTRAL"]),
        r_mult=st.floats(
            min_value=-20.0, max_value=20.0, allow_nan=False, allow_infinity=False
        ),
        conf_count=st.integers(min_value=0, max_value=20),
        tw_weight=st.floats(
            min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False
        ),
    )
    @settings(
        max_examples=35,
        suppress_health_check=[HealthCheck.too_slow],
        deadline=None,
    )
    def test_structured_features_always_64_in_unit_range(
        self,
        htf_high: float,
        htf_low: float,
        htf_body: float,
        htf_bias: str,
        r_mult: float,
        conf_count: int,
        tw_weight: float,
    ) -> None:
        """For arbitrary valid structured inputs, feature vector is (64,) in [0, 1].

        Validates: FR-RAG-2
        """
        setup = _make_setup(
            htf_high_proximity_pct=htf_high,
            htf_low_proximity_pct=htf_low,
            htf_body_pct=htf_body,
            htf_open_bias=htf_bias,
            r_multiple=r_mult,
            confluence_count=conf_count,
            time_window_weight=tw_weight,
        )
        embedder = StructuredFeatureEmbedder()
        features = embedder.extract_features(setup)
        assert features.shape == (64,), f"Expected (64,), got {features.shape}"
        assert (features >= 0.0).all(), f"Feature below 0: {features[features < 0]}"
        assert (features <= 1.0).all(), f"Feature above 1: {features[features > 1]}"

    @given(
        text=st.text(min_size=0, max_size=300),
    )
    @settings(
        max_examples=20,
        suppress_health_check=[HealthCheck.too_slow],
        deadline=None,
    )
    def test_narrative_embedding_always_384_no_nan(self, text: str) -> None:
        """NarrativeEmbedder produces (384,) with no NaN for any text (including empty).

        Validates: FR-RAG-2
        """
        result = NarrativeEmbedder().embed(text)
        assert result.shape == (NARRATIVE_DIM,), (
            f"Expected (384,), got {result.shape} for text={text!r}"
        )
        assert not np.isnan(result).any(), f"NaN for text={text!r}"
