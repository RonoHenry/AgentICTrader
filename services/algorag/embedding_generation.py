"""
Query-time embedding generation for AlgoRAG retrieval (Task 10.3).

Builds the same 528-dim multi-modal vector (384 narrative + 128 structured +
16 temporal, weighted 40/40/20) used to index historical setups, but from a
live :class:`~services.algorag.models.RetrievalRequest` rather than a fully
resolved :class:`~scripts.rag.utils.setup_enricher.EnrichedSetup`. Reusing
the exact same component embedders and structured-feature projection matrix
(seeded, deterministic) as the ingestion pipeline is what keeps cosine
similarity between a live query and stored setups meaningful.

A live query has no known trade outcome yet, so the two outcome-related
structured features (r_multiple, WIN/LOSS) are always encoded as neutral
zeros — the retrieval is "what does this situation look like", not "what did
this trade close as".
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List

import numpy as np

from scripts.rag.utils.narrative_embedder import NarrativeEmbedder
from scripts.rag.utils.structured_feature_embedder import (
    FEATURE_VEC_DIM,
    StructuredFeatureEmbedder,
)
from scripts.rag.utils.temporal_embedder import TemporalEmbedder

if TYPE_CHECKING:
    from services.algorag.models import RetrievalRequest

_NARRATIVE_WEIGHT: float = 0.4
_STRUCTURED_WEIGHT: float = 0.4
_TEMPORAL_WEIGHT: float = 0.2

_MAX_SWING_DIST: float = 0.1
_MAX_CONFLUENCE: float = 10.0

# Component embedders are stateless w.r.t. the request and expensive to
# construct (SBERT load, projection matrix), so they're created once and
# reused across calls — mirroring MultiModalEmbedder's approach.
_narrative_embedder = NarrativeEmbedder()
_structured_embedder = StructuredFeatureEmbedder()
_temporal_embedder = TemporalEmbedder()


def _clip01(value: float) -> float:
    return float(min(1.0, max(0.0, value)))


def _extract_query_features(request: "RetrievalRequest") -> np.ndarray:
    """Build the 64-dim raw structured feature vector for a live query.

    Mirrors ``StructuredFeatureEmbedder.extract_features``'s index layout so
    the shared projection matrix produces a comparable embedding. Fields not
    present on ``RetrievalRequest`` (htf_structure / pd_arrays sub-keys)
    default to neutral values when absent.
    """
    htf = request.htf_structure or {}
    pd_arrays = request.pd_arrays or {}

    features = np.zeros(FEATURE_VEC_DIM, dtype=np.float32)

    features[0] = _clip01(float(htf.get("htf_high_proximity_pct", 0.0)) / 100.0)
    features[1] = _clip01(float(htf.get("htf_low_proximity_pct", 0.0)) / 100.0)
    features[2] = _clip01(float(htf.get("htf_body_pct", 0.0)) / 100.0)
    features[3] = _clip01(float(htf.get("htf_close_position", 0.0)) / 100.0)

    bias = (request.htf_open_bias or "NEUTRAL").upper()
    if bias == "BULLISH":
        features[4] = 1.0
    elif bias == "BEARISH":
        features[5] = 1.0
    else:
        features[6] = 1.0

    features[7] = 1.0 if pd_arrays.get("bos_detected") else 0.0
    features[8] = 1.0 if pd_arrays.get("choch_detected") else 0.0
    features[9] = 1.0 if pd_arrays.get("fvg_present") else 0.0
    features[10] = 1.0 if pd_arrays.get("liquidity_sweep") else 0.0

    features[11] = _clip01(float(htf.get("swing_high_distance", 0.0)) / _MAX_SWING_DIST)
    features[12] = _clip01(float(htf.get("swing_low_distance", 0.0)) / _MAX_SWING_DIST)

    features[13] = 1.0 if request.time_window else 0.0
    features[14] = 1.0 if request.time_window else 0.0

    # Outcome is unknown for a live setup — encode as neutral, not a guess.
    features[15] = 0.0
    features[16] = 0.0

    confluence_count = len(request.confluence_factors or [])
    features[17] = _clip01(confluence_count / _MAX_CONFLUENCE)

    return features


def generate_query_embedding(request: "RetrievalRequest") -> List[float]:
    """Generate the 528-dim query embedding for a retrieval request.

    Args:
        request: The incoming retrieval request.

    Returns:
        A 528-element list of floats: 384 narrative + 128 structured + 16
        temporal, each pre-scaled by its combination weight (40/40/20) so it
        can be compared directly against vectors stored by the ingestion
        pipeline.
    """
    narrative_text = request.narrative or ""
    narrative_emb = np.asarray(
        _narrative_embedder.embed(narrative_text), dtype=np.float32
    )

    raw_features = _extract_query_features(request)
    structured_emb = np.asarray(
        _structured_embedder.project_features(raw_features), dtype=np.float32
    )

    temporal_emb = np.asarray(
        _temporal_embedder.encode(request.timestamp), dtype=np.float32
    )

    combined = np.concatenate(
        [
            narrative_emb * _NARRATIVE_WEIGHT,
            structured_emb * _STRUCTURED_WEIGHT,
            temporal_emb * _TEMPORAL_WEIGHT,
        ]
    ).astype(np.float32)

    return combined.tolist()
