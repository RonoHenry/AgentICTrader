#!/usr/bin/env python3
"""
Example usage of ConfluenceFeatureExtractor with RAG integration.

This script demonstrates how to use the Confluence Scorer feature extractor
in different scenarios:
1. With RAG client (full feature extraction) 
2. Without RAG client (graceful degradation)
3. Error handling and validation

Usage:
    python ml/models/confluence_scorer/example_usage.py
"""
from __future__ import annotations

import sys
import os
import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List

# Add project root to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from ml.models.confluence_scorer.features import ConfluenceFeatureExtractor
from ml.algorag.client import AlgoRAGClient

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_sample_candles() -> List[Dict[str, Any]]:
    """Create sample candle data for testing."""
    return [
        {
            "time": "2024-01-01T08:00:00Z",
            "open": 1.5000,
            "high": 1.5100, 
            "low": 1.4900,
            "close": 1.5080,
            "volume": 1000,
        },
        {
            "time": "2024-01-01T08:05:00Z",
            "open": 1.5080,
            "high": 1.5120,
            "low": 1.5060,
            "close": 1.5110,
            "volume": 1200,
        },
        {
            "time": "2024-01-01T08:10:00Z",
            "open": 1.5110,
            "high": 1.5150,
            "low": 1.5090,
            "close": 1.5140,
            "volume": 800,
        },
    ]


def create_sample_setup_data() -> Dict[str, Any]:
    """Create sample setup data for testing."""
    return {
        "instrument": "EURUSD",
        "timestamp": datetime(2024, 1, 1, 8, 10, tzinfo=timezone.utc),
        "direction": "LONG",
        "entry_price": 1.5140,
        "timeframe": "M5",
        "htf_timeframe": "H1",
        "current_price": 1.5140,
    }


async def example_with_rag_client():
    """Example: Feature extraction with RAG client."""
    logger.info("=== Example 1: With RAG Client ===")
    
    # Create sample data
    candles = create_sample_candles()
    setup_data = create_sample_setup_data()
    
    try:
        # Initialize RAG client (would connect to AlgoRAG service)
        async with AlgoRAGClient(base_url="http://localhost:8003") as rag_client:
            extractor = ConfluenceFeatureExtractor(rag_client=rag_client)
            
            # Extract features
            features = await extractor.extract_features(candles, setup_data)
            
            logger.info(f"Traditional features:")
            logger.info(f"  HTF high proximity: {features.htf_high_proximity_pct:.1f}%")
            logger.info(f"  HTF low proximity: {features.htf_low_proximity_pct:.1f}%")
            logger.info(f"  Time window weight: {features.time_window_weight:.2f}")
            logger.info(f"  Narrative phase: {features.narrative_phase}")
            logger.info(f"  BOS detected: {features.bos_detected}")
            logger.info(f"  FVG present: {features.fvg_present}")
            
            logger.info(f"RAG features:")
            logger.info(f"  Avg R-multiple: {features.avg_r_multiple:.2f}")
            logger.info(f"  Win rate: {features.win_rate:.2f}")
            logger.info(f"  Sample size: {features.sample_size:.2f}")
            logger.info(f"  Max similarity: {features.max_similarity:.2f}")
            
            # Convert to array for model input
            feature_vector = features.to_array()
            logger.info(f"Feature vector shape: {feature_vector.shape}")
            logger.info(f"Feature vector: {feature_vector}")
            
    except Exception as e:
        logger.error(f"RAG client connection failed: {e}")
        logger.info("Falling back to example without RAG...")
        await example_without_rag_client()


async def example_without_rag_client():
    """Example: Feature extraction without RAG client (graceful degradation)."""
    logger.info("=== Example 2: Without RAG Client (Graceful Degradation) ===")
    
    # Create sample data  
    candles = create_sample_candles()
    setup_data = create_sample_setup_data()
    
    # Initialize extractor without RAG client
    extractor = ConfluenceFeatureExtractor()
    
    # Extract features
    features = await extractor.extract_features(candles, setup_data)
    
    logger.info(f"Traditional features work normally:")
    logger.info(f"  HTF high proximity: {features.htf_high_proximity_pct:.1f}%")
    logger.info(f"  HTF low proximity: {features.htf_low_proximity_pct:.1f}%")
    logger.info(f"  Time window weight: {features.time_window_weight:.2f}")
    logger.info(f"  Narrative phase: {features.narrative_phase}")
    
    logger.info(f"RAG features gracefully degrade to zeros:")
    logger.info(f"  Avg R-multiple: {features.avg_r_multiple:.2f}")
    logger.info(f"  Win rate: {features.win_rate:.2f}")
    logger.info(f"  Sample size: {features.sample_size:.2f}")
    logger.info(f"  Max similarity: {features.max_similarity:.2f}")
    
    # Feature vector still works
    feature_vector = features.to_array()
    logger.info(f"Feature vector shape: {feature_vector.shape}")
    logger.info(f"All features valid: {not any(v != v for v in feature_vector)}")  # Check no NaN


async def example_error_handling():
    """Example: Error handling with malformed data."""
    logger.info("=== Example 3: Error Handling ===")
    
    # Test with problematic data
    problematic_scenarios = [
        {
            "name": "Empty candles",
            "candles": [],
            "setup_data": create_sample_setup_data(),
        },
        {
            "name": "Malformed candle data", 
            "candles": [{"invalid": "data"}],  # Completely invalid structure
            "setup_data": create_sample_setup_data(),
        },
        {
            "name": "Missing setup data",
            "candles": create_sample_candles(),
            "setup_data": {"instrument": "EURUSD"},  # Missing other fields
        },
        {
            "name": "Extreme price values",
            "candles": [{
                "time": "2024-01-01T08:00:00Z",
                "open": 0.00001,
                "high": 999999.0,
                "low": -999999.0, 
                "close": 0.00001,
                "volume": 0,
            }],
            "setup_data": create_sample_setup_data(),
        },
    ]
    
    extractor = ConfluenceFeatureExtractor()
    
    for scenario in problematic_scenarios:
        try:
            logger.info(f"Testing: {scenario['name']}")
            features = await extractor.extract_features(
                scenario["candles"], 
                scenario["setup_data"]
            )
            
            feature_vector = features.to_array()
            has_nan = any(v != v for v in feature_vector)  # NaN check
            has_inf = any(abs(v) == float('inf') for v in feature_vector)  # Inf check
            
            logger.info(f"  ✓ Success! Shape: {feature_vector.shape}, "
                       f"NaN: {has_nan}, Inf: {has_inf}")
            
        except Exception as e:
            logger.error(f"  ✗ Failed: {e}")


async def example_feature_bounds_validation():
    """Example: Demonstrate feature bounds validation."""
    logger.info("=== Example 4: Feature Bounds Validation ===")
    
    candles = create_sample_candles()
    setup_data = create_sample_setup_data()
    
    extractor = ConfluenceFeatureExtractor()
    features = await extractor.extract_features(candles, setup_data)
    
    # Validate bounds
    checks = [
        ("time_window_weight", features.time_window_weight, 0.0, 1.0),
        ("htf_close_position", features.htf_close_position, 0.0, 1.0),
        ("win_rate", features.win_rate, 0.0, 1.0),
        ("sample_size", features.sample_size, 0.0, 1.0),
        ("max_similarity", features.max_similarity, 0.0, 1.0),
    ]
    
    logger.info("Feature bounds validation:")
    for name, value, min_bound, max_bound in checks:
        is_valid = min_bound <= value <= max_bound
        status = "✓" if is_valid else "✗"
        logger.info(f"  {status} {name}: {value:.3f} [{min_bound}, {max_bound}]")


async def main():
    """Run all examples."""
    logger.info("Confluence Feature Extractor Examples")
    logger.info("=" * 50)
    
    try:
        # Try with RAG client first
        await example_with_rag_client()
    except Exception:
        # Fall back to without RAG
        await example_without_rag_client()
    
    await example_error_handling()
    await example_feature_bounds_validation()
    
    logger.info("\n" + "=" * 50)
    logger.info("All examples completed successfully!")


if __name__ == "__main__":
    asyncio.run(main())