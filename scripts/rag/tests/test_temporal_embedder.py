"""
TDD – Task 4.4: Tests for TemporalEmbedder pipeline component.

RED  phase: tests that define the expected behaviour of TemporalEmbedder
            before the implementation exists.
GREEN phase: implementation in scripts/rag/utils/temporal_embedder.py
             satisfies all assertions.
REFACTOR: timezone normalization, robust input validation.

Validates: Requirements FR-RAG-2 (multi-modal embeddings – temporal component).

Invariants enforced:
- Output is always exactly 16-dim
- No NaN values in output
- Same input always produces same output (determinism)
- Values in dims 0–5 are in [-1.0, 1.0]
- Dims 6–15 are all zeros (reserved)
- Cyclical property: hour 0 and hour 24 map to same encoding
- Timezone normalization: UTC and aware datetime (same moment) produce same embedding
"""

from __future__ import annotations

import math
from datetime import datetime, timezone, timedelta

import numpy as np
import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

from scripts.rag.utils.temporal_embedder import TemporalEmbedder

TEMPORAL_DIM = 16


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def embedder() -> TemporalEmbedder:
    """Shared TemporalEmbedder instance."""
    return TemporalEmbedder()


@pytest.fixture
def sample_ts() -> datetime:
    """A fixed UTC-aware timestamp for deterministic tests."""
    return datetime(2024, 3, 15, 9, 15, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# 1. Instantiation
# ---------------------------------------------------------------------------


class TestTemporalEmbedderInstantiation:
    """Verify TemporalEmbedder can be created and exposes the encode() method."""

    def test_instantiates_without_error(self):
        emb = TemporalEmbedder()
        assert emb is not None

    def test_has_encode_method(self, embedder: TemporalEmbedder):
        assert callable(getattr(embedder, "encode", None))


# ---------------------------------------------------------------------------
# 2. Output shape and type
# ---------------------------------------------------------------------------


class TestOutputShapeAndType:
    """Verify encode() returns a 16-dim float64 array."""

    def test_returns_numpy_array(self, embedder: TemporalEmbedder, sample_ts: datetime):
        result = embedder.encode(sample_ts)
        assert isinstance(result, np.ndarray)

    def test_output_shape_is_16(self, embedder: TemporalEmbedder, sample_ts: datetime):
        result = embedder.encode(sample_ts)
        assert result.shape == (TEMPORAL_DIM,), (
            f"Expected shape ({TEMPORAL_DIM},), got {result.shape}"
        )

    def test_output_dtype_is_float64(self, embedder: TemporalEmbedder, sample_ts: datetime):
        result = embedder.encode(sample_ts)
        assert result.dtype == np.float64


# ---------------------------------------------------------------------------
# 3. No NaN values
# ---------------------------------------------------------------------------


class TestNoNaNValues:
    """Verify encode() output never contains NaN."""

    def test_no_nan_for_regular_timestamp(self, embedder: TemporalEmbedder, sample_ts: datetime):
        result = embedder.encode(sample_ts)
        assert not np.isnan(result).any(), "NaN values found in output"

    def test_no_nan_for_midnight(self, embedder: TemporalEmbedder):
        ts = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        result = embedder.encode(ts)
        assert not np.isnan(result).any()

    def test_no_nan_for_end_of_year(self, embedder: TemporalEmbedder):
        ts = datetime(2024, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
        result = embedder.encode(ts)
        assert not np.isnan(result).any()


# ---------------------------------------------------------------------------
# 4. Determinism
# ---------------------------------------------------------------------------


class TestDeterminism:
    """Same timestamp must always produce the same embedding."""

    def test_same_timestamp_same_result(self, embedder: TemporalEmbedder, sample_ts: datetime):
        v1 = embedder.encode(sample_ts)
        v2 = embedder.encode(sample_ts)
        np.testing.assert_array_equal(v1, v2)

    def test_different_timestamps_different_results(self, embedder: TemporalEmbedder):
        ts1 = datetime(2024, 3, 15, 9, 0, 0, tzinfo=timezone.utc)
        ts2 = datetime(2024, 3, 15, 14, 0, 0, tzinfo=timezone.utc)
        v1 = embedder.encode(ts1)
        v2 = embedder.encode(ts2)
        assert not np.array_equal(v1, v2), "Different timestamps should produce different embeddings"


# ---------------------------------------------------------------------------
# 5. Value ranges
# ---------------------------------------------------------------------------


class TestValueRanges:
    """dims 0-5 must be in [-1, 1]; dims 6-15 must be zero."""

    def test_dims_0_to_5_in_range(self, embedder: TemporalEmbedder, sample_ts: datetime):
        result = embedder.encode(sample_ts)
        for i in range(6):
            assert -1.0 <= result[i] <= 1.0, (
                f"Dim {i} value {result[i]} is outside [-1.0, 1.0]"
            )

    def test_dims_6_to_15_are_zeros(self, embedder: TemporalEmbedder, sample_ts: datetime):
        result = embedder.encode(sample_ts)
        np.testing.assert_array_equal(
            result[6:],
            np.zeros(10),
            err_msg="Dims 6-15 (reserved) must all be zero",
        )

    def test_dims_6_to_15_are_zeros_various_timestamps(self, embedder: TemporalEmbedder):
        timestamps = [
            datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc),
            datetime(2024, 6, 15, 12, 30, tzinfo=timezone.utc),
            datetime(2024, 12, 31, 23, 59, tzinfo=timezone.utc),
        ]
        for ts in timestamps:
            result = embedder.encode(ts)
            np.testing.assert_array_equal(result[6:], np.zeros(10))


# ---------------------------------------------------------------------------
# 6. Cyclical encoding correctness
# ---------------------------------------------------------------------------


class TestCyclicalEncoding:
    """Verify the sin/cos formulas match the spec exactly."""

    def test_hour_encoding_at_midnight(self, embedder: TemporalEmbedder):
        """Hour 0 → sin(0) = 0, cos(0) = 1."""
        ts = datetime(2024, 3, 15, 0, 0, 0, tzinfo=timezone.utc)
        result = embedder.encode(ts)
        expected_sin = math.sin(2 * math.pi * 0 / 24)  # 0.0
        expected_cos = math.cos(2 * math.pi * 0 / 24)  # 1.0
        assert math.isclose(result[0], expected_sin, abs_tol=1e-12)
        assert math.isclose(result[1], expected_cos, abs_tol=1e-12)

    def test_hour_encoding_at_noon(self, embedder: TemporalEmbedder):
        """Hour 12 → sin(π) ≈ 0, cos(π) = -1."""
        ts = datetime(2024, 3, 15, 12, 0, 0, tzinfo=timezone.utc)
        result = embedder.encode(ts)
        expected_sin = math.sin(2 * math.pi * 12 / 24)
        expected_cos = math.cos(2 * math.pi * 12 / 24)
        assert math.isclose(result[0], expected_sin, abs_tol=1e-12)
        assert math.isclose(result[1], expected_cos, abs_tol=1e-12)

    def test_hour_encoding_at_6am(self, embedder: TemporalEmbedder):
        """Hour 6 → sin(π/2) = 1, cos(π/2) ≈ 0."""
        ts = datetime(2024, 3, 15, 6, 0, 0, tzinfo=timezone.utc)
        result = embedder.encode(ts)
        expected_sin = math.sin(2 * math.pi * 6 / 24)
        expected_cos = math.cos(2 * math.pi * 6 / 24)
        assert math.isclose(result[0], expected_sin, abs_tol=1e-12)
        assert math.isclose(result[1], expected_cos, abs_tol=1e-12)

    def test_dow_encoding(self, embedder: TemporalEmbedder):
        """Check day-of-week sin/cos for a known Monday (weekday 0)."""
        # 2024-03-11 is a Monday (weekday() == 0)
        ts = datetime(2024, 3, 11, 9, 0, 0, tzinfo=timezone.utc)
        result = embedder.encode(ts)
        dow = ts.weekday()  # 0
        expected_sin = math.sin(2 * math.pi * dow / 5)
        expected_cos = math.cos(2 * math.pi * dow / 5)
        assert math.isclose(result[2], expected_sin, abs_tol=1e-12)
        assert math.isclose(result[3], expected_cos, abs_tol=1e-12)

    def test_month_encoding_january(self, embedder: TemporalEmbedder):
        """January → month=1, sin(2π*1/12), cos(2π*1/12)."""
        ts = datetime(2024, 1, 15, 9, 0, 0, tzinfo=timezone.utc)
        result = embedder.encode(ts)
        expected_sin = math.sin(2 * math.pi * 1 / 12)
        expected_cos = math.cos(2 * math.pi * 1 / 12)
        assert math.isclose(result[4], expected_sin, abs_tol=1e-12)
        assert math.isclose(result[5], expected_cos, abs_tol=1e-12)

    def test_month_encoding_december(self, embedder: TemporalEmbedder):
        """December → month=12."""
        ts = datetime(2024, 12, 15, 9, 0, 0, tzinfo=timezone.utc)
        result = embedder.encode(ts)
        expected_sin = math.sin(2 * math.pi * 12 / 12)
        expected_cos = math.cos(2 * math.pi * 12 / 12)
        assert math.isclose(result[4], expected_sin, abs_tol=1e-12)
        assert math.isclose(result[5], expected_cos, abs_tol=1e-12)


# ---------------------------------------------------------------------------
# 7. Cyclical wraparound (hour 0 == hour 24 modulo)
# ---------------------------------------------------------------------------


class TestCyclicalWraparound:
    """Hour 0 and the equivalent of hour 24 (next midnight) share encoding."""

    def test_hour_0_and_hour_24_same_encoding(self, embedder: TemporalEmbedder):
        """
        Hour 0 on day D and hour 0 on day D+1 have the same hour encoding.
        The difference lies only in the day-of-week component.
        """
        ts_midnight_1 = datetime(2024, 3, 15, 0, 0, 0, tzinfo=timezone.utc)
        ts_midnight_2 = datetime(2024, 3, 16, 0, 0, 0, tzinfo=timezone.utc)
        v1 = embedder.encode(ts_midnight_1)
        v2 = embedder.encode(ts_midnight_2)
        # Hour dims (0, 1) must be identical
        assert math.isclose(v1[0], v2[0], abs_tol=1e-12), "hour_sin differs"
        assert math.isclose(v1[1], v2[1], abs_tol=1e-12), "hour_cos differs"


# ---------------------------------------------------------------------------
# 8. Timezone normalization (REFACTOR step)
# ---------------------------------------------------------------------------


class TestTimezoneNormalization:
    """UTC and timezone-aware datetime for the same moment produce same embedding."""

    def test_naive_datetime_treated_as_utc(self, embedder: TemporalEmbedder):
        """A naive datetime should be treated as UTC and match explicit UTC."""
        naive_ts = datetime(2024, 3, 15, 9, 15, 0)  # no tzinfo
        utc_ts = datetime(2024, 3, 15, 9, 15, 0, tzinfo=timezone.utc)
        v_naive = embedder.encode(naive_ts)
        v_utc = embedder.encode(utc_ts)
        np.testing.assert_array_equal(v_naive, v_utc)

    def test_aware_non_utc_converted_to_utc(self, embedder: TemporalEmbedder):
        """
        UTC+2 timestamp at 11:15 is the same moment as UTC at 09:15.
        The embedding should use the UTC hour (9), not the local hour (11).
        """
        utc_plus_2 = timezone(timedelta(hours=2))
        local_ts = datetime(2024, 3, 15, 11, 15, 0, tzinfo=utc_plus_2)
        utc_ts = datetime(2024, 3, 15, 9, 15, 0, tzinfo=timezone.utc)
        v_local = embedder.encode(local_ts)
        v_utc = embedder.encode(utc_ts)
        np.testing.assert_array_equal(v_local, v_utc)

    def test_utc_minus_5_converted_correctly(self, embedder: TemporalEmbedder):
        """
        UTC-5 timestamp at 04:15 is the same moment as UTC at 09:15.
        """
        utc_minus_5 = timezone(timedelta(hours=-5))
        local_ts = datetime(2024, 3, 15, 4, 15, 0, tzinfo=utc_minus_5)
        utc_ts = datetime(2024, 3, 15, 9, 15, 0, tzinfo=timezone.utc)
        v_local = embedder.encode(local_ts)
        v_utc = embedder.encode(utc_ts)
        np.testing.assert_array_equal(v_local, v_utc)


# ---------------------------------------------------------------------------
# 9. Property-based tests
# ---------------------------------------------------------------------------


@pytest.mark.property
class TestTemporalEmbedderProperties:
    """
    Property-based tests enforcing invariants across arbitrary valid UTC timestamps.

    Validates: Requirements FR-RAG-2
    """

    @given(
        ts=st.datetimes(
            min_value=datetime(2010, 1, 1),
            max_value=datetime(2035, 12, 31),
            timezones=st.just(timezone.utc),
        )
    )
    @settings(
        max_examples=50,
        suppress_health_check=[HealthCheck.too_slow],
        deadline=None,
    )
    def test_output_always_16_dim(self, ts: datetime) -> None:
        """For any valid UTC timestamp, encode() produces a 16-dim vector.

        Validates: Requirements FR-RAG-2
        """
        emb = TemporalEmbedder()
        result = emb.encode(ts)
        assert result.shape == (TEMPORAL_DIM,), (
            f"Expected (16,), got {result.shape} for ts={ts}"
        )

    @given(
        ts=st.datetimes(
            min_value=datetime(2010, 1, 1),
            max_value=datetime(2035, 12, 31),
            timezones=st.just(timezone.utc),
        )
    )
    @settings(
        max_examples=50,
        suppress_health_check=[HealthCheck.too_slow],
        deadline=None,
    )
    def test_output_never_contains_nan(self, ts: datetime) -> None:
        """For any valid UTC timestamp, encode() output never contains NaN.

        Validates: Requirements FR-RAG-2
        """
        emb = TemporalEmbedder()
        result = emb.encode(ts)
        assert not np.isnan(result).any(), f"NaN values found for ts={ts}"

    @given(
        ts=st.datetimes(
            min_value=datetime(2010, 1, 1),
            max_value=datetime(2035, 12, 31),
            timezones=st.just(timezone.utc),
        )
    )
    @settings(
        max_examples=50,
        suppress_health_check=[HealthCheck.too_slow],
        deadline=None,
    )
    def test_dims_0_to_5_always_in_range(self, ts: datetime) -> None:
        """For any valid UTC timestamp, dims 0-5 are in [-1.0, 1.0].

        Validates: Requirements FR-RAG-2
        """
        emb = TemporalEmbedder()
        result = emb.encode(ts)
        for i in range(6):
            assert -1.0 <= result[i] <= 1.0, (
                f"Dim {i} value {result[i]:.6f} out of range for ts={ts}"
            )

    @given(
        ts=st.datetimes(
            min_value=datetime(2010, 1, 1),
            max_value=datetime(2035, 12, 31),
            timezones=st.just(timezone.utc),
        )
    )
    @settings(
        max_examples=50,
        suppress_health_check=[HealthCheck.too_slow],
        deadline=None,
    )
    def test_reserved_dims_always_zero(self, ts: datetime) -> None:
        """For any valid UTC timestamp, dims 6-15 are always zero.

        Validates: Requirements FR-RAG-2
        """
        emb = TemporalEmbedder()
        result = emb.encode(ts)
        np.testing.assert_array_equal(result[6:], np.zeros(10))
