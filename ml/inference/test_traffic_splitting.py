"""
Tests for traffic splitting functionality in A/B testing framework.

Tests traffic distribution, sticky sessions, and configurable split ratios
for A/B testing between baseline and RAG-augmented models.
"""
from __future__ import annotations

import os
import sys
from unittest.mock import Mock, patch, MagicMock
import pytest
import numpy as np
from typing import Dict, Any, Optional

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from ml.inference.ab_testing import TrafficSplitter, ABTestingFramework, ModelVersion


class TestTrafficSplitting:
    """Test cases for traffic splitting implementation."""
    
    def test_fifty_fifty_traffic_split(self):
        """RED: Test 50/50 traffic split between v1 and v2 models."""
        splitter = TrafficSplitter(split_ratio=0.5)
        
        # Test with large sample to verify distribution
        v1_count = 0
        v2_count = 0
        sample_size = 1000
        
        for i in range(sample_size):
            version = splitter.get_model_version(user_id=f"user_{i}")
            if version == ModelVersion.V1_BASELINE:
                v1_count += 1
            elif version == ModelVersion.V2_RAG:
                v2_count += 1
        
        # Should be roughly 50/50 (allow 15% deviation for statistical variance)
        expected = sample_size // 2
        tolerance = int(sample_size * 0.15)  # 15% tolerance
        
        assert expected - tolerance <= v1_count <= expected + tolerance, f"v1 count {v1_count} outside tolerance"
        assert expected - tolerance <= v2_count <= expected + tolerance, f"v2 count {v2_count} outside tolerance"
        assert v1_count + v2_count == sample_size
    
    def test_sticky_sessions_consistency(self):
        """RED: Test that same user gets same model version across multiple calls."""
        splitter = TrafficSplitter(split_ratio=0.5)
        
        # Test multiple users for consistency
        test_users = ["user_abc", "user_xyz", "user_123", "user_test", "consistent_user"]
        
        for user_id in test_users:
            # Get assignment multiple times
            assignments = []
            for _ in range(10):  # Test 10 consecutive calls
                version = splitter.get_model_version(user_id=user_id)
                assignments.append(version)
            
            # All assignments should be identical
            assert all(v == assignments[0] for v in assignments), f"User {user_id} got inconsistent assignments"
    
    def test_different_split_ratios(self):
        """RED: Test configurable split ratios (90/10, 25/75)."""
        test_cases = [
            (0.1, 10),   # 10% v2, 90% v1
            (0.25, 25),  # 25% v2, 75% v1
            (0.75, 75),  # 75% v2, 25% v1
            (0.9, 90),   # 90% v2, 10% v1
        ]
        
        sample_size = 1000
        tolerance = 8  # 8% tolerance for statistical variance
        
        for split_ratio, expected_v2_pct in test_cases:
            splitter = TrafficSplitter(split_ratio=split_ratio)
            
            v1_count = 0
            v2_count = 0
            
            for i in range(sample_size):
                version = splitter.get_model_version(user_id=f"test_{split_ratio}_{i}")
                if version == ModelVersion.V1_BASELINE:
                    v1_count += 1
                elif version == ModelVersion.V2_RAG:
                    v2_count += 1
            
            actual_v2_pct = (v2_count / sample_size) * 100
            
            assert expected_v2_pct - tolerance <= actual_v2_pct <= expected_v2_pct + tolerance, \
                f"Split ratio {split_ratio}: expected {expected_v2_pct}% v2, got {actual_v2_pct}%"
    
    def test_deterministic_user_assignment(self):
        """RED: Test that user assignment is deterministic across different splitter instances."""
        # Create two different splitter instances with same ratio
        splitter1 = TrafficSplitter(split_ratio=0.5)
        splitter2 = TrafficSplitter(split_ratio=0.5)
        
        test_users = ["user_1", "user_2", "user_3", "deterministic_test"]
        
        for user_id in test_users:
            version1 = splitter1.get_model_version(user_id)
            version2 = splitter2.get_model_version(user_id)
            
            # Same user should get same assignment across different instances
            assert version1 == version2, f"User {user_id} got different assignments from different splitters"
    
    def test_assignment_info_details(self):
        """RED: Test that assignment info provides correct details."""
        splitter = TrafficSplitter(split_ratio=0.3)  # 30% v2, 70% v1
        
        user_id = "info_test_user"
        assignment_info = splitter.get_assignment_info(user_id)
        
        # Should contain required fields
        assert "user_id" in assignment_info
        assert "assigned_version" in assignment_info
        assert "hash_fraction" in assignment_info
        assert "split_ratio" in assignment_info
        assert "assignment_reason" in assignment_info
        
        # Verify values
        assert assignment_info["user_id"] == user_id
        assert assignment_info["split_ratio"] == 0.3
        assert assignment_info["assignment_reason"] == "hash_based_sticky_session"
        assert assignment_info["assigned_version"] in ["v1-baseline", "v2-rag"]
        assert 0.0 <= assignment_info["hash_fraction"] <= 1.0
        
        # Verify assignment logic consistency
        expected_version = ModelVersion.V2_RAG if assignment_info["hash_fraction"] < 0.3 else ModelVersion.V1_BASELINE
        actual_version = splitter.get_model_version(user_id)
        assert actual_version == expected_version
    
    def test_edge_case_split_ratios(self):
        """RED: Test edge cases with 0% and 100% split ratios."""
        # Test 0% v2 (all v1)
        splitter_0 = TrafficSplitter(split_ratio=0.0)
        
        for i in range(100):
            version = splitter_0.get_model_version(f"user_{i}")
            assert version == ModelVersion.V1_BASELINE, "0% split should assign all users to v1"
        
        # Test 100% v2 (all v2) 
        splitter_100 = TrafficSplitter(split_ratio=1.0)
        
        for i in range(100):
            version = splitter_100.get_model_version(f"user_{i}")
            assert version == ModelVersion.V2_RAG, "100% split should assign all users to v2"
    
    def test_invalid_split_ratio(self):
        """RED: Test that invalid split ratios raise ValueError."""
        invalid_ratios = [-0.1, 1.1, 2.0, -1.0]
        
        for invalid_ratio in invalid_ratios:
            with pytest.raises(ValueError, match="split_ratio must be between 0.0 and 1.0"):
                TrafficSplitter(split_ratio=invalid_ratio)


class TestIntegratedTrafficSplitting:
    """Test integrated traffic splitting with A/B testing framework."""
    
    @patch('ml.inference.ab_testing.os.getenv')
    def test_framework_traffic_distribution(self, mock_getenv):
        """RED: Test traffic distribution through complete A/B framework."""
        # Enable feature flag
        mock_getenv.return_value = "true"
        
        framework = ABTestingFramework(split_ratio=0.4)  # 40% v2, 60% v1
        
        # Mock model loading
        with patch.object(framework.model_registry, 'load_model') as mock_load:
            mock_model = Mock()
            mock_load.return_value = mock_model
            
            v1_assignments = 0
            v2_assignments = 0
            sample_size = 500
            
            for i in range(sample_size):
                version, model = framework.get_model_for_user(f"framework_user_{i}")
                
                if version == ModelVersion.V1_BASELINE:
                    v1_assignments += 1
                elif version == ModelVersion.V2_RAG:
                    v2_assignments += 1
            
            # Should follow 40/60 split with tolerance
            expected_v2 = int(sample_size * 0.4)
            tolerance = int(sample_size * 0.1)  # 10% tolerance
            
            assert expected_v2 - tolerance <= v2_assignments <= expected_v2 + tolerance
            assert v1_assignments + v2_assignments == sample_size
    
    @patch('ml.inference.ab_testing.os.getenv')
    def test_framework_sticky_sessions(self, mock_getenv):
        """RED: Test sticky sessions through A/B testing framework."""
        # Enable feature flag
        mock_getenv.return_value = "true"
        
        framework = ABTestingFramework(split_ratio=0.5)
        
        with patch.object(framework.model_registry, 'load_model') as mock_load:
            mock_model = Mock()
            mock_load.return_value = mock_model
            
            test_user = "sticky_framework_user"
            
            # Get multiple assignments for same user
            assignments = []
            for _ in range(5):
                version, model = framework.get_model_for_user(test_user)
                assignments.append(version)
            
            # All should be the same
            assert all(v == assignments[0] for v in assignments), "Framework should maintain sticky sessions"
    
    @patch('ml.inference.ab_testing.os.getenv')
    def test_feature_flag_overrides_splitting(self, mock_getenv):
        """RED: Test that disabled feature flag overrides traffic splitting."""
        # Disable feature flag
        mock_getenv.return_value = "false"
        
        # Even with 100% v2 split, should get v1 when flag disabled
        framework = ABTestingFramework(split_ratio=1.0)
        
        with patch.object(framework.model_registry, 'load_model') as mock_load:
            mock_model = Mock()
            mock_load.return_value = mock_model
            
            for i in range(10):
                version, model = framework.get_model_for_user(f"flag_test_user_{i}")
                assert version == ModelVersion.V1_BASELINE, "Disabled flag should force v1 regardless of split ratio"