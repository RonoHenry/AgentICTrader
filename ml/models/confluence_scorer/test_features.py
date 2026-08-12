"""
Tests for Confluence Scorer feature extraction with RAG integration.

Following TDD methodology: RED → GREEN → REFACTOR
"""
from __future__ import annotations

import asyncio
import pytest
import numpy as np
from datetime import datetime, timezone
from unittest.mock import Mock, AsyncMock, patch
from typing import List, Dict, Any

from ml.models.confluence_scorer.features import (
    ConfluenceFeatures,
    ConfluenceFeatureExtractor,
)
from ml.algorag.client import AlgoRAGClient


@pytest.fixture
def sample_candles():
    """Sample candle data for testing."""
    return [
        {
            "time": "2024-01-01T08:00:00Z",
            "open": 1.5000,
            "high": 1.5100,
            "low": 1.4900,
            "close": 1.5080,
            "volume": 1000,
        },
        {
            "time": "2024-01-01T08:05:00Z",
            "open": 1.5080,
            "high": 1.5120,
            "low": 1.5060,
            "close": 1.5110,
            "volume": 1200,
        },
        {
            "time": "2024-01-01T08:10:00Z",
            "open": 1.5110,
            "high": 1.5150,
            "low": 1.5090,
            "close": 1.5140,
            "volume": 800,
        },
    ]


@pytest.fixture
def sample_setup_data():
    """Sample setup data for testing."""
    return {
        "instrument": "EURUSD",
        "timestamp": datetime(2024, 1, 1, 8, 10, tzinfo=timezone.utc),
        "direction": "LONG",
        "entry_price": 1.5140,
        "timeframe": "M5",
        "htf_timeframe": "H1",
        "current_price": 1.5140,
    }


@pytest.fixture
def mock_rag_client():
    """Mock RAG client for testing."""
    client = Mock(spec=AlgoRAGClient)
    client.retrieve_with_fallback = AsyncMock(return_value={
        "similar_setups": [],
        "rag_metrics": {
            "avg_r_multiple_similar": 2.5,
            "win_rate_similar": 0.75,
            "sample_size": 10,
            "max_similarity_score": 0.85,
        },
        "query_time_ms": 45.0
    })
    return client


class TestConfluenceFeatures:
    """Test the ConfluenceFeatures dataclass."""
    
    def test_to_array_shape(self):
        """Test that to_array returns correct shape (14 features)."""
        features = ConfluenceFeatures(
            htf_high_proximity_pct=15.0,
            htf_low_proximity_pct=85.0,
            htf_body_pct=65.0,
            htf_close_position=0.8,
            time_window_weight=0.9,
            narrative_phase="MANIPULATION",
            bos_detected=True,
            choch_detected=False,
            fvg_present=True,
            liquidity_sweep=False,
            # RAG features
            avg_r_multiple=2.5,
            win_rate=0.75,
            sample_size=0.1,  # normalized (10/100)
            max_similarity=0.85,
        )
        
        array = features.to_array()
        assert array.shape == (14,), f"Expected 14 features, got {array.shape}"
        assert isinstance(array, np.ndarray)
    
    def test_to_array_values(self):
        """Test that to_array maps values correctly."""
        features = ConfluenceFeatures(
            htf_high_proximity_pct=15.0,
            htf_low_proximity_pct=85.0,
            htf_body_pct=65.0,
            htf_close_position=0.8,
            time_window_weight=0.9,
            narrative_phase="MANIPULATION",
            bos_detected=True,
            choch_detected=False,
            fvg_present=True,
            liquidity_sweep=False,
            # RAG features
            avg_r_multiple=2.5,
            win_rate=0.75,
            sample_size=0.1,
            max_similarity=0.85,
        )
        
        array = features.to_array()
        
        # Test traditional features
        assert array[0] == 15.0  # htf_high_proximity_pct
        assert array[1] == 85.0  # htf_low_proximity_pct
        assert array[2] == 65.0  # htf_body_pct
        assert array[3] == 0.8   # htf_close_position
        assert array[4] == 0.9   # time_window_weight
        assert array[5] == 1     # narrative_phase (MANIPULATION = 1)
        assert array[6] == 1     # bos_detected (True = 1)
        assert array[7] == 0     # choch_detected (False = 0)
        assert array[8] == 1     # fvg_present (True = 1)
        assert array[9] == 0     # liquidity_sweep (False = 0)
        
        # Test RAG features
        assert array[10] == 2.5  # avg_r_multiple
        assert array[11] == 0.75 # win_rate
        assert array[12] == 0.1  # sample_size (normalized)
        assert array[13] == 0.85 # max_similarity
    
    def test_narrative_phase_mapping(self):
        """Test narrative phase categorical mapping."""
        test_cases = [
            ("ACCUMULATION", 0),
            ("MANIPULATION", 1),
            ("EXPANSION", 2),
            ("DISTRIBUTION", 3),
            ("TRANSITION", 4),
            ("OFF", 5),
            ("UNKNOWN", 5),  # Default to OFF
        ]
        
        for phase, expected_value in test_cases:
            features = ConfluenceFeatures(
                htf_high_proximity_pct=0,
                htf_low_proximity_pct=0,
                htf_body_pct=0,
                htf_close_position=0,
                time_window_weight=0,
                narrative_phase=phase,
                bos_detected=False,
                choch_detected=False,
                fvg_present=False,
                liquidity_sweep=False,
            )
            array = features.to_array()
            assert array[5] == expected_value, f"Expected {expected_value} for {phase}, got {array[5]}"


class TestConfluenceFeatureExtractor:
    """Test the ConfluenceFeatureExtractor class."""
    
    def test_init_without_rag_client(self):
        """Test initialization without RAG client."""
        extractor = ConfluenceFeatureExtractor()
        assert extractor.rag_client is None
    
    def test_init_with_rag_client(self, mock_rag_client):
        """Test initialization with RAG client."""
        extractor = ConfluenceFeatureExtractor(rag_client=mock_rag_client)
        assert extractor.rag_client is mock_rag_client
    
    @pytest.mark.asyncio
    async def test_extract_features_without_rag(self, sample_candles, sample_setup_data):
        """Test feature extraction without RAG client (graceful degradation)."""
        extractor = ConfluenceFeatureExtractor()
        
        # Mock the traditional feature extractors
        with patch.object(extractor, '_extract_traditional_features') as mock_traditional:
            mock_traditional.return_value = {
                "htf_high_proximity_pct": 20.0,
                "htf_low_proximity_pct": 80.0,
                "htf_body_pct": 60.0,
                "htf_close_position": 0.75,
                "time_window_weight": 0.8,
                "narrative_phase": "EXPANSION",
                "bos_detected": True,
                "choch_detected": False,
                "fvg_present": False,
                "liquidity_sweep": True,
            }
            
            features = await extractor.extract_features(sample_candles, sample_setup_data)
            
            # Check traditional features
            assert features.htf_high_proximity_pct == 20.0
            assert features.htf_low_proximity_pct == 80.0
            assert features.narrative_phase == "EXPANSION"
            assert features.bos_detected is True
            assert features.liquidity_sweep is True
            
            # Check RAG features are zeros (graceful degradation)
            assert features.avg_r_multiple == 0.0
            assert features.win_rate == 0.0
            assert features.sample_size == 0.0
            assert features.max_similarity == 0.0
    
    @pytest.mark.asyncio
    async def test_extract_features_with_rag(self, sample_candles, sample_setup_data, mock_rag_client):
        """Test feature extraction with RAG client."""
        extractor = ConfluenceFeatureExtractor(rag_client=mock_rag_client)
        
        # Mock the traditional feature extractors
        with patch.object(extractor, '_extract_traditional_features') as mock_traditional:
            mock_traditional.return_value = {
                "htf_high_proximity_pct": 20.0,
                "htf_low_proximity_pct": 80.0,
                "htf_body_pct": 60.0,
                "htf_close_position": 0.75,
                "time_window_weight": 0.8,
                "narrative_phase": "EXPANSION",
                "bos_detected": True,
                "choch_detected": False,
                "fvg_present": False,
                "liquidity_sweep": True,
            }
            
            features = await extractor.extract_features(sample_candles, sample_setup_data)
            
            # Check traditional features
            assert features.htf_high_proximity_pct == 20.0
            assert features.narrative_phase == "EXPANSION"
            
            # Check RAG features from mock client
            assert features.avg_r_multiple == 2.5
            assert features.win_rate == 0.75
            assert features.sample_size == 0.1  # 10/100 normalized
            assert features.max_similarity == 0.85
            
            # Verify RAG client was called
            mock_rag_client.retrieve_with_fallback.assert_called_once_with(sample_setup_data)
    
    @pytest.mark.asyncio
    async def test_extract_rag_features_graceful_degradation(self, sample_setup_data, mock_rag_client):
        """Test RAG feature extraction graceful degradation on error."""
        # Make RAG client raise an exception
        mock_rag_client.retrieve_with_fallback.side_effect = Exception("RAG unavailable")
        
        extractor = ConfluenceFeatureExtractor(rag_client=mock_rag_client)
        rag_features = await extractor._extract_rag_features(sample_setup_data)
        
        # Should return zeros on error
        assert rag_features == {
            "avg_r_multiple": 0.0,
            "win_rate": 0.0,
            "sample_size": 0.0,
            "max_similarity": 0.0,
        }
    
    def test_extract_traditional_features_integration(self, sample_candles, sample_setup_data):
        """Test traditional feature extraction integrates with existing extractors."""
        extractor = ConfluenceFeatureExtractor()
        
        # This test will fail initially (RED) - we need to implement proper integration
        with patch('ml.features.htf_projections.HTFProjectionExtractor') as MockHTF, \
             patch('ml.features.zone_features.ZoneFeatureExtractor') as MockZone, \
             patch('ml.features.session_features.TimeWindowClassifier') as MockSession:
            
            # Setup mocks for the existing extractors
            mock_htf = Mock()
            mock_htf.compute_projections.return_value = Mock(
                htf_high_proximity_pct=15.0,
                htf_low_proximity_pct=85.0,
                htf_body_pct=65.0,
                htf_close_position=0.8,
            )
            MockHTF.return_value = mock_htf
            
            mock_zone = Mock()
            mock_zone.extract.return_value = Mock(
                bos_detected=True,
                choch_detected=False,
                fvg_present=True,
                liquidity_sweep=False,
            )
            MockZone.return_value = mock_zone
            
            mock_session = Mock()
            mock_session.classify.return_value = Mock(
                time_window_weight=0.9,
                narrative_phase="MANIPULATION",
            )
            MockSession.return_value = mock_session
            
            # This should use real extractors, not placeholder values
            features = extractor._extract_traditional_features(sample_candles, sample_setup_data)
            
            # Assert the extractors were called properly
            MockHTF.assert_called_once()
            MockZone.assert_called_once()
            MockSession.assert_called_once()
            
            # Assert features came from extractors, not placeholder
            assert features["htf_high_proximity_pct"] == 15.0
            assert features["bos_detected"] is True
            assert features["time_window_weight"] == 0.9


class TestRAGFeatureNormalization:
    """Test RAG feature normalization and missing value handling."""
    
    @pytest.mark.asyncio
    async def test_sample_size_normalization(self, sample_setup_data):
        """Test sample_size is normalized by dividing by 100."""
        mock_rag_client = Mock()
        mock_rag_client.retrieve_with_fallback = AsyncMock(return_value={
            "rag_metrics": {
                "avg_r_multiple_similar": 1.0,
                "win_rate_similar": 0.5,
                "sample_size": 25,  # Should become 0.25 after normalization
                "max_similarity_score": 0.5,
            }
        })
        
        extractor = ConfluenceFeatureExtractor(rag_client=mock_rag_client)
        rag_features = await extractor._extract_rag_features(sample_setup_data)
        
        assert rag_features["sample_size"] == 0.25  # 25/100
    
    @pytest.mark.asyncio
    async def test_missing_rag_metrics(self, sample_setup_data):
        """Test handling of missing RAG metrics in response."""
        mock_rag_client = Mock()
        mock_rag_client.retrieve_with_fallback = AsyncMock(return_value={
            "rag_metrics": {
                # Missing some fields
                "avg_r_multiple_similar": 2.0,
                # win_rate_similar missing
                # sample_size missing  
                "max_similarity_score": 0.8,
            }
        })
        
        extractor = ConfluenceFeatureExtractor(rag_client=mock_rag_client)
        rag_features = await extractor._extract_rag_features(sample_setup_data)
        
        # Should use defaults for missing fields
        assert rag_features["avg_r_multiple"] == 2.0
        assert rag_features["win_rate"] == 0.0  # default
        assert rag_features["sample_size"] == 0.0  # default
        assert rag_features["max_similarity"] == 0.8
    
    @pytest.mark.asyncio
    async def test_empty_rag_response(self, sample_setup_data):
        """Test handling of empty RAG response."""
        mock_rag_client = Mock()
        mock_rag_client.retrieve_with_fallback = AsyncMock(return_value={})
        
        extractor = ConfluenceFeatureExtractor(rag_client=mock_rag_client)
        rag_features = await extractor._extract_rag_features(sample_setup_data)
        
        # Should use all defaults
        assert rag_features == {
            "avg_r_multiple": 0.0,
            "win_rate": 0.0,
            "sample_size": 0.0,
            "max_similarity": 0.0,
        }


class TestFeatureNormalizationAndValidation:
    """Test feature normalization and missing value handling."""
    
    @pytest.mark.asyncio
    async def test_feature_bounds_validation(self, sample_candles, sample_setup_data):
        """Test that all features are within expected bounds."""
        extractor = ConfluenceFeatureExtractor()
        
        features = await extractor.extract_features(sample_candles, sample_setup_data)
        feature_array = features.to_array()
        
        # Test bounds for specific features
        assert 0.0 <= features.time_window_weight <= 1.0, "time_window_weight should be [0,1]"
        assert 0.0 <= features.win_rate <= 1.0, "win_rate should be [0,1]"  
        assert 0.0 <= features.sample_size <= 1.0, "sample_size should be normalized [0,1]"
        assert 0.0 <= features.max_similarity <= 1.0, "max_similarity should be [0,1]"
        
        # HTF close position should be [0,1] (percentage within range)
        assert 0.0 <= features.htf_close_position <= 1.0, "htf_close_position should be [0,1]"
        
        # No NaN or infinite values
        assert not np.isnan(feature_array).any(), "No NaN values allowed"
        assert not np.isinf(feature_array).any(), "No infinite values allowed"
    
    @pytest.mark.asyncio
    async def test_missing_setup_data_handling(self, sample_candles):
        """Test handling of missing setup data fields."""
        incomplete_setup = {
            "instrument": "EURUSD",  # Missing other fields
        }
        
        extractor = ConfluenceFeatureExtractor()
        
        # Should not crash and should use reasonable defaults
        features = await extractor.extract_features(sample_candles, incomplete_setup)
        
        assert isinstance(features, ConfluenceFeatures)
        feature_array = features.to_array()
        assert not np.isnan(feature_array).any()
    
    @pytest.mark.asyncio
    async def test_empty_candles_handling(self, sample_setup_data):
        """Test handling of empty candles list."""
        extractor = ConfluenceFeatureExtractor()
        
        # Should use fallback values and not crash
        features = await extractor.extract_features([], sample_setup_data)
        
        assert isinstance(features, ConfluenceFeatures)
        feature_array = features.to_array()
        assert not np.isnan(feature_array).any()
    
    @pytest.mark.asyncio 
    async def test_extreme_price_values(self, sample_setup_data):
        """Test handling of extreme price values."""
        extreme_candles = [
            {
                "time": "2024-01-01T08:00:00Z",
                "open": 0.00001,  # Very small
                "high": 0.00002,
                "low": 0.000005,
                "close": 0.000015,
                "volume": 1000,
            },
            {
                "time": "2024-01-01T08:05:00Z", 
                "open": 999999.0,  # Very large
                "high": 1000000.0,
                "low": 999998.0,
                "close": 999999.5,
                "volume": 1000,
            },
        ]
        
        extractor = ConfluenceFeatureExtractor()
        features = await extractor.extract_features(extreme_candles, sample_setup_data)
        
        # Should handle extreme values gracefully
        feature_array = features.to_array()
        assert not np.isnan(feature_array).any()
        assert not np.isinf(feature_array).any()


@pytest.mark.integration
class TestConfluenceFeatureExtractorIntegration:
    """Integration tests requiring real extractors."""
    
    @pytest.mark.asyncio
    async def test_end_to_end_feature_extraction(self, sample_candles, sample_setup_data, mock_rag_client):
        """Test end-to-end feature extraction with real extractor instances."""
        extractor = ConfluenceFeatureExtractor(rag_client=mock_rag_client)
        
        # This test should pass after we implement proper traditional feature integration
        features = await extractor.extract_features(sample_candles, sample_setup_data)
        
        # Verify we get a complete ConfluenceFeatures object
        assert isinstance(features, ConfluenceFeatures)
        
        # Verify array conversion works
        feature_array = features.to_array()
        assert feature_array.shape == (14,)
        
        # Verify no NaN values
        assert not np.isnan(feature_array).any()
        
        # Verify RAG features are included
        assert feature_array[10] == 2.5   # avg_r_multiple
        assert feature_array[11] == 0.75  # win_rate
        assert feature_array[12] == 0.1   # sample_size (normalized)
        assert feature_array[13] == 0.85  # max_similarity


@pytest.mark.property
class TestConfluenceFeatureProperties:
    """Property-based tests using Hypothesis."""
    
    @pytest.mark.asyncio
    async def test_feature_array_always_14_elements(self, sample_candles, sample_setup_data):
        """Property: feature array should always have exactly 14 elements."""
        extractor = ConfluenceFeatureExtractor()
        
        # Test with different setup variations
        for i in range(5):
            modified_setup = sample_setup_data.copy()
            modified_setup["current_price"] = 1.0 + (i * 0.01)  # Vary price
            
            features = await extractor.extract_features(sample_candles, modified_setup)
            array = features.to_array()
            
            assert array.shape == (14,), f"Iteration {i}: Expected 14 features, got {array.shape}"
            assert len(array) == 14, f"Iteration {i}: Array length mismatch"
    
    @pytest.mark.asyncio
    async def test_rag_features_bounds_invariant(self, sample_candles, sample_setup_data):
        """Property: RAG features should always be within expected bounds."""
        mock_rag_responses = [
            {"rag_metrics": {"avg_r_multiple_similar": 5.0, "win_rate_similar": 0.8, 
                           "sample_size": 50, "max_similarity_score": 0.9}},
            {"rag_metrics": {"avg_r_multiple_similar": -1.0, "win_rate_similar": 1.5,  # Invalid bounds
                           "sample_size": 200, "max_similarity_score": -0.5}},
            {"rag_metrics": {}},  # Empty metrics
            {},  # No rag_metrics key
        ]
        
        for i, response in enumerate(mock_rag_responses):
            mock_client = Mock()
            mock_client.retrieve_with_fallback = AsyncMock(return_value=response)
            
            extractor = ConfluenceFeatureExtractor(rag_client=mock_client)
            features = await extractor.extract_features(sample_candles, sample_setup_data)
            
            # Verify bounds invariant
            assert 0.0 <= features.avg_r_multiple <= 10.0, f"Case {i}: avg_r_multiple out of bounds"
            assert 0.0 <= features.win_rate <= 1.0, f"Case {i}: win_rate out of bounds"
            assert 0.0 <= features.sample_size <= 1.0, f"Case {i}: sample_size out of bounds"
            assert 0.0 <= features.max_similarity <= 1.0, f"Case {i}: max_similarity out of bounds"
    
    @pytest.mark.asyncio
    async def test_deterministic_output_property(self, sample_candles, sample_setup_data):
        """Property: same input should always produce same output."""
        extractor = ConfluenceFeatureExtractor()
        
        # Run extraction multiple times with identical inputs
        results = []
        for _ in range(3):
            features = await extractor.extract_features(sample_candles, sample_setup_data)
            results.append(features.to_array())
        
        # All results should be identical
        for i in range(1, len(results)):
            np.testing.assert_array_equal(
                results[0], results[i], 
                err_msg=f"Results not deterministic: run 0 vs run {i}"
            )
    
    def test_feature_vector_completeness(self):
        """Property: all features should be represented in the feature vector."""
        features = ConfluenceFeatures(
            htf_high_proximity_pct=10.0,
            htf_low_proximity_pct=90.0,
            htf_body_pct=50.0,
            htf_close_position=0.6,
            time_window_weight=0.8,
            narrative_phase="EXPANSION",
            bos_detected=True,
            choch_detected=False,
            fvg_present=True,
            liquidity_sweep=False,
            avg_r_multiple=3.0,
            win_rate=0.7,
            sample_size=0.2,
            max_similarity=0.9,
        )
        
        array = features.to_array()
        
        # Verify each feature is correctly placed
        expected = [
            10.0,    # htf_high_proximity_pct
            90.0,    # htf_low_proximity_pct
            50.0,    # htf_body_pct
            0.6,     # htf_close_position
            0.8,     # time_window_weight
            2,       # narrative_phase (EXPANSION = 2)
            1,       # bos_detected (True = 1)
            0,       # choch_detected (False = 0)
            1,       # fvg_present (True = 1)
            0,       # liquidity_sweep (False = 0)
            3.0,     # avg_r_multiple
            0.7,     # win_rate
            0.2,     # sample_size
            0.9,     # max_similarity
        ]
        
        np.testing.assert_array_equal(array, expected)


class TestEdgeCasesAndErrorHandling:
    """Test edge cases and error handling scenarios."""
    
    @pytest.mark.asyncio
    async def test_malformed_candle_data(self, sample_setup_data):
        """Test handling of malformed candle data."""
        malformed_candles = [
            {"time": "invalid", "open": "not_a_number", "high": None},  # Invalid data types
            {},  # Missing required fields
            {"open": 1.5, "high": 1.4, "low": 1.6, "close": 1.55},  # Invalid OHLC relationship
        ]
        
        extractor = ConfluenceFeatureExtractor()
        
        # Should handle gracefully without crashing
        features = await extractor.extract_features(malformed_candles, sample_setup_data)
        
        assert isinstance(features, ConfluenceFeatures)
        array = features.to_array()
        assert not np.isnan(array).any()
        assert not np.isinf(array).any()
    
    @pytest.mark.asyncio
    async def test_concurrent_feature_extraction(self, sample_candles, sample_setup_data):
        """Test concurrent feature extraction (thread safety)."""
        extractor = ConfluenceFeatureExtractor()
        
        # Run multiple extractions concurrently
        tasks = [
            extractor.extract_features(sample_candles, sample_setup_data)
            for _ in range(5)
        ]
        
        results = await asyncio.gather(*tasks)
        
        # All results should be valid and similar
        for result in results:
            assert isinstance(result, ConfluenceFeatures)
            array = result.to_array()
            assert array.shape == (14,)
            assert not np.isnan(array).any()
    
    @pytest.mark.asyncio
    async def test_rag_client_timeout_handling(self, sample_candles, sample_setup_data):
        """Test handling of RAG client timeouts."""
        mock_client = Mock()
        mock_client.retrieve_with_fallback = AsyncMock(side_effect=asyncio.TimeoutError("Connection timeout"))
        
        extractor = ConfluenceFeatureExtractor(rag_client=mock_client)
        features = await extractor.extract_features(sample_candles, sample_setup_data)
        
        # Should fall back to zero RAG features
        assert features.avg_r_multiple == 0.0
        assert features.win_rate == 0.0
        assert features.sample_size == 0.0
        assert features.max_similarity == 0.0