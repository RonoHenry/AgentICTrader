# RAG Implementation Guide - Practical Steps

## Quick Start: Build Your First RAG Prototype

This guide walks you through implementing a minimal viable RAG system for AgentICTrader in **2-3 weeks**.

---

## Week 1: Data Preparation & Vector Store Setup

### Day 1-2: Extract & Enrich Historical Setups

**Goal**: Transform trade journal entries into RAG-ready documents

**Script**: `scripts/rag/prepare_historical_setups.py`

```python
"""
Extract historical setups from trade journal and enrich with context.
"""

import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime, timedelta
import pandas as pd

async def enrich_trade_with_context(trade, timescaledb_conn):
    """
    Enrich a single trade with HTF structure, PD arrays, time windows.
    """
    entry_time = trade['entry']['time']
    instrument = trade['instrument']
    
    # 1. Fetch historical candles around entry time
    candles = await fetch_candles(
        instrument=instrument,
        start_time=entry_time - timedelta(hours=24),
        end_time=entry_time,
        timeframes=['M5', 'H1', 'H4']
    )
    
    # 2. Compute HTF structure
    htf_structure = compute_htf_structure(
        candles=candles,
        entry_time=entry_time,
        entry_price=trade['entry']['price']
    )
    
    # 3. Detect PD arrays
    pd_arrays = detect_pd_arrays(
        candles=candles,
        entry_time=entry_time,
        entry_price=trade['entry']['price']
    )
    
    # 4. Classify time window
    time_window = classify_time_window(entry_time, instrument)
    
    # 5. Extract reference prices
    reference_prices = extract_reference_prices(
        candles=candles,
        entry_time=entry_time
    )
    
    # 6. Compute confluence factors
    confluence_factors = compute_confluence(
        htf_structure=htf_structure,
        pd_arrays=pd_arrays,
        time_window=time_window
    )
    
    # 7. Generate narrative
    narrative = generate_narrative(
        trade=trade,
        htf_structure=htf_structure,
        pd_arrays=pd_arrays,
        time_window=time_window,
        reference_prices=reference_prices
    )
    
    # 8. Build enriched document
    enriched_setup = {
        "trade_id": trade['trade_id'],
        "timestamp": entry_time.isoformat(),
        "instrument": instrument,
        "time_window": time_window['name'],
        "narrative_phase": time_window['phase'],
        "htf_structure": htf_structure,
        "pd_arrays": pd_arrays,
        "reference_prices": reference_prices,
        "confluence_factors": confluence_factors,
        "confluence_count": len(confluence_factors),
        "entry_price": trade['entry']['price'],
        "direction": trade['direction'],
        "stop_loss": trade['risk']['stop_loss'],
        "take_profit": trade['risk']['take_profit'],
        "r_ratio": trade['risk']['r_ratio'],
        "outcome": trade['outcome'],
        "narrative": narrative
    }
    
    return enriched_setup


async def main():
    # Connect to MongoDB
    mongo_client = AsyncIOMotorClient("mongodb://localhost:27017")
    db = mongo_client.agentictrader
    
    # Fetch all closed trades
    trades = await db.trade_journal.find({
        "status": "CLOSED",
        "outcome.result": {"$in": ["WIN", "LOSS"]}
    }).to_list(length=None)
    
    print(f"Found {len(trades)} closed trades")
    
    # Enrich each trade
    enriched_setups = []
    for i, trade in enumerate(trades, 1):
        print(f"Enriching trade {i}/{len(trades)}: {trade['trade_id']}")
        try:
            enriched = await enrich_trade_with_context(trade, timescaledb_conn)
            enriched_setups.append(enriched)
        except Exception as e:
            print(f"Error enriching {trade['trade_id']}: {e}")
    
    # Save to JSON for inspection
    import json
    with open('data/enriched_setups.json', 'w') as f:
        json.dump(enriched_setups, f, indent=2, default=str)
    
    print(f"Enriched {len(enriched_setups)} setups")
    print(f"Saved to data/enriched_setups.json")

if __name__ == "__main__":
    asyncio.run(main())
```

**Output**: `data/enriched_setups.json` with 500+ enriched setups

---

### Day 3-4: Generate Embeddings

**Script**: `scripts/rag/generate_embeddings.py`

```python
"""
Generate embeddings for enriched setups.
"""

from sentence_transformers import SentenceTransformer
import numpy as np
import json
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA

# Load models
narrative_model = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')

def generate_narrative_embedding(narrative):
    """Generate 384-dim embedding from narrative text."""
    return narrative_model.encode(narrative, convert_to_numpy=True)

def generate_structured_embedding(setup):
    """Generate 128-dim embedding from structured features."""
    features = [
        # Time window (one-hot encoded)
        1 if setup['time_window'] == 'LONDON_KILLZONE' else 0,
        1 if setup['time_window'] == 'NY_AM_KILLZONE' else 0,
        # ... other time windows
        
        # HTF structure
        setup['htf_structure']['htf_high_proximity_pct'] / 100.0,
        setup['htf_structure']['htf_low_proximity_pct'] / 100.0,
        setup['htf_structure']['htf_body_pct'] / 100.0,
        
        # PD arrays (binary flags)
        1 if 'FVG' in setup['pd_arrays'] else 0,
        1 if 'LIQUIDITY_SWEEP' in setup['pd_arrays'] else 0,
        1 if 'ORDER_BLOCK' in setup['pd_arrays'] else 0,
        
        # Confluence
        setup['confluence_count'] / 10.0,
        
        # ... more features (total: 64)
    ]
    
    # Normalize and reduce dimensionality
    features = np.array(features).reshape(1, -1)
    # Apply PCA (pre-fitted on training data)
    reduced = pca_model.transform(features)
    return reduced[0]  # 128-dim

def generate_temporal_embedding(timestamp):
    """Generate 16-dim cyclical temporal embedding."""
    dt = datetime.fromisoformat(timestamp)
    
    hour = dt.hour + dt.minute / 60.0
    day_of_week = dt.weekday()
    
    return np.array([
        np.sin(2 * np.pi * hour / 24),
        np.cos(2 * np.pi * hour / 24),
        np.sin(2 * np.pi * day_of_week / 7),
        np.cos(2 * np.pi * day_of_week / 7),
        # ... more temporal features (total: 16)
    ])

def generate_combined_embedding(setup):
    """Generate final 528-dim embedding."""
    narrative_emb = generate_narrative_embedding(setup['narrative'])
    structured_emb = generate_structured_embedding(setup)
    temporal_emb = generate_temporal_embedding(setup['timestamp'])
    
    # Combine with weights
    combined = np.concatenate([
        narrative_emb * 0.4,      # 384-dim
        structured_emb * 0.4,     # 128-dim
        temporal_emb * 0.2        # 16-dim
    ])
    
    return combined  # 528-dim

def main():
    # Load enriched setups
    with open('data/enriched_setups.json', 'r') as f:
        setups = json.load(f)
    
    print(f"Generating embeddings for {len(setups)} setups...")
    
    # Generate embeddings
    for i, setup in enumerate(setups, 1):
        print(f"Processing {i}/{len(setups)}: {setup['trade_id']}")
        
        embedding = generate_combined_embedding(setup)
        setup['embedding'] = embedding.tolist()
    
    # Save with embeddings
    with open('data/setups_with_embeddings.json', 'w') as f:
        json.dump(setups, f, indent=2)
    
    print(f"Saved {len(setups)} setups with embeddings")

if __name__ == "__main__":
    main()
```

---

### Day 5: Deploy Qdrant Vector Store

**Docker Compose**: Add to `docker/docker-compose.yml`

```yaml
  qdrant:
    image: qdrant/qdrant:latest
    container_name: agentictrader_qdrant
    ports:
      - "6333:6333"
      - "6334:6334"
    volumes:
      - qdrant_storage:/qdrant/storage
    environment:
      - QDRANT__SERVICE__GRPC_PORT=6334
    networks:
      - agentictrader_network
    restart: unless-stopped

volumes:
  qdrant_storage:
```

**Start Qdrant**:
```bash
docker compose up -d qdrant
```

**Verify**:
```bash
curl http://localhost:6333/collections
```

---

### Day 6-7: Ingest Data into Qdrant

**Script**: `scripts/rag/ingest_to_qdrant.py`

```python
"""
Ingest enriched setups with embeddings into Qdrant.
"""

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
import json
from uuid import uuid4

def create_collection(client):
    """Create Qdrant collection for trading setups."""
    client.create_collection(
        collection_name="trading_setups",
        vectors_config=VectorParams(
            size=528,
            distance=Distance.COSINE
        )
    )
    print("Created collection: trading_setups")

def ingest_setups(client, setups):
    """Bulk insert setups into Qdrant."""
    points = []
    
    for setup in setups:
        point = PointStruct(
            id=str(uuid4()),
            vector=setup['embedding'],
            payload={
                "trade_id": setup['trade_id'],
                "timestamp": setup['timestamp'],
                "instrument": setup['instrument'],
                "time_window": setup['time_window'],
                "narrative_phase": setup['narrative_phase'],
                "htf_open_bias": setup['htf_structure']['htf_open_bias'],
                "confluence_count": setup['confluence_count'],
                "confluence_factors": setup['confluence_factors'],
                "outcome_result": setup['outcome']['result'],
                "outcome_r_multiple": setup['outcome']['r_multiple'],
                "outcome_pnl": setup['outcome']['pnl_usd'],
                "narrative": setup['narrative'],
                # Store full setup for retrieval
                "full_setup": setup
            }
        )
        points.append(point)
    
    # Batch insert
    client.upsert(
        collection_name="trading_setups",
        points=points
    )
    
    print(f"Ingested {len(points)} setups")

def main():
    # Connect to Qdrant
    client = QdrantClient(host="localhost", port=6333)
    
    # Create collection
    try:
        create_collection(client)
    except Exception as e:
        print(f"Collection may already exist: {e}")
    
    # Load setups with embeddings
    with open('data/setups_with_embeddings.json', 'r') as f:
        setups = json.load(f)
    
    # Ingest
    ingest_setups(client, setups)
    
    # Verify
    collection_info = client.get_collection("trading_setups")
    print(f"Collection info: {collection_info}")

if __name__ == "__main__":
    main()
```

---

## Week 2: RAG Service Implementation

### Day 8-10: Build RAG FastAPI Service

**Service**: `services/rag-engine/main.py`

```python
"""
RAG Engine FastAPI Service
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer
import numpy as np
from typing import List, Dict, Any, Optional
from datetime import datetime

app = FastAPI(title="RAG Engine")

# Initialize clients
qdrant_client = QdrantClient(host="localhost", port=6333)
narrative_model = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')

class CurrentSetup(BaseModel):
    """Current market setup for retrieval."""
    instrument: str
    timestamp: str
    time_window: str
    htf_open_bias: str
    narrative: str
    htf_structure: Dict[str, Any]
    pd_arrays: Dict[str, Any]
    confluence_factors: List[str]
    confluence_count: int

class RetrievalResponse(BaseModel):
    """Response from RAG retrieval."""
    similar_setups: List[Dict[str, Any]]
    rag_metrics: Dict[str, float]
    query_time_ms: float

def generate_query_embedding(setup: CurrentSetup) -> np.ndarray:
    """Generate query embedding from current setup."""
    # Narrative embedding
    narrative_emb = narrative_model.encode(setup.narrative, convert_to_numpy=True)
    
    # Structured embedding (simplified for example)
    structured_features = [
        setup.htf_structure.get('htf_high_proximity_pct', 0) / 100.0,
        setup.htf_structure.get('htf_low_proximity_pct', 0) / 100.0,
        setup.confluence_count / 10.0,
        # ... more features
    ]
    structured_emb = np.array(structured_features[:128])  # Pad/truncate to 128
    
    # Temporal embedding
    dt = datetime.fromisoformat(setup.timestamp)
    hour = dt.hour + dt.minute / 60.0
    temporal_emb = np.array([
        np.sin(2 * np.pi * hour / 24),
        np.cos(2 * np.pi * hour / 24),
        # ... more temporal features
    ])
    temporal_emb = np.pad(temporal_emb, (0, 16 - len(temporal_emb)))  # Pad to 16
    
    # Combine
    combined = np.concatenate([
        narrative_emb * 0.4,
        structured_emb * 0.4,
        temporal_emb * 0.2
    ])
    
    return combined

def rerank_results(results: List[Any], current_setup: CurrentSetup) -> List[Dict[str, Any]]:
    """Re-rank retrieved results by outcome quality, recency, confluence."""
    reranked = []
    
    for result in results:
        payload = result.payload
        base_score = result.score
        
        # R-multiple boost
        r_multiple = payload.get('outcome_r_multiple', 0)
        r_boost = min(r_multiple / 5.0, 1.0) * 0.2
        
        # Recency boost
        setup_date = datetime.fromisoformat(payload['timestamp'])
        days_old = (datetime.now() - setup_date).days
        recency_boost = np.exp(-days_old / 90) * 0.15
        
        # Confluence overlap boost
        setup_confluence = set(payload.get('confluence_factors', []))
        current_confluence = set(current_setup.confluence_factors)
        overlap = len(setup_confluence & current_confluence)
        confluence_boost = (overlap / 5.0) * 0.15
        
        final_score = base_score + r_boost + recency_boost + confluence_boost
        
        reranked.append({
            "setup": payload['full_setup'],
            "similarity_score": base_score,
            "final_score": final_score,
            "r_multiple": r_multiple,
            "timestamp": payload['timestamp'],
            "narrative": payload['narrative']
        })
    
    # Sort by final score
    reranked.sort(key=lambda x: x['final_score'], reverse=True)
    
    return reranked

def compute_rag_metrics(similar_setups: List[Dict[str, Any]]) -> Dict[str, float]:
    """Compute aggregate metrics from retrieved setups."""
    if not similar_setups:
        return {
            "avg_r_multiple_similar": 0.0,
            "win_rate_similar": 0.0,
            "sample_size": 0,
            "max_similarity_score": 0.0
        }
    
    r_multiples = [s['r_multiple'] for s in similar_setups]
    wins = [s for s in similar_setups if s['setup']['outcome']['result'] == 'WIN']
    
    return {
        "avg_r_multiple_similar": np.mean(r_multiples),
        "win_rate_similar": len(wins) / len(similar_setups),
        "sample_size": len(similar_setups),
        "max_similarity_score": similar_setups[0]['similarity_score'] if similar_setups else 0.0,
        "avg_confluence_count": np.mean([s['setup']['confluence_count'] for s in similar_setups])
    }

@app.post("/rag/retrieve", response_model=RetrievalResponse)
async def retrieve_similar_setups(setup: CurrentSetup):
    """Retrieve similar historical setups."""
    import time
    start_time = time.time()
    
    try:
        # Generate query embedding
        query_vector = generate_query_embedding(setup)
        
        # Search with metadata filters
        results = qdrant_client.search(
            collection_name="trading_setups",
            query_vector=query_vector.tolist(),
            query_filter={
                "must": [
                    {"key": "instrument", "match": {"value": setup.instrument}},
                    {"key": "time_window", "match": {"value": setup.time_window}},
                    {"key": "htf_open_bias", "match": {"value": setup.htf_open_bias}},
                    {"key": "outcome_result", "match": {"value": "WIN"}}
                ]
            },
            limit=10
        )
        
        # Re-rank
        reranked = rerank_results(results, setup)
        
        # Take top 5
        top_5 = reranked[:5]
        
        # Compute metrics
        rag_metrics = compute_rag_metrics(top_5)
        
        query_time = (time.time() - start_time) * 1000  # ms
        
        return RetrievalResponse(
            similar_setups=top_5,
            rag_metrics=rag_metrics,
            query_time_ms=query_time
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "rag-engine"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8003)
```

**Run**:
```bash
cd services/rag-engine
uvicorn main:app --port 8003 --reload
```

**Test**:
```bash
curl -X POST http://localhost:8003/rag/retrieve \
  -H "Content-Type: application/json" \
  -d '{
    "instrument": "EURUSD",
    "timestamp": "2024-05-06T09:15:00Z",
    "time_window": "LONDON_KILLZONE",
    "htf_open_bias": "BULLISH",
    "narrative": "Price swept Asian low during London Killzone",
    "htf_structure": {"htf_high_proximity_pct": 68.5},
    "pd_arrays": {"FVG": true},
    "confluence_factors": ["HTF_BULLISH", "FVG_RESPECTED"],
    "confluence_count": 5
  }'
```

---

## Week 3: Integration & Testing

### Day 11-12: Integrate with Confluence Scorer

**Update**: `ml/models/confluence_scorer/train.py`

Add RAG features to training data:

```python
# Fetch RAG metrics for each training example
rag_metrics = await rag_client.retrieve(setup)

# Add to feature vector
features = np.concatenate([
    original_features,
    [
        rag_metrics['avg_r_multiple_similar'],
        rag_metrics['win_rate_similar'],
        rag_metrics['sample_size'] / 100.0,  # Normalize
        rag_metrics['max_similarity_score']
    ]
])
```

Retrain model with augmented features.

---

### Day 13-14: Integrate with LLM Reasoning

**Update**: `services/nlp/llm_service.py`

```python
async def generate_trade_reasoning_with_rag(setup: dict, rag_client):
    """Generate reasoning using RAG-retrieved examples."""
    
    # Retrieve similar setups
    similar = await rag_client.retrieve(setup)
    
    # Build context
    context = ""
    for i, s in enumerate(similar['similar_setups'][:3], 1):
        context += f"""
        Example {i} ({s['timestamp'][:10]}):
        {s['narrative']}
        Outcome: {s['r_multiple']}R
        """
    
    # LLM prompt
    prompt = f"""
    Current Setup: {setup['narrative']}
    
    Similar Historical Setups:
    {context}
    
    Generate reasoning using 3-question framework...
    """
    
    reasoning = await claude_api.generate(prompt)
    return reasoning
```

---

### Day 15-17: Testing & Validation

**Backtesting Script**: `scripts/rag/backtest_rag.py`

```python
"""
Backtest RAG-augmented system vs. baseline.
"""

async def backtest_with_rag(test_setups):
    """Run backtest with RAG augmentation."""
    results = []
    
    for setup in test_setups:
        # Get ML prediction
        ml_confidence = ml_model.predict(setup)
        
        # Get RAG metrics
        rag_metrics = await rag_client.retrieve(setup)
        
        # Augmented confidence
        augmented_confidence = confluence_scorer.predict(
            features=setup_features + rag_metrics
        )
        
        # Compare
        results.append({
            "setup_id": setup['id'],
            "ml_confidence": ml_confidence,
            "augmented_confidence": augmented_confidence,
            "actual_outcome": setup['outcome'],
            "rag_sample_size": rag_metrics['sample_size'],
            "rag_win_rate": rag_metrics['win_rate_similar']
        })
    
    return results

# Run backtest
results = await backtest_with_rag(test_setups)

# Compute metrics
baseline_sharpe = compute_sharpe(results, use_ml_only=True)
rag_sharpe = compute_sharpe(results, use_rag=True)

print(f"Baseline Sharpe: {baseline_sharpe:.3f}")
print(f"RAG-Augmented Sharpe: {rag_sharpe:.3f}")
print(f"Improvement: {rag_sharpe - baseline_sharpe:.3f}")
```

---

## Success Checklist

- [ ] 500+ historical setups enriched and ingested
- [ ] Qdrant running and indexed
- [ ] RAG service responds in < 100ms
- [ ] Similar setups retrieved correctly
- [ ] RAG metrics computed accurately
- [ ] Confluence Scorer retrained with RAG features
- [ ] LLM reasoning cites actual examples
- [ ] Backtest shows Sharpe improvement ≥ 0.1
- [ ] Dashboard displays similar setups

---

## Next Steps

1. **Production Deployment**: Deploy RAG service to production
2. **Monitoring**: Track retrieval quality, latency, impact on decisions
3. **Continuous Improvement**: Add new setups daily, refine embeddings
4. **Advanced Features**: Chart image embeddings, regime-aware retrieval

---

## Troubleshooting

### Issue: Retrieval returns no results
**Solution**: Check metadata filters are not too restrictive. Relax filters or expand historical data.

### Issue: Embeddings don't cluster well
**Solution**: Fine-tune sentence-transformer on trading narratives. Adjust embedding weights.

### Issue: RAG metrics don't improve performance
**Solution**: Verify similar setups are actually similar. Check re-ranking logic. Increase sample size.

---

## Resources

- Qdrant Documentation: https://qdrant.tech/documentation/
- Sentence-Transformers: https://www.sbert.net/
- RAG Best Practices: https://www.pinecone.io/learn/retrieval-augmented-generation/
