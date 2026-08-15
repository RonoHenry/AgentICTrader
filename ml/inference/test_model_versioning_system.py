"""
Tests for model versioning system - Task 17.1

RED phase: Tests for loading confluence-scorer-v1 (baseline) and confluence-scorer-v2-rag
GREEN phase: Implementation of model registry with version selection
REFACTOR phase: Add feature flags for A/B test control

**Validates: Requirements FR-RAG-5**
"""
from __future__ import annotations

import os
import sys
import pytest
from unittest.mock import Mock, patch, MagicMock
import numpy as np
from typing import Dict, Any, Optional

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from ml.inference.model_versioning import ModelVersionRegistry, ModelVersion
from ml.inference.feature_flags import get_feature_flags


class TestModelVersioningSystemRED:
    """RED phase: Write failing tests for model versioning system."""
    
    @patch('ml.inference.model_versioning.mlflow.tracking.MlflowClient')
    def test_load_confluence_scorer_v1_baseline(self, mock_mlflow_client):
        """RED: Test loading confluence-scorer-v1 (baseline) model."""
        # No real MLflow server in this environment - previously unmocked,
        # this hung retrying a real connection to http://localhost:5000 and
        # polluted global mlflow tracking state for every later test in the
        # process (see .kiro memory test_suite_isolation_bug.md). Mocking
        # only the network boundary: get_latest_versions() returning empty
        # exercises the real, already-correct _load_from_mlflow ->
        # _create_stub_model fallback path this test's assertions expect.
        mock_client_instance = Mock()
        mock_client_instance.get_latest_versions.return_value = []
        mock_mlflow_client.return_value = mock_client_instance

        registry = ModelVersionRegistry()

        # Should be able to load v1 baseline model
        model = registry.load_model("confluence-scorer", ModelVersion.V1_BASELINE)

        # At this point, model should fail to load because we haven't implemented it yet
        # But the test defines the expected behavior
        assert model is not None, "Should be able to load confluence-scorer-v1 baseline"

        # Model should have standard sklearn interface
        assert hasattr(model, 'predict'), "Model should have predict method"
        assert hasattr(model, 'predict_proba'), "Model should have predict_proba method"

        # Should work with feature vectors (original 64 features)
        test_features = np.random.rand(1, 64)
        prediction = model.predict_proba(test_features)
        assert prediction.shape == (1, 2), "Should return binary classification probabilities"

    @patch('ml.inference.model_versioning.mlflow.tracking.MlflowClient')
    def test_load_confluence_scorer_v2_rag(self, mock_mlflow_client):
        """RED: Test loading confluence-scorer-v2-rag model."""
        mock_client_instance = Mock()
        mock_client_instance.get_latest_versions.return_value = []
        mock_mlflow_client.return_value = mock_client_instance

        registry = ModelVersionRegistry()

        # Should be able to load v2 RAG-enhanced model
        model = registry.load_model("confluence-scorer", ModelVersion.V2_RAG)

        # At this point, model should fail to load because we haven't implemented it yet
        assert model is not None, "Should be able to load confluence-scorer-v2-rag"

        # Model should have standard sklearn interface
        assert hasattr(model, 'predict'), "Model should have predict method"
        assert hasattr(model, 'predict_proba'), "Model should have predict_proba method"

        # Should work with extended feature vectors (64 original + 4 RAG features = 68)
        test_features = np.random.rand(1, 68)
        prediction = model.predict_proba(test_features)
        assert prediction.shape == (1, 2), "Should return binary classification probabilities"

    @patch('ml.inference.model_versioning.mlflow.tracking.MlflowClient')
    def test_model_registry_version_selection(self, mock_mlflow_client):
        """RED: Test model registry can select between versions."""
        mock_client_instance = Mock()
        mock_client_instance.get_latest_versions.return_value = []
        mock_mlflow_client.return_value = mock_client_instance

        registry = ModelVersionRegistry()

        # Should be able to get both versions
        v1_model = registry.load_model("confluence-scorer", ModelVersion.V1_BASELINE)
        v2_model = registry.load_model("confluence-scorer", ModelVersion.V2_RAG)
        
        assert v1_model is not None, "Should load v1 baseline"
        assert v2_model is not None, "Should load v2 RAG-enhanced"
        assert v1_model is not v2_model, "Should be different model instances"
        
        # Should have different expected feature counts
        v1_info = registry.get_model_info("confluence-scorer", ModelVersion.V1_BASELINE)
        v2_info = registry.get_model_info("confluence-scorer", ModelVersion.V2_RAG)
        
        assert v1_info["feature_count"] == 64, "V1 should expect 64 features"
        assert v2_info["feature_count"] == 68, "V2 should expect 68 features (64 + 4 RAG)"
        assert not v1_info["features_enhanced"], "V1 should not have enhanced features"
        assert v2_info["features_enhanced"], "V2 should have enhanced RAG features"
    
    def test_graceful_degradation_fallback(self):
        """RED: Test graceful degradation when RAG model unavailable."""
        registry = ModelVersionRegistry()
        
        # Simulate v2 model not available
        with patch.object(registry, '_load_from_mlflow') as mock_load:
            # Return None for v2, valid model for v1
            def side_effect(model_name):
                if "v2" in model_name:
                    return None  # v2 not available
                else:
                    mock_model = Mock()
                    mock_model.predict_proba = Mock(return_value=np.array([[0.7, 0.3]]))
                    return mock_model
            
            mock_load.side_effect = side_effect
            
            # Should handle graceful degradation
            v2_model = registry.load_model("confluence-scorer", ModelVersion.V2_RAG)
            assert v2_model is None, "Should return None when model unavailable"
            
            # v1 should still work
            v1_model = registry.load_model("confluence-scorer", ModelVersion.V1_BASELINE)
            assert v1_model is not None, "Should still load v1 as fallback"
    
    def test_feature_flags_ab_test_control(self):
        """RED: Test feature flags control A/B testing."""
        feature_flags = get_feature_flags()
        
        # Should have confluence scorer A/B test flag
        assert feature_flags.is_enabled("confluence_scorer_ab_test", "test_user") in [True, False], \
            "Should have boolean result for A/B test flag"
        
        # Should be able to enable/disable A/B testing
        feature_flags.update_flag("confluence_scorer_ab_test", enabled=True)
        assert feature_flags.is_enabled("confluence_scorer_ab_test", "test_user") == True, \
            "Should enable A/B testing when flag is on"
        
        feature_flags.update_flag("confluence_scorer_ab_test", enabled=False)
        assert feature_flags.is_enabled("confluence_scorer_ab_test", "test_user") == False, \
            "Should disable A/B testing when flag is off"
    
    def test_integration_with_ml_inference_service(self):
        """RED: Test integration with existing ML inference service."""
        # This test will be implemented in GREEN phase
        # It ensures the versioning system integrates with main.py inference engine
        
        from ml.inference.main import ModelRegistry as OriginalModelRegistry
        
        # Should be able to extend existing ModelRegistry
        registry = ModelVersionRegistry()
        
        # Should integrate with existing inference patterns
        assert hasattr(registry, 'load_model'), "Should have load_model interface"
        assert hasattr(registry, 'get_model_info'), "Should have metadata interface"
        
        # Should support both v1 and v2 models
        versions = registry.list_available_versions("confluence-scorer")
        assert ModelVersion.V1_BASELINE in versions, "Should support v1 baseline"
        assert ModelVersion.V2_RAG in versions, "Should support v2 RAG-enhanced"


class TestABTestingIntegrationRED:
    """RED phase: Tests for A/B testing integration with versioning."""
    
    def test_version_based_traffic_splitting(self):
        """RED: Test traffic splitting between v1 and v2 models."""
        from ml.inference.ab_testing import ABTestingFramework
        
        framework = ABTestingFramework(split_ratio=0.5)
        
        # Should distribute users between v1 and v2
        user_assignments = {}
        for i in range(100):
            user_id = f"user_{i}"
            version, model = framework.get_model_for_user(user_id)
            user_assignments[user_id] = version
        
        # Should have both versions assigned
        versions_used = set(user_assignments.values())
        assert ModelVersion.V1_BASELINE in versions_used, "Should assign some users to v1"
        assert ModelVersion.V2_RAG in versions_used, "Should assign some users to v2"
        
        # Should be roughly 50/50 (allowing for variance in small sample)
        v1_count = sum(1 for v in user_assignments.values() if v == ModelVersion.V1_BASELINE)
        v2_count = sum(1 for v in user_assignments.values() if v == ModelVersion.V2_RAG)
        assert 30 <= v1_count <= 70, f"Expected ~50 v1 assignments, got {v1_count}"
        assert 30 <= v2_count <= 70, f"Expected ~50 v2 assignments, got {v2_count}"
    
    def test_sticky_user_sessions(self):
        """RED: Test users get consistent model version across sessions."""
        from ml.inference.ab_testing import ABTestingFramework
        
        framework = ABTestingFramework(split_ratio=0.5)
        
        # Same user should get same version consistently
        test_users = ["user_sticky_1", "user_sticky_2", "user_sticky_3"]
        
        for user_id in test_users:
            # Get version multiple times
            version1, _ = framework.get_model_for_user(user_id)
            version2, _ = framework.get_model_for_user(user_id) 
            version3, _ = framework.get_model_for_user(user_id)
            
            assert version1 == version2 == version3, \
                f"User {user_id} should get consistent version, got {version1}, {version2}, {version3}"
    
    def test_feature_flag_overrides_traffic_splitting(self):
        """RED: Test feature flags can override traffic splitting."""
        from ml.inference.ab_testing import ABTestingFramework
        
        # When A/B test is disabled, should always use v1 baseline
        with patch('ml.inference.ab_testing.get_feature_flags') as mock_flags:
            mock_flag_manager = Mock()
            mock_flag_manager.is_enabled.return_value = False  # A/B test disabled
            mock_flags.return_value = mock_flag_manager
            
            framework = ABTestingFramework(split_ratio=0.5)  # 50% split configured
            
            # Should always return v1 when flag is off, regardless of split ratio
            for i in range(10):
                version, _ = framework.get_model_for_user(f"user_{i}")
                assert version == ModelVersion.V1_BASELINE, \
                    "Should use v1 baseline when A/B test flag is disabled"


@pytest.mark.integration
class TestModelVersioningIntegrationRED:
    """RED phase: Integration tests requiring MLflow and infrastructure."""
    
    def test_mlflow_model_loading_v1(self):
        """RED: Test actual MLflow model loading for v1."""
        # This test requires MLflow server running
        registry = ModelVersionRegistry()
        
        # Should try to load from MLflow registry
        model = registry.load_model("confluence-scorer", ModelVersion.V1_BASELINE)
        
        # For now, might be None if models not yet trained
        # But the infrastructure should be in place
        if model is not None:
            assert hasattr(model, 'predict_proba'), "Loaded model should have predict_proba"
        
        # Should have correct MLflow model name mapping
        v1_info = registry.get_model_info("confluence-scorer", ModelVersion.V1_BASELINE)
        assert v1_info["mlflow_name"] == "confluence-scorer-v1", "Should map to correct MLflow name"
    
    def test_mlflow_model_loading_v2(self):
        """RED: Test actual MLflow model loading for v2.""" 
        registry = ModelVersionRegistry()
        
        # Should try to load RAG-enhanced model
        model = registry.load_model("confluence-scorer", ModelVersion.V2_RAG)
        
        # For now, might be None if models not yet trained
        if model is not None:
            assert hasattr(model, 'predict_proba'), "Loaded model should have predict_proba"
        
        # Should have correct MLflow model name mapping
        v2_info = registry.get_model_info("confluence-scorer", ModelVersion.V2_RAG)
        assert v2_info["mlflow_name"] == "confluence-scorer-v2-rag", "Should map to correct MLflow name"


if __name__ == "__main__":
    # Run the RED tests - they should all fail initially
    pytest.main([__file__, "-v", "--tb=short"])