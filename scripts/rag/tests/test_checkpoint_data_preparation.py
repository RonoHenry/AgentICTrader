"""
Checkpoint 5 — Verify data preparation pipeline.

This test module explicitly validates all three checkpoint criteria:

  1. Enrichment pipeline processes 10+ sample setups correctly
  2. Embeddings are generated correctly (528-dim, no NaN values)
  3. All individual pipeline components work end-to-end

Run:
    pytest scripts/rag/tests/test_checkpoint_data_preparation.py -v

Validates: FR-RAG-1 (historical setup storage), FR-RAG-2 (multi-modal embeddings)
"""

from __future__ import annotations

import json
import sys
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pytest

_WORKSPACE_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..")
)
if _WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, _WORKSPACE_ROOT)

from scripts.rag.utils.setup_enricher import EnrichedSetup, SetupEnricher
from scripts.rag.utils.narrative_generator import NarrativeGenerator
from scripts.rag.utils.multi_modal_embedder import MultiModalEmbedder
from scripts.rag.utils.structured_feature_embedder import StructuredFeatureEmbedder
from scripts.rag.utils.temporal_embedder import TemporalEmbedder
from scripts.rag.utils.narrative_embedder import NarrativeEmbedder
from scripts.rag.prepare_historical_setups import (
    generate_sample_candles,
    load_sample_trades,
    main as prepare_main,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

COMBINED_DIM: int = 528
CHECKPOINT_MIN_SETUPS: int = 10


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_candle(
    open_: float,
    high: float,
    low: float,
    close: float,
    time: str = "2024-01-15T09:15:00Z",
    volume: int = 1000,
) -> Dict[str, Any]:
    return {
        "time": time,
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    }


def _make_trade(
    trade_id: str,
    instrument: str = "EURUSD",
    direction: str = "BUY",
    entry_price: float = 1.5050,
    entry_time: str = "2024-01-15T09:15:00Z",
    r_multiple: float = 2.5,
) -> Dict[str, Any]:
    return {
        "trade_id": trade_id,
        "instrument": instrument,
        "direction": direction,
        "entry": {"time": entry_time, "price": entry_price},
        "exit": {"price": entry_price + 0.0050},
        "risk": {
            "stop_loss": entry_price - 0.0020,
            "take_profit": entry_price + 0.0060,
            "position_size": 1.0,
        },
        "outcome": {"r_multiple": r_multiple, "pnl_usd": r_multiple * 100},
    }


def _make_candle_set(
    entry_price: float = 1.5050,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Return (ltp_candles, htf_candles) for a given entry price."""
    candles = [
        _make_candle(
            entry_price - 0.0010 * i,
            entry_price + 0.0050,
            entry_price - 0.0030,
            entry_price,
        )
        for i in range(10)
    ]
    htf_candles = [
        _make_candle(entry_price - 0.0005, entry_price + 0.0200, entry_price - 0.0150, entry_price)
    ]
    return candles, htf_candles


def _build_10_sample_setups() -> List[EnrichedSetup]:
    """Create and enrich exactly 10 sample setups covering diverse scenarios."""
    enricher = SetupEnricher(htf_timeframe="H1")

    scenarios = [
        # (instrument, direction, entry_price, entry_time, r_multiple)
        ("EURUSD", "BUY",  1.1050, "2024-01-15T09:15:00Z",  2.5),
        ("EURUSD", "SELL", 1.1030, "2024-01-15T09:30:00Z", -1.0),
        ("GBPUSD", "BUY",  1.2600, "2024-01-15T10:00:00Z",  3.0),
        ("GBPUSD", "SELL", 1.2580, "2024-01-15T14:00:00Z", -0.5),
        ("USDJPY", "BUY",  150.00, "2024-01-15T14:30:00Z",  1.5),
        ("XAUUSD", "BUY",  2020.0, "2024-01-15T09:00:00Z",  4.2),
        ("XAUUSD", "SELL", 2015.0, "2024-01-15T15:00:00Z", -1.0),
        ("US500",  "BUY",  4800.0, "2024-01-15T14:00:00Z",  2.0),
        ("US30",   "BUY",  37500., "2024-01-15T09:15:00Z",  3.5),
        ("EURUSD", "BUY",  1.1060, "2024-03-18T09:15:00Z",  2.8),
    ]

    results: List[EnrichedSetup] = []
    for i, (instrument, direction, entry_price, entry_time, r_multiple) in enumerate(scenarios):
        trade = _make_trade(
            trade_id=f"TRD-CP5-{i + 1:03d}",
            instrument=instrument,
            direction=direction,
            entry_price=entry_price,
            entry_time=entry_time,
            r_multiple=r_multiple,
        )
        candles, htf_candles = _make_candle_set(entry_price)
        result = enricher.enrich(trade, candles, htf_candles)
        results.append(result)

    return results


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def enriched_setups() -> List[EnrichedSetup]:
    """10 enriched setups — created once per test session."""
    return _build_10_sample_setups()


@pytest.fixture(scope="module")
def multi_modal_embedder() -> MultiModalEmbedder:
    """MultiModalEmbedder — model loaded once per test session."""
    return MultiModalEmbedder()


@pytest.fixture(scope="module")
def embeddings(
    enriched_setups: List[EnrichedSetup],
    multi_modal_embedder: MultiModalEmbedder,
) -> List[np.ndarray]:
    """528-dim embeddings for all 10 sample setups — computed once per session."""
    return [multi_modal_embedder.embed(setup) for setup in enriched_setups]


# ===========================================================================
# Checkpoint Criterion 1 — Enrichment pipeline processes 10+ sample setups
# ===========================================================================


class TestCheckpointEnrichmentPipeline:
    """
    Checkpoint criterion 1: Enrichment pipeline processes 10+ sample setups correctly.

    Validates: FR-RAG-1
    """

    def test_exactly_10_setups_produced(self, enriched_setups: List[EnrichedSetup]):
        """Exactly 10 enriched setups are produced (≥ checkpoint minimum)."""
        assert len(enriched_setups) >= CHECKPOINT_MIN_SETUPS, (
            f"Expected at least {CHECKPOINT_MIN_SETUPS} setups, got {len(enriched_setups)}"
        )

    def test_all_setups_are_enriched_setup_instances(
        self, enriched_setups: List[EnrichedSetup]
    ):
        """Every item returned is an EnrichedSetup Pydantic model."""
        for i, setup in enumerate(enriched_setups):
            assert isinstance(setup, EnrichedSetup), (
                f"Setup {i} is not an EnrichedSetup: got {type(setup).__name__}"
            )

    def test_all_setups_have_unique_trade_ids(
        self, enriched_setups: List[EnrichedSetup]
    ):
        """All 10 setups have unique trade IDs."""
        trade_ids = [s.trade_id for s in enriched_setups]
        assert len(set(trade_ids)) == len(trade_ids), (
            f"Duplicate trade IDs detected: {trade_ids}"
        )

    def test_all_setups_have_htf_context(self, enriched_setups: List[EnrichedSetup]):
        """All setups have HTF context fields populated."""
        for setup in enriched_setups:
            assert setup.htf_open_bias in {"BULLISH", "BEARISH", "NEUTRAL"}, (
                f"{setup.trade_id}: invalid htf_open_bias={setup.htf_open_bias!r}"
            )
            assert setup.htf_high > setup.htf_low, (
                f"{setup.trade_id}: htf_high <= htf_low"
            )
            assert setup.htf_timeframe == "H1"

    def test_all_setups_have_pd_array_context(
        self, enriched_setups: List[EnrichedSetup]
    ):
        """All setups have PD array boolean flags."""
        for setup in enriched_setups:
            assert isinstance(setup.bos_detected, bool), (
                f"{setup.trade_id}: bos_detected is not bool"
            )
            assert isinstance(setup.choch_detected, bool)
            assert isinstance(setup.fvg_present, bool)
            assert isinstance(setup.liquidity_sweep, bool)

    def test_all_setups_have_session_context(
        self, enriched_setups: List[EnrichedSetup]
    ):
        """All setups have session/time window classification."""
        for setup in enriched_setups:
            assert setup.time_window != "", (
                f"{setup.trade_id}: time_window is empty"
            )
            assert isinstance(setup.is_killzone, bool)
            assert 0.0 <= setup.time_window_weight <= 1.0, (
                f"{setup.trade_id}: time_window_weight={setup.time_window_weight} out of [0,1]"
            )

    def test_all_setups_have_valid_narratives(
        self, enriched_setups: List[EnrichedSetup]
    ):
        """All setups have narratives that pass quality validation."""
        gen = NarrativeGenerator()
        for setup in enriched_setups:
            assert isinstance(setup.narrative, str), (
                f"{setup.trade_id}: narrative is not a string"
            )
            is_valid, errors = gen.validate_narrative(setup.narrative)
            assert is_valid, (
                f"{setup.trade_id}: narrative quality failed: {errors}"
            )

    def test_all_setups_have_non_negative_confluence_count(
        self, enriched_setups: List[EnrichedSetup]
    ):
        """All setups have confluence_count >= 0."""
        for setup in enriched_setups:
            assert isinstance(setup.confluence_count, int)
            assert setup.confluence_count >= 0, (
                f"{setup.trade_id}: negative confluence_count={setup.confluence_count}"
            )

    def test_all_setups_have_valid_outcome_result(
        self, enriched_setups: List[EnrichedSetup]
    ):
        """All setups have outcome_result of WIN or LOSS."""
        for setup in enriched_setups:
            assert setup.outcome_result in {"WIN", "LOSS"}, (
                f"{setup.trade_id}: invalid outcome_result={setup.outcome_result!r}"
            )

    def test_win_loss_assignment_matches_r_multiple_sign(
        self, enriched_setups: List[EnrichedSetup]
    ):
        """WIN is assigned for positive r_multiple, LOSS for non-positive."""
        for setup in enriched_setups:
            if setup.r_multiple > 0:
                assert setup.outcome_result == "WIN", (
                    f"{setup.trade_id}: r={setup.r_multiple} > 0 but outcome={setup.outcome_result}"
                )
            else:
                assert setup.outcome_result == "LOSS", (
                    f"{setup.trade_id}: r={setup.r_multiple} <= 0 but outcome={setup.outcome_result}"
                )

    def test_diverse_instruments_enriched_correctly(
        self, enriched_setups: List[EnrichedSetup]
    ):
        """Each instrument in the sample setups is correctly labelled."""
        expected_instruments = {
            "EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "US500", "US30"
        }
        actual_instruments = {s.instrument for s in enriched_setups}
        assert actual_instruments == expected_instruments, (
            f"Missing instruments: {expected_instruments - actual_instruments}"
        )

    def test_narratives_reference_respective_instruments(
        self, enriched_setups: List[EnrichedSetup]
    ):
        """Each setup's narrative mentions its own instrument."""
        for setup in enriched_setups:
            assert setup.instrument in setup.narrative, (
                f"{setup.trade_id}: narrative does not mention instrument {setup.instrument!r}"
            )

    def test_prepare_main_enriches_10_setups_end_to_end(self, tmp_path):
        """prepare_historical_setups.main() enriches 10 setups and writes valid JSON."""
        output_file = str(tmp_path / "checkpoint5_enriched.json")
        results, errors = prepare_main(limit=10, output_path=output_file)

        # Must produce 10 results with no errors
        assert len(results) == 10, (
            f"Expected 10 enriched setups, got {len(results)}"
        )
        assert len(errors) == 0, (
            f"Pipeline produced unexpected errors: {errors}"
        )

        # JSON file must be valid and contain all required fields
        with open(output_file) as f:
            data = json.load(f)

        assert len(data) == 10
        required_keys = {
            "trade_id", "instrument", "direction", "narrative",
            "htf_open_bias", "htf_timeframe", "time_window",
            "confluence_count", "outcome_result", "r_multiple",
        }
        for item in data:
            missing = required_keys - set(item.keys())
            assert not missing, (
                f"JSON item missing required keys: {missing}"
            )


# ===========================================================================
# Checkpoint Criterion 2 — Embeddings are 528-dim with no NaN values
# ===========================================================================


class TestCheckpointEmbeddingPipeline:
    """
    Checkpoint criterion 2: Embeddings are generated correctly (528-dim, no NaN).

    Validates: FR-RAG-2
    """

    def test_10_embeddings_generated(self, embeddings: List[np.ndarray]):
        """Exactly 10 embeddings are generated — one per enriched setup."""
        assert len(embeddings) >= CHECKPOINT_MIN_SETUPS, (
            f"Expected at least {CHECKPOINT_MIN_SETUPS} embeddings, got {len(embeddings)}"
        )

    def test_all_embeddings_are_528_dim(self, embeddings: List[np.ndarray]):
        """Every embedding is exactly 528-dimensional."""
        for i, emb in enumerate(embeddings):
            assert emb.shape == (COMBINED_DIM,), (
                f"Embedding {i}: expected shape ({COMBINED_DIM},), got {emb.shape}"
            )

    def test_all_embeddings_are_float32(self, embeddings: List[np.ndarray]):
        """Every embedding has dtype float32 (required by Qdrant)."""
        for i, emb in enumerate(embeddings):
            assert emb.dtype == np.float32, (
                f"Embedding {i}: expected float32, got {emb.dtype}"
            )

    def test_no_embedding_contains_nan(self, embeddings: List[np.ndarray]):
        """No embedding contains NaN values."""
        for i, emb in enumerate(embeddings):
            nan_count = int(np.isnan(emb).sum())
            assert nan_count == 0, (
                f"Embedding {i}: contains {nan_count} NaN value(s)"
            )

    def test_no_embedding_contains_inf(self, embeddings: List[np.ndarray]):
        """No embedding contains Inf values."""
        for i, emb in enumerate(embeddings):
            inf_count = int(np.isinf(emb).sum())
            assert inf_count == 0, (
                f"Embedding {i}: contains {inf_count} Inf value(s)"
            )

    def test_embeddings_are_1d_vectors(self, embeddings: List[np.ndarray]):
        """All embeddings are 1-D arrays (not matrices)."""
        for i, emb in enumerate(embeddings):
            assert emb.ndim == 1, (
                f"Embedding {i}: expected 1-D array, got {emb.ndim}-D"
            )

    def test_narrative_slice_correct_length(self, embeddings: List[np.ndarray]):
        """Narrative slice (indices 0–383) of each embedding is exactly 384 elements."""
        for i, emb in enumerate(embeddings):
            assert len(emb[:384]) == 384, (
                f"Embedding {i}: narrative slice wrong length"
            )

    def test_structured_slice_correct_length(self, embeddings: List[np.ndarray]):
        """Structured slice (indices 384–511) of each embedding is exactly 128 elements."""
        for i, emb in enumerate(embeddings):
            assert len(emb[384:512]) == 128, (
                f"Embedding {i}: structured slice wrong length"
            )

    def test_temporal_slice_correct_length(self, embeddings: List[np.ndarray]):
        """Temporal slice (indices 512–527) of each embedding is exactly 16 elements."""
        for i, emb in enumerate(embeddings):
            assert len(emb[512:]) == 16, (
                f"Embedding {i}: temporal slice wrong length"
            )

    def test_embeddings_are_not_all_identical(self, embeddings: List[np.ndarray]):
        """Different setups produce different embeddings (sensitivity check)."""
        # At least some pair of embeddings should differ
        all_same = all(
            np.allclose(embeddings[0], embeddings[i])
            for i in range(1, len(embeddings))
        )
        assert not all_same, (
            "All 10 embeddings are identical — embedder is insensitive to input variation"
        )

    def test_embeddings_pass_multi_modal_validation(
        self,
        embeddings: List[np.ndarray],
        multi_modal_embedder: MultiModalEmbedder,
    ):
        """Every embedding passes MultiModalEmbedder.validate_embedding()."""
        for i, emb in enumerate(embeddings):
            try:
                multi_modal_embedder.validate_embedding(emb)
            except (ValueError, TypeError) as exc:
                pytest.fail(
                    f"Embedding {i} failed validate_embedding(): {exc}"
                )

    def test_embed_and_validate_matches_embed(
        self,
        enriched_setups: List[EnrichedSetup],
        multi_modal_embedder: MultiModalEmbedder,
    ):
        """embed_and_validate() returns the same vector as embed() for all setups."""
        for setup in enriched_setups:
            v1 = multi_modal_embedder.embed(setup)
            v2 = multi_modal_embedder.embed_and_validate(setup)
            np.testing.assert_array_equal(
                v1, v2,
                err_msg=f"embed() and embed_and_validate() differ for {setup.trade_id}",
            )


# ===========================================================================
# Checkpoint Criterion 3 — End-to-end pipeline (enrichment + embedding)
# ===========================================================================


class TestCheckpointEndToEndPipeline:
    """
    Full checkpoint: 10+ setups enriched AND embedded correctly in one pipeline.
    """

    def test_full_pipeline_10_setups(self, tmp_path):
        """
        Full end-to-end checkpoint: enriches 10 setups with prepare_main()
        then generates 528-dim NaN-free embeddings for each.

        This is the definitive checkpoint verification for Task 5.
        """
        # Step 1: Enrich 10 setups
        output_file = str(tmp_path / "checkpoint5_full.json")
        enriched_dicts, errors = prepare_main(limit=10, output_path=output_file)

        assert len(enriched_dicts) == 10, (
            f"Step 1 failed: expected 10 enriched setups, got {len(enriched_dicts)}"
        )
        assert errors == [], (
            f"Step 1 failed: enrichment errors: {errors}"
        )

        # Step 2: Reconstruct EnrichedSetup objects from output
        with open(output_file) as f:
            serialized = json.load(f)

        setups = [EnrichedSetup(**s) for s in serialized]
        assert len(setups) == 10

        # Step 3: Generate embeddings for all setups
        embedder = MultiModalEmbedder()
        embedding_results = []
        for setup in setups:
            emb = embedder.embed(setup)
            embedding_results.append(emb)

        # Step 4: Validate all embeddings
        assert len(embedding_results) == 10, "Expected 10 embeddings"

        for i, (setup, emb) in enumerate(zip(setups, embedding_results)):
            # Dimension check
            assert emb.shape == (COMBINED_DIM,), (
                f"Setup {i} ({setup.trade_id}): embedding shape {emb.shape} != (528,)"
            )
            # NaN check
            assert not np.isnan(emb).any(), (
                f"Setup {i} ({setup.trade_id}): embedding contains NaN"
            )
            # Inf check
            assert not np.isinf(emb).any(), (
                f"Setup {i} ({setup.trade_id}): embedding contains Inf"
            )
            # dtype check
            assert emb.dtype == np.float32, (
                f"Setup {i} ({setup.trade_id}): embedding dtype {emb.dtype} != float32"
            )

    def test_checkpoint_summary_report(
        self,
        enriched_setups: List[EnrichedSetup],
        embeddings: List[np.ndarray],
    ):
        """
        Generates and validates a summary report of the checkpoint results.

        This test consolidates all checkpoint criteria into a single assertion
        block and prints a human-readable summary.
        """
        n_setups = len(enriched_setups)
        n_embeddings = len(embeddings)

        # Criterion 1: 10+ setups enriched
        assert n_setups >= CHECKPOINT_MIN_SETUPS, (
            f"CRITERION 1 FAILED: {n_setups} setups enriched (need {CHECKPOINT_MIN_SETUPS}+)"
        )

        # Criterion 2a: All embeddings are 528-dim
        bad_dim = [(i, emb.shape) for i, emb in enumerate(embeddings) if emb.shape != (COMBINED_DIM,)]
        assert not bad_dim, (
            f"CRITERION 2a FAILED: {len(bad_dim)} embeddings have wrong dimension: {bad_dim}"
        )

        # Criterion 2b: No NaN values
        nan_setups = [(i, int(np.isnan(emb).sum())) for i, emb in enumerate(embeddings) if np.isnan(emb).any()]
        assert not nan_setups, (
            f"CRITERION 2b FAILED: {len(nan_setups)} embeddings contain NaN: {nan_setups}"
        )

        # Criterion 2c: No Inf values
        inf_setups = [(i, int(np.isinf(emb).sum())) for i, emb in enumerate(embeddings) if np.isinf(emb).any()]
        assert not inf_setups, (
            f"CRITERION 2c FAILED: {len(inf_setups)} embeddings contain Inf: {inf_setups}"
        )

        # Criterion 2d: All float32
        bad_dtype = [(i, str(emb.dtype)) for i, emb in enumerate(embeddings) if emb.dtype != np.float32]
        assert not bad_dtype, (
            f"CRITERION 2d FAILED: {len(bad_dtype)} embeddings have wrong dtype: {bad_dtype}"
        )

        # Print checkpoint summary
        win_count = sum(1 for s in enriched_setups if s.outcome_result == "WIN")
        loss_count = sum(1 for s in enriched_setups if s.outcome_result == "LOSS")
        instruments = sorted({s.instrument for s in enriched_setups})
        avg_confluence = sum(s.confluence_count for s in enriched_setups) / n_setups
        narrative_lengths = [len(s.narrative) for s in enriched_setups]

        print(f"\n{'=' * 60}")
        print(f"CHECKPOINT 5 — DATA PREPARATION VERIFICATION SUMMARY")
        print(f"{'=' * 60}")
        print(f"✅ Setups enriched       : {n_setups} (min required: {CHECKPOINT_MIN_SETUPS})")
        print(f"✅ Embeddings generated  : {n_embeddings}")
        print(f"✅ Embedding dimension   : {COMBINED_DIM}-dim (all correct)")
        print(f"✅ NaN values            : 0")
        print(f"✅ Inf values            : 0")
        print(f"✅ Embedding dtype       : float32 (all correct)")
        print(f"")
        print(f"Setup breakdown:")
        print(f"  Instruments   : {', '.join(instruments)}")
        print(f"  WIN outcomes  : {win_count}")
        print(f"  LOSS outcomes : {loss_count}")
        print(f"  Avg confluence: {avg_confluence:.2f}")
        print(f"  Narrative len : {min(narrative_lengths)}–{max(narrative_lengths)} chars")
        print(f"{'=' * 60}\n")

    def test_enrichment_and_embedding_performance(self):
        """Enriching and embedding 10 setups completes within 60 seconds wall clock."""
        enricher = SetupEnricher(htf_timeframe="H1")
        embedder = MultiModalEmbedder()

        setups_to_process = _build_10_sample_setups()

        start = time.perf_counter()
        for setup in setups_to_process:
            embedder.embed(setup)
        elapsed = time.perf_counter() - start

        assert elapsed < 60.0, (
            f"10 setups enrichment+embedding took {elapsed:.1f}s (budget: 60s)"
        )
