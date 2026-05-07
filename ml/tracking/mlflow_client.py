"""
MLflow experiment tracking client.

This module provides a wrapper around MLflow for:
- Experiment management
- Parameter and metric logging
- Model logging and registration
- Run management

The three predefined experiments align with the AgentICTrader ML pipeline:
1. regime-classifier: Classifies market regime (TRENDING_BULLISH, TRENDING_BEARISH, RANGING, etc.)
2. pattern-detector: Detects price action patterns (BOS, CHoCH, FVG, etc.)
3. confluence-scorer: Scores setup confluence to generate confidence values

Usage:
    tracker = MLflowTracker(tracking_uri="http://localhost:5000")
    
    with tracker.start_run(experiment_name="regime-classifier", run_name="xgb_v1"):
        tracker.log_params({"learning_rate": 0.01, "max_depth": 5})
        tracker.log_metrics({"accuracy": 0.85, "f1_score": 0.82})
        tracker.log_model(model, "model")
        tracker.register_model("runs:/run_id/model", "regime-classifier")
"""

import os
from contextlib import contextmanager
from typing import Any, Dict, Optional

import mlflow
from mlflow.tracking import MlflowClient


# Predefined experiment names for the three ML models in the AgentICTrader pipeline
EXPERIMENT_NAMES = [
    "regime-classifier",    # Market regime classification
    "pattern-detector",     # Price action pattern detection
    "confluence-scorer",    # Setup confluence scoring
]


class MLflowTracker:
    """
    Wrapper class for MLflow experiment tracking.
    
    Provides a simplified interface for:
    - Creating and managing experiments
    - Logging parameters, metrics, and models
    - Registering models to the model registry
    
    Attributes:
        tracking_uri: MLflow tracking server URI
        client: MLflow client instance for API operations
    """
    
    def __init__(self, tracking_uri: Optional[str] = None):
        """
        Initialize MLflow tracker.
        
        Args:
            tracking_uri: MLflow tracking server URI. 
                         Defaults to MLFLOW_TRACKING_URI env var or http://localhost:5000
        
        Example:
            # Use default tracking URI from environment
            tracker = MLflowTracker()
            
            # Use custom tracking URI
            tracker = MLflowTracker("http://mlflow.example.com:5000")
        """
        self.tracking_uri = tracking_uri or os.getenv(
            "MLFLOW_TRACKING_URI", "http://localhost:5000"
        )
        mlflow.set_tracking_uri(self.tracking_uri)
        self.client = MlflowClient()
    
    def get_or_create_experiment(self, experiment_name: str) -> str:
        """
        Get existing experiment or create a new one.
        
        Args:
            experiment_name: Name of the experiment
            
        Returns:
            Experiment ID
        """
        experiment = self.client.get_experiment_by_name(experiment_name)
        
        if experiment is not None:
            return experiment.experiment_id
        
        return self.client.create_experiment(experiment_name)
    
    @contextmanager
    def start_run(
        self, 
        experiment_name: str, 
        run_name: Optional[str] = None,
        **kwargs
    ):
        """
        Start an MLflow run as a context manager.
        
        Args:
            experiment_name: Name of the experiment
            run_name: Optional name for the run
            **kwargs: Additional arguments passed to mlflow.start_run
            
        Yields:
            MLflow run object
            
        Example:
            with tracker.start_run("regime-classifier", "xgb_v1"):
                tracker.log_params({"lr": 0.01})
                tracker.log_metrics({"acc": 0.85})
        """
        experiment_id = self.get_or_create_experiment(experiment_name)
        
        with mlflow.start_run(
            experiment_id=experiment_id,
            run_name=run_name,
            **kwargs
        ) as run:
            yield run
    
    def log_params(self, params: Dict[str, Any]) -> None:
        """
        Log parameters to the current active run.
        
        Args:
            params: Dictionary of parameter names and values
            
        Example:
            tracker.log_params({
                "learning_rate": 0.01,
                "max_depth": 5,
                "n_estimators": 100
            })
        """
        mlflow.log_params(params)
    
    def log_metrics(self, metrics: Dict[str, float]) -> None:
        """
        Log metrics to the current active run.
        
        Args:
            metrics: Dictionary of metric names and values
            
        Example:
            tracker.log_metrics({
                "accuracy": 0.85,
                "f1_score": 0.82,
                "precision": 0.88
            })
        """
        mlflow.log_metrics(metrics)
    
    def log_model(
        self, 
        model: Any, 
        artifact_path: str,
        **kwargs
    ) -> None:
        """
        Log a model to the current active run.
        
        Args:
            model: The model object to log (sklearn, xgboost, etc.)
            artifact_path: Path within the run's artifact directory
            **kwargs: Additional arguments passed to mlflow.sklearn.log_model
            
        Example:
            tracker.log_model(xgb_model, "model")
        """
        mlflow.sklearn.log_model(model, artifact_path, **kwargs)
    
    def register_model(
        self, 
        model_uri: str, 
        model_name: str
    ) -> None:
        """
        Register a model to the MLflow model registry.
        
        Args:
            model_uri: URI of the model (e.g., "runs:/run_id/model")
            model_name: Name to register the model under
            
        Example:
            tracker.register_model(
                "runs:/abc123/model",
                "regime-classifier"
            )
        """
        mlflow.register_model(model_uri, model_name)
