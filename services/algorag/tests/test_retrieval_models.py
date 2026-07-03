"""
Test retrieval request/response models for AlgoRAG service.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from services.algorag.models import (
    RAGMetrics,
    RetrievalRequest,
    RetrievalResponse,
    SimilarSetup,
)


class TestRetrievalRequest:
    """Tests for RetrievalRequest Pydantic model."""

    def test_minimal_request(self):
        """Test creating a minimal retrieval request with required fields only."""
        request = RetrievalRequest(
            instrument="EURUSD",
            timestamp=datetime.now(timezone.utc),
        )
        
        assert request.instrument == "EURUSD"
        assert isinstance(request.timestamp, datetime)
        assert request.time_window is None
        assert request.htf_open_bias is None
        assert request.narrative is None
        assert request.htf_structure is None
        assert request.pd_arrays is None
        assert request.confluence_factors is None
        assert request.top_k == 10  # default
        assert request.outcome_filter == "WIN"  # default

    def test_full_request(self):
        """Test creating a complete retrieval request with all fields."""
        request = RetrievalRequest(
            instrument="gbpusd",  # should be converted to uppercase
            timestamp=datetime(2024, 3, 15, 9, 15, 0, tzinfo=timezone.utc),
            time_window="LONDON_KILLZONE",
            htf_open_bias="BULLISH",
            narrative="Price swept Asian low and respects premium array",
            htf_structure={"htf_high": 1.2650, "htf_low": 1.2600, "htf_open": 1.2620},
            pd_arrays={"fvg_present": True, "liquidity_sweep": True},
            confluence_factors=["HTF_ALIGNMENT", "PREMIUM_DISCOUNT", "KILLZONE"],
            top_k=15,
            outcome_filter="LOSS",
        )
        
        assert request.instrument == "GBPUSD"  # should be uppercase
        assert request.time_window == "LONDON_KILLZONE"
        assert request.htf_open_bias == "BULLISH"
        assert len(request.confluence_factors) == 3
        assert request.top_k == 15
        assert request.outcome_filter == "LOSS"

    def test_instrument_validation(self):
        """Test instrument is converted to uppercase."""
        request = RetrievalRequest(
            instrument="xauusd",
            timestamp=datetime.now(timezone.utc),
        )
        assert request.instrument == "XAUUSD"

    def test_top_k_validation(self):
        """Test top_k field validation."""
        # Valid range
        request = RetrievalRequest(
            instrument="EURUSD",
            timestamp=datetime.now(timezone.utc),
            top_k=25,
        )
        assert request.top_k == 25

        # Invalid range - too low
        with pytest.raises(ValueError, match="Input should be greater than or equal to 1"):
            RetrievalRequest(
                instrument="EURUSD",
                timestamp=datetime.now(timezone.utc),
                top_k=0,
            )

        # Invalid range - too high
        with pytest.raises(ValueError, match="Input should be less than or equal to 50"):
            RetrievalRequest(
                instrument="EURUSD",
                timestamp=datetime.now(timezone.utc),
                top_k=51,
            )


class TestSimilarSetup:
    """Tests for SimilarSetup model."""

    def test_valid_similar_setup(self):
        """Test creating a valid similar setup."""
        setup = SimilarSetup(
            trade_id="TRD-001",
            timestamp=datetime(2024, 3, 15, 9, 15, 0, tzinfo=timezone.utc),
            instrument="EURUSD",
            time_window="LONDON_KILLZONE",
            htf_open_bias="BULLISH",
            confluence_count=5,
            outcome_result="WIN",
            outcome_r_multiple=3.2,
            narrative="Strong bullish setup with HTF alignment",
            similarity_score=0.94,
            final_score=0.92,
        )
        
        assert setup.trade_id == "TRD-001"
        assert setup.confluence_count == 5
        assert setup.outcome_result == "WIN"
        assert setup.outcome_r_multiple == 3.2
        assert setup.similarity_score == 0.94
        assert setup.final_score == 0.92

    def test_similarity_score_bounds(self):
        """Test similarity_score is bounded between 0 and 1."""
        # Valid scores
        setup = SimilarSetup(
            trade_id="TRD-001",
            timestamp=datetime.now(timezone.utc),
            instrument="EURUSD",
            time_window="LONDON_KILLZONE",
            htf_open_bias="BULLISH",
            confluence_count=3,
            outcome_result="WIN",
            outcome_r_multiple=2.1,
            narrative="Test setup",
            similarity_score=0.85,
            final_score=0.80,
        )
        assert setup.similarity_score == 0.85

        # Invalid - too low
        with pytest.raises(ValueError, match="Input should be greater than or equal to 0"):
            SimilarSetup(
                trade_id="TRD-001",
                timestamp=datetime.now(timezone.utc),
                instrument="EURUSD",
                time_window="LONDON_KILLZONE",
                htf_open_bias="BULLISH",
                confluence_count=3,
                outcome_result="WIN",
                outcome_r_multiple=2.1,
                narrative="Test setup",
                similarity_score=-0.1,
                final_score=0.80,
            )

        # Invalid - too high
        with pytest.raises(ValueError, match="Input should be less than or equal to 1"):
            SimilarSetup(
                trade_id="TRD-001",
                timestamp=datetime.now(timezone.utc),
                instrument="EURUSD",
                time_window="LONDON_KILLZONE",
                htf_open_bias="BULLISH",
                confluence_count=3,
                outcome_result="WIN",
                outcome_r_multiple=2.1,
                narrative="Test setup",
                similarity_score=1.1,
                final_score=0.80,
            )


class TestRAGMetrics:
    """Tests for RAGMetrics model."""

    def test_valid_rag_metrics(self):
        """Test creating valid RAG metrics."""
        metrics = RAGMetrics(
            avg_r_multiple_similar=2.8,
            win_rate_similar=0.75,
            sample_size=4,
            max_similarity_score=0.94,
            avg_confluence_count=4.5,
        )
        
        assert metrics.avg_r_multiple_similar == 2.8
        assert metrics.win_rate_similar == 0.75
        assert metrics.sample_size == 4
        assert metrics.max_similarity_score == 0.94
        assert metrics.avg_confluence_count == 4.5

    def test_win_rate_bounds(self):
        """Test win_rate_similar is bounded between 0 and 1."""
        # Valid win rates
        metrics = RAGMetrics(
            avg_r_multiple_similar=2.0,
            win_rate_similar=0.0,  # all losses
            sample_size=3,
            max_similarity_score=0.8,
            avg_confluence_count=3.0,
        )
        assert metrics.win_rate_similar == 0.0

        metrics = RAGMetrics(
            avg_r_multiple_similar=3.0,
            win_rate_similar=1.0,  # all wins
            sample_size=3,
            max_similarity_score=0.9,
            avg_confluence_count=4.0,
        )
        assert metrics.win_rate_similar == 1.0

        # Invalid - too low
        with pytest.raises(ValueError, match="Input should be greater than or equal to 0"):
            RAGMetrics(
                avg_r_multiple_similar=2.0,
                win_rate_similar=-0.1,
                sample_size=3,
                max_similarity_score=0.8,
                avg_confluence_count=3.0,
            )

        # Invalid - too high
        with pytest.raises(ValueError, match="Input should be less than or equal to 1"):
            RAGMetrics(
                avg_r_multiple_similar=2.0,
                win_rate_similar=1.1,
                sample_size=3,
                max_similarity_score=0.8,
                avg_confluence_count=3.0,
            )

    def test_sample_size_validation(self):
        """Test sample_size must be non-negative."""
        # Valid sample size
        metrics = RAGMetrics(
            avg_r_multiple_similar=2.0,
            win_rate_similar=0.6,
            sample_size=0,  # empty result set
            max_similarity_score=0.0,
            avg_confluence_count=0.0,
        )
        assert metrics.sample_size == 0

        # Invalid - negative
        with pytest.raises(ValueError, match="Input should be greater than or equal to 0"):
            RAGMetrics(
                avg_r_multiple_similar=2.0,
                win_rate_similar=0.6,
                sample_size=-1,
                max_similarity_score=0.8,
                avg_confluence_count=3.0,
            )


class TestRetrievalResponse:
    """Tests for RetrievalResponse model."""

    def test_empty_response(self):
        """Test creating an empty retrieval response."""
        response = RetrievalResponse(
            similar_setups=[],
            rag_metrics=RAGMetrics(
                avg_r_multiple_similar=0.0,
                win_rate_similar=0.0,
                sample_size=0,
                max_similarity_score=0.0,
                avg_confluence_count=0.0,
            ),
            query_time_ms=45.2,
        )
        
        assert len(response.similar_setups) == 0
        assert response.rag_metrics.sample_size == 0
        assert response.query_time_ms == 45.2

    def test_full_response(self):
        """Test creating a complete retrieval response."""
        similar_setups = [
            SimilarSetup(
                trade_id="TRD-001",
                timestamp=datetime(2024, 3, 15, 9, 15, 0, tzinfo=timezone.utc),
                instrument="EURUSD",
                time_window="LONDON_KILLZONE",
                htf_open_bias="BULLISH",
                confluence_count=5,
                outcome_result="WIN",
                outcome_r_multiple=3.2,
                narrative="Strong bullish setup",
                similarity_score=0.94,
                final_score=0.92,
            ),
            SimilarSetup(
                trade_id="TRD-002",
                timestamp=datetime(2024, 3, 10, 14, 30, 0, tzinfo=timezone.utc),
                instrument="EURUSD",
                time_window="NY_KILLZONE",
                htf_open_bias="BULLISH",
                confluence_count=4,
                outcome_result="WIN",
                outcome_r_multiple=2.1,
                narrative="Premium discount play",
                similarity_score=0.87,
                final_score=0.85,
            ),
        ]
        
        response = RetrievalResponse(
            similar_setups=similar_setups,
            rag_metrics=RAGMetrics(
                avg_r_multiple_similar=2.65,
                win_rate_similar=1.0,
                sample_size=2,
                max_similarity_score=0.94,
                avg_confluence_count=4.5,
            ),
            query_time_ms=67.3,
        )
        
        assert len(response.similar_setups) == 2
        assert response.rag_metrics.sample_size == 2
        assert response.rag_metrics.win_rate_similar == 1.0
        assert response.query_time_ms == 67.3

    def test_query_time_validation(self):
        """Test query_time_ms must be non-negative."""
        # Valid query time
        response = RetrievalResponse(
            similar_setups=[],
            rag_metrics=RAGMetrics(
                avg_r_multiple_similar=0.0,
                win_rate_similar=0.0,
                sample_size=0,
                max_similarity_score=0.0,
                avg_confluence_count=0.0,
            ),
            query_time_ms=0.0,
        )
        assert response.query_time_ms == 0.0

        # Invalid - negative
        with pytest.raises(ValueError, match="Input should be greater than or equal to 0"):
            RetrievalResponse(
                similar_setups=[],
                rag_metrics=RAGMetrics(
                    avg_r_multiple_similar=0.0,
                    win_rate_similar=0.0,
                    sample_size=0,
                    max_similarity_score=0.0,
                    avg_confluence_count=0.0,
                ),
                query_time_ms=-1.0,
            )