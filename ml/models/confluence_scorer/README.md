# Confluence Scorer with RAG Integration

## Overview

The Confluence Scorer is a machine learning model that evaluates trading setup quality by combining traditional technical analysis features with RAG (Retrieval-Augmented Generation) features from similar historical setups.

**Task 16.1 Status: ✅ COMPLETE**
- ✅ Proper integration with existing feature extractors
- ✅ RAG feature extraction with graceful degradation
- ✅ Feature normalization and missing value handling
- ✅ Comprehensive unit tests (24 tests, all passing)
- ✅ Property-based testing for invariants
- ✅ Error handling and validation
- ✅ Documentation and examples

## Architecture

```
ConfluenceFeatureExtractor
├── Traditional Features (10)
│   ├── HTFProjectionExtractor → HTF OHLC features
│   ├── ZoneFeatureExtractor → Structure/pattern detection  
│   └── TimeWindowClassifier → Session-based features
└── RAG Features (4)
    └── AlgoRAGClient → Historical context from similar setups
```

## Feature Vector (14 elements)

| Index | Feature | Range | Source | Description |
|-------|---------|-------|--------|-------------|
| 0 | `htf_high_proximity_pct` | 0-100 | HTF | Distance to HTF high (%) |
| 1 | `htf_low_proximity_pct` | 0-100 | HTF | Distance to HTF low (%) |
| 2 | `htf_body_pct` | 0-100 | HTF | HTF candle body size (%) |
| 3 | `htf_close_position` | 0-1 | HTF | HTF close position in range |
| 4 | `time_window_weight` | 0-1 | Session | Killzone probability weight |
| 5 | `narrative_phase` | 0-5 | Session | Categorical phase encoding |
| 6 | `bos_detected` | 0/1 | Zone | Break of Structure flag |
| 7 | `choch_detected` | 0/1 | Zone | Change of Character flag |
| 8 | `fvg_present` | 0/1 | Zone | Fair Value Gap flag |
| 9 | `liquidity_sweep` | 0/1 | Zone | Liquidity sweep flag |
| **10** | **`avg_r_multiple`** | **0-10** | **RAG** | **Avg R from similar setups** |
| **11** | **`win_rate`** | **0-1** | **RAG** | **Win rate from similar setups** |
| **12** | **`sample_size`** | **0-1** | **RAG** | **Sample size (normalized/100)** |
| **13** | **`max_similarity`** | **0-1** | **RAG** | **Max similarity to historical** |

**Bold features (10-13) are new RAG enhancements added in Task 16.1.**

## Usage

### Basic Usage

```python
from ml.models.confluence_scorer.features import ConfluenceFeatureExtractor

# Without RAG (graceful degradation)
extractor = ConfluenceFeatureExtractor()
features = await extractor.extract_features(candles, setup_data)
feature_vector = features.to_array()  # Shape: (14,)
```

### With RAG Integration

```python
from ml.models.confluence_scorer.features import ConfluenceFeatureExtractor
from ml.algorag.client import AlgoRAGClient

# With RAG client
async with AlgoRAGClient() as rag_client:
    extractor = ConfluenceFeatureExtractor(rag_client=rag_client)
    features = await extractor.extract_features(candles, setup_data)
    
    print(f"Traditional features working: {features.htf_high_proximity_pct}")
    print(f"RAG features active: {features.avg_r_multiple}")
```

### Input Data Format

**Candles:**
```python
candles = [
    {
        "time": "2024-01-01T08:00:00Z",
        "open": 1.5000,
        "high": 1.5100,
        "low": 1.4900, 
        "close": 1.5080,
        "volume": 1000,
    },
    # ... more candles
]
```

**Setup Data:**
```python
setup_data = {
    "instrument": "EURUSD",
    "timestamp": datetime(2024, 1, 1, 8, 10, tzinfo=timezone.utc),
    "direction": "LONG",
    "entry_price": 1.5140,
    "timeframe": "M5",
    "htf_timeframe": "H1", 
    "current_price": 1.5140,
}
```

## Key Properties

### ✅ Graceful Degradation
- Works without RAG client (RAG features = 0.0)
- Continues functioning when RAG service is unavailable
- No errors when network/service issues occur

### ✅ Feature Normalization
- All features within expected bounds
- Percentages: 0-100 range maintained
- Ratios: normalized to 0-1 range
- No NaN or infinite values

### ✅ Error Resilience
- Handles malformed candle data
- Works with missing setup fields
- Graceful fallbacks for extreme price values
- Comprehensive validation and bounds checking

### ✅ Thread Safety
- Supports concurrent feature extraction
- Stateless operation (no shared mutable state)
- Async-safe implementation

### ✅ Deterministic
- Same input always produces same output
- Reproducible results for testing/debugging
- Consistent feature ordering

## Testing

### Run All Tests
```bash
# Full test suite (24 tests)
pytest ml/models/confluence_scorer/test_features.py -v

# Property-based tests only  
pytest ml/models/confluence_scorer/test_features.py -m property -v

# Integration tests only
pytest ml/models/confluence_scorer/test_features.py -m integration -v
```

### Test Coverage
- ✅ Unit tests: Basic functionality, edge cases
- ✅ Integration tests: Real extractor integration 
- ✅ Property tests: Invariant validation
- ✅ Error handling: Malformed data, timeouts
- ✅ Bounds validation: Feature ranges, normalization
- ✅ Concurrency tests: Thread safety

### Example Usage Script
```bash
# Run interactive examples
python ml/models/confluence_scorer/example_usage.py
```

## Integration Points

### Existing Feature Extractors
- `HTFProjectionExtractor`: HTF OHLC computation
- `ZoneFeatureExtractor`: Pattern/structure detection  
- `TimeWindowClassifier`: Session classification

### RAG Service
- `AlgoRAGClient`: Retrieves similar historical setups
- Endpoint: `POST /rag/retrieve`
- Graceful degradation when unavailable

### ML Pipeline 
- Compatible with existing Confluence Scorer training
- Feature vector maintains backward compatibility
- Ready for Task 16.2 (model retraining)

## Implementation Details

### Traditional Feature Integration
- Uses real extractors (not placeholders)
- Proper HTF candle construction from M5 data
- Session classification with NY timezone handling
- Zone feature detection with structure analysis

### RAG Feature Processing
- Sample size normalized by dividing by 100
- Win rate validated to [0,1] bounds
- R-multiple capped at reasonable max (10.0)
- Similarity score validated to [0,1] bounds

### Error Handling
```python
# HTF extraction with fallback
try:
    htf_projection = htf_extractor.compute_projections(...)
    htf_features = {...}
except Exception as e:
    logger.warning(f"HTF extraction failed: {e}")
    htf_features = default_htf_features()
```

### Validation Pipeline
```python
# Final validation pass
for key, value in features.items():
    if isinstance(value, float) and (np.isnan(value) or np.isinf(value)):
        logger.warning(f"Invalid {key}: {value}, using default")
        features[key] = safe_default(key)
```

## Migration Guide

### From v1 (Traditional Only) to v2 (RAG Enhanced)

**No breaking changes:** Existing code continues to work unchanged.

```python
# v1 - still works
extractor = ConfluenceFeatureExtractor() 
features = await extractor.extract_features(candles, setup)

# v2 - enhanced with RAG  
async with AlgoRAGClient() as rag_client:
    extractor = ConfluenceFeatureExtractor(rag_client=rag_client)
    features = await extractor.extract_features(candles, setup)
```

**Feature vector changes:**
- v1: 10 features (traditional only)
- v2: 14 features (traditional + 4 RAG features)
- Existing models need retraining (Task 16.2)

## Next Steps

### ✅ Task 16.1: Complete
- Traditional feature integration ✅
- RAG feature extraction ✅  
- Feature normalization ✅
- Comprehensive testing ✅

### 🔄 Task 16.2: Retrain Model (Next)
- Create training script with 14-feature vectors
- Retrain Confluence Scorer with RAG features
- Validate model performance improvement
- Update MLflow model registry

### 🔄 Task 16.3: Integration Tests (Optional) 
- End-to-end pipeline testing
- Performance benchmarking
- Production readiness validation