# Agent Architecture

## Overview
The agent is a LangGraph state graph that encodes the cognitive process of an expert discretionary trader performing Top Down Analysis. It runs a continuous **Observe → Analyse → Decide → Act → Review → Learn** cycle.

## Agent State
`AgentState` in `agent/state.py` is the single Pydantic model carried through every node. Never pass raw dicts between nodes.

Key state groups:
- **Setup data**: `setup_id`, `instrument`, `timeframe`, `direction`, `detected_at`
- **ML outputs**: `regime`, `regime_confidence`, `patterns`, `raw_confidence`, `htf_alignment`
- **Sentiment**: `sentiment_score`, `sentiment_label`, `sentiment_aligned`, `top_headlines`
- **Calendar**: `calendar_clear`, `minutes_to_next_event`, `next_event_name`
- **Decision**: `final_confidence`, `decision` (EXECUTE/NOTIFY/SKIP/WAIT), `decision_reason`, `mode`
- **Trade plan**: `trade_plan` (entry, stop_loss, take_profit_1/2, r_ratio, recommended_size)
- **Risk**: `risk_validation` (verdict APPROVED/REJECTED, rejection_reason, checks)
- **LLM**: `trade_reasoning`
- **Execution**: `broker_order_id`, `trade_id`
- **Outcome**: `outcome`, `r_multiple`, `close_price`, `close_time`
- **Meta**: `error`, `processing_times`

## Node Responsibilities

### `observe_node` (`agent/nodes/observe_node.py`)
- Entry point — receives setup from Kafka `setups.detected`
- Validates setup is still relevant (price hasn't moved too far from entry)
- Sets `decision = SKIP` if setup expired
- Records `processing_times["observe"]`

### `analyse_node` (`agent/nodes/analyse_node.py`)
- Enriches with sentiment from Redis (`sentiment:{instrument}`)
- Checks economic calendar blackout (±15 min around high-impact events)
- Computes `final_confidence`:
  ```python
  sentiment_bonus = +0.05 if aligned else -0.08
  calendar_bonus  = +0.03 if clear else -0.15
  final_confidence = clamp(raw_confidence + sentiment_bonus + calendar_bonus, 0.0, 1.0)
  ```
- Records `processing_times["analyse"]`

### `decide_node` (`agent/nodes/decide_node.py`)
- Applies confidence threshold gate (hard minimum 0.65, configurable notify threshold 0.75)
- Hard blocks on `calendar_clear == False`
- Calls Risk Engine synchronously — must return APPROVED to proceed
- Generates `trade_reasoning` via LLM if all gates pass
- Routes to NOTIFY (human-in-loop) or EXECUTE (autonomous mode)
- Records `processing_times["decide"]`

### `notify_node` (`agent/nodes/notify_node.py`)
- Formats push notification: instrument, direction, score, patterns, entry/SL/TP, R-ratio, sentiment, calendar
- Dispatches via FCM (`services/notifications/fcm_service.py`)
- Logs decision to MongoDB

### `execute_node` (`agent/nodes/execute_node.py`)
- Only runs in `AgentMode.AUTONOMOUS`
- Re-validates `risk_validation.verdict == APPROVED` before placing order (belt and suspenders)
- Places order via broker API, stores `broker_order_id` and `trade_id`
- Sends execution confirmation notification

### `review_node` (`agent/nodes/review_node.py`)
- Monitors open trade on polling interval
- Manages partial exit at 1R (close 50%, move SL to breakeven)
- Loops back to itself until trade closes
- On close: sets `outcome`, `close_price`, `close_time`, `r_multiple`

### `learn_node` (`agent/nodes/learn_node.py`)
- Updates trade journal in MongoDB with final outcome
- Queues retraining sample: `{setup_features, confidence_score, r_multiple, outcome_label}`
- Retraining triggered when queue reaches 50 new samples or on weekly schedule

## Graph Routing
```python
# agent/edges.py
observe  → analyse  (always)
analyse  → decide   (always)
decide   → end      (if SKIP)
decide   → notify   (if NOTIFY)
decide   → execute  (if EXECUTE)
notify   → end
execute  → end      (if error)
execute  → review   (if success)
review   → review   (if trade still open)
review   → learn    (if trade closed)
learn    → end
```

## Safety Layers (cannot be bypassed)
1. **Confidence threshold gate** in `decide_node` — hard floor 0.65
2. **Risk Engine synchronous gate** in `decide_node` — must return APPROVED
3. **Pre-execution recheck** in `execute_node` — re-validates approval even after decide approved

## Kill Switch
```python
# Any service publishes to Kafka topic: agent.kill_switch
# OR: POST /agent/pause → sets agent_mode = PAUSED in Redis
# Agent halts ALL execution immediately on daily/weekly drawdown breach
```

## Risk Rules (enforced by Risk Engine, never bypassed)
- Max risk per trade: 1–2% account equity (user-configurable)
- Max daily drawdown: 3% hard limit
- Max weekly drawdown: 6% hard limit
- Max concurrent open trades: 3
- News blackout: no new trades within ±15 minutes of high-impact events
- Confidence floor: 0.65 absolute minimum

## Agent Modes
- `HUMAN_IN_LOOP` (default) — alerts only, no autonomous execution
- `AUTONOMOUS` — full execution via broker API, opt-in, feature-flagged per user

## Services the Agent Calls
| Service | How | Purpose |
|---|---|---|
| Risk Engine | Synchronous HTTP | Trade approval gate |
| ML Inference | HTTP `/predict` | Get confidence score |
| AlgoRAG | HTTP `POST /rag/retrieve` | Historical context |
| NLP/LLM | HTTP | Generate trade reasoning |
| Broker API | HTTP | Place/manage orders |
| Redis | Direct | Sentiment cache, state cache, blackout flags |
| MongoDB | Direct | Decision log, trade journal |
| Kafka | Consumer | Receive `setups.detected`, `sentiment.signals` |
| FCM | SDK | Push notifications |

## Broker Tools (`agent/broker_tools.py`)
Wraps broker API (OANDA / Deriv) for: `place_order`, `get_trade_status`, `close_partial`, `move_sl_to_breakeven`. Always import from here — never call broker APIs directly from nodes.

## Testing Agent Nodes
```python
# Pattern: inject mock AgentState, assert on output state fields and side effects
async def test_decide_node_skips_below_threshold():
    state = AgentState(
        setup_id="test-001",
        instrument="EURUSD",
        timeframe="M5",
        detected_at=datetime.now(tz=timezone.utc),
        raw_confidence=0.60,
        final_confidence=0.60,
        calendar_clear=True,
    )
    result = await decide_node(state)
    assert result.decision == DecisionAction.SKIP
    assert "threshold" in result.decision_reason.lower()
```
