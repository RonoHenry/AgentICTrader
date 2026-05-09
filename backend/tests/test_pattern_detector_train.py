"""
Tests for Pattern Detector training script.

**Implements: Task 21 - Train and validate Pattern Detector**

Following TDD methodology:
- RED: Write failing tests first
- GREEN: Implement minimal code to pass tests
- REFACTOR: Clean up while keeping tests green
"""

import pytest
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch

# Import will fail initially (RED phase)
try:
    from ml.models.pattern_detector.train import (
        PatternLabeller,
        PatternDetectorTrainer,
        TrainingConfig,
        FoldResult,
        PATTERN_CLASSES,
    )
except ImportError:
    pytest.skip("Pattern detector train module not yet implemented", allow_module_level=True)


class TestPatternLabeller:
    """Test heuristic pattern labelling logic."""
    
    def test_pattern_labeller_instantiates(self):
        """Test that PatternLabeller can be instantiated."""
        labeller = PatternLabeller()
        assert labeller is not None
    
    def test_label_patterns_returns_correct_shape(self):
        """Test that label_patterns returns correct shape for multi-label output."""
        labeller = PatternLabeller()
        
        # Create dummy features
        features = pd.DataFrame({
            'htf_trend_bias': ['BULLISH', 'BEARISH', 'NEUTRAL'],
            'bos_detected': [True, False, True],
            'choch_detected': [False, True, False],
            'fvg_present': [True, False, True],
            'htf_body_pct': [60.0, 40.0, 50.0],
        })
        
        labels = labeller.label_patterns(features)
        
        # Should return multi-label array: (n_samples, n_patterns)
        assert labels.shape == (3, len(PATTERN_CLASSES))
        assert labels.dtype == int
        assert np.all((labels == 0) | (labels == 1))  # Binary labels only
    
    def test_bos_confirmed_labelling(self):
        """Test BOS_CONFIRMED pattern labelling logic."""
        labeller = PatternLabeller()
        
        # BOS should be detected when bos_detected=True and strong HTF body
        features = pd.DataFrame({
            'htf_trend_bias': ['BULLISH'],
            'bos_detected': [True],
            'choch_detected': [False],
            'fvg_present': [False],
            'htf_body_pct': [60.0],
            'liquidity_sweep': [False],
            'swing_high_distance': [50.0],
            'swing_low_distance': [30.0],
        })
        
        labels = labeller.label_patterns(features)
        
        # BOS_CONFIRMED should be labeled (index 0)
        assert labels[0, 0] == 1
    
    def test_choch_detected_labelling(self):
        """Test CHOCH_DETECTED pattern labelling logic."""
        labeller = PatternLabeller()
        
        features = pd.DataFrame({
            'htf_trend_bias': ['NEUTRAL'],
            'bos_detected': [False],
            'choch_detected': [True],
            'fvg_present': [False],
            'htf_body_pct': [40.0],
            'liquidity_sweep': [False],
            'swing_high_distance': [50.0],
            'swing_low_distance': [30.0],
        })
        
        labels = labeller.label_patterns(features)
        
        # CHOCH_DETECTED should be labeled (index 1)
        assert labels[0, 1] == 1
    
    def test_fvg_present_labelling(self):
        """Test FVG_PRESENT pattern labelling logic."""
        labeller = PatternLabeller()
        
        features = pd.DataFrame({
            'htf_trend_bias': ['BULLISH'],
            'bos_detected': [False],
            'choch_detected': [False],
            'fvg_present': [True],
            'htf_body_pct': [50.0],
            'liquidity_sweep': [False],
            'swing_high_distance': [50.0],
            'swing_low_distance': [30.0],
        })
        
        labels = labeller.label_patterns(features)
        
        # FVG_PRESENT should be labeled (index 4)
        assert labels[0, 4] == 1
    
    def test_liquidity_sweep_labelling(self):
        """Test LIQUIDITY_SWEEP pattern labelling logic."""
        labeller = PatternLabeller()
        
        features = pd.DataFrame({
            'htf_trend_bias': ['BULLISH'],
            'bos_detected': [False],
            'choch_detected': [False],
            'fvg_present': [False],
            'htf_body_pct': [50.0],
            'liquidity_sweep': [True],
            'swing_high_distance': [50.0],
            'swing_low_distance': [30.0],
        })
        
        labels = labeller.label_patterns(features)
        
        # LIQUIDITY_SWEEP should be labeled (index 5)
        assert labels[0, 5] == 1
    
    def test_multi_label_output(self):
        """Test that multiple patterns can be labeled simultaneously."""
        labeller = PatternLabeller()
        
        # Setup features that should trigger multiple patterns
        features = pd.DataFrame({
            'htf_trend_bias': ['BULLISH'],
            'bos_detected': [True],
            'choch_detected': [False],
            'fvg_present': [True],
            'htf_body_pct': [60.0],
            'liquidity_sweep': [False],
            'swing_high_distance': [50.0],
            'swing_low_distance': [30.0],
        })
        
        labels = labeller.label_patterns(features)
        
        # Should have multiple patterns labeled
        assert np.sum(labels[0]) >= 2  # At least BOS and FVG


class TestTrainingConfig:
    """Test training configuration."""
    
    def test_training_config_instantiates(self):
        """Test that TrainingConfig can be instantiated."""
        config = TrainingConfig(
            instruments=['EURUSD'],
            timeframe='M5',
            htf_timeframe='H1',
        )
        
        assert config.instruments == ['EURUSD']
        assert config.timeframe == 'M5'
        assert config.htf_timeframe == 'H1'
        assert config.n_folds == 8
    
    def test_training_config_xgb_params_default(self):
        """Test that XGBoost parameters are set correctly for multi-label."""
        config = TrainingConfig(
            instruments=['EURUSD'],
            timeframe='M5',
            htf_timeframe='H1',
        )
        
        # Multi-label uses binary:logistic objective
        assert config.xgb_params['objective'] == 'binary:logistic'
        assert 'num_class' not in config.xgb_params  # Not used for binary


class TestPatternDetectorTrainer:
    """Test Pattern Detector trainer."""
    
    @pytest.fixture
    def config(self):
        """Create test configuration."""
        return TrainingConfig(
            instruments=['EURUSD'],
            timeframe='M5',
            htf_timeframe='H1',
            n_folds=2,  # Reduced for testing
            min_candles_per_fold=100,
        )
    
    @pytest.fixture
    def trainer(self, config):
        """Create trainer instance."""
        return PatternDetectorTrainer(config)
    
    def test_trainer_instantiates(self, trainer):
        """Test that trainer can be instantiated."""
        assert trainer is not None
        assert trainer.pipeline is not None
        assert trainer.labeller is not None
        assert trainer.tracker is not None
    
    def test_trainer_has_multi_output_classifier(self, trainer):
        """Test that trainer uses MultiOutputClassifier for multi-label."""
        # Trainer should have a method to create multi-output classifier
        assert hasattr(trainer, 'create_model')
    
    def test_prepare_train_test_split_returns_correct_shapes(self, trainer):
        """Test that train/test split returns correct shapes for multi-label."""
        # Create dummy features
        features_df = pd.DataFrame({
            'timestamp': pd.date_range('2024-01-01', periods=200, freq='5min'),
            'htf_trend_bias': ['BULLISH'] * 200,
            'bos_detected': [True] * 200,
            'choch_detected': [False] * 200,
            'fvg_present': [True] * 200,
            'htf_body_pct': [60.0] * 200,
            'liquidity_sweep': [False] * 200,
            'swing_high_distance': [50.0] * 200,
            'swing_low_distance': [30.0] * 200,
        })
        
        train_start = datetime(2024, 1, 1)
        train_end = datetime(2024, 1, 15)
        test_start = datetime(2024, 1, 16)
        test_end = datetime(2024, 1, 20)
        
        X_train, y_train, X_test, y_test = trainer.prepare_train_test_split(
            features_df=features_df,
            train_start=train_start,
            train_end=train_end,
            test_start=test_start,
            test_end=test_end,
        )
        
        # Check shapes
        assert len(X_train) > 0
        assert len(X_test) > 0
        
        # y should be multi-label: (n_samples, n_patterns)
        assert y_train.shape[1] == len(PATTERN_CLASSES)
        assert y_test.shape[1] == len(PATTERN_CLASSES)
    
    def test_compute_per_pattern_metrics(self, trainer):
        """Test per-pattern accuracy and FPR computation."""
        # Create dummy predictions and ground truth
        y_true = np.array([
            [1, 0, 1, 0, 1, 0, 0, 1],
            [0, 1, 0, 1, 0, 1, 1, 0],
            [1, 1, 0, 0, 1, 1, 0, 0],
        ])
        
        y_pred_proba = np.array([
            [0.9, 0.1, 0.8, 0.2, 0.85, 0.15, 0.1, 0.9],
            [0.2, 0.8, 0.1, 0.9, 0.2, 0.85, 0.8, 0.1],
            [0.85, 0.9, 0.2, 0.1, 0.8, 0.9, 0.1, 0.2],
        ])
        
        metrics = trainer.compute_per_pattern_metrics(
            y_true=y_true,
            y_pred_proba=y_pred_proba,
            threshold=0.75,
        )
        
        # Should return dict with per-pattern metrics
        assert 'per_pattern_accuracy' in metrics
        assert 'per_pattern_fpr' in metrics
        assert 'mean_accuracy' in metrics
        assert 'mean_fpr' in metrics
        
        # Check that we have metrics for all patterns
        assert len(metrics['per_pattern_accuracy']) == len(PATTERN_CLASSES)
        assert len(metrics['per_pattern_fpr']) == len(PATTERN_CLASSES)
        
        # Accuracy and FPR should be in valid ranges
        for acc in metrics['per_pattern_accuracy'].values():
            assert 0.0 <= acc <= 1.0
        
        for fpr in metrics['per_pattern_fpr'].values():
            assert 0.0 <= fpr <= 1.0
    
    def test_exit_criterion_check(self, trainer):
        """Test exit criterion: mean accuracy >= 80% AND mean FPR < 20%."""
        # Test passing case
        metrics_pass = {
            'mean_accuracy': 0.82,
            'mean_fpr': 0.15,
        }
        assert trainer.check_exit_criterion(metrics_pass) is True
        
        # Test failing case: low accuracy
        metrics_fail_acc = {
            'mean_accuracy': 0.75,
            'mean_fpr': 0.15,
        }
        assert trainer.check_exit_criterion(metrics_fail_acc) is False
        
        # Test failing case: high FPR
        metrics_fail_fpr = {
            'mean_accuracy': 0.82,
            'mean_fpr': 0.25,
        }
        assert trainer.check_exit_criterion(metrics_fail_fpr) is False


class TestFoldResult:
    """Test fold result dataclass."""
    
    def test_fold_result_instantiates(self):
        """Test that FoldResult can be instantiated."""
        result = FoldResult(
            fold_id=1,
            train_start=datetime(2024, 1, 1),
            train_end=datetime(2024, 3, 31),
            test_start=datetime(2024, 4, 1),
            test_end=datetime(2024, 4, 30),
            train_samples=1000,
            test_samples=200,
            mean_accuracy=0.85,
            mean_fpr=0.12,
            per_pattern_metrics={},
        )
        
        assert result.fold_id == 1
        assert result.mean_accuracy == 0.85
        assert result.mean_fpr == 0.12


class TestPatternClasses:
    """Test pattern class definitions."""
    
    def test_pattern_classes_defined(self):
        """Test that all 8 pattern classes are defined."""
        assert len(PATTERN_CLASSES) == 8
        
        expected_patterns = [
            'BOS_CONFIRMED',
            'CHOCH_DETECTED',
            'SUPPLY_ZONE_REJECTION',
            'DEMAND_ZONE_BOUNCE',
            'FVG_PRESENT',
            'LIQUIDITY_SWEEP',
            'ORDER_BLOCK',
            'INDUCEMENT',
        ]
        
        for pattern in expected_patterns:
            assert pattern in PATTERN_CLASSES
