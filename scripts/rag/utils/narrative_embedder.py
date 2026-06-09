"""
Narrative Embedder — pipeline-facing component for AlgoRAG.

Wraps the underlying SBERT model to encode setup narrative strings into
384-dimensional float32 vectors, with input validation and batch processing.

This is the component used by the data preparation pipeline (scripts/rag/)
when generating embeddings for historical setups.  The underlying model
(sentence-transformers/all-MiniLM-L6-v2) is loaded lazily and cached via
the module-level singleton in services.algorag.embedding_models.

Usage example::

    from scripts.rag.utils.narrative_embedder import NarrativeEmbedder

    embedder = NarrativeEmbedder()

    # Single narrative → (384,) float32 vector
    vector = embedder.embed("Price swept Asian low before reversing bullish.")

    # Multiple narratives → (N, 384) float32 array
    matrix = embedder.embed_batch(["Setup A.", "Setup B."], batch_size=32)
"""

from __future__ import annotations

import sys
import os

# Ensure workspace root is importable so we can reach services.algorag
_WORKSPACE_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..")
)
if _WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, _WORKSPACE_ROOT)

import logging
from typing import List

import numpy as np

from services.algorag.embedding_models import get_embedding_model

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

NARRATIVE_DIM: int = 384
_DEFAULT_BATCH_SIZE: int = 32


# ---------------------------------------------------------------------------
# NarrativeEmbedder
# ---------------------------------------------------------------------------


class NarrativeEmbedder:
    """Pipeline-facing encoder for trading setup narrative strings.

    Encodes narrative text into 384-dimensional float32 vectors using the
    ``sentence-transformers/all-MiniLM-L6-v2`` SBERT model.  The underlying
    model is loaded lazily on first use and cached as a module-level singleton.

    Attributes:
        dim: The output embedding dimensionality (always 384).
    """

    @property
    def dim(self) -> int:
        """Output dimensionality of the narrative embedding (384)."""
        return NARRATIVE_DIM

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def embed(self, text: str) -> np.ndarray:
        """Encode a single narrative string into a 384-dim float32 vector.

        Args:
            text: The narrative string to encode.  Must be a non-None string.

        Returns:
            A 1-D numpy array of shape ``(384,)`` with dtype ``float32``.

        Raises:
            TypeError: If ``text`` is not a string.
            ValueError: If ``text`` is ``None``.
        """
        self._validate_single(text)
        model = get_embedding_model()
        result: np.ndarray = model.encode(text)
        return np.asarray(result, dtype=np.float32).flatten()

    def embed_batch(
        self,
        texts: List[str],
        batch_size: int = _DEFAULT_BATCH_SIZE,
    ) -> np.ndarray:
        """Encode a list of narrative strings into a (N, 384) float32 array.

        Processes inputs in chunks of ``batch_size`` to keep memory usage
        bounded when encoding large sets of historical setups.

        Args:
            texts: A list of N narrative strings to encode.
            batch_size: Number of texts to encode in each forward pass.
                        Defaults to 32.

        Returns:
            A 2-D numpy array of shape ``(N, 384)`` with dtype ``float32``.
            Returns an empty array of shape ``(0, 384)`` when ``texts`` is empty.

        Raises:
            TypeError: If ``texts`` is not a list, or if any element is not a string.
            ValueError: If any element of ``texts`` is ``None``.
        """
        self._validate_batch(texts)

        if len(texts) == 0:
            return np.empty((0, NARRATIVE_DIM), dtype=np.float32)

        model = get_embedding_model()

        # Process in batches to bound memory usage
        chunks: List[np.ndarray] = []
        for start in range(0, len(texts), batch_size):
            chunk_texts = texts[start : start + batch_size]
            chunk_result: np.ndarray = model.encode_batch(chunk_texts)
            chunks.append(np.asarray(chunk_result, dtype=np.float32))

        return np.vstack(chunks)

    # ------------------------------------------------------------------
    # Input validation helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_single(text: object) -> None:
        """Raise TypeError/ValueError for invalid single-text inputs."""
        if text is None:
            raise ValueError("narrative text must not be None")
        if not isinstance(text, str):
            raise TypeError(
                f"narrative text must be a str, got {type(text).__name__!r}"
            )

    @staticmethod
    def _validate_batch(texts: object) -> None:
        """Raise TypeError/ValueError for invalid batch inputs."""
        if not isinstance(texts, list):
            raise TypeError(
                f"texts must be a list of strings, got {type(texts).__name__!r}"
            )
        for i, item in enumerate(texts):  # type: ignore[union-attr]
            if item is None:
                raise ValueError(f"texts[{i}] must not be None")
            if not isinstance(item, str):
                raise TypeError(
                    f"texts[{i}] must be a str, got {type(item).__name__!r}"
                )
