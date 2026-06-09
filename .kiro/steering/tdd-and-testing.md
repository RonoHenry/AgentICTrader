# TDD & Testing Standards

## The Rule
No production code is written without a failing test first. No exceptions.

## TDD Cycle
```
RED   → Write a failing test that describes the behaviour you want
GREEN → Write the minimal code to make it pass
REFACTOR → Clean up without changing behaviour, tests stay green
```

## Test Layers

### Unit Tests
- Test a single function, class, or node in isolation
- No external services, no network, no DB
- Must run in < 1ms each
- Location: co-located with source or in a `tests/` subdirectory alongside the module

### Integration Tests
- Require Docker services running (Qdrant, TimescaleDB, Redis, MongoDB)
- Always mark with `@pytest.mark.integration`
- Location: `tests/integration/` or `<service>/tests/`

### Property-Based Tests (Hypothesis)
- Use `hypothesis` for invariants: embedding dimensions, feature ranges, score bounds
- Always mark with `@pytest.mark.property`
- Critical for: risk engine rules, confidence scorer bounds, embedding shape/NaN checks, feature engineering

### Contract Tests
- Verify Kafka message schemas match between producer and consumer
- Verify API response shapes match between services
- Mark with `@pytest.mark.contract`

## Running Tests
```bash
# Unit tests only (no Docker needed)
pytest -m "not integration and not infrastructure" -v

# All tests (requires Docker)
pytest -v

# Specific module
pytest ml/features/ -v
pytest scripts/rag/ -v
pytest services/algorag/ -v

# With coverage
pytest --cov=. --cov-report=html -v

# Property-based tests
pytest -m property -v
```

## Coverage Targets
| Domain | Target |
|---|---|
| Risk Engine | 100% |
| Agent nodes | ≥ 95% |
| ML features / RAG pipeline | ≥ 90% |
| API endpoints | ≥ 85% |

## Commit Rules
- Never commit with failing tests
- Every PR must include tests for new functionality
- Run before every commit:
```bash
pytest -m "not integration and not infrastructure" -v --tb=short
```

## ML Feature Testing Pattern
```python
# 1. Test output shape and value range
# 2. Test edge cases (NaN, zero volume, single candle, empty lists)
# 3. Implement the feature
# 4. Run tests → green
# 5. Refactor
```

## Shared Fixtures (conftest.py)
Key fixtures available at workspace root:
- `sample_candles` — 5 OHLCV candles as numpy array
- `sample_candle_dict` — Single OHLCV candle as dict
- `bullish_candles` / `bearish_candles` — Directional sequences
- `mock_risk_approved` / `mock_risk_rejected` — Risk engine mocks
- `mock_kafka_producer` — Kafka mock
