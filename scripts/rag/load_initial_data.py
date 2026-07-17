#!/usr/bin/env python3
"""
Load initial historical trading setups into AlgoRAG Qdrant vector store.

Usage:
    python scripts/rag/load_initial_data.py [--limit N] [--output OUTPUT_PATH] [--dry-run]

Steps:
1. Load historical trades from MongoDB (falls back to sample data if unavailable)
2. Enrich each trade with HTF/PD array/session context
3. Generate 528-dim multi-modal embeddings
4. Ingest into Qdrant vector store
5. Generate and save data quality report

This script follows the TDD process and implements FR-RAG-1: Historical Setup Storage.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

# Ensure workspace root is on the path
_WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, _WORKSPACE_ROOT)

from scripts.rag.utils.setup_enricher import SetupEnricher, EnrichedSetup
from services.algorag.embedding_models import get_embedding_model, NarrativeEmbeddingModel
from services.algorag.ingestion_service import IngestionService, BatchIngestionResult
from services.algorag.qdrant_client import QdrantClientWrapper

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EMBEDDING_DIM_NARRATIVE = 384
EMBEDDING_DIM_STRUCTURED = 128
EMBEDDING_DIM_TEMPORAL = 16
EMBEDDING_DIM_COMBINED = 528

# Fixed projection matrix for deterministic structured embedding generation
# Use np.random with fixed seed for reproducibility
_RNG = np.random.default_rng(42)
_PROJECTION_MATRIX = _RNG.standard_normal((64, 128)).astype(np.float32)


# ---------------------------------------------------------------------------
# Embedding generation functions
# ---------------------------------------------------------------------------


def build_structured_embedding(enriched_setup: EnrichedSetup) -> np.ndarray:
    """Extract 64 structured features from EnrichedSetup and project to 128-dim.

    Features extracted (64 total):
    - HTF metrics (4): htf_high_proximity_pct, htf_low_proximity_pct, htf_body_pct, htf_close_position
    - HTF bias one-hot (3): BULLISH/BEARISH/NEUTRAL
    - PD array flags (4): bos_detected, choch_detected, fvg_present, liquidity_sweep
    - Swing distances (2): swing_high_distance, swing_low_distance
    - Session (2): time_window_weight, is_killzone
    - Outcome (3): r_multiple (normalized), WIN/LOSS one-hot (2)
    - Confluence (1): confluence_count
    - Remaining padded to 64 with zeros

    All features normalised to [0, 1] range before projection.

    Args:
        enriched_setup: EnrichedSetup instance with all fields populated.

    Returns:
        128-dim float32 numpy array with no NaN or Inf values.
    """
    features = np.zeros(64, dtype=np.float32)

    # HTF metrics (4 features, dims 0-3)
    features[0] = enriched_setup.htf_high_proximity_pct / 100.0
    features[1] = enriched_setup.htf_low_proximity_pct / 100.0
    features[2] = enriched_setup.htf_body_pct / 100.0
    features[3] = enriched_setup.htf_close_position

    # HTF bias one-hot (3 features, dims 4-6)
    bias_map = {"BULLISH": 0, "BEARISH": 1, "NEUTRAL": 2}
    bias_idx = bias_map.get(enriched_setup.htf_open_bias, 2)
    features[4 + bias_idx] = 1.0

    # PD array flags (4 features, dims 7-10)
    features[7] = 1.0 if enriched_setup.bos_detected else 0.0
    features[8] = 1.0 if enriched_setup.choch_detected else 0.0
    features[9] = 1.0 if enriched_setup.fvg_present else 0.0
    features[10] = 1.0 if enriched_setup.liquidity_sweep else 0.0

    # Swing distances (2 features, dims 11-12, clip to [0, 1] after normalization)
    features[11] = np.clip(enriched_setup.swing_high_distance / 0.01, 0.0, 1.0)
    features[12] = np.clip(enriched_setup.swing_low_distance / 0.01, 0.0, 1.0)

    # Session features (2 features, dims 13-14)
    features[13] = enriched_setup.time_window_weight
    features[14] = 1.0 if enriched_setup.is_killzone else 0.0

    # Outcome (3 features, dims 15-17)
    # r_multiple: normalize to [0, 1] using tanh to handle both positive and negative values
    features[15] = (np.tanh(enriched_setup.r_multiple / 10.0) + 1.0) / 2.0
    # WIN/LOSS one-hot (2 features)
    features[16] = 1.0 if enriched_setup.outcome_result == "WIN" else 0.0
    features[17] = 1.0 if enriched_setup.outcome_result == "LOSS" else 0.0

    # Confluence count (1 feature, dim 18, normalize by dividing by max expected count of 6)
    features[18] = np.clip(enriched_setup.confluence_count / 6.0, 0.0, 1.0)

    # Remaining features (dims 19-63) are already zeros (reserved)

    # Project 64-dim to 128-dim using fixed projection matrix, then apply tanh normalization
    projected = np.dot(features, _PROJECTION_MATRIX)
    normalized = np.tanh(projected).astype(np.float32)

    return normalized


def build_temporal_embedding(timestamp: datetime) -> np.ndarray:
    """Generate 16-dim cyclical temporal encoding from timestamp.

    Encoding uses sin/cos transforms for periodicity:
    - hour_sin, hour_cos (dims 0-1)
    - day_of_week_sin, day_of_week_cos (dims 2-3)
    - month_sin, month_cos (dims 4-5)
    - dims 6-15: zeros (reserved for future features)

    Args:
        timestamp: UTC-aware datetime object.

    Returns:
        16-dim float32 numpy array with cyclical encoding in dims 0-5, zeros in dims 6-15.
    """
    embedding = np.zeros(16, dtype=np.float32)

    hour = timestamp.hour
    day_of_week = timestamp.weekday()  # 0=Monday, 6=Sunday
    month = timestamp.month

    # Cyclical encoding with sin/cos
    embedding[0] = np.sin(2 * np.pi * hour / 24)
    embedding[1] = np.cos(2 * np.pi * hour / 24)
    embedding[2] = np.sin(2 * np.pi * day_of_week / 5)  # 5 trading days
    embedding[3] = np.cos(2 * np.pi * day_of_week / 5)
    embedding[4] = np.sin(2 * np.pi * month / 12)
    embedding[5] = np.cos(2 * np.pi * month / 12)

    # dims 6-15 remain zeros (reserved)

    return embedding


def build_combined_embedding(
    narrative: str,
    enriched_setup: EnrichedSetup,
    narrative_model: NarrativeEmbeddingModel,
) -> np.ndarray:
    """Generate 528-dim combined multi-modal embedding.

    Combines three embedding types with weights:
    - Narrative (384-dim) * 0.4
    - Structured (128-dim) * 0.4
    - Temporal (16-dim) * 0.2

    Args:
        narrative: Narrative text string.
        enriched_setup: EnrichedSetup instance.
        narrative_model: Loaded NarrativeEmbeddingModel instance.

    Returns:
        528-dim float32 numpy array with no NaN or Inf values.
    """
    # Narrative embedding (384-dim)
    narrative_emb = narrative_model.encode(narrative)  # already float32
    narrative_weighted = narrative_emb * 0.4

    # Structured embedding (128-dim)
    structured_emb = build_structured_embedding(enriched_setup)
    structured_weighted = structured_emb * 0.4

    # Temporal embedding (16-dim)
    temporal_emb = build_temporal_embedding(enriched_setup.timestamp)
    temporal_weighted = temporal_emb * 0.2

    # Concatenate: 384 + 128 + 16 = 528
    combined = np.concatenate([narrative_weighted, structured_weighted, temporal_weighted])

    return combined.astype(np.float32)


# ---------------------------------------------------------------------------
# Data quality report generation
# ---------------------------------------------------------------------------


def generate_data_quality_report(
    successful_setups: List[Dict[str, Any]],
    errors: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Generate data quality report from enrichment results.

    Args:
        successful_setups: List of successfully enriched setup dicts.
        errors: List of error dicts with 'trade_id' and 'error' keys.

    Returns:
        Dict with keys: total, successful, failed, error_rate_pct, avg_r_multiple,
        win_rate, instruments.
    """
    successful_count = len(successful_setups)
    failed_count = len(errors)
    total = successful_count + failed_count

    if total == 0:
        return {
            "total": 0,
            "successful": 0,
            "failed": 0,
            "error_rate_pct": 0.0,
            "avg_r_multiple": 0.0,
            "win_rate": 0.0,
            "instruments": [],
        }

    error_rate_pct = (failed_count / total) * 100.0 if total > 0 else 0.0

    # Compute avg_r_multiple and win_rate from successful setups
    if successful_count > 0:
        r_multiples = [s.get("r_multiple", 0.0) for s in successful_setups]
        avg_r_multiple = sum(r_multiples) / len(r_multiples)

        wins = sum(1 for s in successful_setups if s.get("outcome_result") == "WIN")
        win_rate = wins / successful_count
    else:
        avg_r_multiple = 0.0
        win_rate = 0.0

    # Collect unique instruments
    instruments = list(set(s.get("instrument", "UNKNOWN") for s in successful_setups))

    return {
        "total": total,
        "successful": successful_count,
        "failed": failed_count,
        "error_rate_pct": error_rate_pct,
        "avg_r_multiple": avg_r_multiple,
        "win_rate": win_rate,
        "instruments": instruments,
    }


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------


class DataLoader:
    """Loads historical trades from MongoDB, with fallback to sample data."""

    def load_from_journal(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Load historical trades from MongoDB trade_journal, fallback to sample data.

        Attempts to connect to MongoDB and load from trade_journal collection.
        On any error (connection, auth, etc.), falls back silently to sample trades.

        Args:
            limit: Maximum number of trades to load.

        Returns:
            List of trade dicts (at least 1, respecting limit).
        """
        try:
            # Attempt MongoDB connection and query
            from pymongo import MongoClient
            from pymongo.errors import PyMongoError

            mongo_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
            client = MongoClient(mongo_uri, serverSelectionTimeoutMS=2000)
            db = client["trading_db"]
            collection = db["trade_journal"]

            # Verify connection
            client.server_info()

            # Load trades
            trades = list(collection.find().limit(limit))
            if trades:
                logger.info(f"Loaded {len(trades)} trades from MongoDB trade_journal")
                return trades
            else:
                logger.warning("MongoDB trade_journal is empty, using sample data")
                return self._load_sample_trades(limit)

        except (ImportError, PyMongoError, Exception) as e:
            logger.warning(f"MongoDB unavailable ({e}), using sample data")
            return self._load_sample_trades(limit)

    def load_candles_for_trade(self, trade: Dict[str, Any]) -> Tuple[List[Dict], List[Dict]]:
        """Load candles and HTF candles for a trade.

        In production, this would query TimescaleDB. For MVP, generates sample candles.

        Args:
            trade: Trade dict with entry time.

        Returns:
            Tuple of (candles, htf_candles) as lists of dicts.
        """
        entry_time = trade.get("entry", {}).get("time") or trade.get("entry_time")
        candles = self._generate_sample_candles(entry_time, n=20)
        htf_candles = self._generate_sample_candles(entry_time, n=5)
        return candles, htf_candles

    def _load_sample_trades(self, limit: int) -> List[Dict[str, Any]]:
        """Generate sample trades for testing (fallback when MongoDB unavailable)."""
        base_time = "2024-01-15T09:15:00Z"
        trades = []
        for i in range(min(limit, 10)):  # Cap sample data at 10
            entry_price = 1.5000 + i * 0.0010
            trades.append({
                "trade_id": f"TRD-SAMPLE-{i + 1:03d}",
                "instrument": "EURUSD",
                "direction": "BUY" if i % 2 == 0 else "SELL",
                "entry": {"time": base_time, "price": entry_price},
                "exit": {
                    "time": "2024-01-15T11:00:00Z",
                    "price": entry_price + 0.0050,
                },
                "risk": {
                    "stop_loss": entry_price - 0.0020,
                    "take_profit": entry_price + 0.0060,
                    "position_size": 1.0,
                },
                "outcome": {
                    "r_multiple": 2.5 if i % 2 == 0 else -1.0,
                    "pnl_usd": 250.0,
                    "outcome_result": "WIN" if i % 2 == 0 else "LOSS",
                },
            })
        return trades

    def _generate_sample_candles(
        self, entry_time: Optional[str], n: int = 20
    ) -> List[Dict[str, Any]]:
        """Generate synthetic candles for testing."""
        candles = []
        base_price = 1.5000
        for i in range(n):
            open_ = base_price + i * 0.0001
            candles.append({
                "time": entry_time or "2024-01-15T09:00:00Z",
                "open": open_,
                "high": open_ + 0.0010,
                "low": open_ - 0.0005,
                "close": open_ + 0.0005,
                "volume": 1000,
            })
        return candles


# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------


async def main(
    limit: int = 100,
    output_path: str = "data/enriched_setups.json",
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Main pipeline: load → enrich → embed → ingest → report.

    Args:
        limit: Maximum number of trades to process.
        output_path: Path to save enriched setups JSON.
        dry_run: If True, skip Qdrant ingestion (useful for testing).

    Returns:
        Data quality report dict.
    """
    logger.info(f"Starting AlgoRAG initial data load (limit={limit}, dry_run={dry_run})")

    # Initialize components
    enricher = SetupEnricher(htf_timeframe="H1")
    narrative_model = get_embedding_model()
    data_loader = DataLoader()

    # Load trades
    logger.info("Loading historical trades...")
    trades = data_loader.load_from_journal(limit)
    logger.info(f"Loaded {len(trades)} trades")

    # Enrich and embed
    enriched_setups: List[Dict[str, Any]] = []
    embeddings: List[np.ndarray] = []
    errors: List[Dict[str, Any]] = []

    logger.info("Enriching trades and generating embeddings...")
    for i, trade in enumerate(trades):
        try:
            # Load candles
            candles, htf_candles = data_loader.load_candles_for_trade(trade)

            # Enrich
            enriched = enricher.enrich(trade, candles, htf_candles)

            # Generate embedding
            embedding = build_combined_embedding(
                enriched.narrative, enriched, narrative_model
            )

            # Validate embedding
            assert embedding.shape == (EMBEDDING_DIM_COMBINED,), (
                f"Invalid embedding shape: {embedding.shape}"
            )
            assert not np.isnan(embedding).any(), "NaN in embedding"
            assert not np.isinf(embedding).any(), "Inf in embedding"

            enriched_setups.append(enriched.model_dump(mode="json"))
            embeddings.append(embedding)

            if (i + 1) % 10 == 0:
                logger.info(f"Processed {i + 1}/{len(trades)} trades")

        except Exception as e:
            logger.warning(f"Failed to enrich trade {trade.get('trade_id')}: {e}")
            errors.append({"trade_id": trade.get("trade_id"), "error": str(e)})

    logger.info(f"Enriched {len(enriched_setups)} setups, {len(errors)} errors")

    # Save enriched setups to JSON
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w") as f:
        json.dump(enriched_setups, f, indent=2, default=str)
    logger.info(f"Saved enriched setups to {output_path}")

    # Ingest to Qdrant (unless dry_run)
    if not dry_run and enriched_setups:
        logger.info("Ingesting to Qdrant vector store...")
        wrapper = QdrantClientWrapper()
        await wrapper.ensure_collection()

        ingestion_service = IngestionService(wrapper=wrapper)
        items = [
            (setup, emb.tolist()) for setup, emb in zip(enriched_setups, embeddings)
        ]
        result: BatchIngestionResult = await ingestion_service.ingest_batch(items)

        logger.info(
            f"Ingestion complete: {result.successful}/{result.total} successful, "
            f"{result.failed} failed, {result.skipped} skipped"
        )

        if result.errors:
            for trade_id, error in result.errors[:5]:  # Log first 5 errors
                logger.warning(f"Ingestion error for {trade_id}: {error}")

        await wrapper.close()
    else:
        if dry_run:
            logger.info("Dry run mode — skipping Qdrant ingestion")
        else:
            logger.warning("No enriched setups to ingest")

    # Generate quality report
    report = generate_data_quality_report(enriched_setups, errors)
    logger.info("\n" + "=" * 60)
    logger.info("DATA QUALITY REPORT")
    logger.info("=" * 60)
    logger.info(f"Total trades processed:  {report['total']}")
    logger.info(f"Successfully enriched:   {report['successful']}")
    logger.info(f"Failed:                  {report['failed']}")
    logger.info(f"Error rate:              {report['error_rate_pct']:.2f}%")
    logger.info(f"Avg R-multiple:          {report['avg_r_multiple']:.2f}")
    logger.info(f"Win rate:                {report['win_rate']:.2%}")
    logger.info(f"Instruments found:       {', '.join(report['instruments'])}")
    logger.info("=" * 60)

    # Save quality report
    report_path = output_path.replace(".json", "_quality_report.json")
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
    logger.info(f"Saved quality report to {report_path}")

    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Load initial historical trading setups into AlgoRAG vector store."
    )
    parser.add_argument("--limit", type=int, default=100, help="Max trades to load")
    parser.add_argument(
        "--output", default="data/enriched_setups.json", help="Output JSON path"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Skip Qdrant ingestion"
    )
    args = parser.parse_args()

    asyncio.run(main(args.limit, args.output, args.dry_run))
