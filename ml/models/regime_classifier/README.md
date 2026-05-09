# Regime Classifier Training

This directory contains the training script for the Regime Classifier model.

## Overview

The Regime Classifier is an XGBoost multi-class classifier that classifies market regime into 5 classes:

1. **TRENDING_BULLISH** - Strong upward trend with BOS confirmation
2. **TRENDING_BEARISH** - Strong downward trend with BOS confirmation
3. **RANGING** - Sideways price action, no clear trend
4. **BREAKOUT** - FVG present with BOS, potential breakout scenario
5. **NEWS_DRIVEN** - High volatility during news windows

## Features Used

The classifier uses features from the complete feature pipeline:

### HTF Projection Features
- `htf_open`, `htf_high`, `htf_low` - HTF candle OHLC levels
- `htf_open_bias` - Directional bias (BULLISH/BEARISH/NEUTRAL)
- `htf_high_proximity_pct`, `htf_low_proximity_pct` - Distance to HTF boundaries
- `htf_body_pct`, `htf_upper_wick_pct`, `htf_lower_wick_pct` - HTF candle structure
- `htf_close_position` - HTF close position within range

### Candle Structure Features
- `body_pct`, `upper_wick_pct`, `lower_wick_pct` - Candle body and wick percentages
- `close_position` - Close position within range
- `is_bullish` - Bullish/bearish candle flag

### Zone Features
- `bos_detected` - Break of Structure detection
- `choch_detected` - Change of Character detection
- `fvg_present` - Fair Value Gap presence
- `liquidity_sweep` - Liquidity sweep detection
- `swing_high_distance`, `swing_low_distance` - Distance to swing points
- `htf_trend_bias` - HTF trend bias from HTF candle direction

### Session Features
- `time_window` - ICT killzone classification
- `narrative_phase` - Narrative phase (ACCUMULATION, MANIPULATION, EXPANSION, etc.)
- `time_window_weight` - Probability weight for time window
- `is_killzone`, `is_high_probability_window` - Killzone flags
- `price_vs_daily_open`, `price_vs_weekly_open`, `price_vs_true_day_open` - Price position vs reference opens

## Training Methodology

### Walk-Forward Validation
- **Minimum 8 folds** with 3-month expanding window
- Each fold trains on expanding historical data and tests on the next 1-month period
- Ensures no look-ahead bias and realistic out-of-sample performance

### Regime Labelling
Since we don't have pre-labelled regime data, the script uses heuristic rules to label historical candles:

1. **NEWS_DRIVEN**: During news windows with high volatility (HTF body > 60%)
2. **BREAKOUT**: FVG present + BOS detected + strong HTF body (> 50%)
3. **TRENDING_BULLISH**: Bullish HTF bias + BOS + no CHoCH
4. **TRENDING_BEARISH**: Bearish HTF bias + BOS + no CHoCH
5. **RANGING**: Neutral bias, CHoCH detected, small HTF body, or mid-range price

### XGBoost Configuration
Default hyperparameters:
```python
{
    "objective": "multi:softmax",
    "num_class": 5,
    "max_depth": 6,
    "learning_rate": 0.1,
    "n_estimators": 100,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "random_state": 42,
    "eval_metric": "mlogloss",
}
```

### Exit Criterion
- **≥ 75% accuracy** on unseen data across all folds
- If criterion is met, the best model is saved to MLflow model registry as "regime-classifier"

## Usage

### Prerequisites
1. TimescaleDB running with historical candle data loaded
2. MLflow tracking server running (default: http://localhost:5000)
3. Environment variables configured in `.env`

### Basic Usage
```bash
# Train on default instruments (EURUSD, GBPUSD) with M5 timeframe
python -m ml.models.regime_classifier.train

# Train on specific instruments
python -m ml.models.regime_classifier.train --instruments EURUSD GBPUSD US500 XAUUSD

# Train with custom timeframe and HTF
python -m ml.models.regime_classifier.train --timeframe M15 --htf-timeframe H4

# Train with more folds
python -m ml.models.regime_classifier.train --n-folds 12
```

### Command-Line Arguments
- `--instruments`: Trading instruments to train on (default: EURUSD GBPUSD)
- `--timeframe`: Timeframe for training data (default: M5)
- `--htf-timeframe`: Higher timeframe for HTF projections (default: H1)
- `--n-folds`: Number of walk-forward folds (default: 8)
- `--fold-window-months`: Training window size in months (default: 3)
- `--test-window-months`: Test window size in months (default: 1)

## MLflow Tracking

All experiments are logged to MLflow under the `regime-classifier` experiment:

### Logged Parameters
- `instruments`: Comma-separated list of instruments
- `timeframe`, `htf_timeframe`: Timeframes used
- `n_folds`, `fold_window_months`, `test_window_months`: Validation configuration
- All XGBoost hyperparameters

### Logged Metrics
- `mean_accuracy`: Mean accuracy across all folds
- `std_accuracy`: Standard deviation of accuracy
- `min_accuracy`, `max_accuracy`: Min/max accuracy across folds
- `n_folds_completed`: Number of folds successfully completed

### Model Artifacts
- Best model saved to MLflow model registry as "regime-classifier"
- Model can be loaded for inference using MLflow's model loading API

## Output

The training script produces:

1. **Console logs**: Real-time training progress and fold results
2. **MLflow experiment**: All parameters, metrics, and artifacts logged
3. **Training summary**: Final report with aggregate metrics
4. **Model registration**: Best model registered to MLflow model registry (if exit criterion met)

### Example Output
```
================================================================================
TRAINING SUMMARY
================================================================================
Total folds: 8
Mean accuracy: 0.7823 ± 0.0345
Min accuracy: 0.7234
Max accuracy: 0.8156
================================================================================

✓ Exit criterion met: mean accuracy ≥ 75%
✓ Model training completed successfully
```

## Next Steps

After training:

1. **Review MLflow UI**: Check experiment results at http://localhost:5000
2. **Analyze fold results**: Review classification reports and confusion matrices
3. **Tune hyperparameters**: If accuracy < 75%, adjust XGBoost parameters
4. **Improve labelling**: Refine heuristic rules in `RegimeLabeller` class
5. **Deploy model**: Load model from MLflow registry for inference

## Troubleshooting

### No data loaded
- Ensure TimescaleDB is running and contains historical data
- Check database connection parameters in `.env`
- Verify instruments and timeframes exist in the database

### Low accuracy
- Increase training data (more instruments, longer history)
- Tune XGBoost hyperparameters
- Improve regime labelling heuristics
- Add more features to the pipeline

### Insufficient samples
- Reduce `min_candles_per_fold` in `TrainingConfig`
- Increase `fold_window_months` for larger training windows
- Load more historical data into TimescaleDB

## Implementation Notes

**Implements: Task 20 - Train and validate Regime Classifier**

This training script fulfills all requirements:
- ✓ Creates `ml/models/regime_classifier/train.py`
- ✓ Uses HTF projection + candle + zone + session features
- ✓ Trains XGBoost multi-class classifier for 5 regime classes
- ✓ Implements walk-forward validation with minimum 8 folds, 3-month expanding window
- ✓ Logs all experiments to MLflow
- ✓ Validates exit criterion: ≥ 75% accuracy on unseen data
- ✓ Saves best model to MLflow model registry as "regime-classifier"
