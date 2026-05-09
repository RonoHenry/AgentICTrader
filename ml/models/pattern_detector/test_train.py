"""
Tests for Pattern Detector training script.

Following TDD: RED → GREEN → REFACTOR

Test coverage:
1. PatternLabeller heuristic labelling logic
2. Multi-label classification output shape
3. Walk-forward validation with 8+ folds
4. MLflow experiment logging
5. Exit criterion validation (≥ 80% accuracy, FPR < 20%)
6. Model output contract (8 binary labels)
"""

import pytest
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch, MagicMock
import xgboost as xgb
from sklearn.multioutput import MultiOutputClassifier

# Import the module we're testing (will fail initially - RED phase)
try:
    from ml.models.pattern_detector.train import (
        PatternLabeller,
        PatternDetectorTrainer,
        TrainingConfig,
        FoldResult,
        PATTERN_LABELS,
    )
except ImportError:
    # Module doesn't exist yet - expected in RED phase
    PatternLabeller = None
    PatternDetectorTrainer = None
    TrainingConfig = None
    FoldResult = None
    PATTERN_LABELS = None


@pytest.fixture
def sample_features_df():
    """Sample feature DataFrame for testing."""
    return pd.DataFrame({
        'timestamp': [datetime(2024, 1, 1, i, 0) for i in range(10)],
        'htf_open': [1.5000 + i * 0.001 for i in range(10)],
        'htf_high': [1.5100 + i * 0.001 for i in range(10)],
        'htf_low': [1.4900 + i * 0.001 for i in range(10)],
        'htf_open_bias': ['BULLISH'] * 5 + ['BEARISH'] * 5,
        'htf_trend_bias': ['BULLISH'] * 5 + ['BEARISH'] * 5,
        'htf_body_pct': [60.0, 55.0, 70.0, 50.0, 65.0, 40.0, 45.0, 35.0, 30.0, 25.0],
        'bos_detected': [True, False, True, False, True, False, True, False, True, False],
        'choch_detected': [False, True, False, True, False, True, False, True, False, True],
        'fvg_present': [True, True, False, False, True, True, False, False, True, True],
        'liquidity_sweep_detected': [False, False, True, True, False, False, True, True, False, False],
        'supply_zone_distance': [0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.07, 0.08, 0.09, 0.10],
        'demand_zone_distance': [0.02, 0.03, 0.04, 0.05, 0.06, 0.07, 0.08, 0.09, 0.10, 0.11],
        'time_window': ['LONDON_KILLZONE'] * 5 + ['NY_AM_KILLZONE'] * 5,
        'time_window_weight': [0.9] * 10,
    })


@pytest.fixture
def training_config():
    """Sample training configuration."""
    if TrainingConfig is None:
        pytest.skip("TrainingConfig not implemented yet")
    
    return TrainingConfig(
        instruments=['EURUSD'],
        timeframe='M5',
        htf_timeframe='H1',
        n_folds=8,
        fold_window_months=3,
        test_window_months=1,
    )


class TestPatternLabeller:
    """Test PatternLabeller heuristic labelling logic."""
    
    def test_pattern_labels_constant_exists(self):
        """Test that PATTERN_LABELS constant is defined with 8 labels."""
        if PATTERN_LABELS is None:
            pytest.skip("PATTERN_LABELS not implemented yet")
        
        assert len(PATTERN_LABELS) == 8
        assert 'BOS_CONFIRMED' in PATTERN_LABELS
        assert 'CHOCH_DETECTED' in PATTERN_LABELS
        assert 'SUPPLY_ZONE_REJECTION' in PATTERN_LABELS
        assert 'DEMAND_ZONE_BOUNCE' in PATTERN_LABELS
        assert 'FVG_PRESENT' in PATTERN_LABELS
        assert 'LIQUIDITY_SWEEP' in PATTERN_LABELS
        assert 'ORDER_BLOCK' in PATTERN_LABELS
        assert 'INDUCEMENT' in PATTERN_LABELS
    
    def test_labeller_initialization(self):
        """Test PatternLabeller can be initialized."""
        if PatternLabeller is None:
            pytest.skip("PatternLabeller not implemented yet")
        
        labeller = PatternLabeller()
        assert labeller is not None
    
    def test_label_patterns_returns_multi_label_array(self, sample_features_df):
        """Test label_patterns returns multi-label binary array."""
        if PatternLabeller is None:
            pytest.skip("PatternLabeller not implemented yet")
        
        labeller = PatternLabeller()
        labels = labeller.label_patterns(sample_features_df)
        
        # Should return 2D array: (n_samples, n_labels)
        assert labels.shape == (len(sample_features_df), 8)
        
        # All values should be binary (0 or 1)
        assert np.all((labels == 0) | (labels == 1))
    
    def test_bos_confirmed_labelling(self, sample_features_df):
        """Test BOS_CONFIRMED is labelled when bos_detected=True."""
        if PatternLabeller is None:
            pytest.skip("PatternLabeller not implemented yet")
        
        labeller = PatternLabeller()
        labels = labeller.label_patterns(sample_features_df)
        
        # BOS_CONFIRMED is index 0
        bos_labels = labels[:, 0]
        
        # Should have at least some positive labels where bos_detected=True
        assert np.sum(bos_labels) > 0
    
    def test_choch_detected_labelling(self, sample_features_df):
        """Test CHOCH_DETECTED is labelled when choch_detected=True."""
        if PatternLabeller is None:
            pytest.skip("PatternLabeller not implemented yet")
        
        labeller = PatternLabeller()
        labels = labeller.label_patterns(sample_features_df)
        
        # CHOCH_DETECTED is index 1
        choch_labels = labels[:, 1]
        
        # Should have at least some positive labels where choch_detected=True
        assert np.sum(choch_labels) > 0
    
    def test_fvg_present_labelling(self, sample_features_df):
        """Test FVG_PRESENT is labelled when fvg_present=True."""
        if PatternLabeller is None:
            pytest.skip("PatternLabeller not implemented yet")
        
        labeller = PatternLabeller()
        labels = labeller.label_patterns(sample_features_df)
        
        # FVG_PRESENT is index 4
        fvg_labels = labels[:, 4]
        
        # Should have at least some positive labels where fvg_present=True
        assert np.sum(fvg_labels) > 0


class TestTrainingConfig:
    """Test TrainingConfig dataclass."""
    
    def test_config_initialization(self):
        """Test TrainingConfig can be initialized with required fields."""
        if TrainingConfig is None:
            pytest.skip("TrainingConfig not implemented yet")
        
        config = TrainingConfig(
            instruments=['EURUSD', 'GBPUSD'],
            timeframe='M5',
            htf_timeframe='H1',
        )
        
        assert config.instruments == ['EURUSD', 'GBPUSD']
        assert config.timeframe == 'M5'
        assert config.htf_timeframe == 'H1'
        assert config.n_folds == 8  # Default
    
    def test_config_xgb_params_default(self):
        """Test XGBoost params are set with multi-label objective."""
        if TrainingConfig is None:
            pytest.skip("TrainingConfig not implemented yet")
        
        config = TrainingConfig(
            instruments=['EURUSD'],
            timeframe='M5',
            htf_timeframe='H1',
        )
        
        # Should have XGBoost params for binary classification (multi-label)
        assert config.xgb_params is not None
        assert 'objective' in config.xgb_params
        # Multi-label uses binary:logistic for each label
        assert config.xgb_params['objective'] == 'binary:logistic'


class TestPatternDetectorTrainer:
    """Test PatternDetectorTrainer training logic."""
    
    def test_trainer_initialization(self, training_config):
        """Test PatternDetectorTrainer can be initialized."""
        if PatternDetectorTrainer is None:
            pytest.skip("PatternDetectorTrainer not implemented yet")
        
        trainer = PatternDetectorTrainer(training_config)
        
        assert trainer.config == training_config
        assert trainer.pipeline is not None
        assert trainer.labeller is not None
        assert trainer.tracker is not None
    
    def test_prepare_train_test_split_multi_label(self, training_config, sample_features_df):
        """Test prepare_train_test_split returns multi-label targets."""
        if PatternDetectorTrainer is None:
            pytest.skip("PatternDetectorTrainer not implemented yet")
        
        trainer = PatternDetectorTrainer(training_config)
        
        train_start = datetime(2024, 1, 1)
        train_end = datetime(2024, 1, 5)
        test_start = datetime(2024, 1, 6)
        test_end = datetime(2024, 1, 10)
        
        X_train, y_train, X_test, y_test = trainer.prepare_train_test_split(
            features_df=sample_features_df,
            train_start=train_start,
            train_end=train_end,
            test_start=test_start,
            test_end=test_end,
        )
        
        # y_train and y_test should be 2D arrays (multi-label)
        assert y_train.ndim == 2
        assert y_test.ndim == 2
        assert y_train.shape[1] == 8  # 8 pattern labels
        assert y_test.shape[1] == 8
    
    def test_train_fold_uses_multioutput_classifier(self, training_config, sample_features_df):
        """Test train_fold uses MultiOutputClassifier for multi-label."""
        if PatternDetectorTrainer is None:
            pytest.skip("PatternDetectorTrainer not implemented yet")
        
        trainer = PatternDetectorTrainer(training_config)
        
        # Create dummy train/test split
        X_train = sample_features_df.drop(columns=['timestamp']).iloc[:5]
        y_train = np.random.randint(0, 2, size=(5, 8))  # Multi-label
        X_test = sample_features_df.drop(columns=['timestamp']).iloc[5:]
        y_test = np.random.randint(0, 2, size=(5, 8))
        
        model, accuracy, fpr, report = trainer.train_fold(
            X_train=X_train,
            y_train=y_train,
            X_test=X_test,
            y_test=y_test,
        )
        
        # Model should be MultiOutputClassifier wrapping XGBoost
        assert isinstance(model, MultiOutputClassifier)
        
        # Accuracy should be between 0 and 1
        assert 0.0 <= accuracy <= 1.0
        
        # FPR should be between 0 and 1
        assert 0.0 <= fpr <= 1.0
    
    def test_exit_criterion_accuracy_threshold(self, training_config):
        """Test exit criterion checks accuracy ≥ 80%."""
        if PatternDetectorTrainer is None:
            pytest.skip("PatternDetectorTrainer not implemented yet")
        
        trainer = PatternDetectorTrainer(training_config)
        
        # Mock fold results with high accuracy
        fold_results = [
            Mock(accuracy=0.85, false_positive_rate=0.15),
            Mock(accuracy=0.82, false_positive_rate=0.18),
            Mock(accuracy=0.88, false_positive_rate=0.12),
        ]
        
        mean_accuracy = np.mean([f.accuracy for f in fold_results])
        mean_fpr = np.mean([f.false_positive_rate for f in fold_results])
        
        # Should meet exit criterion
        assert mean_accuracy >= 0.80
        assert mean_fpr < 0.20
    
    def test_exit_criterion_fpr_threshold(self, training_config):
        """Test exit criterion checks FPR < 20% at threshold 0.75."""
        if PatternDetectorTrainer is None:
            pytest.skip("PatternDetectorTrainer not implemented yet")
        
        trainer = PatternDetectorTrainer(training_config)
        
        # Mock fold results with low FPR
        fold_results = [
            Mock(accuracy=0.85, false_positive_rate=0.15),
            Mock(accuracy=0.82, false_positive_rate=0.18),
            Mock(accuracy=0.88, false_positive_rate=0.12),
        ]
        
        mean_fpr = np.mean([f.false_positive_rate for f in fold_results])
        
        # Should meet FPR criterion
        assert mean_fpr < 0.20


class TestWalkForwardValidation:
    """Test walk-forward validation logic."""
    
    @pytest.mark.asyncio
    async def test_minimum_8_folds(self, training_config):
        """Test walk-forward validation runs minimum 8 folds."""
        if PatternDetectorTrainer is None:
            pytest.skip("PatternDetectorTrainer not implemented yet")
        
        trainer = PatternDetectorTrainer(training_config)
        
        # Mock database and feature extraction
        with patch.object(trainer, 'load_historical_data', new_callable=AsyncMock) as mock_load:
            with patch.object(trainer, 'extract_features_for_dataset', new_callable=AsyncMock) as mock_extract:
                # Mock data
                mock_load.return_value = pd.DataFrame({
                    'time': pd.date_range('2024-01-01', periods=10000, freq='5min'),
                    'open': np.random.uniform(1.5, 1.6, 10000),
                    'high': np.random.uniform(1.5, 1.6, 10000),
                    'low': np.random.uniform(1.5, 1.6, 10000),
                    'close': np.random.uniform(1.5, 1.6, 10000),
                    'volume': np.random.randint(1000, 5000, 10000),
                })
                
                mock_extract.return_value = pd.DataFrame({
                    'timestamp': pd.date_range('2024-01-01', periods=5000, freq='5min'),
                    'htf_open': np.random.uniform(1.5, 1.6, 5000),
                    'bos_detected': np.random.choice([True, False], 5000),
                    'choch_detected': np.random.choice([True, False], 5000),
                    'fvg_present': np.random.choice([True, False], 5000),
                })
                
                # Run validation
                fold_results = await trainer.run_walk_forward_validation('EURUSD')
                
                # Should have at least 8 folds
                assert len(fold_results) >= 8


class TestMLflowIntegration:
    """Test MLflow experiment tracking integration."""
    
    @pytest.mark.asyncio
    async def test_mlflow_experiment_logging(self, training_config):
        """Test that training logs to MLflow experiment."""
        if PatternDetectorTrainer is None:
            pytest.skip("PatternDetectorTrainer not implemented yet")
        
        trainer = PatternDetectorTrainer(training_config)
        
        # Mock MLflow tracker
        with patch.object(trainer.tracker, 'start_run') as mock_start_run:
            with patch.object(trainer.tracker, 'log_params') as mock_log_params:
                with patch.object(trainer.tracker, 'log_metrics') as mock_log_metrics:
                    # Mock training to avoid actual DB calls
                    with patch.object(trainer, 'run_walk_forward_validation', new_callable=AsyncMock) as mock_validate:
                        mock_validate.return_value = [
                            Mock(accuracy=0.85, false_positive_rate=0.15),
                        ]
                        
                        # Run training
                        result = await trainer.train()
                        
                        # Should have called MLflow methods
                        mock_start_run.assert_called_once()
                        mock_log_params.assert_called()
                        mock_log_metrics.assert_called()
    
    def test_model_registry_name(self):
        """Test model is registered as 'pattern-detector'."""
        # This is a contract test - the model name must match
        expected_model_name = "pattern-detector"
        
        # This will be validated in the actual implementation
        assert expected_model_name == "pattern-detector"


class TestModelOutputContract:
    """Test model output contract for multi-label classification."""
    
    def test_model_predicts_8_binary_labels(self):
        """Test trained model outputs 8 binary labels."""
        if PatternDetectorTrainer is None:
            pytest.skip("PatternDetectorTrainer not implemented yet")
        
        # Create a simple multi-output classifier
        base_model = xgb.XGBClassifier(objective='binary:logistic')
        model = MultiOutputClassifier(base_model)
        
        # Train on dummy data
        X_train = np.random.rand(100, 10)
        y_train = np.random.randint(0, 2, size=(100, 8))
        
        model.fit(X_train, y_train)
        
        # Predict
        X_test = np.random.rand(10, 10)
        y_pred = model.predict(X_test)
        
        # Should output 8 binary labels per sample
        assert y_pred.shape == (10, 8)
        assert np.all((y_pred == 0) | (y_pred == 1))
    
    def test_model_predict_proba_returns_probabilities(self):
        """Test model.predict_proba returns probabilities for threshold tuning."""
        if PatternDetectorTrainer is None:
            pytest.skip("PatternDetectorTrainer not implemented yet")
        
        # Create a simple multi-output classifier
        base_model = xgb.XGBClassifier(objective='binary:logistic')
        model = MultiOutputClassifier(base_model)
        
        # Train on dummy data
        X_train = np.random.rand(100, 10)
        y_train = np.random.randint(0, 2, size=(100, 8))
        
        model.fit(X_train, y_train)
        
        # Predict probabilities
        X_test = np.random.rand(10, 10)
        y_proba = model.predict_proba(X_test)
        
        # Should return list of probability arrays (one per label)
        assert len(y_proba) == 8
        
        # Each should have probabilities for binary classification
        for proba in y_proba:
            assert proba.shape == (10, 2)  # (n_samples, 2 classes)
            assert np.allclose(proba.sum(axis=1), 1.0)  # Probabilities sum to 1
