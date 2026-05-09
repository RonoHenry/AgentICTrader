"""
Tests for Regime Classifier training script.

This test module verifies:
- Training configuration initialization
- Regime labelling heuristics
- Feature preparation logic
- Walk-forward validation setup

**Validates: Task 20 - Train and validate Regime Classifier**
"""

import pytest
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

# Import training components
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from ml.models.regime_classifier.train import (
    TrainingConfig,
    RegimeLabeller,
    REGIME_CLASSES,
)


class TestTrainingConfig:
    """Test TrainingConfig dataclass."""
    
    def test_default_config(self):
        """Test default configuration initialization."""
        config = TrainingConfig(
            instruments=["EURUSD"],
            timeframe="M5",
            htf_timeframe="H1",
        )
        
        assert config.instruments == ["EURUSD"]
        assert config.timeframe == "M5"
        assert config.htf_timeframe == "H1"
        assert config.n_folds == 8
        assert config.fold_window_months == 3
        assert config.test_window_months == 1
        assert config.min_candles_per_fold == 1000
        
        # Check XGBoost params
        assert config.xgb_params is not None
        assert config.xgb_params["objective"] == "multi:softmax"
        assert config.xgb_params["num_class"] == len(REGIME_CLASSES)
        assert config.xgb_params["max_depth"] == 6
        assert config.xgb_params["learning_rate"] == 0.1
    
    def test_custom_config(self):
        """Test custom configuration."""
        custom_params = {
            "objective": "multi:softmax",
            "num_class": 5,
            "max_depth": 8,
            "learning_rate": 0.05,
            "n_estimators": 200,
        }
        
        config = TrainingConfig(
            instruments=["EURUSD", "GBPUSD"],
            timeframe="M15",
            htf_timeframe="H4",
            n_folds=10,
            fold_window_months=6,
            test_window_months=2,
            xgb_params=custom_params,
        )
        
        assert config.instruments == ["EURUSD", "GBPUSD"]
        assert config.timeframe == "M15"
        assert config.htf_timeframe == "H4"
        assert config.n_folds == 10
        assert config.fold_window_months == 6
        assert config.test_window_months == 2
        assert config.xgb_params["max_depth"] == 8
        assert config.xgb_params["learning_rate"] == 0.05


class TestRegimeLabeller:
    """Test RegimeLabeller heuristic rules."""
    
    def test_news_driven_labelling(self):
        """Test NEWS_DRIVEN regime labelling."""
        labeller = RegimeLabeller()
        
        # Create features for news-driven scenario
        features = pd.DataFrame([{
            "htf_trend_bias": "BULLISH",
            "bos_detected": False,
            "choch_detected": False,
            "fvg_present": False,
            "time_window": "NEWS_WINDOW",
            "htf_body_pct": 70.0,  # High volatility
            "htf_high_proximity_pct": 30.0,
            "htf_low_proximity_pct": 70.0,
        }])
        
        labels = labeller.label_regime(features)
        
        assert len(labels) == 1
        assert labels[0] == "NEWS_DRIVEN"
    
    def test_breakout_labelling(self):
        """Test BREAKOUT regime labelling."""
        labeller = RegimeLabeller()
        
        # Create features for breakout scenario
        features = pd.DataFrame([{
            "htf_trend_bias": "BULLISH",
            "bos_detected": True,
            "choch_detected": False,
            "fvg_present": True,  # FVG present
            "time_window": "NY_AM_KILLZONE",
            "htf_body_pct": 60.0,  # Strong body
            "htf_high_proximity_pct": 20.0,
            "htf_low_proximity_pct": 80.0,
        }])
        
        labels = labeller.label_regime(features)
        
        assert len(labels) == 1
        assert labels[0] == "BREAKOUT"
    
    def test_trending_bullish_labelling(self):
        """Test TRENDING_BULLISH regime labelling."""
        labeller = RegimeLabeller()
        
        # Create features for trending bullish scenario
        features = pd.DataFrame([{
            "htf_trend_bias": "BULLISH",
            "bos_detected": True,
            "choch_detected": False,
            "fvg_present": False,
            "time_window": "LONDON_KILLZONE",
            "htf_body_pct": 45.0,
            "htf_high_proximity_pct": 25.0,
            "htf_low_proximity_pct": 75.0,
        }])
        
        labels = labeller.label_regime(features)
        
        assert len(labels) == 1
        assert labels[0] == "TRENDING_BULLISH"
    
    def test_trending_bearish_labelling(self):
        """Test TRENDING_BEARISH regime labelling."""
        labeller = RegimeLabeller()
        
        # Create features for trending bearish scenario
        features = pd.DataFrame([{
            "htf_trend_bias": "BEARISH",
            "bos_detected": True,
            "choch_detected": False,
            "fvg_present": False,
            "time_window": "NY_AM_KILLZONE",
            "htf_body_pct": 50.0,
            "htf_high_proximity_pct": 80.0,
            "htf_low_proximity_pct": 20.0,
        }])
        
        labels = labeller.label_regime(features)
        
        assert len(labels) == 1
        assert labels[0] == "TRENDING_BEARISH"
    
    def test_ranging_labelling_neutral_bias(self):
        """Test RANGING regime labelling with neutral bias."""
        labeller = RegimeLabeller()
        
        # Create features for ranging scenario (neutral bias)
        features = pd.DataFrame([{
            "htf_trend_bias": "NEUTRAL",
            "bos_detected": False,
            "choch_detected": False,
            "fvg_present": False,
            "time_window": "ASIAN_RANGE",
            "htf_body_pct": 20.0,  # Small body
            "htf_high_proximity_pct": 50.0,
            "htf_low_proximity_pct": 50.0,
        }])
        
        labels = labeller.label_regime(features)
        
        assert len(labels) == 1
        assert labels[0] == "RANGING"
    
    def test_ranging_labelling_choch(self):
        """Test RANGING regime labelling with CHoCH."""
        labeller = RegimeLabeller()
        
        # Create features for ranging scenario (CHoCH detected)
        features = pd.DataFrame([{
            "htf_trend_bias": "BULLISH",
            "bos_detected": False,
            "choch_detected": True,  # CHoCH indicates reversal/ranging
            "fvg_present": False,
            "time_window": "LONDON_CLOSE",
            "htf_body_pct": 35.0,
            "htf_high_proximity_pct": 45.0,
            "htf_low_proximity_pct": 55.0,
        }])
        
        labels = labeller.label_regime(features)
        
        assert len(labels) == 1
        assert labels[0] == "RANGING"
    
    def test_ranging_labelling_mid_range(self):
        """Test RANGING regime labelling with mid-range price."""
        labeller = RegimeLabeller()
        
        # Create features for ranging scenario (mid-range price)
        features = pd.DataFrame([{
            "htf_trend_bias": "BULLISH",
            "bos_detected": False,
            "choch_detected": False,
            "fvg_present": False,
            "time_window": "OFF_HOURS",
            "htf_body_pct": 40.0,
            "htf_high_proximity_pct": 50.0,  # Mid-range
            "htf_low_proximity_pct": 50.0,   # Mid-range
        }])
        
        labels = labeller.label_regime(features)
        
        assert len(labels) == 1
        assert labels[0] == "RANGING"
    
    def test_multiple_candles_labelling(self):
        """Test labelling multiple candles."""
        labeller = RegimeLabeller()
        
        # Create features for multiple scenarios
        features = pd.DataFrame([
            {
                "htf_trend_bias": "BULLISH",
                "bos_detected": True,
                "choch_detected": False,
                "fvg_present": False,
                "time_window": "NY_AM_KILLZONE",
                "htf_body_pct": 45.0,
                "htf_high_proximity_pct": 25.0,
                "htf_low_proximity_pct": 75.0,
            },
            {
                "htf_trend_bias": "NEUTRAL",
                "bos_detected": False,
                "choch_detected": False,
                "fvg_present": False,
                "time_window": "ASIAN_RANGE",
                "htf_body_pct": 15.0,
                "htf_high_proximity_pct": 50.0,
                "htf_low_proximity_pct": 50.0,
            },
            {
                "htf_trend_bias": "BEARISH",
                "bos_detected": True,
                "choch_detected": False,
                "fvg_present": True,
                "time_window": "LONDON_KILLZONE",
                "htf_body_pct": 55.0,
                "htf_high_proximity_pct": 75.0,
                "htf_low_proximity_pct": 25.0,
            },
        ])
        
        labels = labeller.label_regime(features)
        
        assert len(labels) == 3
        assert labels[0] == "TRENDING_BULLISH"
        assert labels[1] == "RANGING"
        assert labels[2] == "BREAKOUT"
    
    def test_all_regime_classes_covered(self):
        """Test that all regime classes can be labelled."""
        labeller = RegimeLabeller()
        
        # Create features that should trigger each regime class
        features = pd.DataFrame([
            # TRENDING_BULLISH
            {
                "htf_trend_bias": "BULLISH",
                "bos_detected": True,
                "choch_detected": False,
                "fvg_present": False,
                "time_window": "NY_AM_KILLZONE",
                "htf_body_pct": 45.0,
                "htf_high_proximity_pct": 25.0,
                "htf_low_proximity_pct": 75.0,
            },
            # TRENDING_BEARISH
            {
                "htf_trend_bias": "BEARISH",
                "bos_detected": True,
                "choch_detected": False,
                "fvg_present": False,
                "time_window": "LONDON_KILLZONE",
                "htf_body_pct": 50.0,
                "htf_high_proximity_pct": 80.0,
                "htf_low_proximity_pct": 20.0,
            },
            # RANGING
            {
                "htf_trend_bias": "NEUTRAL",
                "bos_detected": False,
                "choch_detected": False,
                "fvg_present": False,
                "time_window": "ASIAN_RANGE",
                "htf_body_pct": 20.0,
                "htf_high_proximity_pct": 50.0,
                "htf_low_proximity_pct": 50.0,
            },
            # BREAKOUT
            {
                "htf_trend_bias": "BULLISH",
                "bos_detected": True,
                "choch_detected": False,
                "fvg_present": True,
                "time_window": "NY_AM_KILLZONE",
                "htf_body_pct": 60.0,
                "htf_high_proximity_pct": 20.0,
                "htf_low_proximity_pct": 80.0,
            },
            # NEWS_DRIVEN
            {
                "htf_trend_bias": "BULLISH",
                "bos_detected": False,
                "choch_detected": False,
                "fvg_present": False,
                "time_window": "NEWS_WINDOW",
                "htf_body_pct": 75.0,
                "htf_high_proximity_pct": 30.0,
                "htf_low_proximity_pct": 70.0,
            },
        ])
        
        labels = labeller.label_regime(features)
        
        assert len(labels) == 5
        assert set(labels) == set(REGIME_CLASSES)
        assert labels[0] == "TRENDING_BULLISH"
        assert labels[1] == "TRENDING_BEARISH"
        assert labels[2] == "RANGING"
        assert labels[3] == "BREAKOUT"
        assert labels[4] == "NEWS_DRIVEN"


class TestRegimeClasses:
    """Test regime class constants."""
    
    def test_regime_classes_defined(self):
        """Test that all regime classes are defined."""
        assert len(REGIME_CLASSES) == 5
        assert "TRENDING_BULLISH" in REGIME_CLASSES
        assert "TRENDING_BEARISH" in REGIME_CLASSES
        assert "RANGING" in REGIME_CLASSES
        assert "BREAKOUT" in REGIME_CLASSES
        assert "NEWS_DRIVEN" in REGIME_CLASSES
    
    def test_regime_classes_unique(self):
        """Test that regime classes are unique."""
        assert len(REGIME_CLASSES) == len(set(REGIME_CLASSES))


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
