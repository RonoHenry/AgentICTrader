"""
Qdrant client wrapper with connection pooling, collection management,
and retry logic. All configuration is read from services.algorag.config.
"""

import asyncio
import logging
from typing import Any, List, Optional

from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models as qmodels
from qdrant_client.http.exceptions import UnexpectedResponse

from services.algorag.config import QdrantConfig, settings

logger = logging.getLogger(__name__)

VECTOR_DIM = 528


class QdrantConnectionError(Exception):
    """Raised when the Qdrant client cannot connect or a retried operation fails."""


class QdrantClientWrapper:
    """
    Thin wrapper around AsyncQdrantClient that adds:
    - Connection pooling (singleton client per wrapper instance)
    - Idempotent collection creation
    - Automatic retry on transient failures (up to config.max_retries)
    - Typed error surface (QdrantConnectionError)
    """

    def __init__(self, config: Optional[QdrantConfig] = None) -> None:
        self._config: QdrantConfig = config or settings.qdrant
        self._client: Optional[AsyncQdrantClient] = None

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def get_client(self) -> AsyncQdrantClient:
        """Return the singleton AsyncQdrantClient, creating it if needed."""
        if self._client is None:
            self._client = AsyncQdrantClient(
                host=self._config.host,
                port=self._config.port,
                timeout=self._config.timeout,
            )
        return self._client

    async def close(self) -> None:
        """Close the underlying client connection."""
        if self._client is not None:
            await self._client.close()
            self._client = None

    async def is_healthy(self) -> bool:
        """Return True if Qdrant responds to a ping."""
        try:
            await self.get_client().get_collections()
            return True
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Collection management
    # ------------------------------------------------------------------

    async def ensure_collection(
        self,
        collection_name: Optional[str] = None,
        vector_size: int = VECTOR_DIM,
    ) -> None:
        """
        Create the collection if it does not yet exist (idempotent).
        Uses cosine distance and creates payload indexes for fast filtering.
        """
        name = collection_name or self._config.collection
        client = self.get_client()
        try:
            await client.get_collection(name)
            logger.info("Collection '%s' already exists — skipping creation", name)
        except Exception:
            logger.info("Creating collection '%s' (%d-dim, cosine)", name, vector_size)
            await client.create_collection(
                collection_name=name,
                vectors_config=qmodels.VectorParams(
                    size=vector_size,
                    distance=qmodels.Distance.COSINE,
                ),
            )
            # Create payload indexes for common metadata filters
            for field in ("instrument", "time_window", "htf_open_bias", "outcome_result"):
                await client.create_payload_index(
                    collection_name=name,
                    field_name=field,
                    field_schema=qmodels.PayloadSchemaType.KEYWORD,
                )

    # ------------------------------------------------------------------
    # CRUD helpers
    # ------------------------------------------------------------------

    async def upsert(
        self,
        points: List[qmodels.PointStruct],
        collection_name: Optional[str] = None,
    ) -> None:
        """Upsert one or more points into the collection with retry."""
        name = collection_name or self._config.collection
        await self._with_retry(
            self.get_client().upsert,
            collection_name=name,
            points=points,
        )

    async def search(
        self,
        query_vector: List[float],
        collection_name: Optional[str] = None,
        query_filter: Optional[qmodels.Filter] = None,
        limit: int = 10,
    ) -> List[Any]:
        """Run a cosine similarity search with optional metadata filter."""
        name = collection_name or self._config.collection
        return await self._with_retry(
            self.get_client().search,
            collection_name=name,
            query_vector=query_vector,
            query_filter=query_filter,
            limit=limit,
            with_payload=True,
        )

    async def delete(
        self,
        point_ids: List[str],
        collection_name: Optional[str] = None,
    ) -> None:
        """Delete points by their UUIDs."""
        name = collection_name or self._config.collection
        await self._with_retry(
            self.get_client().delete,
            collection_name=name,
            points_selector=qmodels.PointIdsList(points=point_ids),
        )

    async def count(self, collection_name: Optional[str] = None) -> int:
        """Return the number of vectors indexed in the collection."""
        name = collection_name or self._config.collection
        try:
            info = await self.get_client().get_collection(name)
            return info.points_count or 0
        except Exception:
            return 0

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _with_retry(self, fn, *args, **kwargs) -> Any:
        """Call `fn(*args, **kwargs)`, retrying up to max_retries on failure."""
        max_retries: int = self._config.max_retries
        retry_backoff: float = self._config.retry_backoff
        last_exc: Optional[Exception] = None
        for attempt in range(1, max_retries + 1):
            try:
                return await fn(*args, **kwargs)
            except Exception as exc:
                last_exc = exc
                if attempt < max_retries:
                    wait = retry_backoff * attempt
                    logger.warning(
                        "Qdrant operation failed (attempt %d/%d), retrying in %.1fs: %s",
                        attempt,
                        max_retries,
                        wait,
                        exc,
                    )
                    if wait > 0:
                        await asyncio.sleep(wait)
        raise QdrantConnectionError(
            f"Qdrant operation failed after {max_retries} attempts"
        ) from last_exc
