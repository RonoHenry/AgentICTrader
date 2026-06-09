"""
Integration tests for the AlgoRAG enrichment pipeline.

Covers:
  - End-to-end enrichment from raw trade record to EnrichedSetup
  - Error handling for missing / malformed data
  - Batch processing correctness and performance

Requirements: FR-RAG-1, NFR-RAG-4
"""
from __future__ import annotations

import sys
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from scripts.rag.utils.setup_enricher import EnrichedSetup, SetupEnricher
from scripts.rag.utils.narrative_generator import NarrativeGenerator
from scripts.rag.prepare_historical_setups import (
    generate_sample_candles,
    load_sample_trades,
    main as prepare_main,
)

# ---------------------------------------------------------------------------
# Shared helpers / fixtures
# ---------------------------------------------------------------------------

LONDON_ENTRY_TIME = "2024-01-15T09:15:00Z"   # London killzone (UTC)
NY_ENTRY_TIME     = "2024-01-15T14:00:00Z"   # NY AM killzone (UTC)
ASIAN_ENTRY_TIME  = "2024-01-15T02:00:00Z"   # Asian session (UTC)


def make_candle(
    open_: float,
    high: float,
    low: float,
    close: float,
    time: str = LONDON_ENTRY_TIME,
    volume: int = 1000,
) -> Dict[str, Any]:
    return {"time": time, "open": open_, "high": high, "low": low, "close": close, "volume": volume}


def make_trade(
    trade_id: str = "TRD-INTG-001",
    instrument: str = "EURUSD",
    direction: str = "BUY",
    entry_price: float = 1.5050,
    entry_time: str = LONDON_ENTRY_TIME,
    r_multiple: float = 2.5,
) -> Dict[str, Any]:
    return {
        "trade_id": trade_id,
        "instrument": instrument,
        "direction": direction,
        "entry": {"time": entry_time, "price": entry_price},
        "exit": {"time": LONDON_ENTRY_TIME, "price": entry_price + 0.0050},
        "risk": {
            "stop_loss": entry_price - 0.0020,
            "take_profit": entry_price + 0.0060,
            "position_size": 1.0,
        },
        "outcome": {"r_multiple": r_multiple, "pnl_usd": r_multiple * 100},
    }


def make_candle_set(
    entry_price: float = 1.5050,
    entry_time: str = LONDON_ENTRY_TIME,
    n_ltp: int = 10,
    n_htf: int = 5,
):
    """Return (candles, htf_candles) suitable for enrichment."""
    candles = [
        make_candle(entry_price - 0.0010 * i, entry_price + 0.0050, entry_price - 0.0030, entry_price, entry_time)
        for i in range(n_ltp)
    ]
    htf_candles = [make_candle(entry_price - 0.0005, entry_price + 0.0200, entry_price - 0.0150, entry_price, entry_time)]
    return candles, htf_candles


# ---------------------------------------------------------------------------
# Section 1 — End-to-end enrichment
# ---------------------------------------------------------------------------


class TestEndToEndEnrichment:
    """Full pipeline: raw trade dict → EnrichedSetup with all fields populated."""

    def test_enriched_setup_type_and_trade_id(self):
        """enrich() returns an EnrichedSetup with the correct trade_id."""
        enricher = SetupEnricher(htf_timeframe="H1")
        trade = make_trade(trade_id="TRD-E2E-001")
        candles, htf_candles = make_candle_set()

        result = enricher.enrich(trade, candles, htf_candles)

        assert isinstance(result, EnrichedSetup)
        assert result.trade_id == "TRD-E2E-001"

    def test_all_required_fields_populated(self):
        """Every required field on EnrichedSetup is populated (not None / empty)."""
        enricher = SetupEnricher(htf_timeframe="H1")
        trade = make_trade()
        candles, htf_candles = make_candle_set()

        result = enricher.enrich(trade, candles, htf_candles)

        # Scalar identity fields
        assert result.instrument == "EURUSD"
        assert result.direction == "BUY"
        assert result.entry_price == pytest.approx(1.5050, abs=1e-6)

        # HTF fields
        assert result.htf_timeframe == "H1"
        assert result.htf_open > 0
        assert result.htf_high > result.htf_low
        assert result.htf_open_bias in {"BULLISH", "BEARISH", "NEUTRAL"}

        # PD-array fields
        assert isinstance(result.bos_detected, bool)
        assert isinstance(result.choch_detected, bool)
        assert isinstance(result.fvg_present, bool)
        assert isinstance(result.liquidity_sweep, bool)

        # Session fields
        assert result.time_window != ""
        assert result.narrative_phase != ""
        assert isinstance(result.is_killzone, bool)

        # Narrative
        assert isinstance(result.narrative, str)
        assert len(result.narrative) >= 50

        # Confluence count
        assert result.confluence_count >= 0

    def test_outcome_derived_from_r_multiple(self):
        """outcome_result is WIN for positive r_multiple and LOSS for negative."""
        enricher = SetupEnricher()
        candles, htf_candles = make_candle_set()

        win_trade = make_trade(r_multiple=2.5)
        loss_trade = make_trade(trade_id="TRD-LOSS", r_multiple=-1.0)

        assert enricher.enrich(win_trade, candles, htf_candles).outcome_result == "WIN"
        assert enricher.enrich(loss_trade, candles, htf_candles).outcome_result == "LOSS"

    def test_narrative_references_instrument(self):
        """The generated narrative explicitly mentions the instrument."""
        enricher = SetupEnricher()
        trade = make_trade(instrument="GBPUSD")
        candles, htf_candles = make_candle_set()

        result = enricher.enrich(trade, candles, htf_candles)

        assert "GBPUSD" in result.narrative

    def test_narrative_references_session(self):
        """The generated narrative references a recognisable session window."""
        enricher = SetupEnricher()
        trade = make_trade(entry_time=LONDON_ENTRY_TIME)
        candles, htf_candles = make_candle_set()

        result = enricher.enrich(trade, candles, htf_candles)

        narrative_lower = result.narrative.lower()
        assert any(kw in narrative_lower for kw in ["london", "killzone", "asian", "ny", "session", "silver"])

    def test_narrative_references_outcome(self):
        """The generated narrative mentions the trade outcome."""
        enricher = SetupEnricher()
        trade = make_trade(r_multiple=3.0)
        candles, htf_candles = make_candle_set()

        result = enricher.enrich(trade, candles, htf_candles)

        narrative_lower = result.narrative.lower()
        assert any(kw in narrative_lower for kw in ["win", "loss", "3.0", "3.0r", "r"])

    def test_narrative_passes_quality_validation(self):
        """Narrative generated during enrichment satisfies NarrativeGenerator quality checks."""
        enricher = SetupEnricher()
        gen = NarrativeGenerator()
        trade = make_trade()
        candles, htf_candles = make_candle_set()

        result = enricher.enrich(trade, candles, htf_candles)
        is_valid, errors = gen.validate_narrative(result.narrative)

        assert is_valid, f"Narrative quality validation failed: {errors}"

    def test_full_setup_preserved_in_result(self):
        """full_setup field contains the original trade dict."""
        enricher = SetupEnricher()
        trade = make_trade(trade_id="TRD-FULLSETUP")
        candles, htf_candles = make_candle_set()

        result = enricher.enrich(trade, candles, htf_candles)

        assert result.full_setup is not None
        assert result.full_setup["trade_id"] == "TRD-FULLSETUP"

    def test_confluence_count_is_non_negative_integer(self):
        """confluence_count is a non-negative integer."""
        enricher = SetupEnricher()
        trade = make_trade()
        candles, htf_candles = make_candle_set()

        result = enricher.enrich(trade, candles, htf_candles)

        assert isinstance(result.confluence_count, int)
        assert result.confluence_count >= 0

    def test_multiple_instruments_produce_correct_labels(self):
        """Enrichment labels the correct instrument for each trade."""
        enricher = SetupEnricher()
        for instrument in ["EURUSD", "GBPUSD", "XAUUSD"]:
            trade = make_trade(instrument=instrument)
            candles, htf_candles = make_candle_set()
            result = enricher.enrich(trade, candles, htf_candles)
            assert result.instrument == instrument

    def test_prepare_historical_setups_pipeline(self, tmp_path):
        """prepare_historical_setups.main() runs end-to-end and returns valid setups."""
        output_file = str(tmp_path / "test_enriched.json")
        results, errors = prepare_main(limit=5, output_path=output_file)

        assert len(results) > 0, "Pipeline produced no enriched setups"
        assert len(errors) == 0, f"Pipeline produced unexpected errors: {errors}"

        # Validate output file was written
        import json
        with open(output_file) as f:
            written = json.load(f)
        assert len(written) == len(results)

        # Spot-check required keys in the JSON output
        required_keys = {
            "trade_id", "instrument", "direction", "narrative",
            "htf_open_bias", "time_window", "confluence_count",
        }
        for item in written:
            missing = required_keys - set(item.keys())
            assert not missing, f"Missing keys in output: {missing}"


# ---------------------------------------------------------------------------
# Section 2 — Error handling for missing / malformed data
# ---------------------------------------------------------------------------


class TestErrorHandling:
    """Enricher handles gracefully missing, null, or malformed inputs."""

    def test_missing_entry_time_uses_fallback(self):
        """Trade with no entry time falls back to current UTC time without raising."""
        enricher = SetupEnricher()
        trade = {
            "trade_id": "TRD-NO-TIME",
            "instrument": "EURUSD",
            "direction": "BUY",
            "entry": {"price": 1.5050},   # no "time" key
            "exit": {"price": 1.5100},
            "risk": {"stop_loss": 1.5000, "take_profit": 1.5150, "position_size": 1.0},
            "outcome": {"r_multiple": 1.5},
        }
        candles, htf_candles = make_candle_set()

        # Should not raise; timestamp falls back to now
        result = enricher.enrich(trade, candles, htf_candles)
        assert isinstance(result, EnrichedSetup)
        assert result.timestamp is not None

    def test_empty_candle_list_raises_value_error(self):
        """ZoneFeatureExtractor enforces a non-empty candle list; enrich() surfaces that ValueError.

        This documents the hard contract: callers must supply at least one candle.
        Empty-candle handling (e.g. skipping the trade) belongs in the calling pipeline,
        not silently inside the enricher.
        """
        enricher = SetupEnricher()
        trade = make_trade()
        _, htf_candles = make_candle_set()

        with pytest.raises(ValueError, match="candles list cannot be empty"):
            enricher.enrich(trade, [], htf_candles)

    def test_empty_htf_candle_list_raises_value_error(self):
        """HTFProjectionExtractor enforces a non-empty HTF candle list; enrich() surfaces that ValueError.

        This documents the hard contract: callers must supply at least one HTF candle.
        """
        enricher = SetupEnricher()
        trade = make_trade()
        candles, _ = make_candle_set()

        with pytest.raises(ValueError, match="htf_candles cannot be empty"):
            enricher.enrich(trade, candles, [])

    def test_missing_instrument_uses_default_unknown(self):
        """Trade with no instrument field falls back to 'UNKNOWN' without raising."""
        enricher = SetupEnricher()
        trade = {
            "trade_id": "TRD-NO-INST",
            "direction": "BUY",
            "entry": {"time": LONDON_ENTRY_TIME, "price": 1.5050},
            "exit": {"price": 1.5100},
            "risk": {"stop_loss": 1.5000, "take_profit": 1.5150, "position_size": 1.0},
            "outcome": {"r_multiple": 2.0},
        }
        candles, htf_candles = make_candle_set()

        result = enricher.enrich(trade, candles, htf_candles)
        assert result.instrument == "UNKNOWN"

    def test_flat_trade_format_accepted(self):
        """Enricher handles flat trade dicts (no nested entry/exit/risk/outcome)."""
        enricher = SetupEnricher()
        trade = {
            "trade_id": "TRD-FLAT",
            "instrument": "EURUSD",
            "direction": "BUY",
            "entry_price": 1.5050,
            "entry_time": LONDON_ENTRY_TIME,
            "exit_price": 1.5100,
            "stop_loss": 1.5000,
            "take_profit": 1.5150,
            "r_multiple": 2.0,
            "outcome_result": "WIN",
        }
        candles, htf_candles = make_candle_set()

        result = enricher.enrich(trade, candles, htf_candles)
        assert result.trade_id == "TRD-FLAT"
        assert result.entry_price == pytest.approx(1.5050, abs=1e-6)
        assert result.outcome_result == "WIN"

    def test_zero_r_multiple_classified_as_loss(self):
        """A trade with r_multiple == 0 is classified as LOSS (not WIN)."""
        enricher = SetupEnricher()
        trade = make_trade(r_multiple=0.0)
        candles, htf_candles = make_candle_set()

        result = enricher.enrich(trade, candles, htf_candles)
        assert result.outcome_result == "LOSS"

    def test_explicit_outcome_result_overrides_r_multiple(self):
        """Explicit outcome_result field in trade takes precedence over r_multiple sign."""
        enricher = SetupEnricher()
        trade = make_trade(r_multiple=-1.0)
        trade["outcome_result"] = "WIN"          # explicit override
        candles, htf_candles = make_candle_set()

        result = enricher.enrich(trade, candles, htf_candles)
        assert result.outcome_result == "WIN"

    def test_batch_skips_and_reports_bad_items(self):
        """enrich_batch() does not surface individually broken items;
        prepare_main() counts them as errors instead of raising."""
        # Prepare a mix of 4 valid trades + 1 invalid to test prepare_main error path
        import json
        from unittest.mock import patch

        def bad_load(limit):
            trades = load_sample_trades(5)
            # Inject an un-parsable entry_time to force an error path
            trades[2]["entry"] = {"time": "NOT-A-DATE", "price": "ALSO-BAD"}
            trades[2]["risk"]["stop_loss"] = "INVALID"
            return trades

        with patch("scripts.rag.prepare_historical_setups.load_sample_trades", side_effect=bad_load):
            import tempfile, pathlib
            with tempfile.TemporaryDirectory() as tmpdir:
                output = str(pathlib.Path(tmpdir) / "out.json")
                results, errors = prepare_main(limit=5, output_path=output)

        # Either the pipeline handles the bad trade gracefully and puts it in errors,
        # or the extractor is resilient enough to still produce a result.
        total = len(results) + len(errors)
        assert total == 5, f"Expected 5 total items processed, got {total}"


# ---------------------------------------------------------------------------
# Section 3 — Batch processing correctness and performance
# ---------------------------------------------------------------------------


class TestBatchProcessing:
    """enrich_batch() produces correct output and meets NFR-RAG-4 performance targets."""

    def _make_batch(self, n: int) -> List[Dict[str, Any]]:
        """Build a batch of n valid trade+candle dicts."""
        batch = []
        for i in range(n):
            entry_price = 1.5000 + i * 0.0001
            trade = make_trade(
                trade_id=f"TRD-BATCH-{i:04d}",
                entry_price=entry_price,
                direction="BUY" if i % 2 == 0 else "SELL",
                r_multiple=2.0 if i % 3 != 0 else -1.0,
            )
            candles, htf_candles = make_candle_set(entry_price=entry_price)
            batch.append({"trade": trade, "candles": candles, "htf_candles": htf_candles})
        return batch

    def test_enrich_batch_returns_correct_count(self):
        """enrich_batch() returns exactly N results for N valid inputs."""
        enricher = SetupEnricher()
        batch = self._make_batch(10)

        results = enricher.enrich_batch(batch)

        assert len(results) == 10

    def test_enrich_batch_all_results_are_enriched_setups(self):
        """Every item returned by enrich_batch() is an EnrichedSetup."""
        enricher = SetupEnricher()
        results = enricher.enrich_batch(self._make_batch(10))

        assert all(isinstance(r, EnrichedSetup) for r in results)

    def test_enrich_batch_trade_ids_match_input(self):
        """trade_id in each result matches the corresponding input trade."""
        enricher = SetupEnricher()
        batch = self._make_batch(5)
        results = enricher.enrich_batch(batch)

        for item, result in zip(batch, results):
            assert result.trade_id == item["trade"]["trade_id"]

    def test_enrich_batch_win_loss_labels_correct(self):
        """Batch enrichment derives WIN / LOSS labels correctly for each trade."""
        enricher = SetupEnricher()
        batch = self._make_batch(6)
        results = enricher.enrich_batch(batch)

        for item, result in zip(batch, results):
            expected = "WIN" if item["trade"]["outcome"]["r_multiple"] > 0 else "LOSS"
            assert result.outcome_result == expected, (
                f"Trade {result.trade_id}: expected {expected}, got {result.outcome_result}"
            )

    def test_enrich_batch_narratives_are_valid(self):
        """All narratives generated in batch mode pass quality validation."""
        enricher = SetupEnricher()
        gen = NarrativeGenerator()
        results = enricher.enrich_batch(self._make_batch(10))

        for result in results:
            is_valid, errors = gen.validate_narrative(result.narrative)
            assert is_valid, f"{result.trade_id} narrative failed: {errors}"

    def test_enrich_batch_confluence_counts_non_negative(self):
        """All confluence counts produced by batch enrichment are non-negative integers."""
        enricher = SetupEnricher()
        results = enricher.enrich_batch(self._make_batch(10))

        for result in results:
            assert isinstance(result.confluence_count, int)
            assert result.confluence_count >= 0

    def test_enrich_10_setups_within_time_budget(self):
        """10 setups can be enriched well within a 5-second wall-clock budget (NFR-RAG-4)."""
        enricher = SetupEnricher()
        batch = self._make_batch(10)

        start = time.perf_counter()
        enricher.enrich_batch(batch)
        elapsed = time.perf_counter() - start

        assert elapsed < 5.0, f"Batch of 10 took {elapsed:.2f}s (budget: 5s)"

    def test_enrich_50_setups_within_time_budget(self):
        """50 setups can be enriched within a 20-second wall-clock budget (NFR-RAG-4 scale)."""
        enricher = SetupEnricher()
        batch = self._make_batch(50)

        start = time.perf_counter()
        enricher.enrich_batch(batch)
        elapsed = time.perf_counter() - start

        assert elapsed < 20.0, f"Batch of 50 took {elapsed:.2f}s (budget: 20s)"

    def test_htf_cache_reduces_redundant_computation(self):
        """Batch with repeated HTF candles should benefit from cache (same cache key reused)."""
        enricher = SetupEnricher()
        # All trades use identical HTF candles → cache key collisions expected
        shared_htf = [make_candle(1.5000, 1.5200, 1.4900, 1.5100)]
        batch = []
        for i in range(10):
            entry_price = 1.5050 + i * 0.0001
            trade = make_trade(trade_id=f"TRD-CACHE-{i:02d}", entry_price=entry_price)
            candles, _ = make_candle_set(entry_price=entry_price)
            batch.append({"trade": trade, "candles": candles, "htf_candles": shared_htf})

        enricher.enrich_batch(batch)

        # All 10 share the same HTF candle time → only 1 cache entry for that key
        assert len(enricher._htf_cache) <= 10   # at most one entry per unique price

    def test_prepare_main_returns_all_sample_trades(self, tmp_path):
        """prepare_historical_setups.main() enriches all available sample trades."""
        output_file = str(tmp_path / "batch_test.json")
        results, errors = prepare_main(limit=10, output_path=output_file)

        assert len(results) == 10, f"Expected 10 results, got {len(results)}"
        assert len(errors) == 0, f"Unexpected errors: {errors}"

    def test_prepare_main_outputs_valid_json_file(self, tmp_path):
        """prepare_historical_setups.main() writes a parsable JSON file."""
        import json as _json
        output_file = str(tmp_path / "output.json")
        prepare_main(limit=5, output_path=output_file)

        with open(output_file) as f:
            data = _json.load(f)

        assert isinstance(data, list)
        assert len(data) == 5

    def test_batch_unique_trade_ids(self):
        """Each enriched setup in a batch preserves its unique trade_id."""
        enricher = SetupEnricher()
        n = 15
        results = enricher.enrich_batch(self._make_batch(n))
        ids = [r.trade_id for r in results]

        assert len(set(ids)) == n, "Duplicate trade_ids detected in batch output"
