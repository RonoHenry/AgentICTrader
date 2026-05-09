# RAG Enhancement - Design Document

## Architecture Overview

The RAG system augments the existing ML pipeline with a vector-based memory system that retrieves and ranks similar historical setups.

**Full Architecture**: See `docs/RAG_ARCHITECTURE.md`  
**System Diagrams**: See `docs/RAG_SYSTEM_DIAGRAM.md`

---

## Key Design Decisions

### 1. Vector Store: Qdrant
**Choice**: Qdrant (self-hosted)  
**Rationale**:
- Native metadata filtering + vector search
- High performance (Rust-based)
- Easy Docker deployment
- Python async SDK
- Cost-effective ($40/month vs. $70/month for Pinecone)

**Alternative Considered**: Pinecone (managed service)  
**Rejected Because**: Higher cost, vendor lock-in

### 2. Embedding Strategy: Multi-Modal
**Choice**: 528-dim combined embedding  
**Components**:
- Narrative embedding (384-dim, 40% weight) - Sentence-BERT
- Structured embedding (128-dim, 40% weight) - Custom autoencoder
- Temporal embedding (16-dim, 20% weight) - Cyclical encoding

**Rationale**: Captures semantic meaning, structured features, and time context

### 3. Retrieval Pipeline: Filter → Search → Re-Rank
**Steps**:
1. Metadata filtering (instrument, time window, HTF bias, winning setups)
2. Vector similarity search (cosine distance, top-10)
3. Re-ranking (outcome quality + recency + confluence overlap)
4. Top-5 selection

**Rationale**: Balances precision and recall, prioritizes high-quality examples

### 4. Integration Pattern: Augmentation Not Replacement
**Choice**: Add RAG features to existing ML pipeline  
**Rationale**:
- Preserves baseline functionality
- Allows A/B testing
- Graceful degradation if RAG fails
- Incremental value delivery

---

## Component Design

### 1. Data Preparation Pipeline

**Script**: `scripts/rag/prepare_historical_setups.py`

**Input**: MongoDB `trade_journal` collection  
**Output**: `data/enriched_setups.json`

**Process**:
```python
for trade in trade_journal:
    # Fetch historical candles
    candles = fetch_from_timescaledb(trade.entry_time)
    
    # Compute HTF structure (reuse existing extractors)
    htf = HTFProjectionExtractor().compute(candles)
    
    # Detect PD arrays (reuse existing extractors)
    pd_arrays = ZoneFeatureExtractor().extract(candles)
    
    # Classify time window (reuse existing extractors)
    time_window = TimeWindowClassifier().classify(trade.entry_time)
    
    # Generate narrative
    narrative = generate_narrative(trade, htf, pd_arrays, time_window)
    
    # Build enriched document
    enriched_setup = {
        "trade_id": trade.id,
        "timestamp": trade.entry_time,
        "htf_structure": htf,
        "pd_arrays": pd_arrays,
        "time_window": time_window,
        "narrative": narrative,
        "outcome": trade.outcome
    }
```

### 2. Embedding Generation

**Script**: `scripts/rag/generate_embeddings.py`

**Models**:
- Narrative: `sentence-transformers/all-MiniLM-L6-v2`
- Structured: Custom autoencoder (trained on feature vectors)
- Temporal: Cyclical encoding (sin/cos transforms)

**Process**:
```python
def generate_embedding(setup):
    # Narrative embedding
    narrative_emb = sbert_model.encode(setup['narrative'])  # 384-dim
    
    # Structured embedding
    features = extract_structured_features(setup)  # 64 features
    structured_emb = autoencoder.encode(features)  # 128-dim
    
    # Temporal embedding
    temporal_emb = encode_temporal(setup['timestamp'])  # 16-dim
    
    # Combine
    combined = np.concatenate([
        narrative_emb * 0.4,
        structured_emb * 0.4,
        temporal_emb * 0.2
    ])  # 528-dim
    
    return combined
```

### 3. Vector Store Schema

**Collection**: `trading_setups`  
**Vector Size**: 528  
**Distance Metric**: Cosine

**Payload Structure**:
```json
{
  "trade_id": "TRD-001",
  "timestamp": "2024-03-15T09:15:00Z",
  "instrument": "EURUSD",
  "time_window": "LONDON_KILLZONE",
  "htf_open_bias": "BULLISH",
  "confluence_count": 5,
  "outcome_result": "WIN",
  "outcome_r_multiple": 4.2,
  "narrative": "Price swept Asian low...",
  "full_setup": { /* complete setup object */ }
}
```

**Indexes**: instrument, time_window, htf_open_bias, outcome_result

### 4. RAG Service API

**Service**: `services/rag-engine/main.py`  
**Framework**: FastAPI  
**Port**: 8003

**Endpoints**:

```python
POST /rag/retrieve
Request:
{
  "instrument": "EURUSD",
  "timestamp": "2024-05-06T09:15:00Z",
  "time_window": "LONDON_KILLZONE",
  "htf_open_bias": "BULLISH",
  "narrative": "Price swept Asian low...",
  "htf_structure": {...},
  "pd_arrays": {...},
  "confluence_factors": [...]
}

Response:
{
  "similar_setups": [
    {
      "setup": {...},
      "similarity_score": 0.94,
      "final_score": 0.97,
      "r_multiple": 4.2,
      "timestamp": "2024-03-15",
      "narrative": "..."
    }
  ],
  "rag_metrics": {
    "avg_r_multiple_similar": 3.6,
    "win_rate_similar": 0.85,
    "sample_size": 5,
    "max_similarity_score": 0.94
  },
  "query_time_ms": 45.2
}
```

```python
POST /rag/ingest
Request:
{
  "setup": { /* enriched setup */ },
  "embedding": [0.023, -0.145, ...]
}

Response:
{
  "status": "success",
  "setup_id": "uuid"
}
```

```python
GET /health
Response:
{
  "status": "healthy",
  "service": "rag-engine",
  "vector_store": "connected",
  "setup_count": 1247
}
```

### 5. ML Integration

**Confluence Scorer v2**: `ml/models/confluence_scorer/train_with_rag.py`

**Augmented Features**:
```python
# Original features (from Phase 1)
original_features = [
    htf_high_proximity_pct,
    htf_low_proximity_pct,
    htf_body_pct,
    # ... 60 more features
]

# RAG features (new)
rag_features = [
    avg_r_multiple_similar,
    win_rate_similar,
    sample_size / 100.0,  # normalized
    max_similarity_score
]

# Combined
combined_features = np.concatenate([original_features, rag_features])
```

**Training Process**:
1. For each training example, call RAG service to get similar setups
2. Compute RAG metrics
3. Append to feature vector
4. Train XGBoost with augmented features
5. Save as `confluence-scorer-v2-rag`

### 6. LLM Integration

**Service**: `services/nlp/llm_service.py`

**Function**: `generate_trade_reasoning_with_rag()`

**Process**:
```python
async def generate_trade_reasoning_with_rag(setup, rag_client):
    # Retrieve similar setups
    rag_response = await rag_client.retrieve(setup)
    similar = rag_response['similar_setups'][:3]
    
    # Build context
    context = format_similar_setups_for_llm(similar)
    
    # LLM prompt
    prompt = f"""
    Current Setup: {setup['narrative']}
    
    Similar Historical Setups:
    {context}
    
    Generate reasoning using 3-question framework...
    """
    
    # Generate with Claude
    reasoning = await claude_api.generate(prompt)
    
    return reasoning
```

---

## Data Flow

### Setup Ingestion Flow
```
Trade Close
    ↓
[Enrich with HTF/PD arrays] (reuse existing extractors)
    ↓
[Generate Narrative]
    ↓
[Generate Embedding]
    ↓
[Ingest to Qdrant]
    ↓
Available for Retrieval
```

### Retrieval Flow
```
Current Setup Detected
    ↓
[Generate Query Embedding]
    ↓
[Metadata Filtering] (instrument, time window, HTF bias)
    ↓
[Vector Search] (top-10)
    ↓
[Re-Ranking] (outcome + recency + confluence)
    ↓
[Top-5 Selection]
    ↓
[Compute RAG Metrics]
    ↓
Return to Confluence Scorer + LLM
```

---

## Technology Stack

| Component | Technology | Version |
|-----------|-----------|---------|
| Vector Store | Qdrant | latest |
| Embedding Model | Sentence-BERT | all-MiniLM-L6-v2 |
| RAG Service | FastAPI | 0.115+ |
| LLM | Claude API | claude-3-sonnet |
| Client Library | qdrant-client | 1.7+ |
| Embedding Library | sentence-transformers | 2.6+ |

---

## Deployment Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Docker Compose                        │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │
│  │   Qdrant     │  │  RAG Service │  │  ML Service  │ │
│  │  Port: 6333  │  │  Port: 8003  │  │  Port: 8002  │ │
│  └──────────────┘  └──────────────┘  └──────────────┘ │
│                                                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │
│  │ TimescaleDB  │  │   MongoDB    │  │    Redis     │ │
│  │  Port: 5432  │  │  Port: 27017 │  │  Port: 6379  │ │
│  └──────────────┘  └──────────────┘  └──────────────┘ │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

---

## Monitoring & Observability

### Metrics to Track
- Retrieval latency (p50, p95, p99)
- Retrieval accuracy (similarity → outcome correlation)
- RAG feature impact on confidence scores
- User engagement with similar setups panel
- Vector store size and query performance

### Logging
- All retrieval requests with query parameters
- Retrieved setup IDs and similarity scores
- RAG metrics computed
- Errors and fallbacks

### Alerting
- Retrieval latency > 200ms
- Vector store connection failures
- Embedding generation failures
- Low similarity scores (< 0.5) for all results

---

## Security Considerations

- Vector store accessible only from internal network
- No PII in embeddings or narratives
- API authentication via JWT (same as other services)
- Rate limiting on retrieval endpoint (100 req/min per user)

---

## Performance Targets

| Metric | Target | Measurement |
|--------|--------|-------------|
| Retrieval Latency (p50) | < 50ms | Prometheus histogram |
| Retrieval Latency (p95) | < 100ms | Prometheus histogram |
| Embedding Generation | < 500ms | Application logs |
| Real-time Ingestion | < 60s | End-to-end timing |
| Similarity Correlation | r > 0.5 | Offline analysis |
| Sharpe Improvement | ≥ 0.1 | Backtest results |

---

## References

- Full Architecture: `docs/RAG_ARCHITECTURE.md`
- Implementation Guide: `docs/RAG_IMPLEMENTATION_GUIDE.md`
- Integration Strategy: `docs/RAG_INTEGRATION_STRATEGY.md`
- System Diagrams: `docs/RAG_SYSTEM_DIAGRAM.md`
