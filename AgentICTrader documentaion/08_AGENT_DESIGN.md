# Agentic AI Design
**Project:** AgentICTrader.AI
**Version:** 1.0.0
**Last Updated:** 2026-04-04

---

## 1. Agent Philosophy

The AgentICTrader agent is not a chatbot. It is an autonomous decision-making system modelled directly on the cognitive process of an expert discretionary trader performing Top Down Analysis. Every node in the agent's state graph represents a specific mental step that the trader performs before entering a trade.

**The agent's internal monologue:**
```
"The D1 is bearish. H4 confirms. I'm on the M5 now.
 Price broke structure. There's a supply zone overhead.
 Sentiment is negative. Calendar is clear.
 Risk check passes. Confidence is 0.83. This is a valid short.
 I'm sending the alert."
```

That monologue is what we're encoding.

---

## 2. Agent State Definition

The entire agent context is carried in a typed state object that flows through every node.

```python
# agent/src/graph/state.py

from typing import Optional, List, Dict, Any
from pydantic import BaseModel
from datetime import datetime
from enum import Enum

class Direction(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"

class AgentMode(str, Enum):
    HUMAN_IN_LOOP = "HUMAN_IN_LOOP"
    AUTONOMOUS = "AUTONOMOUS"

class DecisionAction(str, Enum):
    EXECUTE = "EXECUTE"
    NOTIFY = "NOTIFY"
    SKIP = "SKIP"
    WAIT = "WAIT"

class RiskVerdictEnum(str, Enum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"

class Pattern(BaseModel):
    type: str
    confidence: float
    level: Optional[float] = None
    zone: Optional[Dict] = None

class TradePlan(BaseModel):
    entry: float
    stop_loss: float
    take_profit_1: float
    take_profit_2: Optional[float] = None
    r_ratio: float
    recommended_size: float

class RiskValidation(BaseModel):
    verdict: RiskVerdictEnum
    rejection_reason: Optional[str] = None
    checks: Dict[str, str] = {}
    recommended_size: Optional[float] = None

class AgentState(BaseModel):
    # ── Setup Data ──
    setup_id: str
    instrument: str
    timeframe: str
    direction: Optional[Direction] = None
    detected_at: datetime

    # ── ML Outputs ──
    regime: Optional[str] = None
    regime_confidence: Optional[float] = None
    patterns: List[Pattern] = []
    raw_confidence: Optional[float] = None
    htf_alignment: Dict[str, str] = {}

    # ── Sentiment ──
    sentiment_score: Optional[float] = None
    sentiment_label: Optional[str] = None
    sentiment_aligned: Optional[bool] = None
    top_headlines: List[str] = []

    # ── Calendar ──
    calendar_clear: bool = True
    minutes_to_next_event: Optional[int] = None
    next_event_name: Optional[str] = None

    # ── Final Score ──
    final_confidence: Optional[float] = None

    # ── Trade Plan ──
    trade_plan: Optional[TradePlan] = None

    # ── Risk ──
    risk_validation: Optional[RiskValidation] = None

    # ── Decision ──
    decision: Optional[DecisionAction] = None
    decision_reason: Optional[str] = None
    mode: AgentMode = AgentMode.HUMAN_IN_LOOP

    # ── LLM Reasoning ──
    trade_reasoning: Optional[str] = None

    # ── Execution ──
    broker_order_id: Optional[str] = None
    trade_id: Optional[str] = None

    # ── Outcome (populated in review/learn) ──
    outcome: Optional[str] = None
    r_multiple: Optional[float] = None
    close_price: Optional[float] = None
    close_time: Optional[datetime] = None

    # ── Meta ──
    error: Optional[str] = None
    processing_times: Dict[str, float] = {}
```

---

## 3. Node Implementations

### 3.1 `observe_node`
**Input:** Kafka message from `setups.detected`
**Output:** AgentState populated with setup data + raw ML outputs

```python
# agent/src/graph/nodes/observe.py

async def observe_node(state: AgentState) -> AgentState:
    """
    Entry point. Receives setup from ML engine via Kafka.
    Fetches fresh candle context and validates setup is still valid.
    """
    t0 = time.time()

    # Verify setup is still relevant (not expired)
    latest_candle = await market_tools.get_latest_candle(
        state.instrument, state.timeframe
    )

    # Check if price has moved too far from original entry
    if abs(latest_candle.close - state.trade_plan.entry) > state.trade_plan.r_risk * 0.5:
        state.decision = DecisionAction.SKIP
        state.decision_reason = "Price moved too far from entry since setup detected"
        return state

    state.processing_times["observe"] = time.time() - t0
    return state
```

### 3.2 `analyse_node`
**Input:** State with setup + ML data
**Output:** State enriched with sentiment + calendar + final confidence

```python
# agent/src/graph/nodes/analyse.py

async def analyse_node(state: AgentState) -> AgentState:
    """
    Enriches setup with sentiment, calendar, and computes final confidence.
    """
    t0 = time.time()

    # Get sentiment
    sentiment = await sentiment_tools.get_sentiment(state.instrument)
    state.sentiment_score = sentiment.score
    state.sentiment_label = sentiment.label
    state.sentiment_aligned = (
        (state.direction == Direction.SHORT and sentiment.score < -0.2) or
        (state.direction == Direction.LONG and sentiment.score > 0.2)
    )
    state.top_headlines = sentiment.top_headlines

    # Check calendar
    calendar = await sentiment_tools.check_calendar(state.instrument)
    state.calendar_clear = calendar.minutes_to_next_high_impact > 15
    state.minutes_to_next_event = calendar.minutes_to_next_high_impact
    state.next_event_name = calendar.next_event_name

    # Apply sentiment adjustment to confidence
    sentiment_bonus = 0.05 if state.sentiment_aligned else -0.08
    calendar_bonus = 0.03 if state.calendar_clear else -0.15

    state.final_confidence = min(1.0, max(0.0,
        state.raw_confidence + sentiment_bonus + calendar_bonus
    ))

    state.processing_times["analyse"] = time.time() - t0
    return state
```

### 3.3 `decide_node`
**Input:** Fully enriched state
**Output:** Decision (EXECUTE / NOTIFY / SKIP) + risk validation

```python
# agent/src/graph/nodes/decide.py

CONFIDENCE_THRESHOLD = 0.75  # Loaded from user config

async def decide_node(state: AgentState) -> AgentState:
    """
    Applies threshold gate, calls risk engine, makes final decision.
    """
    t0 = time.time()

    # Confidence gate
    if state.final_confidence < CONFIDENCE_THRESHOLD:
        state.decision = DecisionAction.SKIP
        state.decision_reason = f"Confidence {state.final_confidence:.2f} below threshold {CONFIDENCE_THRESHOLD}"
        return state

    # Calendar hard block
    if not state.calendar_clear:
        state.decision = DecisionAction.SKIP
        state.decision_reason = f"High-impact event in {state.minutes_to_next_event} minutes: {state.next_event_name}"
        return state

    # Risk engine validation (synchronous gate)
    risk_result = await risk_tools.validate_trade(
        instrument=state.instrument,
        direction=state.direction,
        stop_loss=state.trade_plan.stop_loss,
        entry=state.trade_plan.entry
    )
    state.risk_validation = risk_result

    if risk_result.verdict == RiskVerdictEnum.REJECTED:
        state.decision = DecisionAction.SKIP
        state.decision_reason = f"Risk rejected: {risk_result.rejection_reason}"
        return state

    # All gates passed — generate reasoning
    state.trade_reasoning = await llm_tools.generate_trade_reasoning(state)

    # Route based on mode
    if state.mode == AgentMode.HUMAN_IN_LOOP:
        state.decision = DecisionAction.NOTIFY
    else:
        state.decision = DecisionAction.EXECUTE

    state.processing_times["decide"] = time.time() - t0
    return state
```

### 3.4 `notify_node`

```python
# agent/src/graph/nodes/notify.py

async def notify_node(state: AgentState) -> AgentState:
    """
    Formats and dispatches push notification to trader.
    """
    message = format_alert(state)
    # e.g. "🔴 US500 SHORT | Score: 0.83 | BOS + Supply Zone
    #       Entry: 6,519 | SL: 6,528 | TP: 6,460 | 3.2R
    #       Sentiment: Bearish | Calendar: Clear"

    await notification_service.send_push(
        user_id=state.user_id,
        title=f"{state.instrument} {state.direction} Setup",
        body=message,
        data={"setup_id": state.setup_id}
    )

    await journal_tools.log_decision(state)
    return state
```

### 3.5 `execute_node`

```python
# agent/src/graph/nodes/execute.py

async def execute_node(state: AgentState) -> AgentState:
    """
    Places order via broker API. Only runs in AUTONOMOUS mode.
    """
    # Final pre-execution risk check (belt and suspenders)
    if state.risk_validation.verdict != RiskVerdictEnum.APPROVED:
        state.decision = DecisionAction.SKIP
        state.error = "Execution aborted: risk validation not approved"
        return state

    order_result = await broker_tools.place_order(
        instrument=state.instrument,
        direction=state.direction,
        size=state.risk_validation.recommended_size,
        stop_loss=state.trade_plan.stop_loss,
        take_profit=state.trade_plan.take_profit_1
    )

    state.broker_order_id = order_result.order_id
    state.trade_id = await journal_tools.create_trade_record(state, order_result)

    await notification_service.send_push(
        title=f"Trade Executed: {state.instrument} {state.direction}",
        body=f"Entry: {order_result.fill_price} | Size: {state.risk_validation.recommended_size}"
    )

    await journal_tools.log_decision(state)
    return state
```

### 3.6 `review_node`

```python
# agent/src/graph/nodes/review.py

async def review_node(state: AgentState) -> AgentState:
    """
    Monitors open trade. Manages partial exits, trailing SL.
    Runs on a polling interval until trade closes.
    """
    trade_status = await broker_tools.get_trade_status(state.broker_order_id)

    if trade_status.is_closed:
        state.outcome = trade_status.close_reason
        state.close_price = trade_status.close_price
        state.close_time = trade_status.close_time
        state.r_multiple = calculate_r_multiple(
            state.trade_plan.entry,
            state.close_price,
            state.trade_plan.stop_loss,
            state.direction
        )
        return state  # → learn_node

    # Partial exit at 1R
    if trade_status.unrealised_r >= 1.0 and not state.partial_taken:
        await broker_tools.close_partial(state.broker_order_id, 0.5)
        await broker_tools.move_sl_to_breakeven(state.broker_order_id, state.trade_plan.entry)
        state.partial_taken = True

    return state  # Continue monitoring
```

### 3.7 `learn_node`

```python
# agent/src/graph/nodes/learn.py

async def learn_node(state: AgentState) -> AgentState:
    """
    Logs trade outcome and queues data for model retraining.
    """
    # Update trade journal with outcome
    await journal_tools.close_trade_record(
        trade_id=state.trade_id,
        close_price=state.close_price,
        close_time=state.close_time,
        r_multiple=state.r_multiple,
        outcome=state.outcome
    )

    # Queue for retraining
    await ml_tools.queue_retraining_sample({
        "setup_id": state.setup_id,
        "features": state.setup_features_snapshot,
        "confidence_score": state.final_confidence,
        "r_multiple": state.r_multiple,
        "outcome_label": 1 if state.r_multiple > 0 else 0
    })

    logger.info(f"Trade {state.trade_id} closed. R: {state.r_multiple:.2f}. Queued for retraining.")
    return state
```

---

## 4. Graph Routing Logic

```python
# agent/src/graph/edges.py

def route_after_decide(state: AgentState) -> str:
    if state.decision == DecisionAction.SKIP:
        return "end"
    elif state.decision == DecisionAction.NOTIFY:
        return "notify_node"
    elif state.decision == DecisionAction.EXECUTE:
        return "execute_node"

def route_after_execute(state: AgentState) -> str:
    if state.error:
        return "end"
    return "review_node"

def route_after_review(state: AgentState) -> str:
    if state.outcome:  # Trade closed
        return "learn_node"
    return "review_node"  # Continue monitoring
```

---

## 5. Safety Controls

The agent has three layers of safety that cannot be bypassed:

1. **Confidence Threshold Gate** (`decide_node`) — Soft configurable threshold, hard minimum of 0.65
2. **Risk Engine Gate** (`decide_node`) — Synchronous call, must return APPROVED
3. **Pre-execution Recheck** (`execute_node`) — Even if decide approved, execute re-validates

**Kill Switch:**
```python
# Any service can publish to kill-switch topic
# Agent subscribes and halts ALL execution immediately
kafka_consumer.subscribe(["agent.kill_switch"])

# Manual via API
POST /agent/pause  →  sets agent_mode = PAUSED in Redis
```

---

*Document Owner: Agent Engineer | Review Cycle: Per Agent Version*
