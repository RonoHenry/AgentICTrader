"""
Performance checkpoint tests for Task 14.

These tests verify the RAG service meets performance requirements:
- Retrieval endpoint returns results < 100ms (p95 requirement)
- RAG metrics computation is working correctly
- Service health check is functional

Requirements: NFR-RAG-1 (Performance)
"""

from __future__ import annotations

import asyncio
import pytest
import statistics
import time
from datetime import datetime, timezone
from unittest.mock import AsyncMock

from services.algorag.models import (
    HealthResponse,
    RetrievalRequest,
    RetrievalResponse, 
    RAGMetrics,
    SimilarSetup,
)


@pytest.mark.integration
class TestPerformanceCheckpoint:
    """Performance validation tests for Task 14 checkpoint."""

    async def test_health_endpoint_response_time(self):
        """RED: Test health endpoint responds quickly (< 50ms)."""
        from services.algorag.main import app
        from httpx import AsyncClient
        from unittest.mock import patch, AsyncMock
        
        # Mock Qdrant for health check
        with patch('services.algorag.main.get_qdrant') as mock_get_qdrant:
            mock_wrapper = AsyncMock()
            mock_wrapper.count.return_value = 500  # Mock setup count
            mock_get_qdrant.return_value = mock_wrapper
            
            # Mock the health check methods
            with patch('services.algorag.main._check_qdrant_health', return_value=True), \
                 patch('services.algorag.main._get_setup_count', return_value=500):
                
                async with AsyncClient(app=app, base_url="http://testserver") as client:
                    # Measure response time
                    start = time.perf_counter()
                    response = await client.get("/health")
                    elapsed_ms = (time.perf_counter() - start) * 1000
                    
                    # Health check should be very fast
                    assert elapsed_ms < 50.0  # 50ms threshold
                    assert response.status_code == 200
                    
                    # Parse response
                    health_data = response.json()
                    assert health_data["service"] == "algorag"
                    assert "status" in health_data
                    assert "setup_count" in health_data

    async def test_retrieval_endpoint_latency_target(self):
        """RED: Test retrieval endpoint meets < 100ms requirement (with mocked Qdrant)."""
        from services.algorag.main import app
        from httpx import AsyncClient
        from unittest.mock import patch, AsyncMock
        
        # Mock search results
        mock_hits = [
            AsyncMock(
                id="test-1",
                score=0.95,
                payload={
                    "trade_id": "TRD-001",
                    "timestamp": "2024-03-15T09:15:00Z",
                    "instrument": "EURUSD",
                    "time_window": "LONDON_KILLZONE",
                    "htf_open_bias": "BULLISH",
                    "confluence_count": 5,
                    "outcome_result": "WIN",
                    "outcome_r_multiple": 4.2,
                    "narrative": "Price swept Asian low, found support at discount PD array",
                    "full_setup": {"type": "test_setup"}
                }
            ),
            AsyncMock(
                id="test-2",
                score=0.87,
                payload={
                    "trade_id": "TRD-002", 
                    "timestamp": "2024-03-10T14:30:00Z",
                    "instrument": "EURUSD",
                    "time_window": "NY_KILLZONE",
                    "htf_open_bias": "BULLISH",
                    "confluence_count": 3,
                    "outcome_result": "WIN",
                    "outcome_r_multiple": 2.8,
                    "narrative": "Clean BOS, entry at FVG",
                    "full_setup": {"type": "test_setup"}
                }
            )
        ]
        
        # Mock the QdrantClientWrapper.search method
        async def mock_search(*args, **kwargs):
            # Add small delay to simulate network latency but keep under target
            await asyncio.sleep(0.02)  # 20ms simulated latency
            return mock_hits
        
        with patch('services.algorag.main.get_qdrant') as mock_get_qdrant:
            mock_wrapper = AsyncMock()
            mock_wrapper.search = mock_search
            mock_get_qdrant.return_value = mock_wrapper
            
            async with AsyncClient(app=app, base_url="http://testserver") as client:
                request_data = {
                    "instrument": "EURUSD",
                    "timestamp": "2024-05-06T09:15:00Z",
                    "time_window": "LONDON_KILLZONE",
                    "htf_open_bias": "BULLISH",
                    "narrative": "Current setup description",
                    "htf_structure": {"htf_high": 1.0900, "htf_low": 1.0850},
                    "pd_arrays": {"fvg_count": 1, "ob_count": 2},  # Dict, not List
                    "confluence_factors": ["bos", "fvg", "time_window"],
                    "top_k": 10
                }
                
                # Measure response time
                start = time.perf_counter()
                response = await client.post("/rag/retrieve", json=request_data)
                elapsed_ms = (time.perf_counter() - start) * 1000
                
                # Should meet p95 latency requirement 
                assert elapsed_ms < 100.0  # 100ms threshold from requirements
                assert response.status_code == 200
                
                # Verify response structure
                result = response.json()
                assert "similar_setups" in result
                assert "rag_metrics" in result
                assert "query_time_ms" in result
                assert len(result["similar_setups"]) >= 0

    async def test_retrieval_latency_multiple_requests(self):
        """RED: Test retrieval latency across multiple requests (p95 check)."""
        from services.algorag.main import app
        from httpx import AsyncClient
        from unittest.mock import patch, AsyncMock
        
        # Mock fast search results
        mock_hits = [
            AsyncMock(
                id=f"test-{i}",
                score=0.9 - (i * 0.1),
                payload={
                    "trade_id": f"TRD-{i:03d}",
                    "timestamp": "2024-03-15T09:15:00Z",
                    "instrument": "EURUSD", 
                    "time_window": "LONDON_KILLZONE",
                    "htf_open_bias": "BULLISH",
                    "confluence_count": 3,
                    "outcome_result": "WIN",
                    "outcome_r_multiple": 2.5 + i,
                    "narrative": f"Setup {i}",
                    "full_setup": {"type": "test_setup"}
                }
            ) for i in range(5)
        ]
        
        async def mock_search(*args, **kwargs):
            # Variable latency simulation (10-30ms)
            await asyncio.sleep(0.01 + (asyncio.get_event_loop().time() % 0.02))
            return mock_hits
        
        with patch('services.algorag.main.get_qdrant') as mock_get_qdrant:
            mock_wrapper = AsyncMock()
            mock_wrapper.search = mock_search  
            mock_get_qdrant.return_value = mock_wrapper
            
            async with AsyncClient(app=app, base_url="http://testserver") as client:
                request_data = {
                    "instrument": "EURUSD",
                    "timestamp": "2024-05-06T09:15:00Z",
                    "narrative": "Test setup",
                    "htf_structure": {},
                    "pd_arrays": {},  # Dict, not List
                    "confluence_factors": [],
                    "top_k": 5
                }
                
                # Run multiple requests and collect latencies
                latencies = []
                for i in range(20):
                    start = time.perf_counter()
                    response = await client.post("/rag/retrieve", json=request_data)
                    elapsed_ms = (time.perf_counter() - start) * 1000
                    
                    assert response.status_code == 200
                    latencies.append(elapsed_ms)
                
                # Calculate percentiles
                latencies.sort()
                p50 = statistics.median(latencies)
                p95 = statistics.quantiles(latencies, n=20)[18]  # 95th percentile
                p99 = statistics.quantiles(latencies, n=100)[98] if len(latencies) >= 100 else max(latencies)
                
                # Verify performance targets from requirements
                assert p50 < 50.0   # p50 target from NFR-RAG-1
                assert p95 < 100.0  # p95 target from NFR-RAG-1
                
                print(f"Performance results: p50={p50:.2f}ms, p95={p95:.2f}ms, p99={p99:.2f}ms")

    async def test_rag_metrics_computation_correctness(self):
        """RED: Test RAG metrics are computed correctly."""
        from services.algorag.main import _build_rag_metrics
        from services.algorag.models import SimilarSetup
        
        # Create test setups with known metrics
        setups = [
            SimilarSetup(
                trade_id="TRD-001",
                timestamp=datetime(2024, 3, 15, tzinfo=timezone.utc),
                instrument="EURUSD",
                time_window="LONDON_KILLZONE", 
                htf_open_bias="BULLISH",
                confluence_count=5,
                outcome_result="WIN",
                outcome_r_multiple=4.0,  # High R
                narrative="Great setup",
                similarity_score=0.95,
                final_score=0.95,
            ),
            SimilarSetup(
                trade_id="TRD-002",
                timestamp=datetime(2024, 3, 10, tzinfo=timezone.utc),
                instrument="EURUSD",
                time_window="NY_KILLZONE",
                htf_open_bias="BULLISH", 
                confluence_count=3,
                outcome_result="WIN",
                outcome_r_multiple=2.0,  # Moderate R
                narrative="Good setup",
                similarity_score=0.87,
                final_score=0.87,
            ),
            SimilarSetup(
                trade_id="TRD-003", 
                timestamp=datetime(2024, 3, 5, tzinfo=timezone.utc),
                instrument="EURUSD",
                time_window="LONDON_KILLZONE",
                htf_open_bias="BEARISH",
                confluence_count=4,
                outcome_result="LOSS",  # Loss
                outcome_r_multiple=-1.0,
                narrative="Poor setup",
                similarity_score=0.82,
                final_score=0.82,
            ),
        ]
        
        # Compute metrics (top-5, but only 3 setups)
        metrics = _build_rag_metrics(setups)
        
        # Verify calculations
        assert metrics.sample_size == 3
        assert metrics.win_rate_similar == 2/3  # 2 wins out of 3 (≈ 0.667)
        assert abs(metrics.avg_r_multiple_similar - 1.67) < 0.1  # (4.0 + 2.0 - 1.0) / 3 
        assert metrics.max_similarity_score == 0.95
        assert abs(metrics.avg_confluence_count - 4.0) < 0.1  # (5 + 3 + 4) / 3
        
        # Test bounds
        assert 0.0 <= metrics.win_rate_similar <= 1.0
        assert 0.0 <= metrics.max_similarity_score <= 1.0
        assert metrics.sample_size >= 0

    async def test_rag_metrics_empty_setups(self):
        """RED: Test RAG metrics with empty results."""
        from services.algorag.main import _build_rag_metrics
        
        metrics = _build_rag_metrics([])
        
        assert metrics.avg_r_multiple_similar == 0.0
        assert metrics.win_rate_similar == 0.0
        assert metrics.sample_size == 0
        assert metrics.max_similarity_score == 0.0
        assert metrics.avg_confluence_count == 0.0

    async def test_rag_metrics_top_5_limitation(self):
        """RED: Test RAG metrics only uses top-5 results."""
        from services.algorag.main import _build_rag_metrics
        from services.algorag.models import SimilarSetup
        
        # Create 10 setups but only first 5 should be used
        setups = []
        for i in range(10):
            setup = SimilarSetup(
                trade_id=f"TRD-{i:03d}",
                timestamp=datetime(2024, 3, i+1, tzinfo=timezone.utc),
                instrument="EURUSD",
                time_window="LONDON_KILLZONE",
                htf_open_bias="BULLISH", 
                confluence_count=i+1,  # Different confluence counts
                outcome_result="WIN",
                outcome_r_multiple=i+1.0,  # Different R-multiples 
                narrative=f"Setup {i}",
                similarity_score=0.9 - (i * 0.05),
                final_score=0.9 - (i * 0.05),
            )
            setups.append(setup)
        
        metrics = _build_rag_metrics(setups)
        
        # Should only use first 5 setups
        assert metrics.sample_size == 5
        expected_avg_r = (1.0 + 2.0 + 3.0 + 4.0 + 5.0) / 5  # 3.0
        assert abs(metrics.avg_r_multiple_similar - expected_avg_r) < 0.1
        expected_avg_confluence = (1 + 2 + 3 + 4 + 5) / 5  # 3.0
        assert abs(metrics.avg_confluence_count - expected_avg_confluence) < 0.1

    @pytest.mark.parametrize("embed_size", [528])
    async def test_embedding_dimension_validation(self, embed_size):
        """RED: Test service accepts correct embedding dimensions."""
        from services.algorag.main import app
        from httpx import AsyncClient
        from unittest.mock import patch, AsyncMock
        
        with patch('services.algorag.main.get_qdrant') as mock_get_qdrant:
            mock_wrapper = AsyncMock()
            mock_wrapper.upsert = AsyncMock()
            mock_get_qdrant.return_value = mock_wrapper
            
            async with AsyncClient(app=app, base_url="http://testserver") as client:
                request_data = {
                    "setup": {
                        "trade_id": "TRD-TEST",
                        "instrument": "EURUSD",
                        "timestamp": "2024-05-06T09:15:00Z",
                        "outcome_result": "WIN",
                        "outcome_r_multiple": 2.5,
                    },
                    "embedding": [0.1] * embed_size  # Correct dimension
                }
                
                response = await client.post("/rag/ingest", json=request_data)
                
                # Should accept 528-dim embeddings
                if embed_size == 528:
                    assert response.status_code == 201
                else:
                    # Would fail validation for other dimensions (if implemented)
                    pass

    async def test_service_graceful_degradation(self):
        """RED: Test service handles failures gracefully."""
        from services.algorag.main import app
        from httpx import AsyncClient
        from unittest.mock import patch, AsyncMock
        
        # Mock Qdrant failure
        with patch('services.algorag.main.get_qdrant') as mock_get_qdrant:
            mock_wrapper = AsyncMock()
            mock_wrapper.search.side_effect = Exception("Connection timeout")
            mock_get_qdrant.return_value = mock_wrapper
            
            async with AsyncClient(app=app, base_url="http://testserver") as client:
                request_data = {
                    "instrument": "EURUSD",
                    "timestamp": "2024-05-06T09:15:00Z",
                    "narrative": "Test setup",
                    "htf_structure": {},
                    "pd_arrays": {},  # Dict, not List
                    "confluence_factors": [],
                }
                
                response = await client.post("/rag/retrieve", json=request_data)
                
                # Should return graceful error, not crash
                assert response.status_code == 503  # Service Unavailable
                assert "unavailable" in response.json()["detail"].lower()


@pytest.mark.unit
class TestRAGMetricsUnitTests:
    """Unit tests for RAG metrics computation."""
    
    def test_metrics_statistical_validity_minimum_samples(self):
        """RED: Test minimum sample size for statistical validity."""
        # According to design.md, minimum sample_size = 3 for statistical validity
        from services.algorag.main import _build_rag_metrics
        from services.algorag.models import SimilarSetup
        
        # Test with less than 3 samples
        setups = [
            SimilarSetup(
                trade_id="TRD-001",
                timestamp=datetime(2024, 3, 15, tzinfo=timezone.utc),
                instrument="EURUSD",
                time_window="LONDON_KILLZONE",
                htf_open_bias="BULLISH",
                confluence_count=3,
                outcome_result="WIN",
                outcome_r_multiple=2.0,
                narrative="Test",
                similarity_score=0.9,
                final_score=0.9,
            )
        ]
        
        metrics = _build_rag_metrics(setups)
        assert metrics.sample_size == 1
        # With sample_size < 3, metrics may be less reliable
        # but still computed for system functionality

    def test_metrics_win_rate_calculation_accuracy(self):
        """RED: Test win rate calculation is accurate."""
        from services.algorag.main import _build_rag_metrics
        from services.algorag.models import SimilarSetup
        
        # Test with known win/loss ratio
        setups = []
        # 3 wins
        for i in range(3):
            setups.append(SimilarSetup(
                trade_id=f"WIN-{i}",
                timestamp=datetime(2024, 3, i+1, tzinfo=timezone.utc),
                instrument="EURUSD",
                time_window="LONDON_KILLZONE",
                htf_open_bias="BULLISH",
                confluence_count=3,
                outcome_result="WIN",
                outcome_r_multiple=2.0,
                narrative="Win setup",
                similarity_score=0.9,
                final_score=0.9,
            ))
        
        # 2 losses 
        for i in range(2):
            setups.append(SimilarSetup(
                trade_id=f"LOSS-{i}",
                timestamp=datetime(2024, 3, i+10, tzinfo=timezone.utc),
                instrument="EURUSD", 
                time_window="NY_KILLZONE",
                htf_open_bias="BEARISH",
                confluence_count=2,
                outcome_result="LOSS",
                outcome_r_multiple=-1.0,
                narrative="Loss setup",
                similarity_score=0.8,
                final_score=0.8,
            ))
        
        metrics = _build_rag_metrics(setups)
        
        # Win rate should be exactly 3/5 = 0.6
        assert metrics.win_rate_similar == 0.6
        assert metrics.sample_size == 5

    def test_metrics_r_multiple_calculation(self):
        """RED: Test R-multiple average calculation includes losses."""
        from services.algorag.main import _build_rag_metrics
        from services.algorag.models import SimilarSetup
        
        setups = [
            # Big win
            SimilarSetup(
                trade_id="TRD-001",
                timestamp=datetime(2024, 3, 1, tzinfo=timezone.utc),
                instrument="EURUSD",
                time_window="LONDON_KILLZONE",
                htf_open_bias="BULLISH", 
                confluence_count=5,
                outcome_result="WIN",
                outcome_r_multiple=6.0,
                narrative="Big win",
                similarity_score=0.95,
                final_score=0.95,
            ),
            # Small win
            SimilarSetup(
                trade_id="TRD-002", 
                timestamp=datetime(2024, 3, 2, tzinfo=timezone.utc),
                instrument="EURUSD",
                time_window="NY_KILLZONE",
                htf_open_bias="BULLISH",
                confluence_count=3,
                outcome_result="WIN", 
                outcome_r_multiple=1.0,
                narrative="Small win",
                similarity_score=0.87,
                final_score=0.87,
            ),
            # Loss
            SimilarSetup(
                trade_id="TRD-003",
                timestamp=datetime(2024, 3, 3, tzinfo=timezone.utc),
                instrument="EURUSD",
                time_window="LONDON_KILLZONE", 
                htf_open_bias="BEARISH",
                confluence_count=2,
                outcome_result="LOSS",
                outcome_r_multiple=-1.0,
                narrative="Loss",
                similarity_score=0.80,
                final_score=0.80,
            ),
        ]
        
        metrics = _build_rag_metrics(setups)
        
        # Average R = (6.0 + 1.0 - 1.0) / 3 = 2.0
        expected_avg_r = 2.0
        assert abs(metrics.avg_r_multiple_similar - expected_avg_r) < 0.01