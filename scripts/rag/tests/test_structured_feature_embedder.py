"""
TDD – Task 4.3: Tests for StructuredFeatureEmbedder pipeline component.

RED  phase: tests that define the expected behaviour of StructuredFeatureEmbedder
            before the implementation exists.
GREEN phase: implementation in scripts/rag/utils/structured_feature_embedder.py
             satisfies all assertions.
REFACTOR: features normalised to [0, 1] range before encoding.

Validates: Requirements FR-RAG-2 (multi-modal embeddings – structured component).

Feature vector spec (64 features, all normalised to [0, 1]):
  HTF metrics    (4):  htf_high_proximity_pct, htf_low_proximity_pct,
                        htf_body_pct, htf_close_position
  HTF bias       (3):  one-hot of BULLISH / BEARISH / NEUTRAL
  PD array flags (4):  bos_detected, choch_detected, fvg_present, liquidity_sweep
  Swing distances(2):  swing_high_distance, swing_low_distance
  Session        (2):  time_window_weight, is_killzone
  Outcome        (2):  r_multiple (normalised), one-hot WIN/LOSS
  Confluence     (1):  confluence_count (normalised)
  Padding        (46): zeros to pad total to 64 features

Output embedding: 64-dim vector projected to 128-dim via linear layer.

Invariants enforced:
  - Input feature vector always exactly 64-dim
  - Output embedding always exactly 128-dim
  - No NaN values in output
  - Same input always produces same output (determinism)
  - All 64 raw features in [0, 1] after normalisation
"""

from __future__ import annotations

import numpy as np
import pytest
from datetime import datetime, timezone
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

from scripts.rag.utils.setup_enricher import EnrichedSetup

# Import under test — will fail until GREEN phase creates the module
from scripts.rag.utils.structured_feature_embedder import StructuredFeatureEmbedder

STRUCTURED_DIM: int = 128
FEATURE_VEC_DIM: int = 64


# ---------------------------------------------------------------------------
# Helpers / sample data
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
        # HTF
        htf_timeframe="H1",
        htf_open=1.0840,
        htf_high=1.0950,
        htf_low=1.0800,
        htf_open_bias="BULLISH",
        htf_high_proximity_pct=66.67,
        htf_low_proximity_pct=33.33,
        htf_body_pct=60.0,
        htf_close_position=50.0,
        # PD arrays
        bos_detected=True,
        choch_detected=False,
        fvg_present=True,
        liquidity_sweep=True,
        swing_high_distance=0.0050,
        swing_low_distance=0.0030,
        htf_trend_bias="BULLISH",
        # Session
        time_window="LONDON_KILLZONE",
        narrative_phase="MANIPULATION",
        time_window_weight=0.9,
        is_killzone=True,
        # Narrative & confluence
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
def embedder() -> StructuredFeatureEmbedder:
    """Shared StructuredFeatureEmbedder instance — created once per test session."""
    return StructuredFeatureEmbedder()


@pytest.fixture
def sample_setup() -> EnrichedSetup:
    return _make_enriched_setup()


# ---------------------------------------------------------------------------
# 1. Instantiation tests
# ---------------------------------------------------------------------------


class TestStructuredFeatureEmbedderInstantiation:
    """Verify StructuredFeatureEmbedder can be created and exposes the right interface."""

    def test_instantiates_without_error(self):
        emb = StructuredFeatureEmbedder()
        assert emb is not None

    def test_has_embed_method(self, embedder: StructuredFeatureEmbedder):
        assert callable(getattr(embedder, "embed", None))

    def test_has_extract_features_method(self, embedder: StructuredFeatureEmbedder):
        assert callable(getattr(embedder, "extract_features", None))

    def test_exposes_dim_attribute(self, embedder: StructuredFeatureEmbedder):
        """StructuredFeatureEmbedder must expose .dim == 128."""
        assert embedder.dim == STRUCTURED_DIM

    def test_exposes_feature_dim_attribute(self, embedder: StructuredFeatureEmbedder):
        """StructuredFeatureEmbedder must expose .feature_dim == 64."""
        assert embedder.feature_dim == FEATURE_VEC_DIM


# ---------------------------------------------------------------------------
# 2. Feature extraction tests — extract_features()
# ---------------------------------------------------------------------------


class TestFeatureExtraction:
    """Verify extract_features() produces the correct 64-dim normalised vector."""

    def test_extract_features_returns_numpy_array(
        self, embedder: StructuredFeatureEmbedder, sample_setup: EnrichedSetup
    ):
        features = embedder.extract_features(sample_setup)
        assert isinstance(features, np.ndarray)

    def test_extract_features_returns_64_dim(
        self, embedder: StructuredFeatureEmbedder, sample_setup: EnrichedSetup
    ):
        features = embedder.extract_features(sample_setup)
        assert features.shape == (FEATURE_VEC_DIM,), (
            f"Expected ({FEATURE_VEC_DIM},), got {features.shape}"
        )

    def test_extract_features_dtype_float32(
        self, embedder: StructuredFeatureEmbedder, sample_setup: EnrichedSetup
    ):
        features = embedder.extract_features(sample_setup)
        assert features.dtype == np.float32

    def test_extract_features_no_nan(
        self, embedder: StructuredFeatureEmbedder, sample_setup: EnrichedSetup
    ):
        features = embedder.extract_features(sample_setup)
        assert not np.isnan(features).any(), "NaN values found in feature vector"

    def test_extract_features_no_inf(
        self, embedder: StructuredFeatureEmbedder, sample_setup: EnrichedSetup
    ):
        features = embedder.extract_features(sample_setup)
        assert not np.isinf(features).any(), "Inf values found in feature vector"

    def test_extract_features_all_in_unit_range(
        self, embedder: StructuredFeatureEmbedder, sample_setup: EnrichedSetup
    ):
        """All 64 features must be in [0, 1] after normalisation (REFACTOR requirement)."""
        features = embedder.extract_features(sample_setup)
        assert (features >= 0.0).all(), f"Features below 0: {features[features < 0]}"
        assert (features <= 1.0).all(), f"Features above 1: {features[features > 1]}"

    # -- HTF metrics (indices 0-3) --

    def test_htf_high_proximity_at_index_0(
        self, embedder: StructuredFeatureEmbedder
    ):
        """htf_high_proximity_pct (0-100) normalised to [0, 1] at index 0."""
        setup = _make_enriched_setup(htf_high_proximity_pct=75.0)
        features = embedder.extract_features(setup)
        assert abs(features[0] - 0.75) < 1e-5

    def test_htf_low_proximity_at_index_1(
        self, embedder: StructuredFeatureEmbedder
    ):
        """htf_low_proximity_pct (0-100) normalised to [0, 1] at index 1."""
        setup = _make_enriched_setup(htf_low_proximity_pct=30.0)
        features = embedder.extract_features(setup)
        assert abs(features[1] - 0.30) < 1e-5

    def test_htf_body_pct_at_index_2(
        self, embedder: StructuredFeatureEmbedder
    ):
        """htf_body_pct (0-100) normalised to [0, 1] at index 2."""
        setup = _make_enriched_setup(htf_body_pct=55.0)
        features = embedder.extract_features(setup)
        assert abs(features[2] - 0.55) < 1e-5

    def test_htf_close_position_at_index_3(
        self, embedder: StructuredFeatureEmbedder
    ):
        """htf_close_position (0-100) normalised to [0, 1] at index 3."""
        setup = _make_enriched_setup(htf_close_position=80.0)
        features = embedder.extract_features(setup)
        assert abs(features[3] - 0.80) < 1e-5

    # -- HTF bias one-hot (indices 4-6) --

    def test_htf_bias_bullish_one_hot(self, embedder: StructuredFeatureEmbedder):
        """BULLISH → [1, 0, 0] at indices 4-6."""
        setup = _make_enriched_setup(htf_open_bias="BULLISH")
        f = embedder.extract_features(setup)
        assert f[4] == pytest.approx(1.0)
        assert f[5] == pytest.approx(0.0)
        assert f[6] == pytest.approx(0.0)

    def test_htf_bias_bearish_one_hot(self, embedder: StructuredFeatureEmbedder):
        """BEARISH → [0, 1, 0] at indices 4-6."""
        setup = _make_enriched_setup(htf_open_bias="BEARISH")
        f = embedder.extract_features(setup)
        assert f[4] == pytest.approx(0.0)
        assert f[5] == pytest.approx(1.0)
        assert f[6] == pytest.approx(0.0)

    def test_htf_bias_neutral_one_hot(self, embedder: StructuredFeatureEmbedder):
        """NEUTRAL → [0, 0, 1] at indices 4-6."""
        setup = _make_enriched_setup(htf_open_bias="NEUTRAL")
        f = embedder.extract_features(setup)
        assert f[4] == pytest.approx(0.0)
        assert f[5] == pytest.approx(0.0)
        assert f[6] == pytest.approx(1.0)

    # -- PD array flags (indices 7-10) --

    def test_bos_detected_true_at_index_7(self, embedder: StructuredFeatureEmbedder):
        setup = _make_enriched_setup(bos_detected=True)
        f = embedder.extract_features(setup)
        assert f[7] == pytest.approx(1.0)

    def test_bos_detected_false_at_index_7(self, embedder: StructuredFeatureEmbedder):
        setup = _make_enriched_setup(bos_detected=False)
        f = embedder.extract_features(setup)
        assert f[7] == pytest.approx(0.0)

    def test_choch_detected_at_index_8(self, embedder: StructuredFeatureEmbedder):
        setup_true = _make_enriched_setup(choch_detected=True)
        setup_false = _make_enriched_setup(choch_detected=False)
        assert embedder.extract_features(setup_true)[8] == pytest.approx(1.0)
        assert embedder.extract_features(setup_false)[8] == pytest.approx(0.0)

    def test_fvg_present_at_index_9(self, embedder: StructuredFeatureEmbedder):
        setup_true = _make_enriched_setup(fvg_present=True)
        setup_false = _make_enriched_setup(fvg_present=False)
        assert embedder.extract_features(setup_true)[9] == pytest.approx(1.0)
        assert embedder.extract_features(setup_false)[9] == pytest.approx(0.0)

    def test_liquidity_sweep_at_index_10(self, embedder: StructuredFeatureEmbedder):
        setup_true = _make_enriched_setup(liquidity_sweep=True)
        setup_false = _make_enriched_setup(liquidity_sweep=False)
        assert embedder.extract_features(setup_true)[10] == pytest.approx(1.0)
        assert embedder.extract_features(setup_false)[10] == pytest.approx(0.0)

    # -- Swing distances (indices 11-12) --

    def test_swing_distances_normalised(self, embedder: StructuredFeatureEmbedder):
        """Swing distances must be normalised to [0, 1]."""
        setup = _make_enriched_setup(swing_high_distance=0.005, swing_low_distance=0.003)
        f = embedder.extract_features(setup)
        assert 0.0 <= f[11] <= 1.0
        assert 0.0 <= f[12] <= 1.0

    # -- Session features (indices 13-14) --

    def test_time_window_weight_at_index_13(self, embedder: StructuredFeatureEmbedder):
        """time_window_weight already in [0, 1] — stored directly."""
        setup = _make_enriched_setup(time_window_weight=0.9)
        f = embedder.extract_features(setup)
        assert abs(f[13] - 0.9) < 1e-5

    def test_is_killzone_at_index_14(self, embedder: StructuredFeatureEmbedder):
        setup_true = _make_enriched_setup(is_killzone=True)
        setup_false = _make_enriched_setup(is_killzone=False)
        assert embedder.extract_features(setup_true)[14] == pytest.approx(1.0)
        assert embedder.extract_features(setup_false)[14] == pytest.approx(0.0)

    # -- Outcome (indices 15-16) --

    def test_r_multiple_normalised_at_index_15(
        self, embedder: StructuredFeatureEmbedder
    ):
        """r_multiple normalised with clip to [0, 10] then /10 → [0, 1]."""
        setup_pos = _make_enriched_setup(r_multiple=5.0, outcome_result="WIN")
        setup_neg = _make_enriched_setup(r_multiple=-2.0, outcome_result="LOSS")
        setup_extreme = _make_enriched_setup(r_multiple=15.0, outcome_result="WIN")

        f_pos = embedder.extract_features(setup_pos)
        f_neg = embedder.extract_features(setup_neg)
        f_extreme = embedder.extract_features(setup_extreme)

        assert abs(f_pos[15] - 0.5) < 1e-5     # 5 / 10 = 0.5
        assert f_neg[15] == pytest.approx(0.0)   # clip(-2) → 0
        assert f_extreme[15] == pytest.approx(1.0)  # clip(15) → 10, /10 → 1.0

    def test_outcome_win_one_hot_at_index_16(self, embedder: StructuredFeatureEmbedder):
        """WIN → 1.0 at index 16; LOSS → 0.0 at index 16."""
        setup_win = _make_enriched_setup(outcome_result="WIN")
        setup_loss = _make_enriched_setup(outcome_result="LOSS")
        assert embedder.extract_features(setup_win)[16] == pytest.approx(1.0)
        assert embedder.extract_features(setup_loss)[16] == pytest.approx(0.0)

    # -- Confluence count (index 17) --

    def test_confluence_count_normalised_at_index_17(
        self, embedder: StructuredFeatureEmbedder
    ):
        """confluence_count normalised as count / 10 → [0, 1]."""
        setup = _make_enriched_setup(confluence_count=5)
        f = embedder.extract_features(setup)
        assert abs(f[17] - 0.5) < 1e-5

    def test_confluence_count_max_clipped(self, embedder: StructuredFeatureEmbedder):
        """confluence_count beyond 10 clips to 1.0."""
        setup = _make_enriched_setup(confluence_count=15)
        f = embedder.extract_features(setup)
        assert f[17] == pytest.approx(1.0)

    # -- Padding (indices 18-63) --

    def test_padding_is_zeros(
        self, embedder: StructuredFeatureEmbedder, sample_setup: EnrichedSetup
    ):
        """Indices 18-63 (padding) must all be 0.0."""
        f = embedder.extract_features(sample_setup)
        np.testing.assert_array_equal(
            f[18:], np.zeros(FEATURE_VEC_DIM - 18, dtype=np.float32)
        )


# ---------------------------------------------------------------------------
# 3. Embedding output tests — embed()
# ---------------------------------------------------------------------------


class TestStructuredEmbedding:
    """Verify embed() projects 64 features to a 128-dim float32 vector."""

    def test_embed_returns_numpy_array(
        self, embedder: StructuredFeatureEmbedder, sample_setup: EnrichedSetup
    ):
        result = embedder.embed(sample_setup)
        assert isinstance(result, np.ndarray)

    def test_embed_returns_128_dim(
        self, embedder: StructuredFeatureEmbedder, sample_setup: EnrichedSetup
    ):
        result = embedder.embed(sample_setup)
        assert result.shape == (STRUCTURED_DIM,), (
            f"Expected ({STRUCTURED_DIM},), got {result.shape}"
        )

    def test_embed_dtype_float32(
        self, embedder: StructuredFeatureEmbedder, sample_setup: EnrichedSetup
    ):
        result = embedder.embed(sample_setup)
        assert result.dtype == np.float32

    def test_embed_no_nan(
        self, embedder: StructuredFeatureEmbedder, sample_setup: EnrichedSetup
    ):
        result = embedder.embed(sample_setup)
        assert not np.isnan(result).any(), "NaN values found in embedding"

    def test_embed_no_inf(
        self, embedder: StructuredFeatureEmbedder, sample_setup: EnrichedSetup
    ):
        result = embedder.embed(sample_setup)
        assert not np.isinf(result).any(), "Inf values found in embedding"

    def test_embed_win_differs_from_loss(self, embedder: StructuredFeatureEmbedder):
        """WIN and LOSS setups must produce different embeddings."""
        setup_win = _make_enriched_setup(outcome_result="WIN", r_multiple=2.0)
        setup_loss = _make_enriched_setup(outcome_result="LOSS", r_multiple=-1.0)
        emb_win = embedder.embed(setup_win)
        emb_loss = embedder.embed(setup_loss)
        assert not np.allclose(emb_win, emb_loss), (
            "WIN and LOSS setups produced identical embeddings"
        )

    def test_embed_bullish_differs_from_bearish(
        self, embedder: StructuredFeatureEmbedder
    ):
        """BULLISH and BEARISH HTF bias setups must produce different embeddings."""
        setup_bull = _make_enriched_setup(htf_open_bias="BULLISH")
        setup_bear = _make_enriched_setup(htf_open_bias="BEARISH")
        assert not np.allclose(
            embedder.embed(setup_bull), embedder.embed(setup_bear)
        )

    # -- Edge cases --

    def test_embed_all_zeros_setup(self, embedder: StructuredFeatureEmbedder):
        """Edge case: all numeric features at minimum values — no NaN."""
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
        )
        result = embedder.embed(setup)
        assert result.shape == (STRUCTURED_DIM,)
        assert not np.isnan(result).any()

    def test_embed_all_max_setup(self, embedder: StructuredFeatureEmbedder):
        """Edge case: all numeric features at maximum values — no NaN."""
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
        )
        result = embedder.embed(setup)
        assert result.shape == (STRUCTURED_DIM,)
        assert not np.isnan(result).any()

    def test_embed_extreme_r_multiple(self, embedder: StructuredFeatureEmbedder):
        """Large positive and negative r_multiple values are clipped gracefully."""
        setup_huge = _make_enriched_setup(r_multiple=999.0, outcome_result="WIN")
        setup_tiny = _make_enriched_setup(r_multiple=-999.0, outcome_result="LOSS")
        for setup in [setup_huge, setup_tiny]:
            result = embedder.embed(setup)
            assert result.shape == (STRUCTURED_DIM,)
            assert not np.isnan(result).any()


# ---------------------------------------------------------------------------
# 4. Determinism tests
# ---------------------------------------------------------------------------


class TestDeterminism:
    """The same setup must always produce the same embedding."""

    def test_embed_is_deterministic(
        self, embedder: StructuredFeatureEmbedder, sample_setup: EnrichedSetup
    ):
        v1 = embedder.embed(sample_setup)
        v2 = embedder.embed(sample_setup)
        np.testing.assert_array_equal(v1, v2)

    def test_extract_features_is_deterministic(
        self, embedder: StructuredFeatureEmbedder, sample_setup: EnrichedSetup
    ):
        f1 = embedder.extract_features(sample_setup)
        f2 = embedder.extract_features(sample_setup)
        np.testing.assert_array_equal(f1, f2)


# ---------------------------------------------------------------------------
# 5. Input validation tests
# ---------------------------------------------------------------------------


class TestInputValidation:
    """Verify StructuredFeatureEmbedder validates inputs."""

    def test_embed_raises_on_non_enriched_setup(
        self, embedder: StructuredFeatureEmbedder
    ):
        """embed() must raise TypeError for non-EnrichedSetup input."""
        with pytest.raises((TypeError, AttributeError, ValueError)):
            embedder.embed({"instrument": "EURUSD"})  # type: ignore[arg-type]

    def test_embed_raises_on_none(self, embedder: StructuredFeatureEmbedder):
        """embed() must raise TypeError for None input."""
        with pytest.raises((TypeError, AttributeError, ValueError)):
            embedder.embed(None)  # type: ignore[arg-type]

    def test_extract_features_raises_on_none(
        self, embedder: StructuredFeatureEmbedder
    ):
        """extract_features() must raise for None input."""
        with pytest.raises((TypeError, AttributeError, ValueError)):
            embedder.extract_features(None)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 6. Property-based tests
# ---------------------------------------------------------------------------


@pytest.mark.property
class TestStructuredFeatureEmbedderProperties:
    """
    Property-based tests enforcing invariants across diverse EnrichedSetup inputs.

    Validates: Requirements FR-RAG-2
    """

    @given(
        htf_high_pct=st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
        htf_low_pct=st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
        htf_body_pct=st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
        htf_close_pos=st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
        htf_bias=st.sampled_from(["BULLISH", "BEARISH", "NEUTRAL"]),
        bos=st.booleans(),
        choch=st.booleans(),
        fvg=st.booleans(),
        sweep=st.booleans(),
        tw_weight=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
        is_kz=st.booleans(),
        r_mult=st.floats(min_value=-10.0, max_value=20.0, allow_nan=False, allow_infinity=False),
        outcome=st.sampled_from(["WIN", "LOSS"]),
        conf_count=st.integers(min_value=0, max_value=15),
    )
    @settings(
        max_examples=40,
        suppress_health_check=[HealthCheck.too_slow],
        deadline=None,
    )
    def test_embed_always_128_dim_no_nan(
        self,
        htf_high_pct: float,
        htf_low_pct: float,
        htf_body_pct: float,
        htf_close_pos: float,
        htf_bias: str,
        bos: bool,
        choch: bool,
        fvg: bool,
        sweep: bool,
        tw_weight: float,
        is_kz: bool,
        r_mult: float,
        outcome: str,
        conf_count: int,
    ) -> None:
        """For arbitrary valid EnrichedSetup, embed() always returns (128,) with no NaN.

        Validates: Requirements FR-RAG-2
        """
        setup = _make_enriched_setup(
            htf_high_proximity_pct=htf_high_pct,
            htf_low_proximity_pct=htf_low_pct,
            htf_body_pct=htf_body_pct,
            htf_close_position=htf_close_pos,
            htf_open_bias=htf_bias,
            bos_detected=bos,
            choch_detected=choch,
            fvg_present=fvg,
            liquidity_sweep=sweep,
            time_window_weight=tw_weight,
            is_killzone=is_kz,
            r_multiple=r_mult,
            outcome_result=outcome,
            confluence_count=conf_count,
        )
        emb = StructuredFeatureEmbedder()
        result = emb.embed(setup)
        assert result.shape == (STRUCTURED_DIM,), (
            f"Expected ({STRUCTURED_DIM},), got {result.shape}"
        )
        assert not np.isnan(result).any(), "NaN values in embedding"
        assert not np.isinf(result).any(), "Inf values in embedding"

    @given(
        htf_high_pct=st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
        htf_body_pct=st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
        htf_bias=st.sampled_from(["BULLISH", "BEARISH", "NEUTRAL"]),
        tw_weight=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
        conf_count=st.integers(min_value=0, max_value=10),
    )
    @settings(
        max_examples=30,
        suppress_health_check=[HealthCheck.too_slow],
        deadline=None,
    )
    def test_feature_vector_always_64_dim_in_unit_range(
        self,
        htf_high_pct: float,
        htf_body_pct: float,
        htf_bias: str,
        tw_weight: float,
        conf_count: int,
    ) -> None:
        """For arbitrary inputs, extract_features() always returns 64-dim vector in [0, 1].

        Validates: Requirements FR-RAG-2
        """
        setup = _make_enriched_setup(
            htf_high_proximity_pct=htf_high_pct,
            htf_body_pct=htf_body_pct,
            htf_open_bias=htf_bias,
            time_window_weight=tw_weight,
            confluence_count=conf_count,
        )
        emb = StructuredFeatureEmbedder()
        features = emb.extract_features(setup)
        assert features.shape == (FEATURE_VEC_DIM,)
        assert (features >= 0.0).all(), f"Feature below 0: {features[features < 0]}"
        assert (features <= 1.0).all(), f"Feature above 1: {features[features > 1]}"
