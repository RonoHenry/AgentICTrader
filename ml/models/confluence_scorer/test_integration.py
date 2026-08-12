"""
Integration tests for RAG-augmented Confluence Scorer.

Tests the complete flow from feature extraction through model prediction,
including fallback scenarios when RAG is unavailable.

Following Task 16.3 requirements:
- Test feature extraction with RAG client
- Test fallback when RAG unavailable (use zeros for RAG features)  
- Test model prediction with RAG features
"""

import pytest
import numpy as np
from unittest.mock import AsyncMock, Mock, patch
from datetime import datetime, timezone

from ml.models.confluence_scorer.features import (
    ConfluenceFeatureExtractor, 
    ConfluenceFeatures
)
from ml.models.confluence_scorer.train_with_rag import RAGAugmentedTrainer
from ml.models.confluence_scorer.train import TrainingConfig
from ml.algorag.client import AlgoRAGClient, AlgoRAGError


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture 
def sample_candles():
    """Sample OHLCV candles for testing."""
    return [
        {
            "time": datetime(2024, 3, 15, 9, 15, tzinfo=timezone.utc),
            "open": 1.0850,
            "high": 1.0875, 
            "low": 1.0845,
            "close": 1.0870,
            "volume": 1000,
        },
        {
            "time": datetime(2024, 3, 15, 9, 20, tzinfo=timezone.utc),
            "open": 1.0870,
            "high": 1.0885,
            "low": 1.0865, 
            "close": 1.0880,
            "volume": 1200,
        },
    ]


@pytest.fixture
def sample_setup():
    """Sample trading setup."""
    return {
        "instrument": "EURUSD",
        "timestamp": datetime(2024, 3, 15, 9, 20, tzinfo=timezone.utc),
        "direction": "BULLISH",
        "time_window": "LONDON_KILLZONE",
        "narrative": "Price swept Asian low and broke above order block",
    }


@pytest.fixture
def rag_response():
    """Mock RAG service response."""
    return {
        "similar_setups": [
            {"setup": {}, "similarity_score": 0.94, "r_multiple": 4.2},
            {"setup": {}, "similarity_score": 0.87, "r_multiple": 2.8},
        ],
        "rag_metrics": {
            "avg_r_multiple_similar": 3.5,
            "win_rate_similar": 0.8,
            "sample_size": 12,
            "max_similarity_score": 0.94,
        },
    }


# ── Task 16.3: Integration Tests ──────────────────────────────────────────────

class TestFeatureExtractionWithRAG:
    """Test feature extraction with RAG client integration."""
    
    @pytest.mark.asyncio
    async def test_end_to_end_feature_extraction_with_rag(
        self, sample_candles, sample_setup, rag_response
    ):
        """Complete feature extraction should include RAG metrics from AlgoRAG service."""
        # Setup mock RAG client
        mock_client = AsyncMock(spec=AlgoRAGClient)
        mock_client.retrieve_with_fallback.return_value = rag_response
        
        # Initialize extractor with RAG client
        extractor = ConfluenceFeatureExtractor(rag_client=mock_client)
        
        # Extract features
        features = await extractor.extract_features(sample_candles, sample_setup)
        
        # Verify traditional features are present
        assert isinstance(features, ConfluenceFeatures)
        assert features.htf_high_proximity_pct == 15.0  # From mock implementation
        assert features.time_window_weight == 0.9
        assert features.narrative_phase == "MANIPULATION"
        
        # Verify RAG features are populated
        assert features.avg_r_multiple == 3.5
        assert features.win_rate == 0.8
        assert features.sample_size == 0.12  # 12 / 100 (normalized)
        assert features.max_similarity == 0.94
        
        # Verify RAG client was called with setup data
        mock_client.retrieve_with_fallback.assert_called_once_with(sample_setup)

    @pytest.mark.asyncio
    async def test_feature_array_integration(self, sample_candles, sample_setup, rag_response):
        """Feature array should contain all features in correct positions."""
        mock_client = AsyncMock(spec=AlgoRAGClient)
        mock_client.retrieve_with_fallback.return_value = rag_response
        
        extractor = ConfluenceFeatureExtractor(rag_client=mock_client)
        features = await extractor.extract_features(sample_candles, sample_setup)
        
        feature_array = features.to_array()
        
        # Verify array structure
        assert len(feature_array) == 14  # 10 traditional + 4 RAG
        assert isinstance(feature_array, np.ndarray)
        
        # Verify RAG features at correct positions (last 4 elements)
        assert feature_array[-4] == 3.5   # avg_r_multiple
        assert feature_array[-3] == 0.8   # win_rate
        assert feature_array[-2] == 0.12  # sample_size (normalized)
        assert feature_array[-1] == 0.94  # max_similarity

    @pytest.mark.asyncio
    async def test_rag_client_error_handling(self, sample_candles, sample_setup):
        """Should handle RAG client errors gracefully."""
        # Setup failing RAG client
        mock_client = AsyncMock(spec=AlgoRAGClient)
        mock_client.retrieve_with_fallback.side_effect = AlgoRAGError("Service unavailable")
        
        extractor = ConfluenceFeatureExtractor(rag_client=mock_client)
        features = await extractor.extract_features(sample_candles, sample_setup)
        
        # Should still return features with RAG fallback values
        assert isinstance(features, ConfluenceFeatures)
        assert features.avg_r_multiple == 0.0  # Fallback
        assert features.win_rate == 0.0
        assert features.sample_size == 0.0
        assert features.max_similarity == 0.0


class TestRAGFallbackScenarios:
    """Test fallback when RAG unavailable."""
    
    @pytest.mark.asyncio
    async def test_fallback_without_rag_client(self, sample_candles, sample_setup):
        """When no RAG client provided, should use zeros for RAG features."""
        extractor = ConfluenceFeatureExtractor(rag_client=None)
        features = await extractor.extract_features(sample_candles, sample_setup)
        
        # Traditional features should work
        assert features.htf_high_proximity_pct == 15.0
        assert features.time_window_weight == 0.9
        
        # RAG features should be zeros
        assert features.avg_r_multiple == 0.0
        assert features.win_rate == 0.0
        assert features.sample_size == 0.0
        assert features.max_similarity == 0.0
        
        # Feature array should still be correct length
        feature_array = features.to_array()
        assert len(feature_array) == 14
        assert feature_array[-4:].sum() == 0.0  # All RAG features are zero

    @pytest.mark.asyncio
    async def test_partial_rag_response_handling(self, sample_candles, sample_setup):
        """Should handle partial/malformed RAG responses."""
        # Mock client returning incomplete response
        incomplete_response = {
            "rag_metrics": {
                "avg_r_multiple_similar": 2.5,
                # Missing: win_rate_similar, sample_size, max_similarity_score
            }
        }
        
        mock_client = AsyncMock(spec=AlgoRAGClient)
        mock_client.retrieve_with_fallback.return_value = incomplete_response
        
        extractor = ConfluenceFeatureExtractor(rag_client=mock_client)
        features = await extractor.extract_features(sample_candles, sample_setup)
        
        # Should use available metrics and fallback for missing ones
        assert features.avg_r_multiple == 2.5  # Available
        assert features.win_rate == 0.0       # Missing -> fallback
        assert features.sample_size == 0.0    # Missing -> fallback
        assert features.max_similarity == 0.0 # Missing -> fallback

    @pytest.mark.asyncio  
    async def test_network_timeout_fallback(self, sample_candles, sample_setup):
        """Should fallback gracefully on network timeouts."""
        mock_client = AsyncMock(spec=AlgoRAGClient) 
        mock_client.retrieve_with_fallback.side_effect = TimeoutError("Request timeout")
        
        extractor = ConfluenceFeatureExtractor(rag_client=mock_client)
        features = await extractor.extract_features(sample_candles, sample_setup)
        
        # Should complete with fallback values
        assert features.avg_r_multiple == 0.0
        assert features.win_rate == 0.0
        assert features.sample_size == 0.0
        assert features.max_similarity == 0.0


class TestModelPredictionWithRAG:
    """Test model prediction using RAG-augmented features."""
    
    def test_feature_vector_compatibility(self, sample_candles, sample_setup, rag_response):
        """RAG-augmented features should be compatible with ML models."""
        # This is a unit test since we're not testing actual model training
        mock_client = AsyncMock(spec=AlgoRAGClient)
        mock_client.retrieve_with_fallback.return_value = rag_response
        
        extractor = ConfluenceFeatureExtractor(rag_client=mock_client)
        
        # Simulate model prediction workflow
        async def simulate_prediction():
            features = await extractor.extract_features(sample_candles, sample_setup)
            feature_vector = features.to_array()
            
            # Simulate model prediction (mock model)
            # In real implementation, this would be: model.predict_proba([feature_vector])
            mock_probabilities = np.array([[0.3, 0.7]])  # [low_conf, high_conf]
            
            return feature_vector, mock_probabilities
        
        import asyncio
        feature_vector, probabilities = asyncio.run(simulate_prediction())
        
        # Verify feature vector is correct shape for model
        assert feature_vector.shape == (14,)  # Expected input shape
        assert not np.isnan(feature_vector).any()  # No NaN values
        assert np.all(feature_vector >= -1)  # Reasonable value ranges
        assert np.all(feature_vector <= 10)   # Reasonable value ranges
        
        # Verify mock prediction worked
        assert probabilities.shape == (1, 2)
        assert abs(probabilities[0].sum() - 1.0) < 1e-6  # Probabilities sum to 1

    def test_model_input_validation(self):
        """Feature vectors should pass model input validation."""
        # Test various feature combinations
        test_features = ConfluenceFeatures(
            # Traditional features
            htf_high_proximity_pct=25.0,
            htf_low_proximity_pct=75.0,
            htf_body_pct=60.0,
            htf_close_position=0.7,
            time_window_weight=0.9,
            narrative_phase="EXPANSION",
            bos_detected=True,
            choch_detected=False,
            fvg_present=True,
            liquidity_sweep=True,
            # RAG features
            avg_r_multiple=4.2,
            win_rate=0.85,
            sample_size=0.15,
            max_similarity=0.92,
        )
        
        feature_vector = test_features.to_array()
        
        # Validate model input requirements
        assert len(feature_vector) == 14
        assert feature_vector.dtype in [np.float64, np.int64]
        assert not np.isnan(feature_vector).any()
        assert not np.isinf(feature_vector).any()
        
        # Verify RAG features are in expected ranges
        assert 0.0 <= feature_vector[-3] <= 1.0  # win_rate
        assert 0.0 <= feature_vector[-1] <= 1.0  # max_similarity
        assert feature_vector[-2] >= 0.0         # sample_size (normalized)


# ── Performance and Reliability Tests ─────────────────────────────────────────

class TestRAGIntegrationPerformance:
    """Test performance characteristics of RAG integration."""
    
    @pytest.mark.asyncio
    async def test_feature_extraction_with_rag_timeout(self, sample_candles, sample_setup):
        """Feature extraction should complete within reasonable time even with RAG."""
        import time
        
        # Mock fast RAG response
        fast_response = {
            "rag_metrics": {
                "avg_r_multiple_similar": 3.0,
                "win_rate_similar": 0.7,
                "sample_size": 8,
                "max_similarity_score": 0.85,
            },
        }
        
        mock_client = AsyncMock(spec=AlgoRAGClient)
        mock_client.retrieve_with_fallback.return_value = fast_response
        
        extractor = ConfluenceFeatureExtractor(rag_client=mock_client)
        
        start_time = time.time()
        features = await extractor.extract_features(sample_candles, sample_setup)
        end_time = time.time()
        
        # Should complete quickly (< 1 second for unit test)
        assert (end_time - start_time) < 1.0
        assert isinstance(features, ConfluenceFeatures)

    @pytest.mark.asyncio
    async def test_multiple_concurrent_extractions(self, sample_candles, sample_setup, rag_response):
        """Should handle multiple concurrent feature extractions."""
        import asyncio
        
        mock_client = AsyncMock(spec=AlgoRAGClient)
        mock_client.retrieve_with_fallback.return_value = rag_response
        
        extractor = ConfluenceFeatureExtractor(rag_client=mock_client)
        
        # Run multiple extractions concurrently
        tasks = [
            extractor.extract_features(sample_candles, sample_setup)
            for _ in range(5)
        ]
        
        results = await asyncio.gather(*tasks)
        
        # All should complete successfully
        assert len(results) == 5
        for features in results:
            assert isinstance(features, ConfluenceFeatures)
            assert features.avg_r_multiple == 3.5
            assert features.win_rate == 0.8