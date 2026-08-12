# A/B Testing Framework for Confluence Scorer Models

## Overview

This document describes the A/B testing framework implemented for testing RAG-augmented Confluence Scorer models against the baseline version. The framework provides traffic splitting, model versioning, feature flag control, and comprehensive metrics collection.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    A/B Testing Framework                     │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌───────────────┐  ┌───────────────┐  ┌─────────────────┐  │
│  │ Model Version │  │ Traffic       │  │ Feature Flag    │  │
│  │ Registry      │  │ Splitter      │  │ Manager         │  │
│  │               │  │               │  │                 │  │
│  │ • V1 Baseline │  │ • Hash-based  │  │ • Environment   │  │
│  │ • V2 RAG      │  │ • Sticky      │  │ • User Override │  │
│  │ • Caching     │  │ • Configurable│  │ • % Rollout     │  │
│  └───────────────┘  └───────────────┘  └─────────────────┘  │
│                                                             │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │                 Metrics Collection                     │  │
│  │ • Per-variant prediction counts                        │  │
│  │ • Confidence scores, win rates, R-multiples           │  │
│  │ • Statistical significance testing                     │  │
│  │ • User assignment tracking                             │  │
│  └─────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

## Key Components

### 1. Model Versioning System (`model_versioning.py`)

**Purpose**: Manages loading and caching of different model versions from MLflow registry.

**Key Features**:
- Version-aware model loading (V1 baseline, V2 RAG)
- Model metadata tracking
- Caching for performance
- Graceful fallbacks when models unavailable

**Usage**:
```python
from ml.inference.model_versioning import ModelVersionRegistry, ModelVersion

registry = ModelVersionRegistry()
v1_model = registry.load_model("confluence-scorer", ModelVersion.V1_BASELINE)
v2_model = registry.load_model("confluence-scorer", ModelVersion.V2_RAG)
```

**Model Metadata**:
- **V1**: 64 features, baseline without RAG
- **V2**: 68 features (64 + 4 RAG features), RAG-augmented

### 2. Traffic Splitting (`ab_testing.py`)

**Purpose**: Deterministic user assignment to model variants with sticky sessions.

**Key Features**:
- Hash-based deterministic assignment
- Sticky sessions (same user → same variant)
- Configurable split ratios (default 50/50)
- Assignment info for debugging

**Usage**:
```python
from ml.inference.ab_testing import TrafficSplitter

splitter = TrafficSplitter(split_ratio=0.3)  # 30% v2, 70% v1
version = splitter.get_model_version("user_123")
```

**Assignment Logic**:
```python
hash_value = int(hashlib.md5(user_id.encode()).hexdigest(), 16)
hash_fraction = (hash_value % 1000000) / 1000000.0

if hash_fraction < split_ratio:
    return ModelVersion.V2_RAG
else:
    return ModelVersion.V1_BASELINE
```

### 3. Feature Flag Management (`feature_flags.py`)

**Purpose**: Centralized control for A/B test rollouts and user overrides.

**Key Features**:
- Environment variable configuration
- User-specific overrides
- Percentage-based gradual rollouts
- Runtime updates

**Configuration**:
```bash
# Environment Variables
CONFLUENCE_SCORER_AB_TEST=true               # Enable A/B test
CONFLUENCE_SCORER_AB_TEST_ROLLOUT=50.0       # 50% rollout
RAG_FEATURES_ENABLED=true                    # Enable RAG features
ENHANCED_REASONING_ENABLED=true              # Enhanced LLM reasoning
```

**Usage**:
```python
from ml.inference.feature_flags import is_feature_enabled

if is_feature_enabled("confluence_scorer_ab_test", user_id="user123"):
    # A/B test is enabled for this user
```

### 4. A/B Testing Framework (`ab_testing.py`)

**Purpose**: Complete A/B testing orchestration and metrics collection.

**Key Features**:
- End-to-end A/B testing workflow
- Metrics collection per variant
- Statistical significance testing
- Integration with inference engine

**Usage**:
```python
from ml.inference.ab_testing import ABTestingFramework

framework = ABTestingFramework(split_ratio=0.4)  # 40% v2

# Get model for user
model_version, model = framework.get_model_for_user("user123")

# Run prediction with A/B testing
result = framework.predict_with_ab_testing(
    user_id="user123",
    instrument="EURUSD", 
    timeframe="M5",
    candles=candles
)
```

## Metrics Collection

### Per-Variant Metrics

Each model variant tracks:
- **Prediction Count**: Total predictions made
- **Average Confidence**: Mean confidence score
- **Win Rate**: Percentage of winning trades
- **Average R-Multiple**: Mean risk-reward ratio
- **Outcomes**: Win/loss counts

### Statistical Significance

The framework calculates significance between variants:
- **Minimum Sample Size**: 100 predictions per variant
- **Improvement Threshold**: >5% difference in win rate
- **Confidence Level**: 95% when significant
- **Method**: Threshold-based (expandable to proper statistical tests)

## API Integration

### Enhanced Prediction Response

The A/B testing framework adds metadata to prediction responses:

```json
{
  "instrument": "EURUSD",
  "confidence_score": 0.85,
  "regime": "TRENDING_BULLISH",
  "patterns": ["BOS_CONFIRMED"],
  "model_version": "v2-rag",           // NEW: Which model was used
  "ab_test_active": true,              // NEW: A/B test enabled
  "prediction_time": "2024-01-01T..."  // NEW: Timestamp
}
```

### A/B Test Summary Endpoint

Access comprehensive A/B test metrics:

```python
summary = framework.get_ab_test_summary()
# Returns:
{
  "ab_test_active": true,
  "split_ratio": 0.5,
  "variant_a": {
    "prediction_count": 150,
    "avg_confidence": 0.72,
    "win_rate": 0.64,
    "avg_r_multiple": 1.8
  },
  "variant_b": {
    "prediction_count": 148,
    "avg_confidence": 0.78,
    "win_rate": 0.71, 
    "avg_r_multiple": 2.1
  },
  "statistical_significance": {
    "significant": true,
    "improvement_pct": 10.9,
    "confidence_level": 0.95
  }
}
```

## Deployment and Operations

### Environment Configuration

**Development**:
```bash
CONFLUENCE_SCORER_AB_TEST=false  # Disabled by default
```

**Staging**:
```bash
CONFLUENCE_SCORER_AB_TEST=true
CONFLUENCE_SCORER_AB_TEST_ROLLOUT=50.0  # 50% rollout
```

**Production**:
```bash
CONFLUENCE_SCORER_AB_TEST=true
CONFLUENCE_SCORER_AB_TEST_ROLLOUT=100.0  # Full rollout after validation
```

### Gradual Rollout Strategy

1. **Phase 1** (Week 1): 5% rollout to minimize risk
2. **Phase 2** (Week 2): 25% rollout if metrics positive
3. **Phase 3** (Week 3): 50% rollout if significance achieved
4. **Phase 4** (Week 4): 100% rollout if V2 significantly better
5. **Rollback**: Set rollout to 0% if issues detected

### Monitoring

**Key Metrics to Monitor**:
- Prediction latency per variant
- Model loading success rates
- Error rates per variant
- User assignment distribution
- Statistical significance over time

**Alerts**:
- High error rate in either variant (>5%)
- Significant performance degradation (>100ms latency)
- Model loading failures
- Unbalanced traffic distribution (>10% deviation)

## Testing

### Test Coverage

The framework includes comprehensive tests:

**Unit Tests**:
- `test_model_versioning.py`: Model registry functionality
- `test_traffic_splitting.py`: Traffic distribution logic  
- `test_feature_flags.py`: Feature flag management

**Integration Tests**:
- `test_ab_testing_integration.py`: End-to-end workflow
- Model fallback behavior
- Metrics accuracy
- Statistical significance

**Running Tests**:
```bash
# Unit tests
pytest ml/inference/test_model_versioning.py -v
pytest ml/inference/test_traffic_splitting.py -v
pytest ml/inference/test_feature_flags.py -v

# Integration tests  
pytest ml/inference/test_ab_testing_integration.py -v
```

## Performance Considerations

### Caching Strategy

- **Model Loading**: Models cached after first load
- **User Assignments**: Assignment cache for debugging
- **Feature Flags**: Singleton pattern for flag manager

### Latency Impact

- **Model Selection**: ~1-2ms overhead per prediction
- **Hash Calculation**: <1ms for user assignment
- **Metrics Recording**: Asynchronous, minimal impact
- **Total Overhead**: <5ms per prediction

## Security

### User Privacy

- User IDs are hashed for assignment (not stored)
- No PII in metrics collection
- Assignments logged for debugging (can be disabled)

### Model Access

- Models loaded only from authenticated MLflow registry
- Version control prevents unauthorized model loading
- Fallback to baseline ensures availability

## Future Enhancements

### Planned Improvements

1. **Advanced Statistical Tests**: Implement proper A/B testing statistics (t-tests, chi-square)
2. **Multi-Armed Bandit**: Dynamic traffic allocation based on performance
3. **Segment-Based Testing**: Different models for different user segments
4. **Real-time Dashboards**: Live A/B test monitoring
5. **Automated Rollouts**: Automatic promotion based on significance

### Integration Points

1. **Dashboard**: Similar setups panel for RAG context
2. **Monitoring**: Prometheus metrics and Grafana dashboards  
3. **Alerting**: Automated alerts for A/B test issues
4. **Data Pipeline**: Export A/B test data for analysis

## Conclusion

The A/B testing framework provides a robust foundation for testing RAG-augmented ML models in production. Key benefits:

✅ **Safe Rollouts**: Gradual deployment with feature flags  
✅ **Deterministic Assignment**: Consistent user experience  
✅ **Comprehensive Metrics**: Statistical significance testing  
✅ **Operational Control**: Runtime configuration and rollback  
✅ **Performance**: Minimal latency impact (<5ms)  
✅ **Reliability**: Graceful fallbacks and error handling  

The framework enables data-driven decisions about model improvements while minimizing risk to the trading system.