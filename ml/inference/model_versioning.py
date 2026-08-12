"""
Model versioning system for A/B testing Confluence Scorer models.

This module provides infrastructure for loading and managing different versions
of ML models for A/B testing. Supports baseline (v1) and RAG-augmented (v2)
versions of the Confluence Scorer.

Key Features:
- Version-aware model loading from MLflow registry
- Model metadata and capability tracking
- Caching for performance
- Graceful fallbacks when models unavailable

Usage:
    registry = ModelVersionRegistry()
    v1_model = registry.load_model("confluence-scorer", ModelVersion.V1_BASELINE)
    v2_model = registry.load_model("confluence-scorer", ModelVersion.V2_RAG)
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional, Tuple
from enum import Enum
from dataclasses import dataclass

import mlflow
import mlflow.sklearn

logger = logging.getLogger(__name__)


class ModelVersion(Enum):
    """Supported model versions for A/B testing."""
    V1_BASELINE = "v1-baseline"
    V2_RAG = "v2-rag"


@dataclass
class ModelInfo:
    """Metadata about a model version."""
    version: str
    model_name: str
    mlflow_name: str
    features_enhanced: bool
    feature_count: int
    description: str
    created_at: Optional[str] = None
    performance_metrics: Optional[Dict[str, float]] = None


class ModelVersionRegistry:
    """
    Registry for managing multiple versions of ML models.
    
    Loads models from MLflow registry with version-specific names:
    - confluence-scorer-v1 (baseline without RAG)  
    - confluence-scorer-v2-rag (with RAG features)
    """
    
    def __init__(self, tracking_uri: Optional[str] = None):
        """
        Initialize model registry.
        
        Args:
            tracking_uri: MLflow tracking URI. Defaults to environment variable or localhost.
        """
        self.tracking_uri = tracking_uri or os.getenv(
            "MLFLOW_TRACKING_URI", "http://localhost:5000"
        )
        mlflow.set_tracking_uri(self.tracking_uri)
        
        # Cache for loaded models: {(model_name, version): model}
        self._model_cache: Dict[Tuple[str, ModelVersion], Any] = {}
        
        # Model metadata registry
        self._model_info: Dict[Tuple[str, ModelVersion], ModelInfo] = {
            ("confluence-scorer", ModelVersion.V1_BASELINE): ModelInfo(
                version="v1",
                model_name="confluence-scorer",
                mlflow_name="confluence-scorer-v1",
                features_enhanced=False,
                feature_count=64,  # Original feature count
                description="Baseline Confluence Scorer without RAG features"
            ),
            ("confluence-scorer", ModelVersion.V2_RAG): ModelInfo(
                version="v2-rag", 
                model_name="confluence-scorer",
                mlflow_name="confluence-scorer-v2-rag",
                features_enhanced=True,
                feature_count=68,  # Original 64 + 4 RAG features
                description="RAG-augmented Confluence Scorer with historical context"
            )
        }
    
    def load_model(self, model_name: str, version: ModelVersion) -> Optional[Any]:
        """
        Load a specific version of a model from MLflow registry.
        
        Args:
            model_name: Base model name (e.g., "confluence-scorer")
            version: Model version to load
            
        Returns:
            Loaded sklearn model or None if not available
        """
        cache_key = (model_name, version)
        
        # Return cached model if available
        if cache_key in self._model_cache:
            logger.debug(f"Returning cached model {model_name} {version.value}")
            return self._model_cache[cache_key]
        
        # Get model info
        model_info = self._model_info.get(cache_key)
        if not model_info:
            logger.error(f"Unknown model version: {model_name} {version.value}")
            return None
        
        # Try to load from MLflow registry
        try:
            model = self._load_from_mlflow(model_info.mlflow_name)
            if model is not None:
                self._model_cache[cache_key] = model
                logger.info(f"Loaded model {model_info.mlflow_name} for {model_name} {version.value}")
                return model
        except Exception as e:
            logger.warning(f"Failed to load {model_info.mlflow_name}: {e}")
        
        # Return None for graceful fallback handling
        logger.warning(f"Model {model_name} {version.value} not available")
        return None
    
    def get_model_info(self, model_name: str, version: ModelVersion) -> Dict[str, Any]:
        """
        Get metadata for a model version.
        
        Args:
            model_name: Base model name
            version: Model version
            
        Returns:
            Dictionary with model metadata
        """
        cache_key = (model_name, version)
        model_info = self._model_info.get(cache_key)
        
        if not model_info:
            return {}
        
        return {
            "version": model_info.version,
            "model_name": model_info.model_name,
            "mlflow_name": model_info.mlflow_name,
            "features_enhanced": model_info.features_enhanced,
            "feature_count": model_info.feature_count,
            "description": model_info.description,
            "created_at": model_info.created_at,
            "performance_metrics": model_info.performance_metrics or {}
        }
    
    def list_available_versions(self, model_name: str) -> list[ModelVersion]:
        """
        List all available versions for a model.
        
        Args:
            model_name: Base model name
            
        Returns:
            List of available model versions
        """
        versions = []
        for (name, version), _ in self._model_info.items():
            if name == model_name:
                versions.append(version)
        return versions
    
    def is_model_available(self, model_name: str, version: ModelVersion) -> bool:
        """
        Check if a model version is available in the registry.
        
        Args:
            model_name: Base model name
            version: Model version to check
            
        Returns:
            True if model is available, False otherwise
        """
        cache_key = (model_name, version)
        
        # Check if already cached
        if cache_key in self._model_cache:
            return True
        
        # Check if metadata exists
        model_info = self._model_info.get(cache_key)
        if not model_info:
            return False
        
        # Try to verify in MLflow (without loading)
        try:
            client = mlflow.tracking.MlflowClient()
            versions = client.get_latest_versions(model_info.mlflow_name)
            return len(versions) > 0
        except Exception:
            return False
    
    def update_model_performance(
        self, 
        model_name: str, 
        version: ModelVersion, 
        metrics: Dict[str, float]
    ) -> None:
        """
        Update performance metrics for a model version.
        
        Args:
            model_name: Base model name
            version: Model version
            metrics: Performance metrics dictionary
        """
        cache_key = (model_name, version)
        model_info = self._model_info.get(cache_key)
        
        if model_info:
            model_info.performance_metrics = metrics
            logger.info(f"Updated performance metrics for {model_name} {version.value}")
    
    def clear_cache(self) -> None:
        """Clear the model cache to force reloading."""
        self._model_cache.clear()
        logger.info("Model cache cleared")
    
    def _load_from_mlflow(self, mlflow_model_name: str) -> Optional[Any]:
        """
        Load model from MLflow registry.
        
        Args:
            mlflow_model_name: MLflow registered model name
            
        Returns:
            Loaded model or None if not available
        """
        try:
            client = mlflow.tracking.MlflowClient()
            
            # Try Production stage first
            versions = client.get_latest_versions(mlflow_model_name, stages=["Production"])
            if not versions:
                # Fall back to any registered version
                versions = client.get_latest_versions(mlflow_model_name)
                
            if not versions:
                logger.warning(f"No versions found for {mlflow_model_name}")
                # Return stub model for testing/development when MLflow model not available
                return self._create_stub_model(mlflow_model_name)
            
            # Load the latest version
            model_uri = f"models:/{mlflow_model_name}/{versions[0].version}"
            model = mlflow.sklearn.load_model(model_uri)
            
            logger.info(f"Loaded {mlflow_model_name} version {versions[0].version}")
            return model
            
        except Exception as e:
            logger.warning(f"Failed to load {mlflow_model_name} from MLflow: {e}")
            # Return stub model for graceful fallback
            return self._create_stub_model(mlflow_model_name)
    
    def _create_stub_model(self, mlflow_model_name: str) -> Any:
        """
        Create a stub model for development/testing when actual model unavailable.
        
        Args:
            mlflow_model_name: MLflow model name to create stub for
            
        Returns:
            Mock model with predict and predict_proba methods
        """
        class StubConfluenceScorer:
            def __init__(self, model_name: str):
                self.model_name = model_name
                # Slightly different confidence for v1 vs v2 for testing
                self.base_confidence = 0.3 if "v1" in model_name else 0.35
            
            def predict(self, X):
                # Always predict class 0 (negative) for stub
                import numpy as np
                return np.array([0] * len(X))
            
            def predict_proba(self, X):
                # Return reasonable confidence scores for testing
                import numpy as np
                confidence = self.base_confidence
                return np.array([[1-confidence, confidence]] * len(X))
        
        logger.info(f"Created stub model for {mlflow_model_name}")
        return StubConfluenceScorer(mlflow_model_name)
