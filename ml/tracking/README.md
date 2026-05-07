# MLflow Experiment Tracking

This module provides a wrapper around MLflow for experiment tracking, model logging, and model registry operations in the AgentICTrader ML pipeline.

## Overview

The MLflow tracking client manages three predefined experiments:

1. **regime-classifier**: Market regime classification (TRENDING_BULLISH, TRENDING_BEARISH, RANGING, BREAKOUT, NEWS_DRIVEN)
2. **pattern-detector**: Price action pattern detection (BOS, CHoCH, FVG, LIQUIDITY_SWEEP, etc.)
3. **confluence-scorer**: Setup confluence scoring to generate confidence values (0.0-1.0)

## Installation

MLflow is included in the project requirements:

```bash
pip install mlflow>=2.11.0
```

## Configuration

Set the MLflow tracking URI via environment variable:

```bash
export MLFLOW_TRACKING_URI=http://localhost:5000
```

Or in `.env`:

```
MLFLOW_TRACKING_URI=http://localhost:5000
```

## Usage

### Basic Example

```python
from ml.tracking.mlflow_client import MLflowTracker

# Initialize tracker
tracker = MLflowTracker()

# Start a run
with tracker.start_run(experiment_name="regime-classifier", run_name="xgb_v1"):
    # Log hyperparameters
    tracker.log_params({
        "learning_rate": 0.01,
        "max_depth": 5,
        "n_estimators": 100
    })
    
    # Log metrics
    tracker.log_metrics({
        "accuracy": 0.85,
        "f1_score": 0.82,
        "precision": 0.88
    })
    
    # Log model
    tracker.log_model(model, "model")
    
    # Register model
    tracker.register_model("runs:/run_id/model", "regime-classifier")
```

### Walk-Forward Validation Example

```python
from ml.tracking.mlflow_client import MLflowTracker

tracker = MLflowTracker()

for fold in range(8):
    with tracker.start_run(
        experiment_name="pattern-detector",
        run_name=f"fold_{fold}"
    ):
        # Train model
        model = train_model(X_train, y_train)
        
        # Evaluate
        metrics = evaluate_model(model, X_test, y_test)
        
        # Log everything
        tracker.log_params({"fold": fold, **hyperparams})
        tracker.log_metrics(metrics)
        tracker.log_model(model, "model")
```

## Predefined Experiments

The module defines three experiment names as constants:

```python
from ml.tracking.mlflow_client import EXPERIMENT_NAMES

print(EXPERIMENT_NAMES)
# ['regime-classifier', 'pattern-detector', 'confluence-scorer']
```

## API Reference

### MLflowTracker

#### `__init__(tracking_uri: Optional[str] = None)`

Initialize the MLflow tracker.

**Parameters:**
- `tracking_uri`: MLflow tracking server URI (defaults to `MLFLOW_TRACKING_URI` env var or `http://localhost:5000`)

#### `get_or_create_experiment(experiment_name: str) -> str`

Get existing experiment or create a new one.

**Returns:** Experiment ID

#### `start_run(experiment_name: str, run_name: Optional[str] = None, **kwargs)`

Start an MLflow run as a context manager.

**Parameters:**
- `experiment_name`: Name of the experiment
- `run_name`: Optional name for the run
- `**kwargs`: Additional arguments passed to `mlflow.start_run`

#### `log_params(params: Dict[str, Any]) -> None`

Log parameters to the current active run.

#### `log_metrics(metrics: Dict[str, float]) -> None`

Log metrics to the current active run.

#### `log_model(model: Any, artifact_path: str, **kwargs) -> None`

Log a model to the current active run.

#### `register_model(model_uri: str, model_name: str) -> None`

Register a model to the MLflow model registry.

## Testing

Run the test suite:

```bash
pytest backend/tests/test_mlflow_client.py -v
```

All tests follow TDD RED → GREEN → REFACTOR methodology.

## MLflow UI

Start the MLflow UI to view experiments:

```bash
mlflow ui --host 0.0.0.0 --port 5000
```

Then navigate to http://localhost:5000

## Integration with Docker

The MLflow tracking server is included in the docker-compose setup. See `docker/docker-compose.yml` for configuration.

## Next Steps

- Task 20: Train and validate Regime Classifier
- Task 21: Train and validate Pattern Detector
- Task 22: Train and validate Confluence Scorer

All model training tasks will use this MLflow tracking client for experiment management.
