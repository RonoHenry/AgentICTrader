"""
Structured Feature Embedder — pipeline component for AlgoRAG.

Extracts 64 structured features from an EnrichedSetup and projects them to a
128-dimensional float32 embedding vector via a deterministic linear projection.

Feature vector layout (all features normalised to [0, 1]):

  Index  Field                          Notes
  -----  ----                           -----
   0     htf_high_proximity_pct / 100   HTF metrics
   1     htf_low_proximity_pct  / 100
   2     htf_body_pct           / 100
   3     htf_close_position     / 100
   4     htf_bias_bullish               HTF bias one-hot
   5     htf_bias_bearish
   6     htf_bias_neutral
   7     bos_detected                   PD array flags (bool → 0/1)
   8     choch_detected
   9     fvg_present
  10     liquidity_sweep
  11     swing_high_distance (norm)     Swing distances, clipped at 0.1 → /0.1
  12     swing_low_distance  (norm)
  13     time_window_weight             Session (already in [0, 1])
  14     is_killzone                    bool → 0/1
  15     r_multiple_norm                clip(0, 10) / 10
  16     outcome_win                    WIN=1, LOSS=0
  17     confluence_count / 10          clip(0, 10) / 10
  18-63  0.0 (reserved padding)

Output: linear projection 64 → 128 using a fixed random weight matrix seeded
with numpy default_rng(seed=42) for determinism.  The projection is computed as::

    embedding = relu(features @ W.T + b)

where W ∈ ℝ^{128×64} and b ∈ ℝ^{128} are sampled once at class instantiation
from a normal distribution and held constant.

Usage example::

    from scripts.rag.utils.structured_feature_embedder import StructuredFeatureEmbedder
    from scripts.rag.utils.setup_enricher import EnrichedSetup

    embedder = StructuredFeatureEmbedder()

    # Extract raw 64-dim normalised feature vector
    features = embedder.extract_features(enriched_setup)  # shape (64,) float32

    # Full 128-dim embedding
    vector = embedder.embed(enriched_setup)               # shape (128,) float32
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
from typing import Union

import numpy as np

from scripts.rag.utils.setup_enricher import EnrichedSetup

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FEATURE_VEC_DIM: int = 64   # raw normalised feature vector size
STRUCTURED_DIM: int = 128   # output embedding size

# Normalisation clamp values
_MAX_R_MULTIPLE: float = 10.0
_MAX_CONFLUENCE: float = 10.0
_MAX_SWING_DIST: float = 0.1   # 1000 pips — anything beyond clips to 1.0

# Projection seed (fixed for reproducibility)
_PROJECTION_SEED: int = 42


# ---------------------------------------------------------------------------
# StructuredFeatureEmbedder
# ---------------------------------------------------------------------------


class StructuredFeatureEmbedder:
    """Pipeline-facing encoder for structured fields of an EnrichedSetup.

    Extracts 18 semantic features from an :class:`~scripts.rag.utils.setup_enricher.EnrichedSetup`,
    pads to 64 dimensions (all in [0, 1]), then projects to a 128-dimensional
    float32 vector using a fixed random linear layer (ReLU activation).

    The projection weights are seeded deterministically so that the same
    :class:`StructuredFeatureEmbedder` instance and any newly created instance
    always produce identical output for identical input.

    Attributes:
        dim: Output embedding dimensionality (128).
        feature_dim: Raw feature vector dimensionality (64).
    """

    @property
    def dim(self) -> int:
        """Output dimensionality of the structured embedding (128)."""
        return STRUCTURED_DIM

    @property
    def feature_dim(self) -> int:
        """Dimensionality of the intermediate normalised feature vector (64)."""
        return FEATURE_VEC_DIM

    def __init__(self) -> None:
        """Initialise the embedder and pre-compute the projection matrix."""
        rng = np.random.default_rng(seed=_PROJECTION_SEED)
        # W: (128, 64), b: (128,) — Xavier-style scale for stable activations
        scale = np.sqrt(2.0 / FEATURE_VEC_DIM)
        self._W: np.ndarray = rng.normal(0.0, scale, (STRUCTURED_DIM, FEATURE_VEC_DIM)).astype(np.float32)
        self._b: np.ndarray = rng.normal(0.0, scale, (STRUCTURED_DIM,)).astype(np.float32)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def extract_features(self, setup: EnrichedSetup) -> np.ndarray:
        """Extract and normalise 64 structured features from an EnrichedSetup.

        All output features are in the range [0, 1].

        Args:
            setup: A fully populated :class:`EnrichedSetup` instance.

        Returns:
            A 1-D numpy array of shape ``(64,)`` with dtype ``float32``,
            where all values lie in ``[0.0, 1.0]``.

        Raises:
            TypeError: If ``setup`` is not an :class:`EnrichedSetup` instance.
        """
        self._validate(setup)

        features = np.zeros(FEATURE_VEC_DIM, dtype=np.float32)

        # ----------------------------------------------------------------
        # 0–3  HTF metrics (percentage fields → divide by 100)
        # ----------------------------------------------------------------
        features[0] = _clip01(setup.htf_high_proximity_pct / 100.0)
        features[1] = _clip01(setup.htf_low_proximity_pct / 100.0)
        features[2] = _clip01(setup.htf_body_pct / 100.0)
        features[3] = _clip01(setup.htf_close_position / 100.0)

        # ----------------------------------------------------------------
        # 4–6  HTF open bias — one-hot (BULLISH / BEARISH / NEUTRAL)
        # ----------------------------------------------------------------
        bias = (setup.htf_open_bias or "NEUTRAL").upper()
        if bias == "BULLISH":
            features[4] = 1.0
        elif bias == "BEARISH":
            features[5] = 1.0
        else:
            features[6] = 1.0

        # ----------------------------------------------------------------
        # 7–10  PD array flags (bool → 0.0 / 1.0)
        # ----------------------------------------------------------------
        features[7]  = 1.0 if setup.bos_detected else 0.0
        features[8]  = 1.0 if setup.choch_detected else 0.0
        features[9]  = 1.0 if setup.fvg_present else 0.0
        features[10] = 1.0 if setup.liquidity_sweep else 0.0

        # ----------------------------------------------------------------
        # 11–12  Swing distances (clip at _MAX_SWING_DIST, then normalise)
        # ----------------------------------------------------------------
        features[11] = _clip01(setup.swing_high_distance / _MAX_SWING_DIST)
        features[12] = _clip01(setup.swing_low_distance / _MAX_SWING_DIST)

        # ----------------------------------------------------------------
        # 13–14  Session features
        # ----------------------------------------------------------------
        features[13] = _clip01(setup.time_window_weight)        # already [0, 1]
        features[14] = 1.0 if setup.is_killzone else 0.0

        # ----------------------------------------------------------------
        # 15–16  Outcome
        # ----------------------------------------------------------------
        features[15] = _clip01(max(0.0, setup.r_multiple) / _MAX_R_MULTIPLE)
        features[16] = 1.0 if (setup.outcome_result or "").upper() == "WIN" else 0.0

        # ----------------------------------------------------------------
        # 17  Confluence count
        # ----------------------------------------------------------------
        features[17] = _clip01(setup.confluence_count / _MAX_CONFLUENCE)

        # Indices 18–63 remain 0.0 (padding / reserved for future features)

        return features

    def embed(self, setup: EnrichedSetup) -> np.ndarray:
        """Embed an EnrichedSetup into a 128-dimensional float32 vector.

        Applies the linear projection::

            embedding = relu(features @ W.T + b)

        where the weight matrix ``W`` and bias ``b`` are fixed at construction
        time (seeded with numpy default_rng(42)) ensuring full determinism.

        Args:
            setup: A fully populated :class:`EnrichedSetup` instance.

        Returns:
            A 1-D numpy array of shape ``(128,)`` with dtype ``float32``.

        Raises:
            TypeError: If ``setup`` is not an :class:`EnrichedSetup` instance.
        """
        features = self.extract_features(setup)  # (64,) float32 — also validates

        # Linear projection: (64,) @ (64, 128) → (128,)
        raw: np.ndarray = features @ self._W.T + self._b
        # ReLU activation keeps values non-negative
        result = np.maximum(raw, 0.0).astype(np.float32)
        return result

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _validate(setup: object) -> None:
        """Raise TypeError if *setup* is not an EnrichedSetup instance."""
        if not isinstance(setup, EnrichedSetup):
            raise TypeError(
                f"setup must be an EnrichedSetup instance, got {type(setup).__name__!r}"
            )


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _clip01(value: float) -> float:
    """Clip *value* to the [0.0, 1.0] range and return as Python float."""
    return float(min(1.0, max(0.0, value)))
