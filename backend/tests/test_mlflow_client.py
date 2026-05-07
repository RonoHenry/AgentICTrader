"""
Tests for MLflow experiment tracking client.

Following TDD RED → GREEN → REFACTOR:
- RED: All tests should FAIL initially (no implementation exists)
- GREEN: Minimal implementation to make tests pass
- REFACTOR: Clean up while keeping tests green
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import mlflow
from mlflow.tracking import MlflowClient
from mlflow.exceptions import MlflowException


@pytest.fixture
def mock_mlflow_client():
    """Mock MLflow client for testing."""
    with patch('mlflow.tracking.MlflowClient') as mock_client:
        yield mock_client


@pytest.fixture
def mock_mlflow():
    """Mock mlflow module functions."""
    with patch('mlflow.set_tracking_uri') as mock_set_uri, \
         patch('mlflow.set_experiment') as mock_set_exp, \
         patch('mlflow.log_params') as mock_log_params, \
         patch('mlflow.log_metrics') as mock_log_metrics, \
         patch('mlflow.log_model') as mock_log_model, \
         patch('mlflow.register_model') as mock_register:
        yield {
            'set_tracking_uri': mock_set_uri,
            'set_experiment': mock_set_exp,
            'log_params': mock_log_params,
            'log_metrics': mock_log_metrics,
            'log_model': mock_log_model,
            'register_model': mock_register,
        }


class TestMLflowClient:
    """Test suite for MLflow experiment tracking client."""

    def test_mlflow_connection_succeeds(self, mock_mlflow_client):
        """
        Smoke test: MLflow connection succeeds.
        
        This test verifies that we can establish a connection to MLflow
        tracking server without errors.
        """
        from ml.tracking.mlflow_client import MLflowTracker
        
        # Mock successful connection
        mock_client_instance = Mock()
        mock_mlflow_client.return_value = mock_client_instance
        
        # Should not raise any exception
        tracker = MLflowTracker(tracking_uri="http://localhost:5000")
        
        # Verify connection was attempted
        mock_mlflow_client.assert_called_once()

    def test_experiment_created_with_correct_name(self):
        """
        Test: experiment created with correct name.
        
        Verifies that experiments are created with the expected names:
        - regime-classifier
        - pattern-detector
        - confluence-scorer
        """
        from ml.tracking.mlflow_client import MLflowTracker
        
        with patch('ml.tracking.mlflow_client.MlflowClient') as mock_client_class:
            mock_client_instance = Mock()
            mock_client_class.return_value = mock_client_instance
            
            # Mock get_experiment_by_name to return None (experiment doesn't exist)
            mock_client_instance.get_experiment_by_name.return_value = None
            mock_client_instance.create_experiment.return_value = "exp_123"
            
            with patch('ml.tracking.mlflow_client.mlflow.set_tracking_uri'):
                tracker = MLflowTracker(tracking_uri="http://localhost:5000")
            
            # Test creating regime-classifier experiment
            exp_id = tracker.get_or_create_experiment("regime-classifier")
            
            mock_client_instance.get_experiment_by_name.assert_called_with("regime-classifier")
            mock_client_instance.create_experiment.assert_called_with("regime-classifier")
            assert exp_id == "exp_123"

    def test_experiment_names_are_predefined(self):
        """
        Test: predefined experiment names are available.
        
        Verifies that the three required experiment names are defined:
        - regime-classifier
        - pattern-detector
        - confluence-scorer
        """
        from ml.tracking.mlflow_client import EXPERIMENT_NAMES
        
        assert "regime-classifier" in EXPERIMENT_NAMES
        assert "pattern-detector" in EXPERIMENT_NAMES
        assert "confluence-scorer" in EXPERIMENT_NAMES

    def test_log_params_works(self, mock_mlflow_client):
        """
        Test: log_params function works.
        
        Verifies that parameters can be logged to MLflow.
        """
        from ml.tracking.mlflow_client import MLflowTracker
        
        mock_client_instance = Mock()
        mock_mlflow_client.return_value = mock_client_instance
        
        tracker = MLflowTracker(tracking_uri="http://localhost:5000")
        
        # Mock active run
        with patch('mlflow.active_run') as mock_active_run:
            mock_run = Mock()
            mock_run.info.run_id = "run_123"
            mock_active_run.return_value = mock_run
            
            with patch('mlflow.log_params') as mock_log_params:
                params = {"learning_rate": 0.01, "max_depth": 5}
                tracker.log_params(params)
                
                mock_log_params.assert_called_once_with(params)

    def test_log_metrics_works(self, mock_mlflow_client):
        """
        Test: log_metrics function works.
        
        Verifies that metrics can be logged to MLflow.
        """
        from ml.tracking.mlflow_client import MLflowTracker
        
        mock_client_instance = Mock()
        mock_mlflow_client.return_value = mock_client_instance
        
        tracker = MLflowTracker(tracking_uri="http://localhost:5000")
        
        # Mock active run
        with patch('mlflow.active_run') as mock_active_run:
            mock_run = Mock()
            mock_run.info.run_id = "run_123"
            mock_active_run.return_value = mock_run
            
            with patch('mlflow.log_metrics') as mock_log_metrics:
                metrics = {"accuracy": 0.85, "f1_score": 0.82}
                tracker.log_metrics(metrics)
                
                mock_log_metrics.assert_called_once_with(metrics)

    def test_log_model_works(self, mock_mlflow_client):
        """
        Test: log_model function works.
        
        Verifies that models can be logged to MLflow.
        """
        from ml.tracking.mlflow_client import MLflowTracker
        
        mock_client_instance = Mock()
        mock_mlflow_client.return_value = mock_client_instance
        
        tracker = MLflowTracker(tracking_uri="http://localhost:5000")
        
        # Mock active run
        with patch('mlflow.active_run') as mock_active_run:
            mock_run = Mock()
            mock_run.info.run_id = "run_123"
            mock_active_run.return_value = mock_run
            
            with patch('mlflow.sklearn.log_model') as mock_log_model:
                mock_model = Mock()
                tracker.log_model(mock_model, "model")
                
                mock_log_model.assert_called_once_with(mock_model, "model")

    def test_register_model_works(self, mock_mlflow_client):
        """
        Test: register_model function works.
        
        Verifies that models can be registered to MLflow model registry.
        """
        from ml.tracking.mlflow_client import MLflowTracker
        
        mock_client_instance = Mock()
        mock_mlflow_client.return_value = mock_client_instance
        
        tracker = MLflowTracker(tracking_uri="http://localhost:5000")
        
        # Mock active run
        with patch('mlflow.active_run') as mock_active_run:
            mock_run = Mock()
            mock_run.info.run_id = "run_123"
            mock_active_run.return_value = mock_run
            
            with patch('mlflow.register_model') as mock_register:
                model_uri = "runs:/run_123/model"
                model_name = "regime-classifier"
                
                tracker.register_model(model_uri, model_name)
                
                mock_register.assert_called_once_with(model_uri, model_name)

    def test_start_run_context_manager(self, mock_mlflow_client):
        """
        Test: start_run works as context manager.
        
        Verifies that runs can be started and managed properly.
        """
        from ml.tracking.mlflow_client import MLflowTracker
        
        mock_client_instance = Mock()
        mock_mlflow_client.return_value = mock_client_instance
        
        tracker = MLflowTracker(tracking_uri="http://localhost:5000")
        
        with patch('mlflow.start_run') as mock_start_run:
            mock_run = MagicMock()
            mock_run.__enter__ = Mock(return_value=mock_run)
            mock_run.__exit__ = Mock(return_value=False)
            mock_start_run.return_value = mock_run
            
            with tracker.start_run(experiment_name="regime-classifier", run_name="test_run"):
                pass
            
            mock_start_run.assert_called_once()

    def test_get_existing_experiment(self):
        """
        Test: get existing experiment returns correct ID.
        
        Verifies that if an experiment already exists, its ID is returned
        without creating a new one.
        """
        from ml.tracking.mlflow_client import MLflowTracker
        
        with patch('ml.tracking.mlflow_client.MlflowClient') as mock_client_class:
            mock_client_instance = Mock()
            mock_client_class.return_value = mock_client_instance
            
            # Mock existing experiment
            mock_experiment = Mock()
            mock_experiment.experiment_id = "existing_exp_456"
            mock_client_instance.get_experiment_by_name.return_value = mock_experiment
            
            with patch('ml.tracking.mlflow_client.mlflow.set_tracking_uri'):
                tracker = MLflowTracker(tracking_uri="http://localhost:5000")
            
            exp_id = tracker.get_or_create_experiment("pattern-detector")
            
            # Should return existing ID without creating new experiment
            assert exp_id == "existing_exp_456"
            mock_client_instance.create_experiment.assert_not_called()

    def test_tracking_uri_is_set(self, mock_mlflow_client):
        """
        Test: tracking URI is properly set during initialization.
        
        Verifies that the MLflow tracking URI is configured correctly.
        """
        from ml.tracking.mlflow_client import MLflowTracker
        
        mock_client_instance = Mock()
        mock_mlflow_client.return_value = mock_client_instance
        
        with patch('mlflow.set_tracking_uri') as mock_set_uri:
            tracker = MLflowTracker(tracking_uri="http://localhost:5000")
            mock_set_uri.assert_called_once_with("http://localhost:5000")
