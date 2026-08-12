"""
Initial Data Loader — loads 500+ historical setups from trade journal,
enriches, embeds, and ingests to Qdrant with data quality reporting.

This script implements Task 8.1 of the AlgoRAG enhancement:
- Load historical trade data from MongoDB trade_journal collection
- Enrich with HTF structure, PD arrays, and session context
- Generate 528-dim embeddings using existing pipeline
- Ingest to Qdrant vector store
- Generate comprehensive data quality report

Usage:
    python scripts/rag/load_initial_data.py --mongo-uri mongodb://localhost:27017
    
    # With custom parameters
    python scripts/rag/load_initial_data.py \
        --mongo-uri mongodb://localhost:27017 \
        --database agentictrader \
        --min-setups 500 \
        --batch-size 50 \
        --output-dir data/rag/

Requirements: FR-RAG-1
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import motor.motor_asyncio as motor_asyncio
from pydantic import BaseModel, Field, field_validator

# Ensure workspace root is importable
_WORKSPACE_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")
)
if _WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, _WORKSPACE_ROOT)

from ml.features.htf_projections import HTFProjectionExtractor
from scripts.rag.utils.setup_enricher import EnrichedSetup, SetupEnricher
from services.algorag.config import settings
from services.algorag.embedding_models import EmbeddingGenerator
from services.algorag.ingestion_service import (
    BatchIngestionResult,
    IngestionService,
)
from services.algorag.qdrant_client import QdrantClientWrapper

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class LoadingProgress(BaseModel):
    """Progress update during data loading."""
    
    phase: str = Field(..., description="Current processing phase")
    processed: int = Field(..., ge=0, description="Number of items processed")
    total: int = Field(..., ge=0, description="Total items to process")
    percent_complete: float = Field(
        default=0.0, ge=0.0, le=100.0, description="Completion percentage"
    )
    current_item: Optional[str] = Field(None, description="Current item being processed")
    
    def __init__(self, **data):
        super().__init__(**data)
        if self.processed > self.total:
            raise ValueError(f"Processed ({self.processed}) cannot exceed total ({self.total})")
        self.percent_complete = (self.processed / self.total * 100.0) if self.total > 0 else 0.0


class DataQualityReport(BaseModel):
    """Comprehensive data quality report for loaded setups."""
    
    timestamp: datetime = Field(..., description="Report generation timestamp")
    total_setups: int = Field(..., ge=0, description="Total setups processed")
    successfully_ingested: int = Field(..., ge=0, description="Successfully ingested to Qdrant")
    failed_ingestion: int = Field(..., ge=0, description="Failed to ingest")
    error_rate_pct: float = Field(..., ge=0.0, le=100.0, description="Error rate percentage")
    
    # Distributions
    instrument_distribution: Dict[str, int] = Field(default_factory=dict)
    outcome_distribution: Dict[str, int] = Field(default_factory=dict)
    time_window_distribution: Dict[str, int] = Field(default_factory=dict)
    
    # Quality metrics
    average_confluence_count: float = Field(..., ge=0.0, description="Mean confluence factors")
    r_multiple_stats: Dict[str, float] = Field(default_factory=dict)
    
    # Errors
    errors: List[str] = Field(default_factory=list, description="Error messages")
    
    @field_validator('error_rate_pct')
    @classmethod
    def validate_error_rate(cls, v: float) -> float:
        if v < 0.0 or v > 100.0:
            raise ValueError(f"Error rate must be 0-100%, got {v}")
        return v


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class DataLoadingError(Exception):
    """Raised when critical data loading operations fail."""
    pass


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


async def fetch_candle_data(trade: Dict[str, Any]) -> Tuple[List[Dict], List[Dict]]:
    """Fetch candle data for a trade from TimescaleDB.
    
    This is a placeholder implementation. In a real system, this would:
    1. Extract entry_time and instrument from trade
    2. Query TimescaleDB for M5 candles around entry time
    3. Query TimescaleDB for H1 candles for HTF context
    4. Return (m5_candles, h1_candles)
    
    For testing purposes, returns empty lists.
    """
    # TODO: Implement actual TimescaleDB queries
    # For now, return empty candle lists for testing
    return [], []


# ---------------------------------------------------------------------------
# Main loader class
# ---------------------------------------------------------------------------


class InitialDataLoader:
    """Loads historical trading setups from MongoDB and ingests to Qdrant."""
    
    def __init__(
        self,
        *,
        db: motor_asyncio.AsyncIOMotorDatabase,
        enricher: Optional[SetupEnricher] = None,
        embedding_generator: Optional[EmbeddingGenerator] = None,
        ingestion_service: Optional[IngestionService] = None,
        qdrant_wrapper: Optional[QdrantClientWrapper] = None,
        min_setups: int = 500,
        batch_size: int = 50,
        progress_callback: Optional[Callable[[LoadingProgress], Any]] = None,
    ):
        """Initialize the data loader.
        
        Args:
            db: MongoDB database instance
            enricher: Setup enrichment service (created if None)
            embedding_generator: Embedding generation service (created if None)
            ingestion_service: Qdrant ingestion service (created if None)
            qdrant_wrapper: Qdrant client wrapper (created if None)
            min_setups: Minimum number of setups to load (default: 500)
            batch_size: Batch size for processing (default: 50)
            progress_callback: Optional callback for progress updates
        """
        self.db = db
        self.trade_collection = db.trade_journal
        self.min_setups = min_setups
        self.batch_size = batch_size
        self.progress_callback = progress_callback
        
        # Initialize services
        self.enricher = enricher or SetupEnricher(htf_timeframe="H1")
        self.embedding_generator = embedding_generator or EmbeddingGenerator()
        self.qdrant_wrapper = qdrant_wrapper or QdrantClientWrapper()
        self.ingestion_service = ingestion_service or IngestionService(
            wrapper=self.qdrant_wrapper,
            batch_size=batch_size,
        )
    
    async def load_historical_setups(self) -> List[Dict[str, Any]]:
        """Load historical trading setups from MongoDB trade_journal collection.
        
        Returns:
            List of trade documents from MongoDB
            
        Raises:
            DataLoadingError: If unable to load minimum required setups
        """
        logger.info("Loading historical setups from trade_journal collection...")
        
        try:
            # Load all trades from collection
            cursor = self.trade_collection.find({})
            trades = await cursor.to_list(length=None)
            
            logger.info(f"Loaded {len(trades)} trades from database")
            
            if len(trades) < self.min_setups:
                raise DataLoadingError(
                    f"Insufficient historical data: found {len(trades)} trades, "
                    f"need at least {self.min_setups}"
                )
            
            return trades
            
        except Exception as exc:
            logger.error(f"Failed to load historical setups: {exc}")
            raise DataLoadingError(f"Database query failed: {exc}") from exc
    
    async def enrich_setups(self, trades: List[Dict[str, Any]]) -> List[EnrichedSetup]:
        """Enrich trades with HTF structure, PD arrays, and session context.
        
        Args:
            trades: List of raw trade documents from MongoDB
            
        Returns:
            List of enriched setups
        """
        logger.info(f"Enriching {len(trades)} setups...")
        
        enriched_setups = []
        errors = 0
        
        for i, trade in enumerate(trades):
            try:
                # Fetch candle data for this trade
                candles, htf_candles = await fetch_candle_data(trade)
                
                # Enrich the setup
                enriched = self.enricher.enrich(trade, candles, htf_candles)
                enriched_setups.append(enriched)
                
                # Report progress
                if self.progress_callback and (i + 1) % 10 == 0:
                    progress = LoadingProgress(
                        phase="enrichment",
                        processed=i + 1,
                        total=len(trades),
                        current_item=trade.get("trade_id", "unknown"),
                    )
                    await self.progress_callback(progress)
                    
            except Exception as exc:
                logger.warning(f"Failed to enrich trade {trade.get('trade_id', 'unknown')}: {exc}")
                errors += 1
                continue
        
        # Final progress update
        if self.progress_callback:
            progress = LoadingProgress(
                phase="enrichment",
                processed=len(enriched_setups),
                total=len(trades),
            )
            await self.progress_callback(progress)
        
        logger.info(f"Successfully enriched {len(enriched_setups)} setups ({errors} errors)")
        return enriched_setups
    
    async def generate_embeddings(
        self, enriched_setups: List[EnrichedSetup]
    ) -> List[Dict[str, Any]]:
        """Generate 528-dim embeddings for enriched setups.
        
        Args:
            enriched_setups: List of enriched setup objects
            
        Returns:
            List of dicts with 'setup' and 'embedding' keys
        """
        logger.info(f"Generating embeddings for {len(enriched_setups)} setups...")
        
        setup_embeddings = []
        errors = 0
        
        for i, setup in enumerate(enriched_setups):
            try:
                # Generate 528-dim embedding
                embedding = await self.embedding_generator.generate_embedding(setup.model_dump())
                
                setup_embeddings.append({
                    "setup": setup.model_dump(),
                    "embedding": embedding,
                })
                
                # Report progress
                if self.progress_callback and (i + 1) % 20 == 0:
                    progress = LoadingProgress(
                        phase="embedding",
                        processed=i + 1,
                        total=len(enriched_setups),
                        current_item=setup.trade_id,
                    )
                    await self.progress_callback(progress)
                    
            except Exception as exc:
                logger.warning(f"Failed to generate embedding for {setup.trade_id}: {exc}")
                errors += 1
                continue
        
        # Final progress update
        if self.progress_callback:
            progress = LoadingProgress(
                phase="embedding",
                processed=len(setup_embeddings),
                total=len(enriched_setups),
            )
            await self.progress_callback(progress)
        
        logger.info(f"Successfully generated {len(setup_embeddings)} embeddings ({errors} errors)")
        return setup_embeddings
    
    async def ingest_to_qdrant(
        self, setup_embeddings: List[Dict[str, Any]]
    ) -> BatchIngestionResult:
        """Ingest setups with embeddings to Qdrant vector store.
        
        Args:
            setup_embeddings: List of setup-embedding pairs
            
        Returns:
            BatchIngestionResult with ingestion statistics
        """
        logger.info(f"Ingesting {len(setup_embeddings)} setups to Qdrant...")
        
        try:
            # Prepare data for ingestion service
            items = []
            for item in setup_embeddings:
                items.append((item["setup"], item["embedding"]))
            
            # Ingest in batches
            result = await self.ingestion_service.ingest_batch(items)
            
            logger.info(
                f"Ingestion complete: {result.successful}/{result.total} successful, "
                f"{result.failed} failed, {result.skipped} skipped"
            )
            
            return result
            
        except Exception as exc:
            logger.error(f"Qdrant ingestion failed: {exc}")
            raise DataLoadingError(f"Vector store ingestion failed: {exc}") from exc
    
    async def generate_data_quality_report(
        self,
        enriched_setups: List[Dict[str, Any]],
        ingestion_result: BatchIngestionResult,
    ) -> DataQualityReport:
        """Generate comprehensive data quality report.
        
        Args:
            enriched_setups: List of enriched setup dictionaries
            ingestion_result: Result from Qdrant ingestion
            
        Returns:
            DataQualityReport with statistics and analysis
        """
        logger.info("Generating data quality report...")
        
        total_setups = len(enriched_setups)
        
        # Calculate error rate
        error_rate_pct = (ingestion_result.failed / total_setups * 100.0) if total_setups > 0 else 0.0
        
        # Analyze distributions
        instrument_dist = {}
        outcome_dist = {}
        time_window_dist = {}
        confluence_counts = []
        r_multiples = []
        
        for setup in enriched_setups:
            # Instrument distribution
            instrument = setup.get("instrument", "UNKNOWN")
            instrument_dist[instrument] = instrument_dist.get(instrument, 0) + 1
            
            # Outcome distribution
            outcome = setup.get("outcome_result", "UNKNOWN")
            outcome_dist[outcome] = outcome_dist.get(outcome, 0) + 1
            
            # Time window distribution
            time_window = setup.get("time_window", "UNKNOWN")
            time_window_dist[time_window] = time_window_dist.get(time_window, 0) + 1
            
            # Confluence and R-multiple stats
            confluence_counts.append(setup.get("confluence_count", 0))
            r_multiples.append(setup.get("r_multiple", 0.0))
        
        # Calculate R-multiple statistics
        r_multiple_stats = {}
        if r_multiples:
            r_multiple_stats = {
                "mean": sum(r_multiples) / len(r_multiples),
                "median": sorted(r_multiples)[len(r_multiples) // 2],
                "std": (
                    sum((x - sum(r_multiples) / len(r_multiples)) ** 2 for x in r_multiples)
                    / len(r_multiples)
                ) ** 0.5,
                "min": min(r_multiples),
                "max": max(r_multiples),
            }
        
        # Calculate average confluence count
        avg_confluence = sum(confluence_counts) / len(confluence_counts) if confluence_counts else 0.0
        
        # Collect error messages
        error_messages = [f"{trade_id}: {error}" for trade_id, error in ingestion_result.errors]
        
        return DataQualityReport(
            timestamp=datetime.now(timezone.utc),
            total_setups=total_setups,
            successfully_ingested=ingestion_result.successful,
            failed_ingestion=ingestion_result.failed,
            error_rate_pct=error_rate_pct,
            instrument_distribution=instrument_dist,
            outcome_distribution=outcome_dist,
            time_window_distribution=time_window_dist,
            average_confluence_count=avg_confluence,
            r_multiple_stats=r_multiple_stats,
            errors=error_messages,
        )
    
    async def save_report(self, report: DataQualityReport, output_path: Path) -> None:
        """Save data quality report to JSON file.
        
        Args:
            report: DataQualityReport to save
            output_path: Path where to save the report
        """
        logger.info(f"Saving data quality report to {output_path}")
        
        # Ensure directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Convert to dict and save as JSON
        report_dict = report.model_dump()
        
        # Convert datetime to ISO string for JSON serialization
        report_dict["timestamp"] = report.timestamp.isoformat()
        
        with open(output_path, 'w') as f:
            json.dump(report_dict, f, indent=2, sort_keys=True)
        
        logger.info(f"Report saved to {output_path}")
    
    async def run(self) -> DataQualityReport:
        """Run the complete data loading pipeline.
        
        Returns:
            DataQualityReport with comprehensive statistics
            
        Raises:
            DataLoadingError: If critical operations fail
        """
        logger.info("Starting initial data loading pipeline...")
        
        try:
            # Step 1: Load historical trades
            trades = await self.load_historical_setups()
            
            # Step 2: Enrich with HTF/PD arrays/session context
            enriched_setups = await self.enrich_setups(trades)
            
            # Step 3: Generate embeddings
            setup_embeddings = await self.generate_embeddings(enriched_setups)
            
            # Step 4: Ingest to Qdrant
            ingestion_result = await self.ingest_to_qdrant(setup_embeddings)
            
            # Step 5: Generate quality report
            enriched_dicts = [setup.model_dump() for setup in enriched_setups]
            report = await self.generate_data_quality_report(enriched_dicts, ingestion_result)
            
            logger.info("Data loading pipeline completed successfully")
            return report
            
        except Exception as exc:
            logger.error(f"Data loading pipeline failed: {exc}")
            raise DataLoadingError(f"Pipeline execution failed: {exc}") from exc


# ---------------------------------------------------------------------------
# CLI interface
# ---------------------------------------------------------------------------


async def main():
    """Main entry point for the data loading script."""
    parser = argparse.ArgumentParser(description="Load initial AlgoRAG data from trade journal")
    parser.add_argument(
        "--mongo-uri",
        default="mongodb://localhost:27017",
        help="MongoDB connection URI"
    )
    parser.add_argument(
        "--database",
        default="agentictrader",
        help="MongoDB database name"
    )
    parser.add_argument(
        "--min-setups",
        type=int,
        default=500,
        help="Minimum number of setups to load"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=50,
        help="Batch size for processing"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/rag"),
        help="Output directory for reports and data"
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging"
    )
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Connect to MongoDB
    logger.info(f"Connecting to MongoDB at {args.mongo_uri}")
    client = motor_asyncio.AsyncIOMotorClient(args.mongo_uri)
    db = client[args.database]
    
    # Progress callback
    async def progress_callback(progress: LoadingProgress):
        logger.info(
            f"{progress.phase.title()}: {progress.processed}/{progress.total} "
            f"({progress.percent_complete:.1f}%) - {progress.current_item or ''}"
        )
    
    try:
        # Initialize and run the loader
        loader = InitialDataLoader(
            db=db,
            min_setups=args.min_setups,
            batch_size=args.batch_size,
            progress_callback=progress_callback,
        )
        
        # Run the pipeline
        report = await loader.run()
        
        # Save the report
        report_path = args.output_dir / "data_quality_report.json"
        await loader.save_report(report, report_path)
        
        # Print summary
        logger.info("=" * 60)
        logger.info("DATA LOADING SUMMARY")
        logger.info("=" * 60)
        logger.info(f"Total setups processed: {report.total_setups}")
        logger.info(f"Successfully ingested: {report.successfully_ingested}")
        logger.info(f"Failed ingestion: {report.failed_ingestion}")
        logger.info(f"Error rate: {report.error_rate_pct:.2f}%")
        logger.info(f"Average confluence count: {report.average_confluence_count:.1f}")
        
        if report.r_multiple_stats:
            logger.info(f"R-multiple mean: {report.r_multiple_stats.get('mean', 0):.2f}")
            logger.info(f"R-multiple median: {report.r_multiple_stats.get('median', 0):.2f}")
        
        logger.info(f"Report saved to: {report_path}")
        
        # Validate success criteria
        if report.successfully_ingested < args.min_setups:
            logger.error(f"FAILED: Only ingested {report.successfully_ingested} setups, need {args.min_setups}")
            return 1
        
        if report.error_rate_pct > 5.0:
            logger.warning(f"WARNING: High error rate {report.error_rate_pct:.2f}%")
        
        logger.info("Data loading completed successfully!")
        return 0
        
    except Exception as exc:
        logger.error(f"Data loading failed: {exc}")
        return 1
    finally:
        client.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))