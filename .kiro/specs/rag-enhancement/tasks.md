# Implementation Plan: AlgoRAG

## Overview

This implementation plan breaks down the **AlgoRAG** feature into discrete, testable coding tasks following TDD methodology (RED → GREEN → REFACTOR). AlgoRAG augments AgentICTrader's ML pipeline with contextual intelligence by retrieving similar historical trading setups using vector embeddings.

**Architecture**: Multi-modal embeddings (narrative + structured + temporal) → Qdrant vector store → FastAPI service (`services/algorag/`) → ML pipeline augmentation

**Integration Points**:
- Confluence Scorer (Task 22) - adds RAG features
- LLM Reasoning (Task 27) - adds historical precedent
- Dashboard (Task 35) - adds similar setups panel

**Timeline**: 10 weeks parallel to main roadmap

---

## Tasks

### Phase 1: Infrastructure Setup

- [x] 1. Set up Qdrant vector store and RAG service infrastructure
  - [x] 1.1 Create Docker configuration for Qdrant
    - Add Qdrant service to `docker/docker-compose.yml` (port 6333)
    - Configure persistent volume for vector data
    - Set memory limits and resource constraints
    - Add health check configuration
    - _Requirements: NFR-RAG-2, NFR-RAG-3_
  
  - [x] 1.2 Write integration tests for Qdrant connection
    - **RED**: Test Qdrant connection, collection creation, basic CRUD operations
    - **GREEN**: Implement Qdrant client wrapper with connection pooling
    - **REFACTOR**: Extract configuration to environment variables
    - _Requirements: NFR-RAG-3_
  
  - [x] 1.3 Create AlgoRAG service directory structure
    - Create `services/algorag/` directory
    - Create `services/algorag/main.py` (FastAPI app)
    - Create `services/algorag/config.py` (configuration)
    - Create `services/algorag/models.py` (Pydantic models)
    - Create `services/algorag/requirements.txt`
    - Create `services/algorag/Dockerfile`
    - _Requirements: FR-RAG-2_
  
  - [x] 1.4 Implement AlgoRAG service health check endpoint
    - **RED**: Test GET /health returns service status and vector store connection
    - **GREEN**: Implement health check with Qdrant connectivity test
    - **REFACTOR**: Add setup count and version info to response
    - _Requirements: NFR-RAG-3_

- [x] 2. Checkpoint - Verify infrastructure
  - Ensure Qdrant container starts successfully
  - Ensure RAG service health check passes
  - Ensure all tests pass, ask the user if questions arise.

### Phase 2: Data Preparation Pipeline

- [x] 3. Implement historical setup enrichment pipeline
  - [x] 3.1 Create setup enrichment script structure
    - Create `scripts/rag/prepare_historical_setups.py`
    - Create `scripts/rag/utils/narrative_generator.py`
    - Create `scripts/rag/utils/setup_enricher.py`
    - Define EnrichedSetup data model
    - _Requirements: FR-RAG-1_
  
  - [x] 3.2 Implement HTF structure extraction for historical setups
    - **RED**: Test extraction of HTF bias, projections, and structure from historical candles
    - **GREEN**: Reuse HTFProjectionExtractor to compute HTF context for past trades
    - **REFACTOR**: Add caching for repeated symbol/timeframe queries
    - _Requirements: FR-RAG-1_
  
  - [x] 3.3 Implement PD array detection for historical setups
    - **RED**: Test extraction of order blocks, FVGs, liquidity zones from historical candles
    - **GREEN**: Reuse ZoneFeatureExtractor to detect PD arrays for past trades
    - **REFACTOR**: Optimize batch processing for multiple setups
    - _Requirements: FR-RAG-1_
  
  - [x] 3.4 Implement time window classification
    - **RED**: Test classification of entry time into killzones (London, NY, Asian)
    - **GREEN**: Implement TimeWindowClassifier using SessionFeatureExtractor logic
    - **REFACTOR**: Extract timezone handling to utility function
    - _Requirements: FR-RAG-1_
  
  - [x] 3.5 Implement narrative generation
    - **RED**: Test generation of human-readable setup descriptions
    - **GREEN**: Implement template-based narrative generator with HTF/PD array context
    - **REFACTOR**: Add narrative quality validation (min length, key terms present)
    - _Requirements: FR-RAG-1_
  
  - [x] 3.6 Write integration tests for enrichment pipeline
    - Test end-to-end enrichment from trade journal to enriched setup
    - Test error handling for missing data
    - Test batch processing performance
    - _Requirements: FR-RAG-1, NFR-RAG-4_

- [x] 4. Implement embedding generation pipeline
  - [x] 4.1 Set up embedding models
    - Install sentence-transformers library
    - Download all-MiniLM-L6-v2 model
    - Create model loading utility with caching
    - _Requirements: FR-RAG-2_
  
  - [x] 4.2 Implement narrative embedding generation
    - **RED**: Test SBERT encoding of setup narratives to 384-dim vectors
    - **GREEN**: Implement narrative embedding with sentence-transformers
    - **REFACTOR**: Add batch processing for multiple narratives
    - _Requirements: FR-RAG-2_
  
  - [x] 4.3 Implement structured feature embedding
    - **RED**: Test extraction and encoding of 64 structured features to 128-dim vectors
    - **GREEN**: Implement feature extraction (HTF metrics, PD array counts, confluence factors)
    - **REFACTOR**: Normalize features to [0, 1] range
    - _Requirements: FR-RAG-2_
  
  - [x] 4.4 Implement temporal embedding generation
    - **RED**: Test cyclical encoding of timestamps to 16-dim vectors
    - **GREEN**: Implement sin/cos transforms for hour, day-of-week, month
    - **REFACTOR**: Add timezone normalization
    - _Requirements: FR-RAG-2_
  
  - [x] 4.5 Implement multi-modal embedding combination
    - **RED**: Test weighted concatenation of 3 embedding types to 528-dim vector
    - **GREEN**: Implement combination with weights (40% narrative, 40% structured, 20% temporal)
    - **REFACTOR**: Add embedding validation (check dimensions, NaN values)
    - _Requirements: FR-RAG-2_
  
  - [x] 4.6 Write unit tests for embedding generation
    - Test each embedding type independently
    - Test edge cases (empty narrative, missing features, invalid timestamps)
    - Test embedding consistency (same input → same output)
    - _Requirements: FR-RAG-2, NFR-RAG-4_

- [x] 5. Checkpoint - Verify data preparation
  - Ensure enrichment pipeline processes 10+ sample setups
  - Ensure embeddings are generated correctly (528-dim, no NaN)
  - Ensure all tests pass, ask the user if questions arise.

### Phase 3: Vector Store Integration

- [x] 6. Implement Qdrant collection management
  - [x] 6.1 Create vector store schema and collection
    - **RED**: Test collection creation with 528-dim vectors, cosine distance
    - **GREEN**: Implement collection creation with payload schema (trade_id, timestamp, instrument, etc.)
    - **REFACTOR**: Add idempotent collection creation (skip if exists)
    - _Requirements: FR-RAG-1_
  
  - [x] 6.2 Implement metadata indexing
    - **RED**: Test creation of indexes on instrument, time_window, htf_open_bias, outcome_result
    - **GREEN**: Implement index creation for fast metadata filtering
    - **REFACTOR**: Add index validation and rebuild capability
    - _Requirements: FR-RAG-2_
  
  - [x] 6.3 Write tests for collection management
    - Test collection creation, deletion, recreation
    - Test index creation and query performance
    - Test schema validation
    - _Requirements: FR-RAG-1, NFR-RAG-2_

- [x] 7. Implement setup ingestion to vector store
  - [x] 7.1 Create ingestion service
    - **RED**: Test batch ingestion of enriched setups with embeddings to Qdrant
    - **GREEN**: Implement batch upsert with error handling and retry logic
    - **REFACTOR**: Add progress tracking and logging
    - _Requirements: FR-RAG-1, FR-RAG-7_
  
  - [x] 7.2 Implement duplicate detection
    - **RED**: Test detection and handling of duplicate trade_ids
    - **GREEN**: Implement upsert logic (update if exists, insert if new)
    - **REFACTOR**: Add conflict resolution strategy
    - _Requirements: FR-RAG-1_
  
  - [x] 7.3 Write integration tests for ingestion
    - Test ingestion of 100+ setups
    - Test error handling (network failures, invalid data)
    - Test ingestion performance (< 1s per setup)
    - _Requirements: FR-RAG-7, NFR-RAG-1_

- [x] 8. Implement initial data load
  - [x] 8.1 Create data loading script
    - Create `scripts/rag/load_initial_data.py`
    - Load 500+ historical setups from trade journal
    - Enrich, embed, and ingest to Qdrant
    - Generate data quality report
    - _Requirements: FR-RAG-1_
  
  - [ ]* 8.2 Write validation tests for initial data
    - Test data quality (< 5% errors)
    - Test embedding quality (no NaN, correct dimensions)
    - Test retrieval works on loaded data
    - _Requirements: FR-RAG-1, NFR-RAG-4_

- [x] 9. Checkpoint - Verify vector store
  - Ensure 500+ setups ingested successfully
  - Ensure retrieval queries return results
  - Ensure all tests pass, ask the user if questions arise.

### Phase 4: RAG Retrieval Service

- [x] 10. Implement retrieval endpoint
  - [x] 10.1 Create retrieval request/response models
    - Define RetrievalRequest Pydantic model (instrument, timestamp, narrative, etc.)
    - Define RetrievalResponse Pydantic model (similar_setups, rag_metrics, query_time_ms)
    - Define SimilarSetup model (setup, similarity_score, final_score, etc.)
    - _Requirements: FR-RAG-2_
  
  - [x] 10.2 Implement metadata filtering
    - **RED**: Test filtering by instrument, time_window, htf_open_bias, outcome_result=WIN
    - **GREEN**: Implement Qdrant filter construction from request parameters
    - **REFACTOR**: Add optional filters (allow missing parameters)
    - _Requirements: FR-RAG-2_
  
  - [x] 10.3 Implement vector similarity search
    - **RED**: Test cosine similarity search returning top-10 results
    - **GREEN**: Implement Qdrant search with query embedding and filters
    - **REFACTOR**: Add timeout handling and error recovery
    - _Requirements: FR-RAG-2, NFR-RAG-1_
  
  - [x] 10.4 Implement re-ranking algorithm
    - **RED**: Test re-ranking by outcome quality + recency + confluence overlap
    - **GREEN**: Implement scoring function with exponential decay (90-day half-life)
    - **REFACTOR**: Make weights configurable (outcome: 0.5, recency: 0.3, confluence: 0.2)
    - _Requirements: FR-RAG-3_
  
  - [x] 10.5 Implement diversity filtering
    - **RED**: Test limiting results to max 3 setups from same day
    - **GREEN**: Implement date-based deduplication in top-10 results
    - **REFACTOR**: Add configurable diversity threshold
    - _Requirements: NFR-RAG-4_
  
  - [x] 10.6 Write unit tests for retrieval logic
    - Test metadata filtering with various combinations
    - Test re-ranking algorithm with mock data
    - Test diversity filtering edge cases
    - _Requirements: FR-RAG-2, FR-RAG-3, NFR-RAG-4_

- [x] 11. Implement RAG metrics computation
  - [x] 11.1 Compute aggregate metrics from retrieved setups
    - **RED**: Test computation of avg_r_multiple, win_rate, sample_size, max_similarity
    - **GREEN**: Implement metrics calculation from top-5 results
    - **REFACTOR**: Add statistical validation (min sample size = 3)
    - _Requirements: FR-RAG-4_
  
  - [ ]* 11.2 Write unit tests for metrics computation
    - Test metrics with various result sets (0, 1, 5, 10 results)
    - Test edge cases (all losses, all wins, mixed outcomes)
    - Test numerical stability (division by zero, NaN handling)
    - _Requirements: FR-RAG-4_

- [x] 12. Implement ingestion endpoint
  - [x] 12.1 Create ingestion endpoint
    - **RED**: Test POST /rag/ingest accepts setup + embedding and stores in Qdrant
    - **GREEN**: Implement async ingestion with validation
    - **REFACTOR**: Add rate limiting and authentication
    - _Requirements: FR-RAG-7_
  
  - [ ]* 12.2 Write integration tests for ingestion endpoint
    - Test successful ingestion
    - Test validation errors (missing fields, invalid embedding)
    - Test duplicate handling
    - _Requirements: FR-RAG-7_

- [ ] 13. Implement performance monitoring
  - [x] 13.1 Add latency tracking
    - **RED**: Test query_time_ms is accurately measured and returned
    - **GREEN**: Implement timing decorator for retrieval endpoint
    - **REFACTOR**: Add Prometheus histogram metrics
    - _Requirements: NFR-RAG-1_
  
  - [x] 13.2 Add error logging
    - **RED**: Test all errors are logged with context (request params, stack trace)
    - **GREEN**: Implement structured logging with correlation IDs
    - **REFACTOR**: Add log aggregation to centralized system
    - _Requirements: NFR-RAG-3_

- [x] 14. Checkpoint - Verify RAG service
  - Ensure retrieval endpoint returns results < 100ms
  - Ensure RAG metrics are computed correctly
  - Ensure all tests pass, ask the user if questions arise.

### Phase 5: ML Pipeline Integration

- [x] 15. Implement AlgoRAG client library
  - [x] 15.1 Create AlgoRAG client for ML services
    - Create `ml/algorag/client.py` with async HTTP client
    - Implement retrieve() method with retry logic
    - Implement connection pooling and timeout handling
    - _Requirements: FR-RAG-5, NFR-RAG-3_
  
  - [ ]* 15.2 Write unit tests for AlgoRAG client
    - Test successful retrieval
    - Test retry logic on failures
    - Test timeout handling
    - Test graceful degradation (return empty metrics on error)
    - _Requirements: FR-RAG-5, NFR-RAG-3_

- [x] 16. Augment Confluence Scorer with RAG features
  - [x] 16.1 Modify feature extraction to include RAG metrics
    - **RED**: Test feature vector includes 4 new RAG features (avg_r_multiple, win_rate, sample_size, max_similarity)
    - **GREEN**: Modify `ml/models/confluence_scorer/features.py` to call RAG client and append metrics
    - **REFACTOR**: Add feature normalization and missing value handling
    - _Requirements: FR-RAG-5_
  
  - [x] 16.2 Retrain Confluence Scorer with RAG features
    - **RED**: Test training script accepts RAG-augmented feature vectors
    - **GREEN**: Modify `ml/models/confluence_scorer/train_with_rag.py` to include RAG features
    - **REFACTOR**: Add feature importance analysis for RAG features
    - _Requirements: FR-RAG-5_
  
  - [ ]* 16.3 Write integration tests for augmented scorer
    - Test feature extraction with RAG client
    - Test fallback when RAG unavailable (use zeros for RAG features)
    - Test model prediction with RAG features
    - _Requirements: FR-RAG-5, NFR-RAG-3_

- [x] 17. Implement A/B testing framework
  - [x] 17.1 Create model versioning system
    - **RED**: Test loading of confluence-scorer-v1 (baseline) and confluence-scorer-v2-rag
    - **GREEN**: Implement model registry with version selection
    - **REFACTOR**: Add feature flags for A/B test control
    - _Requirements: FR-RAG-5_
  
  - [x] 17.2 Implement traffic splitting
    - **RED**: Test 50/50 traffic split between v1 and v2 models
    - **GREEN**: Implement random assignment with sticky sessions
    - **REFACTOR**: Add configurable split ratios
    - _Requirements: FR-RAG-5_
  
  - [x]* 17.3 Write tests for A/B testing framework
    - Test model selection logic
    - Test traffic distribution
    - Test metrics collection per variant
    - _Requirements: FR-RAG-5_

- [x] 18. Checkpoint - Verify ML integration
  - Ensure Confluence Scorer v2 trains successfully
  - Ensure A/B test framework works
  - Ensure all tests pass, ask the user if questions arise.

### Phase 6: LLM Integration

- [ ] 19. Implement RAG-grounded LLM reasoning
  - [x] 19.1 Create LLM prompt templates with RAG context
    - Create `services/nlp/prompts/rag_reasoning.py`
    - Define prompt template with similar setups section
    - Add formatting utilities for historical examples
    - _Requirements: FR-RAG-6_
  
  - [x] 19.2 Modify LLM reasoning to include RAG retrieval
    - **RED**: Test generate_trade_reasoning_with_rag() calls RAG client and includes examples in prompt
    - **GREEN**: Modify `services/nlp/llm_service.py` to retrieve similar setups and format for LLM
    - **REFACTOR**: Add fallback to template-based reasoning if RAG fails
    - _Requirements: FR-RAG-6, NFR-RAG-3_
  
  - [ ]* 19.3 Write integration tests for RAG-grounded reasoning
    - Test reasoning with RAG examples
    - Test fallback when RAG unavailable
    - Test prompt formatting with 0, 1, 3, 5 examples
    - _Requirements: FR-RAG-6, NFR-RAG-3_

- [ ] 20. Checkpoint - Verify LLM integration
  - Ensure LLM reasoning cites historical examples
  - Ensure fallback works when RAG unavailable
  - Ensure all tests pass, ask the user if questions arise.

### Phase 7: Real-Time Ingestion

- [ ] 21. Implement real-time setup ingestion
  - [ ] 21.1 Create trade close event handler
    - **RED**: Test event handler triggers on trade close and starts enrichment pipeline
    - **GREEN**: Implement async event handler in trade execution service
    - **REFACTOR**: Add event queue for decoupling
    - _Requirements: FR-RAG-7_
  
  - [ ] 21.2 Implement async enrichment and ingestion
    - **RED**: Test enrichment + embedding + ingestion completes within 60 seconds
    - **GREEN**: Implement async pipeline with parallel processing
    - **REFACTOR**: Add progress tracking and error notifications
    - _Requirements: FR-RAG-7, NFR-RAG-1_
  
  - [ ]* 21.3 Write integration tests for real-time ingestion
    - Test end-to-end flow from trade close to indexed in Qdrant
    - Test error handling and retry logic
    - Test performance under load (10 concurrent trades)
    - _Requirements: FR-RAG-7, NFR-RAG-1_

- [ ] 22. Checkpoint - Verify real-time ingestion
  - Ensure new setups appear in vector store within 60 seconds
  - Ensure no blocking of main trading loop
  - Ensure all tests pass, ask the user if questions arise.

### Phase 8: Dashboard Integration

- [ ] 23. Implement similar setups panel
  - [ ] 23.1 Create backend API endpoint for similar setups
    - **RED**: Test GET /api/similar-setups/{trade_id} returns similar historical setups
    - **GREEN**: Implement endpoint that calls RAG service and formats response
    - **REFACTOR**: Add caching for frequently accessed trades
    - _Requirements: FR-RAG-8_
  
  - [ ] 23.2 Create frontend component for similar setups panel
    - Create React component `SimilarSetupsPanel.tsx`
    - Display setup cards with date, narrative, outcome, similarity score
    - Add link to historical chart (if available)
    - _Requirements: FR-RAG-8_
  
  - [ ] 23.3 Integrate panel into dashboard
    - **RED**: Test panel appears on trade detail page
    - **GREEN**: Add panel to `services/analytics/dashboard.py` trade detail view
    - **REFACTOR**: Add loading states and error handling
    - _Requirements: FR-RAG-8_
  
  - [ ]* 23.4 Write integration tests for dashboard panel
    - Test panel renders with mock data
    - Test API endpoint integration
    - Test error states (RAG unavailable, no similar setups)
    - _Requirements: FR-RAG-8_

- [ ] 24. Checkpoint - Verify dashboard integration
  - Ensure similar setups panel displays correctly
  - Ensure user engagement metrics tracked
  - Ensure all tests pass, ask the user if questions arise.

### Phase 9: Monitoring & Observability

- [ ] 25. Implement monitoring dashboards
  - [ ] 25.1 Create Prometheus metrics
    - Add retrieval latency histogram (p50, p95, p99)
    - Add retrieval count counter
    - Add error rate counter
    - Add vector store size gauge
    - _Requirements: NFR-RAG-1_
  
  - [ ] 25.2 Create Grafana dashboard
    - Create dashboard with latency charts
    - Add error rate charts
    - Add vector store growth chart
    - Add RAG feature impact chart (Sharpe improvement)
    - _Requirements: NFR-RAG-1_
  
  - [ ]* 25.3 Write tests for metrics collection
    - Test metrics are emitted correctly
    - Test histogram buckets are appropriate
    - Test counter increments
    - _Requirements: NFR-RAG-1_

- [ ] 26. Implement alerting
  - [ ] 26.1 Create alert rules
    - Alert on retrieval latency > 200ms (p95)
    - Alert on vector store connection failures
    - Alert on embedding generation failures
    - Alert on low similarity scores (< 0.5 for all results)
    - _Requirements: NFR-RAG-3_
  
  - [ ] 26.2 Configure alert channels
    - Set up Slack notifications
    - Set up email notifications
    - Add runbook links to alerts
    - _Requirements: NFR-RAG-3_

- [ ] 27. Checkpoint - Verify monitoring
  - Ensure all metrics are collected
  - Ensure dashboards display correctly
  - Ensure alerts fire correctly
  - Ensure all tests pass, ask the user if questions arise.

### Phase 10: Validation & Production Readiness

- [ ] 28. Implement offline evaluation
  - [ ] 28.1 Create similarity-outcome correlation analysis
    - **RED**: Test correlation between similarity scores and actual outcomes
    - **GREEN**: Implement analysis script that computes Pearson correlation (target: r > 0.5)
    - **REFACTOR**: Add visualization of correlation
    - _Requirements: NFR-RAG-4_
  
  - [ ] 28.2 Create backtest with RAG features
    - **RED**: Test backtest shows Sharpe improvement ≥ 0.1 with RAG features
    - **GREEN**: Run backtest comparing baseline vs. RAG-augmented Confluence Scorer
    - **REFACTOR**: Add statistical significance testing
    - _Requirements: FR-RAG-5, NFR-RAG-4_
  
  - [ ]* 28.3 Write validation tests
    - Test false positive rate < 10%
    - Test diversity of retrieved setups
    - Test retrieval quality across different market conditions
    - _Requirements: NFR-RAG-4_

- [ ] 29. Implement production deployment
  - [ ] 29.1 Create deployment scripts
    - Create `scripts/rag/deploy.sh` for production deployment
    - Add environment-specific configurations (dev, staging, prod)
    - Add rollback procedures
    - _Requirements: NFR-RAG-3_
  
  - [ ] 29.2 Create runbooks
    - Create `docs/runbooks/rag_service.md` with troubleshooting steps
    - Document common issues and resolutions
    - Add escalation procedures
    - _Requirements: NFR-RAG-3_
  
  - [ ] 29.3 Create documentation
    - Update `docs/RAG_ARCHITECTURE.md` with final architecture
    - Create `docs/RAG_OPERATIONS.md` with operational procedures
    - Create `docs/RAG_API.md` with API documentation
    - _Requirements: NFR-RAG-5_

- [ ] 30. Final checkpoint - Production readiness

  - Ensure 2000+ setups indexed
  - Ensure retrieval latency < 50ms (p50)
  - Ensure A/B test shows statistical significance
  - Ensure monitoring and alerting live
  - Ensure documentation complete
  - Ensure all tests pass, ask the user if questions arise.

---

## Task Dependency Graph

Local task numbers below (1–30) refer to this document's own numbering. References of the form "platform Task N" refer to `.kiro/specs/agentictrader-platform/tasks.md`'s numbering — the two are independent sequences and are not interchangeable (e.g. local Task 22 here is "Implement ingestion endpoint," which is unrelated to platform Task 22, "Confluence Scorer"). Dependencies are denoted as `prerequisite → dependent`.

```json
{
  "waves": [
    {
      "name": "Infrastructure Setup",
      "tasks": ["1", "2"],
      "description": "Qdrant vector store, AlgoRAG service scaffold, health check"
    },
    {
      "name": "Data Preparation Pipeline",
      "tasks": ["3", "4", "5"],
      "description": "Historical setup enrichment and multi-modal embedding generation",
      "dependencies": ["platform Task 10", "platform Task 11", "platform Task 12", "platform Task 13", "platform Task 15"]
    },
    {
      "name": "Vector Store Integration",
      "tasks": ["6", "7", "8", "9"],
      "description": "Collection management, ingestion, and initial 500+ setup load",
      "dependencies": ["Infrastructure Setup", "Data Preparation Pipeline"]
    },
    {
      "name": "RAG Retrieval Service",
      "tasks": ["10", "11", "12", "13", "14"],
      "description": "Similarity search, re-ranking, metrics, ingestion endpoint, perf monitoring",
      "dependencies": ["Vector Store Integration"]
    },
    {
      "name": "ML Pipeline Integration",
      "tasks": ["15", "16", "17", "18"],
      "description": "AlgoRAG client, Confluence Scorer augmentation, A/B testing framework",
      "dependencies": ["RAG Retrieval Service"]
    },
    {
      "name": "LLM Integration",
      "tasks": ["19", "20"],
      "description": "RAG-grounded trade reasoning generation",
      "dependencies": ["RAG Retrieval Service"]
    },
    {
      "name": "Real-Time Ingestion",
      "tasks": ["21", "22"],
      "description": "Trade-close event handling and async enrichment/ingestion",
      "dependencies": ["Data Preparation Pipeline", "RAG Retrieval Service"]
    },
    {
      "name": "Dashboard Integration",
      "tasks": ["23", "24"],
      "description": "Similar-setups panel, backend endpoint, frontend component",
      "dependencies": ["RAG Retrieval Service"]
    },
    {
      "name": "Monitoring & Observability",
      "tasks": ["25", "26", "27"],
      "description": "Prometheus metrics, Grafana dashboards, alerting",
      "dependencies": ["RAG Retrieval Service"]
    },
    {
      "name": "Validation & Production Readiness",
      "tasks": ["28", "29", "30"],
      "description": "Offline evaluation, backtest, deployment, docs, final checkpoint",
      "dependencies": ["ML Pipeline Integration", "LLM Integration", "Real-Time Ingestion", "Dashboard Integration", "Monitoring & Observability"]
    }
  ]
}
```

### Infrastructure Setup
```
1 (Qdrant + Service Scaffold) → 2 (Infra Checkpoint)
```

### Data Preparation Pipeline
```
platform Task 10 (HTF Extractor) + platform Task 11 (Candle Extractor) + platform Task 12 (Zone Extractor) + platform Task 13 (Session Extractor) + platform Task 15 (Trade Journal Importer) → 3 (Enrichment Pipeline)
3 (Enrichment) → 4 (Embedding Generation)
3 + 4 → 5 (Data Prep Checkpoint)
```

### Vector Store Integration
```
2 (Infra Checkpoint) + 5 (Data Prep Checkpoint) → 6 (Collection Management)
6 (Collection Management) → 7 (Setup Ingestion)
6 + 7 → 8 (Initial Data Load)
6 + 7 + 8 → 9 (Vector Store Checkpoint)
```

### RAG Retrieval Service
```
9 (Vector Store Checkpoint) → 10 (Retrieval Endpoint)
10 (Retrieval Endpoint) → 11 (RAG Metrics Computation)
9 → 12 (Ingestion Endpoint)
10 → 13 (Performance Monitoring)
10 + 11 + 12 + 13 → 14 (RAG Service Checkpoint)
```

### ML Pipeline Integration
```
14 (RAG Service Checkpoint) → 15 (AlgoRAG Client Library)
15 (Client Library) → 16 (Confluence Scorer Augmentation)
16 (Augmented Scorer) → 17 (A/B Testing Framework)
15 + 16 + 17 → 18 (ML Integration Checkpoint)
```

### LLM Integration
```
14 (RAG Service Checkpoint) → 19 (RAG-Grounded LLM Reasoning)
19 → 20 (LLM Integration Checkpoint)
```

### Real-Time Ingestion
```
3 (Enrichment Pipeline) + 12 (Ingestion Endpoint) → 21 (Real-Time Event Handler + Async Pipeline)
21 → 22 (Real-Time Ingestion Checkpoint)
```

### Dashboard Integration
```
14 (RAG Service Checkpoint) → 23 (Similar Setups Panel)
23 → 24 (Dashboard Checkpoint)
```

### Monitoring & Observability
```
14 (RAG Service Checkpoint) → 25 (Prometheus/Grafana Dashboards)
25 → 26 (Alerting)
25 + 26 → 27 (Monitoring Checkpoint)
```

### Validation & Production Readiness
```
18 (ML Integration Checkpoint) + 20 (LLM Integration Checkpoint) + 22 (Real-Time Ingestion Checkpoint) + 24 (Dashboard Checkpoint) + 27 (Monitoring Checkpoint) → 28 (Offline Evaluation)
28 → 29 (Production Deployment)
28 + 29 → 30 (Final Checkpoint)
```

### Dependency Summary by Phase

**Phase 1 — Infrastructure Setup (Tasks 1–2)**
- 1: Qdrant vector store and AlgoRAG service scaffold (no dependencies)
- 2: Infrastructure checkpoint (requires 1)

**Phase 2 — Data Preparation Pipeline (Tasks 3–5)**
- 3: Historical setup enrichment (requires platform Tasks 10, 11, 12, 13, 15; independent of Phase 1)
- 4: Multi-modal embedding generation (requires 3)
- 5: Data preparation checkpoint (requires 3 + 4)

**Phase 3 — Vector Store Integration (Tasks 6–9)**
- 6: Qdrant collection management (requires 2 + 5)
- 7: Setup ingestion to vector store (requires 6)
- 8: Initial data load, 500+ setups (requires 6 + 7)
- 9: Vector store checkpoint (requires 6 + 7 + 8)

**Phase 4 — RAG Retrieval Service (Tasks 10–14)**
- 10: Retrieval endpoint (requires 9)
- 11: RAG metrics computation (requires 10)
- 12: Ingestion endpoint (requires 9)
- 13: Performance monitoring (requires 10)
- 14: RAG service checkpoint (requires 10 + 11 + 12 + 13)

**Phase 5 — ML Pipeline Integration (Tasks 15–18)**
- 15: AlgoRAG client library (requires 14)
- 16: Confluence Scorer augmentation (requires 15)
- 17: A/B testing framework (requires 16)
- 18: ML integration checkpoint (requires 15 + 16 + 17)

**Phase 6 — LLM Integration (Tasks 19–20)**
- 19: RAG-grounded LLM reasoning (requires 14; independent of Phase 5)
- 20: LLM integration checkpoint (requires 19)

**Phase 7 — Real-Time Ingestion (Tasks 21–22)**
- 21: Trade-close event handler and async pipeline (requires 3 + 12)
- 22: Real-time ingestion checkpoint (requires 21)

**Phase 8 — Dashboard Integration (Tasks 23–24)**
- 23: Similar setups panel, backend + frontend (requires 14)
- 24: Dashboard checkpoint (requires 23)

**Phase 9 — Monitoring & Observability (Tasks 25–27)**
- 25: Prometheus metrics and Grafana dashboards (requires 14)
- 26: Alerting (requires 25)
- 27: Monitoring checkpoint (requires 25 + 26)

**Phase 10 — Validation & Production Readiness (Tasks 28–30)**
- 28: Offline evaluation — correlation analysis and backtest (requires 18 + 20 + 22 + 24 + 27)
- 29: Production deployment, runbooks, documentation (requires 28)
- 30: Final checkpoint — production readiness (requires 28 + 29)

### Critical Path
```
1 → 2 → 6 → 7 → 8 → 9 → 10 → 11 → 14 → 15 → 16 → 17 → 18 → 28 → 29 → 30
```
(Phase 2's enrichment/embedding work runs in parallel with Phase 1 and feeds into 6 alongside it — see Parallel Execution Opportunities.)

### Parallel Execution Opportunities
- **Phase 1 and Phase 2 have no dependency on each other** — Qdrant/service scaffolding (1–2) and historical setup enrichment/embedding (3–5) can proceed simultaneously, both feeding into Vector Store Integration (6–9)
- **After 14 (RAG Service Checkpoint)**: Phases 5 (ML Pipeline), 6 (LLM Integration), 8 (Dashboard), and 9 (Monitoring) can all proceed in parallel — none depends on another
- **Phase 7 (Real-Time Ingestion)** only needs 3 (Enrichment) and 12 (Ingestion Endpoint), so it can start before the full RAG Service Checkpoint (14) lands
- **Phase 10 (Validation)** is the sync point — it gates on every other phase completing

### Testing Dependencies
- Task 2: infrastructure tests cover Task 1 (Qdrant container health, service health check)
- Task 5: data-prep tests cover Tasks 3–4 (enrichment correctness, embedding dimensions/NaN checks)
- Task 9: vector-store tests cover Tasks 6–8 (collection schema, ingestion, initial load quality)
- Task 14: RAG service tests cover Tasks 10–13 (retrieval, re-ranking, metrics, ingestion endpoint, latency)
- Task 18: ML integration tests cover Tasks 15–17 (client, augmented scorer, A/B split)
- Task 20: LLM integration tests cover Task 19 (RAG-grounded reasoning, fallback behaviour)
- Task 22: real-time ingestion tests cover Task 21 (event-to-indexed latency, retry logic)
- Task 24: dashboard tests cover Task 23 (panel rendering, API integration, error states)
- Task 27: monitoring tests cover Tasks 25–26 (metric emission, alert firing)
- Task 30: aggregate validation across Tasks 28–29 plus every prior checkpoint, gating production readiness

---

## Notes

- **Tasks marked with `*` are optional** and can be skipped for faster MVP delivery
- **TDD Methodology**: All implementation sub-tasks follow RED → GREEN → REFACTOR pattern
- **Each task references specific requirements** for traceability (e.g., FR-RAG-1, NFR-RAG-2)
- **Checkpoints ensure incremental validation** at reasonable breaks
- **Integration points** with existing platform (Tasks 22, 27, 35) are clearly marked
- **Graceful degradation** is built into all integration points (RAG failures don't break existing features)
- **Performance targets** are validated through tests and monitoring

---

## Success Metrics

### MVP (Minimum Viable AlgoRAG)
- ✅ 500+ historical setups indexed
- ✅ Retrieval latency < 100ms (p95)
- ✅ Similarity correlates with outcome (r > 0.5)
- ✅ LLM reasoning cites actual examples
- ✅ Sharpe improvement ≥ 0.1 vs. baseline

### Production Ready
- ✅ 2000+ historical setups indexed
- ✅ Retrieval latency < 50ms (p50)
- ✅ A/B test shows statistical significance (p < 0.05)
- ✅ Dashboard integration complete
- ✅ Monitoring and alerting live
- ✅ Documentation and runbooks complete

---

## Dependencies

### Completed (Phase 0)
- Task 10: HTF projection extractor (reused in enrichment)
- Task 11: Candle feature extractor (reused in enrichment)
- Task 12: Zone feature extractor (reused in enrichment)
- Task 13: Session feature extractor (reused in time window classification)
- Task 15: Trade journal importer (source of historical setups)
- Task 16: Edge analysis service (outcome metrics)

### Integration Points (Phase 1-2)
- Task 22: Confluence Scorer (retrain with RAG features)
- Task 27: LLM reasoning (RAG-grounded generation)
- Task 35: Web dashboard (similar setups panel)

---

## Testing Strategy

### Unit Tests
- All core logic (embedding generation, re-ranking, metrics computation)
- Edge cases and error conditions
- Numerical stability and validation

### Integration Tests
- End-to-end flows (enrichment → embedding → ingestion → retrieval)
- Service-to-service communication (RAG client → RAG service → Qdrant)
- Error handling and retry logic

### Performance Tests
- Retrieval latency under load
- Ingestion throughput
- Concurrent request handling

### Validation Tests
- Similarity-outcome correlation
- Backtest performance improvement
- False positive rate
- Diversity of results

---

## Risk Mitigation

### Insufficient Historical Data
- Start with 500 setups (MVP threshold)
- Continuously add new setups via real-time ingestion
- Monitor data quality and coverage

### Retrieval Doesn't Improve Performance
- A/B test before rollout (Task 17)
- Keep baseline as fallback
- Measure in backtest first (Task 28)

### Latency Too High
- Use ANN algorithms in Qdrant
- Cache frequent queries
- Set timeout with fallback to baseline

### Integration Breaks Existing Features
- RAG is additive not replacement
- Feature flags for gradual rollout
- Comprehensive integration tests
- Graceful degradation on failures
