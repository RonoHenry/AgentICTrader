"""
Test: load_initial_data.py

TDD Phase: RED — Write failing tests for historical data loading script.

Tests for loading 500+ historical setups from trade journal, enriching,
embedding, and ingesting to Qdrant with data quality reporting.

Requirements: FR-RAG-1
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Ensure workspace root is importable
_WORKSPACE_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..")
)
if _WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, _WORKSPACE_ROOT)

from scripts.rag.load_initial_data import (
    DataLoadingError,
    DataQualityReport,
    InitialDataLoader,
    LoadingProgress,
)
from scripts.rag.utils.setup_enricher import EnrichedSetup
from services.algorag.ingestion_service import BatchIngestionResult


class TestInitialDataLoader(IsolatedAsyncioTestCase):
    """Test the InitialDataLoader class."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_db = MagicMock()
        self.mock_trade_collection = MagicMock()
        self.mock_db.trade_journal = self.mock_trade_collection

        self.mock_enricher = MagicMock()
        self.mock_embedding_gen = MagicMock()
        self.mock_ingestion_service = MagicMock()
        self.mock_qdrant_wrapper = MagicMock()

        self.loader = InitialDataLoader(
            db=self.mock_db,
            enricher=self.mock_enricher,
            embedding_generator=self.mock_embedding_gen,
            ingestion_service=self.mock_ingestion_service,
            qdrant_wrapper=self.mock_qdrant_wrapper,
        )

        # Sample trade data
        self.sample_trade = {
            "trade_id": "TRD-001",
            "instrument": "EURUSD", 
            "direction": "BUY",
            "entry": {
                "time": "2024-01-15T09:15:00Z",
                "price": 1.0850,
            },
            "exit": {
                "time": "2024-01-15T12:30:00Z",
                "price": 1.0895,
            },
            "risk": {
                "stop_loss": 1.0800,
                "take_profit": 1.0950,
            },
            "outcome": {
                "r_multiple": 2.5,
            },
            "outcome_result": "WIN",
        }

    async def test_load_historical_setups_minimum_500(self):
        """RED: Test loading minimum 500 setups from trade journal."""
        # Mock MongoDB find returns 500+ trades
        trades = [self.sample_trade.copy() for _ in range(520)]
        for i, trade in enumerate(trades):
            trade["trade_id"] = f"TRD-{i:03d}"

        self.mock_trade_collection.find.return_value.to_list = AsyncMock(
            return_value=trades
        )

        result = await self.loader.load_historical_setups()
        
        # Should load all 520 trades
        assert len(result) >= 500, f"Should load at least 500 setups, got {len(result)}"
        assert len(result) == 520, f"Should load all 520 trades, got {len(result)}"
        
        # Should call MongoDB with proper filter
        self.mock_trade_collection.find.assert_called_once()
        call_args = self.mock_trade_collection.find.call_args[0]
        assert call_args[0] == {}  # No filter - load all historical trades

    async def test_enrich_setups_batch_processing(self):
        """RED: Test enrichment of historical setups using existing pipeline."""
        trades = [self.sample_trade.copy() for _ in range(5)]
        
        # Mock enricher to return enriched setups
        mock_enriched = EnrichedSetup(
            trade_id="TRD-001",
            timestamp=datetime.now(timezone.utc),
            instrument="EURUSD",
            direction="BUY",
            entry_price=1.0850,
            exit_price=1.0895,
            stop_loss=1.0800,
            take_profit=1.0950,
            r_multiple=2.5,
            outcome_result="WIN",
            htf_timeframe="H1",
            htf_open=1.0840,
            htf_high=1.0900,
            htf_low=1.0820,
            htf_open_bias="BULLISH",
            htf_high_proximity_pct=0.25,
            htf_low_proximity_pct=0.75,
            htf_body_pct=0.40,
            htf_close_position=0.60,
            bos_detected=True,
            choch_detected=False,
            fvg_present=True,
            liquidity_sweep=False,
            swing_high_distance=15.0,
            swing_low_distance=8.0,
            htf_trend_bias="BULLISH",
            time_window="LONDON_KILLZONE",
            narrative_phase="MANIPULATION",
            time_window_weight=0.8,
            is_killzone=True,
            narrative="Price swept Asian low before rejecting from premium zone",
            confluence_count=5,
        )
        
        self.mock_enricher.enrich.return_value = mock_enriched

        # Mock candle data fetching
        with patch('scripts.rag.load_initial_data.fetch_candle_data') as mock_fetch:
            mock_fetch.return_value = ([], [])  # Empty candles for test
            
            result = await self.loader.enrich_setups(trades)
        
        assert len(result) == 5, f"Should enrich all 5 trades, got {len(result)}"
        
        # Should call enricher for each trade
        assert self.mock_enricher.enrich.call_count == 5

    async def test_generate_embeddings_batch_processing(self):
        """RED: Test embedding generation for enriched setups."""
        # Create mock enriched setups
        enriched_setups = []
        for i in range(3):
            setup = EnrichedSetup(
                trade_id=f"TRD-{i:03d}",
                timestamp=datetime.now(timezone.utc),
                instrument="EURUSD",
                direction="BUY",
                entry_price=1.0850,
                exit_price=1.0895,
                stop_loss=1.0800,
                take_profit=1.0950,
                r_multiple=2.5,
                outcome_result="WIN",
                htf_timeframe="H1",
                htf_open=1.0840,
                htf_high=1.0900,
                htf_low=1.0820,
                htf_open_bias="BULLISH",
                htf_high_proximity_pct=0.25,
                htf_low_proximity_pct=0.75,
                htf_body_pct=0.40,
                htf_close_position=0.60,
                bos_detected=True,
                choch_detected=False,
                fvg_present=True,
                liquidity_sweep=False,
                swing_high_distance=15.0,
                swing_low_distance=8.0,
                htf_trend_bias="BULLISH",
                time_window="LONDON_KILLZONE",
                narrative_phase="MANIPULATION",
                time_window_weight=0.8,
                is_killzone=True,
                narrative="Price swept Asian low before rejecting from premium zone",
                confluence_count=5,
            )
            enriched_setups.append(setup)

        # Mock embedding generator to return 528-dim vectors
        self.mock_embedding_gen.generate_embedding.return_value = [0.1] * 528

        result = await self.loader.generate_embeddings(enriched_setups)
        
        assert len(result) == 3, f"Should generate embeddings for all 3 setups, got {len(result)}"
        
        # Check that each result has setup and embedding
        for setup_emb in result:
            assert "setup" in setup_emb
            assert "embedding" in setup_emb
            assert len(setup_emb["embedding"]) == 528, "Embedding should be 528-dim"
        
        # Should call embedding generator for each setup
        assert self.mock_embedding_gen.generate_embedding.call_count == 3

    async def test_ingest_to_qdrant_batch_processing(self):
        """RED: Test ingestion of setups with embeddings to Qdrant."""
        # Mock setup-embedding pairs
        setup_embeddings = []
        for i in range(100):
            setup_embeddings.append({
                "setup": {
                    "trade_id": f"TRD-{i:03d}",
                    "timestamp": "2024-01-15T09:15:00Z",
                    "instrument": "EURUSD",
                    "outcome_result": "WIN",
                    "r_multiple": 2.5,
                },
                "embedding": [0.1] * 528,
            })

        # Mock successful ingestion
        mock_result = BatchIngestionResult(
            total=100,
            successful=95,
            failed=5,
            skipped=0,
            ingested_ids=[f"uuid-{i}" for i in range(95)],
            errors=[("TRD-095", "Connection error"), ("TRD-096", "Invalid data")],
        )
        self.mock_ingestion_service.ingest_batch.return_value = mock_result

        result = await self.loader.ingest_to_qdrant(setup_embeddings)
        
        assert result.successful >= 90, f"Should successfully ingest at least 90%, got {result.successful}/100"
        assert result.failed == 5, f"Should track failures, got {result.failed}"
        
        # Should call ingestion service with correct data
        self.mock_ingestion_service.ingest_batch.assert_called_once()
        call_args = self.mock_ingestion_service.ingest_batch.call_args[0][0]
        assert len(call_args) == 100, "Should pass all 100 setup-embedding pairs"

    async def test_generate_data_quality_report(self):
        """RED: Test generation of data quality report."""
        # Mock ingestion result with some failures
        ingestion_result = BatchIngestionResult(
            total=500,
            successful=485,
            failed=15,
            skipped=0,
            ingested_ids=[f"uuid-{i}" for i in range(485)],
            errors=[
                ("TRD-486", "Invalid embedding dimension"),
                ("TRD-487", "Connection timeout"),
            ],
        )

        # Mock enriched setups data
        enriched_setups = []
        for i in range(500):
            setup = {
                "trade_id": f"TRD-{i:03d}",
                "instrument": "EURUSD" if i % 2 == 0 else "GBPUSD",
                "outcome_result": "WIN" if i % 3 == 0 else "LOSS",
                "r_multiple": 2.5 if i % 3 == 0 else -1.0,
                "time_window": "LONDON_KILLZONE" if i % 4 == 0 else "NY_KILLZONE",
                "confluence_count": 5 if i % 5 == 0 else 3,
            }
            enriched_setups.append(setup)

        report = await self.loader.generate_data_quality_report(
            enriched_setups, ingestion_result
        )
        
        assert isinstance(report, DataQualityReport)
        assert report.total_setups == 500
        assert report.successfully_ingested == 485
        assert report.failed_ingestion == 15
        assert report.error_rate_pct < 5.0, f"Error rate should be < 5%, got {report.error_rate_pct}%"
        
        # Check instrument distribution
        assert "EURUSD" in report.instrument_distribution
        assert "GBPUSD" in report.instrument_distribution
        
        # Check outcome distribution
        assert "WIN" in report.outcome_distribution
        assert "LOSS" in report.outcome_distribution
        
        # Check time window distribution
        assert "LONDON_KILLZONE" in report.time_window_distribution
        assert "NY_KILLZONE" in report.time_window_distribution

    async def test_run_end_to_end_minimum_500_setups(self):
        """RED: Test complete end-to-end data loading process."""
        # Mock all dependencies for successful run
        trades = [self.sample_trade.copy() for _ in range(520)]
        for i, trade in enumerate(trades):
            trade["trade_id"] = f"TRD-{i:03d}"

        self.mock_trade_collection.find.return_value.to_list = AsyncMock(
            return_value=trades
        )

        # Mock enriched setup
        mock_enriched = EnrichedSetup(
            trade_id="TRD-001",
            timestamp=datetime.now(timezone.utc),
            instrument="EURUSD",
            direction="BUY",
            entry_price=1.0850,
            exit_price=1.0895,
            stop_loss=1.0800,
            take_profit=1.0950,
            r_multiple=2.5,
            outcome_result="WIN",
            htf_timeframe="H1",
            htf_open=1.0840,
            htf_high=1.0900,
            htf_low=1.0820,
            htf_open_bias="BULLISH",
            htf_high_proximity_pct=0.25,
            htf_low_proximity_pct=0.75,
            htf_body_pct=0.40,
            htf_close_position=0.60,
            bos_detected=True,
            choch_detected=False,
            fvg_present=True,
            liquidity_sweep=False,
            swing_high_distance=15.0,
            swing_low_distance=8.0,
            htf_trend_bias="BULLISH",
            time_window="LONDON_KILLZONE",
            narrative_phase="MANIPULATION",
            time_window_weight=0.8,
            is_killzone=True,
            narrative="Price swept Asian low before rejecting from premium zone",
            confluence_count=5,
        )
        self.mock_enricher.enrich.return_value = mock_enriched

        # Mock embedding generation
        self.mock_embedding_gen.generate_embedding.return_value = [0.1] * 528

        # Mock successful ingestion
        mock_ingestion_result = BatchIngestionResult(
            total=520,
            successful=505,
            failed=15,
            skipped=0,
            ingested_ids=[f"uuid-{i}" for i in range(505)],
            errors=[],
        )
        self.mock_ingestion_service.ingest_batch.return_value = mock_ingestion_result

        # Mock candle data fetching
        with patch('scripts.rag.load_initial_data.fetch_candle_data') as mock_fetch:
            mock_fetch.return_value = ([], [])  # Empty candles for test
            
            report = await self.loader.run()
        
        assert isinstance(report, DataQualityReport)
        assert report.total_setups >= 500, f"Should process at least 500 setups, got {report.total_setups}"
        assert report.successfully_ingested >= 500, f"Should ingest at least 500 setups, got {report.successfully_ingested}"
        assert report.error_rate_pct < 5.0, f"Error rate should be < 5%, got {report.error_rate_pct}%"

    async def test_error_handling_enrichment_failures(self):
        """RED: Test error handling when enrichment fails for some trades."""
        trades = [self.sample_trade.copy() for _ in range(5)]
        
        # Mock enricher to fail on 2nd trade
        def mock_enrich_with_failure(trade, candles, htf_candles):
            if trade.get("trade_id") == trades[1].get("trade_id"):
                raise ValueError("HTF data unavailable")
            return EnrichedSetup(
                trade_id=trade.get("trade_id", "TRD-001"),
                timestamp=datetime.now(timezone.utc),
                instrument="EURUSD",
                direction="BUY",
                entry_price=1.0850,
                exit_price=1.0895,
                stop_loss=1.0800,
                take_profit=1.0950,
                r_multiple=2.5,
                outcome_result="WIN",
                htf_timeframe="H1",
                htf_open=1.0840,
                htf_high=1.0900,
                htf_low=1.0820,
                htf_open_bias="BULLISH",
                htf_high_proximity_pct=0.25,
                htf_low_proximity_pct=0.75,
                htf_body_pct=0.40,
                htf_close_position=0.60,
                bos_detected=True,
                choch_detected=False,
                fvg_present=True,
                liquidity_sweep=False,
                swing_high_distance=15.0,
                swing_low_distance=8.0,
                htf_trend_bias="BULLISH",
                time_window="LONDON_KILLZONE",
                narrative_phase="MANIPULATION",
                time_window_weight=0.8,
                is_killzone=True,
                narrative="Price swept Asian low before rejecting from premium zone",
                confluence_count=5,
            )
        
        self.mock_enricher.enrich.side_effect = mock_enrich_with_failure

        # Mock candle data fetching
        with patch('scripts.rag.load_initial_data.fetch_candle_data') as mock_fetch:
            mock_fetch.return_value = ([], [])
            
            result = await self.loader.enrich_setups(trades)
        
        # Should return 4 successful enrichments (skipping the failed one)
        assert len(result) == 4, f"Should skip failed enrichment, got {len(result)} successes"

    async def test_progress_reporting_during_processing(self):
        """RED: Test progress reporting during long-running operations."""
        trades = [self.sample_trade.copy() for _ in range(100)]
        
        progress_updates = []
        
        async def mock_progress_callback(progress: LoadingProgress):
            progress_updates.append(progress)
        
        self.loader.progress_callback = mock_progress_callback
        
        # Mock enricher
        mock_enriched = EnrichedSetup(
            trade_id="TRD-001",
            timestamp=datetime.now(timezone.utc),
            instrument="EURUSD",
            direction="BUY",
            entry_price=1.0850,
            exit_price=1.0895,
            stop_loss=1.0800,
            take_profit=1.0950,
            r_multiple=2.5,
            outcome_result="WIN",
            htf_timeframe="H1",
            htf_open=1.0840,
            htf_high=1.0900,
            htf_low=1.0820,
            htf_open_bias="BULLISH",
            htf_high_proximity_pct=0.25,
            htf_low_proximity_pct=0.75,
            htf_body_pct=0.40,
            htf_close_position=0.60,
            bos_detected=True,
            choch_detected=False,
            fvg_present=True,
            liquidity_sweep=False,
            swing_high_distance=15.0,
            swing_low_distance=8.0,
            htf_trend_bias="BULLISH",
            time_window="LONDON_KILLZONE",
            narrative_phase="MANIPULATION",
            time_window_weight=0.8,
            is_killzone=True,
            narrative="Price swept Asian low before rejecting from premium zone",
            confluence_count=5,
        )
        self.mock_enricher.enrich.return_value = mock_enriched

        # Mock candle data fetching
        with patch('scripts.rag.load_initial_data.fetch_candle_data') as mock_fetch:
            mock_fetch.return_value = ([], [])
            
            await self.loader.enrich_setups(trades)
        
        # Should receive progress updates during processing
        assert len(progress_updates) > 0, "Should receive progress updates"
        
        # Check final progress update
        final_progress = progress_updates[-1]
        assert final_progress.phase == "enrichment"
        assert final_progress.processed == 100
        assert final_progress.total == 100
        assert final_progress.percent_complete == 100.0

    async def test_save_report_to_file(self):
        """RED: Test saving data quality report to JSON file."""
        report = DataQualityReport(
            timestamp=datetime.now(timezone.utc),
            total_setups=500,
            successfully_ingested=485,
            failed_ingestion=15,
            error_rate_pct=3.0,
            instrument_distribution={"EURUSD": 250, "GBPUSD": 250},
            outcome_distribution={"WIN": 300, "LOSS": 200},
            time_window_distribution={"LONDON_KILLZONE": 200, "NY_KILLZONE": 300},
            average_confluence_count=4.2,
            r_multiple_stats={"mean": 1.8, "median": 2.0, "std": 1.5},
            errors=["TRD-486: Invalid embedding", "TRD-487: Connection timeout"],
        )
        
        output_path = Path("test_data_quality_report.json")
        
        try:
            await self.loader.save_report(report, output_path)
            
            # Should create file and write JSON
            assert output_path.exists(), "Report file should be created"
            
            # Verify JSON content
            with open(output_path, 'r') as f:
                data = json.load(f)
            
            assert data["total_setups"] == 500
            assert data["error_rate_pct"] == 3.0
            assert "EURUSD" in data["instrument_distribution"]
            
        finally:
            # Cleanup test file
            if output_path.exists():
                output_path.unlink()


class TestDataQualityReport:
    """Test the DataQualityReport model."""

    def test_report_initialization(self):
        """RED: Test report can be initialized with all required fields."""
        report = DataQualityReport(
            timestamp=datetime.now(timezone.utc),
            total_setups=1000,
            successfully_ingested=950,
            failed_ingestion=50,
            error_rate_pct=5.0,
            instrument_distribution={"EURUSD": 500, "GBPUSD": 500},
            outcome_distribution={"WIN": 600, "LOSS": 400},
            time_window_distribution={"LONDON_KILLZONE": 400, "NY_KILLZONE": 600},
            average_confluence_count=4.5,
            r_multiple_stats={"mean": 2.1, "median": 2.0, "std": 1.8},
            errors=["Error 1", "Error 2"],
        )
        
        assert report.total_setups == 1000
        assert report.successfully_ingested == 950
        assert report.error_rate_pct == 5.0

    def test_report_validation_error_rate(self):
        """RED: Test report validates error rate is within reasonable bounds."""
        with pytest.raises(ValueError):
            DataQualityReport(
                timestamp=datetime.now(timezone.utc),
                total_setups=100,
                successfully_ingested=50,
                failed_ingestion=50,
                error_rate_pct=150.0,  # Invalid - over 100%
                instrument_distribution={},
                outcome_distribution={},
                time_window_distribution={},
                average_confluence_count=0.0,
                r_multiple_stats={},
                errors=[],
            )


class TestLoadingProgress:
    """Test the LoadingProgress model."""

    def test_progress_calculation(self):
        """RED: Test progress percentage calculation."""
        progress = LoadingProgress(
            phase="enrichment",
            processed=250,
            total=1000,
        )
        
        assert progress.percent_complete == 25.0

    def test_progress_validation(self):
        """RED: Test progress validation (processed <= total)."""
        with pytest.raises(ValueError):
            LoadingProgress(
                phase="ingestion",
                processed=1500,  # More than total
                total=1000,
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])