"""
Narrative Embedding Model for AlgoRAG.

Provides a singleton-cached wrapper around the sentence-transformers
``all-MiniLM-L6-v2`` model that encodes setup narratives into 384-dimensional
vectors.

Usage example::

    from services.algorag.embedding_models import get_embedding_model

    model = get_embedding_model()
    vector = model.encode("Price swept Asian low before reversing bullish.")
    # vector.shape == (384,)

    batch = model.encode_batch(["Narrative A.", "Narrative B."])
    # batch.shape == (2, 384)
"""

from __future__ import annotations

import logging
from typing import List, Optional

import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MODEL_NAME: str = "sentence-transformers/all-MiniLM-L6-v2"
_NARRATIVE_DIM: int = 384

# Module-level cache — the model is loaded once and reused across calls.
_model_cache: Optional["NarrativeEmbeddingModel"] = None


# ---------------------------------------------------------------------------
# Model class
# ---------------------------------------------------------------------------


class NarrativeEmbeddingModel:
    """Wrapper around the SBERT ``all-MiniLM-L6-v2`` model.

    The underlying ``SentenceTransformer`` is loaded lazily on first access and
    cached at the instance level.  Use :func:`get_embedding_model` to obtain the
    module-level singleton rather than constructing this class directly.

    Attributes:
        _model_name: HuggingFace model identifier.
        _sbert: The underlying ``SentenceTransformer`` instance (loaded on
            first call to ``encode`` or ``encode_batch``).
    """

    def __init__(self, model_name: str = _MODEL_NAME) -> None:
        self._model_name: str = model_name
        self._sbert = None  # lazy load

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load(self) -> None:
        """Load the SentenceTransformer model if not already loaded."""
        if self._sbert is not None:
            return
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore

            logger.info("Loading embedding model '%s' …", self._model_name)
            self._sbert = SentenceTransformer(self._model_name)
            logger.info("Embedding model loaded successfully.")
        except Exception as exc:
            raise RuntimeError(
                f"Failed to load embedding model '{self._model_name}'. "
                "Ensure sentence-transformers is installed and the model is "
                f"accessible: {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def encode(self, text: str) -> np.ndarray:
        """Encode a single narrative text into a 384-dim float32 vector.

        Args:
            text: The narrative string to encode.

        Returns:
            A 1-D numpy array of shape ``(384,)`` with dtype ``float32``.
        """
        self._load()
        result: np.ndarray = self._sbert.encode(
            text,
            convert_to_numpy=True,
            normalize_embeddings=False,
        )
        # Ensure we always return a 1-D array even if the model returns a 2-D
        # array for a single input.
        return np.asarray(result, dtype=np.float32).flatten()

    def encode_batch(self, texts: List[str]) -> np.ndarray:
        """Encode a list of narrative texts into a (N, 384) float32 array.

        Args:
            texts: A list of N narrative strings to encode.

        Returns:
            A 2-D numpy array of shape ``(N, 384)`` with dtype ``float32``.
        """
        self._load()
        result: np.ndarray = self._sbert.encode(
            texts,
            convert_to_numpy=True,
            normalize_embeddings=False,
            batch_size=32,
        )
        return np.asarray(result, dtype=np.float32)


# ---------------------------------------------------------------------------
# Singleton accessor
# ---------------------------------------------------------------------------


def get_embedding_model() -> NarrativeEmbeddingModel:
    """Return the module-level cached :class:`NarrativeEmbeddingModel` instance.

    The model is instantiated on the first call and reused on all subsequent
    calls, avoiding the overhead of loading the weights multiple times.

    Returns:
        The singleton :class:`NarrativeEmbeddingModel` instance.
    """
    global _model_cache
    if _model_cache is None:
        _model_cache = NarrativeEmbeddingModel()
    return _model_cache
