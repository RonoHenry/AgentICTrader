"""
Multi-Modal Embedder — combines narrative, structured, and temporal embeddings
into a single 528-dimensional float32 vector for Qdrant storage.

This is the top-level pipeline component for AlgoRAG embedding generation.
It delegates to the three component embedders and applies the 40/40/20 weight
scheme before concatenating into the final combined vector.

Combination formula (from rag-pipeline.md):
    combined = np.concatenate([
        narrative_emb  * 0.4,   # 384-dim slice  (indices   0–383)
        structured_emb * 0.4,   # 128-dim slice  (indices 384–511)
        temporal_emb   * 0.2,   #  16-dim slice  (indices 512–527)
    ])  # → 528-dim, float32

Invariants (enforced by validate_embedding()):
  - Output is always exactly 528-dim
  - dtype is float32
  - No NaN values
  - No Inf values

Usage example::

    from scripts.rag.utils.multi_modal_embedder import MultiModalEmbedder
    from scripts.rag.utils.setup_enricher import EnrichedSetup

    embedder = MultiModalEmbedder()

    # Combine all three modalities into a single 528-dim vector
    vector = embedder.embed(enriched_setup)             # shape (528,) float32

    # Combine and validate in one call
    vector = embedder.embed_and_validate(enriched_setup)

    # Validate an externally generated vector
    embedder.validate_embedding(some_vector)            # raises if invalid
"""

from __future__ import annotations

import sys
import os

# Ensure workspace root is importable
_WORKSPACE_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..")
)
if _WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, _WORKSPACE_ROOT)

import logging
from typing import Optional

import numpy as np

from scripts.rag.utils.setup_enricher import EnrichedSetup
from scripts.rag.utils.narrative_embedder import NarrativeEmbedder
from scripts.rag.utils.structured_feature_embedder import StructuredFeatureEmbedder
from scripts.rag.utils.temporal_embedder import TemporalEmbedder

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

COMBINED_DIM: int = 528          # 384 + 128 + 16
NARRATIVE_DIM: int = 384
STRUCTURED_DIM: int = 128
TEMPORAL_DIM: int = 16

_NARRATIVE_WEIGHT: float = 0.4
_STRUCTURED_WEIGHT: float = 0.4
_TEMPORAL_WEIGHT: float = 0.2


# ---------------------------------------------------------------------------
# MultiModalEmbedder
# ---------------------------------------------------------------------------


class MultiModalEmbedder:
    """Combines narrative, structured, and temporal embeddings into a 528-dim vector.

    Each of the three modality embedders is created once at construction time
    and reused across all calls to embed().  This ensures the SBERT model and
    the fixed structured projection matrix are loaded/computed only once.

    Weights follow the AlgoRAG spec:
      - Narrative  (384-dim): 40%
      - Structured (128-dim): 40%
      - Temporal    (16-dim): 20%

    The final vector is the weighted concatenation::

        combined = np.concatenate([
            narrative_emb  * 0.4,
            structured_emb * 0.4,
            temporal_emb   * 0.2,
        ])

    Attributes:
        dim:               Output embedding dimensionality (528).
        narrative_weight:  Weight applied to narrative component (0.4).
        structured_weight: Weight applied to structured component (0.4).
        temporal_weight:   Weight applied to temporal component (0.2).
    """

    # Weights are class-level constants; exposed as read-only properties
    _NARRATIVE_WEIGHT: float = _NARRATIVE_WEIGHT
    _STRUCTURED_WEIGHT: float = _STRUCTURED_WEIGHT
    _TEMPORAL_WEIGHT: float = _TEMPORAL_WEIGHT

    def __init__(self) -> None:
        """Initialise all three component embedders."""
        self._narrative_embedder = NarrativeEmbedder()
        self._structured_embedder = StructuredFeatureEmbedder()
        self._temporal_embedder = TemporalEmbedder()

    # ------------------------------------------------------------------
    # Read-only properties
    # ------------------------------------------------------------------

    @property
    def dim(self) -> int:
        """Output dimensionality of the combined embedding (528)."""
        return COMBINED_DIM

    @property
    def narrative_weight(self) -> float:
        """Weight applied to the narrative embedding (0.4 = 40%)."""
        return self._NARRATIVE_WEIGHT

    @property
    def structured_weight(self) -> float:
        """Weight applied to the structured embedding (0.4 = 40%)."""
        return self._STRUCTURED_WEIGHT

    @property
    def temporal_weight(self) -> float:
        """Weight applied to the temporal embedding (0.2 = 20%)."""
        return self._TEMPORAL_WEIGHT

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def embed(self, setup: EnrichedSetup) -> np.ndarray:
        """Combine all three modalities into a single 528-dim float32 embedding.

        Delegates to NarrativeEmbedder, StructuredFeatureEmbedder, and
        TemporalEmbedder, then applies weights and concatenates::

            combined = np.concatenate([
                narrative_emb  * 0.4,   # indices   0–383
                structured_emb * 0.4,   # indices 384–511
                temporal_emb   * 0.2,   # indices 512–527
            ])

        Args:
            setup: A fully populated :class:`EnrichedSetup` instance.

        Returns:
            A 1-D numpy array of shape ``(528,)`` with dtype ``float32``.

        Raises:
            TypeError: If ``setup`` is not an :class:`EnrichedSetup` instance.
        """
        self._validate_input(setup)

        # --- Narrative embedding: (384,) float32 ---
        narrative_emb: np.ndarray = self._narrative_embedder.embed(setup.narrative)
        # Ensure float32 (SBERT may return float32 already, but be explicit)
        narrative_emb = np.asarray(narrative_emb, dtype=np.float32)

        # --- Structured embedding: (128,) float32 ---
        structured_emb: np.ndarray = self._structured_embedder.embed(setup)
        structured_emb = np.asarray(structured_emb, dtype=np.float32)

        # --- Temporal embedding: (16,) float64 → cast to float32 ---
        temporal_emb: np.ndarray = self._temporal_embedder.encode(setup.timestamp)
        temporal_emb = np.asarray(temporal_emb, dtype=np.float32)

        # --- Weighted concatenation: 40% / 40% / 20% ---
        combined: np.ndarray = np.concatenate([
            narrative_emb  * self._NARRATIVE_WEIGHT,
            structured_emb * self._STRUCTURED_WEIGHT,
            temporal_emb   * self._TEMPORAL_WEIGHT,
        ]).astype(np.float32)

        return combined

    def embed_and_validate(self, setup: EnrichedSetup) -> np.ndarray:
        """Embed a setup and immediately validate the resulting vector.

        Equivalent to calling embed() followed by validate_embedding().
        Raises the same exceptions as each of those methods.

        Args:
            setup: A fully populated :class:`EnrichedSetup` instance.

        Returns:
            A validated 1-D numpy array of shape ``(528,)`` with dtype ``float32``.
        """
        combined = self.embed(setup)
        self.validate_embedding(combined)
        return combined

    def validate_embedding(self, embedding: np.ndarray) -> None:
        """Validate that an embedding vector meets all AlgoRAG invariants.

        Checks:
          1. Must be a numpy ndarray.
          2. Must be exactly 528-dimensional.
          3. Must not contain NaN values.
          4. Must not contain Inf values.

        Args:
            embedding: The candidate embedding vector to validate.

        Raises:
            TypeError:  If ``embedding`` is not a numpy ndarray.
            ValueError: If dimensionality, NaN, or Inf checks fail.
        """
        if not isinstance(embedding, np.ndarray):
            raise TypeError(
                f"embedding must be a numpy ndarray, got {type(embedding).__name__!r}"
            )

        if embedding.shape != (COMBINED_DIM,):
            raise ValueError(
                f"embedding must be exactly {COMBINED_DIM}-dimensional, "
                f"got shape {embedding.shape}"
            )

        if np.isnan(embedding).any():
            nan_count = int(np.isnan(embedding).sum())
            raise ValueError(
                f"embedding contains {nan_count} NaN value(s); "
                "check source embedder outputs"
            )

        if np.isinf(embedding).any():
            inf_count = int(np.isinf(embedding).sum())
            raise ValueError(
                f"embedding contains {inf_count} Inf value(s); "
                "check source embedder outputs"
            )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_input(setup: object) -> None:
        """Raise TypeError if *setup* is not an EnrichedSetup instance."""
        if not isinstance(setup, EnrichedSetup):
            raise TypeError(
                f"setup must be an EnrichedSetup instance, "
                f"got {type(setup).__name__!r}"
            )
