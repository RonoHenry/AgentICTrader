"""
Tests for RAG-augmented Confluence Scorer training.

TDD: RED → GREEN → REFACTOR

Test coverage:
1. Training script accepts RAG-augmented feature vectors
2. Feature importance analysis for RAG features
3. A/B testing capability (RAG enabled/disabled)
4. Integration with AlgoRAG client during training

Following Task 16.2 requirements:
- RED: Test training script accepts RAG-augmented feature vectors  
- GREEN: Modify train_with_rag.py to include RAG features
- REFACTOR: Add feature importance analysis for RAG features
"""

import pytest
import numpy as np
import pandas as pd
from unittest.mock import AsyncMock, Mock, patch
from datetime import datetime, timezone

from ml.models.confluence_scorer.train_with_rag import (
    RAGAugmentedTrainer,
)
from ml.models.confluence_scorer.train import TrainingConfig
from ml.models.confluence_scorer.features import ConfluenceFeatureExtractor
from ml.algorag.client import AlgoRAGClient


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def rag_training_config():
    """Training configuration for RAG-augmented training."""
    return TrainingConfig(
        instruments=["EURUSD"],
        timeframe="M5",
        n_folds=3,  # Reduced for testing
    )


@pytest.fixture
def sample_rag_features():
    """Sample feature dataset with RAG features."""
    n = 100
    base_time = datetime(2024, 1, 1, tzinfo=timezone.utc)
    
    return pd.DataFrame({
        "timestamp": pd.date_range(base_time, periods=n, freq="5min"),
        # Traditional features
        "htf_open_bias": ["BULLISH"] * (n // 2) + ["NEUTRAL"] * (n // 2),
        "htf_high_proximity_pct": np.random.uniform(10, 90, n),
        "htf_low_proximity_pct": np.random.uniform(10, 90, n),
        "htf_body_pct": np.random.uniform(20, 80, n),
        "time_window_weight": [0.9] * (n // 2) + [0.1] * (n // 2),
        "narrative_phase": ["MANIPULATION"] * (n // 2) + ["OFF"] * (n // 2),
        "bos_detected": [True] * (n // 2) + [False] * (n // 2),
        "choch_detected": [False] * n,
        "fvg_present": [True] * (n // 2) + [False] * (n // 2),
        "liquidity_sweep": [False] * n,
        # RAG features (new)
        "avg_r_multiple": np.random.uniform(0.5, 5.0, n),
        "win_rate": np.random.uniform(0.3, 0.9, n),
        "sample_size": np.random.uniform(0.01, 0.20, n),  # normalized
        "max_similarity": np.random.uniform(0.6, 1.0, n),
    })


# ── Task 16.2: RED Tests ──────────────────────────────────────────────────────

class TestRAGAugmentedTraining:
    """RED: Test training script accepts RAG-augmented feature vectors."""
    
    def test_rag_trainer_initialization(self, rag_training_config):
        """RAG trainer should initialize with RAG enabled/disabled option."""
        # Test RAG enabled
        trainer_enabled = RAGAugmentedTrainer(rag_training_config, rag_enabled=True)
        assert trainer_enabled.rag_enabled is True
        
        # Test RAG disabled  
        trainer_disabled = RAGAugmentedTrainer(rag_training_config, rag_enabled=False)
        assert trainer_disabled.rag_enabled is False

    def test_feature_extractor_creation(self, rag_training_config):
        """Feature extractor should be created with/without RAG client."""
        trainer = RAGAugmentedTrainer(rag_training_config, rag_enabled=True)
        
        # Mock the RAG client creation
        with patch('ml.models.confluence_scorer.train_with_rag.AlgoRAGClient') as mock_client_class:
            mock_client = Mock()
            mock_client_class.return_value = mock_client
            
            extractor = trainer._build_feature_extractor()
            
            assert isinstance(extractor, ConfluenceFeatureExtractor)
            # Should attempt to create RAG client when enabled
            mock_client_class.assert_called_once()

    def test_feature_extractor_fallback(self, rag_training_config):
        """Feature extractor should fallback to no RAG when client creation fails.""" 
        trainer = RAGAugmentedTrainer(rag_training_config, rag_enabled=True)
        
        # Mock RAG client creation failure
        with patch('ml.models.confluence_scorer.train_with_rag.AlgoRAGClient') as mock_client_class:
            mock_client_class.side_effect = Exception("RAG service unavailable")
            
            extractor = trainer._build_feature_extractor()
            
            assert isinstance(extractor, ConfluenceFeatureExtractor)
            assert extractor.rag_client is None  # Should fallback to None

    @pytest.mark.asyncio
    async def test_rag_features_added_when_enabled(self, rag_training_config, sample_rag_features):
        """When RAG enabled, feature dataset should include RAG columns."""
        trainer = RAGAugmentedTrainer(rag_training_config, rag_enabled=True)
        
        # Mock the base feature loading
        with patch.object(trainer, 'load_feature_dataset', new_callable=AsyncMock) as mock_load:
            # Return base features without RAG columns
            base_features = sample_rag_features.drop(columns=[
                "avg_r_multiple", "win_rate", "sample_size", "max_similarity"
            ])
            mock_load.return_value = base_features
            
            # Load with RAG augmentation
            result = await trainer.load_feature_dataset_with_rag(
                "EURUSD", 
                datetime(2024, 1, 1, tzinfo=timezone.utc),
                datetime(2024, 1, 2, tzinfo=timezone.utc)
            )
            
            # Should have RAG columns added
            assert "avg_r_multiple" in result.columns
            assert "win_rate" in result.columns
            assert "sample_size" in result.columns
            assert "max_similarity" in result.columns
            assert len(result) == len(base_features)

    @pytest.mark.asyncio
    async def test_rag_features_zeros_when_disabled(self, rag_training_config, sample_rag_features):
        """When RAG disabled, RAG features should be added as zeros."""
        trainer = RAGAugmentedTrainer(rag_training_config, rag_enabled=False)
        
        # Mock the base feature loading  
        with patch.object(trainer, 'load_feature_dataset', new_callable=AsyncMock) as mock_load:
            base_features = sample_rag_features.drop(columns=[
                "avg_r_multiple", "win_rate", "sample_size", "max_similarity"
            ])
            mock_load.return_value = base_features
            
            result = await trainer.load_feature_dataset_with_rag(
                "EURUSD",
                datetime(2024, 1, 1, tzinfo=timezone.utc), 
                datetime(2024, 1, 2, tzinfo=timezone.utc)
            )
            
            # Should have RAG columns as zeros
            assert "avg_r_multiple" in result.columns
            assert "win_rate" in result.columns 
            assert "sample_size" in result.columns
            assert "max_similarity" in result.columns
            assert (result["avg_r_multiple"] == 0.0).all()
            assert (result["win_rate"] == 0.0).all()
            assert (result["sample_size"] == 0.0).all()
            assert (result["max_similarity"] == 0.0).all()

    @pytest.mark.asyncio 
    async def test_training_accepts_rag_features(self, rag_training_config, sample_rag_features):
        """Training process should accept and process RAG-augmented features."""
        trainer = RAGAugmentedTrainer(rag_training_config, rag_enabled=True)
        
        # Mock dependencies
        with patch.object(trainer, 'load_feature_dataset_with_rag', new_callable=AsyncMock) as mock_load:
            with patch.object(trainer, 'train', new_callable=AsyncMock) as mock_train:
                mock_load.return_value = sample_rag_features
                mock_train.return_value = {
                    "status": "completed", 
                    "mean_roc_auc": 0.75,
                    "n_folds": 3
                }
                
                result = await trainer.train_with_rag()
                
                # Should call base training
                mock_train.assert_called_once()
                
                # Should include RAG metadata
                assert result["rag_enabled"] is True
                assert result["rag_feature_count"] == 4
                assert result["model_version"] == "confluence-scorer-v2-rag"
                assert result["features_enhanced"] is True

    @pytest.mark.asyncio
    async def test_training_baseline_without_rag(self, rag_training_config, sample_rag_features):
        """Training should work in baseline mode without RAG features."""
        trainer = RAGAugmentedTrainer(rag_training_config, rag_enabled=False)
        
        with patch.object(trainer, 'load_feature_dataset_with_rag', new_callable=AsyncMock) as mock_load:
            with patch.object(trainer, 'train', new_callable=AsyncMock) as mock_train:
                # Return features with zero RAG values
                baseline_features = sample_rag_features.copy()
                baseline_features["avg_r_multiple"] = 0.0
                baseline_features["win_rate"] = 0.0
                baseline_features["sample_size"] = 0.0
                baseline_features["max_similarity"] = 0.0
                
                mock_load.return_value = baseline_features
                mock_train.return_value = {
                    "status": "completed", 
                    "mean_roc_auc": 0.70,
                    "n_folds": 3
                }
                
                result = await trainer.train_with_rag()
                
                # Should indicate RAG disabled
                assert result["rag_enabled"] is False
                assert result["rag_feature_count"] == 0
                assert result["model_version"] == "confluence-scorer-v1-baseline"
                assert result["features_enhanced"] is False


# ── Feature Importance Analysis Tests ──────────────────────────────────────────

class TestRAGFeatureImportance:
    """Test feature importance analysis for RAG features (REFACTOR phase)."""
    
    def test_feature_importance_extraction(self, rag_training_config):
        """Should extract importance scores for RAG features from trained model."""
        trainer = RAGAugmentedTrainer(rag_training_config, rag_enabled=True)
        
        # Create a simple class to mock the classifier
        class MockClassifier:
            def __init__(self):
                self.coef_ = np.array([[0.1, 0.2, 0.3, 0.4, 0.15, 0.25, 0.35, 0.45, 0.05, 0.55, 
                                      0.8, 0.6, 0.2, 0.9]])  # 14 features including 4 RAG
        
        # Create a simple class to mock the pipeline
        class MockPipeline:
            def __init__(self):
                self.named_steps = {'classifier': MockClassifier()}
        
        mock_pipeline = MockPipeline()
        
        feature_names = [
            "htf_high_prox", "htf_low_prox", "htf_body", "htf_close", "time_weight",
            "narrative", "bos", "choch", "fvg", "sweep",
            "avg_r_multiple", "win_rate", "sample_size", "max_similarity"
        ]
        rag_indices = [10, 11, 12, 13]  # Last 4 features are RAG
        
        importance = trainer.analyze_rag_feature_importance(
            mock_pipeline, feature_names, rag_indices
        )
        
        assert len(importance) == 4
        assert "avg_r_multiple" in importance
        assert "win_rate" in importance
        assert "sample_size" in importance
        assert "max_similarity" in importance
        
        # Should use absolute values of coefficients
        assert importance["avg_r_multiple"] == 0.8
        assert importance["win_rate"] == 0.6
        assert importance["sample_size"] == 0.2
        assert importance["max_similarity"] == 0.9

    def test_feature_importance_with_calibrated_classifier(self, rag_training_config):
        """Should handle CalibratedClassifierCV wrapper."""
        trainer = RAGAugmentedTrainer(rag_training_config, rag_enabled=True)
        
        # Mock calibrated classifier
        mock_base_classifier = Mock()
        mock_base_classifier.coef_ = np.array([[0.1, 0.2, 0.3, 0.4, 0.15, 0.25, 0.35, 0.45, 0.05, 0.55,
                                              0.7, 0.5, 0.3, 0.8]])
        
        mock_calibrated = Mock()
        mock_calibrated.estimators_ = [mock_base_classifier]
        
        mock_pipeline = Mock()
        mock_pipeline.named_steps = {'classifier': mock_calibrated}
        
        feature_names = ["f%d" % i for i in range(14)]
        rag_indices = [10, 11, 12, 13]
        
        importance = trainer.analyze_rag_feature_importance(
            mock_pipeline, feature_names, rag_indices
        )
        
        assert len(importance) == 4
        # Should extract from base classifier within calibrated wrapper

    def test_feature_importance_graceful_failure(self, rag_training_config):
        """Should return empty dict when importance extraction fails."""
        trainer = RAGAugmentedTrainer(rag_training_config, rag_enabled=True)
        
        # Mock model without coef_ attribute
        mock_pipeline = Mock()
        mock_pipeline.named_steps = {'classifier': Mock()}
        del mock_pipeline.named_steps['classifier'].coef_  # Remove coef_ attribute
        
        importance = trainer.analyze_rag_feature_importance(
            mock_pipeline, [], []
        )
        
        assert importance == {}
    
    def test_rag_feature_statistics_computation(self, rag_training_config, sample_rag_features):
        """Should compute statistical summaries for RAG features."""
        trainer = RAGAugmentedTrainer(rag_training_config, rag_enabled=True)
        
        stats = trainer.compute_rag_feature_statistics(sample_rag_features)
        
        # Should have stats for each RAG feature
        assert "avg_r_multiple" in stats
        assert "win_rate" in stats
        assert "sample_size" in stats
        assert "max_similarity" in stats
        
        # Each feature should have complete statistics
        for feature_stats in stats.values():
            assert "mean" in feature_stats
            assert "std" in feature_stats
            assert "min" in feature_stats
            assert "max" in feature_stats
            assert "non_zero_count" in feature_stats
            assert "coverage" in feature_stats
            assert "percentiles" in feature_stats
            
            # Percentiles should have all required values
            assert "25" in feature_stats["percentiles"]
            assert "50" in feature_stats["percentiles"]
            assert "75" in feature_stats["percentiles"]
            assert "95" in feature_stats["percentiles"]


# ── Integration Tests ──────────────────────────────────────────────────────────

class TestRAGTrainingIntegration:
    """Integration tests for RAG-augmented training."""
    
    @pytest.mark.asyncio
    async def test_empty_dataset_handling(self, rag_training_config):
        """Should handle empty datasets gracefully."""
        trainer = RAGAugmentedTrainer(rag_training_config, rag_enabled=True)
        
        with patch.object(trainer, 'load_feature_dataset', new_callable=AsyncMock) as mock_load:
            mock_load.return_value = pd.DataFrame()  # Empty dataset
            
            result = await trainer.load_feature_dataset_with_rag(
                "EURUSD",
                datetime(2024, 1, 1, tzinfo=timezone.utc),
                datetime(2024, 1, 2, tzinfo=timezone.utc)
            )
            
            assert result.empty

    @pytest.mark.asyncio
    async def test_method_restoration_after_training(self, rag_training_config):
        """Original load_feature_dataset method should be restored after training."""
        trainer = RAGAugmentedTrainer(rag_training_config, rag_enabled=True)
        
        # Store original method
        original_method = trainer.load_feature_dataset
        
        with patch.object(trainer, 'train', new_callable=AsyncMock) as mock_train:
            mock_train.return_value = {"status": "completed"}
            
            await trainer.train_with_rag()
            
            # Method should be restored
            assert trainer.load_feature_dataset == original_method