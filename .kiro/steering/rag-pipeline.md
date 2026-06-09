# AlgoRAG Pipeline

## What It Is
AlgoRAG augments the ML pipeline with contextual intelligence by retrieving similar historical trading setups using vector embeddings. It is **additive, not a replacement** — the system must degrade gracefully when RAG is unavailable.

## Architecture
```
EnrichedSetup → EmbeddingGenerator → Qdrant (port 6333)
                                          ↓
CurrentSetup → QueryEmbedding → Filter → Search → Re-rank → RAGMetrics
                                                            ↓
                                          Confluence Scorer v2 + LLM Reasoning
```

## Embedding Strategy (528-dim combined vector)
| Component | Dimensions | Weight | Model |
|---|---|---|---|
| Narrative | 384 | 40% | `sentence-transformers/all-MiniLM-L6-v2` |
| Structured features | 128 | 40% | Custom (64 features → 128-dim) |
| Temporal | 16 | 20% | Cyclical sin/cos encoding |

Combined via weighted concatenation:
```python
combined = np.concatenate([
    narrative_emb * 0.4,    # 384-dim
    structured_emb * 0.4,   # 128-dim
    temporal_emb * 0.2,     # 16-dim
])  # → 528-dim
```

**Invariants to enforce in tests:**
- Output is always exactly 528-dim
- No NaN values
- Same input always produces same output (determinism)

## Structured Feature Vector (64 features)
Extracted from `EnrichedSetup` fields:
- **HTF metrics** (4): `htf_high_proximity_pct`, `htf_low_proximity_pct`, `htf_body_pct`, `htf_close_position`
- **HTF bias** (3): one-hot of BULLISH / BEARISH / NEUTRAL
- **PD array flags** (4): `bos_detected`, `choch_detected`, `fvg_present`, `liquidity_sweep`
- **Swing distances** (2): `swing_high_distance`, `swing_low_distance`
- **Session features** (2): `time_window_weight`, `is_killzone`
- **Outcome** (2): `r_multiple`, one-hot WIN/LOSS
- **Confluence** (1): `confluence_count`
- Remaining features padded/derived to reach 64 total
- All features normalised to `[0, 1]` range before encoding

## Temporal Encoding (16-dim)
Cyclical sin/cos encoding captures periodicity without ordinal bias:
```python
hour_sin   = sin(2π * hour / 24)       # dim 0
hour_cos   = cos(2π * hour / 24)       # dim 1
dow_sin    = sin(2π * day_of_week / 5) # dim 2
dow_cos    = cos(2π * day_of_week / 5) # dim 3
month_sin  = sin(2π * month / 12)      # dim 4
month_cos  = cos(2π * month / 12)      # dim 5
# dims 6–15: zeros (reserved for future features)
```

## Retrieval Pipeline (Filter → Search → Re-rank → Top-5)
1. **Metadata filter**: instrument, time_window, htf_open_bias, outcome_result=WIN
2. **Vector search**: cosine similarity, top-10 candidates from Qdrant
3. **Re-ranking score**:
   ```
   final_score = 0.5 * outcome_quality
               + 0.3 * recency_score      # exponential decay, 90-day half-life
               + 0.2 * confluence_overlap
   ```
4. **Diversity filter**: max 3 setups from the same calendar day
5. **Return top-5**

## RAG Metrics (computed from top-5 results)
```python
# services/algorag/models.py → RAGMetrics
avg_r_multiple_similar: float
win_rate_similar: float        # in [0.0, 1.0]
sample_size: int               # min 3 for statistical validity
max_similarity_score: float    # in [0.0, 1.0]
avg_confluence_count: float
```
Minimum `sample_size = 3` before metrics are considered statistically valid.

## AlgoRAG Service (services/algorag/)
- **Framework**: FastAPI, port 8003
- **Key files**:
  - `main.py` — FastAPI app, endpoint routing
  - `config.py` — Settings dataclass (QdrantConfig, ServiceConfig)
  - `models.py` — Pydantic models (RetrievalRequest, RetrievalResponse, IngestionRequest, etc.)
  - `qdrant_client.py` — Qdrant connection wrapper with retry logic
- **Endpoints**:
  - `POST /rag/retrieve` — query similar setups
  - `POST /rag/ingest` — store new enriched setup + embedding
  - `GET /health` — returns status, vector_store connectivity, setup_count

## Qdrant Collection Schema
- **Collection name**: `trading_setups`
- **Vector size**: 528
- **Distance metric**: Cosine
- **Payload fields**: `trade_id`, `timestamp`, `instrument`, `time_window`, `htf_open_bias`, `confluence_count`, `outcome_result`, `outcome_r_multiple`, `narrative`, `full_setup`
- **Indexed fields** (for fast filtering): `instrument`, `time_window`, `htf_open_bias`, `outcome_result`

## Graceful Degradation
Any code calling the RAG service must handle failure silently:
```python
try:
    rag_response = await rag_client.retrieve(setup)
    rag_features = extract_rag_features(rag_response)
except Exception:
    rag_features = [0.0, 0.0, 0.0, 0.0]  # neutral fallback
```
The ML pipeline and LLM reasoning must work without RAG. Never let RAG failures propagate to the trading loop.

## Performance Targets
| Metric | Target |
|---|---|
| Retrieval latency p50 | < 50ms |
| Retrieval latency p95 | < 100ms |
| Embedding generation | < 500ms per setup |
| Real-time ingestion | < 60s from trade close to indexed |
| Similarity → outcome correlation | r > 0.5 |

## Data Preparation Scripts (scripts/rag/)
- `prepare_historical_setups.py` — loads trades, enriches via `SetupEnricher`, saves to `data/enriched_setups.json`
- `utils/setup_enricher.py` — `SetupEnricher` class + `EnrichedSetup` Pydantic model
- `utils/narrative_generator.py` — `NarrativeGenerator` (template-based, ICT 3-question framework)
- Tests live in `scripts/rag/tests/`

## ML Integration (Confluence Scorer v2)
RAG adds 4 new features to the confluence scorer feature vector:
```python
rag_features = [
    avg_r_multiple_similar,
    win_rate_similar,
    sample_size / 100.0,   # normalised
    max_similarity_score,
]
combined_features = np.concatenate([original_features, rag_features])
```
Model saved as `confluence-scorer-v2-rag` in MLflow registry. Requires Sharpe improvement ≥ 0.1 vs baseline before promotion.
