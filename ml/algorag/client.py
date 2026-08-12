"""
AlgoRAG HTTP client for ML services.

This module provides an async HTTP client with connection pooling, retry logic,
and timeout handling for communicating with the AlgoRAG service.

Usage:
    async with AlgoRAGClient() as client:
        result = await client.retrieve(request_data)
        
    # Graceful degradation
    async with AlgoRAGClient() as client:
        result = await client.retrieve_with_fallback(request_data)
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from typing import Any, Dict, Optional
from aiohttp import ClientSession, ClientTimeout, ClientError
from aiohttp.web import Response

logger = logging.getLogger(__name__)


class AlgoRAGError(Exception):
    """Base exception for AlgoRAG client errors."""
    pass


class AlgoRAGTimeout(AlgoRAGError):
    """Exception raised when AlgoRAG requests timeout."""
    pass


class AlgoRAGClient:
    """
    Async HTTP client for AlgoRAG service with retry logic and connection pooling.
    
    Features:
    - Connection pooling via aiohttp ClientSession
    - Configurable retry logic with exponential backoff
    - Timeout handling
    - Graceful degradation support
    - Automatic JSON serialization of datetime objects
    """
    
    def __init__(
        self,
        base_url: str = "http://localhost:8003",
        timeout: float = 5.0,
        max_retries: int = 3,
        retry_delay: float = 0.5
    ):
        """
        Initialize AlgoRAG client.
        
        Args:
            base_url: AlgoRAG service base URL
            timeout: Request timeout in seconds
            max_retries: Maximum number of retry attempts
            retry_delay: Initial delay between retries in seconds
        """
        self.base_url = base_url
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self._session: Optional[ClientSession] = None
    
    async def __aenter__(self) -> AlgoRAGClient:
        """Create aiohttp session for connection pooling."""
        timeout = ClientTimeout(total=self.timeout)
        self._session = ClientSession(timeout=timeout)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Close aiohttp session."""
        if self._session:
            await self._session.close()
    
    def _serialize_datetime(self, data: Dict[str, Any]) -> str:
        """
        Serialize request data to JSON, handling datetime objects.
        
        Args:
            data: Request data dictionary
            
        Returns:
            JSON string with datetime objects serialized to ISO format
        """
        def datetime_serializer(obj):
            if isinstance(obj, datetime):
                return obj.isoformat()
            raise TypeError(f"Object of type {type(obj)} is not JSON serializable")
        
        return json.dumps(data, default=datetime_serializer)
    
    async def retrieve(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Retrieve similar historical setups from AlgoRAG service.
        
        Args:
            request_data: Request parameters including instrument, timestamp, etc.
            
        Returns:
            AlgoRAG response with similar_setups, rag_metrics, and query_time_ms
            
        Raises:
            AlgoRAGError: On request failure after exhausting retries
            AlgoRAGTimeout: On request timeout
        """
        if not self._session:
            raise RuntimeError("Client must be used as async context manager")
        
        url = f"{self.base_url}/rag/retrieve"
        data = self._serialize_datetime(request_data)
        headers = {"Content-Type": "application/json"}
        
        last_exception = None
        
        for attempt in range(self.max_retries):
            try:
                async with self._session.post(url, data=data, headers=headers) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        error_text = await response.text()
                        raise AlgoRAGError(f"HTTP {response.status}: {error_text}")
                        
            except asyncio.TimeoutError as e:
                last_exception = AlgoRAGTimeout(f"Request timed out after {self.timeout}s")
                logger.warning(f"AlgoRAG request timeout (attempt {attempt + 1}/{self.max_retries})")
                
            except ClientError as e:
                last_exception = AlgoRAGError(f"Network error: {str(e)}")
                logger.warning(f"AlgoRAG network error (attempt {attempt + 1}/{self.max_retries}): {e}")
            
            # Wait before retrying (except on last attempt)
            if attempt < self.max_retries - 1:
                await asyncio.sleep(self.retry_delay * (2 ** attempt))  # Exponential backoff
        
        # All retries exhausted
        if isinstance(last_exception, AlgoRAGTimeout):
            raise last_exception
        else:
            raise AlgoRAGError(f"Request failed after {self.max_retries} retries: {last_exception}")
    
    async def retrieve_with_fallback(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Retrieve similar setups with graceful degradation on errors.
        
        This method implements the graceful degradation pattern required by FR-RAG-5
        and NFR-RAG-3. When AlgoRAG is unavailable, it returns empty metrics so the
        ML pipeline can continue functioning.
        
        Args:
            request_data: Request parameters
            
        Returns:
            AlgoRAG response or fallback empty metrics on error
        """
        try:
            return await self.retrieve(request_data)
        except Exception as e:
            logger.warning(f"AlgoRAG unavailable, using fallback: {e}")
            
            # Return empty metrics for graceful degradation
            return {
                "similar_setups": [],
                "rag_metrics": {
                    "avg_r_multiple_similar": 0.0,
                    "win_rate_similar": 0.0,
                    "sample_size": 0,
                    "max_similarity_score": 0.0,
                    "avg_confluence_count": 0.0
                },
                "query_time_ms": 0.0
            }