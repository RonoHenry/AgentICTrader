# Prompt Templates for AgentICTrader

## 1. Market Analysis Prompts

### 1.1 Candle Formation Analysis
```
Analyze the following candle pattern:
Timeframe: {timeframe}
OHLC Data: {ohlc_data}
Previous Patterns: {previous_patterns}
Market Context: {market_context}

Identify:
1. Pattern type
2. Formation probability
3. Potential direction
4. Key levels
```

### 1.2 Market Phase Detection
```
Evaluate market phase based on:
Price Action: {price_action}
Volume: {volume}
Time: {time_context}
Support/Resistance: {key_levels}

Determine:
1. Current phase (Accumulation/Manipulation/Expansion)
2. Phase strength
3. Phase duration probability
4. Next phase prediction
```

## 2. PDArray Analysis

### 2.1 Premium Zone Detection
```
Analyze for premium zones:
Price Range: {price_range}
Timeframe: {timeframe}
Market Structure: {market_structure}
Recent Movements: {recent_moves}

Identify:
1. Zone boundaries
2. Zone strength
3. Entry points
4. Risk levels
```

### 2.2 Discount Zone Detection
```
Analyze for discount zones:
Price Range: {price_range}
Timeframe: {timeframe}
Market Structure: {market_structure}
Recent Movements: {recent_moves}

Identify:
1. Zone boundaries
2. Zone strength
3. Entry points
4. Risk levels
```

## 3. Trade Generation

### 3.1 Entry Signal
```
Generate entry signal based on:
Current Price: {current_price}
Market Phase: {market_phase}
PDArray Zones: {pd_zones}
Risk Parameters: {risk_params}

Determine:
1. Entry type (Buy/Sell)
2. Entry price
3. Position size
4. Stop loss
5. Take profit
```

### 3.2 Exit Signal
```
Generate exit signal based on:
Current Position: {position_details}
Market Conditions: {market_conditions}
Price Action: {price_action}
Risk Status: {risk_status}

Determine:
1. Exit type (Full/Partial)
2. Exit price
3. Exit timing
4. Position adjustment
```

## 4. Risk Management

### 4.1 Position Sizing
```
Calculate position size based on:
Account Balance: {balance}
Risk Percentage: {risk_percent}
Stop Loss Distance: {sl_distance}
Market Volatility: {volatility}

Output:
1. Position size
2. Risk amount
3. Reward potential
4. Risk/Reward ratio
```

### 4.2 Risk Assessment
```
Assess trade risk based on:
Market Conditions: {market_conditions}
Position Details: {position_details}
Current Exposure: {exposure}
Market Phase: {market_phase}

Evaluate:
1. Risk level
2. Adjustment needed
3. Hedge requirements
4. Position viability
```

## 5. Performance Analysis

### 5.1 Trade Review
```
Review trade performance:
Entry/Exit Points: {trade_points}
Market Behavior: {market_behavior}
Expected vs Actual: {performance_comparison}
Market Context: {market_context}

Analyze:
1. Decision accuracy
2. Execution quality
3. Risk management
4. Improvements needed
```

### 5.2 Strategy Optimization
```
Optimize strategy based on:
Historical Performance: {performance_data}
Market Conditions: {market_conditions}
Risk Parameters: {risk_params}
Success Rate: {success_rate}

Recommend:
1. Parameter adjustments
2. Risk modifications
3. Entry/exit improvements
4. Timing optimization
```

## 6. System Monitoring

### 6.1 Performance Monitoring
```
Monitor system performance:
Response Times: {response_times}
Error Rates: {error_rates}
Resource Usage: {resource_usage}
Trade Success: {trade_success}

Evaluate:
1. System health
2. Performance issues
3. Resource needs
4. Optimization requirements
```

### 6.2 Alert Generation
```
Generate system alert:
Alert Type: {alert_type}
Severity: {severity}
Impact: {impact}
Context: {context}

Provide:
1. Alert description
2. Required action
3. Priority level
4. Resolution steps
```
