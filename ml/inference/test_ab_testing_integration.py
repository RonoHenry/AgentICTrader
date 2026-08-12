"""
Integration tests for A/B testing framework.

Tests the complete A/B testing workflow including model versioning,
traffic splitting, feature flags, and metrics collection.
"""
from __future__ import annotations

import os
import sys
from unittest.mock import Mock, patch, MagicMock
import pytest
from typing import Dict, Any, List

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from ml.inference.ab_testing import ABTestingFramework, TrafficSplitter, ModelVersion
from ml.inference.model_versioning import ModelVersionRegistry
from ml.inference.feature_flags import FeatureFlagManager


class TestABTestingIntegration:
    """Integration tests for complete A/B testing framework."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.sample_candles = [
            {
                "time": "2024-01-01T09:00:00Z",
                "open": 1.1000,
                "high": 1.1050,
                "low": 1.0980,
                "close": 1.1020,
                "volume": 1000
            },
            {
                "time": "2024-01-01T09:05:00Z", 
                "open": 1.1020,
                "high": 1.1080,
                "low": 1.1000,
                "close": 1.1060,
                "volume": 1200
            }
        ]
    
    @patch.dict(os.environ, {
        'CONFLUENCE_SCORER_AB_TEST': 'true',
        'CONFLUENCE_SCORER_AB_TEST_ROLLOUT': '100.0'
    })
    def test_complete_ab_testing_workflow(self):
        """RED: Test complete A/B testing workflow from user assignment to metrics."""
        framework = ABTestingFramework(split_ratio=0.5)
        
        with patch.object(framework.model_registry, 'load_model') as mock_load:
            # Mock different models for v1 and v2
            mock_v1_model = Mock()
            mock_v1_model.predict.return_value = [0]
            mock_v1_model.predict_proba.return_value = [[0.6, 0.4]]  # Lower confidence
            
            mock_v2_model = Mock()
            mock_v2_model.predict.return_value = [1] 
            mock_v2_model.predict_proba.return_value = [[0.2, 0.8]]  # Higher confidence
            
            def mock_load_side_effect(model_name, version):
                if version == ModelVersion.V1_BASELINE:
                    return mock_v1_model
                elif version == ModelVersion.V2_RAG:
                    return mock_v2_model
                return None
            
            mock_load.side_effect = mock_load_side_effect
            
            # Test user assignments
            users = ["user_1", "user_2", "user_3", "user_4", "user_5"]
            assignments = {}
            
            for user in users:
                version, model = framework.get_model_for_user(user)
                assignments[user] = version
                
                # Record a mock prediction
                confidence = 0.4 if version == ModelVersion.V1_BASELINE else 0.8
                framework.record_prediction(
                    user_id=user,
                    model_version=version,
                    confidence_score=confidence,
                    outcome="WIN",
                    r_multiple=2.0,
                    metadata={"instrument": "EURUSD", "timeframe": "M5"}
                )
            
            # Verify assignments are consistent 
            for user in users:
                version2, _ = framework.get_model_for_user(user)
                assert assignments[user] == version2, f"User {user} assignment changed"
            
            # Check metrics are collected
            v1_metrics = framework.get_variant_metrics(ModelVersion.V1_BASELINE)
            v2_metrics = framework.get_variant_metrics(ModelVersion.V2_RAG)
            
            # Should have predictions recorded
            total_predictions = v1_metrics["prediction_count"] + v2_metrics["prediction_count"]
            assert total_predictions == len(users)
            
            # V2 should have higher average confidence (if users assigned to it)
            if v2_metrics["prediction_count"] > 0:
                assert v2_metrics["avg_confidence"] > v1_metrics["avg_confidence"]
            
            # Get summary
            summary = framework.get_ab_test_summary()
            assert summary["ab_test_active"] is True
            assert summary["split_ratio"] == 0.5
            assert summary["total_users_assigned"] == len(users)
    
    def test_feature_flag_disables_ab_testing(self):
        """RED: Test that disabled feature flag forces all users to baseline."""
        # Create flag manager and disable the flag
        flag_manager = FeatureFlagManager()
        flag_manager._flags.clear()
        flag_manager.register_flag("confluence_scorer_ab_test", enabled=False)
        
        framework = ABTestingFramework(split_ratio=1.0)  # 100% v2 split
        
        # Patch get_feature_flags to return our disabled flag manager
        with patch('ml.inference.ab_testing.get_feature_flags', return_value=flag_manager):
            with patch.object(framework.model_registry, 'load_model') as mock_load:
                mock_model = Mock()
                mock_load.return_value = mock_model
                
                # All users should get v1 despite 100% v2 split
                for i in range(10):
                    version, model = framework.get_model_for_user(f"user_{i}")
                    assert version == ModelVersion.V1_BASELINE
    
    def test_gradual_rollout_through_feature_flags(self):
        """RED: Test gradual rollout using feature flag percentage."""
        # Create flag manager with 25% rollout
        flag_manager = FeatureFlagManager()
        flag_manager._flags.clear()
        flag_manager.register_flag(
            "confluence_scorer_ab_test", 
            enabled=True, 
            rollout_percentage=25.0
        )
        
        framework = ABTestingFramework(split_ratio=1.0)  # 100% v2 when flag enabled
        
        # Patch get_feature_flags to return our configured flag manager
        with patch('ml.inference.ab_testing.get_feature_flags', return_value=flag_manager):
            with patch.object(framework.model_registry, 'load_model') as mock_load:
                mock_model = Mock()
                mock_load.return_value = mock_model
                
                v1_count = 0
                v2_count = 0
                sample_size = 1000
                
                for i in range(sample_size):
                    version, model = framework.get_model_for_user(f"rollout_user_{i}")
                    if version == ModelVersion.V1_BASELINE:
                        v1_count += 1
                    else:
                        v2_count += 1
                
                # Should be roughly 25% getting A/B test (and thus v2)
                expected_v2 = int(sample_size * 0.25)
                tolerance = int(sample_size * 0.1)  # 10% tolerance
                
                assert expected_v2 - tolerance <= v2_count <= expected_v2 + tolerance
    
    def test_metrics_collection_accuracy(self):
        """RED: Test that metrics are collected accurately for both variants."""
        framework = ABTestingFramework(split_ratio=0.5)
        
        # Clear existing metrics
        framework._variant_metrics[ModelVersion.V1_BASELINE] = framework._variant_metrics[ModelVersion.V1_BASELINE].__class__()
        framework._variant_metrics[ModelVersion.V2_RAG] = framework._variant_metrics[ModelVersion.V2_RAG].__class__()
        
        # Record specific predictions
        test_data = [
            ("user_a", ModelVersion.V1_BASELINE, 0.7, "WIN", 1.5),
            ("user_b", ModelVersion.V1_BASELINE, 0.6, "LOSS", -1.0),
            ("user_c", ModelVersion.V2_RAG, 0.9, "WIN", 3.0),
            ("user_d", ModelVersion.V2_RAG, 0.8, "WIN", 2.0),
        ]
        
        for user_id, version, confidence, outcome, r_multiple in test_data:
            framework.record_prediction(user_id, version, confidence, outcome, r_multiple)
        
        # Verify V1 metrics
        v1_metrics = framework.get_variant_metrics(ModelVersion.V1_BASELINE)
        assert v1_metrics["prediction_count"] == 2
        assert abs(v1_metrics["avg_confidence"] - 0.65) < 1e-10  # (0.7 + 0.6) / 2
        assert v1_metrics["wins"] == 1
        assert v1_metrics["losses"] == 1
        assert v1_metrics["win_rate"] == 0.5
        assert v1_metrics["avg_r_multiple"] == 0.25  # (1.5 + -1.0) / 2
        
        # Verify V2 metrics
        v2_metrics = framework.get_variant_metrics(ModelVersion.V2_RAG)
        assert v2_metrics["prediction_count"] == 2
        assert abs(v2_metrics["avg_confidence"] - 0.85) < 1e-6  # (0.9 + 0.8) / 2 with tolerance
        assert v2_metrics["wins"] == 2
        assert v2_metrics["losses"] == 0
        assert v2_metrics["win_rate"] == 1.0
        assert v2_metrics["avg_r_multiple"] == 2.5  # (3.0 + 2.0) / 2
    
    @patch.dict(os.environ, {
        'CONFLUENCE_SCORER_AB_TEST': 'true',
        'CONFLUENCE_SCORER_AB_TEST_ROLLOUT': '100.0'
    })
    def test_end_to_end_prediction_with_ab_testing(self):
        """RED: Test end-to-end prediction workflow with A/B testing."""
        framework = ABTestingFramework(split_ratio=0.5)
        
        # Mock the inference engine and models
        with patch('ml.inference.main.InferenceEngine') as mock_engine_class:
            mock_engine = Mock()
            mock_engine_class.return_value = mock_engine
            
            # Create a mock registry that supports item assignment
            mock_registry = Mock()
            mock_registry._model_cache = {}
            mock_engine.registry = mock_registry
            
            # Mock prediction result
            mock_prediction = {
                "time": "2024-01-01T09:05:00Z",
                "regime": "TRENDING_BULLISH",
                "patterns": ["BOS_CONFIRMED"],
                "confidence_score": 0.85,
                "htf_projections": {
                    "htf_timeframe": "H1",
                    "htf_open": 1.1000,
                    "htf_high": 1.1100,
                    "htf_low": 1.0950,
                    "open_bias": "BULLISH"
                },
                "entry_price": 1.1060,
                "sl_price": 1.0950,
                "tp_price": 1.1100
            }
            mock_engine.predict.return_value = mock_prediction
            
            # Mock model loading
            with patch.object(framework.model_registry, 'load_model') as mock_load:
                mock_model = Mock()
                mock_load.return_value = mock_model
                
                # Run prediction with A/B testing
                user_id = "test_user_end_to_end"
                result = framework.predict_with_ab_testing(
                    user_id=user_id,
                    instrument="EURUSD",
                    timeframe="M5",
                    candles=self.sample_candles
                )
                
                # Verify A/B testing metadata added
                assert "model_version" in result
                assert "ab_test_active" in result
                assert "prediction_time" in result
                
                assert result["model_version"] in ["v1-baseline", "v2-rag"]
                assert result["ab_test_active"] is True
                
                # Verify original prediction data preserved
                assert result["confidence_score"] == 0.85
                assert result["regime"] == "TRENDING_BULLISH"
                assert result["patterns"] == ["BOS_CONFIRMED"]
                
                # Verify prediction was recorded in metrics
                assigned_version = ModelVersion.V1_BASELINE if result["model_version"] == "v1-baseline" else ModelVersion.V2_RAG
                metrics = framework.get_variant_metrics(assigned_version)
                assert metrics["prediction_count"] >= 1
    
    def test_model_fallback_behavior(self):
        """RED: Test fallback behavior when models are unavailable."""
        framework = ABTestingFramework(split_ratio=0.5)
        
        with patch.object(framework.model_registry, 'load_model') as mock_load:
            # Mock v2 model unavailable, v1 available
            def mock_load_side_effect(model_name, version):
                if version == ModelVersion.V2_RAG:
                    return None  # Simulate unavailable model
                elif version == ModelVersion.V1_BASELINE:
                    return Mock()  # Available model
                return None
            
            mock_load.side_effect = mock_load_side_effect
            
            # Users assigned to v2 should fallback to v1
            user_assigned_to_v2 = None
            
            # Find a user that would be assigned to v2
            for i in range(100):
                test_user = f"fallback_user_{i}"
                assigned_version = framework.traffic_splitter.get_model_version(test_user)
                if assigned_version == ModelVersion.V2_RAG:
                    user_assigned_to_v2 = test_user
                    break
            
            # This user should get v1 due to fallback
            if user_assigned_to_v2:
                version, model = framework.get_model_for_user(user_assigned_to_v2)
                assert version == ModelVersion.V1_BASELINE  # Fallback
                assert model is not None
    
    def test_statistical_significance_calculation(self):
        """RED: Test statistical significance calculation between variants."""
        framework = ABTestingFramework(split_ratio=0.5)
        
        # Clear metrics
        framework._variant_metrics[ModelVersion.V1_BASELINE] = framework._variant_metrics[ModelVersion.V1_BASELINE].__class__()
        framework._variant_metrics[ModelVersion.V2_RAG] = framework._variant_metrics[ModelVersion.V2_RAG].__class__()
        
        # Add enough data for significance testing
        for i in range(150):
            # V1: 60% win rate
            outcome = "WIN" if i % 10 < 6 else "LOSS"
            framework.record_prediction(f"v1_user_{i}", ModelVersion.V1_BASELINE, 0.7, outcome, 1.0)
            
            # V2: 70% win rate (significant improvement)
            outcome = "WIN" if i % 10 < 7 else "LOSS"
            framework.record_prediction(f"v2_user_{i}", ModelVersion.V2_RAG, 0.8, outcome, 1.2)
        
        summary = framework.get_ab_test_summary()
        significance = summary["statistical_significance"]
        
        # Should detect significance with this difference
        assert significance["significant"] is True
        assert significance["improvement_pct"] > 0  # V2 should be better
        assert significance["v1_win_rate"] < significance["v2_win_rate"]
        
    def test_insufficient_data_significance(self):
        """RED: Test that significance is not claimed with insufficient data."""
        framework = ABTestingFramework(split_ratio=0.5)
        
        # Clear metrics
        framework._variant_metrics[ModelVersion.V1_BASELINE] = framework._variant_metrics[ModelVersion.V1_BASELINE].__class__()
        framework._variant_metrics[ModelVersion.V2_RAG] = framework._variant_metrics[ModelVersion.V2_RAG].__class__()
        
        # Add minimal data (below threshold)
        for i in range(10):
            framework.record_prediction(f"small_v1_{i}", ModelVersion.V1_BASELINE, 0.7, "WIN", 1.0)
            framework.record_prediction(f"small_v2_{i}", ModelVersion.V2_RAG, 0.9, "WIN", 2.0)
        
        summary = framework.get_ab_test_summary()
        significance = summary["statistical_significance"]
        
        # Should not claim significance with insufficient data
        assert significance["significant"] is False
        assert significance["reason"] == "insufficient_data"