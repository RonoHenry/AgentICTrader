# RAG Enhancement - Requirements

## Overview

This spec defines the Retrieval-Augmented Generation (RAG) system that augments AgentICTrader's ML pipeline with contextual intelligence, explainability, and historical precedent retrieval.

**Type**: Enhancement (Non-blocking)  
**Timeline**: 10 weeks (parallel to main roadmap)  
**Dependencies**: Phase 0 complete (Tasks 1-17)

---

## Functional Requirements

### FR-RAG-1: Historical Setup Storage
- The system MUST store every historical trading setup with rich context
- Each setup MUST include: HTF structure, PD arrays, time window, confluence factors, outcome
- Setups MUST be indexed by 528-dim embedding vector
- Minimum 500 setups required for MVP, target 2000+ for production

### FR-RAG-2: Semantic Retrieval
- The system MUST retrieve similar historical setups based on current market conditions
- Retrieval MUST use multi-modal embeddings (narrative + structured + temporal)
- Retrieval MUST apply metadata filters (instrument, time window, HTF bias)
- Retrieval latency MUST be < 100ms (p95)

### FR-RAG-3: Re-Ranking
- Retrieved setups MUST be re-ranked by outcome quality, recency, and confluence similarity
- Re-ranking MUST boost high R-multiple setups
- Re-ranking MUST apply exponential decay for old setups (90-day half-life)

### FR-RAG-4: RAG Metrics Generation
- The system MUST compute aggregate metrics from retrieved setups:
  - avg_r_multiple_similar
  - win_rate_similar
  - sample_size
  - max_similarity_score
  - avg_confluence_count

### FR-RAG-5: ML Pipeline Augmentation
- RAG metrics MUST be added as features to Confluence Scorer
- Augmented Confluence Scorer MUST be A/B tested against baseline
- Promotion MUST require Sharpe improvement ≥ 0.1

### FR-RAG-6: LLM Reasoning Enhancement
- LLM reasoning MUST cite actual historical examples from RAG retrieval
- Reasoning MUST follow 3-question framework with historical precedent
- Fallback to template-based reasoning if RAG unavailable

### FR-RAG-7: Real-Time Ingestion
- New setups MUST be added to vector store within 60 seconds of trade close
- Embeddings MUST be generated asynchronously
- No blocking of main trading loop

### FR-RAG-8: Dashboard Integration
- Dashboard MUST display "Similar Historical Setups" panel
- Each similar setup MUST show: date, narrative, outcome, similarity score
- Panel MUST link to historical charts (if available)

---

## Non-Functional Requirements

### NFR-RAG-1: Performance
- Retrieval latency: < 100ms (p95), < 50ms (p50)
- Embedding generation: < 500ms per setup
- Real-time ingestion: < 60s from trade close to indexed

### NFR-RAG-2: Scalability
- Support 10,000+ historical setups
- Handle 100 concurrent retrieval requests
- Horizontal scaling via Qdrant clustering

### NFR-RAG-3: Reliability
- Vector store uptime: ≥ 99.5%
- Graceful degradation: ML pipeline works without RAG
- Automatic retry on retrieval failures (max 3 attempts)

### NFR-RAG-4: Quality
- Similarity score MUST correlate with outcome (r > 0.5)
- Retrieved setups MUST be diverse (no more than 3 from same day)
- False positive rate < 10% (similar setups with opposite outcomes)

### NFR-RAG-5: Explainability
- Every RAG-augmented decision MUST be traceable
- Retrieved examples MUST be verifiable against historical data
- Similarity scores MUST be interpretable

---

## Success Criteria

### Minimum Viable RAG (MVR)
- [ ] 500+ historical setups indexed
- [ ] Retrieval latency < 100ms
- [ ] Similarity correlates with outcome (r > 0.5)
- [ ] LLM reasoning cites actual examples
- [ ] Sharpe improvement ≥ 0.1 vs. baseline

### Production Ready
- [ ] 2000+ historical setups indexed
- [ ] Retrieval latency < 50ms
- [ ] A/B test shows statistical significance (p < 0.05)
- [ ] User trust score ≥ 4/5
- [ ] Dashboard integration complete
- [ ] Monitoring and alerting live

---

## Out of Scope (Future Enhancements)

- Chart image embeddings (CLIP-based visual similarity)
- Multi-instrument transfer learning
- Regime-aware retrieval weighting
- Active learning loop with manual review
- Synthetic data generation for rare patterns

---

## Dependencies

### Completed (Phase 0)
- ✅ Task 10: HTF projection extractor
- ✅ Task 11: Candle feature extractor
- ✅ Task 12: Zone feature extractor
- ✅ Task 13: Session feature extractor
- ✅ Task 15: Trade journal importer
- ✅ Task 16: Edge analysis service

### Integration Points (Phase 1-2)
- 🔗 Task 22: Confluence Scorer (retrain with RAG features)
- 🔗 Task 27: LLM reasoning (RAG-grounded generation)
- 🔗 Task 35: Web dashboard (similar setups panel)

---

## Risks & Mitigation

### Risk 1: Insufficient Historical Data
**Impact**: High  
**Probability**: Medium  
**Mitigation**: Start with 500 setups (MVP), continuously add new setups, synthetic data if needed

### Risk 2: Retrieval Doesn't Improve Performance
**Impact**: High  
**Probability**: Low  
**Mitigation**: A/B test before rollout, keep baseline as fallback, measure in backtest first

### Risk 3: Latency Too High
**Impact**: Medium  
**Probability**: Low  
**Mitigation**: Use ANN algorithms, cache frequent queries, set timeout with fallback

### Risk 4: Integration Breaks Existing Features
**Impact**: High  
**Probability**: Low  
**Mitigation**: RAG is additive not replacement, feature flags, comprehensive tests

---

## Acceptance Criteria

### Phase 1: Data Preparation
- [ ] 500+ setups enriched with HTF/PD array context
- [ ] Narrative descriptions generated for all setups
- [ ] Embeddings generated and validated
- [ ] Data quality report shows < 5% errors

### Phase 2: Vector Store
- [ ] Qdrant deployed and running
- [ ] All setups ingested successfully
- [ ] Retrieval queries return results
- [ ] Latency benchmarks met

### Phase 3: RAG Service
- [ ] FastAPI service deployed on port 8003
- [ ] Health check endpoint responding
- [ ] Retrieval endpoint tested
- [ ] Integration tests passing

### Phase 4: ML Integration
- [ ] Confluence Scorer v2 trained with RAG features
- [ ] Backtest shows Sharpe improvement ≥ 0.1
- [ ] A/B test configured
- [ ] LLM reasoning cites historical examples

### Phase 5: Dashboard
- [ ] Similar setups panel implemented
- [ ] User engagement metrics tracked
- [ ] Positive user feedback collected

### Phase 6: Production
- [ ] Monitoring dashboards live
- [ ] Alerting configured
- [ ] Documentation complete
- [ ] Runbooks created

---

## References

- **Architecture**: `docs/RAG_ARCHITECTURE.md`
- **Implementation Guide**: `docs/RAG_IMPLEMENTATION_GUIDE.md`
- **Integration Strategy**: `docs/RAG_INTEGRATION_STRATEGY.md`
- **System Diagrams**: `docs/RAG_SYSTEM_DIAGRAM.md`
