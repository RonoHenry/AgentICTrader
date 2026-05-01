# Test-Driven Development Process
**Project:** AgentICTrader.AI
**Updated:** 2026-04-24

---

## The Rule

No production code is written without a failing test first. No exceptions.

---

## TDD Cycle

```
RED   → Write a failing test that describes the behaviour you want
GREEN → Write the minimal code to make it pass
REFACTOR → Clean up without changing behaviour, tests stay green
```

---

## Test Layers

### 1. Unit Tests
- Test a single function, class, or node in isolation
- No external services, no network, no DB
- Use mocks/fakes for dependencies
- Must run in < 1ms each
- Location: co-located with source, e.g. `ml/features/test_price_features.py`

### 2. Integration Tests
- Test a component against a real dependency (DB, Kafka, Redis)
- Require Docker services running
- Marked with `@pytest.mark.integration`
- Location: `tests/integration/`

### 3. Contract Tests
- Verify that Kafka message schemas match between producer and consumer
- Verify API response shapes match between services
- Marked with `@pytest.mark.contract`

### 4. Property-Based Tests
- Use `hypothesis` to generate random inputs and verify invariants
- Critical for: risk engine rules, confidence scorer bounds, feature engineering
- Marked with `@pytest.mark.property`

---

## TDD by Domain

### ML Features (ml/features/)
```
1. Write test asserting feature output shape and value range
2. Write test asserting feature handles edge cases (NaN, zero volume, single candle)
3. Implement feature function
4. Run tests → green
5. Refactor
```

### ML Models (ml/models/)
```
1. Write test asserting model output contract:
   - Regime classifier always returns one of 5 valid classes
   - Confidence score always in [0.0, 1.0]
   - Pattern detector returns dict with all expected pattern keys
2. Implement model
3. Run tests → green
```

### Agent Nodes (agent/src/graph/nodes/)
```
1. Write test with mock AgentState input
2. Assert on output state fields
3. Assert on side effects (notification sent, DB written)
4. Implement node
5. Run tests → green
```

### Risk Engine (services/risk-engine/)
```
CRITICAL — every rule gets its own test before implementation:
1. test_daily_drawdown_limit_blocks_trade_when_breached
2. test_weekly_drawdown_limit_blocks_trade_when_breached
3. test_position_size_capped_at_max
4. test_news_blackout_blocks_trade_within_15_minutes
5. test_approved_when_all_checks_pass
Implement each rule to make its test pass.
```

### Market Data Connectors (services/market-data/)
```
1. Write test against mock WebSocket server
2. Assert normalised candle output shape
3. Assert error handling (disconnect, bad data)
4. Implement connector
5. Run tests → green
```

---

## Running Tests

```bash
# Activate virtual environment first
source .venv/Scripts/activate   # Windows Git Bash
source .venv/bin/activate       # Linux/Mac

# Unit tests only (no Docker needed)
pytest -m "not integration and not infrastructure" -v

# All tests (requires Docker services running)
pytest -v

# Specific service
pytest ml/features/ -v
pytest services/risk-engine/ -v
pytest agent/ -v

# With coverage
pytest --cov=. --cov-report=html -v

# Property-based tests
pytest -m property -v
```

---

## Coverage Targets

| Domain | Target |
|---|---|
| Risk Engine | 100% — non-negotiable |
| Agent nodes | ≥ 95% |
| ML feature engineering | ≥ 90% |
| Market data connectors | ≥ 90% |
| API endpoints | ≥ 85% |

---

## Test File Naming

```
ml/features/price_features.py          → ml/features/test_price_features.py
services/risk-engine/src/engine/       → services/risk-engine/tests/
agent/src/graph/nodes/decide.py        → agent/tests/nodes/test_decide.py
```

---

## Shared Fixtures (conftest.py)

Key fixtures available across all tests:

```python
# Sample OHLCV candle data
@pytest.fixture
def sample_candles() -> np.ndarray: ...

# Mock AgentState with valid setup
@pytest.fixture
def mock_agent_state() -> AgentState: ...

# Mock risk engine that always approves
@pytest.fixture
def mock_risk_engine_approved(): ...

# Mock risk engine that always rejects
@pytest.fixture
def mock_risk_engine_rejected(): ...

# Mock Kafka producer
@pytest.fixture
def mock_kafka_producer(): ...

# TimescaleDB test session (integration only)
@pytest.fixture
def db_session(): ...
```

---

## Commit Rules

- Never commit with failing tests
- Every PR must include tests for new functionality
- Coverage must not decrease on any PR
- Run before every commit:

```bash
pytest -m "not integration and not infrastructure" -v --tb=short
```
