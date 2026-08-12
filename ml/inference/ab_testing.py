"""
A/B testing framework for ML model variants.

This module provides traffic splitting, model selection, and metrics collection
for A/B testing different versions of ML models. Supports sticky sessions and
configurable split ratios.

Key Features:
- Deterministic user assignment based on user ID hash
- Sticky sessions (same user always gets same variant)
- Configurable split ratios
- Feature flag integration
- Per-variant metrics collection
- Integration with inference engine

Usage:
    framework = ABTestingFramework(split_ratio=0.5)
    model_version, model = framework.get_model_for_user("user123")
    result = framework.predict_with_ab_testing("user123", "EURUSD", "M5", candles)
"""
from __future__ import annotations

import hashlib
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from collections import defaultdict

from ml.inference.model_versioning import ModelVersionRegistry, ModelVersion
from ml.inference.feature_flags import get_feature_flags

logger = logging.getLogger(__name__)


@dataclass
class VariantMetrics:
    """Metrics for a specific model variant in A/B test."""
    prediction_count: int = 0
    total_confidence: float = 0.0
    wins: int = 0
    losses: int = 0
    total_r_multiple: float = 0.0
    predictions: List[Dict[str, Any]] = field(default_factory=list)
    
    @property
    def avg_confidence(self) -> float:
        """Average confidence score."""
        return self.total_confidence / max(1, self.prediction_count)
    
    @property
    def win_rate(self) -> float:
        """Win rate percentage."""
        total_outcomes = self.wins + self.losses
        return self.wins / max(1, total_outcomes)
    
    @property
    def avg_r_multiple(self) -> float:
        """Average R-multiple."""
        return self.total_r_multiple / max(1, self.prediction_count)


class TrafficSplitter:
    """
    Handles traffic splitting for A/B testing with sticky sessions.
    
    Uses deterministic hashing of user ID to ensure consistent assignment
    across sessions while maintaining the desired split ratio.
    """
    
    def __init__(self, split_ratio: float = 0.5):
        """
        Initialize traffic splitter.
        
        Args:
            split_ratio: Fraction of traffic to send to variant B (0.0 to 1.0)
        """
        if not 0.0 <= split_ratio <= 1.0:
            raise ValueError("split_ratio must be between 0.0 and 1.0")
        
        self.split_ratio = split_ratio
        logger.info(f"Traffic splitter initialized with {split_ratio:.1%} split to v2")
    
    def get_model_version(self, user_id: str) -> ModelVersion:
        """
        Get model version assignment for a user.
        
        Uses deterministic hashing to ensure same user always gets same variant.
        
        Args:
            user_id: Unique identifier for the user
            
        Returns:
            Model version assignment (V1_BASELINE or V2_RAG)
        """
        # Create deterministic hash from user ID
        hash_value = int(hashlib.md5(user_id.encode()).hexdigest(), 16)
        
        # Convert to 0.0-1.0 range
        hash_fraction = (hash_value % 1000000) / 1000000.0
        
        # Assign based on split ratio
        if hash_fraction < self.split_ratio:
            return ModelVersion.V2_RAG
        else:
            return ModelVersion.V1_BASELINE
    
    def get_assignment_info(self, user_id: str) -> Dict[str, Any]:
        """
        Get detailed assignment information for a user.
        
        Args:
            user_id: User identifier
            
        Returns:
            Dictionary with assignment details
        """
        version = self.get_model_version(user_id)
        hash_value = int(hashlib.md5(user_id.encode()).hexdigest(), 16)
        hash_fraction = (hash_value % 1000000) / 1000000.0
        
        return {
            "user_id": user_id,
            "assigned_version": version.value,
            "hash_fraction": hash_fraction,
            "split_ratio": self.split_ratio,
            "assignment_reason": "hash_based_sticky_session"
        }


class ABTestingFramework:
    """
    Complete A/B testing framework for ML model variants.
    
    Integrates traffic splitting, model loading, feature flags,
    and metrics collection for comprehensive A/B testing.
    """
    
    def __init__(
        self, 
        split_ratio: float = 0.5,
        feature_flag_key: str = "confluence_scorer_ab_test",
        tracking_uri: Optional[str] = None
    ):
        """
        Initialize A/B testing framework.
        
        Args:
            split_ratio: Fraction of traffic for variant B
            feature_flag_key: Feature flag key to enable/disable A/B test
            tracking_uri: MLflow tracking URI for model loading
        """
        self.split_ratio = split_ratio
        self.feature_flag_key = feature_flag_key
        
        # Initialize components
        self.model_registry = ModelVersionRegistry(tracking_uri)
        self.traffic_splitter = TrafficSplitter(split_ratio)
        
        # Metrics storage
        self._variant_metrics: Dict[ModelVersion, VariantMetrics] = {
            ModelVersion.V1_BASELINE: VariantMetrics(),
            ModelVersion.V2_RAG: VariantMetrics()
        }
        
        # Assignment cache for debugging
        self._assignments: Dict[str, Tuple[ModelVersion, float]] = {}
        
        logger.info(f"A/B testing framework initialized with {split_ratio:.1%} v2 traffic")
    
    def get_model_for_user(self, user_id: str) -> Tuple[ModelVersion, Optional[Any]]:
        """
        Get the appropriate model version and instance for a user.
        
        Args:
            user_id: User identifier
            
        Returns:
            Tuple of (model_version, model_instance)
        """
        # Check feature flag first
        if not self._is_feature_flag_enabled(user_id):
            logger.debug(f"A/B test disabled by feature flag, using v1 for {user_id}")
            version = ModelVersion.V1_BASELINE
        else:
            # Get assignment from traffic splitter
            version = self.traffic_splitter.get_model_version(user_id)
            logger.debug(f"User {user_id} assigned to {version.value}")
        
        # Cache assignment for debugging
        self._assignments[user_id] = (version, time.time())
        
        # Load model
        model = self.model_registry.load_model("confluence-scorer", version)
        
        if model is None:
            # Fallback to baseline if target model unavailable
            logger.warning(f"Model {version.value} unavailable, falling back to v1")
            version = ModelVersion.V1_BASELINE
            model = self.model_registry.load_model("confluence-scorer", version)
            
            # If even baseline is unavailable, we'll return None and let caller handle
            if model is None:
                logger.error("No models available, returning None")
        
        return version, model
    
    def record_prediction(
        self,
        user_id: str,
        model_version: ModelVersion,
        confidence_score: float,
        outcome: Optional[str] = None,
        r_multiple: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Record a prediction for metrics collection.
        
        Args:
            user_id: User identifier
            model_version: Model version used
            confidence_score: Prediction confidence
            outcome: Trade outcome ("WIN", "LOSS", or None if pending)
            r_multiple: Risk-reward multiple
            metadata: Additional prediction metadata
        """
        metrics = self._variant_metrics[model_version]
        
        # Update counters
        metrics.prediction_count += 1
        metrics.total_confidence += confidence_score
        
        # Update outcome tracking
        if outcome == "WIN":
            metrics.wins += 1
        elif outcome == "LOSS":
            metrics.losses += 1
        
        # Update R-multiple tracking
        if r_multiple is not None:
            metrics.total_r_multiple += r_multiple
        
        # Store detailed prediction record
        prediction_record = {
            "user_id": user_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "confidence_score": confidence_score,
            "outcome": outcome,
            "r_multiple": r_multiple,
            "metadata": metadata or {}
        }
        metrics.predictions.append(prediction_record)
        
        # Trim predictions list if it gets too large (keep last 1000)
        if len(metrics.predictions) > 1000:
            metrics.predictions = metrics.predictions[-1000:]
        
        logger.debug(f"Recorded prediction for {user_id} on {model_version.value}")
    
    def get_variant_metrics(self, model_version: ModelVersion) -> Dict[str, Any]:
        """
        Get metrics for a specific model variant.
        
        Args:
            model_version: Model version to get metrics for
            
        Returns:
            Dictionary with variant metrics
        """
        metrics = self._variant_metrics[model_version]
        
        return {
            "model_version": model_version.value,
            "prediction_count": metrics.prediction_count,
            "avg_confidence": metrics.avg_confidence,
            "win_rate": metrics.win_rate,
            "avg_r_multiple": metrics.avg_r_multiple,
            "total_outcomes": metrics.wins + metrics.losses,
            "wins": metrics.wins,
            "losses": metrics.losses,
            "last_updated": datetime.now(timezone.utc).isoformat()
        }
    
    def get_ab_test_summary(self) -> Dict[str, Any]:
        """
        Get complete A/B test summary with both variants.
        
        Returns:
            Dictionary with A/B test summary
        """
        v1_metrics = self.get_variant_metrics(ModelVersion.V1_BASELINE)
        v2_metrics = self.get_variant_metrics(ModelVersion.V2_RAG)
        
        # Calculate statistical significance if we have enough data
        statistical_significance = self._calculate_significance(
            v1_metrics, v2_metrics
        )
        
        return {
            "ab_test_active": self._is_feature_flag_enabled(),
            "split_ratio": self.split_ratio,
            "variant_a": v1_metrics,
            "variant_b": v2_metrics,
            "total_users_assigned": len(self._assignments),
            "statistical_significance": statistical_significance,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
    
    def predict_with_ab_testing(
        self,
        user_id: str,
        instrument: str,
        timeframe: str,
        candles: List[Dict[str, Any]],
        **kwargs
    ) -> Dict[str, Any]:
        """
        Run prediction with A/B testing model selection.
        
        Args:
            user_id: User identifier for variant assignment
            instrument: Trading instrument
            timeframe: Timeframe
            candles: OHLCV candles
            **kwargs: Additional parameters for prediction
            
        Returns:
            Prediction result with model version info
        """
        # Get model for user
        model_version, model = self.get_model_for_user(user_id)
        
        if model is None:
            raise RuntimeError("No model available for prediction")
        
        # Import here to avoid circular dependency
        from ml.inference.main import InferenceEngine
        
        # Create inference engine with the selected model version
        # This is a simplified approach - in production, you'd want to create
        # a version-aware inference engine
        engine = InferenceEngine(self.model_registry)
        
        # Override the model in the engine's registry for this prediction
        engine.registry._model_cache[("confluence-scorer", model_version)] = model
        
        try:
            # Run prediction
            result = engine.predict(
                instrument=instrument,
                timeframe=timeframe,
                candles=candles,
                **kwargs
            )
            
            # Add A/B testing metadata
            result["model_version"] = model_version.value
            result["ab_test_active"] = self._is_feature_flag_enabled(user_id)
            result["prediction_time"] = datetime.now(timezone.utc).isoformat()
            
            # Record prediction for metrics
            self.record_prediction(
                user_id=user_id,
                model_version=model_version,
                confidence_score=result["confidence_score"],
                metadata={
                    "instrument": instrument,
                    "timeframe": timeframe,
                    "regime": result["regime"],
                    "patterns": result["patterns"]
                }
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Prediction failed for user {user_id}: {e}")
            raise
    
    def _is_feature_flag_enabled(self, user_id: Optional[str] = None) -> bool:
        """
        Check if A/B test feature flag is enabled.
        
        Args:
            user_id: Optional user ID for user-specific overrides
            
        Returns:
            True if feature flag is enabled, False otherwise
        """
        try:
            feature_flags = get_feature_flags()
            return feature_flags.is_enabled(self.feature_flag_key, user_id)
        except Exception as e:
            logger.warning(f"Feature flag check failed: {e}, defaulting to False")
            return False
    
    def _calculate_significance(
        self, 
        v1_metrics: Dict[str, Any], 
        v2_metrics: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Calculate statistical significance between variants.
        
        Args:
            v1_metrics: Variant A metrics
            v2_metrics: Variant B metrics
            
        Returns:
            Statistical significance results
        """
        # Simple implementation - in production use proper statistical tests
        min_sample_size = 100
        
        v1_count = v1_metrics["prediction_count"]
        v2_count = v2_metrics["prediction_count"]
        
        if v1_count < min_sample_size or v2_count < min_sample_size:
            return {
                "significant": False,
                "reason": "insufficient_data",
                "min_sample_size": min_sample_size,
                "v1_count": v1_count,
                "v2_count": v2_count
            }
        
        # Compare win rates
        v1_win_rate = v1_metrics["win_rate"]
        v2_win_rate = v2_metrics["win_rate"]
        improvement = (v2_win_rate - v1_win_rate) / max(0.01, v1_win_rate)
        
        # Simple threshold-based significance (5% improvement)
        significant = abs(improvement) > 0.05
        
        return {
            "significant": significant,
            "improvement_pct": improvement * 100,
            "v1_win_rate": v1_win_rate,
            "v2_win_rate": v2_win_rate,
            "confidence_level": 0.95 if significant else 0.0,
            "method": "threshold_based"
        }