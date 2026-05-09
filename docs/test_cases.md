# Test Cases Documentation

> Living document — updated as new modules are implemented.
> All tests use pytest. Property-based tests use Hypothesis.

---

## 1. Unit Tests

### 1.1 Market Analysis Tests
```python
# Test cases for candle pattern recognition
def test_candle_pattern_recognition():
    # Test bullish patterns (Bullish Candle 2 formation, Candle 3 formation, engulfing)
    # Test bearish patterns (Bearish Candle 2 formation, Candle 3 formation, engulfing)
    # Test neutral patterns (Small body range with huge wick on both ends)
    pass

# Test cases for FVG detection
def test_fvg_detection():
    # Test bullish FVG (gap between candle[i-2].high and candle[i].low)
    # Test bullish IFVG (inverse/filled FVG)
    # Test bearish FVG (gap between candle[i-2].low and candle[i].high)
    # Test bearish IFVG (inverse/filled FVG)
    # Test FVG validation (minimum gap size threshold)
    pass

# Test cases for liquidity pool detection
def test_liquidity_pool_detection():
    # Test accumulation zones (Candle 1, Inside bars)
    # Test manipulation zones (Candle 2, Higher TimeFrame wick formation)
    # Test expansion zones (Candle 3)
    pass
```

### 1.2 HTF Candle Projection Tests
```python
# HTF Candle Projections is the SOLE technical indicator in this system.


# Test cases for HTF auto-timeframe selection
def test_htf_auto_timeframe_selection():
    # Test M1  → M5
    # Test M5  → M15
    # Test M15 → H1
    # Test H1  → H4
    # Test H4  → D1
    # Test D1  → W1
    # Property: HTF is always strictly higher than the input timeframe
    pass

# Test cases for HTF projection level computation
def test_htf_projection_levels():
    # Test HTF Open extraction (bias anchor)
    # Test HTF High extraction (upper range boundary)
    # Test HTF Low extraction (lower range boundary)
    # Test open_bias = BULLISH when current_price > htf_open
    # Test open_bias = BEARISH when current_price < htf_open
    # Test open_bias = NEUTRAL when current_price == htf_open
    # Property: htf_high_proximity_pct + htf_low_proximity_pct = 100 when price within range
    # Property: all proximity percentages are in [0, 100]
    # Property: htf_body_pct + htf_upper_wick_pct + htf_lower_wick_pct = 100
    # Property: htf_close_position is always in [0, 1]
    pass

# Test cases for HTF candle structure
def test_htf_candle_structure():
    # Test HTF body size calculation
    # Test HTF upper wick percentage
    # Test HTF lower wick percentage
    # Test HTF close position within range
    pass
```

### 1.3 Time Window & Narrative Framework Tests
```python
# Time is the determinant factor — same price structure has different probability
# depending on which time window it forms in. All windows defined in NY time (DST-aware).

# Test cases for time window classification
def test_time_window_classification():
    # Test ASIAN_RANGE     — 20:00–00:00 NY → ACCUMULATION phase
    # Test TRUE_DAY_OPEN   — 00:00–01:00 NY → TRANSITION phase (NY midnight reference price)
    # Test LONDON_KILLZONE — 03:00–04:00 NY → MANIPULATION phase (Asian range sweep)
    # Test NEWS_WINDOW     — ±30 min around 08:30 NY → TRANSITION phase (volatility injection)
    # Test NY_KILLZONE     — 07:00–10:00 NY → EXPANSION phase (highest probability)
    # Test NY_EQUITY_OPEN  — 09:30–10:30 NY → EXPANSION phase (indices only: US500, US30)
    # Test DAILY_CLOSE     — 17:00–18:00 NY → DISTRIBUTION phase
    # Test OFF_HOURS       — all other times → OFF phase
    # Property: time_window_weight is always in [0.0, 1.0]
    # Property: is_killzone is True iff time_window in {LONDON_KILLZONE, NY_KILLZONE}
    # Property: is_high_probability_window is True iff time_window_weight >= 0.7
    pass

# Test cases for key reference price tracking
def test_reference_price_tracking():
    # Test daily_open_price set at 18:00 NY (22:00 UTC)
    # Test weekly_open_price set at Sunday 18:00 NY
    # Test true_day_open_price set at 00:00 NY (04:00 UTC)
    # Test price_vs_daily_open = BULLISH when current_price > daily_open
    # Test price_vs_daily_open = BEARISH when current_price < daily_open
    # Test price_vs_true_day_open bias for intraday direction
    pass

# Test cases for narrative phase derivation
def test_narrative_phase():
    # Test ASIAN_RANGE → ACCUMULATION (liquidity being engineered)
    # Test LONDON_KILLZONE → MANIPULATION (Asian range swept, displacement)
    # Test NY_KILLZONE → EXPANSION (delivery of the actual move)
    # Test DAILY_CLOSE → DISTRIBUTION (position squaring)
    # Test TRUE_DAY_OPEN, NEWS_WINDOW → TRANSITION
    pass

# Test cases for time window probability weighting
def test_time_window_weights():
    # Test LONDON_KILLZONE weight = 1.0
    # Test NY_KILLZONE weight = 1.0
    # Test NY_EQUITY_OPEN weight = 0.9
    # Test NEWS_WINDOW weight = 0.8
    # Test TRUE_DAY_OPEN weight = 0.7
    # Test ASIAN_RANGE weight = 0.3
    # Test OFF_HOURS weight = 0.1
    pass

# Test cases for 3-question narrative generation
def test_narrative_generation():
    # Test "Where has price come from?" — HTF context, previous session range
    # Test "Where is it now?" — time window phase, price vs reference opens
    # Test "Where is it likely to go?" — nearest liquidity or imbalance
    # Test bullish entry bias: price below session open (manipulation wick down first)
    # Test bearish entry bias: price above session open (manipulation wick up first)
    # Test DST transitions (NY switches between UTC-4 and UTC-5)
    pass
```

### 1.4 PDArray Tests
```python
# Test cases for premium zone detection (bearish PD arrays)
def test_premium_zone_detection():
    # Test Bearish Order Blocks
    # Test Bearish Breaker Blocks
    # Test Bearish Rejection Blocks
    # Test Bearish FVGs
    # Test Bearish IFVGs
    # Test OTE (Fibonacci Golden Ratio — 62%–79% retracement)
    # Test array identification
    # Test array strength scoring
    # Test array validation (still valid vs mitigated)
    pass

# Test cases for discount zone detection (bullish PD arrays)
def test_discount_zone_detection():
    # Test Bullish Order Blocks
    # Test Bullish Breaker Blocks
    # Test Bullish Rejection Blocks
    # Test Bullish FVGs
    # Test Bullish IFVGs
    # Test OTE (Fibonacci Golden Ratio — 62%–79% retracement)
    # Test zone identification
    # Test zone strength scoring
    # Test zone validation (still valid vs mitigated)
    pass
```

### 1.4 Candle Structure Feature Tests
```python
# Property-based tests for candle feature extractor
def test_candle_feature_properties():
    # Property: body_pct + upper_wick_pct + lower_wick_pct = 100 for all valid candles
    # Property: close_position is always in [0, 1]
    # Property: high >= open, high >= close, high >= low for all candles
    # Property: low <= open, low <= close, low <= high for all candles
    pass
```

### 1.5 ML Model Tests
```python
# Test cases for Regime Classifier
def test_regime_classifier():
    # Test classification into: TRENDING_BULLISH, TRENDING_BEARISH, RANGING, BREAKOUT, NEWS_DRIVEN
    # Test walk-forward validation (minimum 8 folds)
    # Test accuracy >= 75% on unseen data
    pass

# Test cases for Pattern Detector
def test_pattern_detector():
    # Test BOS_CONFIRMED detection
    # Test CHOCH_DETECTED detection
    # Test BEARISH_ARRAY_REJECTION detection
    # Test BULLISH_ARRAY_BOUNCE detection
    # Test FVG_PRESENT detection
    # Test LIQUIDITY_SWEEP detection
    # Test ORDER_BLOCK detection
    # Test INDUCEMENT detection
    # Test accuracy >= 80% on held-out test set
    # Test false positive rate < 20% at confidence threshold 0.75
    pass

# Test cases for Confluence Scorer
def test_confluence_scorer():
    # Test HTF projection levels as primary confluence signals
    #Stacked PD Arrays
    # Test threshold calibration: 0.65 (floor), 0.75 (notify), 0.85 (execute)
    # Test score is always in [0.0, 1.0]
    pass
```

### 1.6 Risk Engine Tests
```python
# Test cases for position sizing
def test_position_sizing():
    # Property: position_size * sl_distance always equals exactly 0.5-1% of equity
    # Test dynamic sizing by SL distance
    pass

# Test cases for drawdown limits
def test_drawdown_limits():
    # Property: /validate always returns approved=False when daily_dd >= 3%
    # Property: /validate always returns approved=False when weekly_dd >= 6%
    # Test news blackout window blocking
    # Test max concurrent trades limit (3)
    # Test confidence floor gate (0.65)
    pass
```

---

## 2. Integration Tests

### 2.1 Data Flow Tests
- Test market data ingestion (tick → candle → TimescaleDB)
- Test real-time data processing latency < 2s from candle close
- Test multi-timeframe synchronization (M1 through D1)
- Test HTF projection levels stored correctly in indicators table
- Test Kafka producer publishing to market.candles and market.ticks

### 2.2 Trading System Tests
- Test order creation via broker API
- Test position management (partial exit at 1R, SL to breakeven)
- Test risk management rules enforced end-to-end
- Test kill switch halts agent immediately

### 2.3 API Integration Tests
- Test Deriv WebSocket API connection and reconnection
- Test OANDA WebSocket connector
- Test WebSocket functionality (candle streaming)
- Test data persistence to TimescaleDB and MongoDB

### 2.4 Agent Pipeline Tests
- Test full pipeline: candle → feature engineering → ML inference → setup detection
- Test observe_node → analyse_node → decide_node routing
- Test Risk Engine called synchronously before every trade decision
- Test alert delivery latency < 3 seconds from setup detection

---

## 3. Performance Tests

### 3.1 Speed Tests
- Process 1000 candles under 1 second
- Generate ML predictions within 500ms from candle close
- Execute trades within 500ms from decision
- HTF projection computation within 50ms per candle

### 3.2 Load Tests
- Handle 100 simultaneous WebSocket connections
- Process multiple timeframes concurrently (M1 through D1)
- Manage multiple trading positions (up to 3 concurrent)

### 3.3 Memory Tests
- Monitor memory usage under load
- Test memory cleanup after candle processing
- Verify no memory leaks in Kafka consumer loop

---

## 4. Validation Tests

### 4.1 Model Validation
- Pattern detection accuracy ≥ 80% on held-out test set
- False positive rate < 20% at confidence threshold 0.75
- Walk-forward validation: minimum 8 folds, 3-month expanding window
- Out-of-sample performance on 2-year period

### 4.2 Strategy Validation
- Backtest Sharpe Ratio ≥ 1.5 on 2-year out-of-sample period
- Maximum backtest drawdown ≤ 10%
- Average R-multiple per trade ≥ 1.5R
- Win rate ≥ trader's historical baseline (±5%)

---

## 5. Security Tests

### 5.1 API Security
- Test JWT authentication on all external endpoints
- Test RBAC enforcement (Admin, Trader, Viewer roles)
- Test rate limiting
- Test broker API key encryption at rest

### 5.2 Data Security
- Test data validation and input sanitization
- Test mTLS between internal services
- Test access controls per user role
- Test full audit log of all agent decisions

---

## 6. User Interface Tests

### 6.1 Dashboard Tests
- Test live setups feed real-time updates (WebSocket)
- Test setup detail panel (HTF O/H/L levels, confidence score, reasoning)
- Test agent decision log viewer
- Test chart rendering

### 6.2 Configuration Tests
- Test user risk config (thresholds, instruments, agent mode)
- Test agent pause/resume controls
- Test parameter validation

---

## 7. Error Handling Tests

### 7.1 System Errors
- Test network failures and reconnection (exponential backoff)
- Test database errors (TimescaleDB, MongoDB)
- Test API timeouts (broker API, LLM API)
- Test Kafka consumer failure recovery

### 7.2 Trading Errors
- Test invalid orders rejected by Risk Engine
- Test confidence below floor (< 0.65) discarded
- Test position limits enforced (max 3 concurrent)
- Test news blackout window blocking new trades

---

## 8. Recovery Tests

### 8.1 System Recovery
- Test automatic WebSocket reconnection (Deriv, OANDA)
- Test agent state recovery after restart
- Test data consistency after reconnection

### 8.2 Backup Recovery
- Test backup procedures for TimescaleDB and MongoDB
- Test data restoration
- Test system restart with state recovery from Redis
