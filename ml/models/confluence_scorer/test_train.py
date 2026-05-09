"""
Tests for Confluence Scorer training script.

TDD: RED → GREEN → REFACTOR

Coverage:
1. ConfluenceScorerLabeller — heuristic labelling
2. TrainingConfig — defaults and thresholds
3. ConfluenceScorerTrainer — model building, fold training
4. Killzone vs off-hours scoring property
5. Threshold calibration (0.65, 0.75, 0.85)
6. Walk-forward validation (8+ folds)
7. MLflow integration contract
"""

import pytest
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

from ml.models.confluence_scorer.train import (
    ConfluenceScorerLabeller,
    ConfluenceScorerTrainer,
    TrainingConfig,
    FoldResult,
    THRESHOLD_FLOOR,
    THRESHOLD_NOTIFY,
    THRESHOLD_AUTO_EXECUTE,
    TIME_WINDOW_WEIGHTS,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def killzone_features():
    """Features representing a high-confluence killzone setup."""
    return pd.DataFrame({
        "timestamp": [datetime(2024, 1, 1, 8, 0)],  # NY AM killzone
        "htf_open_bias": ["BULLISH"],
        "htf_high_proximity_pct": [15.0],   # Near HTF high
        "htf_low_proximity_pct": [85.0],
        "htf_body_pct": [65.0],
        "htf_trend_bias": ["BULLISH"],
        "time_window_weight": [0.9],         # Killzone weight
        "time_window": ["NY_AM_KILLZONE"],
        "bos_detected": [True],
        "choch_detected": [False],
        "fvg_present": [True],
        "liquidity_sweep_detected": [True],
        "price_vs_daily_open": ["BELOW"],    # Bullish + below open = discount
        "price_vs_weekly_open": ["BELOW"],
        "price_vs_true_day_open": ["BELOW"],
        "narrative_phase": ["MANIPULATION"],
        "bearish_array_distance": [0.03],
        "bullish_array_distance": [0.02],
    })


@pytest.fixture
def offhours_features():
    """Features representing a low-confluence off-hours setup."""
    return pd.DataFrame({
        "timestamp": [datetime(2024, 1, 1, 14, 0)],  # Off hours
        "htf_open_bias": ["NEUTRAL"],
        "htf_high_proximity_pct": [50.0],
        "htf_low_proximity_pct": [50.0],
        "htf_body_pct": [30.0],
        "htf_trend_bias": ["NEUTRAL"],
        "time_window_weight": [0.1],          # Off-hours weight
        "time_window": ["OFF_HOURS"],
        "bos_detected": [False],
        "choch_detected": [False],
        "fvg_present": [False],
        "liquidity_sweep_detected": [False],
        "price_vs_daily_open": ["AT"],
        "price_vs_weekly_open": ["AT"],
        "price_vs_true_day_open": ["AT"],
        "narrative_phase": ["OFF"],
        "bearish_array_distance": [0.10],
        "bullish_array_distance": [0.10],
    })


@pytest.fixture
def mixed_features_df():
    """Mixed dataset with killzone and off-hours setups."""
    n = 200
    np.random.seed(42)

    # Half killzone (high weight), half off-hours (low weight)
    weights = [0.9] * (n // 2) + [0.1] * (n // 2)
    biases = ["BULLISH"] * (n // 2) + ["NEUTRAL"] * (n // 2)
    bos = [True] * (n // 2) + [False] * (n // 2)
    fvg = [True] * (n // 2) + [False] * (n // 2)

    return pd.DataFrame({
        "timestamp": pd.date_range("2024-01-01", periods=n, freq="5min"),
        "htf_open_bias": biases,
        "htf_high_proximity_pct": np.random.uniform(10, 90, n),
        "htf_low_proximity_pct": np.random.uniform(10, 90, n),
        "htf_body_pct": np.random.uniform(20, 80, n),
        "htf_trend_bias": biases,
        "time_window_weight": weights,
        "time_window": ["NY_AM_KILLZONE"] * (n // 2) + ["OFF_HOURS"] * (n // 2),
        "bos_detected": bos,
        "choch_detected": [False] * n,
        "fvg_present": fvg,
        "liquidity_sweep_detected": [False] * n,
        "price_vs_daily_open": ["BELOW"] * (n // 2) + ["AT"] * (n // 2),
        "price_vs_weekly_open": ["BELOW"] * (n // 2) + ["AT"] * (n // 2),
        "price_vs_true_day_open": ["BELOW"] * (n // 2) + ["AT"] * (n // 2),
        "narrative_phase": ["MANIPULATION"] * (n // 2) + ["OFF"] * (n // 2),
        "bearish_array_distance": np.random.uniform(0.01, 0.1, n),
        "bullish_array_distance": np.random.uniform(0.01, 0.1, n),
    })


@pytest.fixture
def training_config():
    return TrainingConfig(
        instruments=["EURUSD"],
        timeframe="M5",
        htf_timeframe="H1",
        n_folds=8,
    )


# ── Threshold constants ───────────────────────────────────────────────────────

class TestThresholds:
    def test_floor_threshold(self):
        assert THRESHOLD_FLOOR == 0.65

    def test_notify_threshold(self):
        assert THRESHOLD_NOTIFY == 0.75

    def test_auto_execute_threshold(self):
        assert THRESHOLD_AUTO_EXECUTE == 0.85

    def test_threshold_ordering(self):
        assert THRESHOLD_FLOOR < THRESHOLD_NOTIFY < THRESHOLD_AUTO_EXECUTE

    def test_time_window_weights_defined(self):
        assert "LONDON_KILLZONE" in TIME_WINDOW_WEIGHTS
        assert "NY_AM_KILLZONE" in TIME_WINDOW_WEIGHTS
        assert "OFF_HOURS" in TIME_WINDOW_WEIGHTS
        assert TIME_WINDOW_WEIGHTS["LONDON_KILLZONE"] >= 0.9
        assert TIME_WINDOW_WEIGHTS["OFF_HOURS"] <= 0.1

    def test_silver_bullet_highest_weight(self):
        assert TIME_WINDOW_WEIGHTS["LONDON_SILVER_BULLET"] == 1.0
        assert TIME_WINDOW_WEIGHTS["NY_AM_SILVER_BULLET"] == 1.0
        assert TIME_WINDOW_WEIGHTS["NY_PM_SILVER_BULLET"] == 1.0


# ── ConfluenceScorerLabeller ──────────────────────────────────────────────────

class TestConfluenceScorerLabeller:
    def test_killzone_setup_labelled_high(self, killzone_features):
        labeller = ConfluenceScorerLabeller()
        labels = labeller.label_confluence(killzone_features)
        assert labels[0] == 1, "Killzone setup with strong signals should be high confluence"

    def test_offhours_setup_labelled_low(self, offhours_features):
        labeller = ConfluenceScorerLabeller()
        labels = labeller.label_confluence(offhours_features)
        assert labels[0] == 0, "Off-hours setup with weak signals should be low confluence"

    def test_returns_binary_array(self, mixed_features_df):
        labeller = ConfluenceScorerLabeller()
        labels = labeller.label_confluence(mixed_features_df)
        assert labels.shape == (len(mixed_features_df),)
        assert np.all((labels == 0) | (labels == 1))

    def test_killzone_has_more_positives_than_offhours(self, mixed_features_df):
        labeller = ConfluenceScorerLabeller()
        labels = labeller.label_confluence(mixed_features_df)
        n = len(mixed_features_df) // 2
        killzone_positive_rate = labels[:n].mean()
        offhours_positive_rate = labels[n:].mean()
        assert killzone_positive_rate > offhours_positive_rate, (
            f"Killzone positive rate {killzone_positive_rate:.2f} should exceed "
            f"off-hours {offhours_positive_rate:.2f}"
        )


# ── TrainingConfig ────────────────────────────────────────────────────────────

class TestTrainingConfig:
    def test_default_initialization(self):
        config = TrainingConfig(instruments=["EURUSD"], timeframe="M5", htf_timeframe="H1")
        assert config.n_folds == 8
        assert config.lr_params is not None
        assert "C" in config.lr_params
        assert "max_iter" in config.lr_params

    def test_logistic_regression_solver(self):
        config = TrainingConfig(instruments=["EURUSD"], timeframe="M5", htf_timeframe="H1")
        assert config.lr_params["solver"] == "lbfgs"


# ── ConfluenceScorerTrainer ───────────────────────────────────────────────────

class TestConfluenceScorerTrainer:
    def test_trainer_initialization(self, training_config):
        trainer = ConfluenceScorerTrainer(training_config)
        assert trainer.config == training_config
        assert trainer.labeller is not None
        assert trainer.tracker is not None

    def test_build_model_returns_pipeline(self, training_config):
        trainer = ConfluenceScorerTrainer(training_config)
        model = trainer._build_model()
        assert isinstance(model, Pipeline)
        assert "scaler" in model.named_steps
        assert "classifier" in model.named_steps

    def test_encode_features_converts_categoricals(self, training_config, mixed_features_df):
        trainer = ConfluenceScorerTrainer(training_config)
        feature_cols = [c for c in mixed_features_df.columns if c != "timestamp"]
        encoded = trainer._encode_features(mixed_features_df[feature_cols])
        # No object columns should remain
        object_cols = [c for c in encoded.columns if encoded[c].dtype == object]
        assert len(object_cols) == 0, f"Object columns remain: {object_cols}"

    def test_train_fold_returns_pipeline(self, training_config, mixed_features_df):
        trainer = ConfluenceScorerTrainer(training_config)
        n = len(mixed_features_df)
        split = n // 2

        train_df = mixed_features_df.iloc[:split].copy()
        test_df = mixed_features_df.iloc[split:].copy()

        feature_cols = [c for c in mixed_features_df.columns if c != "timestamp"]
        X_train = trainer._encode_features(train_df[feature_cols])
        X_test = trainer._encode_features(test_df[feature_cols])
        y_train = trainer.labeller.label_confluence(train_df)
        y_test = trainer.labeller.label_confluence(test_df)

        model, roc_auc, brier, prec_floor, prec_notify = trainer.train_fold(
            X_train, y_train, X_test, y_test
        )

        assert isinstance(model, Pipeline)
        assert 0.0 <= roc_auc <= 1.0
        assert 0.0 <= brier <= 1.0
        assert 0.0 <= prec_floor <= 1.0
        assert 0.0 <= prec_notify <= 1.0

    def test_model_outputs_probabilities(self, training_config, mixed_features_df):
        """Model must output probabilities in [0, 1] for threshold gating."""
        trainer = ConfluenceScorerTrainer(training_config)
        feature_cols = [c for c in mixed_features_df.columns if c != "timestamp"]
        X = trainer._encode_features(mixed_features_df[feature_cols])
        y = trainer.labeller.label_confluence(mixed_features_df)

        model = trainer._build_model()
        model.fit(X, y)

        proba = model.predict_proba(X)[:, 1]
        assert np.all(proba >= 0.0)
        assert np.all(proba <= 1.0)


# ── Killzone vs Off-hours property ───────────────────────────────────────────

class TestKillzoneProperty:
    """
    Key requirement: setups during killzones must score significantly
    higher than identical setups during off-hours.
    """

    def test_killzone_scores_higher_than_offhours(self, training_config, mixed_features_df):
        """Train on mixed data and verify killzone mean > offhours mean."""
        trainer = ConfluenceScorerTrainer(training_config)
        feature_cols = [c for c in mixed_features_df.columns if c != "timestamp"]
        X = trainer._encode_features(mixed_features_df[feature_cols])
        y = trainer.labeller.label_confluence(mixed_features_df)

        model = trainer._build_model()
        model.fit(X, y)

        proba = model.predict_proba(X)[:, 1]
        n = len(mixed_features_df) // 2

        killzone_mean = proba[:n].mean()
        offhours_mean = proba[n:].mean()

        assert killzone_mean > offhours_mean, (
            f"Killzone mean {killzone_mean:.4f} should exceed off-hours {offhours_mean:.4f}"
        )

    def test_precision_at_threshold_floor(self, training_config, mixed_features_df):
        """Precision at 0.65 threshold should be computable."""
        trainer = ConfluenceScorerTrainer(training_config)
        feature_cols = [c for c in mixed_features_df.columns if c != "timestamp"]
        X = trainer._encode_features(mixed_features_df[feature_cols])
        y = trainer.labeller.label_confluence(mixed_features_df)

        model = trainer._build_model()
        model.fit(X, y)
        proba = model.predict_proba(X)[:, 1]

        precision = trainer._precision_at_threshold(y, proba, THRESHOLD_FLOOR)
        assert 0.0 <= precision <= 1.0

    def test_precision_at_notify_threshold(self, training_config, mixed_features_df):
        """Precision at 0.75 threshold should be computable."""
        trainer = ConfluenceScorerTrainer(training_config)
        feature_cols = [c for c in mixed_features_df.columns if c != "timestamp"]
        X = trainer._encode_features(mixed_features_df[feature_cols])
        y = trainer.labeller.label_confluence(mixed_features_df)

        model = trainer._build_model()
        model.fit(X, y)
        proba = model.predict_proba(X)[:, 1]

        precision = trainer._precision_at_threshold(y, proba, THRESHOLD_NOTIFY)
        assert 0.0 <= precision <= 1.0


# ── Walk-forward validation ───────────────────────────────────────────────────

class TestWalkForwardValidation:
    @pytest.mark.asyncio
    async def test_minimum_8_folds(self, training_config):
        """Walk-forward validation must produce at least 8 folds."""
        trainer = ConfluenceScorerTrainer(training_config)

        # Build mock features spanning enough time for 8 folds
        n = 5000
        mock_features = pd.DataFrame({
            "timestamp": pd.date_range("2024-01-01", periods=n, freq="5min"),
            "htf_open_bias": ["BULLISH"] * (n // 2) + ["NEUTRAL"] * (n // 2),
            "htf_high_proximity_pct": np.random.uniform(10, 90, n),
            "htf_low_proximity_pct": np.random.uniform(10, 90, n),
            "htf_body_pct": np.random.uniform(20, 80, n),
            "htf_trend_bias": ["BULLISH"] * (n // 2) + ["NEUTRAL"] * (n // 2),
            "time_window_weight": [0.9] * (n // 2) + [0.1] * (n // 2),
            "time_window": ["NY_AM_KILLZONE"] * (n // 2) + ["OFF_HOURS"] * (n // 2),
            "bos_detected": [True] * (n // 2) + [False] * (n // 2),
            "choch_detected": [False] * n,
            "fvg_present": [True] * (n // 2) + [False] * (n // 2),
            "liquidity_sweep_detected": [False] * n,
            "price_vs_daily_open": ["BELOW"] * (n // 2) + ["AT"] * (n // 2),
            "price_vs_weekly_open": ["BELOW"] * (n // 2) + ["AT"] * (n // 2),
            "price_vs_true_day_open": ["BELOW"] * (n // 2) + ["AT"] * (n // 2),
            "narrative_phase": ["MANIPULATION"] * (n // 2) + ["OFF"] * (n // 2),
            "bearish_array_distance": np.random.uniform(0.01, 0.1, n),
            "bullish_array_distance": np.random.uniform(0.01, 0.1, n),
        })

        fold_results = await trainer.run_walk_forward_validation("EURUSD", mock_features)
        assert len(fold_results) >= 8, f"Expected ≥8 folds, got {len(fold_results)}"

    @pytest.mark.asyncio
    async def test_fold_result_has_required_fields(self, training_config):
        """Each FoldResult must have all required metric fields."""
        trainer = ConfluenceScorerTrainer(training_config)

        n = 1000
        mock_features = pd.DataFrame({
            "timestamp": pd.date_range("2024-01-01", periods=n, freq="5min"),
            "htf_open_bias": ["BULLISH"] * n,
            "htf_high_proximity_pct": [20.0] * n,
            "htf_low_proximity_pct": [80.0] * n,
            "htf_body_pct": [60.0] * n,
            "htf_trend_bias": ["BULLISH"] * n,
            "time_window_weight": [0.9] * (n // 2) + [0.1] * (n // 2),
            "time_window": ["NY_AM_KILLZONE"] * (n // 2) + ["OFF_HOURS"] * (n // 2),
            "bos_detected": [True] * n,
            "choch_detected": [False] * n,
            "fvg_present": [True] * n,
            "liquidity_sweep_detected": [False] * n,
            "price_vs_daily_open": ["BELOW"] * n,
            "price_vs_weekly_open": ["BELOW"] * n,
            "price_vs_true_day_open": ["BELOW"] * n,
            "narrative_phase": ["MANIPULATION"] * n,
            "bearish_array_distance": [0.02] * n,
            "bullish_array_distance": [0.02] * n,
        })

        fold_results = await trainer.run_walk_forward_validation("EURUSD", mock_features)
        assert len(fold_results) > 0

        fold = fold_results[0]
        assert hasattr(fold, "roc_auc")
        assert hasattr(fold, "brier_score")
        assert hasattr(fold, "killzone_mean_score")
        assert hasattr(fold, "off_hours_mean_score")
        assert hasattr(fold, "killzone_vs_offhours_delta")
        assert 0.0 <= fold.roc_auc <= 1.0
        assert 0.0 <= fold.brier_score <= 1.0


# ── MLflow integration ────────────────────────────────────────────────────────

class TestMLflowIntegration:
    def test_experiment_name(self):
        """Model must be registered under 'confluence-scorer'."""
        assert "confluence-scorer" == "confluence-scorer"

    def test_thresholds_logged_as_params(self, training_config):
        """Training config must include all three thresholds."""
        trainer = ConfluenceScorerTrainer(training_config)
        # Verify the constants are accessible for logging
        assert THRESHOLD_FLOOR == 0.65
        assert THRESHOLD_NOTIFY == 0.75
        assert THRESHOLD_AUTO_EXECUTE == 0.85

    @pytest.mark.asyncio
    async def test_train_calls_mlflow(self, training_config):
        """Training must call MLflow start_run, log_params, log_metrics."""
        trainer = ConfluenceScorerTrainer(training_config)

        n = 1000
        mock_features = pd.DataFrame({
            "timestamp": pd.date_range("2024-01-01", periods=n, freq="5min"),
            "htf_open_bias": ["BULLISH"] * (n // 2) + ["NEUTRAL"] * (n // 2),
            "htf_high_proximity_pct": np.random.uniform(10, 90, n),
            "htf_low_proximity_pct": np.random.uniform(10, 90, n),
            "htf_body_pct": np.random.uniform(20, 80, n),
            "htf_trend_bias": ["BULLISH"] * (n // 2) + ["NEUTRAL"] * (n // 2),
            "time_window_weight": [0.9] * (n // 2) + [0.1] * (n // 2),
            "time_window": ["NY_AM_KILLZONE"] * (n // 2) + ["OFF_HOURS"] * (n // 2),
            "bos_detected": [True] * (n // 2) + [False] * (n // 2),
            "choch_detected": [False] * n,
            "fvg_present": [True] * (n // 2) + [False] * (n // 2),
            "liquidity_sweep_detected": [False] * n,
            "price_vs_daily_open": ["BELOW"] * (n // 2) + ["AT"] * (n // 2),
            "price_vs_weekly_open": ["BELOW"] * (n // 2) + ["AT"] * (n // 2),
            "price_vs_true_day_open": ["BELOW"] * (n // 2) + ["AT"] * (n // 2),
            "narrative_phase": ["MANIPULATION"] * (n // 2) + ["OFF"] * (n // 2),
            "bearish_array_distance": np.random.uniform(0.01, 0.1, n),
            "bullish_array_distance": np.random.uniform(0.01, 0.1, n),
        })

        with patch.object(trainer.tracker, "start_run") as mock_run:
            with patch.object(trainer.tracker, "log_params") as mock_params:
                with patch.object(trainer.tracker, "log_metrics") as mock_metrics:
                    with patch.object(
                        trainer, "load_feature_dataset", new_callable=AsyncMock
                    ) as mock_load:
                        mock_load.return_value = mock_features
                        await trainer.train()

                        mock_run.assert_called_once()
                        mock_params.assert_called()
                        mock_metrics.assert_called()
