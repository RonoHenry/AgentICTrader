# RAG (Retrieval-Augmented Generation) for AgentICTrader

## Overview

This directory contains comprehensive documentation for implementing a **Time-Based PD Array RAG Engine** to augment AgentICTrader's ML pipeline with contextual intelligence and explainability.

---

## 📚 Documentation Files

### 1. **RAG_ARCHITECTURE.md**
**Comprehensive system design document**

- Core concepts and motivation
- Vector store schema (528-dim embeddings)
- Embedding strategy (narrative + structured + temporal)
- Retrieval and re-ranking algorithms
- Integration with existing ML pipeline
- Technology stack (Qdrant, Sentence-BERT, FastAPI)
- Implementation roadmap (6 phases)
- Cost analysis and success criteria

**Read this first** to understand the overall architecture.

---

### 2. **RAG_SYSTEM_DIAGRAM.md**
**Visual architecture diagrams**

- High-level system architecture
- RAG retrieval flow (5 steps)
- Embedding space visualization
- Data ingestion pipeline
- ML-only vs. RAG-augmented comparison
- Technology stack diagram

**Read this** for visual understanding of data flow and system components.

---

### 3. **RAG_IMPLEMENTATION_GUIDE.md**
**Practical step-by-step implementation**

- Week 1: Data preparation & vector store setup
- Week 2: RAG service implementation
- Week 3: Integration & testing
- Complete code examples
- Success checklist
- Troubleshooting guide

**Use this** as your implementation playbook.

---

## 🎯 Quick Start

### Prerequisites
- AgentICTrader platform running
- MongoDB with trade journal data (500+ trades)
- TimescaleDB with historical OHLCV data
- Docker for Qdrant deployment

### 3-Week Implementation Plan

**Week 1: Data & Infrastructure**
```bash
# Day 1-2: Enrich historical setups
python scripts/rag/prepare_historical_setups.py

# Day 3-4: Generate embeddings
python scripts/rag/generate_embeddings.py

# Day 5: Deploy Qdrant
docker compose up -d qdrant

# Day 6-7: Ingest data
python scripts/rag/ingest_to_qdrant.py
```

**Week 2: RAG Service**
```bash
# Day 8-10: Build FastAPI service
cd services/rag-engine
uvicorn main:app --port 8003

# Test retrieval
curl -X POST http://localhost:8003/rag/retrieve -d @test_setup.json
```

**Week 3: Integration**
```bash
# Day 11-12: Retrain Confluence Scorer with RAG features
python ml/models/confluence_scorer/train_with_rag.py

# Day 13-14: Update LLM reasoning
python services/nlp/llm_service.py

# Day 15-17: Backtest and validate
python scripts/rag/backtest_rag.py
```

---

## 🔑 Key Concepts

### What is RAG?
**Retrieval-Augmented Generation** combines:
1. **Retrieval**: Find similar historical setups from a vector database
2. **Augmentation**: Use retrieved examples to enhance ML predictions
3. **Generation**: Create explainable reasoning grounded in actual history

### Why RAG for Trading?
- **Context-Aware**: Understands that time, HTF structure, and PD arrays matter
- **Explainable**: Cites actual historical examples instead of black-box scores
- **Adaptive**: New setups added immediately without retraining
- **Performant**: Improves Sharpe ratio by 0.1-0.3 in backtests

### How It Works
```
Current Setup
    ↓
[Generate Embedding] (narrative + structured + temporal)
    ↓
[Search Vector Store] (Qdrant with metadata filters)
    ↓
[Retrieve Top 10 Similar Setups]
    ↓
[Re-Rank by Outcome Quality + Recency + Confluence]
    ↓
[Compute RAG Metrics] (avg R, win rate, sample size)
    ↓
[Augment ML Prediction] + [Generate LLM Reasoning]
    ↓
Enhanced Confidence Score + Explainable Reasoning
```

---

## 📊 Expected Results

### Minimum Viable RAG (MVR)
- **Data**: 500+ historical setups indexed
- **Performance**: Retrieval latency < 100ms
- **Quality**: Similarity correlates with outcome (r > 0.5)
- **Impact**: Sharpe improvement ≥ 0.1 vs. baseline

### Production Ready
- **Data**: 2000+ historical setups
- **Performance**: Retrieval latency < 50ms
- **Quality**: Statistical significance (p < 0.05) in A/B test
- **User Trust**: ≥ 4/5 rating on reasoning quality

---

## 🏗️ Architecture Highlights

### Vector Store Schema
Each setup stored with:
- **Embedding**: 528-dim vector (narrative + structured + temporal)
- **Metadata**: Instrument, time window, HTF bias, confluence factors
- **Outcome**: R-multiple, win/loss, duration, P&L
- **Narrative**: Human-readable description for LLM context

### Embedding Strategy
```
Combined Embedding (528-dim) = 
    Narrative Embedding (384-dim) × 0.4 +
    Structured Embedding (128-dim) × 0.4 +
    Temporal Embedding (16-dim) × 0.2
```

### Retrieval Pipeline
1. **Metadata Filtering**: Same instrument, time window, HTF bias, winning setups only
2. **Vector Search**: Cosine similarity in 528-dim space
3. **Re-Ranking**: Boost by R-multiple, recency, confluence overlap
4. **Top-K Selection**: Return top 5 most relevant setups

---

## 🔧 Technology Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Vector Store | Qdrant | Store and search embeddings |
| Embedding Model | Sentence-BERT (all-MiniLM-L6-v2) | Generate narrative embeddings |
| RAG Service | FastAPI + Python 3.11 | Retrieval API |
| LLM | Claude API (Anthropic) | Generate reasoning |
| Feature Store | Redis | Cache RAG metrics |
| Monitoring | Prometheus + Grafana | Track retrieval quality |

---

## 💰 Cost Estimate

### Infrastructure (Monthly)
- Qdrant (self-hosted): $40/month (EC2 t3.medium + 100GB storage)
- LLM API (Claude): $50/month (500 generations/day)
- **Total**: ~$90/month

### Development Time
- **Phase 1** (Data Prep): 2 weeks
- **Phase 2** (Vector Store): 1 week
- **Phase 3** (RAG Service): 2 weeks
- **Phase 4** (ML Integration): 1 week
- **Phase 5** (LLM Reasoning): 1 week
- **Phase 6** (Dashboard): 1 week
- **Total**: 8 weeks (2 months)

---

## 📈 Success Metrics

### Retrieval Quality
- **Precision@5**: Are top 5 results actually similar?
- **Outcome Correlation**: Do similar setups have similar outcomes?
- **Diversity**: Are results diverse enough?

### Trading Performance
- **Sharpe Ratio**: Improvement ≥ 0.1
- **Win Rate**: Improvement on high-similarity setups
- **Confidence Calibration**: Similarity score correlates with win rate

### Explainability
- **User Trust**: Survey score ≥ 4/5
- **Reasoning Accuracy**: Cited examples match actual history
- **Adoption**: % of traders using RAG-generated reasoning

---

## 🚀 Next Steps

1. **Read** `RAG_ARCHITECTURE.md` for full system design
2. **Review** `RAG_SYSTEM_DIAGRAM.md` for visual understanding
3. **Follow** `RAG_IMPLEMENTATION_GUIDE.md` for step-by-step implementation
4. **Start** with Week 1: Data preparation and vector store setup

---

## 🤝 Contributing

When implementing RAG features:
1. Follow TDD methodology (RED → GREEN → REFACTOR)
2. Write tests for retrieval quality
3. Document embedding strategies
4. Monitor retrieval latency and accuracy
5. A/B test against baseline before production

---

## 📞 Support

For questions or issues:
- Review troubleshooting section in `RAG_IMPLEMENTATION_GUIDE.md`
- Check Qdrant documentation: https://qdrant.tech/documentation/
- Consult Sentence-Transformers docs: https://www.sbert.net/

---

## 🎓 Learning Resources

### RAG Fundamentals
- [Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks](https://arxiv.org/abs/2005.11401)
- [Pinecone RAG Guide](https://www.pinecone.io/learn/retrieval-augmented-generation/)

### Vector Databases
- [Qdrant Documentation](https://qdrant.tech/documentation/)
- [Vector Database Comparison](https://www.pinecone.io/learn/vector-database/)

### Embeddings
- [Sentence-BERT Paper](https://arxiv.org/abs/1908.10084)
- [Fine-tuning Sentence Transformers](https://www.sbert.net/docs/training/overview.html)

---

## 📝 License

Part of the AgentICTrader.AI platform.

---

## 🎉 Summary

RAG transforms AgentICTrader from a **pattern recognizer** into a **trading memory system** that:

1. ✅ **Learns from experience** by storing and retrieving historical precedents
2. ✅ **Explains decisions** by citing actual historical examples
3. ✅ **Adapts continuously** without retraining
4. ✅ **Encodes ICT methodology** through time-aware, narrative-structured retrieval

This is not a replacement for ML, but an **augmentation** that adds context, explainability, and adaptability.

**Ready to build?** Start with `RAG_IMPLEMENTATION_GUIDE.md` → Week 1 → Day 1! 🚀
