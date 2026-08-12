"""
Confluence Scorer training script with RAG features.

This script retrains the Confluence Scorer to include RAG features:
- avg_r_multiple_similar - Average R-multiple of similar historical setups
- win_rate_similar - Win rate percentage of similar setups  
- sample_size - Number of similar setups found (normalized by /100)
- max_similarity_score - Highest similarity score among retrieved setups

The training process augments the traditional feature vector with RAG metrics
for improved decision making based on historical context.

Usage:
    python -m ml.models.confluence_scorer.train_with_rag --instruments EURUSD GBPUSD
"""
from __future__ import annotations

import os
import sys
import argparse
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Tuple, Optional

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score
from sklearn.inspection import permutation_importance

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from ml.models.confluence_scorer.train import (
    ConfluenceScorerTrainer,
    TrainingConfig,
    FoldResult,
)
from ml.models.confluence_scorer.features import ConfluenceFeatureExtractor
from ml.algorag.client import AlgoRAGClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class RAGAugmentedTrainer(ConfluenceScorerTrainer):
    """
    Confluence Scorer trainer with RAG feature augmentation.
    
    Extends the base trainer to include RAG features in the feature vector.
    """
    
    def __init__(self, config: TrainingConfig, rag_enabled: bool = True):
        """
        Initialize RAG-augmented trainer.
        
        Args:
            config: Training configuration
            rag_enabled: Whether to include RAG features (for A/B testing)
        """
        super().__init__(config)
        self.rag_enabled = rag_enabled
        self.feature_extractor = None  # Will be initialized with RAG client if available
        
    def _build_feature_extractor(self) -> ConfluenceFeatureExtractor:
        """Build feature extractor with optional RAG integration."""
        if self.rag_enabled:
            try:
                # Initialize RAG client for feature extraction
                rag_client = AlgoRAGClient()
                return ConfluenceFeatureExtractor(rag_client=rag_client)
            except Exception as e:
                logger.warning(f"RAG client unavailable, using fallback: {e}")
                return ConfluenceFeatureExtractor(rag_client=None)
        else:
            return ConfluenceFeatureExtractor(rag_client=None)
    
    async def load_feature_dataset_with_rag(
        self, 
        instrument: str, 
        start_date: datetime, 
        end_date: datetime
    ) -> pd.DataFrame:
        """
        Load pre-computed features with RAG augmentation.
        
        This extends the base feature loading to include RAG features
        by calling the AlgoRAG service for each historical setup.
        """
        # Load base features
        base_features = await self.load_feature_dataset(instrument, start_date, end_date)
        
        if base_features.empty:
            return base_features
            
        if not self.rag_enabled:
            # Add zero RAG features for consistency
            base_features["avg_r_multiple"] = 0.0
            base_features["win_rate"] = 0.0
            base_features["sample_size"] = 0.0
            base_features["max_similarity"] = 0.0
            return base_features
        
        # Initialize feature extractor with RAG if not already done
        if self.feature_extractor is None:
            self.feature_extractor = self._build_feature_extractor()
        
        # Extract RAG features for each training sample
        rag_features_list = []
        
        logger.info(f"Extracting RAG features for {len(base_features)} samples")
        
        for idx, row in base_features.iterrows():
            try:
                # Build setup data from feature row
                setup_data = {
                    "instrument": instrument,
                    "timestamp": row["timestamp"],
                    "htf_open_bias": row.get("htf_open_bias", "NEUTRAL"),
                    "htf_high_proximity_pct": row.get("htf_high_proximity_pct", 50.0),
                    "htf_low_proximity_pct": row.get("htf_low_proximity_pct", 50.0),
                    "htf_body_pct": row.get("htf_body_pct", 50.0),
                    "session": row.get("session", "OFF_HOURS"),
                    # Create a simple narrative for RAG retrieval
                    "narrative": f"{instrument} {row.get('htf_open_bias', 'NEUTRAL')} bias setup during {row.get('session', 'OFF_HOURS')} session"
                }
                
                # Call RAG client if available
                if self.feature_extractor and self.feature_extractor.rag_client:
                    try:
                        rag_response = await self.feature_extractor.rag_client.retrieve_with_fallback(setup_data)
                        rag_metrics = rag_response.get("rag_metrics", {})
                        
                        rag_features = {
                            "avg_r_multiple": float(rag_metrics.get("avg_r_multiple_similar", 0.0)),
                            "win_rate": float(rag_metrics.get("win_rate_similar", 0.0)),
                            "sample_size": float(rag_metrics.get("sample_size", 0)) / 100.0,  # normalized
                            "max_similarity": float(rag_metrics.get("max_similarity_score", 0.0))
                        }
                    except Exception as rag_error:
                        logger.warning(f"RAG retrieval failed for sample {idx}: {rag_error}")
                        # Fallback to zeros
                        rag_features = {
                            "avg_r_multiple": 0.0,
                            "win_rate": 0.0,
                            "sample_size": 0.0,
                            "max_similarity": 0.0
                        }
                else:
                    # No RAG client available, use zeros
                    rag_features = {
                        "avg_r_multiple": 0.0,
                        "win_rate": 0.0,
                        "sample_size": 0.0,
                        "max_similarity": 0.0
                    }
                
                rag_features_list.append(rag_features)
                
            except Exception as e:
                logger.warning(f"Failed to extract RAG features for sample {idx}: {e}")
                # Fallback to zeros
                rag_features_list.append({
                    "avg_r_multiple": 0.0,
                    "win_rate": 0.0,
                    "sample_size": 0.0,
                    "max_similarity": 0.0
                })
        
        # Convert RAG features to DataFrame and concatenate
        rag_df = pd.DataFrame(rag_features_list)
        
        # Ensure indexes match
        rag_df.index = base_features.index
        
        # Add RAG columns to base features
        for col in rag_df.columns:
            base_features[col] = rag_df[col]
        
        # Log RAG feature statistics
        non_zero_samples = (base_features["avg_r_multiple"] > 0).sum()
        avg_sample_size = base_features["sample_size"].mean()
        avg_similarity = base_features["max_similarity"].mean()
        
        logger.info(f"RAG feature extraction completed:")
        logger.info(f"  Samples with RAG data: {non_zero_samples}/{len(base_features)}")
        logger.info(f"  Average sample size: {avg_sample_size:.3f}")
        logger.info(f"  Average max similarity: {avg_similarity:.3f}")
        
        return base_features
    
    def analyze_rag_feature_importance(
        self, 
        model, 
        feature_names: List[str], 
        rag_feature_indices: List[int]
    ) -> Dict[str, float]:
        """
        Analyze the importance of RAG features in the trained model.
        
        Args:
            model: Trained model pipeline
            feature_names: List of all feature names
            rag_feature_indices: Indices of RAG features in the feature vector
            
        Returns:
            Dictionary mapping RAG feature names to importance scores
        """
        try:
            # Get feature importance from the logistic regression model
            if hasattr(model.named_steps['classifier'], 'estimators_'):
                # CalibratedClassifierCV case
                base_classifier = model.named_steps['classifier'].estimators_[0]
            else:
                base_classifier = model.named_steps['classifier']
                
            if hasattr(base_classifier, 'coef_'):
                coef_array = base_classifier.coef_
                # Handle both 1D and 2D coefficient arrays
                if hasattr(coef_array, 'ndim') and coef_array.ndim == 2:
                    coefficients = coef_array[0]  # For binary classification, take first row
                else:
                    coefficients = coef_array  # Already 1D
                
                rag_importances = {}
                for idx, feature_idx in enumerate(rag_feature_indices):
                    if feature_idx < len(coefficients):
                        feature_name = feature_names[feature_idx] if feature_idx < len(feature_names) else f"rag_feature_{idx}"
                        rag_importances[feature_name] = abs(float(coefficients[feature_idx]))
                
                return rag_importances
        except Exception as e:
            logger.warning(f"Could not analyze feature importance: {e}")
            
        return {}
    
    def compute_rag_feature_statistics(
        self, 
        features_df: pd.DataFrame,
        rag_feature_names: List[str] = None
    ) -> Dict[str, Any]:
        """
        Compute statistical summary of RAG features across the dataset.
        
        Args:
            features_df: Dataset with RAG features
            rag_feature_names: Names of RAG features to analyze
            
        Returns:
            Dictionary with statistical summaries
        """
        if rag_feature_names is None:
            rag_feature_names = ["avg_r_multiple", "win_rate", "sample_size", "max_similarity"]
        
        stats = {}
        
        for feature in rag_feature_names:
            if feature in features_df.columns:
                values = features_df[feature]
                non_zero_count = (values > 0).sum()
                
                stats[feature] = {
                    "mean": float(values.mean()),
                    "std": float(values.std()),
                    "min": float(values.min()),
                    "max": float(values.max()),
                    "non_zero_count": int(non_zero_count),
                    "coverage": float(non_zero_count / len(values)) if len(values) > 0 else 0.0,
                    "percentiles": {
                        "25": float(values.quantile(0.25)),
                        "50": float(values.quantile(0.50)),
                        "75": float(values.quantile(0.75)),
                        "95": float(values.quantile(0.95))
                    }
                }
        
        return stats

    async def train_with_rag(self) -> Dict[str, Any]:
        """
        Train Confluence Scorer with RAG feature augmentation.
        
        Returns:
            Training summary with RAG-specific metrics
        """
        logger.info(f"Starting RAG-augmented Confluence Scorer training (RAG enabled: {self.rag_enabled})")
        
        # Use base training method but with RAG-augmented feature loading
        original_load_method = self.load_feature_dataset
        self.load_feature_dataset = self.load_feature_dataset_with_rag
        
        # Collect RAG feature statistics across all instruments
        all_rag_stats = {}
        
        try:
            # Run base training
            training_result = await self.train()
            
            # Add RAG-specific analysis
            if training_result.get("status") == "completed":
                training_result["rag_enabled"] = self.rag_enabled
                training_result["rag_feature_count"] = 4 if self.rag_enabled else 0
                
                # Collect RAG statistics from all instruments
                for instrument in self.config.instruments:
                    try:
                        end_date = datetime.now()
                        start_date = end_date - timedelta(days=3 * 365)
                        
                        # Load features to analyze RAG statistics
                        features_df = await self.load_feature_dataset_with_rag(
                            instrument, start_date, end_date
                        )
                        
                        if not features_df.empty:
                            rag_stats = self.compute_rag_feature_statistics(features_df)
                            all_rag_stats[instrument] = rag_stats
                            
                            logger.info(f"RAG statistics for {instrument}:")
                            for feature, stats in rag_stats.items():
                                coverage = stats["coverage"]
                                mean_val = stats["mean"]
                                logger.info(f"  {feature}: coverage={coverage:.1%}, mean={mean_val:.3f}")
                    
                    except Exception as e:
                        logger.warning(f"Could not compute RAG statistics for {instrument}: {e}")
                
                training_result["rag_feature_statistics"] = all_rag_stats
                
                # Compute overall RAG coverage metrics
                if all_rag_stats:
                    coverage_values = []
                    avg_r_values = []
                    sample_size_values = []
                    
                    for instrument_stats in all_rag_stats.values():
                        if "sample_size" in instrument_stats:
                            coverage_values.append(instrument_stats["sample_size"]["coverage"])
                        if "avg_r_multiple" in instrument_stats:
                            avg_r_values.append(instrument_stats["avg_r_multiple"]["mean"])
                        if "sample_size" in instrument_stats:
                            sample_size_values.append(instrument_stats["sample_size"]["mean"])
                    
                    training_result["rag_summary"] = {
                        "overall_coverage": np.mean(coverage_values) if coverage_values else 0.0,
                        "avg_r_multiple_mean": np.mean(avg_r_values) if avg_r_values else 0.0,
                        "avg_sample_size": np.mean(sample_size_values) if sample_size_values else 0.0,
                    }
                    
                    logger.info("RAG Summary:")
                    logger.info(f"  Overall coverage: {training_result['rag_summary']['overall_coverage']:.1%}")
                    logger.info(f"  Mean R-multiple: {training_result['rag_summary']['avg_r_multiple_mean']:.3f}")
                    logger.info(f"  Mean sample size: {training_result['rag_summary']['avg_sample_size']:.3f}")
                
                # Add model artifact information for RAG version
                if self.rag_enabled:
                    training_result["model_version"] = "confluence-scorer-v2-rag"
                    training_result["features_enhanced"] = True
                else:
                    training_result["model_version"] = "confluence-scorer-v1-baseline"
                    training_result["features_enhanced"] = False
                    
            return training_result
            
        finally:
            # Restore original method
            self.load_feature_dataset = original_load_method


def main():
    """Main training entry point."""
    parser = argparse.ArgumentParser(description="Train Confluence Scorer with RAG features")
    parser.add_argument(
        "--instruments", 
        nargs="+", 
        default=["EURUSD"], 
        help="Instruments to train on"
    )
    parser.add_argument(
        "--disable-rag", 
        action="store_true", 
        help="Disable RAG features (baseline training)"
    )
    parser.add_argument(
        "--n-folds", 
        type=int, 
        default=8, 
        help="Number of cross-validation folds"
    )
    
    args = parser.parse_args()
    
    config = TrainingConfig(
        instruments=args.instruments,
        n_folds=args.n_folds,
    )
    
    trainer = RAGAugmentedTrainer(
        config=config, 
        rag_enabled=not args.disable_rag
    )
    
    import asyncio
    result = asyncio.run(trainer.train_with_rag())
    
    logger.info(f"Training completed: {result}")


if __name__ == "__main__":
    main()