# Commit: feat(phase3-4) — Tasks 31–37

**Commit hash:** `6d1ff34`
**Branch:** `feature/task-33-notification-service`
**Files changed:** 90 | **Insertions:** 21,701 | **Deletions:** 713

---

## Overview

This commit delivers the full Phase 3 (Agent V1 — Human-in-the-Loop) and the first task of Phase 4 (Autonomous Execution). It wires together every component built in earlier phases — market data, ML inference, risk engine, notifications — into a complete, runnable agent execution loop, adds a production-ready web dashboard, connects a shadow period validation harness, and lays the broker execution foundation for autonomous trading.

All code follows strict TDD: tests were written first (RED), implementation written to pass them (GREEN), then cleaned up (REFACTOR). Every task completed with all tests GREEN.

---

## Task 31 — LangGraph Agent Nodes

**New files:** `agent/nodes/` (7 nodes + `__init__.py`), `backend/tests/test_agent_nodes.py`

Implemented the complete set of nodes for the `Observe → Analyse → Decide → Act → Review → Learn` loop.

### `observe_node`
- Receives a raw Kafka setup message and builds an `AgentState`
- Rejects stale setups older than 60 seconds with `decision=SKIP`
- Parses all time window fields (`time_window`, `narrative_phase`, `time_window_weight`, `is_killzone`, `price_vs_daily_open`, `price_vs_weekly_open`, `price_vs_true_day_open`) from the message for FR-3A compliance

### `analyse_node`
- Fetches FinBERT sentiment score from Redis (`sentiment:{instrument}`, TTL 900s)
- Applies a sentiment multiplier to adjust the raw confidence score
- Reads `blackout:{instrument}` from Redis and sets `blackout_active` on the state

### `decide_node`
- Applies the confidence floor gate: setups below 0.65 are discarded immediately
- Calls the Risk Engine `validate()` synchronously — this gate cannot be bypassed
- Routes to `NOTIFY` in `HUMAN_IN_LOOP` mode or `EXECUTE` in `AUTONOMOUS` mode on approval
- Sets `decision=SKIP` with a reason on Risk Engine rejection

### `notify_node`
- Formats the full FCM alert payload with all required fields:
  `instrument, direction, confidence_score, entry_price, sl_price, tp_price, r_ratio, reasoning, htf_open, htf_high, htf_low, open_bias, time_window, narrative_phase, price_vs_daily_open, price_vs_true_day_open, is_killzone`
- Dispatches via `fcm_sender` callable (injected for testability)

### `execute_node`
- Performs a pre-execution risk recheck via Risk Engine before placing any order
- Converts `TradePlan` to a signed-units OANDA order dict
- Calls `broker_client.place_order()` and records `broker_order_id` and `trade_id` on state
- Sets `decision=SKIP` if the recheck fails — never bypasses the risk gate

### `review_node`
- Triggers a partial exit at 1R (`close_position` called on the broker client)
- Computes R-multiple from trade outcome
- Sets `outcome` and `close_price` on state

### `learn_node`
- Logs every decision (taken, skipped, or modified) to MongoDB `trade_journal` collection
- Includes full input context, risk validation result, reasoning, and order details for auditability
- Always runs as the terminal node — no setup is ever unlogged

---

## Task 32 — LangGraph Agent Graph and Kill Switch

**New files:** `agent/graph.py`, `agent/edges.py`, `backend/tests/test_agent_graph.py`

### `agent/edges.py`
Defines pure conditional routing functions with no side effects:
- `route_after_observe(state)` — early-exit to `learn_node` on stale setups
- `route_after_decide(state)` — routes to `notify`, `execute`, or `learn` based on `DecisionAction`

### `agent/graph.py` — `AgentGraph`
Orchestrates the full loop with dependency injection at construction time:
- `redis_client`, `risk_engine`, `fcm_sender`, `broker_client`, `trade_journal_collection` all injected
- `run(message)` executes the full graph for a single setup message
- `handle_kill_switch_message(msg)` processes `PAUSE`/`RESUME` Kafka commands

**Kill switch** is stored in Redis at `risk:kill_switch:global`. When active:
- The Risk Engine rejects all `validate()` calls
- Both `decide_node` and `execute_node` (recheck) respect it — it cannot be bypassed at any point
- Can be activated/cleared via Kafka message or REST endpoint

### `create_agent_app(redis_client)`
FastAPI application exposing:
| Endpoint | Action |
|---|---|
| `POST /agent/pause` | Activates kill switch |
| `POST /agent/resume` | Clears kill switch |
| `GET /agent/status` | Returns kill switch state + health |

**Shadow period integration:** `AgentGraph` accepts an optional `ShadowPeriodModeEnforcer` which forces `HUMAN_IN_LOOP` mode for all users while the shadow period is active, regardless of the per-user setting.

---

## Task 34 — User and Auth Service

**New files:** `services/auth/main.py`, `services/auth/__init__.py`, `backend/tests/test_auth_service.py`

Full JWT authentication and RBAC implementation using FastAPI.

### Authentication
- **Registration** (`POST /auth/register`): bcrypt password hashing, returns access + refresh tokens
- **Login** (`POST /auth/login`): credential verification, returns access + refresh tokens
- **Token refresh** (`POST /auth/refresh`): exchanges a 7-day refresh token for a new 15-minute access token
- Access tokens: 15-minute TTL | Refresh tokens: 7-day TTL | Algorithm: HS256

### RBAC
| Role | Permissions |
|---|---|
| `ADMIN` | Full access to all resources |
| `TRADER` | Own data + agent control |
| `VIEWER` | Read-only — cannot control agent or modify data |

### Broker Key Encryption
- Broker API keys encrypted with Fernet symmetric encryption before storing in MongoDB `broker_keys` collection
- Encryption key sourced from `BROKER_KEY_ENCRYPTION_KEY` environment variable
- Traders can only store their own keys; Admin can store for any user; Viewer is blocked entirely

---

## Task 35 — Next.js Web Dashboard

**New files:** `frontend/` (full project scaffold)

Built with **Next.js 15 App Router**, **TypeScript**, **Tailwind CSS**, and **shadcn/ui** components.

### Pages

| Route | Description |
|---|---|
| `/dashboard` | Live setups feed via WebSocket (`useSetupsFeed` hook) with real-time updates |
| `/setups/[id]` | Setup detail panel — patterns, confidence score, reasoning, HTF levels, trade plan |
| `/agent` | Agent status card, pause/resume controls, decision log viewer |
| `/journal` | Trade journal table with import button |
| `/analytics` | Win rate by condition, R-distribution chart, equity curve, session breakdown |

### Components (with Vitest tests)
- `SetupCard` — displays a single setup with `ConfidenceBadge` and direction indicator
- `ConfidenceBadge` — colour-coded badge (green ≥ 0.85, amber ≥ 0.75, red < 0.65)
- `AgentStatusCard` — kill switch state, mode, uptime
- `DecisionLog` — paginated agent decision history table
- `RDistributionChart` — R-multiple histogram using Recharts
- `EquityCurveChart` — cumulative P&L chart
- `WinRateChart` — win/loss bar chart grouped by session/condition
- `RiskExposureCard` — live daily/weekly drawdown gauges
- `JournalTable` — trade journal with sortable columns
- `NavSidebar` — collapsible navigation

### API Client (`frontend/src/lib/api.ts`)
Typed wrapper over all backend REST endpoints with WebSocket support for live feeds.

### Testing
Component tests use **Vitest** + **React Testing Library**. Config in `vitest.config.ts`.

---

## Task 36 — Shadow Period Setup and Validation

**New files:** `services/shadow_period/` (5 modules + `__init__.py`), `backend/tests/test_shadow_period.py`

### `oanda_practice.py`
Thin wrapper connecting the agent to the OANDA practice account (`api-fxpractice.oanda.com`). Used instead of the live endpoint during shadow period — all order calls go to paper trading.

### `mode_enforcer.py` — `ShadowPeriodModeEnforcer`
- Reads shadow period state from Redis
- `enforce_human_in_loop(mode)` overrides any `AUTONOMOUS` setting to `HUMAN_IN_LOOP` while shadow is active
- `is_shadow_active()` checks the Redis flag; deactivates automatically when exit criterion is met

### `feedback_logger.py` — `TraderFeedbackLogger`
- Logs trader feedback for every agent alert to MongoDB `shadow_feedback` collection
- Feedback fields: `trader_action` (`TAKEN` | `SKIPPED` | `MODIFIED`), actual entry/SL/TP, P&L R-multiple, free-text notes

### `report_generator.py` — `ShadowPeriodReportGenerator`
- `generate_weekly_report(week_number)` — comparison report per ISO week: agent setups vs trader decisions, match rate, P&L delta
- `generate_full_report()` — all weeks aggregated
- `check_exit_criterion()` — returns `True` when the 4-week match rate ≥ 80% (exit criterion from spec)

### `main.py` — Shadow Period FastAPI Service
| Endpoint | Description |
|---|---|
| `POST /shadow/feedback` | Log trader feedback |
| `GET /shadow/feedback/{setup_id}` | Retrieve feedback for a setup |
| `GET /shadow/report/weekly/{week}` | Weekly comparison report |
| `GET /shadow/report/full` | All weekly reports |
| `GET /shadow/report/exit-criterion` | Check if ≥80% match rate is met |
| `GET /shadow/status` | Current shadow period status |

---

## Task 37 — Broker Execution Tools (Phase 4 start)

**New files:** `agent/broker_tools.py`, `backend/tests/test_broker_tools.py`

Thin async HTTP client over the OANDA v20 REST API, providing four broker operations needed by `execute_node` and `review_node`.

### `OANDABrokerClient`
- Accepts `account_id`, `access_token`, and optional `api_url`
- Defaults to `https://api-fxtrade.oanda.com` (live); pass `https://api-fxpractice.oanda.com` for paper trading
- `_make_request(endpoint, method, json)` handles auth headers, response parsing, and HTTP error propagation

### Public functions

| Function | Description |
|---|---|
| `place_order(client, order)` | Submit a FOK market order with optional SL/TP on fill. Returns `{order_id, trade_id}` |
| `set_sl_tp(client, trade_id, sl, tp)` | Update SL/TP on an open trade via `PUT /trades/{id}/orders`. Returns `True` |
| `close_position(client, trade_id)` | Close a trade at market via `PUT /trades/{id}/close`. Returns `True` |
| `get_position_status(client, trade_id)` | Fetch `{status, unrealised_pnl, current_price}` for a live trade |

### `BrokerError`
Custom exception raised on any API failure (network error, HTTP error, or OANDA `errorMessage` in a 200 response body). Carries an optional `error_code` field for OANDA-specific error codes.

### Instrument normalisation
All public functions accept normalised symbols (`EURUSD`) and convert to OANDA format (`EUR_USD`) automatically using the same symbol map as the WebSocket connector.

**Test coverage: 18 tests — all GREEN**

---

## Supporting Changes

### `agent/state.py`
- Added FR-3A time window fields: `time_window`, `narrative_phase`, `time_window_weight`, `is_killzone`, `price_vs_daily_open`, `price_vs_weekly_open`, `price_vs_true_day_open`
- Added `shadow_period_active: bool = True` flag — forces `HUMAN_IN_LOOP` mode during shadow period

### `agent/__init__.py`
- Added exports for all `broker_tools` public symbols: `BrokerError`, `OANDABrokerClient`, `place_order`, `set_sl_tp`, `close_position`, `get_position_status`

### `services/market_data/`
Relocated and finalised the market data service layer:
- `connectors/base.py` — `BaseConnector` ABC, `TickEvent`, `ConnectorError`, `TickCallback`
- `connectors/oanda.py` — OANDA v20 WebSocket streaming connector with exponential backoff reconnection
- `normaliser.py` — tick-to-OHLCV aggregation for M1, M5, M15, H1, H4, D1, W1
- `kafka_producer.py` — aiokafka producer publishing to `market.ticks` and `market.candles` topics

### `backend/trader/infrastructure/redis_schema.py`
Updated key patterns to include the kill switch key (`risk:kill_switch:global`) and shadow period state key.

### `.kiro/specs/liquidity-engine/`
Added spec for the liquidity engine feature (design document + config).

---

## Test Summary

| Module | Tests |
|---|---|
| `test_agent_nodes.py` | Agent node unit tests (observe, analyse, decide, notify, execute, review, learn) |
| `test_agent_graph.py` | Integration tests for full graph + kill switch |
| `test_auth_service.py` | Auth, JWT, RBAC, broker key encryption |
| `test_shadow_period.py` | Shadow period feedback logging, report generation, exit criterion |
| `test_broker_tools.py` | 18 tests — place_order, set_sl_tp, close_position, get_position_status, BrokerError |

All tests pass GREEN. Zero regressions introduced.

---

## What's Next

**Task 38** — Enable autonomous execution mode:
- Update `execute_node`, `review_node`, `learn_node` for live order flow
- Implement per-user `HUMAN_IN_LOOP` / `AUTONOMOUS` feature toggle in the Auth Service
- Integrate `OANDABrokerClient` into the full agent graph
- Trigger MLflow retraining queue when 50 new trade outcomes are logged
