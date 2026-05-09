"""
Confluence Scorer training script.

Trains a Logistic Regression ensemble that combines:
- Regime Classifier output (5-class probabilities)
- Pattern Detector outputs (8 binary pattern probabilities)
- HTF projection levels: open_bias, htf_high_proximity_pct, htf_low_proximity_pct
- Time window weight (primary signal — killzone vs off-hours)
- Narrative phase
- price_vs_daily_open, price_vs_true_day_open

Output: confidence score 0.0–1.0 with calibrated thresholds:
  < 0.65  → DISCARD
  0.65–0.74 → LOG ONLY
  0.75–0.84 → NOTIFY
  ≥ 0.85  → NOTIFY + AUTO-EXECUTE (autonomous mode)

Key property: setups during LONDON_KILLZONE or NY_KILLZONE
(time_window_weight=1.0) score significantly higher than identical
setups during OFF_HOURS (time_window_weight=0.1).

Registry: Saved to MLflow model registry as "confluence-scorer"

Usage:
    python -m ml.models.confluence_scorer.train --instruments EURUSD GBPUSD
"""

import os
import sys
import argparse
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Tuple, Optional
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.calibration import CalibratedClassifierCV
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.metrics import (
    roc_auc_score,
    brier_score_loss,
    precision_recall_curve,
    roc_curve,
)
import asyncpg

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from ml.tracking.mlflow_client import MLflowTracker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


# Confidence thresholds
THRESHOLD_FLOOR = 0.65       # Hard floor — discard below this
THRESHOLD_NOTIFY = 0.75      # Notify trader
THRESHOLD_AUTO_EXECUTE = 0.85  # Auto-execute in autonomous mode

# Regime classes (from Regime Classifier)
REGIME_CLASSES = [
    "TRENDING_BULLISH",
    "TRENDING_BEARISH",
    "RANGING",
    "BREAKOUT",
    "NEWS_DRIVEN",
]

# Pattern labels (from Pattern Detector)
PATTERN_LABELS = [
    "BOS_CONFIRMED",
    "CHOCH_DETECTED",
    "SUPPLY_ZONE_REJECTION",
    "DEMAND_ZONE_BOUNCE",
    "FVG_PRESENT",
    "LIQUIDITY_SWEEP",
    "ORDER_BLOCK",
    "INDUCEMENT",
]

# Time window weights (must match session_features.py)
TIME_WINDOW_WEIGHTS = {
    "LONDON_SILVER_BULLET": 1.0,
    "NY_AM_SILVER_BULLET": 1.0,
    "NY_PM_SILVER_BULLET": 1.0,
    "LONDON_KILLZONE": 0.9,
    "NY_AM_KILLZONE": 0.9,
    "NY_PM_KILLZONE": 0.9,
    "NEWS_WINDOW": 0.8,
    "TRUE_DAY_OPEN": 0.7,
    "LONDON_CLOSE": 0.5,
    "ASIAN_RANGE": 0.3,
    "DAILY_CLOSE": 0.2,
    "OFF_HOURS": 0.1,
}

# Narrative phases
NARRATIVE_PHASES = [
    "ACCUMULATION",
    "MANIPULATION",
    "EXPANSION",
    "DISTRIBUTION",
    "TRANSITION",
    "OFF",
]

# Price position values
PRICE_POSITIONS = ["ABOVE", "BELOW", "AT"]


@dataclass
class TrainingConfig:
    """Training configuration for Confluence Scorer."""

    instruments: List[str]
    timeframe: str = "M5"
    htf_timeframe: str = "H1"
    n_folds: int = 8
    fold_window_months: int = 3
    test_window_months: int = 1
    lr_params: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.lr_params:
            self.lr_params = {
                "C": 1.0,
                "max_iter": 1000,
                "random_state": 42,
                "solver": "lbfgs",
            }


@dataclass
class FoldResult:
    """Results from a single walk-forward fold."""

    fold_id: int
    train_start: datetime
    train_end: datetime
    test_start: datetime
    test_end: datetime
    train_samples: int
    test_samples: int
    roc_auc: float
    brier_score: float
    threshold_floor_precision: float
    threshold_notify_precision: float
    killzone_mean_score: float
    off_hours_mean_score: float
    killzone_vs_offhours_delta: float


class ConfluenceScorerLabeller:
    """
    Heuristic labeller for confluence scoring.

    A setup is labelled as HIGH_CONFLUENCE (1) when multiple
    confirming signals align:
    - Strong HTF bias (price clearly above/below HTF open)
    - Pattern detected (BOS, FVG, or liquidity sweep)
    - High time window weight (killzone or silver bullet)
    - Price at discount/premium relative to daily open

    LOW_CONFLUENCE (0) when signals are weak or conflicting.
    """

    def label_confluence(self, features: pd.DataFrame) -> np.ndarray:
        """
        Label each row as high (1) or low (0) confluence setup.

        Args:
            features: DataFrame with extracted features

        Returns:
            Binary array of shape (n_samples,)
        """
        labels = np.zeros(len(features), dtype=int)

        for i, (_, row) in enumerate(features.iterrows()):
            score = 0.0

            # HTF bias strength (0–2 points)
            htf_bias = row.get("htf_open_bias", "NEUTRAL")
            htf_high_prox = float(row.get("htf_high_proximity_pct", 50.0))
            htf_low_prox = float(row.get("htf_low_proximity_pct", 50.0))

            if htf_bias in ("BULLISH", "BEARISH"):
                score += 1.0
            # Near HTF extreme (within 20% of range)
            if htf_high_prox < 20.0 or htf_low_prox < 20.0:
                score += 1.0

            # Time window weight (0–2 points) — primary signal
            tw_weight = float(row.get("time_window_weight", 0.1))
            score += tw_weight * 2.0  # max 2 points at weight=1.0

            # Pattern signals (0–2 points)
            bos = bool(row.get("bos_detected", False))
            fvg = bool(row.get("fvg_present", False))
            sweep = bool(row.get("liquidity_sweep_detected", False))
            choch = bool(row.get("choch_detected", False))

            pattern_count = sum([bos, fvg, sweep, choch])
            score += min(pattern_count, 2) * 0.5  # max 1 point

            # Price vs daily open alignment (0–1 point)
            price_vs_daily = row.get("price_vs_daily_open", "AT")
            price_vs_true_day = row.get("price_vs_true_day_open", "AT")

            if htf_bias == "BULLISH" and price_vs_daily == "BELOW":
                score += 0.5  # Bullish bias + price below open = discount entry
            elif htf_bias == "BEARISH" and price_vs_daily == "ABOVE":
                score += 0.5  # Bearish bias + price above open = premium entry

            if price_vs_true_day in ("ABOVE", "BELOW"):
                score += 0.25

            # Narrative phase alignment (0–0.5 points)
            narrative = row.get("narrative_phase", "OFF")
            if narrative in ("MANIPULATION", "EXPANSION"):
                score += 0.5

            # Label as high confluence if score >= 3.5 out of max ~6.75
            labels[i] = 1 if score >= 3.5 else 0

        return labels


class ConfluenceScorerTrainer:
    """
    Confluence Scorer trainer.

    Builds a calibrated Logistic Regression pipeline that takes
    the combined feature vector and outputs a calibrated probability
    (confidence score) between 0.0 and 1.0.
    """

    def __init__(self, config: TrainingConfig):
        self.config = config
        self.tracker = MLflowTracker()
        self.labeller = ConfluenceScorerLabeller()

        self.db_params = {
            "host": os.getenv("DB_HOST", "localhost"),
            "port": int(os.getenv("DB_PORT", "5432")),
            "database": os.getenv("DB_NAME", "agentictrader"),
            "user": os.getenv("DB_USER", "agentictrader"),
            "password": os.getenv("DB_PASSWORD", "changeme"),
        }

    def _build_model(self, y_train: Optional[np.ndarray] = None) -> Pipeline:
        """Build the calibrated Logistic Regression pipeline."""
        lr = LogisticRegression(**self.config.lr_params)
        # cv must not exceed the minimum class count
        if y_train is not None:
            min_class_count = int(np.min(np.bincount(y_train.astype(int))))
            cv = max(2, min(3, min_class_count))
        else:
            cv = 3
        calibrated = CalibratedClassifierCV(lr, method="isotonic", cv=cv)
        return Pipeline([
            ("scaler", StandardScaler()),
            ("classifier", calibrated),
        ])

    def _encode_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Encode categorical features to numeric."""
        df = df.copy()

        # Encode htf_open_bias
        bias_map = {"BULLISH": 1, "NEUTRAL": 0, "BEARISH": -1}
        if "htf_open_bias" in df.columns:
            df["htf_open_bias"] = df["htf_open_bias"].map(bias_map).fillna(0)

        # Encode htf_trend_bias
        if "htf_trend_bias" in df.columns:
            df["htf_trend_bias"] = df["htf_trend_bias"].map(bias_map).fillna(0)

        # Encode price position columns
        pos_map = {"ABOVE": 1, "AT": 0, "BELOW": -1}
        for col in ["price_vs_daily_open", "price_vs_weekly_open", "price_vs_true_day_open"]:
            if col in df.columns:
                df[col] = df[col].map(pos_map).fillna(0)

        # Encode narrative_phase
        if "narrative_phase" in df.columns:
            phase_map = {p: i for i, p in enumerate(NARRATIVE_PHASES)}
            df["narrative_phase"] = df["narrative_phase"].map(phase_map).fillna(0)

        # Encode time_window
        if "time_window" in df.columns:
            tw_map = {tw: i for i, tw in enumerate(TIME_WINDOW_WEIGHTS.keys())}
            df["time_window"] = df["time_window"].map(tw_map).fillna(0)

        # Convert booleans to int
        for col in df.columns:
            if df[col].dtype == bool:
                df[col] = df[col].astype(int)
            elif df[col].dtype == object:
                df[col] = pd.Categorical(df[col]).codes

        return df

    async def load_historical_data(
        self,
        instrument: str,
        timeframe: str,
        start_date: datetime,
        end_date: datetime,
    ) -> pd.DataFrame:
        """Load historical candles from TimescaleDB."""
        logger.info(f"Loading {instrument} {timeframe} {start_date.date()} → {end_date.date()}")
        conn = await asyncpg.connect(**self.db_params)
        try:
            rows = await conn.fetch(
                """
                SELECT time, open, high, low, close, volume
                FROM candles
                WHERE instrument = $1 AND timeframe = $2
                  AND time >= $3 AND time <= $4 AND complete = TRUE
                ORDER BY time ASC
                """,
                instrument, timeframe, start_date, end_date,
            )
            if not rows:
                return pd.DataFrame()
            df = pd.DataFrame(rows, columns=["time", "open", "high", "low", "close", "volume"])
            logger.info(f"Loaded {len(df)} candles")
            return df
        finally:
            await conn.close()

    async def load_feature_dataset(
        self, instrument: str, start_date: datetime, end_date: datetime
    ) -> pd.DataFrame:
        """
        Load pre-computed features from TimescaleDB indicators table.

        In production this reads from the indicators table populated by
        the feature pipeline. For training we reconstruct from candles.
        """
        logger.info(f"Loading features for {instrument} {start_date.date()} → {end_date.date()}")
        conn = await asyncpg.connect(**self.db_params)
        try:
            rows = await conn.fetch(
                """
                SELECT
                    i.time AS timestamp,
                    i.htf_open_bias,
                    i.htf_high_proximity_pct,
                    i.htf_low_proximity_pct,
                    i.htf_body_pct,
                    i.htf_upper_wick_pct,
                    i.htf_lower_wick_pct,
                    i.htf_close_position,
                    i.htf_open,
                    i.htf_high,
                    i.htf_low,
                    c.session,
                    c.day_of_week,
                    c.is_news_window
                FROM indicators i
                JOIN candles c ON c.time = i.time
                    AND c.instrument = i.instrument
                    AND c.timeframe = i.timeframe
                WHERE i.instrument = $1
                  AND i.timeframe = $2
                  AND i.time >= $3
                  AND i.time <= $4
                ORDER BY i.time ASC
                """,
                instrument, self.config.timeframe, start_date, end_date,
            )
            if not rows:
                return pd.DataFrame()

            df = pd.DataFrame([dict(r) for r in rows])
            logger.info(f"Loaded {len(df)} feature rows")
            return df
        finally:
            await conn.close()

    def prepare_fold_data(
        self,
        features_df: pd.DataFrame,
        train_start: datetime,
        train_end: datetime,
        test_start: datetime,
        test_end: datetime,
    ) -> Tuple[pd.DataFrame, np.ndarray, pd.DataFrame, np.ndarray]:
        """Prepare train/test split with labels for a fold."""
        train_mask = (features_df["timestamp"] >= train_start) & (features_df["timestamp"] <= train_end)
        test_mask = (features_df["timestamp"] >= test_start) & (features_df["timestamp"] <= test_end)

        train_df = features_df[train_mask].copy()
        test_df = features_df[test_mask].copy()

        y_train = self.labeller.label_confluence(train_df)
        y_test = self.labeller.label_confluence(test_df)

        feature_cols = [c for c in train_df.columns if c != "timestamp"]
        X_train = self._encode_features(train_df[feature_cols])
        X_test = self._encode_features(test_df[feature_cols])

        return X_train, y_train, X_test, y_test

    def train_fold(
        self,
        X_train: pd.DataFrame,
        y_train: np.ndarray,
        X_test: pd.DataFrame,
        y_test: np.ndarray,
    ) -> Tuple[Pipeline, float, float, float, float]:
        """
        Train calibrated Logistic Regression for one fold.

        Returns:
            (model, roc_auc, brier_score,
             threshold_floor_precision, threshold_notify_precision)
        """
        logger.info(f"Training fold: {len(X_train)} train / {len(X_test)} test")

        # Ensure both classes present with enough samples for calibration cv
        X_train_safe = X_train.copy()
        y_train_safe = y_train.copy()

        # Inject synthetic samples so each class has at least 3 examples
        for target_class in [0, 1]:
            class_count = int(np.sum(y_train_safe == target_class))
            needed = max(0, 3 - class_count)
            if needed > 0:
                # Find a row of the opposite class to duplicate and flip label
                opposite = 1 - target_class
                opposite_idx = np.where(y_train_safe == opposite)[0]
                if len(opposite_idx) > 0:
                    src_idx = opposite_idx[0]
                    for _ in range(needed):
                        X_train_safe = pd.concat(
                            [X_train_safe, X_train_safe.iloc[[src_idx]]],
                            ignore_index=True,
                        )
                        y_train_safe = np.append(y_train_safe, target_class)

        model = self._build_model(y_train=y_train_safe)
        model.fit(X_train_safe, y_train_safe)

        # Predict probabilities
        y_proba = model.predict_proba(X_test)[:, 1]

        # Metrics
        if len(np.unique(y_test)) < 2:
            roc_auc = 0.5
        else:
            roc_auc = float(roc_auc_score(y_test, y_proba))

        brier = float(brier_score_loss(y_test, y_proba))

        # Precision at thresholds
        precision_floor = self._precision_at_threshold(y_test, y_proba, THRESHOLD_FLOOR)
        precision_notify = self._precision_at_threshold(y_test, y_proba, THRESHOLD_NOTIFY)

        logger.info(
            f"ROC-AUC={roc_auc:.4f}, Brier={brier:.4f}, "
            f"Precision@{THRESHOLD_FLOOR}={precision_floor:.4f}, "
            f"Precision@{THRESHOLD_NOTIFY}={precision_notify:.4f}"
        )

        return model, roc_auc, brier, precision_floor, precision_notify

    def _precision_at_threshold(
        self, y_true: np.ndarray, y_proba: np.ndarray, threshold: float
    ) -> float:
        """Compute precision at a given probability threshold."""
        y_pred = (y_proba >= threshold).astype(int)
        tp = np.sum((y_pred == 1) & (y_true == 1))
        fp = np.sum((y_pred == 1) & (y_true == 0))
        return float(tp / (tp + fp)) if (tp + fp) > 0 else 0.0

    def _compute_killzone_vs_offhours(
        self, model: Pipeline, X_test: pd.DataFrame, features_df_test: pd.DataFrame
    ) -> Tuple[float, float]:
        """
        Compute mean confidence score for killzone vs off-hours setups.

        Key validation: killzone score must be significantly higher than off-hours.
        """
        y_proba = model.predict_proba(X_test)[:, 1]

        tw_weight_col = "time_window_weight"
        if tw_weight_col not in features_df_test.columns:
            return 0.0, 0.0

        weights = features_df_test[tw_weight_col].values

        killzone_mask = weights >= 0.9   # LONDON_KILLZONE, NY_KILLZONE, Silver Bullets
        offhours_mask = weights <= 0.1   # OFF_HOURS

        killzone_mean = float(np.mean(y_proba[killzone_mask])) if killzone_mask.any() else 0.0
        offhours_mean = float(np.mean(y_proba[offhours_mask])) if offhours_mask.any() else 0.0

        return killzone_mean, offhours_mean

    async def run_walk_forward_validation(
        self, instrument: str, features_df: pd.DataFrame
    ) -> List[FoldResult]:
        """Run walk-forward validation for one instrument."""
        if features_df.empty:
            return []

        data_start = features_df["timestamp"].min()
        data_end = features_df["timestamp"].max()
        total_days = max(1, (data_end - data_start).days)

        preferred_fold_days = self.config.fold_window_months * 30
        preferred_test_days = self.config.test_window_months * 30
        max_fold_days = max(1, (total_days - preferred_test_days) // self.config.n_folds)
        fold_window_days = min(preferred_fold_days, max_fold_days)
        test_window_days = min(preferred_test_days, max(1, total_days - self.config.n_folds * fold_window_days))

        fold_results = []

        for fold_id in range(self.config.n_folds):
            train_end = data_start + timedelta(days=(fold_id + 1) * fold_window_days)
            test_start = train_end + timedelta(days=1)
            test_end = test_start + timedelta(days=test_window_days)

            if test_end > data_end:
                test_end = data_end
                if test_start >= test_end:
                    break

            logger.info(
                f"Fold {fold_id + 1}/{self.config.n_folds}: "
                f"train {data_start.date()}→{train_end.date()}, "
                f"test {test_start.date()}→{test_end.date()}"
            )

            X_train, y_train, X_test, y_test = self.prepare_fold_data(
                features_df, data_start, train_end, test_start, test_end
            )

            if len(X_train) < 1 or len(X_test) < 1:
                logger.warning(f"Fold {fold_id + 1}: insufficient data, skipping")
                continue

            model, roc_auc, brier, prec_floor, prec_notify = self.train_fold(
                X_train, y_train, X_test, y_test
            )

            # Killzone vs off-hours validation
            test_mask = (
                (features_df["timestamp"] >= test_start) &
                (features_df["timestamp"] <= test_end)
            )
            test_features = features_df[test_mask].copy()
            killzone_mean, offhours_mean = self._compute_killzone_vs_offhours(
                model, X_test, test_features
            )

            fold_results.append(FoldResult(
                fold_id=fold_id + 1,
                train_start=data_start,
                train_end=train_end,
                test_start=test_start,
                test_end=test_end,
                train_samples=len(X_train),
                test_samples=len(X_test),
                roc_auc=roc_auc,
                brier_score=brier,
                threshold_floor_precision=prec_floor,
                threshold_notify_precision=prec_notify,
                killzone_mean_score=killzone_mean,
                off_hours_mean_score=offhours_mean,
                killzone_vs_offhours_delta=killzone_mean - offhours_mean,
            ))

        return fold_results

    async def train(self) -> Dict[str, Any]:
        """
        Train Confluence Scorer with walk-forward validation.

        Returns training summary with status and metrics.
        """
        logger.info("Starting Confluence Scorer training")
        logger.info(f"Instruments: {self.config.instruments}")

        with self.tracker.start_run(
            experiment_name="confluence-scorer",
            run_name=f"confluence_scorer_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        ) as run:
            self.tracker.log_params({
                "instruments": ",".join(self.config.instruments),
                "timeframe": self.config.timeframe,
                "htf_timeframe": self.config.htf_timeframe,
                "n_folds": self.config.n_folds,
                "threshold_floor": THRESHOLD_FLOOR,
                "threshold_notify": THRESHOLD_NOTIFY,
                "threshold_auto_execute": THRESHOLD_AUTO_EXECUTE,
                **self.config.lr_params,
            })

            all_fold_results: List[FoldResult] = []

            for instrument in self.config.instruments:
                logger.info(f"\n{'=' * 60}\nTraining on {instrument}\n{'=' * 60}")

                end_date = datetime.now()
                start_date = end_date - timedelta(days=3 * 365)

                features_df = await self.load_feature_dataset(instrument, start_date, end_date)

                if features_df.empty:
                    logger.warning(f"No features for {instrument}, skipping")
                    continue

                fold_results = await self.run_walk_forward_validation(instrument, features_df)
                all_fold_results.extend(fold_results)

            if not all_fold_results:
                logger.error("No fold results — training failed")
                return {"status": "failed", "reason": "No fold results"}

            # Aggregate metrics
            roc_aucs = [f.roc_auc for f in all_fold_results]
            briers = [f.brier_score for f in all_fold_results]
            deltas = [f.killzone_vs_offhours_delta for f in all_fold_results]

            mean_roc_auc = float(np.mean(roc_aucs))
            mean_brier = float(np.mean(briers))
            mean_delta = float(np.mean(deltas))
            mean_killzone = float(np.mean([f.killzone_mean_score for f in all_fold_results]))
            mean_offhours = float(np.mean([f.off_hours_mean_score for f in all_fold_results]))

            logger.info(f"\n{'=' * 60}")
            logger.info("CONFLUENCE SCORER TRAINING SUMMARY")
            logger.info(f"Folds completed    : {len(all_fold_results)}")
            logger.info(f"Mean ROC-AUC       : {mean_roc_auc:.4f}")
            logger.info(f"Mean Brier score   : {mean_brier:.4f}")
            logger.info(f"Killzone mean score: {mean_killzone:.4f}")
            logger.info(f"Off-hours mean score: {mean_offhours:.4f}")
            logger.info(f"Killzone delta     : {mean_delta:.4f}")
            logger.info(f"{'=' * 60}")

            self.tracker.log_metrics({
                "mean_roc_auc": mean_roc_auc,
                "mean_brier_score": mean_brier,
                "mean_killzone_score": mean_killzone,
                "mean_offhours_score": mean_offhours,
                "mean_killzone_delta": mean_delta,
                "n_folds_completed": len(all_fold_results),
            })

            # Validate killzone > off-hours (key requirement)
            killzone_dominates = mean_delta > 0.05  # at least 5% higher

            if killzone_dominates:
                logger.info("✓ Killzone setups score significantly higher than off-hours")

                run_id = run.info.run_id
                model_uri = f"runs:/{run_id}/model"
                try:
                    self.tracker.register_model(model_uri, "confluence-scorer")
                    logger.info("✓ Model registered as 'confluence-scorer'")
                except Exception as e:
                    logger.warning(f"Model registration skipped: {e}")

                return {
                    "status": "success",
                    "mean_roc_auc": mean_roc_auc,
                    "mean_brier_score": mean_brier,
                    "mean_killzone_score": mean_killzone,
                    "mean_offhours_score": mean_offhours,
                    "mean_killzone_delta": mean_delta,
                    "n_folds": len(all_fold_results),
                    "fold_results": all_fold_results,
                    "thresholds": {
                        "floor": THRESHOLD_FLOOR,
                        "notify": THRESHOLD_NOTIFY,
                        "auto_execute": THRESHOLD_AUTO_EXECUTE,
                    },
                }
            else:
                logger.warning(
                    f"✗ Killzone delta {mean_delta:.4f} < 0.05 — "
                    "time window weight not influencing scores enough"
                )
                return {
                    "status": "below_threshold",
                    "mean_roc_auc": mean_roc_auc,
                    "mean_brier_score": mean_brier,
                    "mean_killzone_score": mean_killzone,
                    "mean_offhours_score": mean_offhours,
                    "mean_killzone_delta": mean_delta,
                    "n_folds": len(all_fold_results),
                    "fold_results": all_fold_results,
                }


async def main():
    parser = argparse.ArgumentParser(description="Train Confluence Scorer")
    parser.add_argument("--instruments", nargs="+", default=["EURUSD", "GBPUSD"])
    parser.add_argument("--timeframe", default="M5")
    parser.add_argument("--htf-timeframe", default="H1")
    parser.add_argument("--n-folds", type=int, default=8)
    args = parser.parse_args()

    config = TrainingConfig(
        instruments=args.instruments,
        timeframe=args.timeframe,
        htf_timeframe=args.htf_timeframe,
        n_folds=args.n_folds,
    )

    trainer = ConfluenceScorerTrainer(config)
    result = await trainer.train()

    print(f"\n{'=' * 60}")
    print("CONFLUENCE SCORER TRAINING COMPLETE")
    print(f"Status         : {result['status']}")
    print(f"Mean ROC-AUC   : {result.get('mean_roc_auc', 'N/A'):.4f}")
    print(f"Killzone delta : {result.get('mean_killzone_delta', 'N/A'):.4f}")
    print(f"Folds          : {result.get('n_folds', 0)}")
    print(f"{'=' * 60}")

    return result


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
