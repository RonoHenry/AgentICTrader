"""
Query embedding generation for AlgoRAG retrieval.

This module generates 528-dimensional query embeddings from RetrievalRequest
objects by combining narrative embeddings, structured features, and temporal
encoding as specified in the design document.

Usage example::

    from services.algorag.embedding_generation import generate_query_embedding
    from services.algorag.models import RetrievalRequest

    request = RetrievalRequest(
        instrument="EURUSD",
        timestamp=datetime.now(timezone.utc),
        narrative="Price swept Asian low before reversing at bullish OB"
    )
    
    embedding = generate_query_embedding(request)
    # Returns 528-dimensional list of floats
"""

from __future__ import annotations

import math
import logging
from datetime import datetime
from typing import List

import numpy as np

from services.algorag.models import RetrievalRequest
from services.algorag.embedding_models import get_embedding_model

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants from design document
# ---------------------------------------------------------------------------

NARRATIVE_DIM = 384      # Sentence-BERT all-MiniLM-L6-v2 output
STRUCTURED_DIM = 128     # Custom structured features 
TEMPORAL_DIM = 16        # Cyclical temporal encoding
TOTAL_DIM = 528          # Combined embedding dimension

NARRATIVE_WEIGHT = 0.4   # 40% weight for narrative
STRUCTURED_WEIGHT = 0.4  # 40% weight for structured features  
TEMPORAL_WEIGHT = 0.2    # 20% weight for temporal

# ---------------------------------------------------------------------------
# Main embedding function
# ---------------------------------------------------------------------------


def generate_query_embedding(request: RetrievalRequest) -> List[float]:
    """
    Generate a 528-dimensional query embedding from a RetrievalRequest.
    
    Combines three embedding components with specified weights:
    - Narrative embedding (384-dim, 40% weight) from SBERT
    - Structured features (128-dim, 40% weight) from request fields  
    - Temporal encoding (16-dim, 20% weight) from timestamp
    
    Args:
        request: The retrieval request containing narrative, timestamp, and structured data
        
    Returns:
        List of 528 float values representing the combined embedding vector
        
    Raises:
        Never raises - returns zero vector as fallback on any error
    """
    try:
        # Generate narrative embedding (384-dim)
        narrative_emb = _generate_narrative_embedding(request.narrative or "")
        
        # Generate structured features embedding (128-dim) 
        structured_emb = _generate_structured_embedding(request)
        
        # Generate temporal embedding (16-dim)
        temporal_emb = _generate_temporal_embedding(request.timestamp)
        
        # Combine with specified weights
        combined = np.concatenate([
            narrative_emb * NARRATIVE_WEIGHT,
            structured_emb * STRUCTURED_WEIGHT,  
            temporal_emb * TEMPORAL_WEIGHT,
        ])
        
        # Ensure exactly 528 dimensions
        if combined.shape != (TOTAL_DIM,):
            logger.error("Embedding dimension mismatch: expected %d, got %s", TOTAL_DIM, combined.shape)
            return [0.0] * TOTAL_DIM
        
        # Check for NaN or infinite values
        if not np.isfinite(combined).all():
            logger.error("Embedding contains NaN or infinite values")
            return [0.0] * TOTAL_DIM
            
        return combined.tolist()
        
    except Exception as exc:
        logger.error("Failed to generate query embedding: %s", exc, exc_info=True)
        # Return zero vector as fallback - ensures graceful degradation
        return [0.0] * TOTAL_DIM


# ---------------------------------------------------------------------------
# Component embedding functions
# ---------------------------------------------------------------------------


def _generate_narrative_embedding(narrative: str) -> np.ndarray:
    """Generate 384-dim narrative embedding using SBERT."""
    try:
        if not narrative or not narrative.strip():
            # Return zero embedding for empty narrative
            return np.zeros(NARRATIVE_DIM, dtype=np.float32)
        
        model = get_embedding_model()
        embedding = model.encode(narrative.strip())
        
        # Ensure correct dimensions
        if embedding.shape != (NARRATIVE_DIM,):
            logger.warning("Unexpected narrative embedding shape: %s", embedding.shape)
            return np.zeros(NARRATIVE_DIM, dtype=np.float32)
        
        # Check for NaN or infinite values
        if not np.isfinite(embedding).all():
            logger.warning("Narrative embedding contains NaN or infinite values")
            return np.zeros(NARRATIVE_DIM, dtype=np.float32)
        
        return embedding
        
    except Exception as exc:
        logger.error("Failed to generate narrative embedding: %s", exc)
        return np.zeros(NARRATIVE_DIM, dtype=np.float32)


def _generate_structured_embedding(request: RetrievalRequest) -> np.ndarray:
    """
    Generate 128-dim structured features embedding.
    
    Extracts structured features from the request and encodes them into
    a fixed-size vector. Features include HTF metrics, PD array flags,
    confluence factors, etc.
    """
    try:
        features = []
        
        # HTF structure features (4 features)
        htf_structure = request.htf_structure or {}
        features.extend([
            float(htf_structure.get("htf_high_proximity_pct", 0.0)),
            float(htf_structure.get("htf_low_proximity_pct", 0.0)), 
            float(htf_structure.get("htf_body_pct", 0.0)),
            float(htf_structure.get("htf_close_position", 0.0)),
        ])
        
        # HTF bias one-hot encoding (3 features: BULLISH, BEARISH, NEUTRAL)
        htf_bias = request.htf_open_bias or "NEUTRAL"
        features.extend([
            1.0 if htf_bias == "BULLISH" else 0.0,
            1.0 if htf_bias == "BEARISH" else 0.0, 
            1.0 if htf_bias == "NEUTRAL" else 0.0,
        ])
        
        # PD array flags (4 features)
        pd_arrays = request.pd_arrays or {}
        features.extend([
            1.0 if pd_arrays.get("bos_detected", False) else 0.0,
            1.0 if pd_arrays.get("choch_detected", False) else 0.0,
            1.0 if pd_arrays.get("fvg_present", False) else 0.0,
            1.0 if pd_arrays.get("liquidity_sweep", False) else 0.0,
        ])
        
        # Time window features (2 features)
        time_window = request.time_window or ""
        is_killzone = time_window.endswith("_KILLZONE")
        features.extend([
            _get_time_window_weight(time_window),
            1.0 if is_killzone else 0.0,
        ])
        
        # Confluence count (1 feature)  
        confluence_count = len(request.confluence_factors or [])
        features.append(min(confluence_count / 10.0, 1.0))  # Normalize to [0,1]
        
        # Pad remaining features to reach 64 total (will be projected to 128-dim)
        current_count = len(features)
        remaining = max(0, 64 - current_count)
        features.extend([0.0] * remaining)
        
        # Convert to numpy array and project to 128 dimensions
        features_array = np.array(features[:64], dtype=np.float32)
        
        # Check for NaN or infinite values
        if not np.isfinite(features_array).all():
            logger.warning("Structured features contain NaN or infinite values")
            features_array = np.zeros(64, dtype=np.float32)
        
        # Simple projection: repeat and truncate to get 128 dimensions
        # In production, this could be a learned projection/autoencoder
        projected = np.tile(features_array, 2)[:STRUCTURED_DIM]
        
        return projected
        
    except Exception as exc:
        logger.error("Failed to generate structured embedding: %s", exc)
        return np.zeros(STRUCTURED_DIM, dtype=np.float32)


def _generate_temporal_embedding(timestamp: datetime) -> np.ndarray:
    """
    Generate 16-dim temporal embedding using cyclical encoding.
    
    Uses sin/cos encoding to capture temporal periodicity without
    ordinal bias, as specified in design document.
    """
    try:
        # Extract time components
        hour = timestamp.hour
        day_of_week = timestamp.weekday()  # 0=Monday, 6=Sunday  
        month = timestamp.month
        
        # Cyclical encoding with sin/cos
        temporal_features = [
            math.sin(2 * math.pi * hour / 24),          # hour_sin
            math.cos(2 * math.pi * hour / 24),          # hour_cos
            math.sin(2 * math.pi * day_of_week / 7),    # dow_sin  
            math.cos(2 * math.pi * day_of_week / 7),    # dow_cos
            math.sin(2 * math.pi * month / 12),         # month_sin
            math.cos(2 * math.pi * month / 12),         # month_cos
        ]
        
        # Pad remaining dimensions with zeros (reserved for future features)
        temporal_features.extend([0.0] * (TEMPORAL_DIM - len(temporal_features)))
        
        result = np.array(temporal_features, dtype=np.float32)
        
        # Check for NaN or infinite values
        if not np.isfinite(result).all():
            logger.warning("Temporal embedding contains NaN or infinite values")
            return np.zeros(TEMPORAL_DIM, dtype=np.float32)
        
        return result
        
    except Exception as exc:
        logger.error("Failed to generate temporal embedding: %s", exc)
        return np.zeros(TEMPORAL_DIM, dtype=np.float32)


# ---------------------------------------------------------------------------
# Helper functions  
# ---------------------------------------------------------------------------


def _get_time_window_weight(time_window: str) -> float:
    """
    Get numeric weight for time window based on ICT methodology.
    
    Higher weights for high-probability killzones.
    """
    weights = {
        "LONDON_KILLZONE": 1.0,
        "NY_AM_KILLZONE": 0.9,
        "NY_PM_KILLZONE": 0.8, 
        "SILVER_BULLET": 0.7,
        "ASIAN_KILLZONE": 0.5,
        "LONDON_OPEN": 0.6,
        "NY_OPEN": 0.7,
        "OVERLAP": 0.4,
    }
    
    return weights.get(time_window, 0.1)  # Default low weight for unknown windows