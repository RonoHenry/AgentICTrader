# Data Models & Schema Design
**Project:** AgentICTrader.AI
**Version:** 1.0.0
**Last Updated:** 2026-04-04

---

## 1. Overview

AgentICTrader.AI uses three database technologies, each chosen for its strengths:

| Database | Use Case | Why |
|---|---|---|
| **TimescaleDB** | Time-series OHLCV, tick, indicator data | Optimised for time-series queries, hypertables, continuous aggregates |
| **MongoDB** | Trade journal, agent decision logs, user config | Flexible document schema for rich, nested trade context |
| **Redis** | Live candle cache, agent state, session tokens | Sub-millisecond reads for real-time inference |

---

## 2. TimescaleDB Schemas

### 2.1 `candles` — OHLCV Candle Data

```sql
CREATE TABLE candles (
    time            TIMESTAMPTZ     NOT NULL,
    instrument      VARCHAR(20)     NOT NULL,   -- e.g. 'US500', 'EURUSD'
    timeframe       VARCHAR(5)      NOT NULL,   -- e.g. 'M5', 'H1', 'D1'
    open            NUMERIC(18, 5)  NOT NULL,
    high            NUMERIC(18, 5)  NOT NULL,
    low             NUMERIC(18, 5)  NOT NULL,
    close           NUMERIC(18, 5)  NOT NULL,
    volume          BIGINT,
    spread          NUMERIC(10, 5),
    complete        BOOLEAN         DEFAULT TRUE,
    source          VARCHAR(20),               -- 'OANDA', 'IBKR', 'ALPACA'
    created_at      TIMESTAMPTZ     DEFAULT NOW()
);

-- Convert to hypertable
SELECT create_hypertable('candles', 'time');

-- Indexes
CREATE INDEX ON candles (instrument, timeframe, time DESC);
CREATE INDEX ON candles (instrument, time DESC);

-- Continuous aggregate for D1 rollup from H1
CREATE MATERIALIZED VIEW candles_daily
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 day', time) AS bucket,
    instrument,
    first(open, time)   AS open,
    max(high)           AS high,
    min(low)            AS low,
    last(close, time)   AS close,
    sum(volume)         AS volume
FROM candles
WHERE timeframe = 'H1'
GROUP BY bucket, instrument;
```

### 2.2 `ticks` — Raw Tick Data

```sql
CREATE TABLE ticks (
    time        TIMESTAMPTZ     NOT NULL,
    instrument  VARCHAR(20)     NOT NULL,
    bid         NUMERIC(18, 5)  NOT NULL,
    ask         NUMERIC(18, 5)  NOT NULL,
    mid         NUMERIC(18, 5)  GENERATED ALWAYS AS ((bid + ask) / 2) STORED,
    spread      NUMERIC(10, 5)  GENERATED ALWAYS AS (ask - bid) STORED,
    volume      INTEGER,
    source      VARCHAR(20)
);

SELECT create_hypertable('ticks', 'time');

-- Retention: auto-drop ticks older than 90 days
SELECT add_retention_policy('ticks', INTERVAL '90 days');
```

### 2.3 `indicators` — Pre-computed Technical Indicators

```sql
CREATE TABLE indicators (
    time            TIMESTAMPTZ     NOT NULL,
    instrument      VARCHAR(20)     NOT NULL,
    timeframe       VARCHAR(5)      NOT NULL,
    atr_14          NUMERIC(18, 5),
    atr_pct         NUMERIC(10, 4),         -- ATR as % of price
    rsi_14          NUMERIC(8, 4),
    adx_14          NUMERIC(8, 4),
    ema_50          NUMERIC(18, 5),
    ema_200         NUMERIC(18, 5),
    volume_sma_20   BIGINT,
    volume_delta    BIGINT,
    session         VARCHAR(15),            -- 'LONDON', 'NEW_YORK', 'TOKYO', 'OVERLAP'
    day_of_week     SMALLINT,
    is_news_window  BOOLEAN DEFAULT FALSE
);

SELECT create_hypertable('indicators', 'time');
CREATE INDEX ON indicators (instrument, timeframe, time DESC);
```

### 2.4 `economic_events` — Economic Calendar

```sql
CREATE TABLE economic_events (
    id              UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    event_time      TIMESTAMPTZ     NOT NULL,
    currency        VARCHAR(5)      NOT NULL,
    event_name      VARCHAR(200)    NOT NULL,
    impact          VARCHAR(10)     NOT NULL CHECK (impact IN ('LOW', 'MEDIUM', 'HIGH')),
    forecast        VARCHAR(50),
    previous        VARCHAR(50),
    actual          VARCHAR(50),
    source          VARCHAR(50),
    created_at      TIMESTAMPTZ     DEFAULT NOW()
);

CREATE INDEX ON economic_events (event_time, currency);
CREATE INDEX ON economic_events (event_time, impact);
```

---

## 3. MongoDB Collections

### 3.1 `trade_journal` — Trade History

```json
{
  "_id": "ObjectId",
  "trade_id": "TRD-20260404-001",
  "source": "MANUAL | AGENT",
  "instrument": "US500",
  "direction": "SHORT",
  "status": "CLOSED | OPEN | CANCELLED",

  "entry": {
    "time": "ISODate",
    "price": 6519.0,
    "trigger": "M5_BOS_CONFIRMED"
  },

  "exit": {
    "time": "ISODate",
    "price": 6460.0,
    "reason": "TP_HIT | SL_HIT | MANUAL | PARTIAL"
  },

  "risk": {
    "stop_loss": 6528.0,
    "take_profit": 6460.0,
    "risk_pct": 1.0,
    "position_size": 2.5,
    "r_risk": 9.0,
    "r_reward": 59.0,
    "r_ratio": 6.55
  },

  "outcome": {
    "pnl_pips": 590,
    "pnl_usd": 1475.0,
    "r_multiple": 6.55,
    "duration_minutes": 217
  },

  "setup": {
    "confidence_score": 0.83,
    "regime": "TRENDING_BEARISH",
    "patterns": ["BOS_CONFIRMED", "BEARISH_ARRAY_REJECTION", "LIQUIDITY_SWEEP"],
    "htf_alignment": {
      "D1": "BEARISH",
      "H4": "BEARISH",
      "H1": "BEARISH"
    },
    "session": "NEW_YORK",
    "timeframe_trigger": "M5"
  },

  "sentiment": {
    "score": -0.71,
    "label": "BEARISH",
    "news_tags": ["tariff_escalation", "fed_hawkish", "risk_off"],
    "checked_at": "ISODate"
  },

  "reasoning": "Short US500 on M5 BOS below 6,512. Daily and H4 both in established downtrend. Bearish OB (Bearish Array at Premium) confluence at 6,519–6,528 overhead. Sentiment strongly negative following tariff news. Confidence 0.83 — above threshold. News blackout clear for next 2 hours.",

  "tags": ["clean_setup", "multi_tf_confluence", "news_aligned"],

  "agent_decision_id": "ObjectId | null",
  "created_at": "ISODate",
  "updated_at": "ISODate"
}
```

### 3.2 `agent_decisions` — Full Agent Decision Log

```json
{
  "_id": "ObjectId",
  "decision_id": "DEC-20260404-0047",
  "timestamp": "ISODate",
  "instrument": "US500",
  "timeframe": "M5",

  "input_context": {
    "candle_snapshot": [...],
    "regime": "TRENDING_BEARISH",
    "patterns_detected": ["BOS_CONFIRMED", "BEARISH_ARRAY_REJECTION"],
    "raw_confidence": 0.83,
    "sentiment_score": -0.71,
    "htf_bias": "BEARISH",
    "calendar_clear": true,
    "time_utc": "ISODate",
    "session": "NEW_YORK"
  },

  "risk_validation": {
    "verdict": "APPROVED",
    "checks": {
      "daily_dd_limit": "OK",
      "weekly_dd_limit": "OK",
      "max_position_size": "OK",
      "correlation_exposure": "OK",
      "news_blackout": "OK"
    },
    "recommended_size": 2.5,
    "current_daily_pnl": 0.0
  },

  "decision": {
    "action": "NOTIFY | EXECUTE | SKIP",
    "reason": "Confidence above threshold, all risk checks passed",
    "mode": "HUMAN_IN_LOOP | AUTONOMOUS"
  },

  "notification_sent": true,
  "notification_at": "ISODate",

  "trade_taken": true,
  "trade_id": "TRD-20260404-001",

  "llm_reasoning": "Full LLM-generated reasoning narrative...",

  "created_at": "ISODate"
}
```

### 3.3 `setups` — Detected Setup Archive

```json
{
  "_id": "ObjectId",
  "setup_id": "SET-20260404-0231",
  "detected_at": "ISODate",
  "instrument": "US500",
  "timeframe": "M5",
  "direction": "SHORT",

  "patterns": [
    {
      "type": "BOS_CONFIRMED",
      "level": 6512.0,
      "strength": 0.91,
      "candle_time": "ISODate"
    },
    {
      "type": "BEARISH_ARRAY",
      "high": 6528.0,
      "low": 6519.0,
      "strength": 0.87,
      "test_count": 2
    }
  ],

  "scores": {
    "pattern_score": 0.85,
    "regime_score": 0.90,
    "sentiment_score": 0.75,
    "htf_alignment_score": 0.88,
    "final_confidence": 0.83
  },

  "regime": "TRENDING_BEARISH",
  "session": "NEW_YORK",

  "trade_plan": {
    "entry": 6519.0,
    "stop_loss": 6528.0,
    "take_profit_1": 6490.0,
    "take_profit_2": 6460.0,
    "r_ratio": 3.22
  },

  "outcome": "TRADE_TAKEN | IGNORED | EXPIRED",
  "trade_id": "TRD-20260404-001 | null",
  "expired_at": "ISODate | null",

  "created_at": "ISODate"
}
```

### 3.4 `users` — User Configuration

```json
{
  "_id": "ObjectId",
  "user_id": "USR-0001",
  "email": "trader@agentict.ai",
  "role": "ADMIN | TRADER | VIEWER",

  "risk_config": {
    "max_risk_per_trade_pct": 1.0,
    "max_daily_drawdown_pct": 3.0,
    "max_weekly_drawdown_pct": 6.0,
    "max_open_trades": 3,
    "confidence_threshold": 0.75,
    "instruments_enabled": ["US500", "US30", "EURUSD", "XAUUSD"]
  },

  "agent_config": {
    "mode": "HUMAN_IN_LOOP | AUTONOMOUS",
    "autonomous_enabled": false,
    "notification_channels": ["PUSH", "EMAIL"],
    "alert_on_setups_above": 0.75
  },

  "broker": {
    "provider": "OANDA",
    "account_id": "encrypted",
    "api_key_ref": "kms://...",
    "environment": "PAPER | LIVE"
  },

  "created_at": "ISODate",
  "updated_at": "ISODate"
}
```

---

## 4. Redis Key Schema

| Key Pattern | Type | TTL | Description |
|---|---|---|---|
| `candle:{instrument}:{timeframe}:latest` | Hash | 65s (M1) | Latest complete candle |
| `candle:{instrument}:{timeframe}:live` | Hash | 5s | Current forming candle |
| `indicators:{instrument}:{timeframe}:latest` | Hash | 300s | Latest indicator values |
| `sentiment:{instrument}:latest` | Hash | 900s | Latest sentiment signal |
| `agent:state:{user_id}` | JSON | 3600s | Agent session state |
| `risk:exposure:{user_id}` | Hash | 60s | Current risk exposure snapshot |
| `risk:daily_pnl:{user_id}:{date}` | String | 86400s | Daily P&L running total |
| `session:{token}` | String | 3600s | Auth session token |
| `rate_limit:{user_id}:{endpoint}` | String | 60s | API rate limit counter |

---

## 5. Kafka Topic Schema

### Topic: `market.candles`
```json
{
  "schema_version": "1.0",
  "event_type": "CANDLE_CLOSED",
  "timestamp": "ISODate",
  "instrument": "US500",
  "timeframe": "M5",
  "candle": {
    "time": "ISODate",
    "open": 6519.0,
    "high": 6528.0,
    "low": 6510.0,
    "close": 6512.0,
    "volume": 15420
  }
}
```

### Topic: `setups.detected`
```json
{
  "schema_version": "1.0",
  "event_type": "SETUP_DETECTED",
  "setup_id": "SET-20260404-0231",
  "timestamp": "ISODate",
  "instrument": "US500",
  "direction": "SHORT",
  "confidence": 0.83,
  "patterns": ["BOS_CONFIRMED", "BEARISH_ARRAY_REJECTION"],
  "regime": "TRENDING_BEARISH",
  "trade_plan": { ... },
  "requires_sentiment_enrichment": true
}
```

### Topic: `sentiment.signals`
```json
{
  "schema_version": "1.0",
  "event_type": "SENTIMENT_UPDATED",
  "timestamp": "ISODate",
  "instrument": "US500",
  "sentiment_score": -0.71,
  "label": "BEARISH",
  "source": "NEWS_FINBERT",
  "top_headlines": ["...", "..."],
  "setup_id": "SET-20260404-0231"
}
```

### Topic: `trades.executed`
```json
{
  "schema_version": "1.0",
  "event_type": "TRADE_OPENED | TRADE_CLOSED",
  "trade_id": "TRD-20260404-001",
  "timestamp": "ISODate",
  "instrument": "US500",
  "direction": "SHORT",
  "entry_price": 6519.0,
  "stop_loss": 6528.0,
  "take_profit": 6460.0,
  "size": 2.5,
  "broker_order_id": "...",
  "source": "AGENT | MANUAL"
}
```

---

*Document Owner: Lead Data Engineer | Review Cycle: Per Phase Milestone*
