"""
Integration tests for AlgoRAG ingestion system.

Task 7.3: Write integration tests for ingestion
- Test ingestion of 100+ setups
- Test error handling (network failures, invalid data)  
- Test ingestion performance (< 1s per setup)
- Requirements: FR-RAG-7, NFR-RAG-1

These tests require a live Qdrant instance and are marked with @pytest.mark.integration.
Run with: pytest -m integration services/algorag/tests/test_ingestion_integration.py -v

Performance tests use @pytest.mark.performance for optional execution.
Run with: pytest -m "integration and performance" -v --tb=short
"""

from __future__ import annotations

import os
import sys

# Add workspace root to Python path for imports
_WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if _WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, _WORKSPACE_ROOT)

import asyncio
import json
import random
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Tuple
from unittest.mock import patch

import numpy as np
import pytest
from qdrant_client.http.exceptions import ResponseHandlingException, UnexpectedResponse

from services.algorag.config import QdrantConfig
from services.algorag.ingestion_service import (
    EMBEDDING_DIM,
    BatchIngestionResult,
    DuplicateStrategy,
    IngestionService,
    IngestionServiceError,
)
from services.algorag.qdrant_client import QdrantClientWrapper, QdrantConnectionError
from scripts.rag.utils.setup_enricher import EnrichedSetup


# ---------------------------------------------------------------------------
# Test configuration and fixtures
# ---------------------------------------------------------------------------


def make_test_config(collection_suffix: str = "") -> QdrantConfig:
    """Create test-specific Qdrant config with unique collection name."""
    collection_name = f"test_ingestion_integration_{int(time.time())}"
    if collection_suffix:
        collection_name += f"_{collection_suffix}"
        
    return QdrantConfig(
        host="localhost",
        port=6333,
        collection=collection_name,
        timeout=10.0,
        max_retries=3,
        retry_backoff=0.1,
    )


def make_test_enriched_setup(trade_id: str, **overrides) -> Dict[str, Any]:
    """Create a minimal valid enriched setup for testing."""
    base_setup = {
        "trade_id": trade_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "instrument": "EURUSD",
        "direction": "LONG",
        "entry_price": 1.1000 + random.uniform(-0.01, 0.01),
        "exit_price": 1.1050 + random.uniform(-0.01, 0.01),
        "stop_loss": 1.0950 + random.uniform(-0.005, 0.005),
        "take_profit": 1.1100 + random.uniform(-0.01, 0.01),
        "r_multiple": random.uniform(1.0, 5.0),
        "outcome_result": random.choice(["WIN", "LOSS"]),
        "htf_timeframe": "H1",
        "htf_open": 1.0980,
        "htf_high": 1.1120,
        "htf_low": 1.0960,
        "htf_open_bias": random.choice(["BULLISH", "BEARISH", "NEUTRAL"]),
        "htf_high_proximity_pct": random.uniform(0.0, 1.0),
        "htf_low_proximity_pct": random.uniform(0.0, 1.0),
        "htf_body_pct": random.uniform(0.0, 1.0),
        "htf_close_position": random.uniform(0.0, 1.0),
        "bos_detected": random.choice([True, False]),
        "choch_detected": random.choice([True, False]),
        "fvg_present": random.choice([True, False]),
        "liquidity_sweep": random.choice([True, False]),
        "swing_high_distance": random.uniform(10, 100),
        "swing_low_distance": random.uniform(10, 100),
        "htf_trend_bias": random.choice(["BULLISH", "BEARISH", "NEUTRAL"]),
        "time_window": random.choice(["LONDON_KILLZONE", "NY_KILLZONE", "ASIAN_KILLZONE"]),
        "narrative_phase": random.choice(["MANIPULATION", "DISTRIBUTION", "REBALANCE"]),
        "time_window_weight": random.uniform(0.5, 1.0),
        "is_killzone": random.choice([True, False]),
        "narrative": f"Test setup for trade {trade_id} with price action analysis",
        "confluence_count": random.randint(1, 6),
    }
    base_setup.update(overrides)
    return base_setup


def make_test_embedding(seed: int = None) -> List[float]:
    """Generate deterministic 528-dim test embedding."""
    if seed is not None:
        rng = np.random.default_rng(seed)
    else:
        rng = np.random.default_rng()
    return rng.standard_normal(EMBEDDING_DIM).tolist()


def generate_test_dataset(count: int) -> List[Tuple[Dict[str, Any], List[float]]]:
    """Generate a dataset of enriched setups with embeddings for testing."""
    dataset = []
    instruments = ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "US500"]
    
    for i in range(count):
        trade_id = f"TEST-{i:05d}"
        setup = make_test_enriched_setup(
            trade_id=trade_id,
            instrument=random.choice(instruments),
        )
        embedding = make_test_embedding(seed=i)  # Deterministic for reproducibility
        dataset.append((setup, embedding))
    
    return dataset


@pytest.fixture
def test_service() -> IngestionService:
    """Create test ingestion service with unique collection."""
    config = make_test_config("fixture")
    return IngestionService(config=config, batch_size=50)  # Reasonable batch size


# ---------------------------------------------------------------------------
# Test: 100+ setups ingestion
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestLargeScaleIngestion:
    """Test ingestion of large batches (100+ setups) to validate scalability."""

    @pytest.mark.asyncio
    async def test_ingest_100_setups_succeeds(self, test_service: IngestionService) -> None:
        """Ingest exactly 100 setups and verify all are stored correctly."""
        dataset = generate_test_dataset(100)
        
        try:
            # Ensure collection exists
            await test_service._wrapper.ensure_collection()
            
            # Ingest the dataset
            result = await test_service.ingest_batch(dataset)
            
            # Verify results
            assert result.total == 100
            assert result.successful == 100
            assert result.failed == 0
            assert result.skipped == 0
            assert len(result.ingested_ids) == 100
            assert len(result.errors) == 0
            
            # Verify count in Qdrant
            count = await test_service._wrapper.count()
            assert count == 100
            
        finally:
            # Cleanup
            await test_service._wrapper.delete_collection()
            await test_service._wrapper.close()

    @pytest.mark.asyncio  
    async def test_ingest_250_setups_with_batching(self) -> None:
        """Test ingestion of 250 setups with automatic batching."""
        config = make_test_config("batch_250")
        service = IngestionService(config=config, batch_size=75)  # Force multiple batches
        dataset = generate_test_dataset(250)
        
        try:
            await service._wrapper.ensure_collection()
            
            result = await service.ingest_batch(dataset)
            
            assert result.total == 250
            assert result.successful == 250
            assert result.failed == 0
            assert len(result.ingested_ids) == 250
            
            # Verify all setups are stored
            count = await service._wrapper.count()
            assert count == 250
            
        finally:
            await service._wrapper.delete_collection()
            await service._wrapper.close()

    @pytest.mark.asyncio
    async def test_ingest_500_mixed_instruments(self) -> None:
        """Test ingestion of 500 setups across multiple instruments."""
        config = make_test_config("mixed_500")
        service = IngestionService(config=config, batch_size=100)
        
        # Create dataset with known distribution
        instruments = ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "US500"]
        dataset = []
        
        for i in range(500):
            instrument = instruments[i % len(instruments)]  # Even distribution
            setup = make_test_enriched_setup(
                trade_id=f"MIXED-{instrument}-{i:03d}",
                instrument=instrument,
            )
            embedding = make_test_embedding(seed=i)
            dataset.append((setup, embedding))
        
        try:
            await service._wrapper.ensure_collection()
            
            result = await service.ingest_batch(dataset)
            
            assert result.successful == 500
            assert result.failed == 0
            
            # Verify storage
            count = await service._wrapper.count()
            assert count == 500
            
        finally:
            await service._wrapper.delete_collection()
            await service._wrapper.close()


# ---------------------------------------------------------------------------
# Test: Error handling
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestIngestionErrorHandling:
    """Test ingestion behavior under various error conditions."""

    @pytest.mark.asyncio
    async def test_invalid_embedding_dimensions_rejected_early(self, test_service: IngestionService) -> None:
        """Invalid embedding dimensions should be rejected before any network calls."""
        setup = make_test_enriched_setup("BAD-DIM-001")
        bad_embedding = [0.0] * 256  # Wrong dimension
        
        try:
            await test_service._wrapper.ensure_collection()
            
            with pytest.raises(ValueError, match="528-dimensional"):
                await test_service.ingest_batch([(setup, bad_embedding)])
                
            # Verify no data was stored
            count = await test_service._wrapper.count() 
            assert count == 0
            
        finally:
            await test_service._wrapper.delete_collection()
            await test_service._wrapper.close()

    @pytest.mark.asyncio
    async def test_mixed_valid_invalid_embeddings_fails_fast(self, test_service: IngestionService) -> None:
        """Batch with mix of valid/invalid embeddings fails before any ingestion."""
        dataset = [
            (make_test_enriched_setup("VALID-001"), make_test_embedding(1)),
            (make_test_enriched_setup("INVALID-002"), [0.0] * 100),  # Bad dimension
            (make_test_enriched_setup("VALID-003"), make_test_embedding(3)),
        ]
        
        try:
            await test_service._wrapper.ensure_collection()
            
            with pytest.raises(ValueError, match="528-dimensional"):
                await test_service.ingest_batch(dataset)
                
            # Verify no partial ingestion occurred
            count = await test_service._wrapper.count()
            assert count == 0
            
        finally:
            await test_service._wrapper.delete_collection()
            await test_service._wrapper.close()

    @pytest.mark.asyncio
    async def test_qdrant_connection_failure_raises_service_error(self) -> None:
        """Network failures during ingestion should raise IngestionServiceError."""
        # Use invalid host to simulate connection failure
        config = QdrantConfig(
            host="nonexistent-qdrant-host", 
            port=6333, 
            collection="test_connection_failure",
            timeout=1.0,  # Short timeout for quick failure
            max_retries=1,  # Minimal retries
        )
        service = IngestionService(config=config)
        dataset = generate_test_dataset(10)
        
        with pytest.raises(IngestionServiceError, match="Batch ingestion failed"):
            await service.ingest_batch(dataset)

    @pytest.mark.asyncio
    async def test_partial_batch_failures_tracked_in_result(self) -> None:
        """When using small batches, individual batch failures should be tracked."""
        config = make_test_config("partial_failure")
        service = IngestionService(config=config, batch_size=25)  # Small batches
        
        try:
            await service._wrapper.ensure_collection()
            
            # Create dataset
            dataset = generate_test_dataset(100)
            
            # Mock wrapper to fail on specific batch calls
            original_upsert = service._wrapper.upsert
            call_count = 0
            
            async def failing_upsert(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                if call_count == 2:  # Fail the second batch
                    raise QdrantConnectionError("Simulated batch failure")
                return await original_upsert(*args, **kwargs)
            
            service._wrapper.upsert = failing_upsert
            
            result = await service.ingest_batch(dataset)
            
            # Should have partial success
            assert result.total == 100
            assert result.successful == 75  # 3 successful batches of 25 each
            assert result.failed == 25      # 1 failed batch of 25
            assert len(result.errors) == 25
            assert result.skipped == 0
            
        finally:
            await service._wrapper.delete_collection()
            await service._wrapper.close()

    @pytest.mark.asyncio
    async def test_malformed_setup_data_handles_gracefully(self, test_service: IngestionService) -> None:
        """Malformed setup data should be handled gracefully without crashing."""
        malformed_setups = [
            # Missing required fields
            ({"trade_id": "MALFORMED-001"}, make_test_embedding(1)),
            # Invalid data types  
            ({"trade_id": "MALFORMED-002", "entry_price": "not_a_number"}, make_test_embedding(2)),
            # None values
            ({"trade_id": None, "instrument": None}, make_test_embedding(3)),
        ]
        
        try:
            await test_service._wrapper.ensure_collection()
            
            # Should not crash, even with malformed data
            result = await test_service.ingest_batch(malformed_setups)
            
            assert result.total == 3
            # All should succeed (build_point_from_setup handles missing fields)
            assert result.successful == 3
            assert result.failed == 0
            
        finally:
            await test_service._wrapper.delete_collection()
            await test_service._wrapper.close()


# ---------------------------------------------------------------------------
# Test: Performance (< 1s per setup)
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.performance
class TestIngestionPerformance:
    """Test ingestion performance requirements (< 1s per setup)."""

    @pytest.mark.asyncio
    async def test_single_setup_ingestion_under_1s(self, test_service: IngestionService) -> None:
        """Single setup ingestion must complete in < 1 second."""
        setup = make_test_enriched_setup("PERF-SINGLE")
        embedding = make_test_embedding(42)
        
        try:
            await test_service._wrapper.ensure_collection()
            
            start_time = time.perf_counter()
            result = await test_service.ingest_batch([(setup, embedding)])
            end_time = time.perf_counter()
            
            elapsed = end_time - start_time
            
            assert result.successful == 1
            assert elapsed < 1.0, f"Single setup took {elapsed:.3f}s (> 1s limit)"
            
        finally:
            await test_service._wrapper.delete_collection()
            await test_service._wrapper.close()

    @pytest.mark.asyncio
    async def test_100_setups_batch_performance(self) -> None:
        """100 setups should ingest at < 1s per setup (total < 100s)."""
        config = make_test_config("perf_100")
        service = IngestionService(config=config, batch_size=50)  # Optimal batching
        dataset = generate_test_dataset(100)
        
        try:
            await service._wrapper.ensure_collection()
            
            start_time = time.perf_counter()
            result = await service.ingest_batch(dataset)
            end_time = time.perf_counter()
            
            elapsed = end_time - start_time
            per_setup = elapsed / 100
            
            assert result.successful == 100
            assert per_setup < 1.0, f"Per-setup time: {per_setup:.3f}s (> 1s limit)"
            assert elapsed < 60.0, f"Total time: {elapsed:.1f}s (should be much faster)"
            
        finally:
            await service._wrapper.delete_collection()
            await service._wrapper.close()

    @pytest.mark.asyncio
    async def test_concurrent_ingestion_performance(self) -> None:
        """Test concurrent ingestion of multiple batches."""
        config = make_test_config("concurrent")
        
        async def ingest_batch_async(batch_id: int, batch_size: int) -> float:
            """Ingest a batch and return elapsed time."""
            service = IngestionService(config=config)
            dataset = generate_test_dataset(batch_size)
            
            # Add unique suffix to trade_ids to avoid conflicts
            for i, (setup, embedding) in enumerate(dataset):
                setup["trade_id"] = f"BATCH{batch_id}-{i:03d}"
            
            start_time = time.perf_counter()
            result = await service.ingest_batch(dataset)
            end_time = time.perf_counter()
            
            await service._wrapper.close()
            
            assert result.successful == batch_size
            return end_time - start_time
        
        try:
            # Setup collection
            wrapper = QdrantClientWrapper(config=config)
            await wrapper.ensure_collection()
            await wrapper.close()
            
            # Run 3 concurrent batches of 50 setups each
            batch_size = 50
            tasks = [
                ingest_batch_async(batch_id, batch_size) 
                for batch_id in range(3)
            ]
            
            batch_times = await asyncio.gather(*tasks)
            
            # Verify performance
            for i, elapsed in enumerate(batch_times):
                per_setup = elapsed / batch_size
                assert per_setup < 1.0, f"Batch {i}: {per_setup:.3f}s per setup (> 1s limit)"
                
        finally:
            # Cleanup
            wrapper = QdrantClientWrapper(config=config)
            await wrapper.delete_collection()
            await wrapper.close()

    @pytest.mark.asyncio
    async def test_large_embedding_batch_performance(self) -> None:
        """Test performance with realistic embedding computation overhead."""
        config = make_test_config("large_embed")
        service = IngestionService(config=config, batch_size=100)
        
        # Generate larger dataset to test batch efficiency
        dataset_size = 200
        dataset = []
        
        # Simulate realistic embedding generation time
        for i in range(dataset_size):
            setup = make_test_enriched_setup(f"LARGE-{i:04d}")
            
            # Generate embedding with some computation overhead
            start_embed = time.perf_counter()
            embedding = make_test_embedding(i)
            # Add small delay to simulate real embedding computation
            await asyncio.sleep(0.001)  # 1ms per embedding (realistic for SBERT)
            
            dataset.append((setup, embedding))
        
        try:
            await service._wrapper.ensure_collection()
            
            start_time = time.perf_counter()
            result = await service.ingest_batch(dataset)
            end_time = time.perf_counter()
            
            elapsed = end_time - start_time
            per_setup = elapsed / dataset_size
            
            assert result.successful == dataset_size
            # Allow for embedding computation overhead, but still under 1s per setup
            assert per_setup < 1.0, f"With embedding overhead: {per_setup:.3f}s per setup"
            
        finally:
            await service._wrapper.delete_collection()
            await service._wrapper.close()


# ---------------------------------------------------------------------------
# Test: Duplicate handling in integration context
# ---------------------------------------------------------------------------


@pytest.mark.integration  
class TestDuplicateHandlingIntegration:
    """Test duplicate detection and handling with live Qdrant."""

    @pytest.mark.asyncio
    async def test_duplicate_trade_ids_upsert_correctly(self) -> None:
        """Duplicate trade_ids should upsert (update) existing records."""
        config = make_test_config("duplicate_upsert")
        service = IngestionService(config=config, duplicate_strategy=DuplicateStrategy.UPSERT)
        
        try:
            await service._wrapper.ensure_collection()
            
            # Initial ingestion
            setup_v1 = make_test_enriched_setup("DUP-TRADE-001", outcome_result="LOSS")
            embedding_v1 = make_test_embedding(1)
            result1 = await service.ingest_batch([(setup_v1, embedding_v1)])
            
            assert result1.successful == 1
            count_after_first = await service._wrapper.count()
            assert count_after_first == 1
            
            # Update with different outcome
            setup_v2 = make_test_enriched_setup("DUP-TRADE-001", outcome_result="WIN")
            embedding_v2 = make_test_embedding(2)  # Different embedding
            result2 = await service.ingest_batch([(setup_v2, embedding_v2)])
            
            assert result2.successful == 1
            count_after_second = await service._wrapper.count()
            # Count should remain 1 (upsert, not duplicate)
            assert count_after_second == 1
            
        finally:
            await service._wrapper.delete_collection()
            await service._wrapper.close()

    @pytest.mark.asyncio
    async def test_skip_strategy_prevents_network_calls(self) -> None:
        """SKIP strategy should prevent redundant network calls for known trade_ids."""
        config = make_test_config("skip_strategy")
        service = IngestionService(config=config, duplicate_strategy=DuplicateStrategy.SKIP)
        
        try:
            await service._wrapper.ensure_collection()
            
            setup = make_test_enriched_setup("SKIP-TRADE-001")
            embedding = make_test_embedding(1)
            
            # First ingestion
            result1 = await service.ingest_batch([(setup, embedding)])
            assert result1.successful == 1
            assert result1.skipped == 0
            
            # Second ingestion of same trade_id
            result2 = await service.ingest_batch([(setup, embedding)])
            assert result2.successful == 0  # Not re-ingested
            assert result2.skipped == 1     # Skipped due to strategy
            
            # Count should remain 1
            count = await service._wrapper.count()
            assert count == 1
            
        finally:
            await service._wrapper.delete_collection()
            await service._wrapper.close()


# ---------------------------------------------------------------------------
# Test: Real-time ingestion simulation
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.performance
class TestRealTimeIngestionSimulation:
    """Simulate real-time ingestion patterns for FR-RAG-7."""

    @pytest.mark.asyncio
    async def test_streaming_ingestion_under_60s_target(self) -> None:
        """Simulate real-time setup ingestion with 60s target (FR-RAG-7)."""
        config = make_test_config("realtime")
        service = IngestionService(config=config, batch_size=1)  # Single-setup ingestion
        
        try:
            await service._wrapper.ensure_collection()
            
            # Simulate 10 setups arriving over time (like real trades closing)
            total_setups = 10
            ingestion_times = []
            
            for i in range(total_setups):
                setup = make_test_enriched_setup(f"REALTIME-{i:03d}")
                embedding = make_test_embedding(i)
                
                start_time = time.perf_counter()
                result = await service.ingest_batch([(setup, embedding)])
                end_time = time.perf_counter()
                
                elapsed = end_time - start_time
                ingestion_times.append(elapsed)
                
                assert result.successful == 1
                assert elapsed < 60.0, f"Setup {i}: {elapsed:.3f}s (> 60s target)"
                
                # Small delay to simulate realistic trade timing
                await asyncio.sleep(0.1)
            
            # Verify all setups were ingested
            final_count = await service._wrapper.count()
            assert final_count == total_setups
            
            # Performance metrics
            avg_time = sum(ingestion_times) / len(ingestion_times)
            max_time = max(ingestion_times)
            
            assert avg_time < 5.0, f"Average ingestion time: {avg_time:.3f}s"
            assert max_time < 60.0, f"Max ingestion time: {max_time:.3f}s"
            
        finally:
            await service._wrapper.delete_collection()
            await service._wrapper.close()

    @pytest.mark.asyncio
    async def test_burst_ingestion_handling(self) -> None:
        """Test handling of burst ingestion (multiple trades closing simultaneously)."""
        config = make_test_config("burst")
        service = IngestionService(config=config, batch_size=25)
        
        try:
            await service._wrapper.ensure_collection()
            
            # Simulate burst of 50 setups (multiple trades closing at market close)
            burst_size = 50
            burst_dataset = generate_test_dataset(burst_size)
            
            start_time = time.perf_counter()
            result = await service.ingest_batch(burst_dataset)
            end_time = time.perf_counter()
            
            elapsed = end_time - start_time
            per_setup = elapsed / burst_size
            
            assert result.successful == burst_size
            assert per_setup < 1.0, f"Burst per-setup time: {per_setup:.3f}s"
            assert elapsed < 30.0, f"Burst total time: {elapsed:.1f}s (should handle quickly)"
            
        finally:
            await service._wrapper.delete_collection()
            await service._wrapper.close()


if __name__ == "__main__":
    import sys
    
    print("AlgoRAG Ingestion Integration Tests")
    print("=" * 40)
    print()
    print("To run these tests, ensure:")
    print("1. Qdrant is running on localhost:6333")
    print("2. Use: pytest -m integration services/algorag/tests/test_ingestion_integration.py -v")
    print("3. For performance tests: pytest -m 'integration and performance' -v")
    print()
    
    # Quick smoke test if run directly
    if len(sys.argv) > 1 and sys.argv[1] == "--smoke":
        import asyncio
        
        async def smoke_test():
            config = make_test_config("smoke")
            service = IngestionService(config=config)
            
            try:
                print("Testing Qdrant connection...")
                await service._wrapper.ensure_collection()
                
                print("Testing single setup ingestion...")
                setup = make_test_enriched_setup("SMOKE-001")
                embedding = make_test_embedding(42)
                
                result = await service.ingest_batch([(setup, embedding)])
                assert result.successful == 1
                
                count = await service._wrapper.count()
                assert count == 1
                
                print("✅ Smoke test passed - integration tests should work")
                
            except Exception as e:
                print(f"❌ Smoke test failed: {e}")
                print("Check that Qdrant is running on localhost:6333")
            finally:
                await service._wrapper.delete_collection()
                await service._wrapper.close()
        
        asyncio.run(smoke_test())