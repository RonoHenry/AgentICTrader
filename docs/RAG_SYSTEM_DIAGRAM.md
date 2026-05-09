# RAG System Architecture Diagrams

## 1. High-Level System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     AGENTICTRADER PLATFORM                       │
└─────────────────────────────────────────────────────────────────┘

┌──────────────────┐
│  Market Data     │
│  (Real-time)     │
└────────┬─────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────┐
│                    FEATURE ENGINEERING                           │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │ HTF Selector │  │ PD Array     │  │ Time Window  │         │
│  │ (3-Tier)     │  │ Detector     │  │ Classifier   │         │
│  └──────────────┘  └──────────────┘  └──────────────┘         │
└────────┬────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────┐
│                    INTELLIGENCE LAYER                            │
│                                                                  │
│  ┌────────────────────────────────────────────────────────┐    │
│  │              ML PIPELINE (Existing)                     │    │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │    │
│  │  │   Regime     │  │   Pattern    │  │  Confluence  │ │    │
│  │  │ Classifier   │  │   Detector   │  │   Scorer     │ │    │
│  │  │  (XGBoost)   │  │  (XGBoost)   │  │  (XGBoost)   │ │    │
│  │  └──────────────┘  └──────────────┘  └──────┬───────┘ │    │
│  └────────────────────────────────────────────────┼────────┘    │
│                                                   │              │
│  ┌────────────────────────────────────────────────┼────────┐    │
│  │              RAG ENGINE (New)                  │        │    │
│  │                                                │        │    │
│  │  ┌──────────────────────────────────────────┐ │        │    │
│  │  │         EMBEDDING GENERATOR              │ │        │    │
│  │  │  ┌────────────┐  ┌────────────┐         │ │        │    │
│  │  │  │ Narrative  │  │ Structured │         │ │        │    │
│  │  │  │ Embedding  │  │  Feature   │         │ │        │    │
│  │  │  │ (SBERT)    │  │ Embedding  │         │ │        │    │
│  │  │  └────────────┘  └────────────┘         │ │        │    │
│  │  └──────────────────────────────────────────┘ │        │    │
│  │                      │                         │        │    │
│  │                      ▼                         │        │    │
│  │  ┌──────────────────────────────────────────┐ │        │    │
│  │  │         VECTOR STORE (Qdrant)            │ │        │    │
│  │  │                                          │ │        │    │
│  │  │  ┌────────────────────────────────────┐ │ │        │    │
│  │  │  │  Historical Setups (500-2000+)     │ │ │        │    │
│  │  │  │  - Embeddings (528-dim)            │ │ │        │    │
│  │  │  │  - Metadata (time, HTF, PD arrays) │ │ │        │    │
│  │  │  │  - Outcomes (R-multiple, win/loss) │ │ │        │    │
│  │  │  └────────────────────────────────────┘ │ │        │    │
│  │  └──────────────────────────────────────────┘ │        │    │
│  │                      │                         │        │    │
│  │                      ▼                         │        │    │
│  │  ┌──────────────────────────────────────────┐ │        │    │
│  │  │      RETRIEVAL & RE-RANKING              │ │        │    │
│  │  │  - Metadata filtering                    │ │        │    │
│  │  │  - Vector similarity search              │ │        │    │
│  │  │  - Outcome-based re-ranking              │ │        │    │
│  │  └──────────────────────────────────────────┘ │        │    │
│  │                      │                         │        │    │
│  │                      ▼                         │        │    │
│  │  ┌──────────────────────────────────────────┐ │        │    │
│  │  │      RAG METRICS                         │ │        │    │
│  │  │  - avg_r_multiple_similar: 3.6           │ │        │    │
│  │  │  - win_rate_similar: 0.85                │ │        │    │
│  │  │  - sample_size: 12                       │ │        │    │
│  │  │  - max_similarity: 0.94                  │ │        │    │
│  │  └──────────────────────────────────────────┘ │        │    │
│  └────────────────────────────────────────────────┼────────┘    │
│                                                   │              │
│                      ┌────────────────────────────┘              │
│                      │                                           │
│                      ▼                                           │
│  ┌────────────────────────────────────────────────────────┐    │
│  │         AUGMENTED CONFLUENCE SCORER                     │    │
│  │  Input: ML features + RAG metrics                       │    │
│  │  Output: Enhanced confidence score (0.0-1.0)            │    │
│  └────────────────────────────────────────────────────────┘    │
└────────┬─────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────┐
│                    LLM REASONING GENERATOR                       │
│  Input: Current setup + Retrieved similar setups                │
│  Output: Human-readable reasoning (3-question framework)         │
└────────┬─────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────┐
│                    AGENT DECISION NODE                           │
│  - Confidence score: 0.82                                        │
│  - Similar setups: 12 (avg 3.6R, 85% win rate)                  │
│  - Reasoning: "Price swept Asian low during London Killzone..." │
└─────────────────────────────────────────────────────────────────┘
```

---

## 2. RAG Retrieval Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                    CURRENT MARKET SETUP                          │
│  - EURUSD @ 1.0852                                              │
│  - Time: 09:15 UTC (LONDON_KILLZONE)                           │
│  - HTF Bias: BULLISH (price below H4 open)                     │
│  - PD Arrays: FVG + Liquidity Sweep                            │
└────────┬─────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────┐
│              STEP 1: GENERATE QUERY EMBEDDING                    │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  Narrative: "Price swept Asian low during London         │  │
│  │  Killzone. HTF bias bullish. FVG respected at 1.0850."   │  │
│  └────────────────────────┬─────────────────────────────────┘  │
│                           │                                     │
│                           ▼                                     │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  Sentence-BERT Encoding                                  │  │
│  │  → narrative_embedding (384-dim)                         │  │
│  └────────────────────────┬─────────────────────────────────┘  │
│                           │                                     │
│  ┌────────────────────────┴─────────────────────────────────┐  │
│  │  Structured Features:                                     │  │
│  │  - time_window_weight: 0.9                               │  │
│  │  - htf_high_proximity: 68.5%                             │  │
│  │  - confluence_count: 5                                    │  │
│  │  → structured_embedding (128-dim)                        │  │
│  └────────────────────────┬─────────────────────────────────┘  │
│                           │                                     │
│  ┌────────────────────────┴─────────────────────────────────┐  │
│  │  Temporal Features:                                       │  │
│  │  - sin(2π * 9.25 / 24) = 0.707                          │  │
│  │  - cos(2π * 9.25 / 24) = 0.707                          │  │
│  │  → temporal_embedding (16-dim)                           │  │
│  └────────────────────────┬─────────────────────────────────┘  │
│                           │                                     │
│                           ▼                                     │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  Combined Query Vector (528-dim)                         │  │
│  │  = [narrative * 0.4, structured * 0.4, temporal * 0.2]  │  │
│  └──────────────────────────────────────────────────────────┘  │
└────────┬─────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────┐
│              STEP 2: METADATA FILTERING                          │
│                                                                  │
│  Hard Filters (Applied BEFORE vector search):                   │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  ✓ instrument = "EURUSD"                                 │  │
│  │  ✓ time_window = "LONDON_KILLZONE"                       │  │
│  │  ✓ htf_open_bias = "BULLISH"                             │  │
│  │  ✓ outcome.result = "WIN"                                │  │
│  │  ✓ timestamp >= "2024-01-01"  (last 12 months)          │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                  │
│  Candidate Pool: 847 setups → 43 setups after filtering         │
└────────┬─────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────┐
│              STEP 3: VECTOR SIMILARITY SEARCH                    │
│                                                                  │
│  Qdrant ANN Search (Cosine Similarity):                         │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  Top 10 Results:                                         │  │
│  │  1. Setup #1247 (2024-03-15) - similarity: 0.94         │  │
│  │  2. Setup #1089 (2024-02-28) - similarity: 0.91         │  │
│  │  3. Setup #0923 (2024-01-19) - similarity: 0.89         │  │
│  │  4. Setup #1156 (2024-03-08) - similarity: 0.87         │  │
│  │  5. Setup #0845 (2024-01-05) - similarity: 0.85         │  │
│  │  ...                                                     │  │
│  └──────────────────────────────────────────────────────────┘  │
└────────┬─────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────┐
│              STEP 4: RE-RANKING                                  │
│                                                                  │
│  Re-rank by:                                                     │
│  - Outcome quality (R-multiple)                                  │
│  - Recency (exponential decay)                                   │
│  - Confluence similarity                                         │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  Final Top 5:                                            │  │
│  │  1. Setup #1247 (2024-03-15) - score: 0.97              │  │
│  │     R: 4.2, Confluence: 5/5 match                        │  │
│  │  2. Setup #1089 (2024-02-28) - score: 0.93              │  │
│  │     R: 3.1, Confluence: 4/5 match                        │  │
│  │  3. Setup #1156 (2024-03-08) - score: 0.91              │  │
│  │     R: 5.8, Confluence: 4/5 match                        │  │
│  │  4. Setup #0923 (2024-01-19) - score: 0.88              │  │
│  │     R: 2.9, Confluence: 5/5 match                        │  │
│  │  5. Setup #0845 (2024-01-05) - score: 0.84              │  │
│  │     R: 3.4, Confluence: 3/5 match                        │  │
│  └──────────────────────────────────────────────────────────┘  │
└────────┬─────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────┐
│              STEP 5: COMPUTE RAG METRICS                         │
│                                                                  │
│  Aggregate statistics from retrieved setups:                     │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  avg_r_multiple_similar: 3.88                            │  │
│  │  win_rate_similar: 1.00  (5/5 wins)                      │  │
│  │  sample_size: 5                                          │  │
│  │  max_similarity_score: 0.97                              │  │
│  │  avg_confluence_count: 4.2                               │  │
│  │  recency_weighted_win_rate: 1.00                         │  │
│  └──────────────────────────────────────────────────────────┘  │
└────────┬─────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────┐
│              OUTPUT: AUGMENTED FEATURES                          │
│                                                                  │
│  Feed to Confluence Scorer:                                      │
│  - Original ML features (HTF, PD arrays, time window, etc.)     │
│  - RAG metrics (avg R, win rate, similarity, etc.)              │
│                                                                  │
│  Feed to LLM Reasoning Generator:                                │
│  - Current setup details                                         │
│  - Top 3 similar setups with narratives                         │
│  - Aggregate statistics                                          │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. Embedding Space Visualization (Conceptual)

```
                    EMBEDDING SPACE (528-dim, projected to 2D)

                    ┌─────────────────────────────────────┐
                    │                                     │
                    │         LONDON KILLZONE             │
                    │         (BULLISH BIAS)              │
                    │                                     │
                    │    ●  ●                             │
                    │  ●  ●  ●  ← Cluster: FVG + Sweep   │
                    │    ●  ★  ●  (Current Setup)        │
                    │      ●                              │
                    │                                     │
                    │                                     │
                    │                                     │
                    │                                     │
                    │                                     │
                    └─────────────────────────────────────┘

                    ┌─────────────────────────────────────┐
                    │                                     │
                    │         NY AM KILLZONE              │
                    │         (BULLISH BIAS)              │
                    │                                     │
                    │        ●  ●                         │
                    │      ●  ●  ●  ← Different cluster  │
                    │        ●                            │
                    │                                     │
                    │                                     │
                    └─────────────────────────────────────┘

                    ┌─────────────────────────────────────┐
                    │                                     │
                    │         LONDON KILLZONE             │
                    │         (BEARISH BIAS)              │
                    │                                     │
                    │    ●  ●                             │
                    │  ●  ●  ●  ← Separate cluster       │
                    │    ●                                │
                    │                                     │
                    └─────────────────────────────────────┘

Legend:
  ● = Historical setup
  ★ = Current query setup
  
Clusters form naturally based on:
- Time window (London vs. NY)
- HTF bias (Bullish vs. Bearish)
- PD array types (FVG, Sweep, Order Block)
- Confluence factors
```

---

## 4. Data Flow: Historical Setup Ingestion

```
┌─────────────────────────────────────────────────────────────────┐
│                    TRADE JOURNAL (MongoDB)                       │
│  - 500+ closed trades                                           │
│  - Entry/exit prices, outcomes, timestamps                      │
└────────┬─────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────┐
│              ENRICHMENT PIPELINE                                 │
│                                                                  │
│  For each trade:                                                 │
│  1. Fetch historical OHLCV data from TimescaleDB                │
│  2. Compute HTF structure (3-tier correlation)                  │
│  3. Detect PD arrays (FVG, sweeps, order blocks)                │
│  4. Classify time window                                         │
│  5. Extract reference prices (daily/weekly/true day open)       │
│  6. Compute confluence factors                                   │
│  7. Generate narrative description                              │
└────────┬─────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────┐
│              EMBEDDING GENERATION                                │
│                                                                  │
│  1. Narrative embedding (SBERT)                                 │
│  2. Structured feature embedding (PCA/autoencoder)              │
│  3. Temporal embedding (cyclical encoding)                      │
│  4. Combine into 528-dim vector                                 │
└────────┬─────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────┐
│              VECTOR STORE (Qdrant)                               │
│                                                                  │
│  Bulk insert:                                                    │
│  - Embedding vector (528-dim)                                   │
│  - Full payload (all metadata)                                  │
│  - Create indexes on: instrument, time_window, htf_bias         │
└─────────────────────────────────────────────────────────────────┘
```

---

## 5. Comparison: ML-Only vs. RAG-Augmented

```
┌─────────────────────────────────────────────────────────────────┐
│                    ML-ONLY APPROACH                              │
└─────────────────────────────────────────────────────────────────┘

Current Setup
    ↓
[Feature Engineering]
    ↓
[XGBoost Models]
    ↓
Confidence: 0.78
Reasoning: "HTF bias bullish. FVG detected. Expecting expansion."
    ↓
Decision: NOTIFY (confidence >= 0.75)


┌─────────────────────────────────────────────────────────────────┐
│                    RAG-AUGMENTED APPROACH                        │
└─────────────────────────────────────────────────────────────────┘

Current Setup
    ↓
[Feature Engineering]
    ↓
    ├─→ [XGBoost Models] → Base confidence: 0.78
    │
    └─→ [RAG Engine]
            ↓
        [Retrieve Similar Setups]
            ↓
        Similar: 12 setups, avg 3.6R, 85% win rate
            ↓
        [Augmented Confluence Scorer]
            ↓
        Enhanced confidence: 0.82  (+0.04 boost from RAG)
            ↓
        [LLM Reasoning Generator]
            ↓
        Reasoning: "Price swept Asian low at 08:45 during London 
        Killzone. Similar to 2024-03-15 (4.2R), 2024-02-28 (3.1R). 
        HTF bias bullish. Historical precedent shows 85% win rate 
        for this confluence. Target HTF high at 1.0920."
            ↓
        Decision: NOTIFY + AUTO-EXECUTE (confidence >= 0.75, 
                  high similarity to winning setups)


Key Differences:
1. Confidence boost from historical precedent
2. Explainable reasoning with specific examples
3. Risk-adjusted decision (high similarity = higher confidence)
```

---

## 6. Technology Stack

```
┌─────────────────────────────────────────────────────────────────┐
│                    TECHNOLOGY STACK                              │
└─────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────┐
│  Vector Store                                                │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  Qdrant (Docker)                                       │ │
│  │  - Port: 6333                                          │ │
│  │  - Storage: 100GB SSD                                  │ │
│  │  - Collections: trading_setups                         │ │
│  └────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────┐
│  Embedding Models                                            │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  Sentence-BERT: all-MiniLM-L6-v2                       │ │
│  │  - Dimension: 384                                      │ │
│  │  - Speed: ~1ms per encoding                            │ │
│  │                                                        │ │
│  │  Structured Encoder: Custom autoencoder                │ │
│  │  - Input: 64 features                                  │ │
│  │  - Output: 128-dim                                     │ │
│  └────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────┐
│  RAG Service                                                 │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  FastAPI (Python 3.11)                                 │ │
│  │  - Endpoints: /rag/retrieve, /rag/ingest              │ │
│  │  - Port: 8003                                          │ │
│  │  - Dependencies: qdrant-client, sentence-transformers │ │
│  └────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────┐
│  LLM Integration                                             │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  Claude API (Anthropic)                                │ │
│  │  - Model: claude-3-sonnet                              │ │
│  │  - Fallback: OpenAI GPT-4                              │ │
│  └────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────┐
│  Data Pipeline                                               │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  Enrichment: Python scripts                            │ │
│  │  - Input: MongoDB trade_journal                        │ │
│  │  - Output: Qdrant trading_setups                       │ │
│  │  - Schedule: Daily batch + real-time streaming         │ │
│  └────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────┘
```

---

## Summary

This RAG system transforms AgentICTrader from a **pattern recognizer** into a **trading memory system** that:

1. **Stores** every historical setup with rich context
2. **Retrieves** similar setups based on multi-modal similarity
3. **Augments** ML predictions with historical precedent
4. **Explains** decisions by citing actual examples
5. **Adapts** continuously without retraining

The architecture is designed to integrate seamlessly with the existing ML pipeline while adding a new dimension of intelligence: **contextual memory**.
