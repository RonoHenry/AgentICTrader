# ML Pipeline & Model Architecture
**Project:** AgentICTrader.AI
**Version:** 1.0.0
**Last Updated:** 2026-04-04

---

## 1. ML Philosophy

The ML system's sole job is to encode the trader's Price Action edge into a reproducible, probabilistic scoring system. Every model decision must be:

1. **Explainable** — feature importance available for every prediction
2. **Conservative** — in doubt, output a low score. False positives are more costly than missed setups
3. **Validated** — walk-forward validation on unseen data only. No look-ahead bias, ever
4. **Updatable** — models retrain incrementally as new trade outcomes arrive

---

## 2. Feature Engineering

Features are the numerical encoding of everything a discretionary trader reads on a chart.

### 2.1 Candle Structure Features

| Feature | Description |
|---|---|
| `body_size` | Close - Open (absolute) |
| `body_pct` | Body as % of total range |
| `upper_wick_pct` | Upper wick as % of range |
| `lower_wick_pct` | Lower wick as % of range |
| `candle_type` | BULLISH / BEARISH / DOJI / ENGULFING |
| `close_position` | Close position within range (0=low, 1=high) |
| `prev_candle_relation` | Engulf / Inside / Outside / Normal |
| `consecutive_direction` | Number of consecutive same-direction candles |

### 2.2 Zone & Structure Features

| Feature | Description |
|---|---|
| `nearest_bearish_array_dist` | Distance to nearest Bearish PD Array at Premium (Bearish OB / FVG / Breaker / IFVG) |
| `nearest_bullish_array_dist` | Distance to nearest Bullish PD Array at Discount (Bullish OB / FVG / Breaker / IFVG) |
| `in_bearish_array` | Boolean: price inside a Bearish PD Array at Premium |
| `in_bullish_array` | Boolean: price inside a Bullish PD Array at Discount |
| `zone_strength_score` | 0–1: how many times array was respected |
| `bos_confirmed` | Boolean: Break of Structure confirmed |
| `choch_detected` | Boolean: Change of Character detected |
| `fvg_present` | Boolean: Fair Value Gap in recent candles |
| `liquidity_sweep` | Boolean: sweep of recent high/low |
| `swing_high_dist` | Distance to last significant swing high |
| `swing_low_dist` | Distance to last significant swing low |

### 2.3 Momentum & Indicator Features

| Feature | Description |
|---|---|
| `atr_14` | Average True Range, 14-period |
| `atr_pct_of_price` | ATR as % of current price |
| `rsi_14` | RSI, 14-period |
| `adx_14` | ADX trend strength |
| `ema_50_distance` | % distance from 50 EMA |
| `ema_200_distance` | % distance from 200 EMA |
| `price_vs_ema_50` | Above / Below 50 EMA |
| `price_vs_ema_200` | Above / Below 200 EMA |
| `volume_ratio` | Current volume vs 20-period SMA |
| `volume_delta` | Buy volume minus sell volume |

### 2.4 Multi-Timeframe (HTF Alignment) Features

| Feature | Description |
|---|---|
| `h4_trend` | H4 bias: BULLISH / BEARISH / NEUTRAL (-1, 0, 1) |
| `h1_trend` | H1 bias: BULLISH / BEARISH / NEUTRAL |
| `d1_trend` | Daily bias: BULLISH / BEARISH / NEUTRAL |
| `htf_confluence_score` | How many HTFs agree with trade direction (0–3) |
| `h4_in_array` | H4 is at a key Bullish or Bearish PD Array |
| `d1_premium_discount` | Price in H4 premium (bearish array bias) or discount (bullish array bias) |

### 2.5 Session & Time Features

| Feature | Description |
|---|---|
| `session` | LONDON / NEW_YORK / OVERLAP / TOKYO / OFF_HOURS |
| `day_of_week` | 1–5 (Monday–Friday) |
| `hour_of_day` | 0–23 UTC |
| `minutes_to_session_open` | Proximity to session open (liquidity events) |
| `is_news_window` | Boolean: high-impact news within ±15 minutes |
| `minutes_to_news` | Minutes until next high-impact event |

### 2.6 Sentiment Features

| Feature | Description |
|---|---|
| `sentiment_score` | FinBERT score: -1.0 (bearish) to +1.0 (bullish) |
| `sentiment_label` | BEARISH / NEUTRAL / BULLISH |
| `sentiment_aligned` | Boolean: sentiment agrees with trade direction |
| `sentiment_freshness` | Minutes since last sentiment update |

---

## 3. Model 1 — Regime Classifier

**Purpose:** Classify the current market environment before any setup is evaluated.

**Algorithm:** XGBoost Classifier (multi-class)

**Classes:**
- `TRENDING_BULLISH`
- `TRENDING_BEARISH`
- `RANGING`
- `BREAKOUT`
- `NEWS_DRIVEN` (high volatility, avoid)

**Key Features:**
- ADX, ATR %, RSI, candle body sizes, EMA slope, volume ratio, day-of-week, session

**Training:**
- Label historical D1 + H4 candles manually by regime
- Walk-forward validation with 3-month expanding window
- Target: ≥ 75% accuracy on unseen data

**Output:**
```python
{
    "regime": "TRENDING_BEARISH",
    "confidence": 0.88,
    "feature_importance": {...}
}
```

**Deployment Rule:** If regime = `NEWS_DRIVEN` or confidence < 0.65 → no setups evaluated in this session.

---

## 4. Model 2 — Pattern Detector

**Purpose:** Detect specific Price Action patterns that constitute a valid setup.

**Algorithm:** XGBoost Classifier (multi-label) — a setup can have multiple patterns simultaneously

**Patterns Detected:**

| Pattern | Code | Description |
|---|---|---|
| Break of Structure | `BOS_CONFIRMED` | Clean break and close below/above key level |
| Change of Character | `CHOCH_DETECTED` | First sign of trend reversal |
| Bearish Array Rejection | `BEARISH_ARRAY_REJECTION` | Price rejected from Bearish PD Array (Bearish OB / FVG / Breaker / IFVG) at **Premium** of Dealing Range |
| Bullish Array Bounce | `BULLISH_ARRAY_BOUNCE` | Price bounced from Bullish PD Array (Bullish OB / FVG / Breaker / IFVG) at **Discount** of Dealing Range |
| Fair Value Gap | `FVG_PRESENT` | Imbalance / gap in price action |
| Liquidity Sweep | `LIQUIDITY_SWEEP` | Sweep of buy/sell stops before reversal |
| Inducement | `INDUCEMENT` | False break before real move |
| Order Block | `ORDER_BLOCK` | Last opposing candle before strong move |

> **Note:** There are no "supply zones" or "demand zones" in ICT methodology.
> What traders commonly call "supply" is a Bearish PD Array (Bearish OB, FVG, Breaker, IFVG) at Premium of the Dealing Range.
> What traders commonly call "demand" is a Bullish PD Array (Bullish OB, FVG, Breaker, IFVG) at Discount of the Dealing Range.

**Training Data:**
- Source: Trader's annotated historical charts (minimum 500 labelled examples per pattern)
- Augmentation: Synthetic data generation via time-stretching and minor price perturbation
- Labelling tool: Custom `ml/models/pattern_detector/labeller.py` — displays chart, trader marks patterns

**Output:**
```python
{
    "patterns": {
        "BOS_CONFIRMED": {"detected": True, "confidence": 0.91, "level": 6512.0},
        "BEARISH_ARRAY_REJECTION": {"detected": True, "confidence": 0.87, "zone": [6519.0, 6528.0]},
        "LIQUIDITY_SWEEP": {"detected": False, "confidence": 0.31}
    }
}
```

---

## 5. Model 3 — Confluence Scorer

**Purpose:** Produce a single 0.0–1.0 confidence score by combining all signals.

**Algorithm:** Weighted ensemble with learned weights (Logistic Regression over model outputs)

**Input Features (from Models 1 & 2 + feature engineering):**
- Regime confidence
- Number of patterns detected and their individual confidences
- HTF alignment score (0–3)
- Sentiment score + alignment
- Session quality (London/NY overlap = highest)
- Calendar clear (no news within 15 min)
- Zone strength score
- Volume confirmation

**Weight Logic (initial, learned from outcomes):**
```
Confidence = W1 * regime_score
           + W2 * pattern_count_score
           + W3 * htf_alignment_score
           + W4 * sentiment_alignment
           + W5 * session_quality
           + W6 * zone_strength
           + W7 * volume_confirmation
           + W8 * calendar_clear_bonus
           - P1 * news_window_penalty
```

**Thresholds:**
| Score | Action |
|---|---|
| ≥ 0.85 | HIGH CONFIDENCE — notify + auto-execute (if autonomous mode) |
| 0.75–0.84 | MEDIUM-HIGH — notify trader |
| 0.65–0.74 | MEDIUM — log only, watchlist |
| < 0.65 | DISCARD — not published |

---

## 6. Training Pipeline

```
┌─────────────────────────────────────────────────────────────┐
│                    TRAINING PIPELINE                         │
│                                                              │
│  1. DATA PREPARATION                                         │
│     ├── Load raw OHLCV from TimescaleDB                      │
│     ├── Load labelled trade journal from MongoDB             │
│     ├── Run feature engineering pipeline                     │
│     └── Split: train / validation / test (time-based)        │
│                                                              │
│  2. WALK-FORWARD VALIDATION                                  │
│     ├── Initial train window: 12 months                      │
│     ├── Test window: 3 months                                │
│     ├── Step forward 1 month, retrain, repeat                │
│     └── Report: accuracy, precision, recall per fold         │
│                                                              │
│  3. MODEL TRAINING                                           │
│     ├── Regime Classifier → MLflow run                       │
│     ├── Pattern Detector → MLflow run                        │
│     └── Confluence Scorer → MLflow run                       │
│                                                              │
│  4. EVALUATION GATE                                          │
│     ├── Pattern accuracy ≥ 80%                               │
│     ├── False positive rate < 20% at threshold 0.75          │
│     ├── Backtest Sharpe ≥ 1.5                                 │
│     └── Max backtest DD ≤ 10%                                 │
│                                                              │
│  5. PROMOTION                                                │
│     ├── Pass → Register in MLflow Model Registry             │
│     ├── Tag as 'staging' → Integration tests                 │
│     └── Tag as 'production' → Deploy to inference service    │
└─────────────────────────────────────────────────────────────┘
```

---

## 7. Incremental Retraining

Every closed trade outcome feeds back into the training loop:

```python
# Triggered by agent/learn_node.py after trade closes

def queue_retraining(trade_outcome: TradeOutcome):
    """
    Adds trade outcome to retraining queue.
    Retraining triggered when queue reaches 50 new samples
    OR on scheduled weekly run.
    """
    retraining_queue.append({
        "setup_features": trade_outcome.setup_features,
        "confidence_score": trade_outcome.confidence_score,
        "actual_outcome": trade_outcome.r_multiple,  # Labels: >0 = win, ≤0 = loss
        "timestamp": trade_outcome.close_time
    })

    if len(retraining_queue) >= 50:
        trigger_retraining_pipeline()
```

**Safeguard:** New models only promote to production if they outperform the current production model on the last 3 months of held-out data.

---

## 8. Backtesting Framework

**Engine:** Custom Python engine in `ml/backtesting/engine.py`

**Simulation rules:**
- No look-ahead: model only sees data available at candle close time
- Spread and slippage modelled per instrument
- Max 3 concurrent open trades
- Risk per trade: 1% account equity
- Dynamic position sizing based on SL distance
- Partial exits at 1R (50% position) enabled optionally

**Metrics Reported:**
- Total return %
- Sharpe Ratio
- Sortino Ratio
- Maximum Drawdown %
- Win Rate %
- Average R-multiple (winners + losers)
- Expectancy per trade
- Profit factor
- Trade count by session, instrument, regime

---

## 9. MLflow Experiment Tracking

Every training run tracked with:
- Hyperparameters
- Feature importance
- Validation metrics per fold
- Backtest results
- Model artefact (pickled + versioned)
- Training data hash (for reproducibility)

```bash
# Start MLflow UI
mlflow ui --backend-store-uri postgresql://...
# Access at http://localhost:5000
```

---

*Document Owner: ML Engineer | Review Cycle: Per Model Version*
