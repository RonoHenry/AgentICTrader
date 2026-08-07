"""
Tests for AlgoRAG client library.

Following TDD methodology:
1. RED: Write failing tests for desired behavior
2. GREEN: Implement minimal code to make tests pass
3. REFACTOR: Clean up while keeping tests green
"""
from __future__ import annotations

import asyncio
import json
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from aiohttp import ClientError, ClientTimeout, ClientSession
from aiohttp.web import Response

from ml.algorag.client import AlgoRAGClient, AlgoRAGError, AlgoRAGTimeout


class TestAlgoRAGClient:
    """Unit tests for AlgoRAG HTTP client."""
    
    def test_client_initialization(self):
        """Test client initializes with correct default configuration."""
        client = AlgoRAGClient()
        
        assert client.base_url == "http://localhost:8003"
        assert client.timeout == 5.0
        assert client.max_retries == 3
        assert client.retry_delay == 0.5
        assert client._session is None
    
    def test_client_initialization_with_custom_config(self):
        """Test client accepts custom configuration."""
        client = AlgoRAGClient(
            base_url="http://algorag:8003",
            timeout=10.0,
            max_retries=5,
            retry_delay=1.0
        )
        
        assert client.base_url == "http://algorag:8003"
        assert client.timeout == 10.0
        assert client.max_retries == 5
        assert client.retry_delay == 1.0
    
    @pytest.mark.asyncio
    async def test_context_manager_creates_session(self):
        """Test client creates and closes aiohttp session properly."""
        client = AlgoRAGClient()
        
        async with client:
            assert client._session is not None
            assert isinstance(client._session, ClientSession)
            assert not client._session.closed
        
        # Session should be closed after context exit
        assert client._session.closed
    
    @pytest.mark.asyncio
    async def test_retrieve_success(self):
        """Test successful retrieval with mock response."""
        mock_response_data = {
            "similar_setups": [
                {
                    "trade_id": "TRD-001",
                    "timestamp": "2024-03-15T09:15:00Z",
                    "instrument": "EURUSD",
                    "time_window": "LONDON_KILLZONE",
                    "htf_open_bias": "BULLISH",
                    "confluence_count": 5,
                    "outcome_result": "WIN",
                    "outcome_r_multiple": 4.2,
                    "narrative": "Price swept Asian low before bullish continuation",
                    "similarity_score": 0.94,
                    "final_score": 0.97,
                    "full_setup": {}
                }
            ],
            "rag_metrics": {
                "avg_r_multiple_similar": 3.6,
                "win_rate_similar": 0.85,
                "sample_size": 5,
                "max_similarity_score": 0.94,
                "avg_confluence_count": 4.8
            },
            "query_time_ms": 45.2
        }
        
        with patch('aiohttp.ClientSession.post') as mock_post:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json = AsyncMock(return_value=mock_response_data)
            mock_post.return_value.__aenter__.return_value = mock_response
            
            client = AlgoRAGClient()
            
            request_data = {
                "instrument": "EURUSD",
                "timestamp": datetime(2024, 5, 6, 9, 15, 0, tzinfo=timezone.utc),
                "time_window": "LONDON_KILLZONE",
                "htf_open_bias": "BULLISH",
                "narrative": "Current setup narrative",
                "top_k": 10
            }
            
            async with client:
                result = await client.retrieve(request_data)
            
            assert result == mock_response_data
            mock_post.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_retrieve_with_retry_on_network_error(self):
        """Test client retries on network failures."""
        with patch('aiohttp.ClientSession.post') as mock_post:
            # Configure successful response
            success_response = AsyncMock()
            success_response.status = 200
            success_response.json = AsyncMock(return_value={"similar_setups": [], "rag_metrics": {}, "query_time_ms": 30})
            success_context = AsyncMock()
            success_context.__aenter__ = AsyncMock(return_value=success_response)
            
            # First two calls fail, third succeeds
            mock_post.side_effect = [
                ClientError("Connection failed"),
                ClientError("Connection failed"),
                success_context
            ]
            
            client = AlgoRAGClient(retry_delay=0.1)  # Fast retry for testing
            
            async with client:
                # This should succeed after 2 retries
                result = await client.retrieve({
                    "instrument": "EURUSD",
                    "timestamp": datetime.now(timezone.utc)
                })
            
            assert mock_post.call_count == 3
            assert result["similar_setups"] == []
    
    @pytest.mark.asyncio
    async def test_retrieve_exhausts_retries(self):
        """Test client raises error after exhausting retries."""
        with patch('aiohttp.ClientSession.post') as mock_post:
            mock_post.side_effect = ClientError("Persistent network failure")
            
            client = AlgoRAGClient(max_retries=2, retry_delay=0.1)
            
            async with client:
                with pytest.raises(AlgoRAGError) as exc_info:
                    await client.retrieve({
                        "instrument": "EURUSD", 
                        "timestamp": datetime.now(timezone.utc)
                    })
                
                assert "failed after 2 retries" in str(exc_info.value)
            
            assert mock_post.call_count == 2
    
    @pytest.mark.asyncio
    async def test_retrieve_timeout_error(self):
        """Test client handles timeout errors properly."""
        with patch('aiohttp.ClientSession.post') as mock_post:
            mock_post.side_effect = asyncio.TimeoutError()
            
            client = AlgoRAGClient(timeout=1.0, max_retries=1, retry_delay=0.1)
            
            async with client:
                with pytest.raises(AlgoRAGTimeout) as exc_info:
                    await client.retrieve({
                        "instrument": "EURUSD",
                        "timestamp": datetime.now(timezone.utc)
                    })
                
                assert "timed out" in str(exc_info.value).lower()
    
    @pytest.mark.asyncio
    async def test_retrieve_http_error_status(self):
        """Test client handles HTTP error status codes."""
        with patch('aiohttp.ClientSession.post') as mock_post:
            mock_response = AsyncMock()
            mock_response.status = 503
            mock_response.text = AsyncMock(return_value="Service unavailable")
            mock_post.return_value.__aenter__.return_value = mock_response
            
            client = AlgoRAGClient(max_retries=1, retry_delay=0.1)
            
            async with client:
                with pytest.raises(AlgoRAGError) as exc_info:
                    await client.retrieve({
                        "instrument": "EURUSD",
                        "timestamp": datetime.now(timezone.utc)
                    })
                
                assert "503" in str(exc_info.value)
                assert "Service unavailable" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_retrieve_graceful_degradation(self):
        """Test graceful degradation returns empty metrics on error."""
        client = AlgoRAGClient()
        
        with patch.object(client, 'retrieve') as mock_retrieve:
            mock_retrieve.side_effect = AlgoRAGError("Service unavailable")
            
            async with client:
                result = await client.retrieve_with_fallback({
                    "instrument": "EURUSD",
                    "timestamp": datetime.now(timezone.utc)
                })
            
            # Should return empty fallback metrics
            assert result["rag_metrics"]["avg_r_multiple_similar"] == 0.0
            assert result["rag_metrics"]["win_rate_similar"] == 0.0
            assert result["rag_metrics"]["sample_size"] == 0
            assert result["rag_metrics"]["max_similarity_score"] == 0.0
            assert result["similar_setups"] == []
    
    @pytest.mark.asyncio
    async def test_connection_pooling(self):
        """Test client reuses connection session properly."""
        client = AlgoRAGClient()
        
        async with client:
            session1 = client._session
            
            # Multiple requests should reuse same session
            with patch.object(client._session, 'post') as mock_post:
                mock_response = AsyncMock()
                mock_response.status = 200
                mock_response.json = AsyncMock(return_value={"similar_setups": [], "rag_metrics": {}, "query_time_ms": 30})
                mock_post.return_value.__aenter__.return_value = mock_response
                
                await client.retrieve({"instrument": "EURUSD", "timestamp": datetime.now(timezone.utc)})
                await client.retrieve({"instrument": "GBPUSD", "timestamp": datetime.now(timezone.utc)})
                
                # Same session used for both requests
                session2 = client._session
                assert session1 is session2
                assert mock_post.call_count == 2
    
    @pytest.mark.asyncio
    async def test_request_data_serialization(self):
        """Test proper serialization of datetime objects in requests."""
        with patch('aiohttp.ClientSession.post') as mock_post:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json = AsyncMock(return_value={"similar_setups": [], "rag_metrics": {}, "query_time_ms": 30})
            mock_post.return_value.__aenter__.return_value = mock_response
            
            client = AlgoRAGClient()
            
            timestamp = datetime(2024, 5, 6, 9, 15, 0, tzinfo=timezone.utc)
            request_data = {
                "instrument": "EURUSD",
                "timestamp": timestamp,
                "narrative": "Test narrative"
            }
            
            async with client:
                await client.retrieve(request_data)
            
            # Verify datetime was serialized properly
            call_args = mock_post.call_args
            sent_data = json.loads(call_args[1]['data'])
            assert sent_data['timestamp'] == "2024-05-06T09:15:00+00:00"
            assert sent_data['instrument'] == "EURUSD"
            assert sent_data['narrative'] == "Test narrative"


class TestAlgoRAGErrorHandling:
    """Test error handling and graceful degradation."""
    
    def test_algorag_error_creation(self):
        """Test custom exception creation."""
        error = AlgoRAGError("Test error message")
        assert str(error) == "Test error message"
        assert isinstance(error, Exception)
    
    def test_algorag_timeout_creation(self):
        """Test custom timeout exception creation."""
        error = AlgoRAGTimeout("Request timed out after 5.0s")
        assert str(error) == "Request timed out after 5.0s"
        assert isinstance(error, AlgoRAGError)  # Should inherit from AlgoRAGError