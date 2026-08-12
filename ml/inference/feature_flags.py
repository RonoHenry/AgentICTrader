"""
Feature flag management system for A/B testing and gradual rollouts.

This module provides a centralized feature flag system for controlling
A/B tests, model rollouts, and other feature toggles in the ML inference service.

Key Features:
- Environment variable based flags
- User-specific overrides
- Percentage-based rollouts
- Runtime flag updates
- Integration with A/B testing framework

Usage:
    flags = FeatureFlagManager()
    if flags.is_enabled("confluence_scorer_ab_test", user_id="user123"):
        # Use A/B testing
    else:
        # Use baseline
"""
from __future__ import annotations

import logging
import os
from typing import Dict, Any, Optional, Set
from dataclasses import dataclass
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


@dataclass
class FeatureFlag:
    """Definition of a feature flag."""
    key: str
    enabled: bool
    description: str
    rollout_percentage: float = 100.0
    user_overrides: Dict[str, bool] = None
    created_at: str = None
    
    def __post_init__(self):
        if self.user_overrides is None:
            self.user_overrides = {}
        if self.created_at is None:
            self.created_at = datetime.now(timezone.utc).isoformat()


class FeatureFlagManager:
    """
    Manages feature flags for A/B testing and gradual rollouts.
    
    Supports:
    - Environment variable configuration
    - User-specific overrides
    - Percentage-based rollouts
    - Runtime updates
    """
    
    def __init__(self):
        """Initialize feature flag manager."""
        self._flags: Dict[str, FeatureFlag] = {}
        self._load_from_environment()
    
    def is_enabled(
        self, 
        flag_key: str, 
        user_id: Optional[str] = None,
        default: bool = False
    ) -> bool:
        """
        Check if a feature flag is enabled for a user.
        
        Args:
            flag_key: Feature flag key
            user_id: Optional user ID for user-specific overrides
            default: Default value if flag not found
            
        Returns:
            True if flag is enabled, False otherwise
        """
        flag = self._flags.get(flag_key)
        
        if flag is None:
            # Try environment variable as fallback
            env_value = os.getenv(flag_key, str(default)).lower()
            return env_value in ("true", "1", "yes", "on")
        
        # Check user-specific override first
        if user_id and user_id in flag.user_overrides:
            logger.debug(f"Using user override for {flag_key}: {flag.user_overrides[user_id]}")
            return flag.user_overrides[user_id]
        
        # If flag globally disabled, return False
        if not flag.enabled:
            return False
        
        # Check rollout percentage for gradual rollouts
        if flag.rollout_percentage < 100.0 and user_id:
            # Use hash of user_id to determine if user is in rollout
            import hashlib
            hash_value = int(hashlib.md5(user_id.encode()).hexdigest(), 16)
            user_percentage = (hash_value % 1000) / 10.0  # 0.0 to 99.9
            
            enabled = user_percentage < flag.rollout_percentage
            logger.debug(
                f"Rollout check for {flag_key}: user_pct={user_percentage:.1f}, "
                f"rollout_pct={flag.rollout_percentage}, enabled={enabled}"
            )
            return enabled
        
        return flag.enabled
    
    def register_flag(
        self, 
        key: str, 
        enabled: bool = False,
        description: str = "",
        rollout_percentage: float = 100.0
    ) -> None:
        """
        Register a new feature flag.
        
        Args:
            key: Unique flag key
            enabled: Default enabled state
            description: Flag description
            rollout_percentage: Percentage rollout (0-100)
        """
        if key in self._flags:
            logger.warning(f"Flag {key} already registered, updating")
        
        self._flags[key] = FeatureFlag(
            key=key,
            enabled=enabled,
            description=description,
            rollout_percentage=rollout_percentage
        )
        
        logger.info(f"Registered flag {key}: enabled={enabled}, rollout={rollout_percentage}%")
    
    def update_flag(
        self, 
        key: str, 
        enabled: Optional[bool] = None,
        rollout_percentage: Optional[float] = None
    ) -> bool:
        """
        Update an existing feature flag.
        
        Args:
            key: Flag key
            enabled: New enabled state
            rollout_percentage: New rollout percentage
            
        Returns:
            True if flag was updated, False if not found
        """
        flag = self._flags.get(key)
        if not flag:
            logger.warning(f"Cannot update unknown flag: {key}")
            return False
        
        if enabled is not None:
            flag.enabled = enabled
            logger.info(f"Updated {key} enabled: {enabled}")
        
        if rollout_percentage is not None:
            flag.rollout_percentage = rollout_percentage  
            logger.info(f"Updated {key} rollout: {rollout_percentage}%")
        
        return True
    
    def set_user_override(self, flag_key: str, user_id: str, enabled: bool) -> bool:
        """
        Set user-specific override for a flag.
        
        Args:
            flag_key: Flag key
            user_id: User ID
            enabled: Override value
            
        Returns:
            True if override was set, False if flag not found
        """
        flag = self._flags.get(flag_key)
        if not flag:
            logger.warning(f"Cannot set override for unknown flag: {flag_key}")
            return False
        
        flag.user_overrides[user_id] = enabled
        logger.info(f"Set override for {flag_key}, user {user_id}: {enabled}")
        return True
    
    def remove_user_override(self, flag_key: str, user_id: str) -> bool:
        """
        Remove user-specific override.
        
        Args:
            flag_key: Flag key
            user_id: User ID
            
        Returns:
            True if override was removed, False otherwise
        """
        flag = self._flags.get(flag_key)
        if not flag or user_id not in flag.user_overrides:
            return False
        
        del flag.user_overrides[user_id]
        logger.info(f"Removed override for {flag_key}, user {user_id}")
        return True
    
    def get_flag_info(self, flag_key: str) -> Optional[Dict[str, Any]]:
        """
        Get detailed information about a flag.
        
        Args:
            flag_key: Flag key
            
        Returns:
            Flag information dictionary or None if not found
        """
        flag = self._flags.get(flag_key)
        if not flag:
            return None
        
        return {
            "key": flag.key,
            "enabled": flag.enabled,
            "description": flag.description,
            "rollout_percentage": flag.rollout_percentage,
            "user_override_count": len(flag.user_overrides),
            "created_at": flag.created_at
        }
    
    def list_flags(self) -> Dict[str, Dict[str, Any]]:
        """
        List all registered flags.
        
        Returns:
            Dictionary of flag information
        """
        return {
            key: {
                "enabled": flag.enabled,
                "description": flag.description,
                "rollout_percentage": flag.rollout_percentage,
                "user_override_count": len(flag.user_overrides)
            }
            for key, flag in self._flags.items()
        }
    
    def _load_from_environment(self) -> None:
        """Load default flags from environment variables."""
        # Register A/B testing flags
        self.register_flag(
            key="confluence_scorer_ab_test",
            enabled=os.getenv("CONFLUENCE_SCORER_AB_TEST", "false").lower() in ("true", "1", "yes"),
            description="A/B test between baseline and RAG-augmented Confluence Scorer",
            rollout_percentage=self._safe_float_from_env("CONFLUENCE_SCORER_AB_TEST_ROLLOUT", "100.0")
        )
        
        # Register other ML-related flags
        self.register_flag(
            key="rag_features_enabled",
            enabled=os.getenv("RAG_FEATURES_ENABLED", "false").lower() in ("true", "1", "yes"),
            description="Enable RAG features in ML pipeline",
            rollout_percentage=self._safe_float_from_env("RAG_FEATURES_ROLLOUT", "100.0")
        )
        
        self.register_flag(
            key="enhanced_reasoning_enabled",
            enabled=os.getenv("ENHANCED_REASONING_ENABLED", "false").lower() in ("true", "1", "yes"),
            description="Enable enhanced LLM reasoning with RAG context",
            rollout_percentage=self._safe_float_from_env("ENHANCED_REASONING_ROLLOUT", "50.0")
        )
        
        logger.info(f"Loaded {len(self._flags)} feature flags from environment")
    
    def _safe_float_from_env(self, env_var: str, default: str) -> float:
        """Safely convert environment variable to float."""
        try:
            value = os.getenv(env_var, default)
            return float(value)
        except ValueError:
            logger.warning(f"Invalid float value for {env_var}: {value}, using default {default}")
            return float(default)


# Global feature flag manager instance
_feature_flags: Optional[FeatureFlagManager] = None


def get_feature_flags() -> FeatureFlagManager:
    """
    Get the global feature flag manager instance.
    
    Returns:
        FeatureFlagManager instance
    """
    global _feature_flags
    if _feature_flags is None:
        _feature_flags = FeatureFlagManager()
    return _feature_flags


def is_feature_enabled(flag_key: str, user_id: Optional[str] = None) -> bool:
    """
    Convenience function to check if a feature flag is enabled.
    
    Args:
        flag_key: Feature flag key
        user_id: Optional user ID
        
    Returns:
        True if feature is enabled, False otherwise
    """
    return get_feature_flags().is_enabled(flag_key, user_id)