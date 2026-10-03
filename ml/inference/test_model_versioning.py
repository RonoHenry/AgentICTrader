"""
Tests for A/B testing model versioning system.

Tests model registry functionality for loading different versions of the
Confluence Scorer for A/B testing between baseline (v1) and RAG-augmented (v2).
"""
from __future__ import annotations

import os
import sys
from unittest.mock import Mock, patch, MagicMock
import pytest
import numpy as np
from typing import Dict, Any, Optional

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from ml.inference.model_versioning import ModelVersionRegistry, ModelVersion
from ml.inference.ab_testing import ABTestingFramework, TrafficSplitter


# Feature-flag environments for the A/B test. These used to be simulated by
# patching ``ml.inference.ab_testing.os.getenv``, but that attribute is the
# global ``os.getenv``: every env lookup in the process (including
# MLFLOW_TRACKING_URI) returned "true"/"false", so MLflow was pointed at a
# ``./true`` or ``./false`` file store in the repo root.
AB_TEST_ON = {
    "CONFLUENCE_SCORER_AB_TEST": "true",
    "CONFLUENCE_SCORER_AB_TEST_ROLLOUT": "100.0",
}
AB_TEST_OFF = {"CONFLUENCE_SCORER_AB_TEST": "false"}


class TestModelVersionRegistry:
    """Test cases for model version registry."""
    
    @patch('ml.inference.model_versioning.mlflow.sklearn.load_model')
    @patch('ml.inference.model_versioning.mlflow.tracking.MlflowClient')
    def test_load_baseline_model_v1(self, mock_mlflow_client, mock_load_model):
        """RED: Test loading confluence-scorer-v1 baseline model."""
        # Mock MLflow client and model loading
        mock_client_instance = Mock()
        mock_version = Mock()
        mock_version.version = "1"
        mock_client_instance.get_latest_versions.return_value = [mock_version]
        mock_mlflow_client.return_value = mock_client_instance
        
        mock_model = Mock()
        mock_model.predict = Mock(return_value=[0])
        mock_model.predict_proba = Mock(return_value=[[0.7, 0.3]])
        mock_load_model.return_value = mock_model
        
        registry = ModelVersionRegistry()
        
        # Should be able to load v1 baseline
        model = registry.load_model("confluence-scorer", ModelVersion.V1_BASELINE)
        assert model is not None
        
        # Should have correct metadata
        assert registry.get_model_info("confluence-scorer", ModelVersion.V1_BASELINE)["version"] == "v1"
        assert registry.get_model_info("confluence-scorer", ModelVersion.V1_BASELINE)["features_enhanced"] is False
    
    @patch('ml.inference.model_versioning.mlflow.sklearn.load_model')
    @patch('ml.inference.model_versioning.mlflow.tracking.MlflowClient')
    def test_load_rag_model_v2(self, mock_mlflow_client, mock_load_model):
        """RED: Test loading confluence-scorer-v2-rag model."""
        # Mock MLflow client and model loading
        mock_client_instance = Mock()
        mock_version = Mock()
        mock_version.version = "1"
        mock_client_instance.get_latest_versions.return_value = [mock_version]
        mock_mlflow_client.return_value = mock_client_instance
        
        mock_model = Mock()
        mock_model.predict = Mock(return_value=[1])
        mock_model.predict_proba = Mock(return_value=[[0.3, 0.7]])
        mock_load_model.return_value = mock_model
        
        registry = ModelVersionRegistry()
        
        # Should be able to load v2 with RAG
        model = registry.load_model("confluence-scorer", ModelVersion.V2_RAG)
        assert model is not None
        
        # Should have correct metadata
        assert registry.get_model_info("confluence-scorer", ModelVersion.V2_RAG)["version"] == "v2-rag"
        assert registry.get_model_info("confluence-scorer", ModelVersion.V2_RAG)["features_enhanced"] is True
    
    @patch('ml.inference.model_versioning.mlflow.sklearn.load_model')
    @patch('ml.inference.model_versioning.mlflow.tracking.MlflowClient')
    def test_model_registry_caching(self, mock_mlflow_client, mock_load_model):
        """RED: Test that models are cached after first load."""
        # Mock MLflow client and model loading
        mock_client_instance = Mock()
        mock_version = Mock()
        mock_version.version = "1"
        mock_client_instance.get_latest_versions.return_value = [mock_version]
        mock_mlflow_client.return_value = mock_client_instance
        
        mock_model = Mock()
        mock_load_model.return_value = mock_model
        
        registry = ModelVersionRegistry()
        
        # Load same model twice
        model1 = registry.load_model("confluence-scorer", ModelVersion.V1_BASELINE)
        model2 = registry.load_model("confluence-scorer", ModelVersion.V1_BASELINE)
        
        # Should return the same cached instance
        assert model1 is model2
        
        # MLflow should only be called once due to caching
        assert mock_load_model.call_count == 1
    
    @patch('ml.inference.model_versioning.mlflow.sklearn.load_model')
    @patch('ml.inference.model_versioning.mlflow.tracking.MlflowClient')
    def test_fallback_when_model_unavailable(self, mock_mlflow_client, mock_load_model):
        """RED: Test fallback to stub when model not in registry."""
        # No registered versions for this model name - MLflow client returns
        # empty, never a real network call (this used to be unmocked and hung
        # / polluted global mlflow tracking state for every later test in the
        # same process - see .kiro memory test_suite_isolation_bug.md).
        mock_client_instance = Mock()
        mock_client_instance.get_latest_versions.return_value = []
        mock_mlflow_client.return_value = mock_client_instance

        registry = ModelVersionRegistry()

        # Should fallback gracefully for non-existent model
        model = registry.load_model("non-existent-model", ModelVersion.V1_BASELINE)
        assert model is None or hasattr(model, "predict")  # Either None or stub
        mock_load_model.assert_not_called()


class TestTrafficSplitter:
    """Test cases for A/B testing traffic splitting."""
    
    def test_fifty_fifty_split(self):
        """RED: Test 50/50 traffic split between v1 and v2 models."""
        splitter = TrafficSplitter(split_ratio=0.5)
        
        # Test with 1000 samples to verify distribution
        v1_count = 0
        v2_count = 0
        
        for i in range(1000):
            version = splitter.get_model_version(user_id=f"user_{i}")
            if version == ModelVersion.V1_BASELINE:
                v1_count += 1
            else:
                v2_count += 1
        
        # Should be roughly 50/50 (allow 10% deviation)
        assert 400 <= v1_count <= 600
        assert 400 <= v2_count <= 600
    
    def test_sticky_sessions(self):
        """RED: Test that same user gets same model version consistently."""
        splitter = TrafficSplitter(split_ratio=0.5)
        
        # Same user should get consistent assignment
        user_id = "test_user_123"
        version1 = splitter.get_model_version(user_id=user_id)
        version2 = splitter.get_model_version(user_id=user_id)
        version3 = splitter.get_model_version(user_id=user_id)
        
        assert version1 == version2 == version3
    
    def test_configurable_split_ratios(self):
        """RED: Test different split ratios (90/10)."""
        splitter = TrafficSplitter(split_ratio=0.1)  # 10% v2, 90% v1
        
        # Test with 1000 samples
        v1_count = 0
        v2_count = 0
        
        for i in range(1000):
            version = splitter.get_model_version(user_id=f"user_{i}")
            if version == ModelVersion.V1_BASELINE:
                v1_count += 1
            else:
                v2_count += 1
        
        # Should be roughly 10% v2 (allow for variance)
        assert 50 <= v2_count <= 150  # 5-15%
        assert 850 <= v1_count <= 950  # 85-95%


class TestABTestingFramework:
    """Test cases for complete A/B testing framework."""
    
    def test_framework_initialization(self):
        """RED: Test A/B testing framework initialization."""
        framework = ABTestingFramework(
            split_ratio=0.5,
            feature_flag_key="confluence_scorer_ab_test"
        )
        
        assert framework.split_ratio == 0.5
        assert framework.feature_flag_key == "confluence_scorer_ab_test"
        assert framework.model_registry is not None
        assert framework.traffic_splitter is not None
    
    @patch.dict(os.environ, AB_TEST_ON)
    def test_model_selection_with_feature_flag_on(self):
        """RED: Test model selection when A/B test feature flag is enabled."""
        framework = ABTestingFramework(split_ratio=0.5)
        
        with patch.object(framework.model_registry, 'load_model') as mock_load:
            mock_model = Mock()
            mock_load.return_value = mock_model
            
            model_version, model = framework.get_model_for_user("test_user")
            
            # Should return either v1 or v2
            assert model_version in [ModelVersion.V1_BASELINE, ModelVersion.V2_RAG]
            assert model is not None
    
    @patch.dict(os.environ, AB_TEST_OFF)
    def test_model_selection_with_feature_flag_off(self):
        """RED: Test model selection when A/B test feature flag is disabled."""
        framework = ABTestingFramework(split_ratio=0.5)
        
        with patch.object(framework.model_registry, 'load_model') as mock_load:
            mock_model = Mock()
            mock_load.return_value = mock_model
            
            model_version, model = framework.get_model_for_user("test_user")
            
            # Should always return v1 baseline when feature flag is off
            assert model_version == ModelVersion.V1_BASELINE
            assert model is not None
    
    def test_metrics_collection_per_variant(self):
        """RED: Test that metrics are collected separately per model variant."""
        framework = ABTestingFramework(split_ratio=0.5)
        
        # Record predictions for both variants
        framework.record_prediction("user1", ModelVersion.V1_BASELINE, 0.85, "WIN", 2.5)
        framework.record_prediction("user2", ModelVersion.V2_RAG, 0.92, "LOSS", -1.0)
        framework.record_prediction("user3", ModelVersion.V1_BASELINE, 0.78, "WIN", 1.8)
        
        # Should have separate metrics
        v1_metrics = framework.get_variant_metrics(ModelVersion.V1_BASELINE)
        v2_metrics = framework.get_variant_metrics(ModelVersion.V2_RAG)
        
        assert v1_metrics["prediction_count"] == 2
        assert v1_metrics["avg_confidence"] == (0.85 + 0.78) / 2
        assert v1_metrics["win_rate"] == 1.0  # 2/2 wins
        
        assert v2_metrics["prediction_count"] == 1
        assert v2_metrics["avg_confidence"] == 0.92
        assert v2_metrics["win_rate"] == 0.0  # 0/1 wins
    
    @pytest.mark.integration 
    @pytest.mark.parametrize(
        "split_ratio, expected_version",
        [
            (0.0, ModelVersion.V1_BASELINE),  # 0% to v2: every user gets v1
            (1.0, ModelVersion.V2_RAG),       # 100% to v2: every user gets v2
        ],
    )
    @patch.dict(os.environ, AB_TEST_ON)
    def test_integration_with_inference_engine(self, split_ratio, expected_version):
        """RED: Test integration with ML inference engine."""
        framework = ABTestingFramework(split_ratio=split_ratio)
        
        # Mock candles data
        candles = [
            {"time": "2024-01-01T09:00:00Z", "open": 1.1000, "high": 1.1050, "low": 1.0980, "close": 1.1020, "volume": 1000},
            {"time": "2024-01-01T09:05:00Z", "open": 1.1020, "high": 1.1080, "low": 1.1000, "close": 1.1060, "volume": 1200},
        ]
        
        # Each variant returns a different P(high confidence), so the result
        # shows which Confluence Scorer produced the score.
        variant_models = {
            ModelVersion.V1_BASELINE: Mock(predict_proba=Mock(return_value=np.array([[0.7, 0.3]]))),
            ModelVersion.V2_RAG: Mock(predict_proba=Mock(return_value=np.array([[0.2, 0.8]]))),
        }
        variant_confidence = {ModelVersion.V1_BASELINE: 0.3, ModelVersion.V2_RAG: 0.8}
        
        # Should be able to run prediction with selected model
        user_id = "integration_test_user"
        with patch.object(
            framework.model_registry,
            "load_model",
            side_effect=lambda name, version: variant_models[version],
        ):
            result = framework.predict_with_ab_testing(
                user_id=user_id,
                instrument="EURUSD",
                timeframe="M5",
                candles=candles
            )
        
        # Should have prediction result with model version info
        assert "confidence_score" in result
        assert "model_version" in result
        assert "prediction_time" in result
        # ModelVersion values are "v1-baseline" / "v2-rag"; plain "v1" is not one.
        assert result["model_version"] == expected_version.value
        assert result["ab_test_active"] is True
        
        # The confidence score must come from the variant the user was assigned to.
        assert result["confidence_score"] == variant_confidence[expected_version]
        variant_models[expected_version].predict_proba.assert_called_once()
        
        # Regime/pattern models are not registered in the per-test MLflow store,
        # so the inference registry falls back to its stub predictions.
        assert result["regime"] == "RANGING"
        assert result["patterns"] == []
        
        # The prediction is recorded against the variant that served it.
        assert framework.get_variant_metrics(expected_version)["prediction_count"] == 1