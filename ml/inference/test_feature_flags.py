"""
Tests for feature flag management system.

Tests feature flag registration, user overrides, percentage rollouts,
and integration with A/B testing framework.
"""
from __future__ import annotations

import os
import sys
from unittest.mock import Mock, patch
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from ml.inference.feature_flags import FeatureFlagManager, FeatureFlag, get_feature_flags, is_feature_enabled


class TestFeatureFlagManager:
    """Test cases for feature flag manager."""
    
    def test_register_flag_basic(self):
        """RED: Test basic flag registration."""
        manager = FeatureFlagManager()
        
        # Clear existing flags for clean test
        manager._flags.clear()
        
        # Register a new flag
        manager.register_flag(
            key="test_flag",
            enabled=True,
            description="Test flag",
            rollout_percentage=100.0
        )
        
        # Should be registered
        assert "test_flag" in manager._flags
        flag = manager._flags["test_flag"]
        assert flag.key == "test_flag"
        assert flag.enabled is True
        assert flag.description == "Test flag"
        assert flag.rollout_percentage == 100.0
    
    def test_is_enabled_basic(self):
        """RED: Test basic flag enabled check."""
        manager = FeatureFlagManager()
        manager._flags.clear()
        
        # Register enabled and disabled flags
        manager.register_flag("enabled_flag", enabled=True)
        manager.register_flag("disabled_flag", enabled=False)
        
        # Test enabled flag
        assert manager.is_enabled("enabled_flag") is True
        
        # Test disabled flag
        assert manager.is_enabled("disabled_flag") is False
        
        # Test non-existent flag with default
        assert manager.is_enabled("non_existent", default=True) is True
        assert manager.is_enabled("non_existent", default=False) is False
    
    def test_user_overrides(self):
        """RED: Test user-specific flag overrides."""
        manager = FeatureFlagManager()
        manager._flags.clear()
        
        # Register a disabled flag
        manager.register_flag("override_test", enabled=False)
        
        # Set user override
        manager.set_user_override("override_test", "user123", True)
        
        # User should get override value
        assert manager.is_enabled("override_test", user_id="user123") is True
        
        # Other users should get global value
        assert manager.is_enabled("override_test", user_id="other_user") is False
        assert manager.is_enabled("override_test") is False
        
        # Remove override
        manager.remove_user_override("override_test", "user123")
        assert manager.is_enabled("override_test", user_id="user123") is False
    
    def test_percentage_rollout(self):
        """RED: Test percentage-based rollout."""
        manager = FeatureFlagManager()
        manager._flags.clear()
        
        # Register flag with 20% rollout
        manager.register_flag("rollout_test", enabled=True, rollout_percentage=20.0)
        
        # Test with many users to verify distribution
        enabled_count = 0
        total_users = 1000
        
        for i in range(total_users):
            if manager.is_enabled("rollout_test", user_id=f"user_{i}"):
                enabled_count += 1
        
        # Should be approximately 20% (allow 5% variance)
        expected = total_users * 0.2
        tolerance = total_users * 0.05
        
        assert expected - tolerance <= enabled_count <= expected + tolerance
    
    def test_rollout_consistency(self):
        """RED: Test that rollout is consistent for same user."""
        manager = FeatureFlagManager()
        manager._flags.clear()
        
        manager.register_flag("consistent_rollout", enabled=True, rollout_percentage=50.0)
        
        # Same user should get same result multiple times
        user_id = "consistent_user"
        results = []
        
        for _ in range(10):
            results.append(manager.is_enabled("consistent_rollout", user_id=user_id))
        
        # All results should be identical
        assert all(r == results[0] for r in results)
    
    def test_update_flag(self):
        """RED: Test updating existing flags."""
        manager = FeatureFlagManager()
        manager._flags.clear()
        
        # Register flag
        manager.register_flag("update_test", enabled=False, rollout_percentage=50.0)
        
        # Update enabled state
        success = manager.update_flag("update_test", enabled=True)
        assert success is True
        assert manager.is_enabled("update_test") is True
        
        # Update rollout percentage
        success = manager.update_flag("update_test", rollout_percentage=75.0)
        assert success is True
        assert manager._flags["update_test"].rollout_percentage == 75.0
        
        # Try to update non-existent flag
        success = manager.update_flag("non_existent", enabled=True)
        assert success is False
    
    def test_get_flag_info(self):
        """RED: Test getting flag information."""
        manager = FeatureFlagManager()
        manager._flags.clear()
        
        manager.register_flag("info_test", enabled=True, description="Info test flag", rollout_percentage=60.0)
        manager.set_user_override("info_test", "user1", False)
        manager.set_user_override("info_test", "user2", True)
        
        info = manager.get_flag_info("info_test")
        assert info is not None
        assert info["key"] == "info_test"
        assert info["enabled"] is True
        assert info["description"] == "Info test flag"
        assert info["rollout_percentage"] == 60.0
        assert info["user_override_count"] == 2
        assert "created_at" in info
        
        # Non-existent flag
        info = manager.get_flag_info("non_existent")
        assert info is None
    
    def test_list_flags(self):
        """RED: Test listing all flags."""
        manager = FeatureFlagManager()
        manager._flags.clear()
        
        manager.register_flag("flag1", enabled=True, description="First flag")
        manager.register_flag("flag2", enabled=False, description="Second flag")
        
        flags = manager.list_flags()
        assert len(flags) == 2
        assert "flag1" in flags
        assert "flag2" in flags
        assert flags["flag1"]["enabled"] is True
        assert flags["flag2"]["enabled"] is False


class TestFeatureFlagEnvironment:
    """Test feature flag environment loading."""
    
    @patch.dict(os.environ, {
        'CONFLUENCE_SCORER_AB_TEST': 'true',
        'CONFLUENCE_SCORER_AB_TEST_ROLLOUT': '80.0',
        'RAG_FEATURES_ENABLED': 'false',
        'ENHANCED_REASONING_ENABLED': 'yes'
    })
    def test_load_from_environment(self):
        """RED: Test loading flags from environment variables."""
        manager = FeatureFlagManager()
        
        # Should load default flags from environment
        assert manager.is_enabled("confluence_scorer_ab_test") is True
        assert manager._flags["confluence_scorer_ab_test"].rollout_percentage == 80.0
        assert manager.is_enabled("rag_features_enabled") is False
        assert manager.is_enabled("enhanced_reasoning_enabled") is True
    
    def test_environment_fallback(self):
        """RED: Test environment variable fallback for unknown flags."""
        with patch.dict(os.environ, {'CUSTOM_TEST_FLAG': 'true'}):
            manager = FeatureFlagManager()
            
            # Should use environment variable as fallback
            assert manager.is_enabled("CUSTOM_TEST_FLAG") is True
            assert manager.is_enabled("CUSTOM_TEST_FLAG", default=False) is True
            
            # Non-existent env var should use default
            assert manager.is_enabled("NON_EXISTENT_FLAG", default=False) is False


class TestFeatureFlagGlobalAccess:
    """Test global feature flag access functions."""
    
    def test_get_feature_flags_singleton(self):
        """RED: Test that get_feature_flags returns singleton."""
        manager1 = get_feature_flags()
        manager2 = get_feature_flags()
        
        # Should be the same instance
        assert manager1 is manager2
    
    def test_is_feature_enabled_convenience(self):
        """RED: Test convenience function."""
        manager = get_feature_flags()
        manager._flags.clear()
        manager.register_flag("convenience_test", enabled=True)
        
        # Should work through convenience function
        assert is_feature_enabled("convenience_test") is True
        assert is_feature_enabled("convenience_test", user_id="test_user") is True
    
    @patch.dict(os.environ, {'CONVENIENCE_ENV_FLAG': 'true'})
    def test_convenience_with_environment(self):
        """RED: Test convenience function with environment fallback."""
        # Should use environment variable
        assert is_feature_enabled("CONVENIENCE_ENV_FLAG") is True


class TestFeatureFlagEdgeCases:
    """Test edge cases and error conditions."""
    
    def test_invalid_rollout_percentage(self):
        """RED: Test handling of invalid rollout percentages."""
        manager = FeatureFlagManager()
        manager._flags.clear()
        
        # Should accept valid percentages
        manager.register_flag("valid_rollout", rollout_percentage=0.0)
        manager.register_flag("valid_rollout_100", rollout_percentage=100.0)
        
        # Edge case: what happens with > 100%?
        manager.register_flag("high_rollout", enabled=True, rollout_percentage=150.0)
        # Should still work (implementation allows it)
        assert manager.is_enabled("high_rollout", user_id="test") is True
    
    def test_empty_user_id(self):
        """RED: Test handling of empty user ID."""
        manager = FeatureFlagManager()
        manager._flags.clear()
        
        manager.register_flag("empty_user_test", enabled=True, rollout_percentage=50.0)
        
        # Empty user ID should not cause errors
        result1 = manager.is_enabled("empty_user_test", user_id="")
        result2 = manager.is_enabled("empty_user_test", user_id=None)
        
        # Should handle gracefully
        assert isinstance(result1, bool)
        assert isinstance(result2, bool)
    
    def test_user_override_on_nonexistent_flag(self):
        """RED: Test setting override on non-existent flag."""
        manager = FeatureFlagManager()
        manager._flags.clear()
        
        # Should return False and not crash
        success = manager.set_user_override("non_existent", "user", True)
        assert success is False
        
        success = manager.remove_user_override("non_existent", "user")
        assert success is False