"""
TDD – Task 8.1: Tests for load_initial_data.py pipeline components.

RED   phase: these tests define the expected behaviour BEFORE implementation.
GREEN phase: implementation in scripts/rag/load_initial_data.py satisfies assertions.
REFACTOR:    consolidate helpers, improve coverage.

Validates: FR-RAG-1 (Historical Setup Storage) — 500+ setups, 528-dim embeddings,
           enriched context, data quality report.
"""
from __future__ import annotations

import sys
import os
from datetime import datetime, timezone
from typing import Any, Dict, List

import numpy as np
import pytest

# Ensure workspace root is importable
_WORKSPACE_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../../..")
)
if _WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, _WORKSPACE_ROOT)

# ---------------------------------------------------------------------------
# Deferred imports so RED tests can be collected even before the module exists
# ---------------------------------------------------------------------------

def _import_module():
    """Lazy import of the module under test so collection doesn't fail on RED."""
    from scripts.rag.load_initial_data import (  # noqa: F401
        build_structured_embedding,
        build_temporal_embedding,
        build_combined_embedding,
        generate_data_quality_report,
        DataLoader,
    )
    return (
        build_structured_embedding,
        build_temporal_embedding,
        build_combined_embedding,
        generate_data_quality_report,
        DataLoader,
    )


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def sample_enriched_setup():
    """Return a minimal EnrichedSetup instance for embedding tests."""
    from scripts.rag.utils.setup_enricher import EnrichedSetup

    return EnrichedSetup(
        trade_id="TRD-TEST-001",
        timestamp=datetime(2024, 1, 15, 9, 15, 0, tzinfo=timezone.utc),
        instrument="EURUSD",
        direction="BUY",
        entry_price=1.5050,
        exit_price=1.5100,
        stop_loss=1.5000,
        take_profit=1.5150,
        r_multiple=2.5,
        outcome_result="WIN",
        htf_timeframe="H1",
        htf_open=1.5000,
        htf_high=1.5200,
        htf_low=1.4900,
        htf_open_bias="BULLISH",
        htf_high_proximity_pct=50.0,
        htf_low_proximity_pct=50.0,
        htf_body_pct=70.0,
        htf_close_position=0.5,
        bos_detected=True,
        choch_detected=False,
        fvg_present=True,
        liquidity_sweep=False,
        swing_high_distance=0.005,
        swing_low_distance=0.003,
        htf_trend_bias="BULLISH",
        time_window="LONDON_KILLZONE",
        narrative_phase="MANIPULATION",
        time_window_weight=0.9,
        is_killzone=True,
        narrative="Price swept the Asian low before reversing bullish with BOS confirmed.",
        confluence_count=4,
    )


@pytest.fixture(scope="module")
def sample_timestamp():
    """Return a fixed UTC timestamp for temporal embedding tests."""
    return datetime(2024, 1, 15, 9, 15, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# 1. build_structured_embedding tests
# ---------------------------------------------------------------------------


class TestBuildStructuredEmbedding:
    """Unit tests for build_structured_embedding(enriched_setup) → np.ndarray."""

    def test_returns_numpy_array(self, sample_enriched_setup):
        """build_structured_embedding must return a numpy ndarray."""
        (build_structured_embedding, *_) = _import_module()
        result = build_structured_embedding(sample_enriched_setup)
        assert isinstance(result, np.ndarray)

    def test_returns_128_dim(self, sample_enriched_setup):
        """build_structured_embedding must return exactly 128-dim array."""
        (build_structured_embedding, *_) = _import_module()
        result = build_structured_embedding(sample_enriched_setup)
        assert result.shape == (128,), f"Expected (128,), got {result.shape}"

    def test_dtype_is_float32(self, sample_enriched_setup):
        """build_structured_embedding must return float32 dtype."""
        (build_structured_embedding, *_) = _import_module()
        result = build_structured_embedding(sample_enriched_setup)
        assert result.dtype == np.float32

    def test_no_nan_values(self, sample_enriched_setup):
        """build_structured_embedding must not contain NaN values."""
        (build_structured_embedding, *_) = _import_module()
        result = build_structured_embedding(sample_enriched_setup)
        assert not np.isnan(result).any(), "NaN found in structured embedding"

    def test_no_inf_values(self, sample_enriched_setup):
        """build_structured_embedding must not contain Inf values."""
        (build_structured_embedding, *_) = _import_module()
        result = build_structured_embedding(sample_enriched_setup)
        assert not np.isinf(result).any(), "Inf found in structured embedding"

    def test_is_deterministic(self, sample_enriched_setup):
        """Same enriched setup always produces identical structured embedding."""
        (build_structured_embedding, *_) = _import_module()
        v1 = build_structured_embedding(sample_enriched_setup)
        v2 = build_structured_embedding(sample_enriched_setup)
        np.testing.assert_array_equal(v1, v2)

    def test_bullish_bias_differs_from_bearish(self, sample_enriched_setup):
        """BULLISH and BEARISH HTF bias produce different structured embeddings."""
        from scripts.rag.utils.setup_enricher import EnrichedSetup

        (build_structured_embedding, *_) = _import_module()

        bearish_setup = sample_enriched_setup.model_copy(
            update={"htf_open_bias": "BEARISH", "outcome_result": "LOSS", "r_multiple": -1.0}
        )
        v_bullish = build_structured_embedding(sample_enriched_setup)
        v_bearish = build_structured_embedding(bearish_setup)
        assert not np.array_equal(v_bullish, v_bearish), (
            "BULLISH and BEARISH bias should produce different embeddings"
        )


# ---------------------------------------------------------------------------
# 2. build_temporal_embedding tests
# ---------------------------------------------------------------------------


class TestBuildTemporalEmbedding:
    """Unit tests for build_temporal_embedding(timestamp) → np.ndarray."""

    def test_returns_numpy_array(self, sample_timestamp):
        """build_temporal_embedding must return a numpy ndarray."""
        (_, build_temporal_embedding, *_) = _import_module()
        result = build_temporal_embedding(sample_timestamp)
        assert isinstance(result, np.ndarray)

    def test_returns_16_dim(self, sample_timestamp):
        """build_temporal_embedding must return exactly 16-dim array."""
        (_, build_temporal_embedding, *_) = _import_module()
        result = build_temporal_embedding(sample_timestamp)
        assert result.shape == (16,), f"Expected (16,), got {result.shape}"

    def test_dtype_is_float32(self, sample_timestamp):
        """build_temporal_embedding must return float32 dtype."""
        (_, build_temporal_embedding, *_) = _import_module()
        result = build_temporal_embedding(sample_timestamp)
        assert result.dtype == np.float32

    def test_no_nan_values(self, sample_timestamp):
        """build_temporal_embedding must not contain NaN values."""
        (_, build_temporal_embedding, *_) = _import_module()
        result = build_temporal_embedding(sample_timestamp)
        assert not np.isnan(result).any(), "NaN found in temporal embedding"

    def test_values_in_valid_range(self, sample_timestamp):
        """The first 6 cyclical dims must be in [-1, 1]; dims 6-15 must be 0."""
        (_, build_temporal_embedding, *_) = _import_module()
        result = build_temporal_embedding(sample_timestamp)
        assert np.all(result[:6] >= -1.0) and np.all(result[:6] <= 1.0), (
            f"Cyclical dims out of [-1, 1] range: {result[:6]}"
        )
        np.testing.assert_array_equal(
            result[6:], np.zeros(10, dtype=np.float32),
            err_msg="Reserved dims 6-15 must be zero"
        )

    def test_is_deterministic(self, sample_timestamp):
        """Same timestamp always produces identical temporal embedding."""
        (_, build_temporal_embedding, *_) = _import_module()
        v1 = build_temporal_embedding(sample_timestamp)
        v2 = build_temporal_embedding(sample_timestamp)
        np.testing.assert_array_equal(v1, v2)

    def test_different_hours_produce_different_embeddings(self):
        """Different hours produce different temporal embeddings."""
        (_, build_temporal_embedding, *_) = _import_module()
        t1 = datetime(2024, 1, 15, 9, 0, 0, tzinfo=timezone.utc)
        t2 = datetime(2024, 1, 15, 15, 0, 0, tzinfo=timezone.utc)
        v1 = build_temporal_embedding(t1)
        v2 = build_temporal_embedding(t2)
        assert not np.array_equal(v1, v2), (
            "Different hours should produce different temporal embeddings"
        )

    def test_cyclical_hour_encoding(self):
        """Hour 0 and hour 24 should map to the same sin/cos values (cyclical)."""
        (_, build_temporal_embedding, *_) = _import_module()
        t_midnight = datetime(2024, 1, 15, 0, 0, 0, tzinfo=timezone.utc)
        t_day_after = datetime(2024, 1, 16, 0, 0, 0, tzinfo=timezone.utc)
        v1 = build_temporal_embedding(t_midnight)
        v2 = build_temporal_embedding(t_day_after)
        # hour_sin and hour_cos (dims 0 and 1) must be equal
        np.testing.assert_almost_equal(v1[0], v2[0], decimal=5)
        np.testing.assert_almost_equal(v1[1], v2[1], decimal=5)


# ---------------------------------------------------------------------------
# 3. build_combined_embedding tests
# ---------------------------------------------------------------------------


class TestBuildCombinedEmbedding:
    """Unit tests for build_combined_embedding(narrative, enriched_setup, model)."""

    @pytest.fixture(scope="class")
    def narrative_model(self):
        """Load the SBERT model once for the test class."""
        from services.algorag.embedding_models import get_embedding_model
        return get_embedding_model()

    def test_returns_numpy_array(self, sample_enriched_setup, narrative_model):
        """build_combined_embedding must return a numpy ndarray."""
        (*_, build_combined_embedding, _, __) = _import_module()
        result = build_combined_embedding(
            sample_enriched_setup.narrative, sample_enriched_setup, narrative_model
        )
        assert isinstance(result, np.ndarray)

    def test_returns_528_dim(self, sample_enriched_setup, narrative_model):
        """build_combined_embedding must return exactly 528-dim array."""
        (*_, build_combined_embedding, _, __) = _import_module()
        result = build_combined_embedding(
            sample_enriched_setup.narrative, sample_enriched_setup, narrative_model
        )
        assert result.shape == (528,), f"Expected (528,), got {result.shape}"

    def test_dtype_is_float32(self, sample_enriched_setup, narrative_model):
        """build_combined_embedding must return float32 dtype."""
        (*_, build_combined_embedding, _, __) = _import_module()
        result = build_combined_embedding(
            sample_enriched_setup.narrative, sample_enriched_setup, narrative_model
        )
        assert result.dtype == np.float32

    def test_no_nan_values(self, sample_enriched_setup, narrative_model):
        """build_combined_embedding must not contain NaN values."""
        (*_, build_combined_embedding, _, __) = _import_module()
        result = build_combined_embedding(
            sample_enriched_setup.narrative, sample_enriched_setup, narrative_model
        )
        assert not np.isnan(result).any(), "NaN found in combined embedding"

    def test_no_inf_values(self, sample_enriched_setup, narrative_model):
        """build_combined_embedding must not contain Inf values."""
        (*_, build_combined_embedding, _, __) = _import_module()
        result = build_combined_embedding(
            sample_enriched_setup.narrative, sample_enriched_setup, narrative_model
        )
        assert not np.isinf(result).any(), "Inf found in combined embedding"

    def test_dimension_composition(self, sample_enriched_setup, narrative_model):
        """528-dim = 384*0.4 + 128*0.4 + 16*0.2 weight-scaled concatenation."""
        (
            build_structured_embedding,
            build_temporal_embedding,
            build_combined_embedding,
            _,
            __,
        ) = _import_module()
        from services.algorag.embedding_models import get_embedding_model

        model = get_embedding_model()
        narrative_part = model.encode(sample_enriched_setup.narrative) * 0.4
        structured_part = build_structured_embedding(sample_enriched_setup) * 0.4
        temporal_part = build_temporal_embedding(sample_enriched_setup.timestamp) * 0.2

        expected = np.concatenate([narrative_part, structured_part, temporal_part]).astype(np.float32)
        result = build_combined_embedding(
            sample_enriched_setup.narrative, sample_enriched_setup, model
        )
        np.testing.assert_array_almost_equal(result, expected, decimal=5)


# ---------------------------------------------------------------------------
# 4. generate_data_quality_report tests
# ---------------------------------------------------------------------------


class TestGenerateDataQualityReport:
    """Unit tests for generate_data_quality_report(successful_setups, errors)."""

    def _make_successful_setups(self, n: int = 5) -> List[Dict[str, Any]]:
        """Build a list of minimal successful setup dicts."""
        setups = []
        for i in range(n):
            setups.append({
                "trade_id": f"TRD-{i:03d}",
                "instrument": "EURUSD",
                "r_multiple": 2.0 if i % 2 == 0 else -1.0,
                "outcome_result": "WIN" if i % 2 == 0 else "LOSS",
            })
        return setups

    def test_returns_dict(self):
        """generate_data_quality_report must return a dict."""
        (*_, generate_data_quality_report, _) = _import_module()
        result = generate_data_quality_report(self._make_successful_setups(), [])
        assert isinstance(result, dict)

    def test_contains_required_keys(self):
        """Report must contain: total, successful, failed, error_rate_pct, avg_r_multiple, win_rate, instruments."""
        (*_, generate_data_quality_report, _) = _import_module()
        result = generate_data_quality_report(self._make_successful_setups(5), [])
        required_keys = {
            "total",
            "successful",
            "failed",
            "error_rate_pct",
            "avg_r_multiple",
            "win_rate",
            "instruments",
        }
        missing = required_keys - set(result.keys())
        assert not missing, f"Report missing keys: {missing}"

    def test_total_is_sum_of_successful_and_failed(self):
        """total == successful + failed."""
        (*_, generate_data_quality_report, _) = _import_module()
        errors = [{"trade_id": "ERR-001", "error": "timeout"}]
        result = generate_data_quality_report(self._make_successful_setups(4), errors)
        assert result["total"] == result["successful"] + result["failed"]

    def test_error_rate_zero_when_no_errors(self):
        """error_rate_pct must be 0.0 when no errors occurred."""
        (*_, generate_data_quality_report, _) = _import_module()
        result = generate_data_quality_report(self._make_successful_setups(10), [])
        assert result["error_rate_pct"] == 0.0

    def test_error_rate_correct_percentage(self):
        """error_rate_pct = (failed / total) * 100."""
        (*_, generate_data_quality_report, _) = _import_module()
        errors = [{"trade_id": f"ERR-{i}", "error": "fail"} for i in range(1)]
        result = generate_data_quality_report(self._make_successful_setups(9), errors)
        assert result["total"] == 10
        assert abs(result["error_rate_pct"] - 10.0) < 0.01

    def test_avg_r_multiple_computed_correctly(self):
        """avg_r_multiple is the mean of r_multiple values in successful setups."""
        (*_, generate_data_quality_report, _) = _import_module()
        setups = [
            {"trade_id": "T1", "instrument": "EURUSD", "r_multiple": 2.0, "outcome_result": "WIN"},
            {"trade_id": "T2", "instrument": "EURUSD", "r_multiple": 4.0, "outcome_result": "WIN"},
        ]
        result = generate_data_quality_report(setups, [])
        assert abs(result["avg_r_multiple"] - 3.0) < 0.01

    def test_win_rate_computed_correctly(self):
        """win_rate is proportion of WIN outcomes in successful setups."""
        (*_, generate_data_quality_report, _) = _import_module()
        setups = [
            {"trade_id": "T1", "instrument": "EURUSD", "r_multiple": 2.0, "outcome_result": "WIN"},
            {"trade_id": "T2", "instrument": "EURUSD", "r_multiple": -1.0, "outcome_result": "LOSS"},
            {"trade_id": "T3", "instrument": "EURUSD", "r_multiple": 1.5, "outcome_result": "WIN"},
            {"trade_id": "T4", "instrument": "EURUSD", "r_multiple": -1.0, "outcome_result": "LOSS"},
        ]
        result = generate_data_quality_report(setups, [])
        assert abs(result["win_rate"] - 0.5) < 0.01

    def test_instruments_found_lists_unique_instruments(self):
        """instruments field lists the distinct instruments in successful setups."""
        (*_, generate_data_quality_report, _) = _import_module()
        setups = [
            {"trade_id": "T1", "instrument": "EURUSD", "r_multiple": 1.0, "outcome_result": "WIN"},
            {"trade_id": "T2", "instrument": "XAUUSD", "r_multiple": 1.0, "outcome_result": "WIN"},
            {"trade_id": "T3", "instrument": "EURUSD", "r_multiple": 1.0, "outcome_result": "WIN"},
        ]
        result = generate_data_quality_report(setups, [])
        assert set(result["instruments"]) == {"EURUSD", "XAUUSD"}

    def test_empty_setups_returns_zero_report(self):
        """Empty successful setups and errors returns zeroed report (no ZeroDivisionError)."""
        (*_, generate_data_quality_report, _) = _import_module()
        result = generate_data_quality_report([], [])
        assert result["total"] == 0
        assert result["successful"] == 0
        assert result["error_rate_pct"] == 0.0
        assert result["win_rate"] == 0.0


# ---------------------------------------------------------------------------
# 5. DataLoader tests
# ---------------------------------------------------------------------------


class TestDataLoader:
    """Tests for DataLoader.load_from_journal() — should return at least 1 trade."""

    def test_load_from_journal_returns_list(self):
        """load_from_journal must return a list."""
        (*_, DataLoader) = _import_module()
        loader = DataLoader()
        result = loader.load_from_journal(limit=5)
        assert isinstance(result, list)

    def test_load_from_journal_returns_at_least_one(self):
        """load_from_journal must return at least 1 trade dict."""
        (*_, DataLoader) = _import_module()
        loader = DataLoader()
        result = loader.load_from_journal(limit=5)
        assert len(result) >= 1, "Expected at least 1 trade from load_from_journal"

    def test_load_from_journal_respects_limit(self):
        """load_from_journal(limit=N) should not return more than N trades."""
        (*_, DataLoader) = _import_module()
        loader = DataLoader()
        result = loader.load_from_journal(limit=3)
        assert len(result) <= 3

    def test_load_from_journal_returns_dicts(self):
        """Each item in load_from_journal result must be a dict."""
        (*_, DataLoader) = _import_module()
        loader = DataLoader()
        result = loader.load_from_journal(limit=3)
        for item in result:
            assert isinstance(item, dict), f"Expected dict, got {type(item)}"

    def test_load_from_journal_trade_has_trade_id(self):
        """Each trade dict must have a 'trade_id' key."""
        (*_, DataLoader) = _import_module()
        loader = DataLoader()
        result = loader.load_from_journal(limit=3)
        for trade in result:
            assert "trade_id" in trade, "Trade missing 'trade_id' key"

    def test_load_candles_for_trade_returns_tuple(self):
        """load_candles_for_trade must return a tuple of (candles, htf_candles)."""
        (*_, DataLoader) = _import_module()
        loader = DataLoader()
        trades = loader.load_from_journal(limit=1)
        candles, htf_candles = loader.load_candles_for_trade(trades[0])
        assert isinstance(candles, list)
        assert isinstance(htf_candles, list)

    def test_load_candles_returns_non_empty_candles(self):
        """load_candles_for_trade must return non-empty candle lists."""
        (*_, DataLoader) = _import_module()
        loader = DataLoader()
        trades = loader.load_from_journal(limit=1)
        candles, htf_candles = loader.load_candles_for_trade(trades[0])
        assert len(candles) > 0, "Expected non-empty candles"
        assert len(htf_candles) > 0, "Expected non-empty htf_candles"


# ---------------------------------------------------------------------------
# 6. Integration test — full pipeline from load → enrich → embed → ingest
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestFullPipelineIntegration:
    """
    End-to-end integration test: load → enrich → embed → ingest → report.
    Requires Qdrant running on localhost:6333.
    """

    @pytest.mark.asyncio
    async def test_full_pipeline_runs_without_error(self):
        """Running main() with dry_run=True completes without exception."""
        from scripts.rag.load_initial_data import main

        # dry_run=True skips Qdrant ingestion, safe to run without Qdrant
        report = await main(limit=5, output_path="data/test_enriched_setups.json", dry_run=True)
        assert report is not None
        assert isinstance(report, dict)

    @pytest.mark.asyncio
    async def test_pipeline_produces_quality_report(self):
        """Full pipeline with dry_run produces a quality report with expected keys."""
        from scripts.rag.load_initial_data import main

        report = await main(limit=5, output_path="data/test_enriched_setups.json", dry_run=True)
        required = {"total", "successful", "failed", "error_rate_pct", "avg_r_multiple", "win_rate"}
        missing = required - set(report.keys())
        assert not missing, f"Quality report missing keys: {missing}"

    @pytest.mark.asyncio
    async def test_pipeline_enriches_at_least_one_setup(self):
        """Full pipeline with dry_run enriches and embeds at least one setup."""
        from scripts.rag.load_initial_data import main

        report = await main(limit=5, output_path="data/test_enriched_setups.json", dry_run=True)
        assert report["successful"] >= 1, (
            f"Expected at least 1 successful setup, got {report['successful']}"
        )
